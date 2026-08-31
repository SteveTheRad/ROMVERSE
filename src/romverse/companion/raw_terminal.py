from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class RawTerminalRecord:
    """One bounded, privacy-filtered result from a Guardian-approved probe."""

    record_id: str
    captured_at: str
    probe_id: str
    title: str
    lines: tuple[str, ...]
    success: bool
    record_digest: str


class RawTerminalFeed:
    """Thread-safe transient feed for Companion Live Console.

    The feed accepts only named Command Console probes that are already read-only and
    Guardian-bounded. It cannot run a command and deliberately excludes device enumeration and
    host-information probes because their raw output can expose serials or local machine details.
    """

    MAX_RECORDS = 4
    MAX_LINES = 32
    MAX_LINE_LENGTH = 240
    MAX_INPUT_CHARS = 32_000
    ALLOWED_PROBES = {
        "adb-version": "ADB version",
        "device-model": "Device model",
        "android-version": "Android version",
        "battery-details": "Battery details",
        "storage-details": "Storage details",
        "verified-boot-state": "Verified Boot state",
    }
    _ansi = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
    _home_path = re.compile(r"(?<![\w])/(?:home|Users)/[^\s,;]+")
    _windows_path = re.compile(r"\b[A-Za-z]:\\[^\s,;]+")
    _digest = re.compile(r"\b[0-9a-fA-F]{64}\b")
    _email = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
    _bearer = re.compile(r"(?i)\b(?:bearer|token|password|secret)\s*[:=]\s*[^\s]+")

    def __init__(self) -> None:
        self._records: tuple[RawTerminalRecord, ...] = ()
        self._lock = Lock()

    def publish(
        self,
        probe_id: str,
        output: str,
        *,
        private_values: tuple[str, ...] = (),
    ) -> RawTerminalRecord | None:
        probe = str(probe_id).strip().casefold()
        title = self.ALLOWED_PROBES.get(probe)
        if title is None or not isinstance(output, str) or len(output) > self.MAX_INPUT_CHARS:
            return None
        cleaned = self._sanitize(output, private_values)
        if not cleaned:
            cleaned = ("(no visible output)",)
        payload: dict[str, object] = {
            "record_id": uuid4().hex,
            "captured_at": datetime.now(UTC).isoformat(),
            "probe_id": probe,
            "title": title,
            "lines": cleaned,
            "success": self._exit_succeeded(output),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        record = RawTerminalRecord(**payload, record_digest=digest)  # type: ignore[arg-type]
        with self._lock:
            self._records = (record, *self._records)[: self.MAX_RECORDS]
        return record

    def snapshot(self) -> tuple[RawTerminalRecord, ...]:
        with self._lock:
            return self._records

    def clear(self) -> None:
        with self._lock:
            self._records = ()

    def _sanitize(self, output: str, private_values: tuple[str, ...]) -> tuple[str, ...]:
        clean = self._ansi.sub("", output.replace("\r", "\n").replace("\x00", " "))
        for private in private_values:
            value = str(private).strip()
            if value:
                clean = clean.replace(value, "<private-device>")
        clean = self._home_path.sub("<local-path>", clean)
        clean = self._windows_path.sub("<local-path>", clean)
        clean = self._digest.sub("<sha256>", clean)
        clean = self._email.sub("<private-email>", clean)
        clean = self._bearer.sub("<private-credential>", clean)
        lines: list[str] = []
        for raw in clean.splitlines():
            line = "".join(char if ord(char) >= 32 else " " for char in raw)
            line = re.sub(r"\s+", " ", line).strip()
            if not line:
                continue
            lines.append(line[: self.MAX_LINE_LENGTH])
            if len(lines) >= self.MAX_LINES:
                break
        return tuple(lines)

    @staticmethod
    def _exit_succeeded(output: str) -> bool:
        match = re.search(r"(?:^|\n)Exit code:\s*(-?[0-9]+)\s*$", output)
        return bool(match and int(match.group(1)) == 0)


def record_payload(record: RawTerminalRecord) -> dict[str, object]:
    """Return a JSON-ready record mapping for Link telemetry."""

    return asdict(record)
