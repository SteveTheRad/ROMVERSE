from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from romverse.device.evidence_identity import (
    EvidenceIdentityProjectionError,
    evidence_identity_projection_mapping,
    parse_evidence_identity_projection,
    project_canonical_device_identity,
)
from romverse.device.identity import (
    canonical_device_identity_mapping,
    create_canonical_device_identity,
)
from romverse.knowledge.evidence_correlation import EvidenceCorrelationError, correlate_evidence
from romverse.knowledge.online_evidence import (
    ClaimAuthorityDomain,
    ClaimKind,
    EvidenceFreshness,
    EvidenceLifecycleStatus,
    EvidenceScope,
    EvidenceState,
    SourceCategory,
    create_claim,
    create_claim_source_authority,
    evidence_lifecycle_for_claim,
)

NOW = datetime(2026, 9, 10, tzinfo=UTC)
DIGEST = hashlib.sha256(b"official-device-index").hexdigest()
SCOPE = EvidenceScope(
    manufacturers=("Xiaomi",),
    models=("2509FPN0BC",),
    codenames=("popsicle",),
)
KEY_DOMAINS = {
    "device.identity.manufacturer": ClaimAuthorityDomain.DEVICE_IDENTITY,
    "device.identity.model": ClaimAuthorityDomain.MODEL_IDENTITY,
    "device.identity.codename": ClaimAuthorityDomain.CODENAME,
    "device.identity.marketing-name": ClaimAuthorityDomain.DEVICE_IDENTITY,
}


def _claim(
    key: str,
    value: str,
    *,
    scope: EvidenceScope = SCOPE,
    kind=ClaimKind.IDENTITY,
    freshness=EvidenceFreshness.CURRENT,
    state=EvidenceState.OFFICIALLY_DOCUMENTED,
):
    return create_claim(
        claim_key=key,
        scope=scope,
        source_id="official.oem",
        url="https://example.com/devices",
        publisher="OEM",
        category=SourceCategory.OFFICIAL_OEM,
        retrieved_at=NOW,
        content_digest=DIGEST,
        parser_id="romverse.fixture",
        parser_version="1",
        structured_value=value,
        freshness=freshness,
        state=state,
        confidence=90,
        knowledge_kind=kind,
    )


def _base_claims(*, marketing: bool = True):
    claims = [
        _claim("device.identity.manufacturer", "Xiaomi"),
        _claim("device.identity.model", "2509FPN0BC"),
        _claim("device.identity.codename", "popsicle"),
    ]
    if marketing:
        claims.append(_claim("device.identity.marketing-name", "Xiaomi 17 Pro Max"))
    return tuple(claims)


def _report(claims, *, statuses=None, domains=None):
    statuses = statuses or {}
    domains = domains or {claim.claim_id: KEY_DOMAINS[claim.claim_key] for claim in claims}
    authorities = tuple(
        create_claim_source_authority(
            source_id=claim.source.source_id,
            domains=(domains[claim.claim_id],),
            applicable_claim_keys=(claim.claim_key,),
            evidence_claim_ids=(claim.claim_id,),
        )
        for claim in claims
    )
    lifecycles = tuple(
        evidence_lifecycle_for_claim(
            claim,
            observed_at=NOW,
            status=statuses.get(claim.claim_id, EvidenceLifecycleStatus.ACTIVE),
        )
        for claim in claims
    )
    return correlate_evidence(tuple(claims), authorities, lifecycles, domains)


def _reseal_projection(raw):
    unsigned = dict(raw)
    unsigned.pop("projection_digest")
    raw["projection_digest"] = hashlib.sha256(
        json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def test_exact_projection_is_order_independent_discovery_only_and_strictly_parses():
    claims = _base_claims()
    report = _report(claims)

    first = project_canonical_device_identity(report, claims)
    second = project_canonical_device_identity(report, tuple(reversed(claims)))

    assert first == second
    assert first.identity is not None
    assert first.identity.manufacturer == "Xiaomi"
    assert first.identity.model == "2509FPN0BC"
    assert first.identity.codename == "popsicle"
    assert first.identity.marketing_names == ("Xiaomi 17 Pro Max",)
    assert first.identity.brand == first.identity.region == ""
    assert first.identity.oem_identifiers == ()
    assert first.identity.aliases == first.identity.family_ids == ()
    assert first.identity.soc == first.identity.platform == ""
    assert first.identity.evidence_claim_ids == first.selected_claim_ids
    assert first.compatibility == "UNCONFIRMED"
    assert first.execution_authority == "none"
    assert not first.phone_action_allowed
    assert not first.guardian_approval
    assert not first.bootloader_relock_allowed
    assert parse_evidence_identity_projection(evidence_identity_projection_mapping(first)) == first


def test_exact_report_claim_source_key_domain_and_artifact_binding_rejects_substitution():
    claims = _base_claims(marketing=False)
    report = _report(claims)
    substituted = replace(claims[0], structured_value="Samsung")
    with pytest.raises(EvidenceIdentityProjectionError, match="identity"):
        project_canonical_device_identity(report, (substituted, *claims[1:]))
    with pytest.raises(EvidenceIdentityProjectionError, match="exactly bind"):
        project_canonical_device_identity(report, claims[:-1])
    changed_source = replace(claims[0], source=replace(claims[0].source, source_id="other.oem"))
    with pytest.raises(EvidenceIdentityProjectionError):
        project_canonical_device_identity(report, (changed_source, *claims[1:]))
    with pytest.raises(EvidenceIdentityProjectionError, match="Correlation report"):
        project_canonical_device_identity(replace(report, report_digest="0" * 64), claims)


@pytest.mark.parametrize(
    "status",
    [
        EvidenceLifecycleStatus.SUPERSEDED,
        EvidenceLifecycleStatus.QUARANTINED,
        EvidenceLifecycleStatus.EXPIRED,
    ],
)
def test_missing_or_retained_required_evidence_is_unconfirmed(status):
    claims = _base_claims(marketing=False)
    target = claims[1]
    report = _report(claims, statuses={target.claim_id: status})
    projected = project_canonical_device_identity(report, claims)
    assert projected.identity is None
    assert f"required-evidence-not-active:{target.claim_key}" in projected.reasons


def test_missing_duplicate_stale_and_unconfirmed_required_evidence_fail_closed():
    claims = _base_claims(marketing=False)
    report = _report(claims[:2])
    projected = project_canonical_device_identity(report, claims[:2])
    assert projected.identity is None
    assert "missing-required-evidence:device.identity.codename" in projected.reasons

    duplicate = (*claims, _claim("device.identity.model", "2509fpn0bc"))
    projected = project_canonical_device_identity(_report(duplicate), duplicate)
    assert projected.identity is None
    assert "duplicate-required-evidence:device.identity.model" in projected.reasons

    for changed in (
        _claim(
            claims[0].claim_key,
            claims[0].structured_value,
            state=EvidenceState.UNCONFIRMED,
        ),
        _claim(
            claims[0].claim_key,
            claims[0].structured_value,
            freshness=EvidenceFreshness.STALE,
        ),
    ):
        altered = (changed, *claims[1:])
        projected = project_canonical_device_identity(_report(altered), altered)
        assert projected.identity is None
        assert "required-evidence-not-active:device.identity.manufacturer" in projected.reasons


def test_non_identity_wrong_domain_and_unsupported_keys_never_project():
    claims = _base_claims(marketing=False)
    non_identity = _claim("device.identity.codename", "popsicle", kind=ClaimKind.DIAGNOSTIC)
    altered = (*claims[:2], non_identity)
    projected = project_canonical_device_identity(_report(altered), altered)
    assert projected.identity is None
    assert "non-identity-claim:device.identity.codename" in projected.reasons

    wrong_domains = {claim.claim_id: KEY_DOMAINS[claim.claim_key] for claim in claims}
    wrong_domains[claims[1].claim_id] = ClaimAuthorityDomain.DEVICE_IDENTITY
    projected = project_canonical_device_identity(_report(claims, domains=wrong_domains), claims)
    assert projected.identity is None
    assert "wrong-authority-domain:device.identity.model" in projected.reasons

    extra = _claim("device.identity.region", "China")
    all_claims = (*claims, extra)
    domains = {
        claim.claim_id: KEY_DOMAINS.get(claim.claim_key, ClaimAuthorityDomain.DEVICE_IDENTITY)
        for claim in all_claims
    }
    projected = project_canonical_device_identity(_report(all_claims, domains=domains), all_claims)
    assert projected.identity is None
    assert "unsupported-claim-key:device.identity.region" in projected.reasons


def test_contradictions_conflicting_values_and_similar_scopes_remain_unconfirmed():
    one_sided_claims = _base_claims(marketing=False)
    one_sided = replace(one_sided_claims[2], conflicting_claim_ids=(one_sided_claims[1].claim_id,))
    with pytest.raises(EvidenceCorrelationError, match="both"):
        _report((*one_sided_claims[:2], one_sided))

    claims = list(_base_claims(marketing=False))
    other = _claim("device.identity.codename", "popsicle-pro")
    claims[2] = replace(claims[2], conflicting_claim_ids=(other.claim_id,))
    other = replace(other, conflicting_claim_ids=(claims[2].claim_id,))
    contradictory = (*claims, other)
    projected = project_canonical_device_identity(_report(contradictory), contradictory)
    assert projected.identity is None
    assert "duplicate-required-evidence:device.identity.codename" in projected.reasons
    assert "contradicted-required-evidence:device.identity.codename" in projected.reasons

    similar_scope = EvidenceScope(
        manufacturers=("Xiaomi",), models=("2509FPN0BC",), codenames=("popsicle-pro",)
    )
    changed = _claim("device.identity.codename", "popsicle", scope=similar_scope)
    scoped = (*_base_claims(marketing=False)[:2], changed)
    projected = project_canonical_device_identity(_report(scoped), scoped)
    assert projected.identity is None
    assert "conflicting-required-evidence-scope" in projected.reasons


@pytest.mark.parametrize(
    "unsafe",
    [
        "serial:ABC123",
        "imei:123456789012345",
        "account:user7",
        "username:steve",
        "password:secret",
        "token:secret",
        "/home/alice/device",
    ],
)
def test_private_identity_material_is_rejected(unsafe):
    claims = _base_claims(marketing=False)
    changed = replace(claims[0], structured_value=unsafe)
    with pytest.raises(EvidenceIdentityProjectionError, match="private"):
        project_canonical_device_identity(_report(claims), (changed, *claims[1:]))


def test_parser_rejects_extra_schema_digest_types_order_and_authority():
    projection = project_canonical_device_identity(_report(_base_claims()), _base_claims())
    raw = evidence_identity_projection_mapping(projection)
    variants = []
    extra = dict(raw)
    extra["extra"] = True
    variants.append(extra)
    schema = dict(raw)
    schema["schema_version"] = 2
    variants.append(schema)
    digest = dict(raw)
    digest["projection_digest"] = "0" * 64
    variants.append(digest)
    malformed = dict(raw)
    malformed["selected_claim_ids"] = "not-a-list"
    variants.append(malformed)
    reordered = json.loads(json.dumps(raw))
    reordered["selected_claim_ids"] = list(reversed(reordered["selected_claim_ids"]))
    variants.append(reordered)
    authority = dict(raw)
    authority["guardian_approval"] = True
    variants.append(authority)
    relock = dict(raw)
    relock["bootloader_relock_allowed"] = True
    variants.append(relock)
    for value in variants:
        with pytest.raises(EvidenceIdentityProjectionError):
            parse_evidence_identity_projection(value)


def test_parser_rejects_redigested_top_level_marketing_substitution():
    projection = project_canonical_device_identity(_report(_base_claims()), _base_claims())
    raw = evidence_identity_projection_mapping(projection)
    raw["marketing_names"] = ["Substituted retail name"]
    _reseal_projection(raw)

    with pytest.raises(EvidenceIdentityProjectionError, match="marketing metadata"):
        parse_evidence_identity_projection(raw)


def test_parser_rejects_every_redigested_projection_forbidden_identity_field():
    projection = project_canonical_device_identity(_report(_base_claims()), _base_claims())
    assert projection.identity is not None
    base = {
        "manufacturer": projection.identity.manufacturer,
        "brand": "",
        "model": projection.identity.model,
        "codename": projection.identity.codename,
        "region": "",
        "oem_identifiers": (),
        "soc": "",
        "platform": "",
        "marketing_names": projection.identity.marketing_names,
        "aliases": (),
        "family_ids": (),
        "evidence_claim_ids": projection.identity.evidence_claim_ids,
    }
    forbidden = (
        {"brand": "Xiaomi"},
        {"region": "China"},
        {"oem_identifiers": (("sku", "2509FPN0BC-CN"),)},
        {"aliases": ("17 Pro Max",)},
        {"family_ids": ("popsicle-family",)},
        {"soc": "sm8850"},
        {"platform": "qcom"},
    )
    for changed in forbidden:
        raw = evidence_identity_projection_mapping(projection)
        raw["identity"] = canonical_device_identity_mapping(
            create_canonical_device_identity(**(base | changed))
        )
        _reseal_projection(raw)
        with pytest.raises(EvidenceIdentityProjectionError, match="forbidden inferred"):
            parse_evidence_identity_projection(raw)


def test_conflicting_active_marketing_names_preserve_investigation_and_no_identity():
    required = _base_claims(marketing=False)
    first = _claim("device.identity.marketing-name", "Xiaomi 17 Pro Max")
    second = _claim("device.identity.marketing-name", "Xiaomi Popsicle Pro")
    first = replace(first, conflicting_claim_ids=(second.claim_id,))
    second = replace(second, conflicting_claim_ids=(first.claim_id,))
    claims = (*required, first, second)
    report = _report(claims)

    projected = project_canonical_device_identity(report, claims)

    assert report.requires_investigation
    assert projected.identity is None
    assert "explicit-contradiction" in projected.reasons
    assert "conflicting-active-values-or-scopes" in projected.reasons
    assert projected.marketing_names == ("Xiaomi 17 Pro Max", "Xiaomi Popsicle Pro")
