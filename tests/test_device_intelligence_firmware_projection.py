from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from romverse.device.evidence_firmware import (
    EvidenceFirmwareProjectionError,
    evidence_firmware_projection_mapping,
    parse_evidence_firmware_projection,
    project_canonical_firmware_identity,
)
from romverse.device.evidence_identity import project_canonical_device_identity
from romverse.knowledge.evidence_correlation import correlate_evidence
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
SOURCE_DIGEST = hashlib.sha256(b"official-firmware-index").hexdigest()
FIRMWARE_DIGEST = hashlib.sha256(b"firmware-artifact").hexdigest()
LAYOUT_DIGEST = hashlib.sha256(b"partition-layout").hexdigest()
DEVICE_SCOPE = EvidenceScope(
    manufacturers=("Xiaomi",), models=("2509FPN0BC",), codenames=("popsicle",)
)
FIRMWARE_SCOPE = EvidenceScope(
    manufacturers=("Xiaomi",),
    models=("2509FPN0BC",),
    codenames=("popsicle",),
    build_ids=("OS4.0.0.35.XPBCNXM",),
    firmware_versions=("4.0.0.35",),
    android_versions=("17",),
    regions=("China",),
)
BUILD_METADATA = {
    "android_version": "17",
    "artifact_sha256": FIRMWARE_DIGEST,
    "build_id": "OS4.0.0.35.XPBCNXM",
    "firmware_version": "4.0.0.35",
    "model_variant": "2509FPN0BC",
    "region": "China",
    "security_patch": "2026-08-01",
}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _claim(
    key,
    value,
    domain,
    *,
    scope=FIRMWARE_SCOPE,
    kind=ClaimKind.IDENTITY,
    freshness=EvidenceFreshness.CURRENT,
    state=EvidenceState.OFFICIALLY_DOCUMENTED,
    source_digest=SOURCE_DIGEST,
):
    claim = create_claim(
        claim_key=key,
        scope=scope,
        source_id="official.firmware.index",
        url="https://example.com/firmware",
        publisher="OEM",
        category=SourceCategory.OFFICIAL_FIRMWARE_INDEX,
        retrieved_at=NOW,
        content_digest=source_digest,
        parser_id="romverse.fixture",
        parser_version="1",
        structured_value=value,
        freshness=freshness,
        state=state,
        confidence=90,
        knowledge_kind=kind,
    )
    return claim, domain


def _report(items, *, statuses=None):
    statuses = statuses or {}
    claims = tuple(claim for claim, _domain in items)
    domains = {claim.claim_id: domain for claim, domain in items}
    authorities = tuple(
        create_claim_source_authority(
            source_id=claim.source.source_id,
            domains=(domain,),
            applicable_claim_keys=(claim.claim_key,),
            evidence_claim_ids=(claim.claim_id,),
        )
        for claim, domain in items
    )
    lifecycles = tuple(
        evidence_lifecycle_for_claim(
            claim,
            observed_at=NOW,
            status=statuses.get(claim.claim_id, EvidenceLifecycleStatus.ACTIVE),
        )
        for claim in claims
    )
    return correlate_evidence(claims, authorities, lifecycles, domains), claims


def _device_projection():
    items = (
        _claim(
            "device.identity.manufacturer",
            "Xiaomi",
            ClaimAuthorityDomain.DEVICE_IDENTITY,
            scope=DEVICE_SCOPE,
        ),
        _claim(
            "device.identity.model",
            "2509FPN0BC",
            ClaimAuthorityDomain.MODEL_IDENTITY,
            scope=DEVICE_SCOPE,
        ),
        _claim(
            "device.identity.codename",
            "popsicle",
            ClaimAuthorityDomain.CODENAME,
            scope=DEVICE_SCOPE,
        ),
    )
    report, claims = _report(items)
    return project_canonical_device_identity(report, claims)


def _build_item(metadata=None, **changes):
    return _claim(
        "firmware.build-identity",
        _json(metadata or BUILD_METADATA),
        ClaimAuthorityDomain.FIRMWARE_IDENTITY,
        **changes,
    )


def _layout_item(**changes):
    return _claim(
        "firmware.partition.layout",
        LAYOUT_DIGEST,
        ClaimAuthorityDomain.PARTITION_LAYOUT,
        **changes,
    )


def _project(items):
    report, claims = _report(items)
    return project_canonical_firmware_identity(_device_projection(), report, claims)


def _reseal(raw):
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


def test_exact_firmware_projection_is_deterministic_bound_and_strictly_parses():
    projection = _project((_build_item(), _layout_item()))
    reverse = _project((_layout_item(), _build_item()))

    assert projection == reverse
    assert projection.identity is not None
    assert projection.identity.canonical_device_id == _device_projection().identity.device_id
    assert projection.identity.artifact_sha256 == FIRMWARE_DIGEST
    assert projection.identity.partition_layout_digest == LAYOUT_DIGEST
    assert projection.identity.evidence_claim_ids == projection.selected_claim_ids
    assert projection.source_content_digests == (SOURCE_DIGEST,)
    assert FIRMWARE_DIGEST not in projection.source_content_digests
    assert projection.compatibility == "UNCONFIRMED"
    assert projection.execution_authority == "none"
    assert not projection.phone_action_allowed
    assert not projection.guardian_approval
    assert not projection.bootloader_relock_allowed
    assert (
        parse_evidence_firmware_projection(evidence_firmware_projection_mapping(projection))
        == projection
    )


def test_optional_metadata_and_layout_absence_remain_empty_without_inference():
    metadata = dict(BUILD_METADATA)
    for key in ("region", "firmware_version", "android_version", "security_patch"):
        metadata[key] = ""
    scope = replace(
        FIRMWARE_SCOPE,
        regions=(),
        firmware_versions=(),
        android_versions=(),
    )
    projection = _project((_build_item(metadata, scope=scope),))

    assert projection.identity is not None
    assert projection.region == projection.firmware_version == ""
    assert projection.android_version == projection.security_patch == ""
    assert projection.partition_layout_digest == ""


@pytest.mark.parametrize("missing", ["model_variant", "build_id", "artifact_sha256"])
def test_strict_build_json_requires_model_build_and_artifact_digest(missing):
    metadata = dict(BUILD_METADATA)
    metadata[missing] = ""
    with pytest.raises(EvidenceFirmwareProjectionError):
        _project((_build_item(metadata),))


def test_build_json_rejects_extra_fields_malformed_types_and_noncanonical_text():
    extra = dict(BUILD_METADATA)
    extra["extra"] = "value"
    malformed = dict(BUILD_METADATA)
    malformed["region"] = 7
    values = (_json(extra), _json(malformed), json.dumps(BUILD_METADATA, sort_keys=False))
    for value in values:
        with pytest.raises(EvidenceFirmwareProjectionError):
            _project(
                (
                    _claim(
                        "firmware.build-identity",
                        value,
                        ClaimAuthorityDomain.FIRMWARE_IDENTITY,
                    ),
                )
            )


def test_source_content_digest_cannot_substitute_for_firmware_artifact_digest():
    metadata = dict(BUILD_METADATA)
    metadata["artifact_sha256"] = SOURCE_DIGEST
    projection = _project((_build_item(metadata),))

    assert projection.identity is None
    assert "firmware-artifact-substitutes-source-content" in projection.reasons
    assert (
        parse_evidence_firmware_projection(evidence_firmware_projection_mapping(projection))
        == projection
    )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("manufacturers", ("xiaomi",), "manufacturer-scope-not-exact"),
        ("models", ("2509FPN0BG",), "model-scope-not-exact"),
        ("codenames", ("popsicle-pro",), "codename-scope-not-exact"),
        ("build_ids", ("OS4.0.0.36.XPBCNXM",), "build-scope-not-exact"),
        ("firmware_versions", (), "firmware-version-scope-not-exact"),
        ("android_versions", ("18",), "android-version-scope-not-exact"),
        ("regions", ("Global",), "region-scope-not-exact"),
    ],
)
def test_device_and_firmware_scope_must_match_field_for_field(field, value, reason):
    projection = _project((_build_item(scope=replace(FIRMWARE_SCOPE, **{field: value})),))
    assert projection.identity is None
    assert reason in projection.reasons


def test_adjacent_model_metadata_never_matches_projected_device():
    metadata = dict(BUILD_METADATA)
    metadata["model_variant"] = "2509FPN0BG"
    scope = replace(FIRMWARE_SCOPE, models=("2509FPN0BG",))
    projection = _project((_build_item(metadata, scope=scope),))

    assert projection.identity is None
    assert "model-device-binding-not-exact" in projection.reasons


def test_missing_duplicate_retained_stale_and_unconfirmed_build_evidence_fail_closed():
    layout = _layout_item()
    projection = _project((layout,))
    assert projection.identity is None
    assert "missing-required-evidence:firmware.build-identity" in projection.reasons

    second_metadata = dict(BUILD_METADATA)
    second_metadata["build_id"] = "OS4.0.0.36.XPBCNXM"
    second_scope = replace(FIRMWARE_SCOPE, build_ids=(second_metadata["build_id"],))
    projection = _project((_build_item(), _build_item(second_metadata, scope=second_scope)))
    assert projection.identity is None
    assert "duplicate-required-evidence:firmware.build-identity" in projection.reasons

    for status in (
        EvidenceLifecycleStatus.SUPERSEDED,
        EvidenceLifecycleStatus.QUARANTINED,
        EvidenceLifecycleStatus.EXPIRED,
    ):
        item = _build_item()
        report, claims = _report((item,), statuses={item[0].claim_id: status})
        projection = project_canonical_firmware_identity(_device_projection(), report, claims)
        assert projection.identity is None
        assert "evidence-not-active:firmware.build-identity" in projection.reasons

    for changed in (
        {"freshness": EvidenceFreshness.STALE},
        {"state": EvidenceState.UNCONFIRMED},
    ):
        projection = _project((_build_item(**changed),))
        assert projection.identity is None
        assert "evidence-not-active:firmware.build-identity" in projection.reasons


def test_unsupported_wrong_kind_and_wrong_domain_claims_are_unconfirmed():
    variants = (
        _claim(
            "firmware.unapproved",
            _json(BUILD_METADATA),
            ClaimAuthorityDomain.FIRMWARE_IDENTITY,
        ),
        _build_item(kind=ClaimKind.DIAGNOSTIC),
        _claim(
            "firmware.build-identity",
            _json(BUILD_METADATA),
            ClaimAuthorityDomain.PARTITION_LAYOUT,
        ),
    )
    expected = ("unsupported-claim-key", "non-identity-claim", "wrong-authority-domain")
    for item, reason in zip(variants, expected, strict=True):
        projection = _project((item,))
        assert projection.identity is None
        assert any(value.startswith(reason) for value in projection.reasons)


def test_contradiction_and_any_correlation_investigation_block_identity():
    first = _build_item()[0]
    changed_metadata = dict(BUILD_METADATA)
    changed_metadata["security_patch"] = "2026-09-01"
    second = _build_item(changed_metadata)[0]
    first = replace(first, conflicting_claim_ids=(second.claim_id,))
    second = replace(second, conflicting_claim_ids=(first.claim_id,))
    items = (
        (first, ClaimAuthorityDomain.FIRMWARE_IDENTITY),
        (second, ClaimAuthorityDomain.FIRMWARE_IDENTITY),
    )
    projection = _project(items)

    assert projection.identity is None
    assert "explicit-contradiction" in projection.reasons
    assert "conflicting-active-values-or-scopes" in projection.reasons


def test_partition_layout_requires_one_exact_same_scope_digest():
    wrong = _layout_item(scope=replace(FIRMWARE_SCOPE, regions=("Global",)))
    projection = _project((_build_item(), wrong))
    assert projection.identity is None
    assert "partition-layout-scope-not-exact" in projection.reasons

    duplicate = (
        _build_item(),
        _layout_item(),
        _claim(
            "firmware.partition.layout",
            hashlib.sha256(b"other-layout").hexdigest(),
            ClaimAuthorityDomain.PARTITION_LAYOUT,
        ),
    )
    projection = _project(duplicate)
    assert projection.identity is None
    assert "duplicate-evidence:firmware.partition.layout" in projection.reasons


def test_claim_report_and_device_projection_substitution_are_rejected():
    report, claims = _report((_build_item(),))
    changed = replace(claims[0], structured_value=_json(BUILD_METADATA | {"region": "Global"}))
    with pytest.raises(EvidenceFirmwareProjectionError):
        project_canonical_firmware_identity(_device_projection(), report, (changed,))
    with pytest.raises(EvidenceFirmwareProjectionError):
        project_canonical_firmware_identity(_device_projection(), report, ())
    with pytest.raises(EvidenceFirmwareProjectionError, match="Correlation report"):
        project_canonical_firmware_identity(
            _device_projection(), replace(report, report_digest="0" * 64), claims
        )
    device = replace(_device_projection(), projection_digest="0" * 64)
    with pytest.raises(EvidenceFirmwareProjectionError, match="Device projection"):
        project_canonical_firmware_identity(device, report, claims)


@pytest.mark.parametrize(
    "unsafe",
    ["serial:ABC123", "imei:123456789012345", "account:user7", "token:secret", "/home/a/x"],
)
def test_private_build_values_are_rejected(unsafe):
    metadata = dict(BUILD_METADATA)
    metadata["region"] = unsafe
    with pytest.raises(EvidenceFirmwareProjectionError):
        _project((_build_item(metadata),))


def test_stored_projection_rejects_schema_digest_order_authority_and_redigested_semantics():
    projection = _project((_build_item(), _layout_item()))
    raw = evidence_firmware_projection_mapping(projection)
    variants = []
    for field, value in (
        ("schema_version", 2),
        ("projection_digest", "0" * 64),
        ("selected_claim_ids", list(reversed(raw["selected_claim_ids"]))),
        ("guardian_approval", True),
        ("bootloader_relock_allowed", True),
    ):
        changed = json.loads(json.dumps(raw))
        changed[field] = value
        variants.append(changed)
    extra = json.loads(json.dumps(raw))
    extra["extra"] = True
    variants.append(extra)
    for changed in variants:
        with pytest.raises(EvidenceFirmwareProjectionError):
            parse_evidence_firmware_projection(changed)

    for field, value in (
        ("canonical_device_id", "a" * 64),
        ("build_id", "substituted-build"),
        ("firmware_artifact_sha256", "b" * 64),
        ("partition_layout_digest", "c" * 64),
    ):
        changed = json.loads(json.dumps(raw))
        changed[field] = value
        _reseal(changed)
        with pytest.raises(EvidenceFirmwareProjectionError, match="semantics"):
            parse_evidence_firmware_projection(changed)

    changed = json.loads(json.dumps(raw))
    changed["source_content_digests"] = ["d" * 64]
    _reseal(changed)
    with pytest.raises(EvidenceFirmwareProjectionError, match="bindings"):
        parse_evidence_firmware_projection(changed)


def test_stored_nested_firmware_substitution_rejects_even_after_both_digests_change():
    projection = _project((_build_item(),))
    raw = evidence_firmware_projection_mapping(projection)
    nested = dict(raw["identity"])
    nested["build_id"] = "substituted-build"
    basis = {
        "schema": "romverse.canonical-firmware-identity.v1",
        "canonical_device_id": nested["canonical_device_id"],
        "model_variant": nested["model_variant"].casefold(),
        "region": nested["region"].casefold(),
        "build_id": nested["build_id"].casefold(),
        "firmware_version": nested["firmware_version"].casefold(),
        "android_version": nested["android_version"].casefold(),
        "security_patch": nested["security_patch"].casefold(),
        "artifact_sha256": nested["artifact_sha256"],
        "partition_layout_digest": nested["partition_layout_digest"],
    }
    nested["firmware_id"] = hashlib.sha256(_json(basis).encode()).hexdigest()
    raw["identity"] = nested
    _reseal(raw)

    with pytest.raises(EvidenceFirmwareProjectionError, match="semantics"):
        parse_evidence_firmware_projection(raw)
