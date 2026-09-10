"""Pure projection of correlated research evidence into a canonical device identity."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, fields
from datetime import datetime

from romverse.device.identity import (
    CanonicalDeviceIdentity,
    CanonicalIdentityError,
    canonical_device_identity_mapping,
    create_canonical_device_identity,
    parse_canonical_device_identity,
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


class EvidenceIdentityProjectionError(ValueError):
    """Evidence projection input or a stored result failed closed."""


@dataclass(frozen=True, slots=True)
class EvidenceIdentityProjection:
    schema_version: int
    correlation_report_digest: str
    selected_claim_ids: tuple[str, ...]
    marketing_names: tuple[str, ...]
    identity: CanonicalDeviceIdentity | None
    reasons: tuple[str, ...]
    compatibility: str
    execution_authority: str
    phone_action_allowed: bool
    guardian_approval: bool
    bootloader_relock_allowed: bool
    projection_digest: str

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise EvidenceIdentityProjectionError("Identity projection schema is unsupported")
        if (
            self.compatibility != "UNCONFIRMED"
            or self.execution_authority != "none"
            or self.phone_action_allowed
            or self.guardian_approval
            or self.bootloader_relock_allowed
        ):
            raise EvidenceIdentityProjectionError("Identity projection cannot grant authority")
        if (self.identity is None) != bool(self.reasons):
            raise EvidenceIdentityProjectionError("Identity projection result is inconsistent")


_KEY_DOMAINS = {
    "device.identity.manufacturer": ClaimAuthorityDomain.DEVICE_IDENTITY,
    "device.identity.model": ClaimAuthorityDomain.MODEL_IDENTITY,
    "device.identity.codename": ClaimAuthorityDomain.CODENAME,
    "device.identity.marketing-name": ClaimAuthorityDomain.DEVICE_IDENTITY,
}
_REQUIRED_KEYS = (
    "device.identity.manufacturer",
    "device.identity.model",
    "device.identity.codename",
)
_TOKEN = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_PRIVATE_TEXT = re.compile(r"(?i)\b(?:password|secret|token|credential)\b")


def project_canonical_device_identity(
    report: EvidenceCorrelationReport,
    claims: tuple[OnlineEvidenceClaim, ...],
) -> EvidenceIdentityProjection:
    """Return one research-derived identity or a deterministic ``UNCONFIRMED`` result."""

    validated_report = _validated_report(report)
    claim_by_id = _validated_claims(claims)
    records = (*validated_report.active, *validated_report.retained)
    if set(claim_by_id) != {record.claim_id for record in records}:
        raise EvidenceIdentityProjectionError("Claims do not exactly bind the correlation report")

    active_by_key: dict[str, list[OnlineEvidenceClaim]] = {}
    active_records: dict[str, CorrelatedEvidence] = {}
    reasons: set[str] = set()
    for record in records:
        claim = claim_by_id[record.claim_id]
        _bind_record(record, claim)
        if claim.claim_key not in _KEY_DOMAINS:
            reasons.add(f"unsupported-claim-key:{claim.claim_key}")
            continue
        if claim.knowledge_kind is not ClaimKind.IDENTITY:
            reasons.add(f"non-identity-claim:{claim.claim_key}")
            continue
        if record.authority_domain is not _KEY_DOMAINS[claim.claim_key]:
            reasons.add(f"wrong-authority-domain:{claim.claim_key}")
            continue
        if record.use is not CorrelationUse.ACTIVE:
            if claim.claim_key in _REQUIRED_KEYS:
                reasons.add(f"required-evidence-not-active:{claim.claim_key}")
            continue
        active_by_key.setdefault(claim.claim_key, []).append(claim)
        active_records[claim.claim_id] = record

    required: dict[str, OnlineEvidenceClaim] = {}
    for key in _REQUIRED_KEYS:
        candidates = active_by_key.get(key, [])
        if not candidates:
            reasons.add(f"missing-required-evidence:{key}")
        elif len(candidates) != 1:
            reasons.add(f"duplicate-required-evidence:{key}")
        else:
            required[key] = candidates[0]
        if any(
            active_records[claim.claim_id].contradicting_claim_ids
            or "explicit-contradiction" in active_records[claim.claim_id].reasons
            for claim in candidates
        ):
            reasons.add(f"contradicted-required-evidence:{key}")

    if len(required) == len(_REQUIRED_KEYS):
        scopes = {claim.scope for claim in required.values()}
        if len(scopes) != 1:
            reasons.add("conflicting-required-evidence-scope")
        else:
            scope = next(iter(scopes))
            manufacturer = _claim_value(required[_REQUIRED_KEYS[0]])
            model = _claim_value(required[_REQUIRED_KEYS[1]])
            codename = _claim_value(required[_REQUIRED_KEYS[2]])
            if not _exact_singleton(scope.manufacturers, manufacturer):
                reasons.add("manufacturer-scope-not-exact")
            if not _exact_singleton(scope.models, model):
                reasons.add("model-scope-not-exact")
            if not _exact_singleton(scope.codenames, codename):
                reasons.add("codename-scope-not-exact")

    marketing_claims = active_by_key.get("device.identity.marketing-name", [])
    if required and marketing_claims:
        required_scope = next(iter(required.values())).scope
        if any(claim.scope != required_scope for claim in marketing_claims):
            reasons.add("marketing-name-scope-not-exact")
    marketing_names = tuple(sorted({_claim_value(claim) for claim in marketing_claims}))
    selected = tuple(
        sorted(
            claim.claim_id for claims_for_key in active_by_key.values() for claim in claims_for_key
        )
    )

    identity: CanonicalDeviceIdentity | None = None
    if not reasons:
        try:
            identity = create_canonical_device_identity(
                manufacturer=_claim_value(required[_REQUIRED_KEYS[0]]),
                brand="",
                model=_claim_value(required[_REQUIRED_KEYS[1]]),
                codename=_claim_value(required[_REQUIRED_KEYS[2]]),
                evidence_claim_ids=selected,
                marketing_names=marketing_names,
            )
        except CanonicalIdentityError as exc:
            reasons.add("canonical-identity-unconfirmed")
            if "private" in str(exc).casefold():
                raise EvidenceIdentityProjectionError(
                    "Identity projection contains privacy-unsafe evidence"
                ) from exc

    return _seal_projection(
        validated_report.report_digest,
        selected,
        marketing_names,
        identity,
        tuple(sorted(reasons)),
    )


def evidence_identity_projection_mapping(
    projection: EvidenceIdentityProjection,
) -> dict[str, object]:
    return {
        "schema_version": projection.schema_version,
        "correlation_report_digest": projection.correlation_report_digest,
        "selected_claim_ids": list(projection.selected_claim_ids),
        "marketing_names": list(projection.marketing_names),
        "identity": (
            canonical_device_identity_mapping(projection.identity)
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


def parse_evidence_identity_projection(raw: dict[str, object]) -> EvidenceIdentityProjection:
    expected = {field.name for field in fields(EvidenceIdentityProjection)}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise EvidenceIdentityProjectionError("Identity projection fields are invalid")
    if type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
        raise EvidenceIdentityProjectionError("Identity projection schema is unsupported")
    _zero_authority(raw)
    identity_raw = raw.get("identity")
    if identity_raw is not None and not isinstance(identity_raw, dict):
        raise EvidenceIdentityProjectionError("Projected canonical identity is malformed")
    try:
        identity = (
            parse_canonical_device_identity(identity_raw) if identity_raw is not None else None
        )
    except (CanonicalIdentityError, TypeError, ValueError) as exc:
        raise EvidenceIdentityProjectionError("Projected canonical identity is invalid") from exc
    selected = _stored_digests(raw.get("selected_claim_ids"))
    marketing = _stored_texts(raw.get("marketing_names"), 120)
    reasons = _stored_reasons(raw.get("reasons"))
    if identity is not None and identity.evidence_claim_ids != selected:
        raise EvidenceIdentityProjectionError("Projected identity claim binding is invalid")
    projection = EvidenceIdentityProjection(
        1,
        _digest(raw.get("correlation_report_digest")),
        selected,
        marketing,
        identity,
        reasons,
        "UNCONFIRMED",
        "none",
        False,
        False,
        False,
        _digest(raw.get("projection_digest")),
    )
    basis = evidence_identity_projection_mapping(projection)
    basis.pop("projection_digest")
    if projection.projection_digest != hashlib.sha256(_canonical(basis)).hexdigest():
        raise EvidenceIdentityProjectionError("Identity projection digest is invalid")
    if raw != json.loads(json.dumps(evidence_identity_projection_mapping(projection))):
        raise EvidenceIdentityProjectionError("Identity projection is not canonical")
    return projection


def _validated_report(report: EvidenceCorrelationReport) -> EvidenceCorrelationReport:
    if not isinstance(report, EvidenceCorrelationReport):
        raise EvidenceIdentityProjectionError("Correlation report is invalid")
    try:
        parsed = parse_evidence_correlation(evidence_correlation_mapping(report))
    except (EvidenceCorrelationError, TypeError, ValueError) as exc:
        raise EvidenceIdentityProjectionError("Correlation report is invalid") from exc
    if parsed != report:
        raise EvidenceIdentityProjectionError("Correlation report is not canonical")
    return parsed


def _validated_claims(claims: tuple[OnlineEvidenceClaim, ...]) -> dict[str, OnlineEvidenceClaim]:
    if not isinstance(claims, tuple) or len(claims) > 512:
        raise EvidenceIdentityProjectionError("Projection claims must be a bounded tuple")
    result: dict[str, OnlineEvidenceClaim] = {}
    for claim in claims:
        if not isinstance(claim, OnlineEvidenceClaim) or claim.claim_id in result:
            raise EvidenceIdentityProjectionError("Projection claims are invalid or duplicated")
        if (
            claim.execution_authority != "none"
            or claim.phone_action_allowed
            or claim.guardian_approval
        ):
            raise EvidenceIdentityProjectionError("Evidence claim cannot grant authority")
        _safe_text(claim.structured_value, 500)
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
        or (
            record.use is CorrelationUse.ACTIVE
            and claim.state
            in {
                EvidenceState.CONFLICTING,
                EvidenceState.UNCONFIRMED,
                EvidenceState.OUTDATED,
                EvidenceState.RETIRED,
            }
        )
    ):
        raise EvidenceIdentityProjectionError("Claim substitution or binding mismatch")


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
        raise EvidenceIdentityProjectionError("Evidence claim is invalid") from exc
    if rebuilt.claim_id != claim.claim_id:
        raise EvidenceIdentityProjectionError("Evidence claim identity is invalid")


def _claim_value(claim: OnlineEvidenceClaim) -> str:
    if not claim.structured_value or claim.supporting_excerpt:
        raise EvidenceIdentityProjectionError("Identity claim is not an exact structured value")
    return _safe_text(claim.structured_value, 500, required=True)


def _exact_singleton(values: tuple[str, ...], expected: str) -> bool:
    return len(values) == 1 and values[0].strip().casefold() == expected.strip().casefold()


def _seal_projection(
    report_digest: str,
    selected: tuple[str, ...],
    marketing: tuple[str, ...],
    identity: CanonicalDeviceIdentity | None,
    reasons: tuple[str, ...],
) -> EvidenceIdentityProjection:
    projection = EvidenceIdentityProjection(
        1,
        _digest(report_digest),
        tuple(sorted(set(selected))),
        tuple(sorted(set(marketing))),
        identity,
        tuple(sorted(set(reasons))),
        "UNCONFIRMED",
        "none",
        False,
        False,
        False,
        "",
    )
    basis = evidence_identity_projection_mapping(projection)
    basis.pop("projection_digest")
    return EvidenceIdentityProjection(
        projection.schema_version,
        projection.correlation_report_digest,
        projection.selected_claim_ids,
        projection.marketing_names,
        projection.identity,
        projection.reasons,
        projection.compatibility,
        projection.execution_authority,
        projection.phone_action_allowed,
        projection.guardian_approval,
        projection.bootloader_relock_allowed,
        hashlib.sha256(_canonical(basis)).hexdigest(),
    )


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
        raise EvidenceIdentityProjectionError("Identity projection cannot grant authority")


def _safe_text(value: object, maximum: int, *, required: bool = False) -> str:
    if not isinstance(value, str) or "\0" in value:
        raise EvidenceIdentityProjectionError("Identity evidence text is malformed")
    cleaned = " ".join(value.split())
    if len(cleaned) > maximum or (required and not cleaned):
        raise EvidenceIdentityProjectionError("Identity evidence text is invalid")
    if scrub_private_text(cleaned) != cleaned or _PRIVATE_TEXT.search(cleaned):
        raise EvidenceIdentityProjectionError("Identity evidence contains private data")
    return cleaned


def _stored_digests(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise EvidenceIdentityProjectionError("Projection claim IDs are invalid")
    result = tuple(_digest(item) for item in value)
    if result != tuple(sorted(set(result))):
        raise EvidenceIdentityProjectionError("Projection claim IDs are not canonical")
    return result


def _stored_texts(value: object, maximum: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 32:
        raise EvidenceIdentityProjectionError("Projection text collection is invalid")
    result = tuple(_safe_text(item, maximum, required=True) for item in value)
    if result != tuple(sorted(set(result))):
        raise EvidenceIdentityProjectionError("Projection text collection is not canonical")
    return result


def _stored_reasons(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise EvidenceIdentityProjectionError("Projection reasons are invalid")
    result = tuple(_reason(item) for item in value)
    if result != tuple(sorted(set(result))):
        raise EvidenceIdentityProjectionError("Projection reasons are not canonical")
    return result


def _reason(value: object) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise EvidenceIdentityProjectionError("Projection reason is invalid")
    return value


def _digest(value: object) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise EvidenceIdentityProjectionError("Projection digest is invalid")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")
