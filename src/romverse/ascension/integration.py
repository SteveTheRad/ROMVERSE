from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from romverse.ascension.evidence import AscensionEvidenceService
from romverse.ascension.models import AscensionMethod
from romverse.ascension.preparation import RootPatchPreparationService
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore

ProgressCallback = Callable[[int], None]


@dataclass(frozen=True, slots=True)
class RootRomIntegrationReceipt:
    schema_version: int
    integration_id: str
    project_id: str
    method: AscensionMethod
    created_at: str
    source_original_sha256: str
    rollback_record_digest: str
    patched_receipt_digest: str
    target_relative_path: str
    pristine_image_sha256: str
    integrated_image_sha256: str
    snapshot_relative_path: str
    snapshot_sha256: str
    snapshot_size_bytes: int
    build_plan_refresh_required: bool
    authority: str
    phone_changed: bool
    bootloader_relock_allowed: bool
    integration_digest: str


@dataclass(frozen=True, slots=True)
class RootRomRollbackReceipt:
    integration_id: str
    project_id: str
    restored_relative_path: str
    restored_sha256: str
    phone_changed: bool
    success: bool


class RootRomIntegrationService:
    """Integrate a verified root image into local ROM inputs, never into a phone."""

    FORMAT = "romverse.root-rom-integration"
    SCHEMA_VERSION = 1
    RECEIPT_NAME = "root-rom-integration.romverse"
    TRANSACTION_NAME = ".root-rom-integration-transaction.romverse"
    CHUNK_SIZE = 4 * 1024 * 1024
    MAX_RECEIPT_BYTES = 256 * 1024
    MAX_TEXT = 8192

    def __init__(self, store: RomProjectStore) -> None:
        self.store = store

    def integrate(
        self,
        project_id: str,
        method: AscensionMethod,
        progress: ProgressCallback | None = None,
    ) -> RootRomIntegrationReceipt:
        existing = self.load(project_id, method)
        if existing is not None:
            return existing
        project = self.store.get(project_id)
        rollback = AscensionEvidenceService(self.store).load(project_id)
        patched = RootPatchPreparationService(self.store).load_patched(project_id, method)
        if project.original is None or rollback is None or patched is None:
            raise ProjectError(
                "Verify the protected source, rollback capsule, and manager-patched image first"
            )
        self._recover_incomplete(project_id, method, rollback.patch_target.source_relative_path)
        target, target_root, relative = self._target(
            project_id, rollback.patch_target.source_relative_path
        )
        patched_path = self._workspace_file(
            patched.patched_image_path,
            patched.patched_image_sha256,
            patched.patched_image_size_bytes,
        )
        target_size = target.stat().st_size
        patched_size = patched_path.stat().st_size
        planned_bytes = max(1, 3 * (target_size + patched_size))
        completed_bytes = 0

        def processed(amount: int) -> None:
            nonlocal completed_bytes
            completed_bytes += amount
            self._report(progress, min(99, round(completed_bytes * 100 / planned_bytes)))

        self._report(progress, 0)
        current_sha256 = _sha256(target, processed)
        if current_sha256 != rollback.patch_target.sha256:
            raise ProjectError(
                "Root integration requires the pristine source-bound image; the ROM input changed"
            )
        integration_id = uuid4().hex
        snapshot_root = (
            self.store.snapshots_root
            / project_id
            / "ascension-root"
            / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{integration_id[:8]}"
        )
        snapshot = snapshot_root / "files" / relative
        try:
            ensure_private_directory(snapshot.parent, boundary=self.store.workspace)
        except LocalStoreError as exc:
            raise ProjectError(
                "Root integration rollback vault could not be prepared safely"
            ) from exc
        required = target.stat().st_size + patched_path.stat().st_size + 64 * 1024 * 1024
        if shutil.disk_usage(snapshot_root).free < required:
            raise ProjectError(
                "Insufficient free space for root integration and automatic rollback"
            )
        temporary = target.with_name(f".{target.name}.{integration_id}.part")
        integration_root = self.store.projects_root / project_id / "ascension" / "integration"
        try:
            ensure_private_directory(integration_root, boundary=self.store.workspace)
        except LocalStoreError as exc:
            raise ProjectError(
                "Root integration evidence vault could not be prepared safely"
            ) from exc
        transaction_path = integration_root / self.TRANSACTION_NAME
        replaced = False
        try:
            self._copy(target, snapshot, processed)
            snapshot.chmod(0o600)
            if _sha256(snapshot, processed) != rollback.patch_target.sha256:
                raise ProjectError("Root integration rollback snapshot failed SHA-256 verification")
            self._copy(patched_path, temporary, processed)
            if _sha256(temporary, processed) != patched.patched_image_sha256:
                raise ProjectError("Root integration candidate failed SHA-256 verification")
            transaction: dict[str, object] = {
                "schema_version": 1,
                "project_id": project_id,
                "method": method.value,
                "target_relative_path": relative.as_posix(),
                "snapshot_relative_path": snapshot.relative_to(self.store.workspace).as_posix(),
                "snapshot_size_bytes": snapshot.stat().st_size,
                "pristine_image_sha256": rollback.patch_target.sha256,
                "patched_image_sha256": patched.patched_image_sha256,
                "phone_changed": False,
            }
            atomic_write_json(
                transaction_path,
                {
                    "format": "romverse.root-rom-integration-transaction",
                    **transaction,
                    "transaction_digest": _digest(transaction),
                },
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            os.replace(temporary, target)
            replaced = True
            if _sha256(target, processed) != patched.patched_image_sha256:
                raise ProjectError("Integrated root image failed final SHA-256 verification")
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            if replaced:
                self._restore(snapshot, target, rollback.patch_target.sha256)
            if not replaced or _sha256(target) == rollback.patch_target.sha256:
                transaction_path.unlink(missing_ok=True)
            raise ProjectError(
                f"Root integration stopped and the ROM input was restored: {exc}"
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)

        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "integration_id": integration_id,
            "project_id": project_id,
            "method": method.value,
            "created_at": datetime.now(UTC).isoformat(),
            "source_original_sha256": project.original.sha256,
            "rollback_record_digest": rollback.record_digest,
            "patched_receipt_digest": patched.receipt_digest,
            "target_relative_path": relative.as_posix(),
            "pristine_image_sha256": rollback.patch_target.sha256,
            "integrated_image_sha256": patched.patched_image_sha256,
            "snapshot_relative_path": snapshot.relative_to(self.store.workspace).as_posix(),
            "snapshot_sha256": rollback.patch_target.sha256,
            "snapshot_size_bytes": snapshot.stat().st_size,
            "build_plan_refresh_required": True,
            "authority": "isolated-rom-build-only",
            "phone_changed": False,
            "bootloader_relock_allowed": False,
        }
        receipt = RootRomIntegrationReceipt(
            self.SCHEMA_VERSION,
            integration_id,
            project_id,
            method,
            str(payload["created_at"]),
            project.original.sha256,
            rollback.record_digest,
            patched.receipt_digest,
            relative.as_posix(),
            rollback.patch_target.sha256,
            patched.patched_image_sha256,
            str(payload["snapshot_relative_path"]),
            rollback.patch_target.sha256,
            snapshot.stat().st_size,
            True,
            "isolated-rom-build-only",
            False,
            False,
            _digest(payload),
        )
        document = {"format": self.FORMAT, **asdict(receipt), "method": method.value}
        try:
            for receipt_path in (
                integration_root / self.RECEIPT_NAME,
                integration_root / f"integration-{integration_id[:12]}.romverse",
            ):
                atomic_write_json(
                    receipt_path,
                    document,
                    boundary=self.store.workspace,
                    maximum_bytes=self.MAX_RECEIPT_BYTES,
                )
        except LocalStoreError as exc:
            self._restore(snapshot, target, rollback.patch_target.sha256)
            transaction_path.unlink(missing_ok=True)
            raise ProjectError("Root integration receipt could not be stored safely") from exc
        transaction_path.unlink(missing_ok=True)
        self._report(progress, 100)
        return receipt

    def load(
        self,
        project_id: str,
        method: AscensionMethod,
    ) -> RootRomIntegrationReceipt | None:
        path = (
            self.store.projects_root / project_id / "ascension" / "integration" / self.RECEIPT_NAME
        )
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            if (
                set(data)
                != {"format", *(field.name for field in fields(RootRomIntegrationReceipt))}
                or data.pop("format") != self.FORMAT
                or not isinstance(data.get("method"), str)
            ):
                return None
            data["method"] = AscensionMethod(data["method"])
            receipt = RootRomIntegrationReceipt(**data)
        except (LocalStoreError, ValueError, TypeError, KeyError):
            return None
        project = self.store.get(project_id)
        rollback = AscensionEvidenceService(self.store).load(project_id)
        patched = RootPatchPreparationService(self.store).load_patched(project_id, method)
        unsigned = asdict(receipt)
        unsigned.pop("integration_digest")
        unsigned["method"] = receipt.method.value
        if (
            project.original is None
            or rollback is None
            or patched is None
            or not _valid_receipt_shape(receipt, self.MAX_TEXT)
            or receipt.schema_version != self.SCHEMA_VERSION
            or receipt.project_id != project_id
            or receipt.method is not method
            or receipt.source_original_sha256 != project.original.sha256
            or receipt.rollback_record_digest != rollback.record_digest
            or receipt.patched_receipt_digest != patched.receipt_digest
            or receipt.pristine_image_sha256 != rollback.patch_target.sha256
            or receipt.integrated_image_sha256 != patched.patched_image_sha256
            or not receipt.build_plan_refresh_required
            or receipt.authority != "isolated-rom-build-only"
            or receipt.phone_changed
            or receipt.bootloader_relock_allowed
            or receipt.integration_digest != _digest(unsigned)
        ):
            return None
        try:
            target, _root, relative = self._target(
                project_id, rollback.patch_target.source_relative_path
            )
            snapshot = self._workspace_file(
                receipt.snapshot_relative_path,
                receipt.snapshot_sha256,
                receipt.snapshot_size_bytes,
            )
            if (
                receipt.target_relative_path != relative.as_posix()
                or _sha256(target) != receipt.integrated_image_sha256
                or _sha256(snapshot) != receipt.pristine_image_sha256
            ):
                return None
        except (OSError, ProjectError):
            return None
        return receipt

    def rollback_latest(
        self,
        project_id: str,
        method: AscensionMethod,
    ) -> RootRomRollbackReceipt:
        receipt = self.load(project_id, method)
        rollback = AscensionEvidenceService(self.store).load(project_id)
        if receipt is None or rollback is None:
            raise ProjectError("No verified root-ROM integration rollback is available")
        target, _root, relative = self._target(
            project_id, rollback.patch_target.source_relative_path
        )
        snapshot = self._workspace_file(
            receipt.snapshot_relative_path,
            receipt.snapshot_sha256,
            receipt.snapshot_size_bytes,
        )
        self._restore(snapshot, target, receipt.pristine_image_sha256)
        result = RootRomRollbackReceipt(
            receipt.integration_id,
            project_id,
            relative.as_posix(),
            receipt.pristine_image_sha256,
            False,
            True,
        )
        rollback_path = (
            self.store.projects_root
            / project_id
            / "ascension"
            / "integration"
            / f"rollback-{uuid4().hex[:12]}.romverse"
        )
        try:
            atomic_write_json(
                rollback_path,
                {
                    "format": "romverse.root-rom-integration-rollback",
                    "schema_version": 1,
                    "created_at": datetime.now(UTC).isoformat(),
                    **asdict(result),
                },
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
        except LocalStoreError as exc:
            raise ProjectError(
                "Root integration rollback receipt could not be stored safely"
            ) from exc
        return result

    def _recover_incomplete(
        self,
        project_id: str,
        method: AscensionMethod,
        source_relative: str,
    ) -> None:
        transaction_path = (
            self.store.projects_root
            / project_id
            / "ascension"
            / "integration"
            / self.TRANSACTION_NAME
        )
        if not os.path.lexists(transaction_path):
            return
        try:
            data = read_json_object(
                transaction_path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            if set(data) != _TRANSACTION_FIELDS:
                raise ValueError("wrong transaction shape")
            if not _valid_transaction_shape(data):
                raise ValueError("invalid transaction fields")
            stored_digest = data.pop("transaction_digest")
            if data.pop("format") != "romverse.root-rom-integration-transaction":
                raise ValueError("wrong transaction format")
            method_value = data["method"]
            snapshot_size = data["snapshot_size_bytes"]
            unsigned = dict(data)
        except (LocalStoreError, ValueError, TypeError, KeyError) as exc:
            raise ProjectError(
                "Incomplete root integration has invalid recovery metadata; working input was not changed"
            ) from exc
        if (
            data.get("schema_version") != 1
            or data.get("project_id") != project_id
            or method_value != method.value
            or data.get("phone_changed") is not False
            or snapshot_size <= 0
            or stored_digest != _digest(unsigned)
        ):
            raise ProjectError("Incomplete root integration does not match this project and method")
        target, _root, relative = self._target(project_id, source_relative)
        if str(data.get("target_relative_path")) != relative.as_posix():
            raise ProjectError("Incomplete root integration target does not match current evidence")
        pristine = str(data.get("pristine_image_sha256", ""))
        patched = str(data.get("patched_image_sha256", ""))
        try:
            snapshot_relative = str(data["snapshot_relative_path"])
            snapshot = self._workspace_file(
                snapshot_relative,
                pristine,
                snapshot_size,
            )
            target_digest = _sha256(target)
            if target_digest == patched:
                self._restore(snapshot, target, pristine)
            elif target_digest != pristine:
                raise ProjectError(
                    "Incomplete root integration found an unknown target state; automatic recovery stopped"
                )
        except (OSError, ProjectError):
            raise
        transaction_path.unlink(missing_ok=True)

    def _target(self, project_id: str, source_relative: str) -> tuple[Path, Path, Path]:
        relative = Path(source_relative)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ProjectError("Root integration target path is unsafe")
        base = (self.store.working_root / project_id).resolve()
        if relative.parts[0] != "partitions":
            base = (base / "tree").resolve()
        unresolved = base / relative
        if unresolved.is_symlink():
            raise ProjectError("Root integration target cannot be a symbolic link")
        try:
            target = unresolved.resolve(strict=True)
        except OSError as exc:
            raise ProjectError("Root integration target is unavailable") from exc
        if not target.is_file() or not target.is_relative_to(base):
            raise ProjectError("Root integration target escaped the isolated ROM workspace")
        return target, base, relative

    def _workspace_file(self, relative_text: str, expected_sha256: str, size: int) -> Path:
        relative = Path(relative_text)
        if relative.is_absolute() or ".." in relative.parts:
            raise ProjectError("Root integration artifact path is unsafe")
        unresolved = self.store.workspace / relative
        if unresolved.is_symlink():
            raise ProjectError("Root integration artifact cannot be a symbolic link")
        try:
            path = unresolved.resolve(strict=True)
        except OSError as exc:
            raise ProjectError("Root integration artifact is unavailable") from exc
        if (
            not path.is_file()
            or not path.is_relative_to(self.store.workspace)
            or path.stat().st_size != size
            or _sha256(path) != expected_sha256
        ):
            raise ProjectError("Root integration artifact failed integrity verification")
        return path

    def _copy(
        self,
        source: Path,
        destination: Path,
        progress: Callable[[int], None] | None = None,
    ) -> None:
        with source.open("rb") as incoming, destination.open("xb") as outgoing:
            while chunk := incoming.read(self.CHUNK_SIZE):
                outgoing.write(chunk)
                if progress is not None:
                    progress(len(chunk))
            outgoing.flush()
            os.fsync(outgoing.fileno())

    def _restore(self, snapshot: Path, target: Path, expected_sha256: str) -> None:
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.restore")
        try:
            self._copy(snapshot, temporary)
            if _sha256(temporary) != expected_sha256:
                raise ProjectError("Root integration rollback copy failed SHA-256 verification")
            os.replace(temporary, target)
            if _sha256(target) != expected_sha256:
                raise ProjectError("Root integration rollback failed final verification")
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _report(progress: ProgressCallback | None, value: int) -> None:
        if progress is not None:
            progress(max(0, min(100, value)))


def _sha256(
    path: Path,
    progress: Callable[[int], None] | None = None,
) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
            if progress is not None:
                progress(len(chunk))
    return digest.hexdigest()


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


_TRANSACTION_FIELDS = frozenset(
    {
        "format",
        "schema_version",
        "project_id",
        "method",
        "target_relative_path",
        "snapshot_relative_path",
        "snapshot_size_bytes",
        "pristine_image_sha256",
        "patched_image_sha256",
        "phone_changed",
        "transaction_digest",
    }
)


def _safe_text(value: object, maximum: int) -> bool:
    return bool(isinstance(value, str) and value and len(value) <= maximum and "\x00" not in value)


def _sha256_value(value: object) -> bool:
    return bool(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value))


def _valid_receipt_shape(receipt: RootRomIntegrationReceipt, maximum_text: int) -> bool:
    return bool(
        type(receipt.schema_version) is int
        and _safe_text(receipt.integration_id, maximum_text)
        and _safe_text(receipt.project_id, maximum_text)
        and isinstance(receipt.method, AscensionMethod)
        and _safe_text(receipt.created_at, maximum_text)
        and _sha256_value(receipt.source_original_sha256)
        and _sha256_value(receipt.rollback_record_digest)
        and _sha256_value(receipt.patched_receipt_digest)
        and _safe_text(receipt.target_relative_path, maximum_text)
        and _sha256_value(receipt.pristine_image_sha256)
        and _sha256_value(receipt.integrated_image_sha256)
        and _safe_text(receipt.snapshot_relative_path, maximum_text)
        and _sha256_value(receipt.snapshot_sha256)
        and type(receipt.snapshot_size_bytes) is int
        and receipt.snapshot_size_bytes > 0
        and type(receipt.build_plan_refresh_required) is bool
        and _safe_text(receipt.authority, maximum_text)
        and type(receipt.phone_changed) is bool
        and type(receipt.bootloader_relock_allowed) is bool
        and _sha256_value(receipt.integration_digest)
    )


def _valid_transaction_shape(data: dict[str, object]) -> bool:
    return bool(
        data.get("format") == "romverse.root-rom-integration-transaction"
        and type(data.get("schema_version")) is int
        and _safe_text(data.get("project_id"), RootRomIntegrationService.MAX_TEXT)
        and _safe_text(data.get("method"), RootRomIntegrationService.MAX_TEXT)
        and _safe_text(data.get("target_relative_path"), RootRomIntegrationService.MAX_TEXT)
        and _safe_text(data.get("snapshot_relative_path"), RootRomIntegrationService.MAX_TEXT)
        and type(data.get("snapshot_size_bytes")) is int
        and data["snapshot_size_bytes"] > 0
        and _sha256_value(data.get("pristine_image_sha256"))
        and _sha256_value(data.get("patched_image_sha256"))
        and type(data.get("phone_changed")) is bool
        and _sha256_value(data.get("transaction_digest"))
    )
