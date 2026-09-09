from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from romverse.knowledge.evidence_correlation import (
    CorrelationUse,
    EvidenceCorrelationError,
    correlate_evidence,
    evidence_correlation_mapping,
    parse_evidence_correlation,
)
from romverse.knowledge.online_evidence import (
    ClaimAuthorityDomain,
    EvidenceFreshness,
    EvidenceLifecycleStatus,
    EvidenceScope,
    EvidenceState,
    SourceCategory,
    create_claim,
    create_claim_source_authority,
    evidence_lifecycle_for_claim,
)

NOW = datetime(2026, 9, 9, tzinfo=UTC)
DIGEST = hashlib.sha256(b"artifact").hexdigest()


def _claim(value: str = "popsicle", *, key: str = "device.codename", scope=None):
    return create_claim(
        claim_key=key,
        scope=scope or EvidenceScope(manufacturers=("xiaomi",), models=("2509fpn0bc",)),
        source_id="official.oem",
        url="https://example.com/device",
        publisher="OEM",
        category=SourceCategory.OFFICIAL_OEM,
        retrieved_at=NOW,
        content_digest=DIGEST,
        parser_id="romverse.fixture",
        parser_version="1",
        structured_value=value,
        freshness=EvidenceFreshness.CURRENT,
        state=EvidenceState.OFFICIALLY_DOCUMENTED,
        confidence=90,
    )


def _records(claim, *, status=EvidenceLifecycleStatus.ACTIVE):
    authority = create_claim_source_authority(
        source_id=claim.source.source_id,
        domains=(ClaimAuthorityDomain.CODENAME,),
        applicable_claim_keys=(claim.claim_key,),
        evidence_claim_ids=(claim.claim_id,),
    )
    lifecycle = evidence_lifecycle_for_claim(claim, observed_at=NOW, status=status)
    return authority, lifecycle


def test_exact_binding_is_active_order_independent_and_authority_free():
    first = _claim()
    second = _claim("2509fpn0bc", key="device.model")
    first_authority, first_lifecycle = _records(first)
    second_authority = create_claim_source_authority(
        source_id=second.source.source_id,
        domains=(ClaimAuthorityDomain.MODEL_IDENTITY,),
        applicable_claim_keys=(second.claim_key,),
        evidence_claim_ids=(second.claim_id,),
    )
    second_lifecycle = evidence_lifecycle_for_claim(second, observed_at=NOW)
    domains = {
        first.claim_id: ClaimAuthorityDomain.CODENAME,
        second.claim_id: ClaimAuthorityDomain.MODEL_IDENTITY,
    }

    left = correlate_evidence(
        (first, second),
        (first_authority, second_authority),
        (first_lifecycle, second_lifecycle),
        domains,
    )
    right = correlate_evidence(
        (second, first),
        (second_authority, first_authority),
        (second_lifecycle, first_lifecycle),
        domains,
    )

    assert left == right
    assert len(left.active) == 2
    assert not left.retained
    assert left.compatibility == "UNCONFIRMED"
    assert left.execution_authority == "none"
    assert not left.phone_action_allowed
    assert not left.guardian_approval
    assert not left.bootloader_relock_allowed
    assert parse_evidence_correlation(evidence_correlation_mapping(left)) == left


@pytest.mark.parametrize(
    "status",
    [
        EvidenceLifecycleStatus.SUPERSEDED,
        EvidenceLifecycleStatus.QUARANTINED,
        EvidenceLifecycleStatus.EXPIRED,
    ],
)
def test_unusable_lifecycle_is_retained_not_active(status):
    claim = _claim()
    authority, lifecycle = _records(claim, status=status)
    report = correlate_evidence(
        (claim,), (authority,), (lifecycle,), {claim.claim_id: ClaimAuthorityDomain.CODENAME}
    )
    assert not report.active
    assert report.retained[0].use is CorrelationUse.RETAINED_UNUSABLE
    assert report.requires_investigation


def test_missing_or_nonapplicable_authority_and_lifecycle_remain_unconfirmed():
    claim = _claim()
    report = correlate_evidence((claim,), (), (), {})
    assert report.retained[0].use is CorrelationUse.UNCONFIRMED
    assert set(report.retained[0].reasons) == {
        "missing-lifecycle",
        "missing-or-non-applicable-authority",
    }


def test_stale_and_unconfirmed_claims_remain_unconfirmed():
    claim = _claim()
    authority, lifecycle = _records(claim)
    stale = replace(lifecycle, freshness=EvidenceFreshness.STALE)
    report = correlate_evidence(
        (claim,), (authority,), (stale,), {claim.claim_id: ClaimAuthorityDomain.CODENAME}
    )
    assert report.retained[0].use is CorrelationUse.UNCONFIRMED

    unknown = replace(claim, state=EvidenceState.UNCONFIRMED)
    unknown_lifecycle = evidence_lifecycle_for_claim(unknown, observed_at=NOW)
    report = correlate_evidence(
        (unknown,),
        (authority,),
        (unknown_lifecycle,),
        {unknown.claim_id: ClaimAuthorityDomain.CODENAME},
    )
    assert report.retained[0].use is CorrelationUse.UNCONFIRMED


def test_exact_source_key_domain_artifact_and_scope_binding_fail_closed():
    claim = _claim()
    authority, lifecycle = _records(claim)
    with pytest.raises(EvidenceCorrelationError, match="Lifecycle"):
        correlate_evidence(
            (claim,),
            (authority,),
            (replace(lifecycle, artifact_digest="0" * 64),),
            {claim.claim_id: ClaimAuthorityDomain.CODENAME},
        )
    with pytest.raises(EvidenceCorrelationError, match="Lifecycle"):
        correlate_evidence(
            (claim,),
            (authority,),
            (replace(lifecycle, scope=EvidenceScope(models=("similar",))),),
            {claim.claim_id: ClaimAuthorityDomain.CODENAME},
        )
    wrong = replace(authority, source_id="other.source")
    report = correlate_evidence(
        (claim,), (wrong,), (lifecycle,), {claim.claim_id: ClaimAuthorityDomain.CODENAME}
    )
    assert report.retained[0].use is CorrelationUse.UNCONFIRMED
    report = correlate_evidence(
        (claim,), (authority,), (lifecycle,), {claim.claim_id: ClaimAuthorityDomain.MODEL_IDENTITY}
    )
    assert report.retained[0].use is CorrelationUse.UNCONFIRMED


def test_dangling_self_and_one_sided_relationships_are_rejected():
    claim = _claim()
    dangling = replace(claim, corroborating_claim_ids=("0" * 64,))
    with pytest.raises(EvidenceCorrelationError, match="dangling"):
        correlate_evidence((dangling,), (), (), {})
    self_linked = replace(claim, conflicting_claim_ids=(claim.claim_id,))
    with pytest.raises(EvidenceCorrelationError, match="itself"):
        correlate_evidence((self_linked,), (), (), {})
    other = _claim("other")
    one_sided = replace(claim, conflicting_claim_ids=(other.claim_id,))
    with pytest.raises(EvidenceCorrelationError, match="both"):
        correlate_evidence((one_sided, other), (), (), {})


def test_two_sided_contradiction_is_preserved_and_conflicting_values_investigate():
    first = _claim("popsicle")
    second = _claim("popsicle-pro")
    first = replace(first, conflicting_claim_ids=(second.claim_id,))
    second = replace(second, conflicting_claim_ids=(first.claim_id,))
    first_authority, first_lifecycle = _records(first)
    second_authority, second_lifecycle = _records(second)
    report = correlate_evidence(
        (second, first),
        (second_authority, first_authority),
        (second_lifecycle, first_lifecycle),
        {
            first.claim_id: ClaimAuthorityDomain.CODENAME,
            second.claim_id: ClaimAuthorityDomain.CODENAME,
        },
    )
    assert report.requires_investigation
    assert "conflicting-active-values-or-scopes" in report.investigation_reasons
    assert report.active[0].contradicting_claim_ids


def test_duplicate_claim_lifecycle_and_authority_are_rejected():
    claim = _claim()
    authority, lifecycle = _records(claim)
    with pytest.raises(EvidenceCorrelationError, match="Duplicate claim"):
        correlate_evidence((claim, claim), (), (), {})
    with pytest.raises(EvidenceCorrelationError, match="Duplicate lifecycle"):
        correlate_evidence((claim,), (), (lifecycle, lifecycle), {})
    with pytest.raises(EvidenceCorrelationError, match="Duplicate authority"):
        correlate_evidence(
            (claim,),
            (authority, authority),
            (lifecycle,),
            {claim.claim_id: ClaimAuthorityDomain.CODENAME},
        )


def test_strict_parse_rejects_extra_schema_authority_digest_and_malformed_types():
    claim = _claim()
    authority, lifecycle = _records(claim)
    report = correlate_evidence(
        (claim,), (authority,), (lifecycle,), {claim.claim_id: ClaimAuthorityDomain.CODENAME}
    )
    raw = evidence_correlation_mapping(report)
    variants = []
    extra = dict(raw)
    extra["extra"] = True
    variants.append(extra)
    schema = dict(raw)
    schema["schema_version"] = 2
    variants.append(schema)
    authority_raw = dict(raw)
    authority_raw["guardian_approval"] = True
    variants.append(authority_raw)
    digest = dict(raw)
    digest["report_digest"] = "0" * 64
    variants.append(digest)
    malformed = dict(raw)
    malformed["active"] = "not-a-list"
    variants.append(malformed)
    for value in variants:
        with pytest.raises(EvidenceCorrelationError):
            parse_evidence_correlation(json.loads(json.dumps(value)))


@pytest.mark.parametrize(
    "unsafe",
    ["serial:ABC123", "imei:123456789012345", "account:user7", "token:secret", "/home/alice/file"],
)
def test_report_parser_rejects_private_identifiers(unsafe):
    claim = _claim()
    authority, lifecycle = _records(claim)
    raw = evidence_correlation_mapping(
        correlate_evidence(
            (claim,), (authority,), (lifecycle,), {claim.claim_id: ClaimAuthorityDomain.CODENAME}
        )
    )
    raw["active"][0]["source_id"] = unsafe
    with pytest.raises(EvidenceCorrelationError):
        parse_evidence_correlation(raw)
