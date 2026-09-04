from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import uuid4

from romverse.device.identity import DeviceIdentityResolver
from romverse.device.models import AndroidDevice
from romverse.device.root_identity import review_root_identity
from romverse.device_packs.models import DevicePack
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.local_store import atomic_write_json, read_json_object
from romverse.infrastructure.process import SubprocessRunner
from romverse.infrastructure.provisioning import required_tools_for_source
from romverse.rom.inspection import (
    ContainerKind,
    FindingSeverity,
    RomInspectionReport,
    RomInspectionService,
)
from romverse.rom.models import ProjectError
from romverse.rom.ota_metadata import (
    AndroidOtaMetadata,
    OtaMetadataError,
    read_android_ota_metadata,
)
from romverse.rom.projects import RomProjectStore
from romverse.rom.source_identity import (
    FirmwareSourceIdentity,
    identify_firmware_source,
    xiaomi_build_region,
)
from romverse.rom.source_intelligence import (
    FirmwareSourceIntelligenceService,
    SourceBlueprint,
)
from romverse.rom.upgrade import (
    FirmwareRelationship,
    FirmwareUpgradeAssessment,
    assess_device_firmware_upgrade,
)


class EvidenceConfidence(StrEnum):
    VERIFIED = "verified"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNCONFIRMED = "unconfirmed"


class CapabilityState(StrEnum):
    SUPPORTED = "SUPPORTED"
    CAUTION = "CAUTION"
    UNSUPPORTED = "UNSUPPORTED"
    UNCONFIRMED = "UNCONFIRMED"


class FirmwareStructureKind(StrEnum):
    OTA_PAYLOAD = "ota_payload"
    FASTBOOT_SUPER = "fastboot_super"
    PARTITION_BUNDLE = "partition_bundle"
    UNCONFIRMED = "unconfirmed"


@dataclass(frozen=True, slots=True)
class DeviceDnaEvidence:
    evidence_id: str
    source_type: str
    source_ref: str
    detail: str
    confidence: EvidenceConfidence


@dataclass(frozen=True, slots=True)
class DeviceDnaFact:
    fact_id: str
    label: str
    value: str
    confidence: EvidenceConfidence
    evidence_ids: tuple[str, ...] = ()

    @property
    def confirmed(self) -> bool:
        return self.confidence is not EvidenceConfidence.UNCONFIRMED


@dataclass(frozen=True, slots=True)
class DeviceDnaPartition:
    name: str
    size_bytes: int | None
    filesystem: str
    group: str
    confidence: EvidenceConfidence
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CapabilityMapEntry:
    capability_id: str
    label: str
    state: CapabilityState
    detail: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DeviceDnaProfile:
    schema_version: int
    profile_id: str
    project_id: str
    created_at: str
    source_sha256: str
    facts: tuple[DeviceDnaFact, ...]
    partitions: tuple[DeviceDnaPartition, ...]
    capabilities: tuple[CapabilityMapEntry, ...]
    warnings: tuple[str, ...]
    evidence: tuple[DeviceDnaEvidence, ...]
    bootloader_relock_permitted: bool
    profile_digest: str

    def fact(self, fact_id: str) -> DeviceDnaFact | None:
        return next((item for item in self.facts if item.fact_id == fact_id), None)

    def capability(self, capability_id: str) -> CapabilityMapEntry | None:
        return next(
            (item for item in self.capabilities if item.capability_id == capability_id), None
        )


class DeviceDnaStore:
    NAME = "device-dna.romverse"
    FORMAT = "romverse.device-dna"
    MAX_BYTES = 1024 * 1024

    def __init__(self, store: RomProjectStore) -> None:
        self.store = store

    def save(self, profile: DeviceDnaProfile) -> DeviceDnaProfile:
        project = self.store.get(profile.project_id)
        if project.original is None or project.original.sha256 != profile.source_sha256:
            raise ProjectError("Device DNA does not match the protected project source")
        if profile.bootloader_relock_permitted:
            raise ProjectError("Device DNA can never authorize bootloader relocking")
        profile = _seal_profile(profile)
        if not _valid_profile(profile):
            raise ProjectError("Device DNA profile metadata is invalid")
        existing = self.load(profile.project_id)
        if existing is not None and _semantic_payload(existing) == _semantic_payload(profile):
            return existing
        path = self.store.projects_root / profile.project_id / self.NAME
        atomic_write_json(
            path,
            {"format": self.FORMAT, **asdict(profile)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_BYTES,
        )
        return profile

    def load(self, project_id: str) -> DeviceDnaProfile | None:
        try:
            project = self.store.get(project_id)
        except ProjectError:
            return None
        path = self.store.projects_root / project_id / self.NAME
        try:
            data = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if (
                set(data) != {"format", *(field.name for field in fields(DeviceDnaProfile))}
                or data.pop("format") != self.FORMAT
                or not _valid_raw_profile(data)
            ):
                return None
            profile = _profile_from_mapping(data)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, ProjectError):
            return None
        if (
            not _valid_profile(profile)
            or profile.project_id != project_id
            or project.original is None
            or profile.source_sha256 != project.original.sha256
            or profile.bootloader_relock_permitted
        ):
            return None
        return profile


class DeviceDnaService:
    """Compile one conservative project profile from existing ROMVERSE evidence."""

    def __init__(self, store: RomProjectStore, registry: DevicePackRegistry) -> None:
        self.store = store
        self.registry = registry
        self.profiles = DeviceDnaStore(store)

    def refresh(
        self,
        project_id: str,
        device: AndroidDevice | None = None,
        inspection: RomInspectionReport | None = None,
    ) -> DeviceDnaProfile:
        project = self.store.get(project_id)
        if project.original is None:
            raise ProjectError("Import a protected firmware source before creating Device DNA")
        source = identify_firmware_source(project.original.original_name)
        pack = next(
            (item for item in self.registry.packs if item.pack_id == project.device_pack_id), None
        )
        exact_pack = bool(
            pack is not None
            and pack.build_contract is not None
            and pack.build_contract.source.archive_sha256 == project.original.sha256
        )
        persisted_inspection = RomInspectionService(self.store).load_report(project_id)
        inspection = (
            persisted_inspection
            if persisted_inspection is not None and persisted_inspection.schema_version == 2
            else None
        )
        blueprint = _load_current_source_blueprint(
            self.store,
            project_id,
            project.original.sha256,
        )
        ota_metadata: AndroidOtaMetadata | None = None
        ota_error = ""
        try:
            ota_metadata = read_android_ota_metadata(self.store.original_path(project_id))
        except OtaMetadataError as exc:
            ota_error = str(exc)
        profile = self._compile(
            project_id,
            project.original.sha256,
            source,
            device,
            inspection,
            pack,
            exact_pack,
            blueprint,
            ota_metadata,
            ota_error,
        )
        return self.profiles.save(profile)

    def _compile(
        self,
        project_id: str,
        source_sha256: str,
        source: FirmwareSourceIdentity,
        device: AndroidDevice | None,
        inspection: RomInspectionReport | None,
        pack: DevicePack | None,
        exact_pack: bool,
        blueprint: SourceBlueprint | None,
        ota_metadata: AndroidOtaMetadata | None,
        ota_error: str,
    ) -> DeviceDnaProfile:
        upgrade = assess_device_firmware_upgrade(
            device=device,
            source=source,
            blueprint=blueprint,
            ota_metadata=ota_metadata,
            metadata_error=ota_error,
        )
        evidence = _evidence(
            self.store,
            self.registry,
            source_sha256,
            source,
            device,
            inspection,
            pack,
            exact_pack,
            blueprint,
            ota_metadata,
            ota_error,
        )
        facts = _facts(
            source,
            device,
            inspection,
            pack,
            exact_pack,
            blueprint,
            ota_metadata,
            upgrade,
        )
        partitions = _partitions(pack, exact_pack, blueprint)
        warnings = _warnings(
            source,
            device,
            inspection,
            pack,
            exact_pack,
            blueprint,
            ota_metadata,
            ota_error,
            upgrade,
        )
        capabilities = _capability_map(
            source,
            device,
            inspection,
            pack,
            exact_pack,
            blueprint,
            ota_metadata,
            warnings,
        )
        payload: dict[str, object] = {
            "schema_version": 2,
            "profile_id": uuid4().hex,
            "project_id": project_id,
            "created_at": datetime.now(UTC).isoformat(),
            "source_sha256": source_sha256,
            "facts": facts,
            "partitions": partitions,
            "capabilities": capabilities,
            "warnings": warnings,
            "evidence": evidence,
            "bootloader_relock_permitted": False,
        }
        return DeviceDnaProfile(**payload, profile_digest=_digest(payload))  # type: ignore[arg-type]


def _load_current_source_blueprint(
    store: RomProjectStore,
    project_id: str,
    source_sha256: str,
) -> SourceBlueprint | None:
    """Load only the same strict, project-local source evidence used by Forge readiness."""

    try:
        blueprint = FirmwareSourceIntelligenceService(store, (), SubprocessRunner()).load(
            project_id
        )
    except (OSError, TypeError, ValueError):
        return None
    if blueprint is None:
        return None
    kind = str(getattr(blueprint, "source_kind", "")).strip()
    authority = str(getattr(blueprint, "authority", "")).strip()
    digest = str(getattr(blueprint, "blueprint_digest", "")).strip()
    plan_digest = str(getattr(blueprint, "plan_digest", "")).strip()
    return (
        blueprint
        if (
            getattr(blueprint, "project_id", "") == project_id
            and getattr(blueprint, "source_archive_sha256", "") == source_sha256
            and getattr(blueprint, "baseline_candidate_ready", False) is True
            and getattr(blueprint, "phone_changed", True) is False
            and kind in {"ota-payload", "fastboot-super", "partition-bundle"}
            and authority
            in {
                "project-local-build-evidence-only",
                "project-local-inventory-evidence-only",
            }
            and bool(re.fullmatch(r"[0-9a-f]{64}", digest))
            and bool(re.fullmatch(r"[0-9a-f]{64}", plan_digest))
        )
        else None
    )


def _evidence(
    store: RomProjectStore,
    registry: DevicePackRegistry,
    source_sha256: str,
    source: FirmwareSourceIdentity,
    device: AndroidDevice | None,
    inspection: RomInspectionReport | None,
    pack: DevicePack | None,
    exact_pack: bool,
    blueprint: SourceBlueprint | None,
    ota_metadata: AndroidOtaMetadata | None,
    ota_error: str,
) -> tuple[DeviceDnaEvidence, ...]:
    results = [
        DeviceDnaEvidence(
            "source.manifest",
            "protected-original-manifest",
            source_sha256,
            "The immutable project manifest records this source SHA-256.",
            EvidenceConfidence.HIGH,
        ),
        DeviceDnaEvidence(
            "source.filename",
            "bounded-filename-detection",
            source.package_type,
            "; ".join(source.evidence),
            _source_confidence(source),
        ),
    ]
    if ota_metadata is not None:
        results.append(
            DeviceDnaEvidence(
                "source.ota_metadata",
                "android-ota-metadata",
                ota_metadata.metadata_digest,
                "Standard META-INF/com/android/metadata was read without extracting the "
                f"archive; targets={', '.join(ota_metadata.target_devices) or 'unreported'}; "
                f"OTA type={ota_metadata.ota_type or 'unreported'}.",
                EvidenceConfidence.VERIFIED,
            )
        )
    elif ota_error:
        results.append(
            DeviceDnaEvidence(
                "source.ota_metadata",
                "android-ota-metadata",
                "rejected",
                ota_error,
                EvidenceConfidence.UNCONFIRMED,
            )
        )
    if inspection is not None:
        results.append(
            DeviceDnaEvidence(
                "source.container",
                "file-signature-inspection",
                inspection.container.value,
                f"Bounded inspection completed={inspection.complete}; entries={inspection.entry_count}.",
                EvidenceConfidence.HIGH if inspection.complete else EvidenceConfidence.MEDIUM,
            )
        )
        structure = _firmware_structure(inspection)
        if structure is not FirmwareStructureKind.UNCONFIRMED:
            results.append(
                DeviceDnaEvidence(
                    "source.android_structure",
                    "bounded-android-structure-inspection",
                    structure.value,
                    _structure_detail(inspection),
                    _structure_confidence(inspection),
                )
            )
    if blueprint is not None:
        partitions = tuple(getattr(blueprint, "partitions", ()) or ())
        kind = str(getattr(blueprint, "source_kind", ""))
        results.append(
            DeviceDnaEvidence(
                "source.blueprint",
                f"{kind}-source-blueprint",
                str(getattr(blueprint, "blueprint_digest", "")),
                f"Current project-local {kind} blueprint verified {len(partitions)} partition "
                f"record(s) and plan {str(getattr(blueprint, 'plan_digest', ''))[:16]}…; "
                f"authority={getattr(blueprint, 'authority', '')}; phone changed=NO.",
                EvidenceConfidence.VERIFIED,
            )
        )
    if device is not None:
        receipt = DeviceIdentityResolver(store.workspace, registry).load(device)
        results.append(
            DeviceDnaEvidence(
                "device.live",
                "device-identity-receipt" if receipt is not None else "live-adb-properties",
                device.masked_serial(),
                (
                    f"Identity receipt {receipt.receipt_id}; authority={receipt.authority.value}."
                    if receipt is not None
                    else "Read-only Android properties reported by the connected device."
                ),
                EvidenceConfidence.VERIFIED if receipt is not None else EvidenceConfidence.HIGH,
            )
        )
    if pack is not None:
        results.append(
            DeviceDnaEvidence(
                "pack.association",
                "device-pack",
                pack.pack_id,
                (
                    "Exact protected-source build contract matched."
                    if exact_pack
                    else "Read-only Device Pack knowledge; no exact build authority is implied."
                ),
                EvidenceConfidence.VERIFIED if exact_pack else EvidenceConfidence.MEDIUM,
            )
        )
    return tuple(results)


def _facts(
    source: FirmwareSourceIdentity,
    device: AndroidDevice | None,
    inspection: RomInspectionReport | None,
    pack: DevicePack | None,
    exact_pack: bool,
    blueprint: SourceBlueprint | None,
    ota_metadata: AndroidOtaMetadata | None,
    upgrade: FirmwareUpgradeAssessment,
) -> tuple[DeviceDnaFact, ...]:
    live_confidence = (
        EvidenceConfidence.HIGH if device is not None else EvidenceConfidence.UNCONFIRMED
    )
    live_evidence = ("device.live",) if device is not None else ()
    source_confidence = _source_confidence(source)
    source_evidence = ("source.filename",)
    blueprint_evidence = ("source.blueprint",) if blueprint is not None else ()

    def project_source_fact(
        attribute: str, fallback: str
    ) -> tuple[str, EvidenceConfidence, tuple[str, ...]]:
        observed = str(getattr(blueprint, attribute, "")).strip()
        if observed:
            return observed, EvidenceConfidence.VERIFIED, blueprint_evidence
        return fallback, source_confidence, source_evidence

    source_manufacturer, manufacturer_confidence, manufacturer_evidence = project_source_fact(
        "manufacturer", source.manufacturer
    )
    source_codename, codename_confidence, codename_evidence = project_source_fact(
        "codename", source.codename
    )
    source_android, android_confidence, android_evidence = project_source_fact(
        "android_version", source.android_version
    )
    source_build, build_confidence, build_evidence = project_source_fact(
        "build_id", source.build_id
    )
    if ota_metadata is not None and ota_metadata.target_devices:
        source_codename = " | ".join(ota_metadata.target_devices)
        codename_confidence = EvidenceConfidence.VERIFIED
        codename_evidence = ("source.ota_metadata",)
    ota_build = _ota_candidate_build(ota_metadata)
    if ota_build and not source_build:
        source_build = ota_build
        build_confidence = EvidenceConfidence.VERIFIED
        build_evidence = ("source.ota_metadata",)
    build_region = xiaomi_build_region(source_build)
    if build_region:
        source_region, region_confidence, region_evidence = (
            build_region,
            build_confidence,
            build_evidence,
        )
    else:
        source_region, region_confidence, region_evidence = project_source_fact(
            "region", source.region
        )
    upgrade_evidence = tuple(dict.fromkeys((*live_evidence, *codename_evidence, *build_evidence)))
    structure = _effective_structure(inspection, blueprint)
    structure_confidence = _effective_structure_confidence(inspection, blueprint)
    structure_evidence = (
        ("source.blueprint",)
        if blueprint is not None
        else ("source.android_structure", "source.container")
        if _firmware_structure(inspection) is not FirmwareStructureKind.UNCONFIRMED
        else ()
    )
    resolved_tools = required_tools_for_source(
        pack.build_contract if exact_pack and pack is not None else None,
        _source_tool_signals(inspection, blueprint),
    )
    root_review = review_root_identity(
        device.root_detected if device else None,
        device.root_manager_candidate if device else "unknown",
        root_signal_source=device.root_signal_source if device else "",
        manager_evidence=device.root_manager_evidence if device else "",
    )
    return (
        _fact(
            "identity.marketing_name",
            "Device name",
            device.display_name if device else "",
            live_confidence,
            live_evidence,
        ),
        _fact(
            "identity.manufacturer",
            "Manufacturer",
            device.manufacturer if device and device.manufacturer else source_manufacturer,
            live_confidence if device and device.manufacturer else manufacturer_confidence,
            live_evidence if device and device.manufacturer else manufacturer_evidence,
        ),
        _fact(
            "identity.brand",
            "Retail brand",
            device.brand if device else "",
            live_confidence,
            live_evidence,
        ),
        _fact(
            "identity.model",
            "Model",
            device.model if device else "",
            live_confidence,
            live_evidence,
        ),
        _fact(
            "identity.codename",
            "Codename",
            device.codename if device and device.codename else source_codename,
            live_confidence if device and device.codename else codename_confidence,
            live_evidence if device and device.codename else codename_evidence,
        ),
        _fact(
            "identity.product",
            "Product",
            device.product if device else "",
            live_confidence,
            live_evidence,
        ),
        _fact(
            "identity.vendor_device",
            "Vendor device",
            device.vendor_device if device else "",
            live_confidence,
            live_evidence,
        ),
        _fact(
            "identity.hardware_sku",
            "Hardware SKU",
            device.hardware_sku if device else "",
            live_confidence,
            live_evidence,
        ),
        _fact(
            "soc.platform",
            "SoC / platform",
            device.soc_platform if device else "",
            live_confidence,
            live_evidence,
        ),
        _fact(
            "software.android_version",
            "Android version",
            source_android or (device.android_version if device else ""),
            android_confidence if source_android else live_confidence,
            android_evidence if source_android else live_evidence,
        ),
        _fact(
            "software.rom",
            "ROM",
            device.rom_display if device else "",
            live_confidence,
            live_evidence,
        ),
        _fact(
            "software.build",
            "Build",
            source_build or (device.build_id if device else ""),
            build_confidence if source_build else live_confidence,
            build_evidence if source_build else live_evidence,
        ),
        _fact(
            "software.live_incremental",
            "Live incremental build",
            device.build_incremental if device else "",
            live_confidence,
            live_evidence,
        ),
        _fact(
            "software.live_build_timestamp",
            "Live build timestamp",
            str(device.build_timestamp_utc) if device and device.build_timestamp_utc else "",
            live_confidence,
            live_evidence,
        ),
        _fact(
            "software.live_system_incremental",
            "Live system build",
            device.system_build_incremental if device else "",
            live_confidence,
            live_evidence,
        ),
        _fact(
            "firmware.ota_post_incremental",
            "OTA post-build incremental",
            ota_metadata.post_build_incremental if ota_metadata else "",
            EvidenceConfidence.VERIFIED
            if ota_metadata and ota_metadata.post_build_incremental
            else EvidenceConfidence.UNCONFIRMED,
            ("source.ota_metadata",) if ota_metadata else (),
        ),
        _fact(
            "firmware.ota_post_timestamp",
            "OTA post-build timestamp",
            str(ota_metadata.post_timestamp)
            if ota_metadata and ota_metadata.post_timestamp
            else "",
            EvidenceConfidence.VERIFIED
            if ota_metadata and ota_metadata.post_timestamp
            else EvidenceConfidence.UNCONFIRMED,
            ("source.ota_metadata",) if ota_metadata else (),
        ),
        _fact(
            "firmware.upgrade_relationship",
            "Firmware relationship",
            upgrade.summary,
            EvidenceConfidence.HIGH
            if upgrade.relationship is not FirmwareRelationship.UNCONFIRMED
            else EvidenceConfidence.UNCONFIRMED,
            upgrade_evidence,
        ),
        _fact(
            "software.region",
            "Region",
            source_region,
            region_confidence,
            region_evidence,
        ),
        _fact(
            "software.security_patch",
            "Security patch",
            device.security_patch if device else "",
            live_confidence,
            live_evidence,
        ),
        _fact(
            "firmware.package_format",
            "Firmware format",
            _package_format(source, inspection, blueprint),
            structure_confidence
            if structure is not FirmwareStructureKind.UNCONFIRMED
            else source_confidence,
            structure_evidence if structure_evidence else source_evidence,
        ),
        _fact(
            "firmware.adapter",
            "Automatic source adapter",
            _structure_label(structure),
            structure_confidence,
            structure_evidence,
        ),
        _fact(
            "firmware.tool_profile",
            "Resolved tool profile",
            ", ".join(resolved_tools)
            if structure is not FirmwareStructureKind.UNCONFIRMED or exact_pack
            else "",
            EvidenceConfidence.VERIFIED
            if exact_pack or blueprint is not None
            else structure_confidence,
            ("pack.association",)
            if exact_pack
            else ("source.blueprint",)
            if blueprint is not None
            else structure_evidence,
        ),
        _fact(
            "partition.discovered",
            "Discovered partitions",
            ", ".join(_blueprint_partition_names(blueprint))
            if blueprint is not None
            else ", ".join(inspection.partition_signals)
            if inspection
            else "",
            structure_confidence,
            structure_evidence,
        ),
        _fact(
            "partition.architecture",
            "Partition architecture",
            _partition_architecture(device, pack, exact_pack, blueprint),
            EvidenceConfidence.VERIFIED
            if exact_pack or blueprint is not None
            else live_confidence
            if device and device.dynamic_partitions is not None
            else EvidenceConfidence.UNCONFIRMED,
            ("pack.association",)
            if exact_pack
            else ("source.blueprint",)
            if blueprint is not None
            else live_evidence,
        ),
        _fact(
            "partition.ab_scheme",
            "A/B scheme",
            _ab_scheme(device, pack, exact_pack),
            EvidenceConfidence.VERIFIED
            if exact_pack
            else live_confidence
            if device and device.ab_update is not None
            else EvidenceConfidence.UNCONFIRMED,
            ("pack.association",) if exact_pack else live_evidence,
        ),
        _fact(
            "bootloader.state",
            "Bootloader",
            _tri_state(device.bootloader_locked if device else None, "locked", "unlocked"),
            live_confidence,
            live_evidence,
        ),
        _fact(
            "boot.active_slot",
            "Active slot",
            device.slot_suffix.removeprefix("_") if device else "",
            live_confidence,
            live_evidence,
        ),
        _fact(
            "root.state",
            "Root evidence",
            root_review.title,
            EvidenceConfidence.HIGH
            if device and device.root_signal_source == "adb-shell-uid-0"
            else EvidenceConfidence.MEDIUM
            if device and device.root_manager_candidate in {"magisk", "kernelsu_lkm", "conflict"}
            else EvidenceConfidence.UNCONFIRMED,
            live_evidence,
        ),
        _fact(
            "root.manager_candidate",
            "Root Manager candidate",
            root_review.manager_label,
            EvidenceConfidence.MEDIUM
            if device and device.root_manager_candidate in {"magisk", "kernelsu_lkm", "conflict"}
            else EvidenceConfidence.UNCONFIRMED,
            live_evidence,
        ),
        _fact(
            "security.encryption", "Encryption", _encryption(device), live_confidence, live_evidence
        ),
        _fact(
            "security.verified_boot",
            "Verified Boot",
            device.verified_boot if device else "",
            live_confidence,
            live_evidence,
        ),
        _fact(
            "capability.fastboot",
            "Fastboot capability",
            device.fastboot_capability if device else "",
            live_confidence,
            live_evidence,
        ),
        _fact(
            "capability.recovery",
            "Recovery capability",
            device.recovery_capability if device else "",
            live_confidence,
            live_evidence,
        ),
    )


def _partitions(
    pack: DevicePack | None,
    exact_pack: bool,
    blueprint: SourceBlueprint | None,
) -> tuple[DeviceDnaPartition, ...]:
    if exact_pack and pack is not None and pack.build_contract is not None:
        return tuple(
            DeviceDnaPartition(
                rule.name,
                rule.size_bytes,
                rule.filesystem,
                rule.group,
                EvidenceConfidence.VERIFIED,
                ("pack.association",),
            )
            for rule in pack.build_contract.partitions
        )
    if blueprint is None:
        return ()
    kind = str(getattr(blueprint, "source_kind", ""))
    confidence = (
        EvidenceConfidence.VERIFIED if kind == "fastboot-super" else EvidenceConfidence.HIGH
    )
    results: list[DeviceDnaPartition] = []
    for item in tuple(getattr(blueprint, "partitions", ()) or ()):
        name = str(getattr(item, "name", "")).strip()
        if not name:
            continue
        size = getattr(item, "size_bytes", None)
        if type(size) is not int:
            size = getattr(item, "estimated_bytes", None)
        results.append(
            DeviceDnaPartition(
                name,
                size if type(size) is int and size >= 0 else None,
                str(getattr(item, "image_format", "")).strip(),
                str(getattr(item, "group_name", "")).strip(),
                confidence,
                ("source.blueprint",),
            )
        )
    return tuple(results)


def _ota_candidate_build(metadata: AndroidOtaMetadata | None) -> str:
    if metadata is None:
        return ""
    return metadata.post_build_incremental or (
        metadata.post_builds[0] if metadata.post_builds else ""
    )


def _device_matches_candidate(
    device: AndroidDevice,
    candidate_codename: str,
    ota_metadata: AndroidOtaMetadata | None,
) -> bool:
    if ota_metadata is not None and ota_metadata.target_devices:
        live = {
            item.casefold().strip()
            for item in (device.codename, device.product, device.vendor_device)
            if item.strip()
        }
        targets = set(ota_metadata.target_devices)
    else:
        live = {device.codename.casefold().strip()} if device.codename.strip() else set()
        targets = {
            item.casefold().strip() for item in candidate_codename.split("|") if item.strip()
        }
    return bool(live and targets and not live.isdisjoint(targets))


def _warnings(
    source: FirmwareSourceIdentity,
    device: AndroidDevice | None,
    inspection: RomInspectionReport | None,
    pack: DevicePack | None,
    exact_pack: bool,
    blueprint: SourceBlueprint | None,
    ota_metadata: AndroidOtaMetadata | None,
    ota_error: str,
    upgrade: FirmwareUpgradeAssessment,
) -> tuple[str, ...]:
    warnings: list[str] = []
    blueprint_codename = str(getattr(blueprint, "codename", "")).strip()
    source_codename = (
        " | ".join(ota_metadata.target_devices)
        if ota_metadata is not None and ota_metadata.target_devices
        else source.codename or blueprint_codename
    )
    if ota_error:
        warnings.append(f"Android OTA metadata was rejected: {ota_error}.")
    if source.confidence != "high" and not (
        ota_metadata is not None and ota_metadata.target_devices
    ):
        warnings.append("Firmware identity is unconfirmed; no supported vendor signature matched.")
    if device is None:
        warnings.append("No single connected device supplied live identity or boot-state evidence.")
    elif (
        source_codename
        and device.codename
        and not _device_matches_candidate(device, source_codename, ota_metadata)
    ):
        warnings.append(
            f"Connected device codename {device.codename} does not match firmware codename {source_codename}."
        )
    elif exact_pack and pack is not None and not _device_matches_pack(device, pack):
        warnings.append(
            f"Connected device identity does not match exact source-bound Pack {pack.pack_id}."
        )
    if upgrade.relationship is FirmwareRelationship.UPGRADE:
        warnings.append(
            f"{upgrade.summary}. This is a version relationship only; trusted provenance, package "
            "signature, an exact update path, recovery evidence, consent, and installation "
            "authority remain separate requirements."
        )
    elif upgrade.relationship is FirmwareRelationship.DOWNGRADE:
        warnings.append(
            f"{upgrade.summary}. This is not an upgrade; an exact Device Pack and separate "
            "Guardian-reviewed downgrade or recovery contract are required."
        )
    elif upgrade.relationship is FirmwareRelationship.SAME:
        warnings.append(
            f"{upgrade.summary}. The imported firmware is not an upgrade; an exact Device Pack "
            "is required for any explicit reinstall or recovery route."
        )
    elif upgrade.relationship is FirmwareRelationship.INCOMPATIBLE:
        warnings.extend(upgrade.reasons)
    elif device and upgrade.candidate_build:
        warnings.append(
            "ROMVERSE could not prove that the imported firmware is a valid upgrade from the "
            "connected phone. Installation authority remains unavailable."
        )
    if inspection is None and blueprint is None:
        warnings.append("Firmware container inspection has not completed yet.")
    elif inspection is not None and any(
        item.severity is FindingSeverity.CRITICAL for item in inspection.findings
    ):
        warnings.append("Critical firmware structure findings block automated preparation.")
    elif (
        inspection is not None
        and blueprint is None
        and _firmware_structure(inspection) is FirmwareStructureKind.UNCONFIRMED
    ):
        warnings.append(
            "The container is readable, but no supported Android payload, super, or partition-image structure was found."
        )
    if not exact_pack:
        if blueprint is not None:
            warnings.append(
                "No exact source-bound Device Pack contract is active; the verified project-local "
                f"{getattr(blueprint, 'source_kind', 'source')} blueprint supports bounded local "
                "build preparation only. Flash authority remains unavailable."
            )
        else:
            warnings.append(
                "No exact source-bound Device Pack contract is active; build and flash authority remain unavailable."
            )
    return tuple(warnings)


def _capability_map(
    source: FirmwareSourceIdentity,
    device: AndroidDevice | None,
    inspection: RomInspectionReport | None,
    pack: DevicePack | None,
    exact_pack: bool,
    blueprint: SourceBlueprint | None,
    ota_metadata: AndroidOtaMetadata | None,
    warnings: tuple[str, ...],
) -> tuple[CapabilityMapEntry, ...]:
    blueprint_codename = str(getattr(blueprint, "codename", "")).strip()
    source_codename = (
        " | ".join(ota_metadata.target_devices)
        if ota_metadata is not None and ota_metadata.target_devices
        else source.codename or blueprint_codename
    )
    target_identity_evidence = (
        ("source.ota_metadata",)
        if ota_metadata is not None and ota_metadata.target_devices
        else ("source.blueprint",)
        if blueprint_codename
        else ("source.filename",)
    )
    source_mismatch = bool(
        device
        and source_codename
        and device.codename
        and not _device_matches_candidate(device, source_codename, ota_metadata)
    )
    pack_mismatch = bool(
        device and exact_pack and pack is not None and not _device_matches_pack(device, pack)
    )
    mismatch = source_mismatch or pack_mismatch
    critical = bool(
        inspection
        and any(item.severity is FindingSeverity.CRITICAL for item in inspection.findings)
    )
    structure = _effective_structure(inspection, blueprint)
    structure_confidence = _effective_structure_confidence(inspection, blueprint)
    blueprint_ready = blueprint is not None
    blueprint_geometry = bool(
        blueprint is not None and getattr(blueprint, "source_kind", "") == "fastboot-super"
    )
    identity_state = (
        CapabilityState.UNSUPPORTED
        if mismatch
        else CapabilityState.SUPPORTED
        if device and device.codename and device.model
        else CapabilityState.CAUTION
        if device or source_codename
        else CapabilityState.UNCONFIRMED
    )
    firmware_state = (
        CapabilityState.UNSUPPORTED
        if critical
        else CapabilityState.SUPPORTED
        if blueprint_ready
        or (ota_metadata is not None and ota_metadata.target_devices)
        or (
            structure is not FirmwareStructureKind.UNCONFIRMED
            and structure_confidence is EvidenceConfidence.HIGH
        )
        else CapabilityState.CAUTION
        if structure is not FirmwareStructureKind.UNCONFIRMED or source.confidence == "high"
        else CapabilityState.UNCONFIRMED
    )
    adapter_state = (
        CapabilityState.UNSUPPORTED
        if critical
        else CapabilityState.SUPPORTED
        if structure in {FirmwareStructureKind.OTA_PAYLOAD, FirmwareStructureKind.FASTBOOT_SUPER}
        and (blueprint_ready or structure_confidence is EvidenceConfidence.HIGH)
        else CapabilityState.CAUTION
        if structure is not FirmwareStructureKind.UNCONFIRMED
        else CapabilityState.UNCONFIRMED
    )
    resolved_tools = required_tools_for_source(
        pack.build_contract if exact_pack and pack is not None else None,
        _source_tool_signals(inspection, blueprint),
    )
    tool_resolution_state = (
        CapabilityState.UNSUPPORTED
        if critical
        else CapabilityState.SUPPORTED
        if exact_pack
        or (
            blueprint_ready
            and structure
            in {FirmwareStructureKind.OTA_PAYLOAD, FirmwareStructureKind.FASTBOOT_SUPER}
        )
        or (
            structure
            in {
                FirmwareStructureKind.OTA_PAYLOAD,
                FirmwareStructureKind.FASTBOOT_SUPER,
            }
            and structure_confidence is EvidenceConfidence.HIGH
        )
        else CapabilityState.CAUTION
        if structure is FirmwareStructureKind.PARTITION_BUNDLE
        else CapabilityState.UNCONFIRMED
    )
    partition_state = (
        CapabilityState.SUPPORTED
        if exact_pack or blueprint_geometry
        else CapabilityState.CAUTION
        if blueprint_ready or (inspection and inspection.partition_signals)
        else CapabilityState.UNCONFIRMED
    )
    build_state = (
        CapabilityState.UNSUPPORTED
        if critical
        else CapabilityState.SUPPORTED
        if exact_pack or blueprint_ready
        else CapabilityState.CAUTION
        if source.confidence == "high"
        else CapabilityState.UNCONFIRMED
    )
    flash_state = (
        CapabilityState.UNSUPPORTED
        if critical or not exact_pack or mismatch
        else CapabilityState.UNCONFIRMED
    )
    root_review = review_root_identity(
        device.root_detected if device else None,
        device.root_manager_candidate if device else "unknown",
        root_signal_source=device.root_signal_source if device else "",
        manager_evidence=device.root_manager_evidence if device else "",
    )
    return (
        CapabilityMapEntry(
            "device_identity",
            "Device identification",
            identity_state,
            "Live and firmware identity agree."
            if identity_state is CapabilityState.SUPPORTED and (source_codename or exact_pack)
            else "Live device identity is supported; the firmware target identity remains unconfirmed."
            if identity_state is CapabilityState.SUPPORTED and device
            else _first_warning(warnings),
            (("device.live",) + target_identity_evidence) if device else target_identity_evidence,
        ),
        CapabilityMapEntry(
            "firmware_detection",
            "Firmware detection",
            firmware_state,
            "Container and package evidence are available."
            if firmware_state is CapabilityState.SUPPORTED
            else "ROMVERSE needs complete, safe container evidence.",
            ("source.blueprint",)
            if blueprint_ready
            else ("source.android_structure", "source.container")
            if _firmware_structure(inspection) is not FirmwareStructureKind.UNCONFIRMED
            else ("source.filename", "source.container")
            if inspection
            else ("source.filename",),
        ),
        CapabilityMapEntry(
            "source_adapter",
            "Automatic source adapter",
            adapter_state,
            _adapter_capability_detail(structure, adapter_state),
            ("source.blueprint",)
            if blueprint_ready
            else ("source.android_structure", "source.container")
            if _firmware_structure(inspection) is not FirmwareStructureKind.UNCONFIRMED
            else (),
        ),
        CapabilityMapEntry(
            "tool_resolution",
            "Tool resolution",
            tool_resolution_state,
            (
                "Exact source contract selected: "
                if exact_pack
                else "Verified project-local source blueprint selected: "
                if blueprint_ready
                else "Structure-backed source profile selected: "
            )
            + ", ".join(resolved_tools)
            + ". Forge Arsenal must still verify availability on this computer."
            if tool_resolution_state is CapabilityState.SUPPORTED
            else "A bounded partition-inspection profile is available, but deterministic rebuild requirements remain unconfirmed."
            if tool_resolution_state is CapabilityState.CAUTION
            else "Critical structure evidence blocks tool resolution."
            if tool_resolution_state is CapabilityState.UNSUPPORTED
            else "ROMVERSE needs supported Android structure or an exact source contract before selecting tools.",
            ("pack.association",)
            if exact_pack
            else ("source.blueprint",)
            if blueprint_ready
            else ("source.android_structure", "source.container")
            if _firmware_structure(inspection) is not FirmwareStructureKind.UNCONFIRMED
            else (),
        ),
        CapabilityMapEntry(
            "partition_mapping",
            "Partition map",
            partition_state,
            "Exact source-bound partition geometry is available."
            if exact_pack
            else "The verified local fastboot blueprint contains exact logical-partition geometry."
            if blueprint_geometry
            else "The verified local source blueprint contains a bounded partition inventory; exact rebuild geometry remains limited."
            if blueprint_ready
            else "Partition names may be visible, but exact geometry is not confirmed.",
            ("pack.association",)
            if exact_pack
            else ("source.blueprint",)
            if blueprint_ready
            else ("source.android_structure", "source.container")
            if _firmware_structure(inspection) is not FirmwareStructureKind.UNCONFIRMED
            else (),
        ),
        CapabilityMapEntry(
            "rom_build",
            "ROM build preparation",
            build_state,
            "Exact source build contract is active."
            if exact_pack
            else "A verified project-local source blueprint supports bounded local baseline and build preparation; it grants no flash authority."
            if blueprint_ready
            else "A recognized package is not an exact build contract.",
            ("pack.association",)
            if exact_pack
            else ("source.blueprint",)
            if blueprint_ready
            else ("source.filename",),
        ),
        CapabilityMapEntry(
            "guardian_flash",
            "Guardian flash",
            flash_state,
            "Final flash authority requires separate device, backup, slot, AVB, recovery, and physical attestation checks.",
            ("pack.association",)
            if exact_pack
            else ("source.blueprint",)
            if blueprint_ready
            else (),
        ),
        CapabilityMapEntry(
            "root_state",
            "Root-state identification",
            CapabilityState.CAUTION
            if device
            and (
                device.root_detected is True
                or device.root_manager_candidate in {"magisk", "kernelsu_lkm", "conflict"}
            )
            else CapabilityState.UNCONFIRMED,
            root_review.summary,
            ("device.live",) if device else (),
        ),
        CapabilityMapEntry(
            "bootloader_relock",
            "Bootloader relocking",
            CapabilityState.UNSUPPORTED,
            "ROMVERSE never permits or recommends bootloader relocking.",
        ),
    )


def _valid_raw_profile(data: dict[str, object]) -> bool:
    return bool(
        type(data.get("schema_version")) is int
        and data.get("schema_version") in {1, 2}
        and all(
            isinstance(data.get(key), str)
            for key in (
                "profile_id",
                "project_id",
                "created_at",
                "source_sha256",
                "profile_digest",
            )
        )
        and _raw_object_list(
            data.get("facts"),
            {field.name for field in fields(DeviceDnaFact)},
            64,
        )
        and _raw_object_list(
            data.get("partitions"),
            {field.name for field in fields(DeviceDnaPartition)},
            256,
        )
        and _raw_object_list(
            data.get("capabilities"),
            {field.name for field in fields(CapabilityMapEntry)},
            32,
        )
        and _raw_object_list(
            data.get("evidence"),
            {field.name for field in fields(DeviceDnaEvidence)},
            64,
        )
        and isinstance(data.get("warnings"), list)
        and all(isinstance(item, str) for item in data["warnings"])  # type: ignore[index]
        and type(data.get("bootloader_relock_permitted")) is bool
        and all(_valid_raw_fact(item) for item in data["facts"])  # type: ignore[index]
        and all(_valid_raw_partition(item) for item in data["partitions"])  # type: ignore[index]
        and all(_valid_raw_capability(item) for item in data["capabilities"])  # type: ignore[index]
        and all(_valid_raw_evidence(item) for item in data["evidence"])  # type: ignore[index]
    )


def _raw_object_list(value: object, expected_fields: set[str], maximum: int) -> bool:
    return bool(
        isinstance(value, list)
        and len(value) <= maximum
        and all(isinstance(item, dict) and set(item) == expected_fields for item in value)
    )


def _valid_raw_fact(item: object) -> bool:
    return bool(
        isinstance(item, dict)
        and all(
            isinstance(item.get(key), str) for key in ("fact_id", "label", "value", "confidence")
        )
        and _raw_string_list(item.get("evidence_ids"), 16)
    )


def _valid_raw_partition(item: object) -> bool:
    return bool(
        isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and (item.get("size_bytes") is None or type(item.get("size_bytes")) is int)
        and all(isinstance(item.get(key), str) for key in ("filesystem", "group", "confidence"))
        and _raw_string_list(item.get("evidence_ids"), 16)
    )


def _valid_raw_capability(item: object) -> bool:
    return bool(
        isinstance(item, dict)
        and all(
            isinstance(item.get(key), str) for key in ("capability_id", "label", "state", "detail")
        )
        and _raw_string_list(item.get("evidence_ids"), 16)
    )


def _valid_raw_evidence(item: object) -> bool:
    return bool(
        isinstance(item, dict)
        and all(
            isinstance(item.get(key), str)
            for key in ("evidence_id", "source_type", "source_ref", "detail", "confidence")
        )
    )


def _raw_string_list(value: object, maximum: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) <= maximum
        and all(isinstance(item, str) for item in value)
    )


def _profile_from_mapping(data: dict[str, object]) -> DeviceDnaProfile:
    facts = tuple(_fact_from_mapping(item) for item in _mapping_list(data.pop("facts"), "facts"))
    partitions = tuple(
        _partition_from_mapping(item)
        for item in _mapping_list(data.pop("partitions"), "partitions")
    )
    capabilities = tuple(
        _capability_from_mapping(item)
        for item in _mapping_list(data.pop("capabilities"), "capabilities")
    )
    evidence = tuple(
        _evidence_from_mapping(item) for item in _mapping_list(data.pop("evidence"), "evidence")
    )
    warnings = tuple(data.pop("warnings"))  # type: ignore[arg-type]
    return DeviceDnaProfile(
        schema_version=data["schema_version"],  # type: ignore[arg-type]
        profile_id=data["profile_id"],  # type: ignore[arg-type]
        project_id=data["project_id"],  # type: ignore[arg-type]
        created_at=data["created_at"],  # type: ignore[arg-type]
        source_sha256=data["source_sha256"],  # type: ignore[arg-type]
        facts=facts,
        partitions=partitions,
        capabilities=capabilities,
        warnings=warnings,
        evidence=evidence,
        bootloader_relock_permitted=data["bootloader_relock_permitted"],  # type: ignore[arg-type]
        profile_digest=data["profile_digest"],  # type: ignore[arg-type]
    )


def _fact_from_mapping(item: dict[str, object]) -> DeviceDnaFact:
    return DeviceDnaFact(
        item["fact_id"],  # type: ignore[arg-type]
        item["label"],  # type: ignore[arg-type]
        item["value"],  # type: ignore[arg-type]
        EvidenceConfidence(item["confidence"]),  # type: ignore[arg-type]
        tuple(item["evidence_ids"]),  # type: ignore[arg-type]
    )


def _partition_from_mapping(item: dict[str, object]) -> DeviceDnaPartition:
    size = item.get("size_bytes")
    return DeviceDnaPartition(
        item["name"],  # type: ignore[arg-type]
        size,  # type: ignore[arg-type]
        item["filesystem"],  # type: ignore[arg-type]
        item["group"],  # type: ignore[arg-type]
        EvidenceConfidence(item["confidence"]),  # type: ignore[arg-type]
        tuple(item["evidence_ids"]),  # type: ignore[arg-type]
    )


def _capability_from_mapping(item: dict[str, object]) -> CapabilityMapEntry:
    return CapabilityMapEntry(
        item["capability_id"],  # type: ignore[arg-type]
        item["label"],  # type: ignore[arg-type]
        CapabilityState(item["state"]),  # type: ignore[arg-type]
        item["detail"],  # type: ignore[arg-type]
        tuple(item["evidence_ids"]),  # type: ignore[arg-type]
    )


def _evidence_from_mapping(item: dict[str, object]) -> DeviceDnaEvidence:
    return DeviceDnaEvidence(
        item["evidence_id"],  # type: ignore[arg-type]
        item["source_type"],  # type: ignore[arg-type]
        item["source_ref"],  # type: ignore[arg-type]
        item["detail"],  # type: ignore[arg-type]
        EvidenceConfidence(item["confidence"]),  # type: ignore[arg-type]
    )


def _mapping_list(value: object, label: str) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise TypeError(f"Device DNA {label} must be a list of objects")
    return tuple(value)  # type: ignore[return-value]


def _fact(
    fact_id: str,
    label: str,
    value: str,
    confidence: EvidenceConfidence,
    evidence_ids: tuple[str, ...],
) -> DeviceDnaFact:
    clean = str(value).strip()
    return DeviceDnaFact(
        fact_id,
        label,
        clean or "Unconfirmed",
        confidence if clean else EvidenceConfidence.UNCONFIRMED,
        evidence_ids if clean else (),
    )


def _source_confidence(source: FirmwareSourceIdentity) -> EvidenceConfidence:
    return (
        EvidenceConfidence.HIGH if source.confidence == "high" else EvidenceConfidence.UNCONFIRMED
    )


def _package_format(
    source: FirmwareSourceIdentity,
    inspection: RomInspectionReport | None,
    blueprint: SourceBlueprint | None,
) -> str:
    if inspection is None and blueprint is None:
        return source.package_type
    structure = _effective_structure(inspection, blueprint)
    outer = inspection.container.value.replace("_", " ") if inspection is not None else ""
    structure_label = _structure_label(structure)
    if source.confidence == "high" and structure_label:
        return f"{source.package_type}; {structure_label}" + (f" ({outer})" if outer else "")
    if structure_label:
        return structure_label + (f" ({outer})" if outer else "")
    return (
        f"{source.package_type} ({outer})"
        if source.confidence == "high" and outer
        else source.package_type
        if source.confidence == "high"
        else ""
    )


def _firmware_structure(inspection: RomInspectionReport | None) -> FirmwareStructureKind:
    if inspection is None:
        return FirmwareStructureKind.UNCONFIRMED
    signals = set(inspection.partition_signals)
    if "ota_payload" in signals or inspection.container is ContainerKind.ANDROID_PAYLOAD:
        return FirmwareStructureKind.OTA_PAYLOAD
    if "super" in signals:
        return FirmwareStructureKind.FASTBOOT_SUPER
    if signals:
        return FirmwareStructureKind.PARTITION_BUNDLE
    return FirmwareStructureKind.UNCONFIRMED


def _structure_confidence(inspection: RomInspectionReport | None) -> EvidenceConfidence:
    structure = _firmware_structure(inspection)
    if inspection is None or structure is FirmwareStructureKind.UNCONFIRMED:
        return EvidenceConfidence.UNCONFIRMED
    if not inspection.complete:
        return EvidenceConfidence.MEDIUM
    if inspection.container is ContainerKind.RAW:
        return EvidenceConfidence.MEDIUM
    return EvidenceConfidence.HIGH


def _blueprint_structure(blueprint: SourceBlueprint | None) -> FirmwareStructureKind:
    return {
        "ota-payload": FirmwareStructureKind.OTA_PAYLOAD,
        "fastboot-super": FirmwareStructureKind.FASTBOOT_SUPER,
        "partition-bundle": FirmwareStructureKind.PARTITION_BUNDLE,
    }.get(str(getattr(blueprint, "source_kind", "")), FirmwareStructureKind.UNCONFIRMED)


def _effective_structure(
    inspection: RomInspectionReport | None,
    blueprint: SourceBlueprint | None,
) -> FirmwareStructureKind:
    observed = _blueprint_structure(blueprint)
    return (
        observed
        if observed is not FirmwareStructureKind.UNCONFIRMED
        else _firmware_structure(inspection)
    )


def _effective_structure_confidence(
    inspection: RomInspectionReport | None,
    blueprint: SourceBlueprint | None,
) -> EvidenceConfidence:
    return (
        EvidenceConfidence.VERIFIED
        if _blueprint_structure(blueprint) is not FirmwareStructureKind.UNCONFIRMED
        else _structure_confidence(inspection)
    )


def _source_tool_signals(
    inspection: RomInspectionReport | None,
    blueprint: SourceBlueprint | None,
) -> tuple[str, ...]:
    kind = _blueprint_structure(blueprint)
    if kind is FirmwareStructureKind.OTA_PAYLOAD:
        return ("ota_payload",)
    if kind is FirmwareStructureKind.FASTBOOT_SUPER:
        return ("super",)
    if kind is FirmwareStructureKind.PARTITION_BUNDLE:
        return ("partition_bundle",)
    return inspection.partition_signals if inspection is not None else ()


def _blueprint_partition_names(blueprint: SourceBlueprint | None) -> tuple[str, ...]:
    return tuple(
        name
        for item in tuple(getattr(blueprint, "partitions", ()) or ())[:256]
        if (name := str(getattr(item, "name", "")).strip())
    )


def _structure_label(structure: FirmwareStructureKind) -> str:
    return {
        FirmwareStructureKind.OTA_PAYLOAD: "Android OTA payload",
        FirmwareStructureKind.FASTBOOT_SUPER: "Android fastboot / super source",
        FirmwareStructureKind.PARTITION_BUNDLE: "Android partition image bundle",
        FirmwareStructureKind.UNCONFIRMED: "",
    }[structure]


def _structure_detail(inspection: RomInspectionReport) -> str:
    partitions = ", ".join(inspection.partition_signals) or "none"
    metadata = ", ".join(inspection.metadata_signals) or "none"
    return (
        f"Bounded archive signals: partitions={partitions}; metadata={metadata}; "
        f"container={inspection.container.value}; complete={inspection.complete}."
    )


def _adapter_capability_detail(
    structure: FirmwareStructureKind,
    state: CapabilityState,
) -> str:
    if state is CapabilityState.UNSUPPORTED:
        return "Critical structure evidence blocks automatic adapter selection."
    if structure is FirmwareStructureKind.OTA_PAYLOAD:
        return "Payload Atlas is selected for payload.bin inspection and extraction planning."
    if structure is FirmwareStructureKind.FASTBOOT_SUPER:
        return "Sparse-super and logical-partition tooling is selected for this source."
    if structure is FirmwareStructureKind.PARTITION_BUNDLE:
        return (
            "Partition images are recognized, but a deterministic automatic rebuild adapter is "
            "not yet available for this layout."
        )
    return "No supported Android source adapter can be selected from current evidence."


def _partition_architecture(
    device: AndroidDevice | None,
    pack: DevicePack | None,
    exact_pack: bool,
    blueprint: SourceBlueprint | None,
) -> str:
    if exact_pack and pack is not None and pack.build_contract is not None:
        contract = pack.build_contract
        return f"Dynamic partitions; {len(contract.groups)} group(s); metadata slots {contract.metadata_slots}"
    kind = _blueprint_structure(blueprint)
    partitions = _blueprint_partition_names(blueprint)
    if kind is FirmwareStructureKind.FASTBOOT_SUPER:
        groups = tuple(getattr(blueprint, "groups", ()) or ())
        metadata_slots = getattr(blueprint, "metadata_slots", None)
        slots = f"; metadata slots {metadata_slots}" if type(metadata_slots) is int else ""
        return f"Dynamic partitions; {len(groups)} observed group(s){slots}"
    if kind is FirmwareStructureKind.OTA_PAYLOAD:
        return f"OTA payload manifest; {len(partitions)} partition record(s)"
    if kind is FirmwareStructureKind.PARTITION_BUNDLE:
        return f"Hash-backed partition image bundle; {len(partitions)} image(s)"
    if device is not None and device.dynamic_partitions is True:
        return "Dynamic partitions reported by Android"
    if device is not None and device.dynamic_partitions is False:
        return "Non-dynamic partitions reported by Android"
    return ""


def _ab_scheme(device: AndroidDevice | None, pack: DevicePack | None, exact_pack: bool) -> str:
    if exact_pack and pack is not None and pack.build_contract is not None:
        return "Virtual A/B" if pack.build_contract.virtual_ab else "A/B state not declared virtual"
    if device is not None and device.virtual_ab is True:
        return "Virtual A/B"
    if device is not None and device.ab_update is True:
        return "A/B"
    if device is not None and device.ab_update is False:
        return "Non-A/B reported"
    return ""


def _encryption(device: AndroidDevice | None) -> str:
    if device is None:
        return ""
    return " / ".join(value for value in (device.encryption_state, device.encryption_type) if value)


def _tri_state(value: bool | None, when_true: str, when_false: str) -> str:
    return when_true if value is True else when_false if value is False else ""


def _device_matches_pack(device: AndroidDevice, pack: DevicePack) -> bool:
    def matches(value: str, patterns: tuple[str, ...]) -> bool:
        normalized = value.casefold().strip()
        return any(
            pattern == "*" or fnmatch.fnmatchcase(normalized, pattern) for pattern in patterns
        )

    if not (
        matches(device.manufacturer, pack.manufacturers)
        or matches(device.brand, pack.manufacturers)
    ):
        return False
    if pack.model_patterns and not matches(device.model, pack.model_patterns):
        return False
    return not pack.product_patterns or (
        matches(device.product, pack.product_patterns)
        or matches(device.codename, pack.product_patterns)
    )


def _first_warning(warnings: tuple[str, ...]) -> str:
    return warnings[0] if warnings else "More evidence is required."


def _seal_profile(profile: DeviceDnaProfile) -> DeviceDnaProfile:
    unsigned = replace(profile, schema_version=2, profile_digest="")
    payload = asdict(unsigned)
    payload.pop("profile_digest")
    return replace(unsigned, profile_digest=_digest(payload))


def _valid_profile(profile: DeviceDnaProfile) -> bool:
    if not isinstance(profile, DeviceDnaProfile):
        return False
    facts = tuple(profile.facts)
    partitions = tuple(profile.partitions)
    capabilities = tuple(profile.capabilities)
    evidence = tuple(profile.evidence)
    warnings = tuple(profile.warnings)
    evidence_ids = tuple(item.evidence_id for item in evidence)
    fact_ids = tuple(item.fact_id for item in facts)
    partition_names = tuple(item.name for item in partitions)
    capability_ids = tuple(item.capability_id for item in capabilities)
    relock = next(
        (item for item in capabilities if item.capability_id == "bootloader_relock"),
        None,
    )
    unsigned = asdict(profile)
    digest = unsigned.pop("profile_digest")
    return bool(
        type(profile.schema_version) is int
        and profile.schema_version in {1, 2}
        and _hex(profile.profile_id, 32)
        and bool(re.fullmatch(r"[a-z0-9-]{1,64}", profile.project_id))
        and _aware_timestamp(profile.created_at)
        and _hex(profile.source_sha256, 64)
        and isinstance(profile.facts, tuple)
        and 1 <= len(facts) <= 64
        and len(fact_ids) == len(set(fact_ids))
        and all(_valid_fact(item, set(evidence_ids)) for item in facts)
        and isinstance(profile.partitions, tuple)
        and len(partitions) <= 256
        and len(partition_names) == len(set(partition_names))
        and all(_valid_partition(item, set(evidence_ids)) for item in partitions)
        and isinstance(profile.capabilities, tuple)
        and 1 <= len(capabilities) <= 32
        and len(capability_ids) == len(set(capability_ids))
        and all(_valid_capability(item, set(evidence_ids)) for item in capabilities)
        and isinstance(profile.evidence, tuple)
        and 1 <= len(evidence) <= 64
        and len(evidence_ids) == len(set(evidence_ids))
        and all(_valid_evidence(item) for item in evidence)
        and isinstance(profile.warnings, tuple)
        and len(warnings) <= 64
        and all(_valid_text(item, 1024) for item in warnings)
        and profile.bootloader_relock_permitted is False
        and relock is not None
        and relock.state is CapabilityState.UNSUPPORTED
        and _hex(digest, 64)
        and digest == _digest(unsigned)
    )


def _valid_fact(fact: DeviceDnaFact, evidence_ids: set[str]) -> bool:
    return bool(
        isinstance(fact, DeviceDnaFact)
        and _identifier(fact.fact_id)
        and _valid_text(fact.label, 160)
        and _valid_text(fact.value, 1024)
        and isinstance(fact.confidence, EvidenceConfidence)
        and _valid_evidence_ids(fact.evidence_ids, evidence_ids)
    )


def _valid_partition(partition: DeviceDnaPartition, evidence_ids: set[str]) -> bool:
    return bool(
        isinstance(partition, DeviceDnaPartition)
        and _identifier(partition.name)
        and (
            partition.size_bytes is None
            or (type(partition.size_bytes) is int and 0 <= partition.size_bytes < 2**63)
        )
        and _valid_optional_text(partition.filesystem, 128)
        and _valid_optional_text(partition.group, 128)
        and isinstance(partition.confidence, EvidenceConfidence)
        and _valid_evidence_ids(partition.evidence_ids, evidence_ids)
    )


def _valid_capability(capability: CapabilityMapEntry, evidence_ids: set[str]) -> bool:
    return bool(
        isinstance(capability, CapabilityMapEntry)
        and _identifier(capability.capability_id)
        and _valid_text(capability.label, 160)
        and isinstance(capability.state, CapabilityState)
        and _valid_text(capability.detail, 2048)
        and _valid_evidence_ids(capability.evidence_ids, evidence_ids)
    )


def _valid_evidence(evidence: DeviceDnaEvidence) -> bool:
    return bool(
        isinstance(evidence, DeviceDnaEvidence)
        and _identifier(evidence.evidence_id)
        and _valid_text(evidence.source_type, 160)
        and _valid_text(evidence.source_ref, 512)
        and _valid_text(evidence.detail, 2048)
        and isinstance(evidence.confidence, EvidenceConfidence)
    )


def _valid_evidence_ids(values: tuple[str, ...], known: set[str]) -> bool:
    return bool(
        isinstance(values, tuple)
        and len(values) <= 16
        and len(values) == len(set(values))
        and all(_identifier(value) and value in known for value in values)
    )


def _identifier(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", value))


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value))


def _aware_timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 80:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed <= datetime.now(UTC) + timedelta(minutes=5)


def _valid_text(value: object, maximum: int) -> bool:
    return bool(
        isinstance(value, str)
        and 1 <= len(value) <= maximum
        and all(character.isprintable() or character == "\t" for character in value)
    )


def _valid_optional_text(value: object, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= maximum
        and all(character.isprintable() or character == "\t" for character in value)
    )


def _semantic_payload(profile: DeviceDnaProfile) -> dict[str, object]:
    payload = asdict(profile)
    for key in ("profile_id", "created_at", "profile_digest"):
        payload.pop(key, None)
    return payload


def _digest(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _json_default(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"Unsupported Device DNA value: {type(value).__name__}")
