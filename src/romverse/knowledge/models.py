"""Typed, execution-inert records for the expandable offline knowledge archive."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class KnowledgeSourceTier(StrEnum):
    OFFICIAL_VENDOR = "official_vendor"
    OFFICIAL_PLATFORM = "official_platform"
    REPUTABLE_TECHNICAL = "reputable_technical"
    COMMUNITY = "community"
    ROMVERSE_VERIFIED = "romverse_verified"


class KnowledgeConfidence(StrEnum):
    VERIFIED = "verified"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNCONFIRMED = "unconfirmed"


class KnowledgeKind(StrEnum):
    DIAGNOSIS = "diagnosis"
    FIX = "fix"
    GUIDE = "guide"
    COMPATIBILITY = "compatibility"
    RECOVERY = "recovery"


class MatchConfidence(StrEnum):
    EXACT = "exact"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNCONFIRMED = "unconfirmed"


@dataclass(frozen=True, slots=True)
class KnowledgeSource:
    source_id: str
    label: str
    publisher: str
    url: str
    tier: KnowledgeSourceTier
    scope: str
    reviewed_on: str


@dataclass(frozen=True, slots=True)
class DeviceKnowledgeScope:
    manufacturers: tuple[str, ...] = ()
    brands: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    codenames: tuple[str, ...] = ()
    build_ids: tuple[str, ...] = ()
    android_versions: tuple[str, ...] = ()
    bootloader_states: tuple[str, ...] = ()
    partitions: tuple[str, ...] = ()
    scope_note: str = ""


@dataclass(frozen=True, slots=True)
class KnowledgeOperation:
    """A declared operation requirement, never a command or execution grant."""

    operation_id: str
    label: str
    kind: str
    changes_device: bool
    target_partitions: tuple[str, ...]
    verified_input_requirements: tuple[str, ...]
    rollback_route: str


@dataclass(frozen=True, slots=True)
class KnowledgeRecord:
    record_id: str
    revision: int
    title: str
    kind: KnowledgeKind
    summary: str
    symptoms: tuple[str, ...]
    error_codes: tuple[str, ...]
    finding_ids: tuple[str, ...]
    diagnostic_steps: tuple[str, ...]
    fix_steps: tuple[str, ...]
    prerequisites: tuple[str, ...]
    expected_outcomes: tuple[str, ...]
    compatibility: tuple[str, ...]
    known_incompatibility: tuple[str, ...]
    recovery_routes: tuple[str, ...]
    tags: tuple[str, ...]
    scope: DeviceKnowledgeScope
    source_ids: tuple[str, ...]
    confidence: KnowledgeConfidence
    corroboration_count: int
    operations: tuple[KnowledgeOperation, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeArchive:
    schema_version: int
    bundle_id: str
    updated_at: str
    sources: tuple[KnowledgeSource, ...]
    records: tuple[KnowledgeRecord, ...]
    bundle_digest: str


@dataclass(frozen=True, slots=True)
class KnowledgeImportResult:
    added: int
    updated: int
    unchanged: int
    record_count: int
    bundle_digest: str


@dataclass(frozen=True, slots=True)
class KnowledgeFailure:
    """Bounded failure evidence supplied by a boot, flash, or diagnostic producer."""

    phase: str
    message: str
    error_codes: tuple[str, ...] = ()
    finding_ids: tuple[str, ...] = ()
    partition: str = ""
    operation: str = ""
    verified_inputs: tuple[str, ...] = ()
    rollback_routes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class KnowledgeQuery:
    manufacturers: tuple[str, ...] = ()
    brands: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    codenames: tuple[str, ...] = ()
    build_ids: tuple[str, ...] = ()
    android_versions: tuple[str, ...] = ()
    bootloader_states: tuple[str, ...] = ()
    partitions: tuple[str, ...] = ()
    symptoms: tuple[str, ...] = ()
    error_codes: tuple[str, ...] = ()
    finding_ids: tuple[str, ...] = ()
    evidence_terms: tuple[str, ...] = ()
    verified_inputs: tuple[str, ...] = ()
    rollback_routes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class KnowledgeMatch:
    record: KnowledgeRecord
    score: int
    confidence: MatchConfidence
    matched_evidence: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    provenance: tuple[KnowledgeSource, ...]
    safety: str

    @property
    def explanation(self) -> str:
        matched = "; ".join(self.matched_evidence) or "broad local text only"
        missing = (
            f" Missing exact evidence: {', '.join(self.missing_evidence)}."
            if self.missing_evidence
            else ""
        )
        return f"{self.confidence.value.upper()} MATCH • {matched}.{missing} {self.safety}"


@dataclass(frozen=True, slots=True)
class KnowledgeLookupReport:
    trigger: str
    query_digest: str
    archive_digest: str
    matches: tuple[KnowledgeMatch, ...]
    execution_authority: str = "none"
    limitations: tuple[str, ...] = ()

    @property
    def plain_text(self) -> str:
        heading = (
            f"OFFLINE KNOWLEDGE LOOKUP • {self.trigger.upper()} • "
            f"{len(self.matches)} MATCH{'ES' if len(self.matches) != 1 else ''}\n"
            "EXECUTION AUTHORITY • NONE"
        )
        if not self.matches:
            body = (
                "\n\nNo compatible local record matched the supplied evidence. "
                "ROMVERSE did not broaden uncertainty into a repair instruction."
            )
        else:
            rows = []
            for index, match in enumerate(self.matches, 1):
                sources = ", ".join(
                    f"{source.label} [{source.tier.value}; reviewed {source.reviewed_on}] "
                    f"{source.url or 'local ROMVERSE evidence'}"
                    for source in match.provenance
                )
                playbook: list[str] = []
                if match.record.diagnostic_steps:
                    playbook.append(
                        "   Diagnose:\n"
                        + "\n".join(f"   • {step}" for step in match.record.diagnostic_steps)
                    )
                if match.record.fix_steps:
                    playbook.append(
                        "   Compatible guidance:\n"
                        + "\n".join(f"   • {step}" for step in match.record.fix_steps)
                    )
                if match.record.prerequisites:
                    playbook.append("   Prerequisites: " + "; ".join(match.record.prerequisites))
                if match.record.expected_outcomes:
                    playbook.append("   Expected: " + "; ".join(match.record.expected_outcomes))
                if match.record.known_incompatibility:
                    playbook.append(
                        "   Known incompatibility: " + "; ".join(match.record.known_incompatibility)
                    )
                rows.append(
                    f"{index}. {match.record.title}\n"
                    f"   {match.explanation}\n"
                    f"   Record confidence: {match.record.confidence.value} • "
                    f"corroborated outcome/report count: "
                    f"{match.record.corroboration_count}\n"
                    f"   Scope: {match.record.scope.scope_note}\n"
                    + ("\n".join(playbook) + "\n" if playbook else "")
                    + f"   Provenance: {sources}"
                )
            body = "\n\n" + "\n\n".join(rows)
        boundary = (
            "\n\nLIMITS\n" + "\n".join(f"• {item}" for item in self.limitations)
            if self.limitations
            else ""
        )
        return heading + body + boundary
