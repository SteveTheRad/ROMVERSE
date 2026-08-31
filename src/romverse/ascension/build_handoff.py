from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from romverse.ascension.integration import RootRomIntegrationService
from romverse.ascension.models import AscensionMethod
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)
from romverse.rom.builds import RomBuildPlanner
from romverse.rom.inspection import RomInspectionService
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore

ProgressCallback = Callable[[int], None]


@dataclass(frozen=True, slots=True)
class RootRomBuildHandoffReceipt:
    schema_version: int
    handoff_id: str
    project_id: str
    method: AscensionMethod
    created_at: str
    source_original_sha256: str
    integration_digest: str
    target_relative_path: str
    target_partition: str
    artifact_relative_path: str
    artifact_sha256: str
    artifact_size_bytes: int
    packaging_route: str
    build_plan_tree_sha256: str
    build_plan_bound: bool
    authority: str
    phone_changed: bool
    flash_authority: bool
    bootloader_relock_allowed: bool
    handoff_digest: str


class RootRomBuildHandoffService:
    """Seal the integrated root image as a deterministic ROM build artifact.

    This service deliberately has no device transport.  It copies the already
    verified image out of the mutable working input, verifies the copy byte for
    byte, and records exactly which future packaging route must consume it.
    """

    FORMAT = "romverse.root-rom-build-handoff"
    SCHEMA_VERSION = 2
    RECEIPT_NAME = "root-rom-build-handoff.romverse"
    CHUNK_SIZE = 4 * 1024 * 1024
    ALLOWED_PARTITIONS = {"boot", "init_boot", "recovery", "vendor_boot"}
    MAX_RECEIPT_BYTES = 256 * 1024
    MAX_TEXT = 8192

    def __init__(self, store: RomProjectStore) -> None:
        self.store = store

    def seal(
        self,
        project_id: str,
        method: AscensionMethod,
        progress: ProgressCallback | None = None,
    ) -> RootRomBuildHandoffReceipt:
        existing = self.load(project_id, method)
        if existing is not None and existing.schema_version == self.SCHEMA_VERSION:
            return existing
        project = self.store.get(project_id)
        integration_service = RootRomIntegrationService(self.store)
        integration = integration_service.load(project_id, method)
        if project.original is None or integration is None:
            raise ProjectError("Integrate and verify the rooted ROM input before sealing it")
        target, _root, relative = integration_service._target(  # noqa: SLF001
            project_id,
            integration.target_relative_path,
        )
        partition = relative.stem.casefold()
        if partition not in self.ALLOWED_PARTITIONS:
            raise ProjectError("Ascension build handoff found an unsupported target partition")
        digest = _sha256(target)
        if digest != integration.integrated_image_sha256:
            raise ProjectError("Integrated root image changed before the build handoff")
        output_root = self._root(project_id)
        try:
            ensure_private_directory(output_root, boundary=self.store.workspace)
        except LocalStoreError as exc:
            raise ProjectError("Ascension build vault could not be prepared safely") from exc
        artifact = output_root / f"rooted-{partition}-{digest[:20]}.img"
        temporary = output_root / f".{artifact.name}.{uuid4().hex}.part"
        try:
            if artifact.exists():
                if artifact.is_symlink() or not artifact.is_file() or _sha256(artifact) != digest:
                    raise ProjectError("Existing Ascension build artifact failed integrity checks")
            else:
                self._copy(target, temporary)
                if _sha256(temporary) != digest:
                    raise ProjectError("Ascension build artifact failed byte verification")
                os.replace(temporary, artifact)
                artifact.chmod(0o600)
            if artifact.stat().st_size != target.stat().st_size or _sha256(artifact) != digest:
                raise ProjectError("Sealed Ascension build artifact does not match its input")
            artifact.chmod(0o600)
        finally:
            temporary.unlink(missing_ok=True)

        route = "fastboot-image-tree" if relative.parts[0] != "partitions" else "payload-partition"
        build_plan = None
        if RomInspectionService(self.store).summarize_working_tree(project_id) is not None:
            build_plan = RomBuildPlanner(self.store).plan(project_id)
            verification = RomBuildPlanner(self.store).verify_tree(project_id)
            if not verification.valid:
                raise ProjectError("Ascension could not freeze the rooted ROM working tree")
        plan_bound = bool(
            build_plan is not None
            and route == "fastboot-image-tree"
            and relative.as_posix() in build_plan.input_files
        )
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "handoff_id": uuid4().hex,
            "project_id": project_id,
            "method": method.value,
            "created_at": datetime.now(UTC).isoformat(),
            "source_original_sha256": project.original.sha256,
            "integration_digest": integration.integration_digest,
            "target_relative_path": relative.as_posix(),
            "target_partition": partition,
            "artifact_relative_path": artifact.relative_to(self.store.workspace).as_posix(),
            "artifact_sha256": digest,
            "artifact_size_bytes": artifact.stat().st_size,
            "packaging_route": route,
            "build_plan_tree_sha256": build_plan.tree_sha256 if build_plan is not None else "",
            "build_plan_bound": plan_bound,
            "authority": "contained-rom-build-input-only",
            "phone_changed": False,
            "flash_authority": False,
            "bootloader_relock_allowed": False,
        }
        receipt = RootRomBuildHandoffReceipt(
            **{**payload, "method": method},
            handoff_digest=_digest(payload),
        )
        document = {"format": self.FORMAT, **asdict(receipt), "method": method.value}
        try:
            for path in (
                output_root / self.RECEIPT_NAME,
                output_root / f"build-handoff-{receipt.handoff_id[:12]}.romverse",
            ):
                atomic_write_json(
                    path,
                    document,
                    boundary=self.store.workspace,
                    maximum_bytes=self.MAX_RECEIPT_BYTES,
                )
        except LocalStoreError as exc:
            raise ProjectError("Ascension build handoff could not be stored safely") from exc
        return receipt

    def load(
        self,
        project_id: str,
        method: AscensionMethod,
    ) -> RootRomBuildHandoffReceipt | None:
        try:
            data = read_json_object(
                self._root(project_id) / self.RECEIPT_NAME,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            if type(data.get("schema_version")) is not int:
                return None
            schema_version = data["schema_version"]
            if (
                not _handoff_document_shape(data, schema_version)
                or data.pop("format") != self.FORMAT
                or not isinstance(data.get("method"), str)
            ):
                return None
            if schema_version == 1:
                data.setdefault("build_plan_tree_sha256", "")
                data.setdefault("build_plan_bound", False)
            data["method"] = AscensionMethod(data["method"])
            receipt = RootRomBuildHandoffReceipt(**data)
        except (LocalStoreError, ValueError, TypeError, KeyError):
            return None
        project = self.store.get(project_id)
        integration = RootRomIntegrationService(self.store).load(project_id, method)
        unsigned = asdict(receipt)
        unsigned.pop("handoff_digest")
        unsigned["method"] = receipt.method.value
        digest_payload = dict(unsigned)
        if receipt.schema_version == 1:
            digest_payload.pop("build_plan_tree_sha256", None)
            digest_payload.pop("build_plan_bound", None)
        if (
            project.original is None
            or integration is None
            or not _valid_handoff_shape(receipt, self.MAX_TEXT)
            or receipt.schema_version not in {1, self.SCHEMA_VERSION}
            or receipt.project_id != project_id
            or receipt.method is not method
            or receipt.source_original_sha256 != project.original.sha256
            or receipt.integration_digest != integration.integration_digest
            or receipt.target_relative_path != integration.target_relative_path
            or receipt.target_partition not in self.ALLOWED_PARTITIONS
            or receipt.artifact_sha256 != integration.integrated_image_sha256
            or receipt.packaging_route not in {"fastboot-image-tree", "payload-partition"}
            or (
                receipt.schema_version >= 2
                and receipt.build_plan_bound
                != bool(
                    receipt.packaging_route == "fastboot-image-tree"
                    and receipt.build_plan_tree_sha256
                )
            )
            or receipt.authority != "contained-rom-build-input-only"
            or receipt.phone_changed
            or receipt.flash_authority
            or receipt.bootloader_relock_allowed
            or receipt.handoff_digest != _digest(digest_payload)
        ):
            return None
        try:
            artifact = self._artifact(receipt.artifact_relative_path)
            if (
                artifact.stat().st_size != receipt.artifact_size_bytes
                or _sha256(artifact) != receipt.artifact_sha256
            ):
                return None
            if receipt.build_plan_tree_sha256:
                plan = RomBuildPlanner(self.store).load(project_id)
                if (
                    plan is None
                    or plan.tree_sha256 != receipt.build_plan_tree_sha256
                    or not RomBuildPlanner(self.store).verify_tree(project_id).valid
                    or (
                        receipt.build_plan_bound
                        and receipt.target_relative_path not in plan.input_files
                    )
                ):
                    return None
        except (OSError, ProjectError):
            return None
        return receipt

    def artifact_path(self, receipt: RootRomBuildHandoffReceipt) -> Path:
        loaded = self.load(receipt.project_id, receipt.method)
        if loaded != receipt:
            raise ProjectError("Ascension build handoff is no longer verified")
        return self._artifact(receipt.artifact_relative_path)

    def _root(self, project_id: str) -> Path:
        self.store.get(project_id)
        return self.store.projects_root / project_id / "ascension" / "build-handoff"

    def _artifact(self, relative_text: str) -> Path:
        relative = Path(relative_text)
        if relative.is_absolute() or ".." in relative.parts:
            raise ProjectError("Ascension build artifact path is unsafe")
        unresolved = self.store.workspace / relative
        if unresolved.is_symlink():
            raise ProjectError("Ascension build artifact cannot be a symbolic link")
        artifact = unresolved.resolve(strict=True)
        if not artifact.is_file() or not artifact.is_relative_to(self.store.workspace.resolve()):
            raise ProjectError("Ascension build artifact escaped its contained workspace")
        return artifact

    def _copy(
        self,
        source: Path,
        destination: Path,
    ) -> None:
        with source.open("rb") as incoming, destination.open("xb") as outgoing:
            while chunk := incoming.read(self.CHUNK_SIZE):
                outgoing.write(chunk)
            outgoing.flush()
            os.fsync(outgoing.fileno())


def _sha256(
    path: Path,
) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


_BUILD_PLAN_FIELDS = frozenset({"build_plan_tree_sha256", "build_plan_bound"})


def _handoff_document_shape(data: dict[str, object], schema_version: int) -> bool:
    current = {"format", *(field.name for field in fields(RootRomBuildHandoffReceipt))}
    if schema_version == RootRomBuildHandoffService.SCHEMA_VERSION:
        return set(data) == current
    if schema_version == 1:
        return set(data) == current - _BUILD_PLAN_FIELDS
    return False


def _safe_text(value: object, maximum: int, *, allow_empty: bool = False) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) <= maximum
        and "\x00" not in value
        and (allow_empty or value)
    )


def _sha256_value(value: object) -> bool:
    return bool(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value))


def _valid_handoff_shape(receipt: RootRomBuildHandoffReceipt, maximum_text: int) -> bool:
    return bool(
        type(receipt.schema_version) is int
        and _safe_text(receipt.handoff_id, maximum_text)
        and _safe_text(receipt.project_id, maximum_text)
        and isinstance(receipt.method, AscensionMethod)
        and _safe_text(receipt.created_at, maximum_text)
        and _sha256_value(receipt.source_original_sha256)
        and _sha256_value(receipt.integration_digest)
        and _safe_text(receipt.target_relative_path, maximum_text)
        and _safe_text(receipt.target_partition, maximum_text)
        and _safe_text(receipt.artifact_relative_path, maximum_text)
        and _sha256_value(receipt.artifact_sha256)
        and type(receipt.artifact_size_bytes) is int
        and receipt.artifact_size_bytes > 0
        and _safe_text(receipt.packaging_route, maximum_text)
        and (receipt.build_plan_tree_sha256 == "" or _sha256_value(receipt.build_plan_tree_sha256))
        and type(receipt.build_plan_bound) is bool
        and _safe_text(receipt.authority, maximum_text)
        and type(receipt.phone_changed) is bool
        and type(receipt.flash_authority) is bool
        and type(receipt.bootloader_relock_allowed) is bool
        and _sha256_value(receipt.handoff_digest)
    )
