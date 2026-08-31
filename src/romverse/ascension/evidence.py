from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
from contextlib import suppress
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


@dataclass(frozen=True, slots=True)
class BootImageEvidence:
    relative_path: str
    image_name: str
    header_version: int
    ramdisk_size_bytes: int
    ramdisk_present: bool


@dataclass(frozen=True, slots=True)
class RollbackArtifact:
    role: str
    source_relative_path: str
    vault_relative_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class AscensionRollbackRecord:
    schema_version: int
    project_id: str
    source_original_sha256: str
    created_at: str
    patch_target: RollbackArtifact
    stock_recovery: RollbackArtifact | None
    boot_image: BootImageEvidence
    authority: str
    phone_changed: bool
    record_digest: str


class AscensionEvidenceService:
    """Create a source-bound local rollback capsule without touching the phone.

    The capsule is sufficient for manager/image-patch preparation. It deliberately does
    not claim to be a user-data backup or grant authority to flash the device.
    """

    FORMAT = "romverse.ascension-rollback"
    SCHEMA_VERSION = 1
    RECEIPT_NAME = "rollback-capsule.romverse"
    CHUNK_SIZE = 4 * 1024 * 1024
    MAX_RECOVERY_CANDIDATES = 32
    MAX_RECOVERY_BYTES = 1024 * 1024 * 1024
    MAX_RECEIPT_BYTES = 256 * 1024
    MAX_TEXT = 8192

    def __init__(self, store: RomProjectStore) -> None:
        self.store = store

    def ensure(self, project_id: str, patch_target: str) -> AscensionRollbackRecord:
        current = self.load(project_id)
        if current is not None and current.patch_target.source_relative_path == patch_target:
            return current

        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("Import a protected firmware source before preparing rollback")
        original = self.store.verify_original(project_id)
        if not original.valid:
            raise ProjectError(f"Protected source failed verification: {original.status}")

        project_root = (self.store.working_root / project_id).resolve()
        tree = (project_root / "tree").resolve()
        evidence_root = tree
        target_reference = patch_target
        if Path(patch_target).parts[:1] == ("partitions",):
            evidence_root = project_root
        target = self._contained_file(evidence_root, target_reference)
        boot = inspect_android_boot_image(target, evidence_root)
        if not boot.ramdisk_present:
            raise ProjectError(
                f"{target.name} does not contain a boot ramdisk; automatic patch selection stopped"
            )

        recovery = self._resolve_stock_recovery(project_root, tree)

        root = self.store.projects_root / project_id / "ascension" / "rollback"
        try:
            ensure_private_directory(root, boundary=self.store.workspace)
        except LocalStoreError as exc:
            raise ProjectError("Rollback evidence vault could not be prepared safely") from exc
        patch_artifact = self._vault(evidence_root, target, "patch-target", root)
        recovery_artifact = (
            self._vault(recovery[1], recovery[0], "stock-recovery", root)
            if recovery is not None
            else None
        )
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "project_id": project_id,
            "source_original_sha256": project.original.sha256,
            "created_at": datetime.now(UTC).isoformat(),
            "patch_target": asdict(patch_artifact),
            "stock_recovery": asdict(recovery_artifact) if recovery_artifact else None,
            "boot_image": asdict(boot),
            "authority": "verified-local-root-preparation-only",
            "phone_changed": False,
        }
        digest = _digest(payload)
        record = AscensionRollbackRecord(
            self.SCHEMA_VERSION,
            project_id,
            project.original.sha256,
            str(payload["created_at"]),
            patch_artifact,
            recovery_artifact,
            boot,
            "verified-local-root-preparation-only",
            False,
            digest,
        )
        receipt = self.store.projects_root / project_id / "ascension" / self.RECEIPT_NAME
        try:
            ensure_private_directory(receipt.parent, boundary=self.store.workspace)
            atomic_write_json(
                receipt,
                {"format": self.FORMAT, **asdict(record)},
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
        except LocalStoreError as exc:
            raise ProjectError("Rollback evidence receipt could not be stored safely") from exc
        return record

    def load(self, project_id: str) -> AscensionRollbackRecord | None:
        project = self.store.get(project_id)
        path = self.store.projects_root / project_id / "ascension" / self.RECEIPT_NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            if (
                set(data) != {"format", *(field.name for field in fields(AscensionRollbackRecord))}
                or data.pop("format") != self.FORMAT
            ):
                return None
            patch_data = data.pop("patch_target")
            recovery_data = data.pop("stock_recovery")
            boot_data = data.pop("boot_image")
            if (
                not _exact_object(patch_data, RollbackArtifact)
                or not _exact_object(boot_data, BootImageEvidence)
                or (
                    recovery_data is not None and not _exact_object(recovery_data, RollbackArtifact)
                )
            ):
                return None
            patch = RollbackArtifact(**patch_data)
            recovery = RollbackArtifact(**recovery_data) if recovery_data is not None else None
            boot = BootImageEvidence(**boot_data)
            record = AscensionRollbackRecord(
                **data,
                patch_target=patch,
                stock_recovery=recovery,
                boot_image=boot,
            )
        except (LocalStoreError, ValueError, TypeError, KeyError):
            return None
        if (
            project.original is None
            or not _valid_record_shape(record, self.MAX_TEXT)
            or record.schema_version != self.SCHEMA_VERSION
            or record.project_id != project_id
            or record.source_original_sha256 != project.original.sha256
            or record.authority != "verified-local-root-preparation-only"
            or record.phone_changed
            or record.record_digest != _record_digest(record)
        ):
            return None
        if (
            record.patch_target.role != "patch-target"
            or record.boot_image.relative_path != record.patch_target.source_relative_path
            or record.boot_image.image_name != Path(record.patch_target.source_relative_path).name
            or (
                record.stock_recovery is not None and record.stock_recovery.role != "stock-recovery"
            )
        ):
            return None
        vault_root = (self.store.projects_root / project_id / "ascension" / "rollback").resolve()
        artifacts = (record.patch_target,) + (
            (record.stock_recovery,) if record.stock_recovery is not None else ()
        )
        resolved_artifacts: list[Path] = []
        for artifact in artifacts:
            source_reference = Path(artifact.source_relative_path)
            if (
                source_reference.is_absolute()
                or ".." in source_reference.parts
                or not source_reference.parts
            ):
                return None
            path = self.store.workspace / artifact.vault_relative_path
            try:
                resolved = path.resolve(strict=True)
                if (
                    path.is_symlink()
                    or not resolved.is_relative_to(vault_root)
                    or not resolved.is_file()
                    or resolved.stat().st_size != artifact.size_bytes
                    or _sha256(resolved) != artifact.sha256
                    or resolved.name != f"{artifact.sha256[:16]}-{source_reference.name}"
                ):
                    return None
                resolved_artifacts.append(resolved)
            except OSError:
                return None
        try:
            observed_boot = inspect_android_boot_image(
                resolved_artifacts[0],
                vault_root,
            )
        except (IndexError, ProjectError):
            return None
        if (
            observed_boot.header_version != record.boot_image.header_version
            or observed_boot.ramdisk_size_bytes != record.boot_image.ramdisk_size_bytes
            or observed_boot.ramdisk_present != record.boot_image.ramdisk_present
            or not observed_boot.ramdisk_present
        ):
            return None
        return record

    def _vault(
        self,
        tree: Path,
        source: Path,
        role: str,
        root: Path,
    ) -> RollbackArtifact:
        digest = _sha256(source)
        destination = root / f"{digest[:16]}-{source.name}"
        existing_valid = False
        if destination.is_file() and not destination.is_symlink():
            existing_valid = (
                destination.stat().st_size == source.stat().st_size
                and _sha256(destination) == digest
            )
        if not existing_valid:
            if destination.exists() or destination.is_symlink():
                with suppress(OSError):
                    destination.chmod(0o600)
                destination.unlink(missing_ok=True)
            temporary = root / f".{destination.name}.{uuid4().hex}.tmp"
            try:
                with source.open("rb") as incoming, temporary.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing, self.CHUNK_SIZE)
                    outgoing.flush()
                    os.fsync(outgoing.fileno())
                if _sha256(temporary) != digest:
                    raise ProjectError("Rollback capsule copy failed SHA-256 verification")
                os.replace(temporary, destination)
                destination.chmod(0o444)
            finally:
                temporary.unlink(missing_ok=True)
        if _sha256(destination) != digest:
            raise ProjectError("Existing rollback capsule failed SHA-256 verification")
        return RollbackArtifact(
            role,
            source.relative_to(tree).as_posix(),
            destination.relative_to(self.store.workspace).as_posix(),
            destination.stat().st_size,
            digest,
        )

    @staticmethod
    def _contained_file(tree: Path, relative: str) -> Path:
        if not relative or "\x00" in relative:
            raise ProjectError("Patch target path is unavailable")
        unresolved = tree / relative
        if unresolved.is_symlink():
            raise ProjectError("Patch target cannot be a symbolic link")
        try:
            path = unresolved.resolve(strict=True)
        except OSError as exc:
            raise ProjectError("Patch target is unavailable") from exc
        if not path.is_relative_to(tree) or not path.is_file():
            raise ProjectError("Patch target escaped the protected working tree")
        return path

    @staticmethod
    def _named_files(tree: Path, name: str) -> tuple[Path, ...]:
        return tuple(
            sorted(
                (
                    path.resolve()
                    for path in tree.rglob(name)
                    if path.is_file()
                    and not path.is_symlink()
                    and path.resolve().is_relative_to(tree)
                ),
                key=lambda path: path.as_posix(),
            )
        )

    def _resolve_stock_recovery(
        self,
        project_root: Path,
        tree: Path,
    ) -> tuple[Path, Path] | None:
        partitions = project_root / "partitions"
        recoveries = list(self._named_files(tree, "recovery.img"))
        if partitions.is_dir() and not partitions.is_symlink():
            recoveries.extend(self._named_files(partitions.resolve(), "recovery.img"))
        unique = tuple(dict.fromkeys(recoveries))
        if not unique:
            return None
        if len(unique) > self.MAX_RECOVERY_CANDIDATES:
            raise ProjectError(
                f"ROMVERSE found {len(unique)} recovery.img candidates, exceeding the "
                f"{self.MAX_RECOVERY_CANDIDATES}-image rollback ambiguity limit"
            )
        try:
            for path in unique:
                size = path.stat().st_size
                if size <= 0 or size > self.MAX_RECOVERY_BYTES:
                    raise ProjectError(
                        f"Stock recovery candidate {self._project_relative(project_root, path)} "
                        f"has an invalid size ({size:,} bytes)"
                    )
            identities = tuple((path, _sha256(path)) for path in unique) if len(unique) > 1 else ()
        except OSError as exc:
            raise ProjectError("Stock recovery candidates could not be verified") from exc
        if identities and len({digest for _path, digest in identities}) != 1:
            detail = ", ".join(
                f"{self._project_relative(project_root, path)} ({digest[:12]}…)"
                for path, digest in identities[:6]
            )
            raise ProjectError(
                "Conflicting byte-distinct recovery.img rollback candidates were found: " + detail
            )
        selected = min(unique, key=lambda path: self._recovery_rank(project_root, path))
        source_root = tree if selected.is_relative_to(tree) else project_root
        return selected, source_root

    @staticmethod
    def _project_relative(project_root: Path, path: Path) -> str:
        return path.relative_to(project_root).as_posix()

    @classmethod
    def _recovery_rank(cls, project_root: Path, path: Path) -> tuple[int, int, str]:
        relative = cls._project_relative(project_root, path)
        preferred = {
            "partitions/recovery.img": 0,
            "tree/images/recovery.img": 1,
            "tree/recovery.img": 2,
        }
        parts = Path(relative).parts
        return preferred.get(relative.casefold(), 3), len(parts), relative.casefold()


def inspect_android_boot_image(path: Path, tree: Path) -> BootImageEvidence:
    try:
        with path.open("rb") as stream:
            header = stream.read(64)
        image_size = path.stat().st_size
    except OSError as exc:
        raise ProjectError("Boot image header could not be read") from exc
    if len(header) < 44 or header[:8] != b"ANDROID!":
        raise ProjectError(f"{path.name} is not a recognized Android boot image")
    header_version = struct.unpack_from("<I", header, 40)[0]
    if header_version in (3, 4):
        expected_header_size = 1580 if header_version == 3 else 1584
        header_size = struct.unpack_from("<I", header, 20)[0]
        page_size = 4096
        kernel_size = struct.unpack_from("<I", header, 8)[0]
        ramdisk_size = struct.unpack_from("<I", header, 12)[0]
    elif header_version in (0, 1, 2):
        expected_header_size = {0: 1632, 1: 1648, 2: 1660}[header_version]
        header_size = expected_header_size
        page_size = struct.unpack_from("<I", header, 36)[0]
        kernel_size = struct.unpack_from("<I", header, 8)[0]
        ramdisk_size = struct.unpack_from("<I", header, 16)[0]
    else:
        raise ProjectError(f"Unsupported Android boot image header version {header_version}")
    if header_size != expected_header_size:
        raise ProjectError(
            f"Android boot v{header_version} header size {header_size} does not match "
            f"the required {expected_header_size} bytes"
        )
    if (
        page_size < 2048
        or page_size > 65536
        or page_size & (page_size - 1)
        or expected_header_size > page_size
    ):
        raise ProjectError("Android boot image has an invalid page or header layout")
    kernel_end = page_size + kernel_size
    ramdisk_offset = _align(kernel_end, page_size)
    if kernel_end > image_size or ramdisk_offset + ramdisk_size > image_size:
        raise ProjectError("Android boot image sections exceed the available file bytes")
    return BootImageEvidence(
        path.relative_to(tree).as_posix(),
        path.name,
        header_version,
        ramdisk_size,
        ramdisk_size > 0,
    )


def _align(value: int, boundary: int) -> int:
    return (value + boundary - 1) // boundary * boundary


def _record_digest(record: AscensionRollbackRecord) -> str:
    payload = asdict(record)
    payload.pop("record_digest")
    return _digest(payload)


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(AscensionEvidenceService.CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _exact_object(value: object, model: type[object]) -> bool:
    return isinstance(value, dict) and set(value) == {field.name for field in fields(model)}


def _safe_text(value: object, maximum: int, *, allow_empty: bool = False) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) <= maximum
        and "\x00" not in value
        and (allow_empty or value)
    )


def _sha256_value(value: object) -> bool:
    return bool(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value))


def _valid_artifact_shape(artifact: RollbackArtifact, maximum_text: int) -> bool:
    return bool(
        _safe_text(artifact.role, maximum_text)
        and _safe_text(artifact.source_relative_path, maximum_text)
        and _safe_text(artifact.vault_relative_path, maximum_text)
        and type(artifact.size_bytes) is int
        and artifact.size_bytes > 0
        and _sha256_value(artifact.sha256)
    )


def _valid_boot_shape(boot: BootImageEvidence, maximum_text: int) -> bool:
    return bool(
        _safe_text(boot.relative_path, maximum_text)
        and _safe_text(boot.image_name, maximum_text)
        and type(boot.header_version) is int
        and boot.header_version in {0, 1, 2, 3, 4}
        and type(boot.ramdisk_size_bytes) is int
        and boot.ramdisk_size_bytes > 0
        and type(boot.ramdisk_present) is bool
    )


def _valid_record_shape(record: AscensionRollbackRecord, maximum_text: int) -> bool:
    return bool(
        type(record.schema_version) is int
        and _safe_text(record.project_id, maximum_text)
        and _sha256_value(record.source_original_sha256)
        and _safe_text(record.created_at, maximum_text)
        and _valid_artifact_shape(record.patch_target, maximum_text)
        and (
            record.stock_recovery is None
            or _valid_artifact_shape(record.stock_recovery, maximum_text)
        )
        and _valid_boot_shape(record.boot_image, maximum_text)
        and _safe_text(record.authority, maximum_text)
        and type(record.phone_changed) is bool
        and _sha256_value(record.record_digest)
    )
