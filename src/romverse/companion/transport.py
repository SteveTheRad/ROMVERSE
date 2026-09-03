"""Local-network Companion pairing transport.

The endpoint is intentionally limited to pairing state.  Telemetry and any
future command APIs must be added as separate, Guardian-reviewed contracts.
"""

from __future__ import annotations

import json
import os
import socket
import ssl
import threading
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from romverse.companion.pairing import PairingCode, PairingSessionBroker
from romverse.companion.security import LinkSecurityError, LinkTlsIdentity
from romverse.companion.telemetry import CompanionTelemetry, RemoteCompanionSnapshot


class CompanionHTTPServer(ThreadingHTTPServer):
    """HTTP server whose request threads cannot hold interpreter shutdown hostage."""

    # Winsock's SO_REUSEADDR can allow two live servers to claim the same
    # address, which risks pairing with a different local ROMVERSE instance.
    # POSIX reuse remains useful for promptly reopening a recently closed port;
    # Windows instead gets an exclusive bind and falls back to an ephemeral
    # port when another instance already owns the default.
    allow_reuse_address = os.name != "nt"
    daemon_threads = True
    block_on_close = False

    def server_bind(self) -> None:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class CompanionTransport:
    DISCOVERY_PORT = 45678
    DEFAULT_PORT = 8765
    PROTOCOL_VERSION = 3
    # Remember one explicitly approved Companion for thirty days.  The Desktop
    # stores only the bearer-token digest and Reset Pairing revokes it early.
    SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
    MAX_PAIRING_BODY_BYTES = 1_024
    MAX_REMOTE_TELEMETRY_BYTES = 16_384

    def __init__(
        self,
        pairing_provider: Callable[[], PairingCode | None],
        telemetry_provider: Callable[[], CompanionTelemetry] | None = None,
        identity_root: Path | None = None,
    ) -> None:
        self._pairing_provider = pairing_provider
        self._telemetry_provider = telemetry_provider or CompanionTelemetry
        remembered_session = (
            identity_root / "remembered-session.romverse" if identity_root is not None else None
        )
        self._sessions = PairingSessionBroker(
            self.SESSION_TTL_SECONDS,
            state_path=remembered_session,
            state_boundary=identity_root,
        )
        self._remote_lock = threading.Lock()
        self._remote_snapshot: RemoteCompanionSnapshot | None = None
        self._remote_received_at: datetime | None = None
        transport = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                path = urlsplit(self.path).path
                if path == "/pair":
                    self._pair()
                    return
                if path == "/companion/telemetry":
                    self._receive_remote_telemetry()
                    return
                self.send_error(404)

            def _pair(self) -> None:
                body = self._read_json(transport.MAX_PAIRING_BODY_BYTES)
                if body is None:
                    return
                candidate = body.get("code")
                if not isinstance(candidate, str):
                    self._respond({"status": "invalid_request"}, status=400)
                    return
                request_id = transport._sessions.request(
                    transport._pairing_provider(), candidate, self.client_address[0]
                )
                self._respond(
                    {
                        "protocol_version": transport.PROTOCOL_VERSION,
                        "status": "pending" if request_id else "rejected",
                        "request_id": request_id,
                    }
                )

            def _receive_remote_telemetry(self) -> None:
                authorization = self.headers.get("Authorization", "")
                token = authorization.removeprefix("Bearer ").strip()
                if not transport._sessions.authorize(token):
                    self._respond(
                        {
                            "protocol_version": transport.PROTOCOL_VERSION,
                            "status": "unauthorized",
                        },
                        status=401,
                    )
                    return
                body = self._read_json(transport.MAX_REMOTE_TELEMETRY_BYTES)
                if body is None:
                    return
                try:
                    snapshot = RemoteCompanionSnapshot.from_mapping(body)
                    snapshot.verify_freshness(int(datetime.now(UTC).timestamp() * 1_000))
                except (TypeError, ValueError, OverflowError) as error:
                    self._respond(
                        {
                            "protocol_version": transport.PROTOCOL_VERSION,
                            "status": "invalid_telemetry",
                            "detail": str(error),
                        },
                        status=400,
                    )
                    return
                transport._record_remote_snapshot(snapshot)
                self._respond(
                    {
                        "protocol_version": transport.PROTOCOL_VERSION,
                        "status": "accepted",
                        "privacy_scope": snapshot.privacy_scope,
                    },
                    status=202,
                )

            def _read_json(self, maximum: int) -> dict[str, object] | None:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self._respond({"status": "invalid_content_length"}, status=400)
                    return None
                if length <= 0:
                    self._respond({"status": "empty_request"}, status=400)
                    return None
                if length > maximum:
                    self._respond({"status": "request_too_large"}, status=413)
                    return None
                try:
                    body = json.loads(self.rfile.read(length))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._respond({"status": "invalid_json"}, status=400)
                    return None
                if not isinstance(body, dict):
                    self._respond({"status": "invalid_request"}, status=400)
                    return None
                return body

            def do_GET(self) -> None:  # noqa: N802
                path = urlsplit(self.path).path
                if path == "/telemetry":
                    authorization = self.headers.get("Authorization", "")
                    token = authorization.removeprefix("Bearer ").strip()
                    if not transport._sessions.authorize(token):
                        self._respond(
                            {
                                "protocol_version": transport.PROTOCOL_VERSION,
                                "status": "unauthorized",
                            },
                            status=401,
                        )
                        return
                    self._respond(transport._telemetry_provider().to_mapping())
                    return
                if path != "/status":
                    self.send_error(404)
                    return
                request_id = self.headers.get("X-ROMVERSE-Pairing-Request", "").strip()
                session = transport._sessions.status(request_id)
                payload = {
                    "protocol_version": transport.PROTOCOL_VERSION,
                    "status": session.state,
                }
                if session.session_token:
                    payload["session_token"] = session.session_token
                    payload["expires_in_seconds"] = session.expires_in_seconds
                response_status = 403 if session.state == "rejected" else 200
                self._respond(payload, status=response_status)

            def _respond(self, payload: dict[str, object], *, status: int = 200) -> None:
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Strict-Transport-Security", "max-age=31536000")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_args: object) -> None:
                return

        self._server: ThreadingHTTPServer | None = None
        self._identity: LinkTlsIdentity | None = None
        self._temporary_identity: TemporaryDirectory[str] | None = None
        self._availability_error = ""
        server: ThreadingHTTPServer | None = None
        try:
            if identity_root is None:
                self._temporary_identity = TemporaryDirectory(prefix="romverse-link-")
                identity_root = Path(self._temporary_identity.name)
            identity = LinkTlsIdentity.load_or_create(identity_root)
            try:
                server = CompanionHTTPServer(("0.0.0.0", self.DEFAULT_PORT), Handler)
            except OSError:
                # Keep the app usable if another ROMVERSE instance owns the default port.
                server = CompanionHTTPServer(("0.0.0.0", 0), Handler)
            server.socket = identity.server_context().wrap_socket(server.socket, server_side=True)
            self._identity = identity
            self._server = server
        except (LinkSecurityError, OSError, ssl.SSLError) as error:
            # Wireless ROMVERSE Link is optional. An invalid identity, local firewall,
            # sandbox, or restricted account must not prevent the rest of ROMVERSE opening.
            if server is not None:
                with suppress(OSError):
                    server.server_close()
            self._availability_error = str(error) or error.__class__.__name__
        self._thread: threading.Thread | None = None
        self._discovery_stop = threading.Event()
        self._discovery_thread: threading.Thread | None = None
        self._close_lock = threading.Lock()
        self._closed = False

    @property
    def port(self) -> int:
        return int(self._server.server_port) if self._server is not None else 0

    @property
    def available(self) -> bool:
        return self._server is not None

    @property
    def availability_error(self) -> str:
        return self._availability_error

    @property
    def certificate_sha256(self) -> str:
        return self._identity.certificate_sha256 if self._identity is not None else ""

    @property
    def certificate_path(self) -> Path | None:
        return self._identity.certificate_path if self._identity is not None else None

    @property
    def safety_code(self) -> str:
        return self._identity.safety_code if self._identity is not None else ""

    @property
    def discovery_payload(self) -> dict[str, object]:
        return {
            "service": "ROMVERSE_COMPANION",
            "port": self.port,
            "scheme": "https",
            "protocol_version": self.PROTOCOL_VERSION,
            "certificate_sha256": self.certificate_sha256,
            "safety_code": self.safety_code,
        }

    @property
    def pending(self) -> bool:
        return self._sessions.pending

    @property
    def approved(self) -> bool:
        return self._sessions.approved

    @property
    def session_expires_in_seconds(self) -> int:
        return self._sessions.expires_in_seconds

    @property
    def latest_remote_snapshot(self) -> RemoteCompanionSnapshot | None:
        with self._remote_lock:
            return self._remote_snapshot

    @property
    def remote_snapshot_received_at(self) -> datetime | None:
        with self._remote_lock:
            return self._remote_received_at

    def approve(self) -> bool:
        return self._sessions.approve()

    def reset(self) -> None:
        self._sessions.reset()
        with self._remote_lock:
            self._remote_snapshot = None
            self._remote_received_at = None

    def start(self) -> None:
        if self._server is None or self._thread is not None or self._closed:
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="romverse-companion-https",
            daemon=True,
        )
        self._thread.start()
        self._discovery_thread = threading.Thread(
            target=self._broadcast,
            name="romverse-companion-discovery",
            daemon=True,
        )
        self._discovery_thread.start()

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
            self._discovery_stop.set()
            if self._server is not None:
                if self._thread is not None and self._thread.is_alive():
                    self._server.shutdown()
                self._server.server_close()
            if self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=2.0)
            if self._discovery_thread is not None and self._discovery_thread.is_alive():
                self._discovery_thread.join(timeout=3.0)
            if self._temporary_identity is not None:
                self._temporary_identity.cleanup()
                self._temporary_identity = None

    @property
    def running(self) -> bool:
        return bool(self._thread is not None and self._thread.is_alive())

    def _broadcast(self) -> None:
        if not self.available:
            return
        payload = json.dumps(self.discovery_payload, separators=(",", ":")).encode()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as broadcaster:
            broadcaster.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            while not self._discovery_stop.is_set():
                with suppress(OSError):
                    broadcaster.sendto(payload, ("255.255.255.255", self.DISCOVERY_PORT))
                with suppress(OSError):
                    # Common /22 home-LAN fallback used by the development network.
                    broadcaster.sendto(payload, ("192.168.7.255", self.DISCOVERY_PORT))
                self._discovery_stop.wait(2.0)

    def _record_remote_snapshot(self, snapshot: RemoteCompanionSnapshot) -> None:
        with self._remote_lock:
            self._remote_snapshot = snapshot
            self._remote_received_at = datetime.now(UTC)
