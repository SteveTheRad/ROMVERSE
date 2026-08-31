from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from romverse.core.privacy import WorkspacePrivacy
from romverse.device.models import AndroidDevice, DeviceState
from romverse.guardian.approval import ApprovalStore
from romverse.guardian.backup_transfer import media_pull_digest
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.models import GuardianDeniedError, OperationClass, OperationRequest
from romverse.rom.models import ProjectError

ProgressCallback = Callable[[int, int], None]


class PhoneMediaScope(StrEnum):
    CAMERA = "Camera photos"
    PICTURES = "Pictures"
    VIDEOS = "Videos"
    DOWNLOADS = "Downloads"
    DOCUMENTS = "Documents"

    @property
    def remote_path(self) -> str:
        return {
            PhoneMediaScope.CAMERA: "/sdcard/DCIM",
            PhoneMediaScope.PICTURES: "/sdcard/Pictures",
            PhoneMediaScope.VIDEOS: "/sdcard/Movies",
            PhoneMediaScope.DOWNLOADS: "/sdcard/Download",
            PhoneMediaScope.DOCUMENTS: "/sdcard/Documents",
        }[self]

    @property
    def folder_name(self) -> str:
        return self.remote_path.rsplit("/", 1)[-1]


@dataclass(frozen=True, slots=True)
class PhoneMediaBackupPlan:
    schema_version: int
    plan_id: str
    created_at: str
    device_serial: str
    device_key: str
    device_name: str
    model: str
    codename: str
    destination: str
    archive_path: str
    scopes: tuple[PhoneMediaScope, ...]
    free_bytes_before: int
    plan_digest: str


@dataclass(frozen=True, slots=True)
class PhoneMediaBackupReceipt:
    schema_version: int
    receipt_id: str
    created_at: str
    plan_digest: str
    device_key: str
    device_name: str
    model: str
    codename: str
    archive_name: str
    archive_size_bytes: int
    archive_sha256: str
    manifest_sha256: str
    file_count: int
    source_bytes: int
    requested_scopes: tuple[str, ...]
    captured_scopes: tuple[str, ...]
    unavailable_scopes: tuple[str, ...]
    coverage: str
    app_private_data_included: bool
    contacts_or_messages_claimed: bool
    phone_changed: bool
    bootloader_changed: bool
    execution_authority: str
    limitations: tuple[str, ...]
    receipt_digest: str


class PhoneMediaBackupService:
    """Create a verified archive of explicitly selected shared-storage folders."""

    MAX_FILES = 250_000
    MAX_SOURCE_BYTES = 2 * 1024 * 1024 * 1024 * 1024
    CHUNK_SIZE = 4 * 1024 * 1024

    def __init__(
        self,
        workspace: Path,
        adb_executable: Path,
        gateway: ExecutionGateway,
        approvals: ApprovalStore | None = None,
    ) -> None:
        self.workspace = workspace.resolve()
        self.adb_executable = adb_executable.resolve()
        self.gateway = gateway
        self.approvals = approvals or ApprovalStore(workspace)

    def prepare(
        self,
        device: AndroidDevice,
        destination: Path,
        scopes: tuple[PhoneMediaScope, ...],
    ) -> PhoneMediaBackupPlan:
        if device.state is not DeviceState.DEVICE or not device.serial:
            raise ProjectError("Connect and authorize the exact phone before creating a backup")
        selected = tuple(dict.fromkeys(scopes))
        if not selected:
            raise ProjectError("Select at least one shared-storage backup category")
        if any(not isinstance(scope, PhoneMediaScope) for scope in selected):
            raise ProjectError("Backup scope is outside ROMVERSE shared-storage boundaries")
        if destination.is_symlink():
            raise ProjectError("Choose a real destination folder, not a symbolic link")
        try:
            root = destination.expanduser().resolve(strict=True)
        except OSError as exc:
            raise ProjectError("The selected backup destination is unavailable") from exc
        if not root.is_dir() or root.is_relative_to(self.workspace):
            raise ProjectError("Phone backups must use a folder outside the ROMVERSE workspace")
        if not os.access(root, os.W_OK | os.X_OK):
            raise ProjectError("The selected backup destination is not writable")
        now = datetime.now(UTC)
        device_key = WorkspacePrivacy(self.workspace).pseudonym(device.serial)
        plan_id = uuid4().hex
        archive = root / (
            f"ROMVERSE-phone-media-{now.strftime('%Y%m%d-%H%M%S')}-{device_key[:8]}.zip"
        )
        if archive.exists():
            raise ProjectError("The generated backup archive name already exists")
        payload = {
            "schema_version": 1,
            "plan_id": plan_id,
            "created_at": now.isoformat(),
            "device_serial": device.serial,
            "device_key": device_key,
            "device_name": device.display_name[:120],
            "model": device.model[:120],
            "codename": device.codename[:80],
            "destination": str(root),
            "archive_path": str(archive),
            "scopes": tuple(scope.value for scope in selected),
            "free_bytes_before": shutil.disk_usage(root).free,
        }
        return PhoneMediaBackupPlan(
            **{**payload, "scopes": selected},
            plan_digest=_digest(payload),
        )

    def approve(self, plan: PhoneMediaBackupPlan) -> None:
        self._validate_plan(plan)
        target = plan.device_key
        staging = Path(plan.destination) / f".ROMVERSE-{plan.plan_id}.partial"
        for scope in plan.scopes:
            local = staging / scope.folder_name
            self.approvals.issue(
                media_pull_digest(plan.device_serial, scope.remote_path, local),
                target,
            )

    def execute(
        self,
        plan: PhoneMediaBackupPlan,
        progress: ProgressCallback | None = None,
    ) -> PhoneMediaBackupReceipt:
        self._validate_plan(plan)
        archive = Path(plan.archive_path)
        staging = Path(plan.destination) / f".ROMVERSE-{plan.plan_id}.partial"
        partial_archive = archive.with_name(f".{archive.name}.{plan.plan_id}.partial")
        if archive.exists() or partial_archive.exists() or staging.exists():
            raise GuardianDeniedError("Backup output changed after review; prepare a new plan")
        staging.mkdir(mode=0o700)
        captured: list[PhoneMediaScope] = []
        unavailable: list[PhoneMediaScope] = []
        try:
            for scope in plan.scopes:
                local = staging / scope.folder_name
                approval_digest = media_pull_digest(
                    plan.device_serial,
                    scope.remote_path,
                    local,
                )
                if not self.approvals.is_approved(approval_digest, plan.device_key):
                    raise GuardianDeniedError(
                        f"{scope.value} backup transfer has not been explicitly approved"
                    )
                request = OperationRequest(
                    operation_id="backup.pull_media",
                    category=OperationClass.READ_ONLY,
                    executable=str(self.adb_executable),
                    arguments=(
                        "-s",
                        plan.device_serial,
                        "pull",
                        scope.remote_path,
                        str(local),
                    ),
                    purpose=f"Copy user-selected shared storage: {scope.value}",
                    target=plan.device_serial,
                    approval_digest=approval_digest,
                    approval_target=plan.device_key,
                )
                result = self.gateway.execute(request, timeout=4 * 60 * 60)
                if result.ok and local.exists():
                    captured.append(scope)
                elif _remote_missing(result.stderr, result.stdout):
                    unavailable.append(scope)
                else:
                    detail = (result.stderr or result.stdout).strip()[-500:]
                    raise ProjectError(
                        f"{scope.value} could not be copied" + (f": {detail}" if detail else "")
                    )
            files = self._inventory(staging)
            if not files:
                raise ProjectError(
                    "No shared-storage files were found in the selected backup categories"
                )
            source_bytes = sum(path.stat().st_size for path in files)
            if source_bytes > plan.free_bytes_before:
                raise ProjectError("The selected destination no longer has enough free space")
            manifest_files = []
            completed_source_bytes = 0
            with zipfile.ZipFile(
                partial_archive, "w", zipfile.ZIP_STORED, allowZip64=True
            ) as bundle:
                for path in files:
                    relative = path.relative_to(staging).as_posix()
                    base = completed_source_bytes

                    def publish_file_hash(
                        done: int,
                        _total: int,
                        *,
                        offset: int = base,
                    ) -> None:
                        combined = offset + done
                        if progress is not None and combined < source_bytes:
                            progress(combined, source_bytes)

                    digest = _sha256(path, publish_file_hash)
                    size = path.stat().st_size
                    bundle.write(path, f"phone-media/{relative}")
                    manifest_files.append({"path": relative, "size_bytes": size, "sha256": digest})
                    completed_source_bytes += size
                manifest = {
                    "format": "romverse.phone-media-manifest",
                    "schema_version": 1,
                    "created_at": datetime.now(UTC).isoformat(),
                    "plan_digest": plan.plan_digest,
                    "device_key": plan.device_key,
                    "requested_scopes": [scope.value for scope in plan.scopes],
                    "captured_scopes": [scope.value for scope in captured],
                    "unavailable_scopes": [scope.value for scope in unavailable],
                    "coverage": "user-accessible shared storage only",
                    "files": manifest_files,
                }
                manifest_bytes = json.dumps(
                    manifest, sort_keys=True, separators=(",", ":")
                ).encode()
                bundle.writestr("ROMVERSE-MANIFEST.json", manifest_bytes)
            os.replace(partial_archive, archive)
            archive_size = archive.stat().st_size
            archive_digest = _sha256(archive)
            payload = {
                "schema_version": 1,
                "receipt_id": uuid4().hex,
                "created_at": datetime.now(UTC).isoformat(),
                "plan_digest": plan.plan_digest,
                "device_key": plan.device_key,
                "device_name": plan.device_name,
                "model": plan.model,
                "codename": plan.codename,
                "archive_name": archive.name,
                "archive_size_bytes": archive_size,
                "archive_sha256": archive_digest,
                "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "file_count": len(files),
                "source_bytes": source_bytes,
                "requested_scopes": tuple(scope.value for scope in plan.scopes),
                "captured_scopes": tuple(scope.value for scope in captured),
                "unavailable_scopes": tuple(scope.value for scope in unavailable),
                "coverage": "user-accessible shared storage only",
                "app_private_data_included": False,
                "contacts_or_messages_claimed": False,
                "phone_changed": False,
                "bootloader_changed": False,
                "execution_authority": "guardian-approved-read-only-backup",
                "limitations": (
                    "App-private data and credentials are not accessible through this route.",
                    "Contacts, messages, eSIMs, authenticators, and secure folders require separate provider backup review.",
                    "A successful archive does not prove every app can be restored.",
                ),
            }
            receipt = PhoneMediaBackupReceipt(**payload, receipt_digest=_digest(payload))
            _atomic_json(
                archive.with_suffix(f"{archive.suffix}.romverse"),
                {"format": "romverse.phone-media-backup-receipt", **asdict(receipt)},
            )
            self.verify_receipt(archive, receipt)
            if progress is not None:
                terminal = source_bytes or 1
                progress(terminal, terminal)
            return receipt
        except Exception:
            partial_archive.unlink(missing_ok=True)
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    @classmethod
    def verify_receipt(
        cls,
        archive: Path,
        receipt: PhoneMediaBackupReceipt,
    ) -> PhoneMediaBackupReceipt:
        """Revalidate a completed local backup, its sidecar, and embedded manifest."""

        unresolved = archive.expanduser()
        sidecar = unresolved.with_suffix(f"{unresolved.suffix}.romverse")
        if unresolved.is_symlink() or sidecar.is_symlink():
            raise ProjectError("Local phone backup evidence cannot use symbolic links")
        try:
            path = unresolved.resolve(strict=True)
            sidecar_path = sidecar.resolve(strict=True)
            payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
            if payload.pop("format") != "romverse.phone-media-backup-receipt":
                raise ProjectError("Local phone backup receipt format is unsupported")
            for field in (
                "requested_scopes",
                "captured_scopes",
                "unavailable_scopes",
                "limitations",
            ):
                payload[field] = tuple(str(item) for item in payload[field])
            recorded = PhoneMediaBackupReceipt(**payload)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ProjectError("Local phone backup receipt is unavailable or invalid") from exc
        unsigned = asdict(recorded)
        expected_digest = str(unsigned.pop("receipt_digest", ""))
        if (
            recorded != receipt
            or recorded.schema_version != 1
            or recorded.archive_name != path.name
            or recorded.archive_size_bytes != path.stat().st_size
            or recorded.archive_sha256 != _sha256(path)
            or recorded.coverage != "user-accessible shared storage only"
            or recorded.app_private_data_included
            or recorded.contacts_or_messages_claimed
            or recorded.phone_changed
            or recorded.bootloader_changed
            or recorded.execution_authority != "guardian-approved-read-only-backup"
            or expected_digest != _digest(unsigned)
        ):
            raise ProjectError("Local phone backup receipt failed integrity or safety validation")
        try:
            with zipfile.ZipFile(path) as bundle:
                names = bundle.namelist()
                manifest_bytes = bundle.read("ROMVERSE-MANIFEST.json")
            manifest = json.loads(manifest_bytes)
            files = manifest["files"]
            expected_names = {f"phone-media/{item['path']}" for item in files}
        except (OSError, KeyError, TypeError, ValueError, zipfile.BadZipFile) as exc:
            raise ProjectError("Local phone backup archive or manifest is invalid") from exc
        if (
            len(names) != len(set(names))
            or set(names) != expected_names | {"ROMVERSE-MANIFEST.json"}
            or manifest.get("format") != "romverse.phone-media-manifest"
            or manifest.get("schema_version") != 1
            or manifest.get("plan_digest") != recorded.plan_digest
            or manifest.get("device_key") != recorded.device_key
            or manifest.get("coverage") != recorded.coverage
            or tuple(manifest.get("requested_scopes", ())) != recorded.requested_scopes
            or tuple(manifest.get("captured_scopes", ())) != recorded.captured_scopes
            or tuple(manifest.get("unavailable_scopes", ())) != recorded.unavailable_scopes
            or len(files) != recorded.file_count
            or hashlib.sha256(manifest_bytes).hexdigest() != recorded.manifest_sha256
        ):
            raise ProjectError("Local phone backup manifest no longer matches its receipt")
        return recorded

    def _validate_plan(self, plan: PhoneMediaBackupPlan) -> None:
        unsigned = asdict(plan)
        expected = str(unsigned.pop("plan_digest", ""))
        unsigned["scopes"] = tuple(scope.value for scope in plan.scopes)
        if (
            plan.schema_version != 1
            or not plan.device_serial
            or not plan.scopes
            or expected != _digest(unsigned)
        ):
            raise GuardianDeniedError("Phone media backup plan failed integrity validation")
        destination = Path(plan.destination)
        archive = Path(plan.archive_path)
        try:
            destination = destination.resolve(strict=True)
        except OSError as exc:
            raise GuardianDeniedError("Backup destination is no longer available") from exc
        if (
            destination.is_relative_to(self.workspace)
            or archive.parent != destination
            or not archive.name.startswith("ROMVERSE-phone-media-")
            or archive.suffix.casefold() != ".zip"
        ):
            raise GuardianDeniedError("Phone media backup paths changed after review")

    def _inventory(self, staging: Path) -> tuple[Path, ...]:
        files = []
        total = 0
        for path in sorted(staging.rglob("*")):
            if path.is_symlink():
                raise ProjectError("Phone media backup rejected a symbolic link")
            if not path.is_file():
                continue
            total += path.stat().st_size
            if total > self.MAX_SOURCE_BYTES:
                raise ProjectError("Phone media backup exceeds the supported 2 TiB boundary")
            files.append(path)
            if len(files) > self.MAX_FILES:
                raise ProjectError("Phone media backup exceeds the supported file-count boundary")
        return tuple(files)


def _remote_missing(*messages: str) -> bool:
    value = " ".join(messages).casefold()
    return "does not exist" in value or "no such file" in value


def _sha256(
    path: Path,
    progress: ProgressCallback | None = None,
) -> str:
    digest = hashlib.sha256()
    total = path.stat().st_size
    read = 0
    with path.open("rb") as stream:
        while chunk := stream.read(PhoneMediaBackupService.CHUNK_SIZE):
            digest.update(chunk)
            read += len(chunk)
            if progress is not None:
                progress(read, total)
    return digest.hexdigest()


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
