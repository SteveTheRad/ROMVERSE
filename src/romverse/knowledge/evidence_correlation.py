"""Deterministic, side-effect-free correlation of existing evidence contracts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from enum import StrEnum
from types import MappingProxyType

from romverse.knowledge.online_evidence import (
    ClaimAuthorityDomain,
    ClaimSourceAuthority,
    EvidenceFreshness,
    EvidenceLifecycle,
    EvidenceLifecycleStatus,
    EvidenceState,
    OnlineEvidenceClaim,
    scrub_private_text,
)


class EvidenceCorrelationError(ValueError):
    """Correlation input or a stored report failed closed."""


class CorrelationUse(StrEnum):
    ACTIVE = "active"
    RETAINED_UNUSABLE = "retained-unusable"
    UNCONFIRMED = "unconfirmed"


@dataclass(frozen=True, slots=True)
class CorrelatedEvidence:
    claim_id: str
    source_id: str
    claim_key: str
    authority_domain: ClaimAuthorityDomain | None
    artifact_digest: str
    lifecycle_status: EvidenceLifecycleStatus | None
    use: CorrelationUse
    supporting_claim_ids: tuple[str, ...]
    contradicting_claim_ids: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceCorrelationReport:
    schema_version: int
    active: tuple[CorrelatedEvidence, ...]
    retained: tuple[CorrelatedEvidence, ...]
    requires_investigation: bool
    investigation_reasons: tuple[str, ...]
    compatibility: str
    execution_authority: str
    phone_action_allowed: bool
    guardian_approval: bool
    bootloader_relock_allowed: bool
    report_digest: str


_UNUSABLE_LIFECYCLES = {
    EvidenceLifecycleStatus.SUPERSEDED,
    EvidenceLifecycleStatus.QUARANTINED,
    EvidenceLifecycleStatus.EXPIRED,
}
_UNUSABLE_CLAIM_STATES = {
    EvidenceState.CONFLICTING,
    EvidenceState.UNCONFIRMED,
    EvidenceState.OUTDATED,
    EvidenceState.RETIRED,
}
_TOKEN = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def correlate_evidence(
    claims: tuple[OnlineEvidenceClaim, ...],
    authorities: tuple[ClaimSourceAuthority, ...],
    lifecycles: tuple[EvidenceLifecycle, ...],
    claim_domains: Mapping[str, ClaimAuthorityDomain],
) -> EvidenceCorrelationReport:
    """Correlate existing records without promoting compatibility or authority."""

    if (
        not isinstance(claims, tuple)
        or not isinstance(authorities, tuple)
        or not isinstance(lifecycles, tuple)
    ):
        raise EvidenceCorrelationError("Correlation collections must be immutable tuples")
    if not isinstance(claim_domains, Mapping):
        raise EvidenceCorrelationError("Claim domains are invalid")
    if len(claims) > 512 or len(authorities) > 512 or len(lifecycles) > 512:
        raise EvidenceCorrelationError("Correlation input exceeds its boundary")

    if not all(isinstance(item, OnlineEvidenceClaim) for item in claims):
        raise EvidenceCorrelationError("Claim record is invalid")
    if not all(isinstance(item, EvidenceLifecycle) for item in lifecycles):
        raise EvidenceCorrelationError("Lifecycle record is invalid")
    claim_by_id = _unique(claims, lambda item: item.claim_id, "claim")
    lifecycle_by_claim = _unique(lifecycles, lambda item: item.claim_id, "lifecycle")
    authority_keys: set[
        tuple[str, tuple[ClaimAuthorityDomain, ...], tuple[str, ...], tuple[str, ...]]
    ] = set()
    for authority in authorities:
        if not isinstance(authority, ClaimSourceAuthority):
            raise EvidenceCorrelationError("Authority record is invalid")
        key = (
            authority.source_id,
            authority.domains,
            authority.applicable_claim_keys,
            authority.evidence_claim_ids,
        )
        if key in authority_keys:
            raise EvidenceCorrelationError("Duplicate authority record")
        authority_keys.add(key)

    unknown_domains = set(claim_domains) - set(claim_by_id)
    if unknown_domains:
        raise EvidenceCorrelationError("Claim domain mapping is dangling")
    normalized_domains: dict[str, ClaimAuthorityDomain] = {}
    for claim_id, domain in claim_domains.items():
        normalized_domains[_digest(claim_id)] = ClaimAuthorityDomain(domain)

    all_ids = set(claim_by_id)
    for claim in claims:
        related = set(claim.corroborating_claim_ids) | set(claim.conflicting_claim_ids)
        if claim.claim_id in related:
            raise EvidenceCorrelationError("Evidence relationship cannot target itself")
        if not related <= all_ids:
            raise EvidenceCorrelationError("Evidence relationship is dangling")
        for target in claim.conflicting_claim_ids:
            if claim.claim_id not in claim_by_id[target].conflicting_claim_ids:
                raise EvidenceCorrelationError("Contradiction must be explicit on both claims")

    records: list[CorrelatedEvidence] = []
    investigation: set[str] = set()
    for claim in sorted(claims, key=lambda item: item.claim_id):
        lifecycle = lifecycle_by_claim.get(claim.claim_id)
        domain = normalized_domains.get(claim.claim_id)
        reasons: set[str] = set()

        if lifecycle is None:
            reasons.add("missing-lifecycle")
        else:
            _bind_lifecycle(claim, lifecycle)

        applicable = [
            authority
            for authority in authorities
            if authority.source_id == claim.source.source_id
            and claim.claim_id in authority.evidence_claim_ids
            and domain is not None
            and authority.applies_to(domain, claim.claim_key)
        ]
        if len(applicable) > 1:
            raise EvidenceCorrelationError("Claim has ambiguous authority applicability")
        if not applicable:
            reasons.add("missing-or-non-applicable-authority")

        if lifecycle and lifecycle.status in _UNUSABLE_LIFECYCLES:
            use = CorrelationUse.RETAINED_UNUSABLE
            reasons.add(f"lifecycle-{lifecycle.status.value}")
        elif (
            lifecycle is None
            or not applicable
            or lifecycle.freshness in {EvidenceFreshness.STALE, EvidenceFreshness.UNCONFIRMED}
            or claim.state in _UNUSABLE_CLAIM_STATES
        ):
            use = CorrelationUse.UNCONFIRMED
            if lifecycle and lifecycle.freshness in {
                EvidenceFreshness.STALE,
                EvidenceFreshness.UNCONFIRMED,
            }:
                reasons.add(f"freshness-{lifecycle.freshness.value}")
            if claim.state in _UNUSABLE_CLAIM_STATES:
                reasons.add(f"claim-{claim.state.value}")
        else:
            use = CorrelationUse.ACTIVE

        if claim.conflicting_claim_ids:
            reasons.add("explicit-contradiction")
        record = CorrelatedEvidence(
            claim.claim_id,
            claim.source.source_id,
            claim.claim_key,
            domain,
            claim.source.content_digest,
            lifecycle.status if lifecycle else None,
            use,
            tuple(sorted(claim.corroborating_claim_ids)),
            tuple(sorted(claim.conflicting_claim_ids)),
            tuple(sorted(reasons)),
        )
        records.append(record)
        investigation.update(reasons)

    active_records = [item for item in records if item.use is CorrelationUse.ACTIVE]
    for index, left in enumerate(active_records):
        left_claim = claim_by_id[left.claim_id]
        for right in active_records[index + 1 :]:
            right_claim = claim_by_id[right.claim_id]
            if left.claim_key == right.claim_key and (
                left_claim.structured_value != right_claim.structured_value
                or left_claim.scope != right_claim.scope
            ):
                investigation.add("conflicting-active-values-or-scopes")

    active = tuple(item for item in records if item.use is CorrelationUse.ACTIVE)
    retained = tuple(item for item in records if item.use is not CorrelationUse.ACTIVE)
    basis = {
        "schema_version": 1,
        "active": [_record_mapping(item) for item in active],
        "retained": [_record_mapping(item) for item in retained],
        "requires_investigation": bool(investigation),
        "investigation_reasons": sorted(investigation),
        "compatibility": "UNCONFIRMED",
        "execution_authority": "none",
        "phone_action_allowed": False,
        "guardian_approval": False,
        "bootloader_relock_allowed": False,
    }
    digest = hashlib.sha256(_canonical(basis)).hexdigest()
    return EvidenceCorrelationReport(
        1,
        active,
        retained,
        bool(investigation),
        tuple(sorted(investigation)),
        "UNCONFIRMED",
        "none",
        False,
        False,
        False,
        digest,
    )


def evidence_correlation_mapping(report: EvidenceCorrelationReport) -> dict[str, object]:
    mapping = {
        "schema_version": report.schema_version,
        "active": [_record_mapping(item) for item in report.active],
        "retained": [_record_mapping(item) for item in report.retained],
        "requires_investigation": report.requires_investigation,
        "investigation_reasons": list(report.investigation_reasons),
        "compatibility": report.compatibility,
        "execution_authority": report.execution_authority,
        "phone_action_allowed": report.phone_action_allowed,
        "guardian_approval": report.guardian_approval,
        "bootloader_relock_allowed": report.bootloader_relock_allowed,
        "report_digest": report.report_digest,
    }
    return mapping


def parse_evidence_correlation(raw: dict[str, object]) -> EvidenceCorrelationReport:
    expected = {field.name for field in fields(EvidenceCorrelationReport)}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise EvidenceCorrelationError("Correlation report fields are invalid")
    if type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
        raise EvidenceCorrelationError("Correlation report schema is invalid")
    if (
        raw.get("compatibility") != "UNCONFIRMED"
        or raw.get("execution_authority") != "none"
        or type(raw.get("phone_action_allowed")) is not bool
        or raw.get("phone_action_allowed")
        or type(raw.get("guardian_approval")) is not bool
        or raw.get("guardian_approval")
        or type(raw.get("bootloader_relock_allowed")) is not bool
        or raw.get("bootloader_relock_allowed")
    ):
        raise EvidenceCorrelationError("Correlation report cannot grant authority")
    active = _parse_records(raw.get("active"), CorrelationUse.ACTIVE)
    retained = _parse_records(raw.get("retained"), None)
    reasons = _stored_reasons(raw.get("investigation_reasons"))
    requires = raw.get("requires_investigation")
    if type(requires) is not bool or requires != bool(reasons):
        raise EvidenceCorrelationError("Correlation investigation state is invalid")
    report = EvidenceCorrelationReport(
        1,
        active,
        retained,
        requires,
        reasons,
        "UNCONFIRMED",
        "none",
        False,
        False,
        False,
        _digest(raw.get("report_digest")),
    )
    basis = evidence_correlation_mapping(report)
    basis.pop("report_digest")
    if report.report_digest != hashlib.sha256(_canonical(basis)).hexdigest():
        raise EvidenceCorrelationError("Correlation report digest is invalid")
    if raw != json.loads(json.dumps(evidence_correlation_mapping(report))):
        raise EvidenceCorrelationError("Correlation report is not canonical")
    return report


def _bind_lifecycle(claim: OnlineEvidenceClaim, lifecycle: EvidenceLifecycle) -> None:
    if not isinstance(lifecycle, EvidenceLifecycle):
        raise EvidenceCorrelationError("Lifecycle record is invalid")
    if (
        lifecycle.claim_id != claim.claim_id
        or lifecycle.artifact_digest != claim.source.content_digest
        or lifecycle.scope != claim.scope
        or lifecycle.supporting_claim_ids != claim.corroborating_claim_ids
        or lifecycle.contradicting_claim_ids != claim.conflicting_claim_ids
    ):
        raise EvidenceCorrelationError("Lifecycle does not exactly bind its claim")


def _unique(items: tuple[object, ...], key, label: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for item in items:
        value = key(item)
        if value in result:
            raise EvidenceCorrelationError(f"Duplicate {label} record")
        result[value] = item
    return result


def _record_mapping(item: CorrelatedEvidence) -> dict[str, object]:
    mapping = asdict(item)
    mapping["authority_domain"] = item.authority_domain.value if item.authority_domain else None
    mapping["lifecycle_status"] = item.lifecycle_status.value if item.lifecycle_status else None
    mapping["use"] = item.use.value
    mapping["supporting_claim_ids"] = list(item.supporting_claim_ids)
    mapping["contradicting_claim_ids"] = list(item.contradicting_claim_ids)
    mapping["reasons"] = list(item.reasons)
    return mapping


def _parse_records(
    raw: object, required_use: CorrelationUse | None
) -> tuple[CorrelatedEvidence, ...]:
    if not isinstance(raw, list) or len(raw) > 512:
        raise EvidenceCorrelationError("Correlation records are invalid")
    expected = {field.name for field in fields(CorrelatedEvidence)}
    records: list[CorrelatedEvidence] = []
    for value in raw:
        if not isinstance(value, dict) or set(value) != expected:
            raise EvidenceCorrelationError("Correlation record fields are invalid")
        use = CorrelationUse(value.get("use"))
        if required_use is not None and use is not required_use:
            raise EvidenceCorrelationError("Correlation active set is invalid")
        if required_use is None and use is CorrelationUse.ACTIVE:
            raise EvidenceCorrelationError("Correlation retained set is invalid")
        record = CorrelatedEvidence(
            _digest(value.get("claim_id")),
            _token(value.get("source_id")),
            _token(value.get("claim_key")),
            ClaimAuthorityDomain(value["authority_domain"])
            if value.get("authority_domain")
            else None,
            _digest(value.get("artifact_digest")),
            EvidenceLifecycleStatus(value["lifecycle_status"])
            if value.get("lifecycle_status")
            else None,
            use,
            _stored_digests(value.get("supporting_claim_ids")),
            _stored_digests(value.get("contradicting_claim_ids")),
            _stored_reasons(value.get("reasons")),
        )
        records.append(record)
    ordered = tuple(sorted(records, key=lambda item: item.claim_id))
    if tuple(records) != ordered or len({item.claim_id for item in records}) != len(records):
        raise EvidenceCorrelationError("Correlation records are not canonical")
    return ordered


def _stored_digests(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise EvidenceCorrelationError("Correlation relationships are invalid")
    result = tuple(_digest(item) for item in value)
    if result != tuple(sorted(set(result))):
        raise EvidenceCorrelationError("Correlation relationships are not canonical")
    return result


def _stored_reasons(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise EvidenceCorrelationError("Correlation reasons are invalid")
    result = tuple(_token(item) for item in value)
    if result != tuple(sorted(set(result))):
        raise EvidenceCorrelationError("Correlation reasons are not canonical")
    return result


def _token(value: object) -> str:
    if (
        not isinstance(value, str)
        or not _TOKEN.fullmatch(value)
        or scrub_private_text(value) != value
    ):
        raise EvidenceCorrelationError("Correlation identifier is invalid")
    return value


def _digest(value: object) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise EvidenceCorrelationError("Correlation digest is invalid")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


EMPTY_CLAIM_DOMAINS: Mapping[str, ClaimAuthorityDomain] = MappingProxyType({})
