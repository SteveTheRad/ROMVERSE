"""Deterministic offline matching for Device DNA and typed failure evidence."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

from romverse.device.dna import DeviceDnaProfile, EvidenceConfidence
from romverse.device.models import AndroidDevice
from romverse.diagnostics.models import DiagnosticReport
from romverse.knowledge.models import (
    KnowledgeArchive,
    KnowledgeConfidence,
    KnowledgeConflict,
    KnowledgeEvidenceLabel,
    KnowledgeEvidenceStatus,
    KnowledgeFailure,
    KnowledgeLookupReport,
    KnowledgeMatch,
    KnowledgeOperation,
    KnowledgeQuery,
    KnowledgeRecord,
    KnowledgeRiskClass,
    KnowledgeSource,
    KnowledgeSourceTier,
    MatchConfidence,
)
from romverse.knowledge.store import KnowledgeArchiveStore

_CONFIDENCE_VALUE = {
    MatchConfidence.UNCONFIRMED: 0,
    MatchConfidence.LOW: 1,
    MatchConfidence.MEDIUM: 2,
    MatchConfidence.HIGH: 3,
    MatchConfidence.EXACT: 4,
}
_RECORD_CONFIDENCE_CAP = {
    KnowledgeConfidence.UNCONFIRMED: 0,
    KnowledgeConfidence.LOW: 1,
    KnowledgeConfidence.MEDIUM: 2,
    KnowledgeConfidence.HIGH: 3,
    KnowledgeConfidence.VERIFIED: 4,
}
_CONFIDENCE_FOR_VALUE = {value: key for key, value in _CONFIDENCE_VALUE.items()}
_EVIDENCE_STATUS_SCORE = {
    KnowledgeEvidenceStatus.OFFICIAL: 26,
    KnowledgeEvidenceStatus.MAINTAINER_VERIFIED: 20,
    KnowledgeEvidenceStatus.COMMUNITY_CONFIRMED: 14,
    KnowledgeEvidenceStatus.REPORTED_WORKING: 8,
    KnowledgeEvidenceStatus.DRAFT: 4,
    KnowledgeEvidenceStatus.DISPUTED: -20,
    KnowledgeEvidenceStatus.UNSAFE: -45,
    KnowledgeEvidenceStatus.RETIRED: -100,
}
_SOURCE_WEIGHT = {
    KnowledgeSourceTier.OFFICIAL_PLATFORM: 50,
    KnowledgeSourceTier.OFFICIAL_VENDOR: 50,
    KnowledgeSourceTier.ROMVERSE_VERIFIED: 35,
    KnowledgeSourceTier.REPUTABLE_TECHNICAL: 25,
    KnowledgeSourceTier.COMMUNITY: 10,
}
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "android",
        "device",
        "for",
        "from",
        "in",
        "is",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }
)


class OfflineKnowledgeService:
    """Load the local archive and explain ranked matches without executing anything."""

    def __init__(self, workspace: Path) -> None:
        self.store = KnowledgeArchiveStore(workspace)

    def scan_after_device_dna(
        self,
        profile: DeviceDnaProfile,
        *,
        limit: int = 8,
    ) -> KnowledgeLookupReport:
        return self.lookup(
            query_from_device_dna(profile),
            trigger="device-dna",
            limit=limit,
        )

    def scan_after_device_snapshot(
        self,
        device: AndroidDevice,
        *,
        limit: int = 8,
    ) -> KnowledgeLookupReport:
        """Rank local evidence immediately after a read-only transport scan.

        The query deliberately excludes the transport serial, fingerprints,
        storage, memory, battery, and every other user-specific reading.  It is
        suitable for automatic local matching, but never grants an operation.
        """

        return self.lookup(
            query_from_device_snapshot(device),
            trigger="device-connection",
            limit=limit,
        )

    def scan_after_diagnostic_report(
        self,
        device: AndroidDevice,
        report: DiagnosticReport,
        *,
        limit: int = 8,
    ) -> KnowledgeLookupReport:
        """Match current findings without exporting personal device telemetry."""

        return self.lookup(
            query_from_diagnostic_report(device, report),
            trigger="diagnostic-report",
            limit=limit,
        )

    def scan_after_failure(
        self,
        profile: DeviceDnaProfile | None,
        failure: KnowledgeFailure,
        *,
        limit: int = 8,
    ) -> KnowledgeLookupReport:
        base = query_from_device_dna(profile) if profile is not None else KnowledgeQuery()
        return self.lookup(
            query_with_failure(base, failure),
            trigger=f"{_bounded(failure.phase, 80) or 'failure'}-failure",
            limit=limit,
        )

    def lookup(
        self,
        query: KnowledgeQuery,
        *,
        trigger: str = "manual",
        limit: int = 8,
    ) -> KnowledgeLookupReport:
        archive = self.store.ensure_seeded()
        matches = rank_knowledge(archive, query, limit=limit)
        conflicts = detect_knowledge_conflicts(matches)
        limitations = (
            "Matches are local guidance and never execute a command, flash, wipe, unlock, or relock.",
            "Family-level or missing build evidence can support identification, not a destructive action.",
            "Community outcomes remain source-tiered correlations and require exact-device confirmation.",
        )
        return KnowledgeLookupReport(
            trigger=_bounded(trigger, 80) or "manual",
            query_digest=_query_digest(query),
            archive_digest=archive.bundle_digest,
            matches=matches,
            execution_authority="none",
            limitations=limitations,
            conflicts=conflicts,
            safest_answer=_safest_answer(matches, conflicts),
        )


def query_from_device_dna(profile: DeviceDnaProfile | None) -> KnowledgeQuery:
    if profile is None:
        return KnowledgeQuery()
    confirmed = {
        fact.fact_id: fact.value
        for fact in profile.facts
        if fact.value.strip()
        and fact.confidence is not EvidenceConfidence.UNCONFIRMED
        and fact.value.casefold() not in {"unknown", "unconfirmed"}
    }

    def values(*fact_ids: str) -> tuple[str, ...]:
        return _unique(confirmed.get(fact_id, "") for fact_id in fact_ids)

    partitions = [partition.name for partition in profile.partitions]
    discovered = confirmed.get("partition.discovered", "")
    if discovered:
        partitions.extend(part.strip() for part in discovered.split(","))
    evidence_terms = [
        f"{fact.fact_id} {fact.label} {fact.value}"
        for fact in profile.facts
        if fact.value.strip() and fact.confidence is not EvidenceConfidence.UNCONFIRMED
    ]
    evidence_terms.extend(
        f"{capability.capability_id} {capability.label} {capability.state.value} "
        f"{capability.detail}"
        for capability in profile.capabilities
    )
    evidence_terms.extend(profile.warnings)
    return KnowledgeQuery(
        manufacturers=values("identity.manufacturer"),
        brands=values("identity.brand", "firmware.ota_post_brand"),
        models=values("identity.model", "identity.marketing_name"),
        codenames=values(
            "identity.codename",
            "identity.product",
            "identity.vendor_device",
            "firmware.ota_post_product",
            "firmware.ota_post_device",
        ),
        build_ids=values(
            "software.build",
            "software.live_incremental",
            "software.live_system_incremental",
            "firmware.ota_post_build_id",
            "firmware.ota_post_incremental",
        ),
        android_versions=values("software.android_version", "firmware.ota_post_android"),
        bootloader_states=values("bootloader.state"),
        partitions=_unique(partitions),
        evidence_terms=_unique(evidence_terms, maximum=256),
    )


def query_from_device_snapshot(device: AndroidDevice) -> KnowledgeQuery:
    """Create a privacy-bounded archive query from current read-only evidence."""

    bootloader_state = (
        "locked"
        if device.bootloader_locked is True
        else "unlocked"
        if device.bootloader_locked is False
        else ""
    )
    capabilities = (
        f"transport state {device.state.value}",
        f"API level {device.api_level}" if device.api_level else "",
        f"security patch {device.security_patch}" if device.security_patch else "",
        f"ABI {device.abi}" if device.abi else "",
        f"verified boot {device.verified_boot}" if device.verified_boot else "",
        f"active slot {device.slot_suffix}" if device.slot_suffix else "",
        f"SoC platform {device.soc_platform}" if device.soc_platform else "",
        f"hardware {device.hardware}" if device.hardware else "",
        f"hardware SKU {device.hardware_sku}" if device.hardware_sku else "",
        f"A/B updates {'supported' if device.ab_update else 'not reported as supported'}"
        if device.ab_update is not None
        else "",
        f"Virtual A/B {'supported' if device.virtual_ab else 'not reported as supported'}"
        if device.virtual_ab is not None
        else "",
        f"dynamic partitions {'supported' if device.dynamic_partitions else 'not reported as supported'}"
        if device.dynamic_partitions is not None
        else "",
        device.fastboot_capability,
        device.recovery_capability,
    )
    return KnowledgeQuery(
        manufacturers=_unique((device.manufacturer,)),
        brands=_unique((device.brand,)),
        models=_unique((device.model, device.marketing_name)),
        codenames=_unique((device.codename, device.product, device.vendor_device)),
        build_ids=_unique(
            (
                device.rom_display,
                device.build_id,
                device.build_incremental,
                device.system_build_incremental,
            )
        ),
        android_versions=_unique((device.android_version,)),
        bootloader_states=_unique((bootloader_state,)),
        evidence_terms=_unique(capabilities, maximum=32),
    )


def query_from_diagnostic_report(
    device: AndroidDevice,
    report: DiagnosticReport,
) -> KnowledgeQuery:
    """Extend a privacy-bounded device query with typed diagnostic findings.

    Finding identifiers and generic diagnostic language improve local matching.
    Raw evidence values are intentionally excluded because they can contain
    personal telemetry or transport identifiers.
    """

    base = query_from_device_snapshot(device)
    findings = tuple(report.findings)
    return replace(
        base,
        symptoms=_unique(
            (
                text
                for finding in findings
                for text in (finding.title, finding.explanation, finding.guidance)
            ),
            maximum=128,
        ),
        finding_ids=_unique(
            (finding.finding_id for finding in findings),
            maximum=64,
        ),
        evidence_terms=_unique(
            (
                *base.evidence_terms,
                *(f"{finding.severity.value} {finding.title}" for finding in findings),
            ),
            maximum=256,
        ),
    )


def query_with_failure(query: KnowledgeQuery, failure: KnowledgeFailure) -> KnowledgeQuery:
    message = _bounded(failure.message, 4_000)
    phase = _bounded(failure.phase, 80)
    operation = _bounded(failure.operation, 160)
    partition = _bounded(failure.partition, 120)
    return replace(
        query,
        partitions=_unique((*query.partitions, partition)),
        symptoms=_unique((*query.symptoms, message)),
        error_codes=_unique((*query.error_codes, *failure.error_codes), maximum=64),
        finding_ids=_unique((*query.finding_ids, *failure.finding_ids), maximum=64),
        evidence_terms=_unique(
            (*query.evidence_terms, phase, operation, partition, message),
            maximum=256,
        ),
        verified_inputs=_unique((*query.verified_inputs, *failure.verified_inputs), maximum=64),
        rollback_routes=_unique((*query.rollback_routes, *failure.rollback_routes), maximum=64),
    )


def rank_knowledge(
    archive: KnowledgeArchive,
    query: KnowledgeQuery,
    *,
    limit: int = 8,
) -> tuple[KnowledgeMatch, ...]:
    bounded_limit = max(0, min(limit, 64))
    if not bounded_limit:
        return ()
    source_by_id = {source.source_id: source for source in archive.sources}
    results: list[KnowledgeMatch] = []
    for record in archive.records:
        if _scope_conflicts(record, query):
            continue
        provenance = tuple(source_by_id[source_id] for source_id in record.source_ids)
        scored = _score_record(record, query, provenance)
        if scored is None:
            continue
        base_score, matched, missing = scored
        evidence_score = _evidence_score(record, query, provenance)
        score = base_score + evidence_score
        confidence = _match_confidence(record, matched, missing)
        if record.evidence_status in {
            KnowledgeEvidenceStatus.DISPUTED,
            KnowledgeEvidenceStatus.UNSAFE,
            KnowledgeEvidenceStatus.RETIRED,
        }:
            confidence = _lowered_confidence(confidence)
        results.append(
            KnowledgeMatch(
                record=record,
                score=score,
                confidence=confidence,
                matched_evidence=matched,
                missing_evidence=missing,
                provenance=provenance,
                safety=_safety(record.operations, record, query),
                evidence_score=evidence_score,
                evidence_labels=evidence_labels(record, provenance),
            )
        )
    results.sort(
        key=lambda match: (
            -match.score,
            -_CONFIDENCE_VALUE[match.confidence],
            match.record.title.casefold(),
            match.record.record_id,
        )
    )
    selected = tuple(results[:bounded_limit])
    conflicts = detect_knowledge_conflicts(selected)
    disputed = {record_id for conflict in conflicts for record_id in conflict.record_ids}
    return tuple(
        replace(
            match,
            evidence_labels=_unique_labels(
                *match.evidence_labels,
                *((KnowledgeEvidenceLabel.DISPUTED,) if match.record.record_id in disputed else ()),
            ),
        )
        for match in selected
    )


def evidence_labels(
    record: KnowledgeRecord,
    provenance: tuple[KnowledgeSource, ...],
) -> tuple[KnowledgeEvidenceLabel, ...]:
    """Derive visible evidence-state labels without rewriting source records."""

    labels: list[KnowledgeEvidenceLabel] = []
    tiers = {source.tier for source in provenance}
    corpus = _normalize(
        " ".join(
            (
                record.title,
                record.summary,
                *record.tags,
                *record.known_incompatibility,
            )
        )
    )
    if tiers & {
        KnowledgeSourceTier.OFFICIAL_PLATFORM,
        KnowledgeSourceTier.OFFICIAL_VENDOR,
    }:
        labels.append(KnowledgeEvidenceLabel.OFFICIAL)
    if KnowledgeSourceTier.COMMUNITY in tiers:
        labels.append(KnowledgeEvidenceLabel.COMMUNITY_REPORTED)
    if (
        record.evidence_status
        not in {
            KnowledgeEvidenceStatus.DRAFT,
            KnowledgeEvidenceStatus.DISPUTED,
            KnowledgeEvidenceStatus.UNSAFE,
            KnowledgeEvidenceStatus.RETIRED,
        }
        and record.confidence in {KnowledgeConfidence.VERIFIED, KnowledgeConfidence.HIGH}
        and record.corroboration_count >= 1
    ):
        labels.append(KnowledgeEvidenceLabel.VERIFIED)
    if (
        record.evidence_status is KnowledgeEvidenceStatus.DRAFT
        or record.confidence
        in {
            KnowledgeConfidence.MEDIUM,
            KnowledgeConfidence.LOW,
            KnowledgeConfidence.UNCONFIRMED,
        }
        or any(term in corpus.split() for term in {"experimental", "unconfirmed", "hypothesis"})
    ):
        labels.append(KnowledgeEvidenceLabel.EXPERIMENTAL)
    if record.evidence_status in {
        KnowledgeEvidenceStatus.DISPUTED,
        KnowledgeEvidenceStatus.UNSAFE,
    } or any(term in corpus.split() for term in {"disputed", "controversial", "conflicting"}):
        labels.append(KnowledgeEvidenceLabel.DISPUTED)
    if record.evidence_status is KnowledgeEvidenceStatus.RETIRED or any(
        term in corpus.split() for term in {"outdated", "deprecated", "retired", "superseded"}
    ):
        labels.append(KnowledgeEvidenceLabel.OUTDATED)
    if not labels:
        labels.append(KnowledgeEvidenceLabel.EXPERIMENTAL)
    return _unique_labels(*labels)


def detect_knowledge_conflicts(
    matches: tuple[KnowledgeMatch, ...],
) -> tuple[KnowledgeConflict, ...]:
    """Flag only explicit scope-compatible contradictions; silence is not a conflict."""

    conflicts: list[KnowledgeConflict] = []
    for index, left in enumerate(matches):
        for right in matches[index + 1 :]:
            reason = _explicit_conflict_reason(left.record, right.record)
            if not reason:
                continue
            record_ids = tuple(sorted((left.record.record_id, right.record.record_id)))
            conflict_id = hashlib.sha256(
                json.dumps(record_ids, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            conflicts.append(
                KnowledgeConflict(
                    conflict_id,
                    record_ids,
                    reason,
                    "Do not combine either procedure. Prefer current exact-device official "
                    "evidence, preserve rollback material, and keep device-changing actions "
                    "locked until the contradiction is resolved.",
                )
            )
    return tuple(conflicts[:16])


def _explicit_conflict_reason(left: KnowledgeRecord, right: KnowledgeRecord) -> str:
    if _scope_conflicts(left, _query_for_scope(right.scope)) or _scope_conflicts(
        right, _query_for_scope(left.scope)
    ):
        return ""
    left_compatibility = {_normalize(item) for item in left.compatibility}
    right_compatibility = {_normalize(item) for item in right.compatibility}
    left_incompatible = {_normalize(item) for item in left.known_incompatibility}
    right_incompatible = {_normalize(item) for item in right.known_incompatibility}
    direct = (left_compatibility & right_incompatible) | (right_compatibility & left_incompatible)
    if direct:
        return f"{left.title} and {right.title} explicitly disagree about {sorted(direct)[0]}."
    for left_operation in left.operations:
        for right_operation in right.operations:
            overlap = set(_normalized(left_operation.target_partitions)) & set(
                _normalized(right_operation.target_partitions)
            )
            if overlap and (
                left_operation.kind != right_operation.kind
                or _normalize(left_operation.rollback_route)
                != _normalize(right_operation.rollback_route)
            ):
                return (
                    f"{left.title} and {right.title} declare incompatible operations for "
                    f"{', '.join(sorted(overlap))}."
                )
    return ""


def _query_for_scope(scope) -> KnowledgeQuery:
    return KnowledgeQuery(
        manufacturers=scope.manufacturers,
        brands=scope.brands,
        models=scope.models,
        codenames=scope.codenames,
        build_ids=scope.build_ids,
        android_versions=scope.android_versions,
        bootloader_states=scope.bootloader_states,
        partitions=scope.partitions,
    )


def _safest_answer(
    matches: tuple[KnowledgeMatch, ...],
    conflicts: tuple[KnowledgeConflict, ...],
) -> str:
    if conflicts:
        return (
            "Conflicting compatible guidance is present. Stop at evidence collection and "
            "resolve the named conflict with current exact-device official evidence before "
            "opening any device-changing route."
        )
    if not matches:
        return (
            "No compatible local answer is proven. Collect more Device DNA, firmware, "
            "partition, or error evidence instead of broadening the search into a guess."
        )
    lead = next(
        (
            match
            for match in matches
            if match.record.evidence_status
            not in {
                KnowledgeEvidenceStatus.DISPUTED,
                KnowledgeEvidenceStatus.UNSAFE,
                KnowledgeEvidenceStatus.RETIRED,
            }
        ),
        None,
    )
    if lead is None:
        return "The matching records are disputed, unsafe or retired. Use them as diagnostic history, not as a repair recommendation."
    return (
        f"Start with {lead.record.title} as {lead.confidence.value} guidance, retain its "
        "stated scope and prerequisites, and independently confirm any device-changing step."
    )


def _unique_labels(
    *labels: KnowledgeEvidenceLabel,
) -> tuple[KnowledgeEvidenceLabel, ...]:
    order = {
        KnowledgeEvidenceLabel.OFFICIAL: 0,
        KnowledgeEvidenceLabel.VERIFIED: 1,
        KnowledgeEvidenceLabel.COMMUNITY_REPORTED: 2,
        KnowledgeEvidenceLabel.EXPERIMENTAL: 3,
        KnowledgeEvidenceLabel.DISPUTED: 4,
        KnowledgeEvidenceLabel.OUTDATED: 5,
    }
    return tuple(sorted(set(labels), key=order.__getitem__))


def _lowered_confidence(confidence: MatchConfidence) -> MatchConfidence:
    if confidence is MatchConfidence.EXACT:
        return MatchConfidence.HIGH
    if confidence is MatchConfidence.HIGH:
        return MatchConfidence.MEDIUM
    if confidence is MatchConfidence.MEDIUM:
        return MatchConfidence.LOW
    return MatchConfidence.UNCONFIRMED


def _newest_source_reviewed_on(
    provenance: tuple[KnowledgeSource, ...],
) -> datetime | None:
    newest: datetime | None = None
    for source in provenance:
        try:
            reviewed = datetime.fromisoformat(source.reviewed_on).replace(tzinfo=UTC)
        except ValueError:
            continue
        if newest is None or reviewed > newest:
            newest = reviewed
    return newest


def _evidence_score(
    record: KnowledgeRecord,
    query: KnowledgeQuery,
    provenance: tuple[KnowledgeSource, ...],
) -> int:
    source_quality = 0
    if provenance:
        source_quality = max(_SOURCE_WEIGHT.get(source.tier, 0) for source in provenance)
    status_bonus = _EVIDENCE_STATUS_SCORE.get(record.evidence_status, 0)
    confirmation_bonus = max(0, min(record.corroboration_count, 10)) * 4
    stored_confidence_bonus = record.confidence_score if record.confidence_score > 0 else 0
    failure_penalty = min(max(record.failure_count, 0), 16) * 3
    reason_penalty = -18 if record.status_reason else 0
    recency = 0
    reviewed = _newest_source_reviewed_on(provenance)
    if reviewed:
        age_days = max(0, (datetime.now(UTC) - reviewed).days)
        if age_days <= 30:
            recency = 16
        elif age_days <= 90:
            recency = 8
        elif age_days <= 365:
            recency = 4
    exactity_bonus = 0
    if _intersection(record.scope.build_ids, query.build_ids):
        exactity_bonus += 24
    if _intersection(record.scope.models, query.models):
        exactity_bonus += 12
    if _intersection(record.scope.codenames, query.codenames):
        exactity_bonus += 12
    if _intersection(record.scope.partitions, query.partitions):
        exactity_bonus += 4
    score = (
        source_quality
        + status_bonus
        + confirmation_bonus
        + stored_confidence_bonus
        + recency
        + exactity_bonus
        - failure_penalty
        + reason_penalty
    )
    return max(0, min(100, score))


def _score_record(
    record: KnowledgeRecord,
    query: KnowledgeQuery,
    provenance: tuple[KnowledgeSource, ...],
) -> tuple[int, tuple[str, ...], tuple[str, ...]] | None:
    score = max((_SOURCE_WEIGHT[source.tier] for source in provenance), default=0)
    matched: list[str] = []
    missing: list[str] = []

    score += _match_values(query.error_codes, record.error_codes, 1_600, "error", matched)
    score += _embedded_error_match(query.symptoms, record.error_codes, matched)
    score += _embedded_symptom_match(query.symptoms, record.symptoms, matched)
    score += _match_values(query.finding_ids, record.finding_ids, 1_300, "finding", matched)
    score += _scope_score(record.scope.build_ids, query.build_ids, 1_000, "build", matched, missing)
    score += _scope_score(
        record.scope.codenames, query.codenames, 850, "codename", matched, missing
    )
    score += _scope_score(record.scope.models, query.models, 750, "model", matched, missing)
    score += _scope_score(
        record.scope.partitions, query.partitions, 500, "partition", matched, missing
    )
    score += _scope_score(
        record.scope.android_versions,
        query.android_versions,
        260,
        "Android version",
        matched,
        missing,
    )
    score += _scope_score(
        record.scope.bootloader_states,
        query.bootloader_states,
        240,
        "bootloader state",
        matched,
        missing,
    )
    score += _scope_score(record.scope.brands, query.brands, 190, "brand", matched, missing)
    score += _scope_score(
        record.scope.manufacturers,
        query.manufacturers,
        180,
        "manufacturer",
        matched,
        missing,
    )

    query_text = " ".join((*query.symptoms, *query.evidence_terms, *query.error_codes))
    record_text = " ".join(
        (
            record.title,
            record.summary,
            *record.symptoms,
            *record.error_codes,
            *record.finding_ids,
            *record.tags,
            *record.diagnostic_steps,
            *record.known_incompatibility,
        )
    )
    text_score, text_reason = _text_score(query_text, record_text)
    score += text_score
    if text_reason:
        matched.append(text_reason)

    evidence_score = score - max((_SOURCE_WEIGHT[source.tier] for source in provenance), default=0)
    if evidence_score <= 0:
        return None
    confidence_bonus = _RECORD_CONFIDENCE_CAP[record.confidence] * 12
    if record.evidence_status is KnowledgeEvidenceStatus.RETIRED:
        confidence_bonus = 0
    score += confidence_bonus + min(record.corroboration_count, 10)
    return score, tuple(matched), tuple(dict.fromkeys(missing))


def _match_values(
    query_values: tuple[str, ...],
    record_values: tuple[str, ...],
    weight: int,
    label: str,
    matched: list[str],
) -> int:
    common = _intersection(query_values, record_values)
    if not common:
        return 0
    matched.append(f"exact {label}: {', '.join(common[:3])}")
    return weight + min(len(common) - 1, 3) * weight // 10


def _embedded_error_match(
    symptoms: tuple[str, ...],
    record_errors: tuple[str, ...],
    matched: list[str],
) -> int:
    haystack = _normalize(" ".join(symptoms))
    for error in record_errors:
        needle = _normalize(error)
        if len(needle) >= 4 and needle in haystack:
            matched.append(f"exact error in failure text: {error}")
            return 1_500
    return 0


def _embedded_symptom_match(
    symptoms: tuple[str, ...],
    record_symptoms: tuple[str, ...],
    matched: list[str],
) -> int:
    for observed in symptoms:
        observed_text = _normalize(observed)
        observed_tokens = set(observed_text.split())
        for known in record_symptoms:
            known_text = _normalize(known)
            known_tokens = {
                token
                for token in known_text.split()
                if token not in _STOP_WORDS and len(token) >= 3
            }
            if not known_text or not known_tokens:
                continue
            if known_text in observed_text or (
                len(known_tokens) >= 3 and known_tokens <= observed_tokens
            ):
                matched.append(f"failure symptom: {known[:120]}")
                return 1_000
    return 0


def _scope_score(
    record_values: tuple[str, ...],
    query_values: tuple[str, ...],
    weight: int,
    label: str,
    matched: list[str],
    missing: list[str],
) -> int:
    if not record_values:
        return 0
    common = _intersection(record_values, query_values)
    if common:
        matched.append(f"exact {label}: {', '.join(common[:3])}")
        return weight
    missing.append(label)
    return 0


def _text_score(query_text: str, record_text: str) -> tuple[int, str]:
    query_normalized = _normalize(query_text)
    document = _normalize(record_text)
    if not query_normalized or not document:
        return 0, ""
    phrases = tuple(
        phrase
        for phrase in (_normalize(value) for value in query_text.split("\n"))
        if len(phrase) >= 6
    )
    exact_phrase = next((phrase for phrase in phrases if phrase in document), "")
    if exact_phrase:
        return 650, f"failure phrase: {exact_phrase[:120]}"
    query_tokens = {
        token for token in query_normalized.split() if token not in _STOP_WORDS and len(token) >= 3
    }
    document_tokens = set(document.split())
    common = sorted(query_tokens & document_tokens)
    if not common:
        return 0, ""
    rare = [token for token in common if len(token) >= 7 or any(char.isdigit() for char in token)]
    if len(common) < 2 and not rare:
        return 0, ""
    return min(420, len(common) * 45 + len(rare) * 35), (
        "local evidence terms: " + ", ".join((rare or common)[:6])
    )


def _scope_conflicts(record: KnowledgeRecord, query: KnowledgeQuery) -> bool:
    scoped_pairs = (
        (record.scope.build_ids, query.build_ids),
        (record.scope.codenames, query.codenames),
        (record.scope.models, query.models),
        (record.scope.android_versions, query.android_versions),
        (record.scope.manufacturers, query.manufacturers),
    )
    return any(left and right and not _intersection(left, right) for left, right in scoped_pairs)


def _match_confidence(
    record: KnowledgeRecord,
    matched: tuple[str, ...],
    missing: tuple[str, ...],
) -> MatchConfidence:
    text = " ".join(matched)
    has_failure = "exact error" in text or "exact finding" in text
    has_build = "exact build" in text
    has_identity = "exact codename" in text or "exact model" in text
    has_partition = "exact partition" in text
    if has_failure and has_build and has_identity and (has_partition or "partition" not in missing):
        derived = MatchConfidence.EXACT
    elif has_failure or (has_build and has_identity):
        derived = MatchConfidence.HIGH
    elif len(matched) >= 2 or has_identity or has_partition:
        derived = MatchConfidence.MEDIUM
    elif matched:
        derived = MatchConfidence.LOW
    else:
        derived = MatchConfidence.UNCONFIRMED
    capped = min(_CONFIDENCE_VALUE[derived], _RECORD_CONFIDENCE_CAP[record.confidence])
    return _CONFIDENCE_FOR_VALUE[capped]


def _safety(
    operations: tuple[KnowledgeOperation, ...],
    record: KnowledgeRecord,
    query: KnowledgeQuery,
) -> str:
    if record.evidence_status in {
        KnowledgeEvidenceStatus.DISPUTED,
        KnowledgeEvidenceStatus.UNSAFE,
        KnowledgeEvidenceStatus.RETIRED,
    }:
        return f"WITHHELD • record is {record.evidence_status.value}; retained as diagnostic history, not a suggested repair path."
    changing = tuple(operation for operation in operations if operation.changes_device)
    if not changing:
        return "GUIDANCE ONLY • no automatic device-changing operation is declared."
    if record.moderation_required:
        return (
            "LOCKED • this device-changing operation is awaiting moderation "
            "before it can be surfaced as a suggested repair path."
        )
    eligible = tuple(
        operation
        for operation in changing
        if _operation_evidence_complete(operation, record, query)
    )
    if len(eligible) == len(changing):
        if any(operation.risk_class is KnowledgeRiskClass.HIGH for operation in changing):
            return (
                "EXACT EVIDENCE PRESENT • this high-risk operation is shown only for "
                "separate human review; this lookup still grants no execution authority."
            )
        return (
            "EXACT EVIDENCE PRESENT • operation may be shown for separate Guardian review; "
            "this lookup still grants no execution authority."
        )
    return (
        "LOCKED • a device-changing operation is withheld because exact target, build, "
        "partition, verified input, or rollback evidence is missing."
    )


def _operation_evidence_complete(
    operation: KnowledgeOperation,
    record: KnowledgeRecord,
    query: KnowledgeQuery,
) -> bool:
    target_match = bool(
        _intersection(record.scope.models, query.models)
        or _intersection(record.scope.codenames, query.codenames)
    )
    build_match = bool(_intersection(record.scope.build_ids, query.build_ids))
    partitions = set(_normalized(query.partitions))
    targets = set(_normalized(operation.target_partitions))
    inputs = set(_normalized(query.verified_inputs))
    required_inputs = set(_normalized(operation.verified_input_requirements))
    rollback = _normalize(operation.rollback_route) in set(_normalized(query.rollback_routes))
    return bool(
        target_match
        and build_match
        and targets
        and targets <= partitions
        and required_inputs
        and required_inputs <= inputs
        and rollback
    )


def _intersection(left: tuple[str, ...], right: tuple[str, ...]) -> tuple[str, ...]:
    right_normalized = set(_normalized(right))
    return tuple(value for value in left if _normalize(value) in right_normalized)


def _normalized(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(_normalize(value) for value in values if _normalize(value))


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9._-]+", " ", str(value).casefold()).split())


def _unique(values, *, maximum: int = 128) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _bounded(raw, 4_000)
        normalized = _normalize(value)
        if not value or normalized in seen:
            continue
        seen.add(normalized)
        result.append(value)
        if len(result) >= maximum:
            break
    return tuple(result)


def _bounded(value: object, maximum: int) -> str:
    return str(value).replace("\x00", " ").strip()[:maximum]


def _query_digest(query: KnowledgeQuery) -> str:
    encoded = json.dumps(asdict(query), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
