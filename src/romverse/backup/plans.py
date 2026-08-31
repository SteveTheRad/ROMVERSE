from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from romverse.core.privacy import WorkspacePrivacy
from romverse.device.models import AndroidDevice


@dataclass(frozen=True, slots=True)
class BackupPlanRecord:
    plan_id: str
    plan_digest: str
    latest_path: Path
    history_path: Path
    data: dict[str, object]


@dataclass(frozen=True, slots=True)
class BackupPlanRead:
    valid: bool
    integrity_verified: bool
    reason: str
    data: dict[str, object] | None = None


class GuardianBackupPlanStore:
    """Persist recovery-readiness evidence; never performs or claims a phone backup."""

    FORMAT = "romverse.guardian-recovery-readiness-plan"
    SCHEMA_VERSION = 2
    MAXIMUM_BYTES = 1 << 20

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.root = workspace / "backups"
        self.latest_path = self.root / "latest-backup-plan.json"

    def create(self, device: AndroidDevice) -> BackupPlanRecord:
        created_at = datetime.now(UTC).isoformat()
        device_key = WorkspacePrivacy(self.workspace).pseudonym(device.serial)
        plan_id = hashlib.sha256(f"{created_at}:{device_key}".encode()).hexdigest()[:24]
        payload: dict[str, object] = {
            "format": self.FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "plan_id": plan_id,
            "created_at": created_at,
            "device_key": device_key,
            "device_name": device.display_name,
            "status": "review_required",
            "execution_locked": True,
            "execution_authority": "none",
            "phone_data_copied": False,
            "scope": ["recovery readiness evidence only"],
            "future_backup_scope": ["user data", "app data", "device configuration"],
            "readiness": {
                "adb_authorized": True,
                "battery_percent": device.battery_percent,
                "storage_percent_used": device.storage.percent_used,
                "bootloader_locked": device.bootloader_locked,
                "verified_boot": str(device.verified_boot).strip().casefold(),
            },
        }
        digest = hashlib.sha256(_canonical(payload)).hexdigest()
        payload["plan_digest"] = digest
        content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        self.root.mkdir(parents=True, exist_ok=True)
        history_path = self.root / f"backup-plan-{plan_id}.json"
        _atomic_text(history_path, content)
        _atomic_text(self.latest_path, content)
        return BackupPlanRecord(plan_id, digest, self.latest_path, history_path, payload)

    def load_latest(self) -> BackupPlanRead:
        return self.load(self.latest_path)

    def load(self, path: Path) -> BackupPlanRead:
        try:
            if path.is_symlink() or not path.is_file():
                return BackupPlanRead(False, False, "Plan is missing or is not a regular file")
            size = path.stat().st_size
            if size <= 0 or size > self.MAXIMUM_BYTES:
                return BackupPlanRead(False, False, "Plan size is outside the accepted boundary")
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return BackupPlanRead(False, False, "Plan is unreadable or invalid JSON")
        if not isinstance(data, dict):
            return BackupPlanRead(False, False, "Plan document must be an object")
        if not isinstance(data.get("readiness"), dict):
            return BackupPlanRead(False, False, "Plan readiness evidence must be an object")
        if data.get("schema_version") == 1:
            return BackupPlanRead(
                True,
                False,
                "Legacy plan loaded; it predates integrity fingerprints",
                data,
            )
        if data.get("schema_version") != self.SCHEMA_VERSION or data.get("format") != self.FORMAT:
            return BackupPlanRead(False, False, "Unsupported recovery-readiness plan format")
        expected = str(data.get("plan_digest", ""))
        unsigned = dict(data)
        unsigned.pop("plan_digest", None)
        actual = hashlib.sha256(_canonical(unsigned)).hexdigest()
        if len(expected) != 64 or not hmac.compare_digest(expected, actual):
            return BackupPlanRead(False, False, "Recovery-readiness plan integrity mismatch")
        if data.get("execution_locked") is not True or data.get("execution_authority") != "none":
            return BackupPlanRead(False, False, "Recovery-readiness safety boundary is invalid")
        if data.get("phone_data_copied") is not False:
            return BackupPlanRead(False, False, "Plan contains an unsupported backup claim")
        return BackupPlanRead(True, True, "Plan integrity verified", data)

    def history_count(self) -> int:
        if not self.root.is_dir():
            return 0
        return sum(
            path.is_file() and not path.is_symlink()
            for path in self.root.glob("backup-plan-*.json")
        )


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
