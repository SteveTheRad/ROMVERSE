"""Pure projection of correlated evidence into a canonical firmware identity."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, fields
from datetime import datetime

from romverse.device.evidence_identity import (
    EvidenceIdentityProjection,
    EvidenceIdentityProjectionError,
    evidence_identity_projection_mapping,
    parse_evidence_identity_projection,
)
from romverse.knowledge.evidence_correlation import (
    CorrelatedEvidence,
    CorrelationUse,
    EvidenceCorrelationError,
    EvidenceCorrelationReport,
    evidence_correlation_mapping,
    parse_evidence_correlation,
)
from romverse.knowledge.online_evidence import (
    ClaimAuthorityDomain,
    ClaimKind,
    EvidenceLifecycleStatus,
    EvidenceState,
    OnlineEvidenceClaim,
    create_claim,
    scrub_private_text,
)
from romverse.rom.source_identity import (
    CanonicalFirmwareIdentity,
    CanonicalFirmwareIdentityError,
    canonical_firmware_identity_mapping,
    create_canonical_firmware_identity,
    parse_canonical_firmware_identity,
)


class EvidenceFirmwareProjectionError(ValueError):
    """Firmware projection input or a stored result failed closed."""


@dataclass(frozen=True, slots=True)
class FirmwareEvidenceBinding:
    claim_id: str
    source_id: str
    claim_key: str
    authority_domain: ClaimAuthorityDomain
    source_content_digest: str


@dataclass(frozen=True, slots=True)
class EvidenceFirmwareProjection:
    schema_version: int
    device_projection_digest: str
    canonical_device_id: str
    correlation_report_digest: str
    selected_claim_ids: tuple[str, ...]
    source_content_digests: tuple[str, ...]
    claim_bindings: tuple[FirmwareEvidenceBinding, ...]
    model_variant: str
    region: str
    build_id: str
    firmware_version: str
    android_version: str
    security_patch: str
    firmware_artifact_sha256: str
    partition_layout_digest: str
    identity: CanonicalFirmwareIdentity | None
    reasons: tuple[str, ...]
    compatibility: str
    execution_authority: str
    phone_action_allowed: bool
    guardian_approval: bool
    bootloader_relock_allowed: bool
    projection_digest: str

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise EvidenceFirmwareProjectionError("Firmware projection schema is unsupported")
        if (
            self.compatibility != "UNCONFIRMED"
            or self.execution_authority != "none"
            or self.phone_action_allowed
            or self.guardian_approval
            or self.bootloader_relock_allowed
        ):
            raise EvidenceFirmwareProjectionError("Firmware projection cannot grant authority")
        if (self.identity is None) != bool(self.reasons):
            raise EvidenceFirmwareProjectionError("Firmware projection result is inconsistent")


_BUILD_KEY = "firmware.build-identity"
_LAYOUT_KEY = "firmware.partition.layout"
_BUILD_FIELDS = (
    "android_version",
    "artifact_sha256",
    "build_id",
    "firmware_version",
    "model_variant",
    "region",
    "security_patch",
)
_UNUSABLE_STATES = {
    EvidenceState.CONFLICTING,
    EvidenceState.UNCONFIRMED,
    EvidenceState.OUTDATED,
    EvidenceState.RETIRED,
}
_TOKEN = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_PRIVATE_TEXT = re.compile(r"(?i)\b(?:password|secret|token|credential)\b")


def project_canonical_firmware_identity(
    device_projection: EvidenceIdentityProjection,
    report: EvidenceCorrelationReport,
    claims: tuple[OnlineEvidenceClaim, ...],
) -> EvidenceFirmwareProjection:
    """Return one firmware-derived identity or deterministic ``UNCONFIRMED`` evidence."""

    device = _validated_device_projection(device_projection)
    correlation = _validated_report(report)
    claim_by_id = _validated_claims(claims)
    records = (*correlation.active, *correlation.retained)
    if set(claim_by_id) != {record.claim_id for record in records}:
        raise EvidenceFirmwareProjectionError("Claims do not exactly bind the correlation report")

    reasons: set[str] = set(correlation.investigation_reasons)
    active_builds: list[OnlineEvidenceClaim] = []
    active_layouts: list[OnlineEvidenceClaim] = []
    active_records: dict[str, CorrelatedEvidence] = {}
    for record in records:
        claim = claim_by_id[record.claim_id]
        _bind_record(record, claim)
        expected_domain = {
            _BUILD_KEY: ClaimAuthorityDomain.FIRMWARE_IDENTITY,
            _LAYOUT_KEY: ClaimAuthorityDomain.PARTITION_LAYOUT,
        }.get(claim.claim_key)
        if expected_domain is None:
            reasons.add(f"unsupported-claim-key:{claim.claim_key}")
            continue
        if claim.knowledge_kind is not ClaimKind.IDENTITY:
            reasons.add(f"non-identity-claim:{claim.claim_key}")
            continue
        if record.authority_domain is not expected_domain:
            reasons.add(f"wrong-authority-domain:{claim.claim_key}")
            continue
        if record.use is not CorrelationUse.ACTIVE:
            reasons.add(f"evidence-not-active:{claim.claim_key}")
            continue
        active_records[claim.claim_id] = record
        if claim.claim_key == _BUILD_KEY:
            active_builds.append(claim)
        else:
            active_layouts.append(claim)

    if not active_builds:
        reasons.add("missing-required-evidence:firmware.build-identity")
    elif len(active_builds) > 1:
        reasons.add("duplicate-required-evidence:firmware.build-identity")
    if len(active_layouts) > 1:
        reasons.add("duplicate-evidence:firmware.partition.layout")

    for claim in (*active_builds, *active_layouts):
        record = active_records[claim.claim_id]
        if record.contradicting_claim_ids or "explicit-contradiction" in record.reasons:
            reasons.add(f"contradicted-evidence:{claim.claim_key}")

    metadata = {name: "" for name in _BUILD_FIELDS}
    if len(active_builds) == 1:
        metadata = _parse_build_metadata(active_builds[0].structured_value)
        reasons.update(_scope_reasons(active_builds[0], metadata, device))

    layout_digest = ""
    if len(active_layouts) == 1:
        layout_digest = _digest(active_layouts[0].structured_value)
        if len(active_builds) != 1 or active_layouts[0].scope != active_builds[0].scope:
            reasons.add("partition-layout-scope-not-exact")

    selected = tuple(sorted(claim.claim_id for claim in (*active_builds, *active_layouts)))
    source_digests = tuple(
        sorted({claim.source.content_digest for claim in (*active_builds, *active_layouts)})
    )
    bindings = tuple(
        sorted(
            (
                FirmwareEvidenceBinding(
                    claim.claim_id,
                    claim.source.source_id,
                    claim.claim_key,
                    active_records[claim.claim_id].authority_domain,
                    claim.source.content_digest,
                )
                for claim in (*active_builds, *active_layouts)
            ),
            key=lambda item: item.claim_id,
        )
    )
    artifact_digest = metadata["artifact_sha256"]
    if artifact_digest and artifact_digest in source_digests:
        reasons.add("firmware-artifact-substitutes-source-content")

    identity: CanonicalFirmwareIdentity | None = None
    if not reasons:
        try:
            identity = create_canonical_firmware_identity(
                canonical_device_id=device.identity.device_id,
                model_variant=metadata["model_variant"],
                region=metadata["region"],
                build_id=metadata["build_id"],
                firmware_version=metadata["firmware_version"],
                android_version=metadata["android_version"],
                security_patch=metadata["security_patch"],
                artifact_sha256=artifact_digest,
                partition_layout_digest=layout_digest,
                evidence_claim_ids=selected,
            )
        except CanonicalFirmwareIdentityError as exc:
            if "private" in str(exc).casefold():
                raise EvidenceFirmwareProjectionError(
                    "Firmware projection contains privacy-unsafe evidence"
                ) from exc
            reasons.add("canonical-firmware-identity-unconfirmed")

    return _seal_projection(
        device.projection_digest,
        device.identity.device_id,
        correlation.report_digest,
        selected,
        source_digests,
        bindings,
        metadata,
        layout_digest,
        identity,
        tuple(sorted(reasons)),
    )


def evidence_firmware_projection_mapping(
    projection: EvidenceFirmwareProjection,
) -> dict[str, object]:
    return {
        "schema_version": projection.schema_version,
        "device_projection_digest": projection.device_projection_digest,
        "canonical_device_id": projection.canonical_device_id,
        "correlation_report_digest": projection.correlation_report_digest,
        "selected_claim_ids": list(projection.selected_claim_ids),
        "source_content_digests": list(projection.source_content_digests),
        "claim_bindings": [_binding_mapping(item) for item in projection.claim_bindings],
        "model_variant": projection.model_variant,
        "region": projection.region,
        "build_id": projection.build_id,
        "firmware_version": projection.firmware_version,
        "android_version": projection.android_version,
        "security_patch": projection.security_patch,
        "firmware_artifact_sha256": projection.firmware_artifact_sha256,
        "partition_layout_digest": projection.partition_layout_digest,
        "identity": (
            canonical_firmware_identity_mapping(projection.identity)
            if projection.identity is not None
            else None
        ),
        "reasons": list(projection.reasons),
        "compatibility": projection.compatibility,
        "execution_authority": projection.execution_authority,
        "phone_action_allowed": projection.phone_action_allowed,
        "guardian_approval": projection.guardian_approval,
        "bootloader_relock_allowed": projection.bootloader_relock_allowed,
        "projection_digest": projection.projection_digest,
    }


def parse_evidence_firmware_projection(raw: dict[str, object]) -> EvidenceFirmwareProjection:
    expected = {field.name for field in fields(EvidenceFirmwareProjection)}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise EvidenceFirmwareProjectionError("Firmware projection fields are invalid")
    if type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
        raise EvidenceFirmwareProjectionError("Firmware projection schema is unsupported")
    _zero_authority(raw)
    identity_raw = raw.get("identity")
    if identity_raw is not None and not isinstance(identity_raw, dict):
        raise EvidenceFirmwareProjectionError("Projected firmware identity is malformed")
    try:
        identity = (
            parse_canonical_firmware_identity(identity_raw) if identity_raw is not None else None
        )
    except (CanonicalFirmwareIdentityError, TypeError, ValueError) as exc:
        raise EvidenceFirmwareProjectionError("Projected firmware identity is invalid") from exc

    selected = _stored_digests(raw.get("selected_claim_ids"), allow_empty=True)
    source_digests = _stored_digests(raw.get("source_content_digests"), allow_empty=True)
    bindings = _parse_bindings(raw.get("claim_bindings"))
    reasons = _stored_reasons(raw.get("reasons"))
    values = {
        "model_variant": _safe_text(raw.get("model_variant"), 120),
        "region": _safe_text(raw.get("region"), 80),
        "build_id": _safe_text(raw.get("build_id"), 160),
        "firmware_version": _safe_text(raw.get("firmware_version"), 120),
        "android_version": _safe_text(raw.get("android_version"), 40),
        "security_patch": _safe_text(raw.get("security_patch"), 40),
        "artifact_sha256": _optional_digest(raw.get("firmware_artifact_sha256")),
    }
    layout = _optional_digest(raw.get("partition_layout_digest"))
    canonical_device_id = _digest(raw.get("canonical_device_id"))
    if selected != tuple(item.claim_id for item in bindings) or source_digests != tuple(
        sorted({item.source_content_digest for item in bindings})
    ):
        raise EvidenceFirmwareProjectionError("Firmware claim bindings are inconsistent")
    _validate_binding_role_semantics(bindings, values, layout, reasons)
    substituted_source_digest = (
        bool(values["artifact_sha256"]) and values["artifact_sha256"] in source_digests
    )
    substitution_reason = "firmware-artifact-substitutes-source-content" in reasons
    if substituted_source_digest != substitution_reason or (
        substituted_source_digest and identity is not None
    ):
        raise EvidenceFirmwareProjectionError("Firmware artifact digest substitutes source content")
    if identity is not None:
        expected_values = (
            canonical_device_id,
            values["model_variant"],
            values["region"],
            values["build_id"],
            values["firmware_version"],
            values["android_version"],
            values["security_patch"],
            values["artifact_sha256"],
            layout,
            selected,
        )
        actual_values = (
            identity.canonical_device_id,
            identity.model_variant,
            identity.region,
            identity.build_id,
            identity.firmware_version,
            identity.android_version,
            identity.security_patch,
            identity.artifact_sha256,
            identity.partition_layout_digest,
            identity.evidence_claim_ids,
        )
        if actual_values != expected_values:
            raise EvidenceFirmwareProjectionError("Projected firmware semantics are inconsistent")
        if not source_digests:
            raise EvidenceFirmwareProjectionError("Projected firmware claim binding is invalid")

    projection = EvidenceFirmwareProjection(
        1,
        _digest(raw.get("device_projection_digest")),
        canonical_device_id,
        _digest(raw.get("correlation_report_digest")),
        selected,
        source_digests,
        bindings,
        values["model_variant"],
        values["region"],
        values["build_id"],
        values["firmware_version"],
        values["android_version"],
        values["security_patch"],
        values["artifact_sha256"],
        layout,
        identity,
        reasons,
        "UNCONFIRMED",
        "none",
        False,
        False,
        False,
        _digest(raw.get("projection_digest")),
    )
    basis = evidence_firmware_projection_mapping(projection)
    basis.pop("projection_digest")
    if projection.projection_digest != hashlib.sha256(_canonical(basis)).hexdigest():
        raise EvidenceFirmwareProjectionError("Firmware projection digest is invalid")
    if raw != json.loads(json.dumps(evidence_firmware_projection_mapping(projection))):
        raise EvidenceFirmwareProjectionError("Firmware projection is not canonical")
    return projection


def _validated_device_projection(
    projection: EvidenceIdentityProjection,
) -> EvidenceIdentityProjection:
    if not isinstance(projection, EvidenceIdentityProjection):
        raise EvidenceFirmwareProjectionError("Device projection is invalid")
    try:
        parsed = parse_evidence_identity_projection(
            evidence_identity_projection_mapping(projection)
        )
    except (EvidenceIdentityProjectionError, TypeError, ValueError) as exc:
        raise EvidenceFirmwareProjectionError("Device projection is invalid") from exc
    if parsed != projection or parsed.identity is None:
        raise EvidenceFirmwareProjectionError("A formed exact device projection is required")
    return parsed


def _validated_report(report: EvidenceCorrelationReport) -> EvidenceCorrelationReport:
    if not isinstance(report, EvidenceCorrelationReport):
        raise EvidenceFirmwareProjectionError("Correlation report is invalid")
    try:
        parsed = parse_evidence_correlation(evidence_correlation_mapping(report))
    except (EvidenceCorrelationError, TypeError, ValueError) as exc:
        raise EvidenceFirmwareProjectionError("Correlation report is invalid") from exc
    if parsed != report:
        raise EvidenceFirmwareProjectionError("Correlation report is not canonical")
    return parsed


def _validated_claims(claims: tuple[OnlineEvidenceClaim, ...]) -> dict[str, OnlineEvidenceClaim]:
    if not isinstance(claims, tuple) or not claims or len(claims) > 512:
        raise EvidenceFirmwareProjectionError("Firmware claims must be a bounded tuple")
    result: dict[str, OnlineEvidenceClaim] = {}
    for claim in claims:
        if not isinstance(claim, OnlineEvidenceClaim) or claim.claim_id in result:
            raise EvidenceFirmwareProjectionError("Firmware claims are invalid or duplicated")
        if (
            claim.execution_authority != "none"
            or claim.phone_action_allowed
            or claim.guardian_approval
        ):
            raise EvidenceFirmwareProjectionError("Firmware evidence cannot grant authority")
        _safe_text(claim.structured_value, 2_000)
        _safe_text(claim.supporting_excerpt, 800)
        for value in (
            *claim.scope.manufacturers,
            *claim.scope.brands,
            *claim.scope.models,
            *claim.scope.codenames,
            *claim.scope.build_ids,
            *claim.scope.firmware_versions,
            *claim.scope.android_versions,
            *claim.scope.regions,
            claim.scope.scope_note,
        ):
            _safe_text(value, 300)
        _validate_claim_identity(claim)
        result[claim.claim_id] = claim
    return result


def _bind_record(record: CorrelatedEvidence, claim: OnlineEvidenceClaim) -> None:
    if (
        record.claim_id != claim.claim_id
        or record.source_id != claim.source.source_id
        or record.claim_key != claim.claim_key
        or record.artifact_digest != claim.source.content_digest
        or record.supporting_claim_ids != claim.corroborating_claim_ids
        or record.contradicting_claim_ids != claim.conflicting_claim_ids
        or (
            record.use is CorrelationUse.ACTIVE
            and record.lifecycle_status is not EvidenceLifecycleStatus.ACTIVE
        )
        or (record.use is CorrelationUse.ACTIVE and claim.state in _UNUSABLE_STATES)
    ):
        raise EvidenceFirmwareProjectionError("Firmware claim substitution or binding mismatch")


def _validate_claim_identity(claim: OnlineEvidenceClaim) -> None:
    try:
        rebuilt = create_claim(
            claim_key=claim.claim_key,
            scope=claim.scope,
            source_id=claim.source.source_id,
            url=claim.source.url,
            publisher=claim.source.publisher,
            category=claim.source.category,
            retrieved_at=datetime.fromisoformat(claim.source.retrieved_at),
            published_at=(
                datetime.fromisoformat(claim.source.published_at)
                if claim.source.published_at
                else None
            ),
            freshness=claim.source.freshness,
            content_digest=claim.source.content_digest,
            parser_id=claim.source.parser_id,
            parser_version=claim.source.parser_version,
            structured_value=claim.structured_value,
            supporting_excerpt=claim.supporting_excerpt,
            state=claim.state,
            confidence=claim.confidence,
            status_reason=claim.status_reason,
            knowledge_kind=claim.knowledge_kind,
            symptoms=claim.symptoms,
            error_identifiers=claim.error_identifiers,
            prerequisites=claim.prerequisites,
            affected_builds=claim.affected_builds,
            diagnostic_description=claim.diagnostic_description,
            remedy_description=claim.remedy_description,
            expected_result=claim.expected_result,
            rollback_recovery_route=claim.rollback_recovery_route,
            outcome_provenance=claim.outcome_provenance,
        )
    except (TypeError, ValueError) as exc:
        raise EvidenceFirmwareProjectionError("Firmware evidence claim is invalid") from exc
    if rebuilt.claim_id != claim.claim_id:
        raise EvidenceFirmwareProjectionError("Firmware evidence claim identity is invalid")


def _parse_build_metadata(value: str) -> dict[str, str]:
    _safe_text(value, 2_000, required=True)
    try:
        raw = json.loads(value)
    except (json.JSONDecodeError, TypeError) as exc:
        raise EvidenceFirmwareProjectionError("Firmware build metadata is malformed") from exc
    if not isinstance(raw, dict) or tuple(sorted(raw)) != _BUILD_FIELDS:
        raise EvidenceFirmwareProjectionError("Firmware build metadata fields are invalid")
    limits = {
        "android_version": 40,
        "artifact_sha256": 64,
        "build_id": 160,
        "firmware_version": 120,
        "model_variant": 120,
        "region": 80,
        "security_patch": 40,
    }
    parsed = {name: _safe_text(raw[name], limits[name]) for name in _BUILD_FIELDS}
    parsed["artifact_sha256"] = _digest(parsed["artifact_sha256"])
    if not parsed["model_variant"] or not parsed["build_id"]:
        raise EvidenceFirmwareProjectionError("Required firmware build metadata is missing")
    if value != json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True):
        raise EvidenceFirmwareProjectionError("Firmware build metadata is not canonical JSON")
    return parsed


def _scope_reasons(
    claim: OnlineEvidenceClaim,
    metadata: dict[str, str],
    device: EvidenceIdentityProjection,
) -> set[str]:
    assert device.identity is not None
    scope = claim.scope
    reasons: set[str] = set()
    exact = (
        ("manufacturer", scope.manufacturers, device.identity.manufacturer),
        ("model", scope.models, metadata["model_variant"]),
        ("codename", scope.codenames, device.identity.codename),
        ("build", scope.build_ids, metadata["build_id"]),
    )
    for label, values, expected in exact:
        if values != (expected,):
            reasons.add(f"{label}-scope-not-exact")
    optional = (
        ("firmware-version", scope.firmware_versions, metadata["firmware_version"]),
        ("android-version", scope.android_versions, metadata["android_version"]),
        ("region", scope.regions, metadata["region"]),
    )
    for label, values, expected in optional:
        if values != ((expected,) if expected else ()):
            reasons.add(f"{label}-scope-not-exact")
    if metadata["model_variant"] != device.identity.model:
        reasons.add("model-device-binding-not-exact")
    if scope.brands or scope.scope_note:
        reasons.add("scope-contains-unbound-fields")
    return reasons


def _seal_projection(
    device_projection_digest: str,
    canonical_device_id: str,
    report_digest: str,
    selected: tuple[str, ...],
    source_digests: tuple[str, ...],
    bindings: tuple[FirmwareEvidenceBinding, ...],
    metadata: dict[str, str],
    layout: str,
    identity: CanonicalFirmwareIdentity | None,
    reasons: tuple[str, ...],
) -> EvidenceFirmwareProjection:
    values = (
        1,
        _digest(device_projection_digest),
        _digest(canonical_device_id),
        _digest(report_digest),
        tuple(sorted(set(selected))),
        tuple(sorted(set(source_digests))),
        bindings,
        metadata["model_variant"],
        metadata["region"],
        metadata["build_id"],
        metadata["firmware_version"],
        metadata["android_version"],
        metadata["security_patch"],
        metadata["artifact_sha256"],
        layout,
        identity,
        tuple(sorted(set(reasons))),
        "UNCONFIRMED",
        "none",
        False,
        False,
        False,
    )
    unsigned = EvidenceFirmwareProjection(*values, "")
    basis = evidence_firmware_projection_mapping(unsigned)
    basis.pop("projection_digest")
    return EvidenceFirmwareProjection(*values, hashlib.sha256(_canonical(basis)).hexdigest())


def _zero_authority(raw: dict[str, object]) -> None:
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
        raise EvidenceFirmwareProjectionError("Firmware projection cannot grant authority")


def _binding_mapping(binding: FirmwareEvidenceBinding) -> dict[str, object]:
    return {
        "claim_id": binding.claim_id,
        "source_id": binding.source_id,
        "claim_key": binding.claim_key,
        "authority_domain": binding.authority_domain.value,
        "source_content_digest": binding.source_content_digest,
    }


def _parse_bindings(value: object) -> tuple[FirmwareEvidenceBinding, ...]:
    if not isinstance(value, list) or len(value) > 512:
        raise EvidenceFirmwareProjectionError("Firmware evidence bindings are invalid")
    expected = {field.name for field in fields(FirmwareEvidenceBinding)}
    bindings: list[FirmwareEvidenceBinding] = []
    for raw in value:
        if not isinstance(raw, dict) or set(raw) != expected:
            raise EvidenceFirmwareProjectionError("Firmware evidence binding fields are invalid")
        claim_key = _token(raw.get("claim_key"))
        expected_domain = {
            _BUILD_KEY: ClaimAuthorityDomain.FIRMWARE_IDENTITY,
            _LAYOUT_KEY: ClaimAuthorityDomain.PARTITION_LAYOUT,
        }.get(claim_key)
        try:
            domain = ClaimAuthorityDomain(raw.get("authority_domain"))
        except (TypeError, ValueError) as exc:
            raise EvidenceFirmwareProjectionError(
                "Firmware evidence binding domain is invalid"
            ) from exc
        if expected_domain is None or domain is not expected_domain:
            raise EvidenceFirmwareProjectionError("Firmware evidence binding role is invalid")
        bindings.append(
            FirmwareEvidenceBinding(
                _digest(raw.get("claim_id")),
                _token(raw.get("source_id")),
                claim_key,
                domain,
                _digest(raw.get("source_content_digest")),
            )
        )
    ordered = tuple(sorted(bindings, key=lambda item: item.claim_id))
    if tuple(bindings) != ordered or len({item.claim_id for item in bindings}) != len(bindings):
        raise EvidenceFirmwareProjectionError("Firmware evidence bindings are not canonical")
    return ordered


def _validate_binding_role_semantics(
    bindings: tuple[FirmwareEvidenceBinding, ...],
    metadata: dict[str, str],
    layout: str,
    reasons: tuple[str, ...],
) -> None:
    build_count = sum(item.claim_key == _BUILD_KEY for item in bindings)
    layout_count = sum(item.claim_key == _LAYOUT_KEY for item in bindings)
    missing_build = "missing-required-evidence:firmware.build-identity" in reasons
    duplicate_build = "duplicate-required-evidence:firmware.build-identity" in reasons
    duplicate_layout = "duplicate-evidence:firmware.partition.layout" in reasons
    build_metadata_present = any(metadata.values())

    if build_count == 0:
        valid_build = not build_metadata_present and missing_build and not duplicate_build
    elif build_count == 1:
        valid_build = (
            bool(metadata["model_variant"])
            and bool(metadata["build_id"])
            and bool(metadata["artifact_sha256"])
            and not missing_build
            and not duplicate_build
        )
    else:
        valid_build = not build_metadata_present and duplicate_build and not missing_build
    if not valid_build:
        raise EvidenceFirmwareProjectionError("Firmware build binding semantics are inconsistent")

    if layout_count == 0:
        valid_layout = not layout and not duplicate_layout
    elif layout_count == 1:
        valid_layout = bool(layout) and not duplicate_layout
    else:
        valid_layout = not layout and duplicate_layout
    if not valid_layout:
        raise EvidenceFirmwareProjectionError("Firmware layout binding semantics are inconsistent")


def _stored_digests(value: object, *, allow_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise EvidenceFirmwareProjectionError("Firmware digest collection is invalid")
    result = tuple(_digest(item) for item in value)
    if (not allow_empty and not result) or result != tuple(sorted(set(result))):
        raise EvidenceFirmwareProjectionError("Firmware digest collection is not canonical")
    return result


def _stored_reasons(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise EvidenceFirmwareProjectionError("Firmware reasons are invalid")
    result = tuple(_reason(item) for item in value)
    if result != tuple(sorted(set(result))):
        raise EvidenceFirmwareProjectionError("Firmware reasons are not canonical")
    return result


def _reason(value: object) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise EvidenceFirmwareProjectionError("Firmware reason is invalid")
    return value


def _token(value: object) -> str:
    if (
        not isinstance(value, str)
        or not _TOKEN.fullmatch(value)
        or scrub_private_text(value) != value
    ):
        raise EvidenceFirmwareProjectionError("Firmware identifier is invalid")
    return value


def _safe_text(value: object, maximum: int, *, required: bool = False) -> str:
    if not isinstance(value, str) or "\0" in value:
        raise EvidenceFirmwareProjectionError("Firmware evidence text is malformed")
    cleaned = " ".join(value.split())
    if len(cleaned) > maximum or (required and not cleaned):
        raise EvidenceFirmwareProjectionError("Firmware evidence text is invalid")
    if scrub_private_text(cleaned) != cleaned or _PRIVATE_TEXT.search(cleaned):
        raise EvidenceFirmwareProjectionError("Firmware evidence contains private data")
    return cleaned


def _optional_digest(value: object) -> str:
    if value == "":
        return ""
    return _digest(value)


def _digest(value: object) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise EvidenceFirmwareProjectionError("Exact firmware digest is required")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")
