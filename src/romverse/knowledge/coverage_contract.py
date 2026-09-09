"""Strict feature-to-data allowlist for retained ROMVERSE Knowledge fields."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from romverse.knowledge.online_evidence import EvidenceConsumer


class KnowledgeCoverageError(ValueError):
    """A retained field has no exact current-product value contract."""


class KnowledgeField(StrEnum):
    IDENTITY_MANUFACTURER = "identity.manufacturer"
    IDENTITY_MARKETING_NAME = "identity.marketing-name"
    IDENTITY_MODEL = "identity.model"
    IDENTITY_CODENAME = "identity.codename"
    HARDWARE_BOARD_COMPONENT = "hardware.board-component"
    FIRMWARE_BUILD_IDENTITY = "firmware.build-identity"
    BOOT_SECURITY_CAPABILITY = "boot.security-capability"
    PARTITION_LAYOUT = "partition.layout"
    TRANSPORT_ARTIFACT_TYPE = "transport.artifact-type"
    PREREQUISITE = "compatibility.prerequisite"
    INCOMPATIBILITY = "compatibility.incompatibility"
    RECOVERY_ROUTE = "recovery.route"
    HAZARD = "guardian.hazard"
    IRREVERSIBLE_CONDITION = "guardian.irreversible-condition"
    RECOVERY_AVAILABILITY = "recovery.availability"
    REQUIRED_EVIDENCE = "guardian.required-evidence"
    FAILURE_OUTCOME = "recovery.failure-outcome"
    EXPECTED_BOOT_OBSERVATION = "first-light.boot-observation"
    EXPECTED_SERVICE_OBSERVATION = "first-light.service-observation"
    EXPECTED_HARDWARE_OBSERVATION = "first-light.hardware-observation"
    PROVENANCE = "archives.provenance"
    FRESHNESS = "archives.freshness"
    CONFLICT = "archives.conflict"
    CORROBORATION = "archives.corroboration"
    OBSERVED_OUTCOME = "archives.observed-outcome"


@dataclass(frozen=True, slots=True)
class CoverageRule:
    field: KnowledgeField
    claim_key: str
    consumers: tuple[EvidenceConsumer, ...]
    decision_improved: str


_IDENTITY_CONSUMERS = (
    EvidenceConsumer.DEVICE_DNA,
    EvidenceConsumer.COMPATIBILITY_MATRIX,
    EvidenceConsumer.KNOWLEDGE_ARCHIVES,
)


def _rule(
    field: KnowledgeField,
    claim_key: str,
    consumers: tuple[EvidenceConsumer, ...],
    decision: str,
) -> CoverageRule:
    return CoverageRule(field, claim_key, consumers, decision)


_RULES = (
    _rule(
        KnowledgeField.IDENTITY_MANUFACTURER,
        "device.identity.manufacturer",
        _IDENTITY_CONSUMERS,
        "Select the exact OEM evidence family and reject an adjacent manufacturer's artifacts.",
    ),
    _rule(
        KnowledgeField.IDENTITY_MARKETING_NAME,
        "device.identity.marketing-name",
        _IDENTITY_CONSUMERS,
        "Present the exact public product identity and distinguish similarly coded retail devices.",
    ),
    _rule(
        KnowledgeField.IDENTITY_MODEL,
        "device.identity.model",
        _IDENTITY_CONSUMERS,
        "Match the exact retail model and reject firmware scoped to an adjacent model.",
    ),
    _rule(
        KnowledgeField.IDENTITY_CODENAME,
        "device.identity.codename",
        _IDENTITY_CONSUMERS,
        "Match exact device-target metadata and reject an adjacent device family.",
    ),
    _rule(
        KnowledgeField.HARDWARE_BOARD_COMPONENT,
        "device.hardware.board-component",
        (EvidenceConsumer.DEVICE_DNA, EvidenceConsumer.COMPATIBILITY_MATRIX),
        "Determine whether a hardware-specific artifact or expected subsystem applies.",
    ),
    _rule(
        KnowledgeField.FIRMWARE_BUILD_IDENTITY,
        "firmware.build-identity",
        (
            EvidenceConsumer.DEVICE_DNA,
            EvidenceConsumer.COMPATIBILITY_MATRIX,
            EvidenceConsumer.PATHFINDER,
        ),
        "Bind later compatibility and recovery evidence to the exact current or candidate build.",
    ),
    _rule(
        KnowledgeField.BOOT_SECURITY_CAPABILITY,
        "device.boot.security-capability",
        (EvidenceConsumer.DEVICE_DNA, EvidenceConsumer.PATHFINDER, EvidenceConsumer.GUARDIAN),
        "Determine whether a proposed boot artifact can be assessed without bypassing verified-boot safety.",
    ),
    _rule(
        KnowledgeField.PARTITION_LAYOUT,
        "firmware.partition.layout",
        (
            EvidenceConsumer.COMPATIBILITY_MATRIX,
            EvidenceConsumer.PATHFINDER,
            EvidenceConsumer.RECOVERY,
        ),
        "Choose the correct slot, dynamic-partition, and recovery analysis path.",
    ),
    _rule(
        KnowledgeField.TRANSPORT_ARTIFACT_TYPE,
        "compatibility.transport-artifact-type",
        (EvidenceConsumer.COMPATIBILITY_MATRIX, EvidenceConsumer.PATHFINDER),
        "Determine whether the available artifact and transport mode are structurally comparable.",
    ),
    _rule(
        KnowledgeField.PREREQUISITE,
        "compatibility.prerequisite",
        (
            EvidenceConsumer.COMPATIBILITY_MATRIX,
            EvidenceConsumer.PATHFINDER,
            EvidenceConsumer.GUARDIAN,
        ),
        "Identify evidence that must exist before a recoverable experiment can be reviewed.",
    ),
    _rule(
        KnowledgeField.INCOMPATIBILITY,
        "compatibility.incompatibility",
        (
            EvidenceConsumer.COMPATIBILITY_MATRIX,
            EvidenceConsumer.PATHFINDER,
            EvidenceConsumer.GUARDIAN,
        ),
        "Distinguish technically incompatible evidence from non-standard but viable combinations.",
    ),
    _rule(
        KnowledgeField.RECOVERY_ROUTE,
        "recovery.route",
        (EvidenceConsumer.PATHFINDER, EvidenceConsumer.GUARDIAN, EvidenceConsumer.RECOVERY),
        "Determine whether a credible recovery path exists before high-consequence review.",
    ),
    _rule(
        KnowledgeField.HAZARD,
        "guardian.hazard",
        (EvidenceConsumer.GUARDIAN, EvidenceConsumer.RECOVERY),
        "Identify a concrete damage or data-loss hazard that changes the approval decision.",
    ),
    _rule(
        KnowledgeField.IRREVERSIBLE_CONDITION,
        "guardian.irreversible-condition",
        (EvidenceConsumer.GUARDIAN, EvidenceConsumer.RECOVERY),
        "Hard-stop an action when credible evidence shows irreversible harm.",
    ),
    _rule(
        KnowledgeField.RECOVERY_AVAILABILITY,
        "recovery.availability",
        (EvidenceConsumer.GUARDIAN, EvidenceConsumer.RECOVERY),
        "Decide whether a high-consequence failure has an evidence-backed recovery route.",
    ),
    _rule(
        KnowledgeField.REQUIRED_EVIDENCE,
        "guardian.required-evidence",
        (EvidenceConsumer.GUARDIAN, EvidenceConsumer.RECOVERY),
        "Name the exact missing evidence that prevents safe consequential review.",
    ),
    _rule(
        KnowledgeField.FAILURE_OUTCOME,
        "recovery.failure-outcome",
        (EvidenceConsumer.GUARDIAN, EvidenceConsumer.RECOVERY),
        "Set truthful failure and data-wipe expectations and avoid blind retry.",
    ),
    _rule(
        KnowledgeField.EXPECTED_BOOT_OBSERVATION,
        "first-light.expected-boot",
        (EvidenceConsumer.FIRST_LIGHT,),
        "Distinguish expected boot progress from a recoverable or unknown failure.",
    ),
    _rule(
        KnowledgeField.EXPECTED_SERVICE_OBSERVATION,
        "first-light.expected-service",
        (EvidenceConsumer.FIRST_LIGHT,),
        "Evaluate whether required platform services reached their expected read-only state.",
    ),
    _rule(
        KnowledgeField.EXPECTED_HARDWARE_OBSERVATION,
        "first-light.expected-hardware",
        (EvidenceConsumer.FIRST_LIGHT,),
        "Evaluate named hardware subsystems without treating generic boot as full success.",
    ),
    _rule(
        KnowledgeField.PROVENANCE,
        "evidence.provenance",
        (EvidenceConsumer.NEXUS, EvidenceConsumer.KNOWLEDGE_ARCHIVES),
        "Choose evidence with exact source and revision binding over unattributed repetition.",
    ),
    _rule(
        KnowledgeField.FRESHNESS,
        "evidence.freshness",
        (EvidenceConsumer.NEXUS, EvidenceConsumer.KNOWLEDGE_ARCHIVES),
        "Require revalidation when evidence age weakens a current decision.",
    ),
    _rule(
        KnowledgeField.CONFLICT,
        "evidence.conflict",
        (EvidenceConsumer.NEXUS, EvidenceConsumer.KNOWLEDGE_ARCHIVES),
        "Preserve disagreement and route it to focused investigation instead of promotion.",
    ),
    _rule(
        KnowledgeField.CORROBORATION,
        "evidence.corroboration",
        (EvidenceConsumer.NEXUS, EvidenceConsumer.KNOWLEDGE_ARCHIVES),
        "Distinguish genuinely independent support from duplicated source claims.",
    ),
    _rule(
        KnowledgeField.OBSERVED_OUTCOME,
        "evidence.observed-outcome",
        (EvidenceConsumer.NEXUS, EvidenceConsumer.KNOWLEDGE_ARCHIVES),
        "Strengthen or retire an exact scoped claim using a privacy-safe observed result.",
    ),
)

_BY_FIELD = {rule.field: rule for rule in _RULES}


def coverage_rules() -> tuple[CoverageRule, ...]:
    return _RULES


def coverage_rule(field: KnowledgeField | str) -> CoverageRule:
    try:
        normalized = KnowledgeField(field)
    except (TypeError, ValueError) as exc:
        raise KnowledgeCoverageError("Knowledge field is outside current-product coverage") from exc
    return _BY_FIELD[normalized]


def require_claim_coverage(
    field: KnowledgeField | str,
    claim_key: str,
    consumers: tuple[EvidenceConsumer, ...],
) -> CoverageRule:
    rule = coverage_rule(field)
    if claim_key != rule.claim_key:
        raise KnowledgeCoverageError("Claim key does not match its approved Knowledge field")
    if consumers != rule.consumers:
        raise KnowledgeCoverageError("Claim consumers do not match the approved coverage contract")
    if not rule.decision_improved.strip():
        raise KnowledgeCoverageError("Knowledge field has no concrete product decision")
    return rule
