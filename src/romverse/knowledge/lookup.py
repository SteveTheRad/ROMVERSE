"""Deterministic offline matching for Device DNA and typed failure evidence."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, replace
from pathlib import Path

from romverse.device.dna import DeviceDnaProfile, EvidenceConfidence
from romverse.knowledge.models import (
    KnowledgeArchive,
    KnowledgeConfidence,
    KnowledgeFailure,
    KnowledgeLookupReport,
    KnowledgeMatch,
    KnowledgeOperation,
    KnowledgeQuery,
    KnowledgeRecord,
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
        brands=values("identity.brand"),
        models=values("identity.model", "identity.marketing_name"),
        codenames=values("identity.codename", "identity.product", "identity.vendor_device"),
        build_ids=values(
            "software.build",
            "software.live_incremental",
            "software.live_system_incremental",
            "firmware.ota_post_incremental",
        ),
        android_versions=values("software.android_version"),
        bootloader_states=values("bootloader.state"),
        partitions=_unique(partitions),
        evidence_terms=_unique(evidence_terms, maximum=256),
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
        score, matched, missing = scored
        confidence = _match_confidence(record, matched, missing)
        results.append(
            KnowledgeMatch(
                record=record,
                score=score,
                confidence=confidence,
                matched_evidence=matched,
                missing_evidence=missing,
                provenance=provenance,
                safety=_safety(record.operations, record, query),
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
    return tuple(results[:bounded_limit])


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
    score += _match_values(query.finding_ids, record.finding_ids, 1_300, "finding", matched)
    score += _scope_score(record.scope.build_ids, query.build_ids, 1_000, "build", matched, missing)
    score += _scope_score(record.scope.codenames, query.codenames, 850, "codename", matched, missing)
    score += _scope_score(record.scope.models, query.models, 750, "model", matched, missing)
    score += _scope_score(record.scope.partitions, query.partitions, 500, "partition", matched, missing)
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
        token
        for token in query_normalized.split()
        if token not in _STOP_WORDS and len(token) >= 3
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
    changing = tuple(operation for operation in operations if operation.changes_device)
    if not changing:
        return "GUIDANCE ONLY • no automatic device-changing operation is declared."
    eligible = tuple(
        operation for operation in changing if _operation_evidence_complete(operation, record, query)
    )
    if len(eligible) == len(changing):
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
