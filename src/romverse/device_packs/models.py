from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class CapabilityStatus(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    PLANNED = "planned"


class AvbPolicyAuthority(StrEnum):
    REFERENCE_ONLY = "reference_only"
    FLASH_VALIDATED = "flash_validated"


class AvbPolicyMode(StrEnum):
    EXACT_SOURCE_IDENTITY = "exact_source_identity"
    SIGNED_CUSTOM_RECHAIN = "signed_custom_rechain"
    UNLOCKED_UNSIGNED_CHILD = "unlocked_unsigned_child"


class DeviceWriteTransport(StrEnum):
    FASTBOOT = "fastboot"
    FASTBOOTD = "fastbootd"


class PartitionVerificationMethod(StrEnum):
    """Exact readback method declared by a physically tested Device Pack."""

    FASTBOOT_FETCH_SHA256 = "fastboot_fetch_sha256"


@dataclass(frozen=True, slots=True)
class PackCapability:
    capability_id: str
    label: str
    status: CapabilityStatus
    scope: str
    detail: str


@dataclass(frozen=True, slots=True)
class KnowledgeSource:
    source_id: str
    label: str
    url: str
    authority: str
    scope: str
    verified_on: str

    def is_stale(self, as_of: date | None = None, maximum_age_days: int = 180) -> bool:
        checked = date.fromisoformat(self.verified_on)
        return ((as_of or date.today()) - checked).days > maximum_age_days


@dataclass(frozen=True, slots=True)
class FirmwareSourceContract:
    build_id: str
    archive_sha256: str
    payload_sha256: str


@dataclass(frozen=True, slots=True)
class DynamicPartitionGroup:
    name: str
    maximum_size_bytes: int


@dataclass(frozen=True, slots=True)
class ErofsRebuildParameters:
    compression: str
    compression_level: int
    legacy_compress: bool
    timestamp: int
    filesystem_uuid: str
    mount_point: str
    require_fakeroot_state: bool
    require_file_contexts: bool


@dataclass(frozen=True, slots=True)
class AvbHashtreeParameters:
    hash_algorithm: str
    salt: str
    generate_fec: bool


@dataclass(frozen=True, slots=True)
class PartitionBuildRule:
    name: str
    source_size_bytes: int
    size_bytes: int
    group: str
    filesystem: str
    mode: str
    source_sha256: str
    erofs: ErofsRebuildParameters | None = None
    avb_hashtree: AvbHashtreeParameters | None = None


@dataclass(frozen=True, slots=True)
class FileContextSource:
    partition: str
    candidate_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AvbExecutionPolicy:
    """Declarative AVB evidence; it grants no device-changing authority by itself."""

    mode: AvbPolicyMode
    authority: AvbPolicyAuthority
    evidence_build_id: str
    top_level_strategy: str
    chain_partition: str
    candidate_algorithm: str
    candidate_rollback_index: int
    candidate_rollback_index_location: int
    candidate_flags: int
    require_unlocked_bootloader: bool
    require_critical_unlocked: bool
    require_verity_mode: bool
    target_slot: str
    recovery_bootloader_slot: str
    attestation_sha256: str = ""
    signing_public_key_sha1: str = ""


@dataclass(frozen=True, slots=True)
class PartitionWriteRule:
    """One bounded partition-to-artifact declaration; never a shell command."""

    partition: str
    artifact: str
    transport: DeviceWriteTransport
    target_slot: str
    verify_after_write: bool


@dataclass(frozen=True, slots=True)
class PartitionReadbackRule:
    """One exact partition readback and expected full-byte digest."""

    partition: str
    transport: DeviceWriteTransport
    target_slot: str
    method: PartitionVerificationMethod
    expected_size_bytes: int
    expected_sha256: str


@dataclass(frozen=True, slots=True)
class PostBootPropertyRule:
    """One exact read-only Android property expected after a successful boot."""

    property_name: str
    expected_value: str


@dataclass(frozen=True, slots=True)
class DevicePostWriteVerificationContract:
    """Signed readback and first-boot proof; it is not execution authority."""

    contract_id: str
    version: int
    source_build_id: str
    attestation_sha256: str
    readbacks: tuple[PartitionReadbackRule, ...]
    post_boot_properties: tuple[PostBootPropertyRule, ...]
    require_adb_authorized: bool
    boot_timeout_seconds: int


@dataclass(frozen=True, slots=True)
class DeviceWriteContract:
    """Signed write intent that still requires Guardian artifact binding and consent."""

    contract_id: str
    version: int
    source_build_id: str
    attestation_sha256: str
    require_unlocked_bootloader: bool
    require_critical_unlocked: bool
    preserve_user_data_supported: bool
    wipe_user_data_supported: bool
    writes: tuple[PartitionWriteRule, ...]
    bootloader_relock_allowed: bool = False
    post_write_verification_contract: DevicePostWriteVerificationContract | None = None


@dataclass(frozen=True, slots=True)
class DeviceBuildContract:
    contract_id: str
    version: int
    source: FirmwareSourceContract
    super_size_bytes: int
    metadata_size_bytes: int
    metadata_slots: int
    virtual_ab: bool
    groups: tuple[DynamicPartitionGroup, ...]
    partitions: tuple[PartitionBuildRule, ...]
    vbmeta_descriptor_partitions: tuple[str, ...]
    vbmeta_system_sha256: str
    top_level_vbmeta_sha256: str
    allowed_outputs: tuple[str, ...]
    required_tools: tuple[str, ...] = ()
    file_context_sources: tuple[FileContextSource, ...] = ()
    avb_execution_policy: AvbExecutionPolicy | None = None
    partition_write_contract: DeviceWriteContract | None = None

    @property
    def editable_partitions(self) -> tuple[str, ...]:
        return tuple(rule.name for rule in self.partitions if rule.mode == "rebuild")


@dataclass(frozen=True, slots=True)
class DevicePack:
    pack_id: str
    version: str
    display_name: str
    priority: int
    manufacturers: tuple[str, ...]
    model_patterns: tuple[str, ...]
    product_patterns: tuple[str, ...]
    capabilities: tuple[PackCapability, ...]
    notes: tuple[str, ...]
    sha256: str
    build_contract: DeviceBuildContract | None = None
    build_compatible_pack_sha256: tuple[str, ...] = ()
    knowledge_sources: tuple[KnowledgeSource, ...] = ()


@dataclass(frozen=True, slots=True)
class PackResolution:
    pack: DevicePack | None
    matched: bool
    reason: str


@dataclass(frozen=True, slots=True)
class PackLoadIssue:
    filename: str
    reason: str
