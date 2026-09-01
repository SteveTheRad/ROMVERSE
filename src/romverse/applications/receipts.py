from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from romverse.device.apk_install import ApkInstallPlan, plan_summary
from romverse.infrastructure.process import CommandResult


@dataclass(frozen=True, slots=True)
class ApkReceiptRecord:
    receipt_id: str
    receipt_digest: str
    latest_path: Path
    history_path: Path
    data: dict[str, object]


@dataclass(frozen=True, slots=True)
class ApkReceiptRead:
    valid: bool
    integrity_verified: bool
    reason: str
    data: dict[str, object] | None = None


class ApkReceiptStore:
    """Atomic privacy-safe evidence for the approval-gated APK mutation path."""

    FORMAT = "romverse.apk-workflow-receipt"
    SCHEMA_VERSION = 2
    MAXIMUM_BYTES = 1 << 20

    def __init__(self, workspace: Path) -> None:
        self.root = workspace / "logs"
        self.latest_preflight_path = self.root / "latest-apk-preflight.json"
        self.latest_install_path = self.root / "latest-apk-install.json"

    def write_preflight(self, plan: ApkInstallPlan) -> ApkReceiptRecord:
        created_at = datetime.now(UTC).isoformat()
        payload = json.loads(plan_summary(plan))
        payload.update(
            {
                "format": self.FORMAT,
                "schema_version": self.SCHEMA_VERSION,
                "receipt_kind": "preflight",
                "created_at": created_at,
                "approval_required": plan.assessment.approval_required,
                "execution_locked": plan.assessment.execution_locked,
                "safety_ready": plan.safety_ready,
                "device_command_executed": False,
            }
        )
        return self._write(payload, self.latest_preflight_path, "apk-preflight")

    def write_install(
        self,
        plan: ApkInstallPlan,
        result: CommandResult,
        success: bool,
    ) -> ApkReceiptRecord:
        payload = json.loads(plan_summary(plan))
        payload.update(
            {
                "format": self.FORMAT,
                "schema_version": self.SCHEMA_VERSION,
                "receipt_kind": "install-result",
                "completed_at": datetime.now(UTC).isoformat(),
                "success": bool(success),
                "returncode": int(result.returncode),
                "timed_out": bool(result.timed_out),
                "device_command_executed": True,
            }
        )
        return self._write(payload, self.latest_install_path, "apk-install")

    def load_latest_preflight(self) -> ApkReceiptRead:
        return self.load(self.latest_preflight_path, "preflight")

    def load_latest_install(self) -> ApkReceiptRead:
        return self.load(self.latest_install_path, "install-result")

    def load(self, path: Path, expected_kind: str) -> ApkReceiptRead:
        try:
            if path.is_symlink() or not path.is_file():
                return ApkReceiptRead(False, False, "Receipt is missing or not a regular file")
            size = path.stat().st_size
            if size <= 0 or size > self.MAXIMUM_BYTES:
                return ApkReceiptRead(False, False, "Receipt size is outside the accepted boundary")
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return ApkReceiptRead(False, False, "Receipt is unreadable or invalid JSON")
        if not isinstance(data, dict):
            return ApkReceiptRead(False, False, "Receipt document must be an object")
        if data.get("schema_version") == 1:
            legacy_kind = "install-result" if "success" in data else "preflight"
            if legacy_kind != expected_kind:
                return ApkReceiptRead(
                    False, False, "Legacy APK receipt kind does not match its location"
                )
            if any(key in data for key in ("apk_path", "device_serial", "stdout", "stderr")):
                return ApkReceiptRead(False, False, "Legacy APK receipt contains a private field")
            return ApkReceiptRead(
                True,
                False,
                "Legacy receipt loaded; it predates integrity fingerprints",
                data,
            )
        if data.get("schema_version") != self.SCHEMA_VERSION or data.get("format") != self.FORMAT:
            return ApkReceiptRead(False, False, "Unsupported APK receipt format")
        if data.get("receipt_kind") != expected_kind:
            return ApkReceiptRead(False, False, "APK receipt kind does not match its location")
        expected = str(data.get("receipt_digest", ""))
        unsigned = dict(data)
        unsigned.pop("receipt_digest", None)
        actual = hashlib.sha256(_canonical(unsigned)).hexdigest()
        if len(expected) != 64 or not hmac.compare_digest(expected, actual):
            return ApkReceiptRead(False, False, "APK receipt integrity mismatch")
        if not _is_sha256(str(data.get("apk_sha256", ""))) or not _is_sha256(
            str(data.get("manifest_digest", ""))
        ):
            return ApkReceiptRead(False, False, "APK receipt identity evidence is invalid")
        if any(key in data for key in ("apk_path", "device_serial", "stdout", "stderr")):
            return ApkReceiptRead(False, False, "APK receipt contains a forbidden private field")
        command_executed = data.get("device_command_executed")
        expected_executed = expected_kind == "install-result"
        if not isinstance(command_executed, bool) or command_executed != expected_executed:
            return ApkReceiptRead(False, False, "APK receipt execution claim is invalid")
        return ApkReceiptRead(True, True, "APK receipt integrity verified", data)

    def history_count(self, kind: str) -> int:
        if kind not in {"apk-preflight", "apk-install"} or not self.root.is_dir():
            return 0
        return sum(
            path.is_file() and not path.is_symlink() for path in self.root.glob(f"{kind}-*.json")
        )

    def _write(
        self,
        payload: dict[str, object],
        latest_path: Path,
        filename_prefix: str,
    ) -> ApkReceiptRecord:
        identity_time = str(payload.get("created_at") or payload.get("completed_at") or "")
        receipt_id = hashlib.sha256(
            f"{payload['receipt_kind']}:{payload['manifest_digest']}:{identity_time}".encode()
        ).hexdigest()[:24]
        payload["receipt_id"] = receipt_id
        digest = hashlib.sha256(_canonical(payload)).hexdigest()
        payload["receipt_digest"] = digest
        content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        self.root.mkdir(parents=True, exist_ok=True)
        history_path = self.root / f"{filename_prefix}-{receipt_id}.json"
        _atomic_text(history_path, content)
        _atomic_text(latest_path, content)
        return ApkReceiptRecord(receipt_id, digest, latest_path, history_path, payload)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _atomic_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
