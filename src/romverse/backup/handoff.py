from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from romverse.core.privacy import WorkspacePrivacy
from romverse.device.models import AndroidDevice
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


class CloudBackupProvider(StrEnum):
    GOOGLE = "Google Backup / Google One"
    XIAOMI = "Xiaomi Cloud"
    OEM = "Other manufacturer cloud"
    OTHER = "Other trusted cloud backup"


@dataclass(frozen=True, slots=True)
class BackupHandoffReceipt:
    schema_version: int
    receipt_id: str
    project_id: str
    project_source_sha256: str
    device_pseudonym: str
    device_name: str
    model: str
    codename: str
    build_id: str
    method: str
    provider: str
    last_backup_label: str
    confirmed_at: str
    backup_completed: bool
    restore_access_confirmed: bool
    critical_data_scope_reviewed: bool
    limitations_acknowledged: bool
    independently_readable_file_verified: bool
    cloud_contents_inspected: bool
    phone_changed: bool
    execution_authority: str
    receipt_digest: str


class BackupHandoffService:
    """Record explicit cloud-backup evidence without claiming access to cloud contents."""

    RECEIPT_NAME = "user-data-backup-handoff.romverse"
    FORMAT = "romverse.user-data-backup-handoff"

    def __init__(self, store: RomProjectStore) -> None:
        self.store = store

    def confirm_cloud(
        self,
        project_id: str,
        device: AndroidDevice,
        provider: CloudBackupProvider,
        last_backup_label: str,
        *,
        backup_completed: bool,
        restore_access_confirmed: bool,
        critical_data_scope_reviewed: bool,
        limitations_acknowledged: bool,
    ) -> BackupHandoffReceipt:
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("Import the protected firmware before backup handoff")
        if not device.serial or not device.codename:
            raise ProjectError("Connect and authorize the exact target before backup handoff")
        if not all(
            (
                backup_completed,
                restore_access_confirmed,
                critical_data_scope_reviewed,
                limitations_acknowledged,
            )
        ):
            raise ProjectError("Every cloud-backup confirmation must be reviewed")
        label = re.sub(r"\s+", " ", str(last_backup_label)).strip()
        if not label or len(label) > 120 or any(ord(char) < 32 for char in label):
            raise ProjectError("Enter the date or status shown by the cloud-backup provider")
        now = datetime.now(UTC).isoformat()
        payload = {
            "schema_version": 1,
            "receipt_id": uuid4().hex,
            "project_id": project_id,
            "project_source_sha256": project.original.sha256,
            "device_pseudonym": WorkspacePrivacy(self.store.workspace).pseudonym(device.serial),
            "device_name": device.display_name[:120],
            "model": device.model[:120],
            "codename": device.codename[:80],
            "build_id": (device.rom_display or device.build_id)[:160],
            "method": "user-confirmed-cloud-backup",
            "provider": provider.value,
            "last_backup_label": label,
            "confirmed_at": now,
            "backup_completed": True,
            "restore_access_confirmed": True,
            "critical_data_scope_reviewed": True,
            "limitations_acknowledged": True,
            "independently_readable_file_verified": False,
            "cloud_contents_inspected": False,
            "phone_changed": False,
            "execution_authority": "guardian-handoff-evidence-only",
        }
        digest = hashlib.sha256(_canonical(payload)).hexdigest()
        receipt = BackupHandoffReceipt(**payload, receipt_digest=digest)
        path = self.store.projects_root / project_id / self.RECEIPT_NAME
        _atomic_json(path, {"format": self.FORMAT, **asdict(receipt)})
        return receipt

    def load(
        self,
        project_id: str,
        device: AndroidDevice | None = None,
    ) -> BackupHandoffReceipt | None:
        project = self.store.get(project_id)
        path = self.store.projects_root / project_id / self.RECEIPT_NAME
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.pop("format") != self.FORMAT:
                return None
            receipt = BackupHandoffReceipt(**payload)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None
        unsigned = asdict(receipt)
        expected = str(unsigned.pop("receipt_digest", ""))
        actual = hashlib.sha256(_canonical(unsigned)).hexdigest()
        source_sha256 = project.original.sha256 if project.original is not None else ""
        if (
            receipt.schema_version != 1
            or receipt.project_id != project_id
            or receipt.project_source_sha256 != source_sha256
            or not hmac.compare_digest(expected, actual)
            or receipt.method != "user-confirmed-cloud-backup"
            or receipt.execution_authority != "guardian-handoff-evidence-only"
            or receipt.phone_changed
            or receipt.independently_readable_file_verified
            or receipt.cloud_contents_inspected
            or not all(
                (
                    receipt.backup_completed,
                    receipt.restore_access_confirmed,
                    receipt.critical_data_scope_reviewed,
                    receipt.limitations_acknowledged,
                )
            )
        ):
            return None
        if device is not None:
            expected_device = WorkspacePrivacy(self.store.workspace).pseudonym(device.serial)
            if (
                receipt.device_pseudonym != expected_device
                or receipt.codename.casefold() != device.codename.casefold()
                or receipt.model.casefold() != device.model.casefold()
            ):
                return None
        return receipt


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
