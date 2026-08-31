from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
    remove_regular_file,
)


@dataclass(frozen=True, slots=True)
class PairingCode:
    code: str
    created_at: str
    expires_at: str

    @property
    def expired(self) -> bool:
        return datetime.now(UTC) >= datetime.fromisoformat(self.expires_at)


def create_pairing_code(ttl_minutes: int = 10) -> PairingCode:
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=max(1, ttl_minutes))
    code = f"{secrets.randbelow(1_000_000):06d}"
    return PairingCode(code, now.isoformat(), expires.isoformat())


def verify_pairing_code(pairing: PairingCode, candidate: str) -> bool:
    """Validate a user-entered code without ever accepting an expired session."""

    normalized = "".join(candidate.split())
    return (
        len(normalized) == 6
        and normalized.isdecimal()
        and not pairing.expired
        and secrets.compare_digest(normalized, pairing.code)
    )


@dataclass(frozen=True, slots=True)
class PairingSessionStatus:
    state: str
    session_token: str = ""
    expires_in_seconds: int = 0


class PairingSessionBroker:
    """One-request, remembered-session authorization for local Companion telemetry.

    Only a SHA-256 digest of the high-entropy bearer token is persisted.  This
    lets an explicitly approved phone reconnect after Desktop or the network
    restarts without leaving a reusable credential in the Desktop state file.
    Reset and expiry revoke the remembered session immediately.
    """

    MAX_FAILED_ATTEMPTS = 8
    FAILURE_WINDOW_SECONDS = 60
    STATE_SCHEMA_VERSION = 2
    LEGACY_STATE_SCHEMA_VERSION = 1
    MAX_STATE_BYTES = 64 * 1024
    TOKEN_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")

    def __init__(
        self,
        ttl_seconds: int = 12 * 60 * 60,
        clock: Callable[[], float] = time.time,
        state_path: Path | None = None,
        state_boundary: Path | None = None,
    ) -> None:
        self._ttl_seconds = max(60, ttl_seconds)
        self._clock = clock
        self._state_path = state_path
        self._state_boundary = state_boundary or (
            state_path.parent if state_path is not None else None
        )
        self._lock = threading.Lock()
        self._pending_request_id = ""
        self._session_token = ""
        self._session_token_digest = ""
        self._session_expires = 0.0
        self._failed_attempts: dict[str, list[float]] = {}
        self._load_remembered_session()

    def request(
        self,
        pairing: PairingCode | None,
        candidate: str,
        client_id: str = "local-client",
    ) -> str:
        normalized_client = client_id.strip()[:128] or "unknown-client"
        with self._lock:
            now = self._clock()
            failures = [
                attempt
                for attempt in self._failed_attempts.get(normalized_client, ())
                if now - attempt < self.FAILURE_WINDOW_SECONDS
            ]
            if len(failures) >= self.MAX_FAILED_ATTEMPTS:
                self._failed_attempts[normalized_client] = failures
                return ""
            if pairing is None or not verify_pairing_code(pairing, candidate):
                failures.append(now)
                self._failed_attempts[normalized_client] = failures
                return ""
            self._failed_attempts.pop(normalized_client, None)
            self._pending_request_id = secrets.token_urlsafe(24)
            self._clear_session_locked()
            return self._pending_request_id

    def approve(self) -> bool:
        with self._lock:
            if not self._pending_request_id:
                return False
            self._session_token = secrets.token_urlsafe(32)
            self._session_token_digest = self._token_digest(self._session_token)
            self._session_expires = self._clock() + self._ttl_seconds
            try:
                self._persist_session_locked()
            except LocalStoreError:
                self._clear_session_locked()
                return False
            return True

    def status(self, request_id: str) -> PairingSessionStatus:
        with self._lock:
            if not request_id or not secrets.compare_digest(request_id, self._pending_request_id):
                return PairingSessionStatus("rejected")
            if not self._session_active_locked():
                return PairingSessionStatus("pending")
            return PairingSessionStatus(
                "approved",
                self._session_token,
                max(0, int(self._session_expires - self._clock())),
            )

    def authorize(self, candidate: str) -> bool:
        with self._lock:
            return (
                self._session_active_locked()
                and bool(candidate)
                and secrets.compare_digest(
                    self._token_digest(candidate), self._session_token_digest
                )
            )

    @property
    def pending(self) -> bool:
        with self._lock:
            return bool(self._pending_request_id) and not self._session_active_locked()

    @property
    def approved(self) -> bool:
        with self._lock:
            return self._session_active_locked()

    def reset(self) -> None:
        with self._lock:
            self._pending_request_id = ""
            self._clear_session_locked()
            self._failed_attempts.clear()

    def _session_active_locked(self) -> bool:
        if self._session_token_digest and self._clock() >= self._session_expires:
            self._clear_session_locked()
        return bool(self._session_token_digest)

    @staticmethod
    def _token_digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _clear_session_locked(self) -> None:
        self._session_token = ""
        self._session_token_digest = ""
        self._session_expires = 0.0
        self._remove_state_safely()

    def _load_remembered_session(self) -> None:
        if (
            self._state_path is None
            or self._state_boundary is None
            or not os.path.lexists(self._state_path)
        ):
            return
        try:
            payload = read_json_object(
                self._state_path,
                boundary=self._state_boundary,
                maximum_bytes=self.MAX_STATE_BYTES,
            )
            schema_version = payload.get("schema_version")
            if schema_version == self.STATE_SCHEMA_VERSION:
                if set(payload) != {
                    "schema_version",
                    "token_sha256",
                    "expires_at_epoch_seconds",
                    "record_digest",
                }:
                    raise ValueError("remembered session has an invalid shape")
                unsigned = dict(payload)
                stored_digest = unsigned.pop("record_digest")
                if not isinstance(stored_digest, str) or not secrets.compare_digest(
                    stored_digest, _digest(unsigned)
                ):
                    raise ValueError("remembered session digest is invalid")
            elif schema_version == self.LEGACY_STATE_SCHEMA_VERSION:
                if set(payload) != {
                    "schema_version",
                    "token_sha256",
                    "expires_at_epoch_seconds",
                }:
                    raise ValueError("legacy remembered session has an invalid shape")
            else:
                raise ValueError("remembered session schema is unsupported")
            digest = payload["token_sha256"]
            raw_expires = payload["expires_at_epoch_seconds"]
            if (
                isinstance(raw_expires, bool)
                or type(raw_expires) not in {int, float}
                or not math.isfinite(raw_expires)
            ):
                raise ValueError("remembered session expiry is invalid")
            if schema_version == self.STATE_SCHEMA_VERSION and type(raw_expires) is not int:
                raise ValueError("current remembered session expiry must be an integer")
            expires = float(raw_expires)
            now = self._clock()
            if (
                type(schema_version) is not int
                or not isinstance(digest, str)
                or self.TOKEN_DIGEST_PATTERN.fullmatch(digest) is None
                or not now < expires <= now + self._ttl_seconds
            ):
                raise ValueError("remembered session is invalid or expired")
        except (LocalStoreError, ValueError, TypeError, KeyError):
            self._remove_state_safely()
            return
        self._session_token_digest = digest
        self._session_expires = expires
        if schema_version == self.LEGACY_STATE_SCHEMA_VERSION:
            try:
                self._persist_session_locked()
            except LocalStoreError:
                self._session_token_digest = ""
                self._session_expires = 0.0

    def _persist_session_locked(self) -> None:
        if (
            self._state_path is None
            or self._state_boundary is None
            or not self._session_token_digest
        ):
            return
        payload = {
            "schema_version": self.STATE_SCHEMA_VERSION,
            "token_sha256": self._session_token_digest,
            "expires_at_epoch_seconds": math.floor(self._session_expires),
        }
        ensure_private_directory(self._state_path.parent, boundary=self._state_boundary)
        atomic_write_json(
            self._state_path,
            {**payload, "record_digest": _digest(payload)},
            boundary=self._state_boundary,
            maximum_bytes=self.MAX_STATE_BYTES,
        )

    def _remove_state_safely(self) -> None:
        if self._state_path is None or self._state_boundary is None:
            return
        with suppress(LocalStoreError):
            remove_regular_file(
                self._state_path,
                boundary=self._state_boundary,
                missing_ok=True,
            )


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
