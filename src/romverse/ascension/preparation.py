from __future__ import annotations

import hashlib
import json
import os
import struct
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from romverse.ascension.evidence import AscensionEvidenceService
from romverse.ascension.models import AscensionMethod, OfficialRootRelease
from romverse.ascension.releases import OfficialRootReleaseService
from romverse.guardian.ascension_transfer import ascension_output_method
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
class RootPatchCapsule:
    schema_version: int
    capsule_id: str
    project_id: str
    method: AscensionMethod
    created_at: str
    source_original_sha256: str
    rollback_record_digest: str
    input_image_path: str
    input_image_sha256: str
    input_image_size_bytes: int
    manager_path: str
    manager_tag: str
    manager_sha256: str
    expected_output_name: str
    authority: str
    phone_changed: bool
    capsule_digest: str


@dataclass(frozen=True, slots=True)
class PatchedImageReceipt:
    schema_version: int
    receipt_id: str
    project_id: str
    method: AscensionMethod
    created_at: str
    capsule_digest: str
    source_image_sha256: str
    patched_image_path: str
    patched_image_sha256: str
    patched_image_size_bytes: int
    header_version: int
    ramdisk_size_bytes: int
    verification_scope: str
    flash_authority: str
    phone_changed: bool
    receipt_digest: str
    lineage_scope: str = ""
    lineage_confidence: str = ""
    normalized_header_sha256: str = ""
    source_kernel_size_bytes: int = 0
    patched_kernel_size_bytes: int = 0
    source_kernel_sha256: str = ""
    patched_kernel_sha256: str = ""


@dataclass(frozen=True, slots=True)
class _BootImageLayout:
    header_version: int
    ramdisk_size_bytes: int
    header_size_bytes: int
    page_size_bytes: int
    kernel_size_bytes: int
    normalized_header_sha256: str
    kernel_sha256: str


@dataclass(frozen=True, slots=True)
class _PatchLineage:
    scope: str
    confidence: str
    normalized_header_sha256: str
    source_kernel_size_bytes: int
    patched_kernel_size_bytes: int
    source_kernel_sha256: str
    patched_kernel_sha256: str


class RootPatchPreparationService:
    """Prepare and verify local root-patch inputs; never invoke a phone transport."""

    FORMAT = "romverse.root-patch-capsule"
    PATCHED_FORMAT = "romverse.patched-root-image"
    SCHEMA_VERSION = 1
    PATCHED_SCHEMA_VERSION = 2
    RECEIPT_NAME = "latest-patch-capsule.romverse"
    PATCHED_NAME = "latest-patched-image.romverse"
    CHUNK_SIZE = 4 * 1024 * 1024
    MAX_PATCH_GROWTH = 64 * 1024 * 1024
    MAX_RECEIPT_BYTES = 256 * 1024
    MAX_TEXT = 8192

    def __init__(
        self,
        store: RomProjectStore,
        release_service: OfficialRootReleaseService | None = None,
    ) -> None:
        self.store = store
        self.release_service = release_service or OfficialRootReleaseService(store.workspace)

    def prepare(
        self,
        project_id: str,
        method: AscensionMethod,
        release: OfficialRootRelease,
        manager_path: Path,
        progress: ProgressCallback | None = None,
    ) -> RootPatchCapsule:
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("A protected firmware source is required for root preparation")
        rollback = AscensionEvidenceService(self.store).load(project_id)
        if rollback is None:
            raise ProjectError("Automatic rollback evidence must be verified first")
        if release.provider is not method or release.asset.provider is not method:
            raise ProjectError("Official manager does not match the selected Ascension method")
        manager = self._verified_workspace_file(manager_path, release.asset.sha256)
        verified = self.release_service.load_verified(method)
        if verified is None:
            raise ProjectError(
                "Root preparation requires a freshly signature-verified official Manager from the Ascension vault"
            )
        vaulted_release, vaulted_manager = verified
        if release != vaulted_release or manager != vaulted_manager.resolve():
            raise ProjectError(
                "Root preparation refused manager metadata or a path that does not exactly match the revalidated Ascension vault"
            )
        source = self._verified_workspace_file(
            self.store.workspace / rollback.patch_target.vault_relative_path,
            rollback.patch_target.sha256,
        )

        existing = self.load(project_id, method)
        if (
            existing is not None
            and existing.rollback_record_digest == rollback.record_digest
            and self.matches_release(existing, release)
        ):
            return existing

        root = self.store.projects_root / project_id / "ascension" / "capsules" / method.value
        try:
            ensure_private_directory(root, boundary=self.store.workspace)
        except LocalStoreError as exc:
            raise ProjectError("Root patch capsule vault could not be prepared safely") from exc
        input_path = (
            root
            / f"{rollback.patch_target.sha256[:16]}-{Path(rollback.patch_target.source_relative_path).name}"
        )
        manager_copy = root / f"{release.asset.sha256[:16]}-{release.asset.name}"
        planned_bytes = max(1, 2 * (source.stat().st_size + manager.stat().st_size))
        completed_bytes = 0

        def copied(amount: int) -> None:
            nonlocal completed_bytes
            completed_bytes += amount
            self._report(progress, min(99, round(completed_bytes * 100 / planned_bytes)))

        self._report(progress, 0)
        source_reused = self._copy_verified(
            source,
            input_path,
            rollback.patch_target.sha256,
            copied,
        )
        if source_reused:
            copied(source.stat().st_size)
        manager_reused = self._copy_verified(
            manager,
            manager_copy,
            release.asset.sha256,
            copied,
        )
        if manager_reused:
            copied(manager.stat().st_size)
        expected = (
            f"magisk_patched-{rollback.patch_target.sha256[:8]}.img"
            if method is AscensionMethod.MAGISK
            else f"kernelsu_patched-{rollback.patch_target.sha256[:8]}.img"
        )
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "capsule_id": uuid4().hex,
            "project_id": project_id,
            "method": method.value,
            "created_at": datetime.now(UTC).isoformat(),
            "source_original_sha256": project.original.sha256,
            "rollback_record_digest": rollback.record_digest,
            "input_image_path": input_path.relative_to(self.store.workspace).as_posix(),
            "input_image_sha256": rollback.patch_target.sha256,
            "input_image_size_bytes": input_path.stat().st_size,
            "manager_path": manager_copy.relative_to(self.store.workspace).as_posix(),
            "manager_tag": release.tag,
            "manager_sha256": release.asset.sha256,
            "expected_output_name": expected,
            "authority": "verified-root-patch-inputs-only",
            "phone_changed": False,
        }
        digest = _digest(payload)
        capsule = RootPatchCapsule(
            self.SCHEMA_VERSION,
            str(payload["capsule_id"]),
            project_id,
            method,
            str(payload["created_at"]),
            project.original.sha256,
            rollback.record_digest,
            str(payload["input_image_path"]),
            rollback.patch_target.sha256,
            input_path.stat().st_size,
            str(payload["manager_path"]),
            release.tag,
            release.asset.sha256,
            expected,
            "verified-root-patch-inputs-only",
            False,
            digest,
        )
        try:
            atomic_write_json(
                root / self.RECEIPT_NAME,
                {"format": self.FORMAT, **asdict(capsule), "method": method.value},
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
        except LocalStoreError as exc:
            raise ProjectError("Root patch capsule receipt could not be stored safely") from exc
        self._report(progress, 100)
        return capsule

    @staticmethod
    def matches_release(
        capsule: RootPatchCapsule,
        release: OfficialRootRelease,
    ) -> bool:
        """Return whether a capsule is bound to this exact official manager release."""

        return bool(
            capsule.method is release.provider
            and release.asset.provider is release.provider
            and capsule.manager_tag == release.tag == release.asset.tag
            and capsule.manager_sha256 == release.asset.sha256
        )

    def load(self, project_id: str, method: AscensionMethod) -> RootPatchCapsule | None:
        project = self.store.get(project_id)
        path = (
            self.store.projects_root
            / project_id
            / "ascension"
            / "capsules"
            / method.value
            / self.RECEIPT_NAME
        )
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            if (
                set(data) != {"format", *(field.name for field in fields(RootPatchCapsule))}
                or data.pop("format") != self.FORMAT
                or not isinstance(data.get("method"), str)
            ):
                return None
            data["method"] = AscensionMethod(data["method"])
            capsule = RootPatchCapsule(**data)
        except (LocalStoreError, ValueError, TypeError, KeyError):
            return None
        unsigned = asdict(capsule)
        unsigned.pop("capsule_digest")
        unsigned["method"] = capsule.method.value
        if (
            project.original is None
            or not _valid_capsule_shape(capsule, self.MAX_TEXT)
            or capsule.schema_version != self.SCHEMA_VERSION
            or capsule.project_id != project_id
            or capsule.method is not method
            or capsule.source_original_sha256 != project.original.sha256
            or capsule.authority != "verified-root-patch-inputs-only"
            or capsule.phone_changed
            or capsule.capsule_digest != _digest(unsigned)
        ):
            return None
        for relative, digest, size in (
            (capsule.input_image_path, capsule.input_image_sha256, capsule.input_image_size_bytes),
            (capsule.manager_path, capsule.manager_sha256, 0),
        ):
            try:
                artifact = self._workspace_relative(relative)
                if size and artifact.stat().st_size != size:
                    return None
                if _sha256(artifact) != digest:
                    return None
            except (OSError, ProjectError):
                return None
        return capsule

    def import_patched(
        self,
        project_id: str,
        method: AscensionMethod,
        source: Path,
        progress: ProgressCallback | None = None,
    ) -> PatchedImageReceipt:
        capsule = self.load(project_id, method)
        if capsule is None:
            raise ProjectError("Prepare and verify the root patch capsule first")
        path = source.expanduser()
        if path.is_symlink():
            raise ProjectError("Patched image cannot be a symbolic link")
        try:
            path = path.resolve(strict=True)
            stat = path.stat()
        except OSError as exc:
            raise ProjectError("Patched image is unavailable") from exc
        identified_method = ascension_output_method(path.name)
        if identified_method is not None and identified_method != method.value:
            actual = AscensionMethod(identified_method)
            raise ProjectError(
                f"The filename identifies a {actual.display_name} output, but Ascension is following the {method.display_name} route"
            )
        if not path.is_file() or stat.st_size <= 64:
            raise ProjectError("Patched image is empty or incomplete")
        if stat.st_size > capsule.input_image_size_bytes + self.MAX_PATCH_GROWTH:
            raise ProjectError("Patched image exceeds the bounded boot-image growth limit")
        source_image = self._workspace_relative(capsule.input_image_path)
        lineage = _verify_patch_lineage(source_image, path, method)
        header_version, ramdisk_size = _boot_header(path)
        digest = _sha256(path)
        if digest == capsule.input_image_sha256:
            raise ProjectError("Patched image is byte-identical to the pristine source image")
        root = self.store.projects_root / project_id / "ascension" / "patched" / method.value
        try:
            ensure_private_directory(root, boundary=self.store.workspace)
        except LocalStoreError as exc:
            raise ProjectError("Patched image vault could not be prepared safely") from exc
        destination = root / f"{digest[:16]}-{capsule.expected_output_name}"
        planned_passes = 3 if destination.exists() or destination.is_symlink() else 2
        planned_bytes = max(1, stat.st_size * planned_passes)
        completed_bytes = 0

        def copied(amount: int) -> None:
            nonlocal completed_bytes
            completed_bytes += amount
            self._report(progress, min(99, round(completed_bytes * 100 / planned_bytes)))

        self._report(progress, 0)
        self._copy_verified(path, destination, digest, copied)
        payload: dict[str, object] = {
            "schema_version": self.PATCHED_SCHEMA_VERSION,
            "receipt_id": uuid4().hex,
            "project_id": project_id,
            "method": method.value,
            "created_at": datetime.now(UTC).isoformat(),
            "capsule_digest": capsule.capsule_digest,
            "source_image_sha256": capsule.input_image_sha256,
            "patched_image_path": destination.relative_to(self.store.workspace).as_posix(),
            "patched_image_sha256": digest,
            "patched_image_size_bytes": destination.stat().st_size,
            "header_version": header_version,
            "ramdisk_size_bytes": ramdisk_size,
            "verification_scope": "source-capsule-and-immutable-lineage-consistency",
            "flash_authority": "none",
            "phone_changed": False,
            "lineage_scope": lineage.scope,
            "lineage_confidence": lineage.confidence,
            "normalized_header_sha256": lineage.normalized_header_sha256,
            "source_kernel_size_bytes": lineage.source_kernel_size_bytes,
            "patched_kernel_size_bytes": lineage.patched_kernel_size_bytes,
            "source_kernel_sha256": lineage.source_kernel_sha256,
            "patched_kernel_sha256": lineage.patched_kernel_sha256,
        }
        receipt_digest = _digest(payload)
        receipt = PatchedImageReceipt(
            schema_version=self.PATCHED_SCHEMA_VERSION,
            receipt_id=str(payload["receipt_id"]),
            project_id=project_id,
            method=method,
            created_at=str(payload["created_at"]),
            capsule_digest=capsule.capsule_digest,
            source_image_sha256=capsule.input_image_sha256,
            patched_image_path=str(payload["patched_image_path"]),
            patched_image_sha256=digest,
            patched_image_size_bytes=destination.stat().st_size,
            header_version=header_version,
            ramdisk_size_bytes=ramdisk_size,
            verification_scope="source-capsule-and-immutable-lineage-consistency",
            flash_authority="none",
            phone_changed=False,
            receipt_digest=receipt_digest,
            lineage_scope=lineage.scope,
            lineage_confidence=lineage.confidence,
            normalized_header_sha256=lineage.normalized_header_sha256,
            source_kernel_size_bytes=lineage.source_kernel_size_bytes,
            patched_kernel_size_bytes=lineage.patched_kernel_size_bytes,
            source_kernel_sha256=lineage.source_kernel_sha256,
            patched_kernel_sha256=lineage.patched_kernel_sha256,
        )
        try:
            atomic_write_json(
                root / self.PATCHED_NAME,
                {"format": self.PATCHED_FORMAT, **asdict(receipt), "method": method.value},
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
        except LocalStoreError as exc:
            raise ProjectError("Patched image receipt could not be stored safely") from exc
        self._report(progress, 100)
        return receipt

    def load_patched(
        self,
        project_id: str,
        method: AscensionMethod,
    ) -> PatchedImageReceipt | None:
        capsule = self.load(project_id, method)
        if capsule is None:
            return None
        path = (
            self.store.projects_root
            / project_id
            / "ascension"
            / "patched"
            / method.value
            / self.PATCHED_NAME
        )
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            if (
                type(data.get("schema_version")) is not int
                or not _patched_document_shape(data, int(data["schema_version"]))
                or data.pop("format") != self.PATCHED_FORMAT
                or not isinstance(data.get("method"), str)
            ):
                return None
            data["method"] = AscensionMethod(data["method"])
            if data["schema_version"] == self.SCHEMA_VERSION:
                for field in _PATCH_LINEAGE_FIELDS:
                    data.setdefault(field, "" if "size_bytes" not in field else 0)
            receipt = PatchedImageReceipt(**data)
        except (LocalStoreError, ValueError, TypeError, KeyError):
            return None
        unsigned = asdict(receipt)
        unsigned.pop("receipt_digest")
        unsigned["method"] = receipt.method.value
        if (
            not _valid_patched_shape(receipt, self.MAX_TEXT)
            or receipt.schema_version not in {self.SCHEMA_VERSION, self.PATCHED_SCHEMA_VERSION}
            or receipt.project_id != project_id
            or receipt.method is not method
            or receipt.capsule_digest != capsule.capsule_digest
            or receipt.source_image_sha256 != capsule.input_image_sha256
            or receipt.flash_authority != "none"
            or receipt.phone_changed
        ):
            return None
        try:
            artifact = self._workspace_relative(receipt.patched_image_path)
            if (
                artifact.stat().st_size != receipt.patched_image_size_bytes
                or _sha256(artifact) != receipt.patched_image_sha256
            ):
                return None
            header, ramdisk = _boot_header(artifact)
            source_image = self._workspace_relative(capsule.input_image_path)
        except (OSError, ProjectError):
            return None
        if header != receipt.header_version or ramdisk != receipt.ramdisk_size_bytes:
            return None
        if receipt.schema_version == self.SCHEMA_VERSION:
            legacy_unsigned = dict(unsigned)
            for field in (
                "lineage_scope",
                "lineage_confidence",
                "normalized_header_sha256",
                "source_kernel_size_bytes",
                "patched_kernel_size_bytes",
                "source_kernel_sha256",
                "patched_kernel_sha256",
            ):
                legacy_unsigned.pop(field)
            if (
                receipt.verification_scope != "source-bound-structural-patch-candidate"
                or receipt.receipt_digest != _digest(legacy_unsigned)
            ):
                return None
            try:
                lineage = _verify_patch_lineage(source_image, artifact, method)
            except ProjectError:
                return None
            upgraded = replace(
                receipt,
                schema_version=self.PATCHED_SCHEMA_VERSION,
                verification_scope="source-capsule-and-immutable-lineage-consistency",
                receipt_digest="",
                lineage_scope=lineage.scope,
                lineage_confidence=lineage.confidence,
                normalized_header_sha256=lineage.normalized_header_sha256,
                source_kernel_size_bytes=lineage.source_kernel_size_bytes,
                patched_kernel_size_bytes=lineage.patched_kernel_size_bytes,
                source_kernel_sha256=lineage.source_kernel_sha256,
                patched_kernel_sha256=lineage.patched_kernel_sha256,
            )
            upgraded_unsigned = asdict(upgraded)
            upgraded_unsigned.pop("receipt_digest")
            upgraded_unsigned["method"] = method.value
            upgraded = replace(upgraded, receipt_digest=_digest(upgraded_unsigned))
            try:
                atomic_write_json(
                    path,
                    {"format": self.PATCHED_FORMAT, **asdict(upgraded), "method": method.value},
                    boundary=self.store.workspace,
                    maximum_bytes=self.MAX_RECEIPT_BYTES,
                )
            except LocalStoreError:
                return None
            return upgraded
        if (
            receipt.schema_version != self.PATCHED_SCHEMA_VERSION
            or receipt.verification_scope != "source-capsule-and-immutable-lineage-consistency"
            or receipt.lineage_confidence not in {"high", "caution", "limited"}
            or receipt.lineage_scope
            not in {
                "normalized-header-and-kernel",
                "normalized-header-kernelless",
                "normalized-header-magisk-kernel-modified",
            }
            or not _sha256_value(receipt.normalized_header_sha256)
            or receipt.source_kernel_size_bytes < 0
            or receipt.patched_kernel_size_bytes < 0
            or not _optional_sha256(receipt.source_kernel_sha256)
            or not _optional_sha256(receipt.patched_kernel_sha256)
            or receipt.receipt_digest != _digest(unsigned)
        ):
            return None
        try:
            source_layout = _boot_layout(source_image)
            patched_layout = _boot_layout(artifact)
        except ProjectError:
            return None
        if (
            source_layout.normalized_header_sha256 != receipt.normalized_header_sha256
            or patched_layout.normalized_header_sha256 != receipt.normalized_header_sha256
            or source_layout.kernel_size_bytes != receipt.source_kernel_size_bytes
            or patched_layout.kernel_size_bytes != receipt.patched_kernel_size_bytes
        ):
            return None
        return receipt

    def _verified_workspace_file(self, path: Path, expected_sha256: str) -> Path:
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise ProjectError("Required Ascension artifact is unavailable") from exc
        if (
            path.is_symlink()
            or not resolved.is_file()
            or not resolved.is_relative_to(self.store.workspace.resolve())
            or _sha256(resolved) != expected_sha256
        ):
            raise ProjectError("Required Ascension artifact failed workspace verification")
        return resolved

    def _workspace_relative(self, relative: str) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or "\x00" in relative:
            raise ProjectError("Unsafe Ascension artifact path")
        unresolved = self.store.workspace / candidate
        if unresolved.is_symlink():
            raise ProjectError("Ascension artifact cannot be a symbolic link")
        try:
            resolved = unresolved.resolve(strict=True)
        except OSError as exc:
            raise ProjectError("Ascension artifact is unavailable") from exc
        if not resolved.is_file() or not resolved.is_relative_to(self.store.workspace.resolve()):
            raise ProjectError("Ascension artifact escaped the workspace")
        return resolved

    def _copy_verified(
        self,
        source: Path,
        destination: Path,
        expected_sha256: str,
        progress: Callable[[int], None] | None = None,
    ) -> bool:
        if destination.is_file() and not destination.is_symlink():
            if _sha256(destination, progress) == expected_sha256:
                return True
            destination.chmod(0o600)
            destination.unlink()
        elif destination.exists() or destination.is_symlink():
            raise ProjectError("Ascension capsule destination is not a regular file")
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        try:
            with source.open("rb") as incoming, temporary.open("xb") as outgoing:
                while chunk := incoming.read(self.CHUNK_SIZE):
                    outgoing.write(chunk)
                    if progress is not None:
                        progress(len(chunk))
                outgoing.flush()
                os.fsync(outgoing.fileno())
            if _sha256(temporary, progress) != expected_sha256:
                raise ProjectError("Ascension capsule copy failed SHA-256 verification")
            os.replace(temporary, destination)
            destination.chmod(0o444)
        finally:
            temporary.unlink(missing_ok=True)
        return False

    @staticmethod
    def _report(progress: ProgressCallback | None, value: int) -> None:
        if progress is not None:
            progress(value)


def _boot_header(path: Path) -> tuple[int, int]:
    layout = _boot_layout(path)
    return layout.header_version, layout.ramdisk_size_bytes


def _boot_layout(path: Path) -> _BootImageLayout:
    try:
        with path.open("rb") as stream:
            prefix = stream.read(4096)
        image_size = path.stat().st_size
    except OSError as exc:
        raise ProjectError("Patched boot image header could not be read") from exc
    if len(prefix) < 44 or prefix[:8] != b"ANDROID!":
        raise ProjectError("Patched output is not a recognized Android boot image")
    version = struct.unpack_from("<I", prefix, 40)[0]
    if version in (3, 4):
        expected_header_size = 1580 if version == 3 else 1584
        header_size = struct.unpack_from("<I", prefix, 20)[0]
        page_size = 4096
        kernel_size = struct.unpack_from("<I", prefix, 8)[0]
        ramdisk_size = struct.unpack_from("<I", prefix, 12)[0]
        mutable_ranges = [(8, 16)]
        if version == 4:
            mutable_ranges.append((1580, 1584))
    elif version in (0, 1, 2):
        expected_header_size = {0: 1632, 1: 1648, 2: 1660}[version]
        header_size = expected_header_size
        page_size = struct.unpack_from("<I", prefix, 36)[0]
        kernel_size = struct.unpack_from("<I", prefix, 8)[0]
        ramdisk_size = struct.unpack_from("<I", prefix, 16)[0]
        mutable_ranges = [(8, 12), (16, 20), (576, 608)]
    else:
        raise ProjectError(f"Patched image uses unsupported boot header version {version}")
    if header_size != expected_header_size:
        raise ProjectError(
            f"Patched image header size {header_size} does not match Android boot v{version}"
        )
    if (
        page_size < 2048
        or page_size > 65536
        or page_size & (page_size - 1)
        or expected_header_size > page_size
        or len(prefix) < expected_header_size
    ):
        raise ProjectError("Patched image uses an invalid Android boot page or header layout")
    kernel_offset = page_size
    kernel_end = kernel_offset + kernel_size
    ramdisk_offset = _align(kernel_end, page_size)
    ramdisk_end = ramdisk_offset + ramdisk_size
    if kernel_end > image_size or ramdisk_end > image_size:
        raise ProjectError("Patched image sections exceed the available boot image bytes")
    if ramdisk_size <= 0:
        raise ProjectError("Patched boot image contains no ramdisk")
    normalized = bytearray(prefix[:expected_header_size])
    for start, end in mutable_ranges:
        normalized[start:end] = b"\0" * (end - start)
    return _BootImageLayout(
        version,
        ramdisk_size,
        expected_header_size,
        page_size,
        kernel_size,
        hashlib.sha256(normalized).hexdigest(),
        _hash_region(path, kernel_offset, kernel_size) if kernel_size else "",
    )


def _verify_patch_lineage(
    source: Path,
    patched: Path,
    method: AscensionMethod,
) -> _PatchLineage:
    pristine = _boot_layout(source)
    candidate = _boot_layout(patched)
    if (
        candidate.header_version != pristine.header_version
        or candidate.header_size_bytes != pristine.header_size_bytes
        or candidate.page_size_bytes != pristine.page_size_bytes
        or candidate.normalized_header_sha256 != pristine.normalized_header_sha256
    ):
        raise ProjectError(
            "Patched image immutable Android header lineage does not match the pristine capsule input"
        )
    pristine_has_kernel = pristine.kernel_size_bytes > 0
    candidate_has_kernel = candidate.kernel_size_bytes > 0
    if pristine_has_kernel != candidate_has_kernel:
        raise ProjectError("Patched image changed whether the source boot image contains a kernel")
    kernel_matches = bool(
        pristine_has_kernel
        and pristine.kernel_size_bytes == candidate.kernel_size_bytes
        and pristine.kernel_sha256 == candidate.kernel_sha256
    )
    if method is AscensionMethod.KERNELSU_LKM and pristine_has_kernel and not kernel_matches:
        raise ProjectError(
            "KernelSU LKM output changed the pristine kernel; this route is allowed to modify only the ramdisk"
        )
    if not pristine_has_kernel:
        scope = "normalized-header-kernelless"
        confidence = "limited"
    elif kernel_matches:
        scope = "normalized-header-and-kernel"
        confidence = "high"
    else:
        scope = "normalized-header-magisk-kernel-modified"
        confidence = "caution"
    return _PatchLineage(
        scope,
        confidence,
        pristine.normalized_header_sha256,
        pristine.kernel_size_bytes,
        candidate.kernel_size_bytes,
        pristine.kernel_sha256,
        candidate.kernel_sha256,
    )


def _align(value: int, boundary: int) -> int:
    return (value + boundary - 1) // boundary * boundary


def _hash_region(path: Path, offset: int, size: int) -> str:
    digest = hashlib.sha256()
    remaining = size
    try:
        with path.open("rb") as stream:
            stream.seek(offset)
            while remaining:
                chunk = stream.read(min(RootPatchPreparationService.CHUNK_SIZE, remaining))
                if not chunk:
                    raise ProjectError("Android boot kernel section ended unexpectedly")
                digest.update(chunk)
                remaining -= len(chunk)
    except OSError as exc:
        raise ProjectError("Android boot kernel lineage could not be read") from exc
    return digest.hexdigest()


def _sha256(path: Path, progress: Callable[[int], None] | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(RootPatchPreparationService.CHUNK_SIZE):
            digest.update(chunk)
            if progress is not None:
                progress(len(chunk))
    return digest.hexdigest()


def _sha256_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _optional_sha256(value: object) -> bool:
    return value == "" or _sha256_value(value)


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


_PATCH_LINEAGE_FIELDS = frozenset(
    {
        "lineage_scope",
        "lineage_confidence",
        "normalized_header_sha256",
        "source_kernel_size_bytes",
        "patched_kernel_size_bytes",
        "source_kernel_sha256",
        "patched_kernel_sha256",
    }
)


def _patched_document_shape(data: dict[str, object], schema_version: int) -> bool:
    current = {"format", *(field.name for field in fields(PatchedImageReceipt))}
    if schema_version == RootPatchPreparationService.PATCHED_SCHEMA_VERSION:
        return set(data) == current
    if schema_version == RootPatchPreparationService.SCHEMA_VERSION:
        return set(data) == current - _PATCH_LINEAGE_FIELDS
    return False


def _safe_text(value: object, maximum: int, *, allow_empty: bool = False) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) <= maximum
        and "\x00" not in value
        and (allow_empty or value)
    )


def _valid_capsule_shape(capsule: RootPatchCapsule, maximum_text: int) -> bool:
    return bool(
        type(capsule.schema_version) is int
        and _safe_text(capsule.capsule_id, maximum_text)
        and _safe_text(capsule.project_id, maximum_text)
        and isinstance(capsule.method, AscensionMethod)
        and _safe_text(capsule.created_at, maximum_text)
        and _sha256_value(capsule.source_original_sha256)
        and _sha256_value(capsule.rollback_record_digest)
        and _safe_text(capsule.input_image_path, maximum_text)
        and _sha256_value(capsule.input_image_sha256)
        and type(capsule.input_image_size_bytes) is int
        and capsule.input_image_size_bytes > 0
        and _safe_text(capsule.manager_path, maximum_text)
        and _safe_text(capsule.manager_tag, maximum_text)
        and _sha256_value(capsule.manager_sha256)
        and _safe_text(capsule.expected_output_name, maximum_text)
        and _safe_text(capsule.authority, maximum_text)
        and type(capsule.phone_changed) is bool
        and _sha256_value(capsule.capsule_digest)
    )


def _valid_patched_shape(receipt: PatchedImageReceipt, maximum_text: int) -> bool:
    return bool(
        type(receipt.schema_version) is int
        and _safe_text(receipt.receipt_id, maximum_text)
        and _safe_text(receipt.project_id, maximum_text)
        and isinstance(receipt.method, AscensionMethod)
        and _safe_text(receipt.created_at, maximum_text)
        and _sha256_value(receipt.capsule_digest)
        and _sha256_value(receipt.source_image_sha256)
        and _safe_text(receipt.patched_image_path, maximum_text)
        and _sha256_value(receipt.patched_image_sha256)
        and type(receipt.patched_image_size_bytes) is int
        and receipt.patched_image_size_bytes > 64
        and type(receipt.header_version) is int
        and receipt.header_version in {0, 1, 2, 3, 4}
        and type(receipt.ramdisk_size_bytes) is int
        and receipt.ramdisk_size_bytes > 0
        and _safe_text(receipt.verification_scope, maximum_text)
        and _safe_text(receipt.flash_authority, maximum_text)
        and type(receipt.phone_changed) is bool
        and _sha256_value(receipt.receipt_digest)
        and _safe_text(receipt.lineage_scope, maximum_text, allow_empty=True)
        and _safe_text(receipt.lineage_confidence, maximum_text, allow_empty=True)
        and _optional_sha256(receipt.normalized_header_sha256)
        and type(receipt.source_kernel_size_bytes) is int
        and receipt.source_kernel_size_bytes >= 0
        and type(receipt.patched_kernel_size_bytes) is int
        and receipt.patched_kernel_size_bytes >= 0
        and _optional_sha256(receipt.source_kernel_sha256)
        and _optional_sha256(receipt.patched_kernel_sha256)
    )
