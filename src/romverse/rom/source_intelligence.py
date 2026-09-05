from __future__ import annotations

import hashlib
import json
import re
import struct
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from romverse.infrastructure.local_store import atomic_write_json, read_json_object
from romverse.infrastructure.process import CommandRunner
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.models import ProjectError
from romverse.rom.ota_metadata import (
    AndroidOtaMetadata,
    OtaMetadataError,
    read_android_ota_metadata,
)
from romverse.rom.payloads import PayloadPartition, PayloadService
from romverse.rom.projects import RomProjectStore
from romverse.rom.source_blueprint import (
    FastbootSourceBlueprintService,
    ProgressCallback,
)
from romverse.rom.source_evidence_adapters import (
    BoundedFirmwareSourceEvidenceAdapter,
    FirmwareAdapter,
    FirmwareSourceAnalysis,
    FirmwareSourceEvidenceAdapterRegistry,
    FirmwareSourceSnapshot,
    match_fastboot_super,
    match_ota_payload,
    match_partition_bundle,
)
from romverse.rom.source_identity import FirmwareSourceIdentity, identify_firmware_source


class SourceBlueprint(Protocol):
    project_id: str
    source_kind: str
    manufacturer: str
    codename: str
    build_id: str
    android_version: str
    region: str
    source_archive_sha256: str
    partitions: tuple[object, ...]
    plan_digest: str
    candidate_sha256: str
    authority: str
    phone_changed: bool
    baseline_candidate_ready: bool
    avb_topology_verified: bool
    blueprint_digest: str


@dataclass(frozen=True, slots=True)
class OtaPayloadBlueprint:
    schema_version: int
    project_id: str
    created_at: str
    manufacturer: str
    codename: str
    build_id: str
    android_version: str
    region: str
    source_archive_sha256: str
    payload_path: str
    payload_size_bytes: int
    payload_modified_ns: int
    payload_sha256: str
    partitions: tuple[PayloadPartition, ...]
    plan_mode: str
    plan_digest: str
    authority: str
    phone_changed: bool
    blueprint_digest: str

    @property
    def source_kind(self) -> str:
        return FirmwareAdapter.OTA_PAYLOAD.value

    @property
    def candidate_sha256(self) -> str:
        return self.payload_sha256

    @property
    def baseline_candidate_ready(self) -> bool:
        return bool(self.partitions and self.plan_mode == "verified-ota-payload-baseline")

    @property
    def avb_topology_verified(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class ObservedPartitionImage:
    name: str
    path: str
    size_bytes: int
    modified_ns: int
    sha256: str
    image_format: str


@dataclass(frozen=True, slots=True)
class PartitionBundleBlueprint:
    """Hash-backed inventory of an extracted partition-image source.

    This records a byte-identical protected baseline. It does not describe a rebuild,
    AVB signing, recovery, or device-write policy.
    """

    schema_version: int
    project_id: str
    created_at: str
    manufacturer: str
    codename: str
    build_id: str
    android_version: str
    region: str
    source_archive_sha256: str
    images: tuple[ObservedPartitionImage, ...]
    plan_mode: str
    plan_digest: str
    authority: str
    phone_changed: bool
    blueprint_digest: str

    @property
    def source_kind(self) -> str:
        return FirmwareAdapter.PARTITION_BUNDLE.value

    @property
    def candidate_sha256(self) -> str:
        return self.source_archive_sha256

    @property
    def baseline_candidate_ready(self) -> bool:
        return bool(self.images and self.plan_mode == "verified-partition-bundle-baseline")

    @property
    def avb_topology_verified(self) -> bool:
        return False

    @property
    def partitions(self) -> tuple[ObservedPartitionImage, ...]:
        return self.images


class FirmwareSourceIntelligenceService:
    """Classify the extracted source and run the matching evidence adapter automatically."""

    OTA_NAME = "ota-source-blueprint.romverse"
    BUNDLE_NAME = "partition-bundle-blueprint.romverse"
    MAX_BLUEPRINT_BYTES = 512 * 1024
    MAX_PARTITION_IMAGES = 256
    MAX_PARTITION_BUNDLE_BYTES = 256 * 1024 * 1024 * 1024

    def __init__(
        self,
        store: RomProjectStore,
        tool_statuses: tuple[ToolStatus, ...],
        runner: CommandRunner,
    ) -> None:
        self.store = store
        self.tool_statuses = tool_statuses
        self.runner = runner
        self._fastboot_source = FastbootSourceBlueprintService(store, tool_statuses, runner)
        self._adapter_registry = FirmwareSourceEvidenceAdapterRegistry(
            (
                BoundedFirmwareSourceEvidenceAdapter(
                    FirmwareAdapter.OTA_PAYLOAD,
                    "project-local-build-evidence-only",
                    match_ota_payload,
                    self._prepare_ota_adapter,
                    self._load_ota,
                ),
                BoundedFirmwareSourceEvidenceAdapter(
                    FirmwareAdapter.FASTBOOT_SUPER,
                    "project-local-build-evidence-only",
                    match_fastboot_super,
                    self._prepare_fastboot_adapter,
                    self._fastboot_source.load,
                ),
                BoundedFirmwareSourceEvidenceAdapter(
                    FirmwareAdapter.PARTITION_BUNDLE,
                    "project-local-inventory-evidence-only",
                    match_partition_bundle,
                    self._prepare_partition_bundle_adapter,
                    self._load_partition_bundle,
                ),
            )
        )

    def analyze(self, project_id: str) -> FirmwareSourceAnalysis:
        return self._adapter_registry.analyze(self._snapshot(project_id))

    def _snapshot(self, project_id: str) -> FirmwareSourceSnapshot:
        tree = (self.store.working_root / project_id / "tree").resolve()
        if not tree.is_dir():
            raise ProjectError("Create the isolated firmware tree before source analysis")
        payloads = self._files(tree, "payload.bin")
        supers = self._files(tree, "super.img")
        images = tuple(
            sorted(
                path.relative_to(self.store.workspace).as_posix()
                for path in tree.rglob("*")
                if path.suffix.casefold() == ".img"
                and path.is_file()
                and not path.is_symlink()
                and path.resolve().is_relative_to(tree)
            )
        )
        return FirmwareSourceSnapshot(
            tuple(path.relative_to(self.store.workspace).as_posix() for path in payloads),
            tuple(path.relative_to(self.store.workspace).as_posix() for path in supers),
            images,
        )

    def prepare(
        self,
        project_id: str,
        progress: ProgressCallback | None = None,
    ) -> SourceBlueprint:
        return self._adapter_registry.prepare(project_id, self._snapshot(project_id), progress)

    def load(self, project_id: str) -> SourceBlueprint | None:
        return self._adapter_registry.load(project_id)

    def _prepare_fastboot_adapter(
        self,
        project_id: str,
        analysis: FirmwareSourceAnalysis,
        progress: ProgressCallback | None,
    ) -> SourceBlueprint:
        if analysis.adapter is not FirmwareAdapter.FASTBOOT_SUPER:
            raise ProjectError("Fastboot evidence adapter received a mismatched source analysis")
        return self._fastboot_source.prepare(project_id, progress)

    def _prepare_ota_adapter(
        self,
        project_id: str,
        analysis: FirmwareSourceAnalysis,
        progress: ProgressCallback | None,
    ) -> OtaPayloadBlueprint:
        if analysis.adapter is not FirmwareAdapter.OTA_PAYLOAD:
            raise ProjectError("OTA evidence adapter received a mismatched source analysis")
        return self._prepare_ota(project_id, progress)

    def _prepare_partition_bundle_adapter(
        self,
        project_id: str,
        analysis: FirmwareSourceAnalysis,
        progress: ProgressCallback | None,
    ) -> PartitionBundleBlueprint:
        if analysis.adapter is not FirmwareAdapter.PARTITION_BUNDLE:
            raise ProjectError("Partition evidence adapter received a mismatched source analysis")
        return self._prepare_partition_bundle(project_id, analysis, progress)

    def _prepare_ota(
        self,
        project_id: str,
        progress: ProgressCallback | None,
    ) -> OtaPayloadBlueprint:
        executable = self._payload_dumper()
        payloads = PayloadService(self.store, executable, self.runner)

        manifest = payloads.scan(project_id)
        project = self.store.get(project_id)
        assert project.original is not None
        identity = identify_firmware_source(project.original.original_name)
        try:
            ota_metadata = read_android_ota_metadata(self.store.original_path(project_id))
        except OtaMetadataError as exc:
            raise ProjectError(f"Android OTA metadata was rejected: {exc}") from exc
        manufacturer, codename, build_id, android_version, region = _ota_blueprint_identity(
            identity,
            ota_metadata,
        )
        payload_path = self.store.workspace / manifest.payload_path
        payload_stat = payload_path.stat()
        plan_payload = {
            "mode": "verified-ota-payload-baseline",
            "source_archive_sha256": project.original.sha256,
            "payload_sha256": manifest.payload_sha256,
            "partitions": [
                {"name": item.name, "estimated_bytes": item.estimated_bytes}
                for item in manifest.partitions
            ],
            "phone_changed": False,
        }
        plan_digest = _digest(plan_payload)
        payload = {
            "schema_version": 1,
            "project_id": project_id,
            "created_at": datetime.now(UTC).isoformat(),
            "manufacturer": manufacturer,
            "codename": codename,
            "build_id": build_id,
            "android_version": android_version,
            "region": region,
            "source_archive_sha256": project.original.sha256,
            "payload_path": manifest.payload_path,
            "payload_size_bytes": payload_stat.st_size,
            "payload_modified_ns": payload_stat.st_mtime_ns,
            "payload_sha256": manifest.payload_sha256,
            "partitions": [asdict(item) for item in manifest.partitions],
            "plan_mode": "verified-ota-payload-baseline",
            "plan_digest": plan_digest,
            "authority": "project-local-build-evidence-only",
            "phone_changed": False,
        }
        blueprint_digest = _digest(payload)
        values = dict(payload)
        values.pop("partitions")
        blueprint = OtaPayloadBlueprint(
            **values,
            partitions=manifest.partitions,
            blueprint_digest=blueprint_digest,
        )
        atomic_write_json(
            self.store.projects_root / project_id / self.OTA_NAME,
            {"format": "romverse.ota-source-blueprint", **asdict(blueprint)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_BLUEPRINT_BYTES,
        )
        if progress is not None:
            progress(100)
        return blueprint

    def _load_ota(self, project_id: str) -> OtaPayloadBlueprint | None:
        path = self.store.projects_root / project_id / self.OTA_NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BLUEPRINT_BYTES,
            )
            if (
                set(data) != {"format", *(field.name for field in fields(OtaPayloadBlueprint))}
                or data.pop("format") != "romverse.ota-source-blueprint"
            ):
                return None
            raw_partitions = data.pop("partitions")
            if (
                not isinstance(raw_partitions, list)
                or not 1 <= len(raw_partitions) <= PayloadService.MAX_PARTITIONS
            ):
                return None
            partitions = tuple(PayloadPartition(**item) for item in raw_partitions)
            blueprint = OtaPayloadBlueprint(**data, partitions=partitions)
            project = self.store.get(project_id)
            payload = self._workspace_path(blueprint.payload_path)
            stat = payload.stat()
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, ProjectError):
            return None
        values = asdict(blueprint)
        expected = str(values.pop("blueprint_digest"))
        if (
            blueprint.schema_version != 1
            or not _aware_timestamp(blueprint.created_at)
            or blueprint.project_id != project_id
            or project.original is None
            or blueprint.source_archive_sha256 != project.original.sha256
            or blueprint.authority != "project-local-build-evidence-only"
            or blueprint.phone_changed
            or not _sha256_value(blueprint.source_archive_sha256)
            or not _sha256_value(blueprint.payload_sha256)
            or not _sha256_value(blueprint.plan_digest)
            or stat.st_size != blueprint.payload_size_bytes
            or stat.st_mtime_ns != blueprint.payload_modified_ns
            or _digest(values) != expected
            or not blueprint.baseline_candidate_ready
            or any(not _valid_payload_partition(item) for item in partitions)
        ):
            return None
        return blueprint

    def _prepare_partition_bundle(
        self,
        project_id: str,
        analysis: FirmwareSourceAnalysis,
        progress: ProgressCallback | None,
    ) -> PartitionBundleBlueprint:
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("Import and verify a protected firmware source first")
        verification = self.store.verify_original(project_id)
        if not verification.valid:
            raise ProjectError(f"Protected source failed verification: {verification.status}")
        tree = (self.store.working_root / project_id / "tree").resolve()
        if not tree.is_dir():
            raise ProjectError("Create the isolated firmware tree first")
        if not 1 <= len(analysis.partition_images) <= self.MAX_PARTITION_IMAGES:
            raise ProjectError(
                f"Partition bundle must contain 1 to {self.MAX_PARTITION_IMAGES} regular images"
            )

        candidates: list[tuple[str, Path, int, int]] = []
        names: set[str] = set()
        total_bytes = 0
        for relative in analysis.partition_images:
            image = self._workspace_path(relative)
            if not image.is_relative_to(tree):
                raise ProjectError("Partition bundle image escaped the isolated firmware tree")
            name = image.stem.casefold().strip()
            if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,63}", name):
                raise ProjectError(f"Partition image has an unsupported name: {image.name}")
            if name in names:
                raise ProjectError(f"Partition bundle contains more than one image for role {name}")
            names.add(name)
            initial_stat = image.stat()
            size = initial_stat.st_size
            if size <= 0:
                raise ProjectError(f"Partition image is empty: {image.name}")
            total_bytes += size
            if total_bytes > self.MAX_PARTITION_BUNDLE_BYTES:
                raise ProjectError("Partition bundle exceeds the 256 GiB Guardian inspection limit")
            candidates.append((name, image, size, initial_stat.st_mtime_ns))

        completed_bytes = 0
        observed: list[ObservedPartitionImage] = []
        for name, image, initial_size, initial_modified_ns in candidates:
            digest = hashlib.sha256()
            image_bytes = 0
            with image.open("rb") as stream:
                while chunk := stream.read(4 * 1024 * 1024):
                    digest.update(chunk)
                    image_bytes += len(chunk)
                    completed_bytes += len(chunk)
                    if progress is not None and completed_bytes < total_bytes:
                        progress(max(0, min(99, int(completed_bytes * 100 / total_bytes))))
            stat = image.stat()
            if (
                image_bytes != initial_size
                or stat.st_size != initial_size
                or stat.st_mtime_ns != initial_modified_ns
            ):
                raise ProjectError(f"Partition image changed while it was hashed: {image.name}")
            observed.append(
                ObservedPartitionImage(
                    name=name,
                    path=image.relative_to(self.store.workspace).as_posix(),
                    size_bytes=stat.st_size,
                    modified_ns=stat.st_mtime_ns,
                    sha256=digest.hexdigest(),
                    image_format=_partition_image_format(image),
                )
            )

        images = tuple(sorted(observed, key=lambda item: (item.name, item.path)))
        identity = identify_firmware_source(project.original.original_name)
        plan_payload = {
            "mode": "verified-partition-bundle-baseline",
            "source_archive_sha256": project.original.sha256,
            "images": [asdict(item) for item in images],
            "phone_changed": False,
        }
        plan_digest = _digest(plan_payload)
        payload = {
            "schema_version": 1,
            "project_id": project_id,
            "created_at": datetime.now(UTC).isoformat(),
            "manufacturer": identity.manufacturer,
            "codename": identity.codename,
            "build_id": identity.build_id,
            "android_version": identity.android_version,
            "region": identity.region,
            "source_archive_sha256": project.original.sha256,
            "images": [asdict(item) for item in images],
            "plan_mode": "verified-partition-bundle-baseline",
            "plan_digest": plan_digest,
            "authority": "project-local-inventory-evidence-only",
            "phone_changed": False,
        }
        blueprint_digest = _digest(payload)
        values = dict(payload)
        values.pop("images")
        blueprint = PartitionBundleBlueprint(
            **values,
            images=images,
            blueprint_digest=blueprint_digest,
        )
        atomic_write_json(
            self.store.projects_root / project_id / self.BUNDLE_NAME,
            {"format": "romverse.partition-bundle-blueprint", **asdict(blueprint)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_BLUEPRINT_BYTES,
        )
        if progress is not None:
            progress(100)
        return blueprint

    def _load_partition_bundle(self, project_id: str) -> PartitionBundleBlueprint | None:
        path = self.store.projects_root / project_id / self.BUNDLE_NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BLUEPRINT_BYTES,
            )
            if (
                set(data) != {"format", *(field.name for field in fields(PartitionBundleBlueprint))}
                or data.pop("format") != "romverse.partition-bundle-blueprint"
            ):
                return None
            raw_images = data.pop("images")
            if (
                not isinstance(raw_images, list)
                or not 1 <= len(raw_images) <= self.MAX_PARTITION_IMAGES
            ):
                return None
            images = tuple(ObservedPartitionImage(**item) for item in raw_images)
            blueprint = PartitionBundleBlueprint(**data, images=images)
            project = self.store.get(project_id)
            tree = (self.store.working_root / project_id / "tree").resolve(strict=True)
            paths = tuple(self._workspace_path(item.path) for item in images)
            stats = tuple(item.stat() for item in paths)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, ProjectError):
            return None
        values = asdict(blueprint)
        expected = str(values.pop("blueprint_digest"))
        names = tuple(item.name for item in images)
        expected_plan = _digest(
            {
                "mode": "verified-partition-bundle-baseline",
                "source_archive_sha256": blueprint.source_archive_sha256,
                "images": [asdict(item) for item in images],
                "phone_changed": False,
            }
        )
        if (
            blueprint.schema_version != 1
            or not _aware_timestamp(blueprint.created_at)
            or blueprint.project_id != project_id
            or project.original is None
            or blueprint.source_archive_sha256 != project.original.sha256
            or blueprint.authority != "project-local-inventory-evidence-only"
            or blueprint.phone_changed
            or not _sha256_value(blueprint.source_archive_sha256)
            or not _sha256_value(blueprint.plan_digest)
            or blueprint.plan_digest != expected_plan
            or _digest(values) != expected
            or not blueprint.baseline_candidate_ready
            or len(set(names)) != len(names)
            or images != tuple(sorted(images, key=lambda item: (item.name, item.path)))
            or sum(item.size_bytes for item in images) > self.MAX_PARTITION_BUNDLE_BYTES
            or any(not _valid_partition_image(item) for item in images)
            or any(not item.is_relative_to(tree) for item in paths)
            or any(
                path.stem.casefold() != item.name for item, path in zip(images, paths, strict=True)
            )
            or any(
                _partition_image_format(image_path) != item.image_format
                for item, image_path in zip(images, paths, strict=True)
            )
            or any(
                stat.st_size != item.size_bytes or stat.st_mtime_ns != item.modified_ns
                for item, stat in zip(images, stats, strict=True)
            )
        ):
            return None
        return blueprint

    def _payload_dumper(self) -> Path:
        for item in self.tool_statuses:
            if item.name == "Payload Dumper" and item.available and item.path:
                path = Path(item.path).resolve()
                if path.is_file():
                    return path
        raise ProjectError("Payload Dumper is required; ROMVERSE can install it in Forge Arsenal")

    def _workspace_path(self, relative: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_./ -]{1,4096}", relative) or ".." in Path(relative).parts:
            raise ProjectError("Source blueprint contains an unsafe path")
        path = (self.store.workspace / relative).resolve(strict=True)
        if not path.is_relative_to(self.store.workspace.resolve()) or not path.is_file():
            raise ProjectError("Source blueprint path escaped the workspace")
        return path

    @staticmethod
    def _files(tree: Path, name: str) -> tuple[Path, ...]:
        return tuple(
            sorted(
                path.resolve()
                for path in tree.rglob("*")
                if path.name.casefold() == name.casefold()
                and path.is_file()
                and not path.is_symlink()
                and path.resolve().is_relative_to(tree)
            )
        )


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _ota_blueprint_identity(
    filename_identity: FirmwareSourceIdentity,
    metadata: AndroidOtaMetadata | None,
) -> tuple[str, str, str, str, str]:
    """Reconcile filename evidence with exact standard OTA post-build fields."""

    if metadata is None:
        return (
            filename_identity.manufacturer,
            filename_identity.codename,
            filename_identity.build_id,
            filename_identity.android_version,
            filename_identity.region,
        )
    targets = tuple(dict.fromkeys(metadata.target_devices))
    post_devices = tuple(
        dict.fromkeys(fingerprint.device.casefold() for fingerprint in metadata.post_fingerprints)
    )
    filename_codename = filename_identity.codename.casefold().strip()
    exact_targets = post_devices or targets
    if filename_codename and exact_targets and filename_codename not in exact_targets:
        raise ProjectError(
            "Firmware filename target and Android OTA package target disagree; source preparation stopped"
        )

    brands = _single_post_fingerprint_field(metadata, "brand", "brand")
    release = _single_post_fingerprint_field(metadata, "release", "Android release")
    post_build_id = _single_post_fingerprint_field(metadata, "build_id", "build ID")
    if (
        filename_identity.android_version
        and release
        and _android_release_key(filename_identity.android_version) != _android_release_key(release)
    ):
        raise ProjectError(
            "Firmware filename Android version and Android OTA post-build release disagree; source preparation stopped"
        )
    codename = filename_identity.codename or (
        post_devices[0] if len(post_devices) == 1 else targets[0] if len(targets) == 1 else ""
    )
    return (
        filename_identity.manufacturer or brands,
        codename,
        filename_identity.build_id or post_build_id or metadata.post_build_incremental,
        filename_identity.android_version or release,
        filename_identity.region,
    )


def _single_post_fingerprint_field(
    metadata: AndroidOtaMetadata,
    attribute: str,
    label: str,
) -> str:
    values = tuple(
        dict.fromkeys(
            str(getattr(fingerprint, attribute)).strip()
            for fingerprint in metadata.post_fingerprints
            if str(getattr(fingerprint, attribute)).strip()
        )
    )
    if len(values) > 1:
        raise ProjectError(f"Android OTA post-build {label} is ambiguous")
    return values[0] if values else ""


def _android_release_key(value: str) -> tuple[int, ...] | tuple[str]:
    normalized = str(value).strip()
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", normalized):
        numbers = [int(part) for part in normalized.split(".")]
        while len(numbers) > 1 and numbers[-1] == 0:
            numbers.pop()
        return tuple(numbers)
    return (normalized.casefold(),)


def _valid_payload_partition(item: PayloadPartition) -> bool:
    return bool(
        re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,63}", item.name)
        and type(item.estimated_bytes) is int
        and 0 <= item.estimated_bytes <= PayloadService.MAX_PARTITION_BYTES
        and isinstance(item.category, str)
        and 0 < len(item.category) <= 80
        and type(item.recommended) is bool
        and type(item.critical) is bool
        and isinstance(item.extracted_path, str)
        and len(item.extracted_path) <= 4_096
        and type(item.actual_bytes) is int
        and 0 <= item.actual_bytes <= PayloadService.MAX_PARTITION_BYTES
        and (not item.sha256 or _sha256_value(item.sha256))
        and isinstance(item.image_format, str)
        and 0 < len(item.image_format) <= 40
    )


def _valid_partition_image(item: ObservedPartitionImage) -> bool:
    return bool(
        re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,63}", item.name)
        and isinstance(item.path, str)
        and 0 < len(item.path) <= 4_096
        and type(item.size_bytes) is int
        and 0 < item.size_bytes <= FirmwareSourceIntelligenceService.MAX_PARTITION_BUNDLE_BYTES
        and type(item.modified_ns) is int
        and item.modified_ns > 0
        and _sha256_value(item.sha256)
        and item.image_format
        in {
            "Android boot image",
            "Android vendor boot image",
            "Android sparse image",
            "AVB metadata image",
            "ext4 filesystem",
            "EROFS filesystem",
            "raw partition image",
        }
    )


def _partition_image_format(path: Path) -> str:
    with path.open("rb") as stream:
        header = stream.read(4096)
    if header.startswith(b"ANDROID!"):
        return "Android boot image"
    if header.startswith(b"VNDRBOOT"):
        return "Android vendor boot image"
    if header.startswith(b"AVB0"):
        return "AVB metadata image"
    if len(header) >= 4 and struct.unpack_from("<I", header)[0] == 0xED26FF3A:
        return "Android sparse image"
    if len(header) >= 1082 and header[1080:1082] == b"\x53\xef":
        return "ext4 filesystem"
    if len(header) >= 1028 and struct.unpack_from("<I", header, 1024)[0] == 0xE0F5E1E2:
        return "EROFS filesystem"
    return "raw partition image"


def _sha256_value(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _aware_timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 80:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed <= datetime.now(UTC) + timedelta(minutes=5)
