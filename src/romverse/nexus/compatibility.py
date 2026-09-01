from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from romverse.device.dna import (
    CapabilityState,
    DeviceDnaEvidence,
    DeviceDnaProfile,
    DeviceDnaStore,
    EvidenceConfidence,
)
from romverse.infrastructure.local_store import atomic_write_json, read_json_object
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


class CompatibilityStatus(StrEnum):
    VERIFIED = "Verified"
    STRONG_MATCH = "Strong Match"
    LIMITED_EVIDENCE = "Limited Evidence"
    UNKNOWN = "Unknown"
    KNOWN_INCOMPATIBLE = "Known Incompatible"


class EvidenceFreshness(StrEnum):
    CURRENT = "current"
    AGING = "aging"
    STALE = "stale"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CompatibilityEvidence:
    evidence_id: str
    source_type: str
    source_ref: str
    detail: str
    confidence: EvidenceConfidence
    freshness: EvidenceFreshness
    scope: str


@dataclass(frozen=True, slots=True)
class CompatibilityDecision:
    capability_id: str
    label: str
    status: CompatibilityStatus
    confidence: EvidenceConfidence
    freshness: EvidenceFreshness
    scope: str
    summary: str
    technically_possible: bool
    proven_compatible: bool
    evidence: tuple[CompatibilityEvidence, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CompatibilityMatrix:
    schema_version: int
    matrix_id: str
    project_id: str
    device_dna_digest: str
    created_at: str
    decisions: tuple[CompatibilityDecision, ...]
    community_telemetry_used: bool
    guardian_advisory_only: bool
    bootloader_relock_permitted: bool
    matrix_digest: str

    def decision(self, capability_id: str) -> CompatibilityDecision | None:
        return next((item for item in self.decisions if item.capability_id == capability_id), None)


class CompatibilityMatrixStore:
    NAME = "compatibility-matrix.romverse"
    FORMAT = "romverse.compatibility-matrix"
    MAX_BYTES = 1024 * 1024

    def __init__(self, store: RomProjectStore) -> None:
        self.store = store

    def save(self, matrix: CompatibilityMatrix) -> CompatibilityMatrix:
        dna = DeviceDnaStore(self.store).load(matrix.project_id)
        if dna is None or dna.profile_digest != matrix.device_dna_digest:
            raise ProjectError("Compatibility Matrix is not bound to current Device DNA")
        if (
            matrix.community_telemetry_used
            or not matrix.guardian_advisory_only
            or matrix.bootloader_relock_permitted
        ):
            raise ProjectError("Compatibility Matrix safety or telemetry policy is invalid")
        matrix = _seal_matrix(matrix)
        if not _valid_matrix(matrix, dna):
            raise ProjectError("Compatibility Matrix metadata is invalid")
        existing = self.load(matrix.project_id)
        if existing is not None and _semantic(existing) == _semantic(matrix):
            return existing
        path = self.store.projects_root / matrix.project_id / self.NAME
        atomic_write_json(
            path,
            {"format": self.FORMAT, **asdict(matrix)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_BYTES,
        )
        return matrix

    def load(self, project_id: str) -> CompatibilityMatrix | None:
        try:
            self.store.get(project_id)
        except ProjectError:
            return None
        path = self.store.projects_root / project_id / self.NAME
        try:
            payload = read_json_object(
                path,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if (
                set(payload) != {"format", *(field.name for field in fields(CompatibilityMatrix))}
                or payload.pop("format") != self.FORMAT
                or not _valid_raw_matrix(payload)
            ):
                return None
            matrix = _from_mapping(payload)
            dna = DeviceDnaStore(self.store).load(project_id)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, ProjectError):
            return None
        if (
            dna is None
            or not _valid_matrix(matrix, dna)
            or matrix.project_id != project_id
            or matrix.device_dna_digest != dna.profile_digest
            or matrix.community_telemetry_used
            or not matrix.guardian_advisory_only
            or matrix.bootloader_relock_permitted
        ):
            return None
        return matrix


class CompatibilityMatrixService:
    """Derive conservative compatibility decisions from current persisted Device DNA."""

    def __init__(self, store: RomProjectStore) -> None:
        self.store = store
        self.matrices = CompatibilityMatrixStore(store)

    def assess(
        self,
        profile: DeviceDnaProfile,
        *,
        as_of: datetime | None = None,
    ) -> CompatibilityMatrix:
        persisted = DeviceDnaStore(self.store).load(profile.project_id)
        if persisted is None or persisted.profile_digest != profile.profile_digest:
            raise ProjectError("Compatibility Matrix requires current, trusted Device DNA")
        now = as_of or datetime.now(UTC)
        if now.tzinfo is None:
            raise ProjectError("Compatibility Matrix assessment time needs a timezone")
        profile_freshness = _freshness(profile.created_at, now)
        evidence = {item.evidence_id: item for item in profile.evidence}
        decisions = tuple(
            _decision(item, evidence, profile_freshness) for item in profile.capabilities
        )
        payload: dict[str, object] = {
            "schema_version": 2,
            "matrix_id": uuid4().hex,
            "project_id": profile.project_id,
            "device_dna_digest": profile.profile_digest,
            "created_at": now.astimezone(UTC).isoformat(),
            "decisions": decisions,
            "community_telemetry_used": False,
            "guardian_advisory_only": True,
            "bootloader_relock_permitted": False,
        }
        matrix = CompatibilityMatrix(**payload, matrix_digest=_digest(payload))  # type: ignore[arg-type]
        return self.matrices.save(matrix)


def _decision(
    capability,
    evidence_by_id: dict[str, DeviceDnaEvidence],
    freshness: EvidenceFreshness,
) -> CompatibilityDecision:
    sources = tuple(
        _source(evidence_by_id[evidence_id], freshness)
        for evidence_id in capability.evidence_ids
        if evidence_id in evidence_by_id
    )
    if capability.capability_id == "bootloader_relock":
        guardian = CompatibilityEvidence(
            "guardian.never-relock",
            "guardian-policy",
            "guardian/never-relock",
            "ROMVERSE never authorizes, recommends, or performs bootloader relocking.",
            EvidenceConfidence.VERIFIED,
            EvidenceFreshness.CURRENT,
            "all devices, projects, builds, and flash routes",
        )
        return CompatibilityDecision(
            capability.capability_id,
            capability.label,
            CompatibilityStatus.KNOWN_INCOMPATIBLE,
            EvidenceConfidence.VERIFIED,
            EvidenceFreshness.CURRENT,
            guardian.scope,
            capability.detail,
            False,
            False,
            (guardian,),
            ("Bootloader relocking is permanently prohibited.",),
        )

    status = _status(capability.state, sources)
    confidence = _confidence(status, sources)
    scope = " + ".join(dict.fromkeys(item.scope for item in sources)) or "unconfirmed scope"
    technically_possible = capability.state in {
        CapabilityState.SUPPORTED,
        CapabilityState.CAUTION,
    }
    proven = status is CompatibilityStatus.VERIFIED
    warnings = ()
    if status is CompatibilityStatus.STRONG_MATCH:
        warnings = ("Strong evidence is not the same as exact proven compatibility.",)
    elif status is CompatibilityStatus.LIMITED_EVIDENCE:
        warnings = ("A technically possible route still needs exact compatibility evidence.",)
    elif status is CompatibilityStatus.UNKNOWN:
        warnings = ("ROMVERSE has not found enough evidence and will not guess.",)
    elif status is CompatibilityStatus.KNOWN_INCOMPATIBLE:
        warnings = ("Known incompatibility blocks this capability; do not bypass Guardian.",)
    return CompatibilityDecision(
        capability.capability_id,
        capability.label,
        status,
        confidence,
        freshness if sources else EvidenceFreshness.UNKNOWN,
        scope,
        capability.detail,
        technically_possible,
        proven,
        sources,
        warnings,
    )


def _status(
    state: CapabilityState, sources: tuple[CompatibilityEvidence, ...]
) -> CompatibilityStatus:
    if state is CapabilityState.UNSUPPORTED:
        return CompatibilityStatus.KNOWN_INCOMPATIBLE
    if state is CapabilityState.UNCONFIRMED:
        return CompatibilityStatus.UNKNOWN
    if state is CapabilityState.CAUTION:
        return CompatibilityStatus.LIMITED_EVIDENCE
    exact = any(
        item.source_type == "device-pack"
        and item.confidence is EvidenceConfidence.VERIFIED
        and "exact protected firmware source" in item.scope
        for item in sources
    )
    if exact:
        return CompatibilityStatus.VERIFIED
    strong = len(sources) >= 2 and all(
        item.confidence in {EvidenceConfidence.VERIFIED, EvidenceConfidence.HIGH}
        for item in sources
    )
    return CompatibilityStatus.STRONG_MATCH if strong else CompatibilityStatus.LIMITED_EVIDENCE


def _confidence(
    status: CompatibilityStatus, sources: tuple[CompatibilityEvidence, ...]
) -> EvidenceConfidence:
    if status is CompatibilityStatus.VERIFIED:
        return EvidenceConfidence.VERIFIED
    if status is CompatibilityStatus.STRONG_MATCH:
        return EvidenceConfidence.HIGH
    if status is CompatibilityStatus.UNKNOWN or not sources:
        return EvidenceConfidence.UNCONFIRMED
    if any(item.confidence is EvidenceConfidence.HIGH for item in sources):
        return EvidenceConfidence.MEDIUM
    return EvidenceConfidence.LOW


def _source(evidence: DeviceDnaEvidence, freshness: EvidenceFreshness) -> CompatibilityEvidence:
    scope = {
        "protected-original-manifest": "exact protected firmware source",
        "bounded-filename-detection": "firmware filename and bounded package pattern",
        "file-signature-inspection": "exact protected firmware container",
        "device-identity-receipt": "connected device identity receipt",
        "live-adb-properties": "connected device read-only property snapshot",
        "device-pack": (
            "exact protected firmware source and Device Pack build contract"
            if evidence.confidence is EvidenceConfidence.VERIFIED
            else "reference-only Device Pack knowledge"
        ),
    }.get(evidence.source_type, "recorded Device DNA evidence")
    return CompatibilityEvidence(
        evidence.evidence_id,
        evidence.source_type,
        evidence.source_ref,
        evidence.detail,
        evidence.confidence,
        freshness,
        scope,
    )


def _freshness(created_at: str, as_of: datetime) -> EvidenceFreshness:
    try:
        created = datetime.fromisoformat(created_at)
    except ValueError:
        return EvidenceFreshness.UNKNOWN
    if created.tzinfo is None:
        return EvidenceFreshness.UNKNOWN
    days = max(0, (as_of.astimezone(UTC) - created.astimezone(UTC)).days)
    if days <= 30:
        return EvidenceFreshness.CURRENT
    if days <= 180:
        return EvidenceFreshness.AGING
    return EvidenceFreshness.STALE


def _seal_matrix(matrix: CompatibilityMatrix) -> CompatibilityMatrix:
    unsigned = replace(matrix, schema_version=2, matrix_digest="")
    payload = asdict(unsigned)
    payload.pop("matrix_digest")
    return replace(unsigned, matrix_digest=_digest(payload))


def _valid_matrix(matrix: CompatibilityMatrix, dna: DeviceDnaProfile) -> bool:
    if not isinstance(matrix, CompatibilityMatrix):
        return False
    try:
        assessed_at = datetime.fromisoformat(matrix.created_at)
    except ValueError:
        return False
    if assessed_at.tzinfo is None:
        return False
    evidence = {item.evidence_id: item for item in dna.evidence}
    expected_decisions = tuple(
        _decision(item, evidence, _freshness(dna.created_at, assessed_at))
        for item in dna.capabilities
    )
    decision_ids = tuple(item.capability_id for item in matrix.decisions)
    unsigned = asdict(matrix)
    digest = unsigned.pop("matrix_digest")
    return bool(
        type(matrix.schema_version) is int
        and matrix.schema_version in {1, 2}
        and _hex(matrix.matrix_id, 32)
        and bool(re.fullmatch(r"[a-z0-9-]{1,64}", matrix.project_id))
        and _hex(matrix.device_dna_digest, 64)
        and matrix.device_dna_digest == dna.profile_digest
        and _aware_timestamp(matrix.created_at)
        and isinstance(matrix.decisions, tuple)
        and 1 <= len(matrix.decisions) <= 32
        and len(decision_ids) == len(set(decision_ids))
        and all(_valid_decision(item) for item in matrix.decisions)
        and matrix.decisions == expected_decisions
        and matrix.community_telemetry_used is False
        and matrix.guardian_advisory_only is True
        and matrix.bootloader_relock_permitted is False
        and _hex(digest, 64)
        and digest == _digest(unsigned)
    )


def _valid_decision(decision: CompatibilityDecision) -> bool:
    return bool(
        isinstance(decision, CompatibilityDecision)
        and _identifier(decision.capability_id)
        and _valid_text(decision.label, 160)
        and isinstance(decision.status, CompatibilityStatus)
        and isinstance(decision.confidence, EvidenceConfidence)
        and isinstance(decision.freshness, EvidenceFreshness)
        and _valid_text(decision.scope, 1024)
        and _valid_text(decision.summary, 2048)
        and type(decision.technically_possible) is bool
        and type(decision.proven_compatible) is bool
        and isinstance(decision.evidence, tuple)
        and len(decision.evidence) <= 64
        and all(_valid_evidence(item) for item in decision.evidence)
        and isinstance(decision.warnings, tuple)
        and len(decision.warnings) <= 64
        and all(_valid_text(item, 1024) for item in decision.warnings)
    )


def _valid_evidence(evidence: CompatibilityEvidence) -> bool:
    return bool(
        isinstance(evidence, CompatibilityEvidence)
        and _identifier(evidence.evidence_id)
        and _valid_text(evidence.source_type, 160)
        and _valid_text(evidence.source_ref, 512)
        and _valid_text(evidence.detail, 2048)
        and isinstance(evidence.confidence, EvidenceConfidence)
        and isinstance(evidence.freshness, EvidenceFreshness)
        and _valid_text(evidence.scope, 1024)
    )


def _identifier(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", value))


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value))


def _aware_timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 80:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _valid_text(value: object, maximum: int) -> bool:
    return bool(
        isinstance(value, str)
        and 1 <= len(value) <= maximum
        and all(character.isprintable() or character == "\t" for character in value)
    )


def _semantic(matrix: CompatibilityMatrix) -> dict[str, object]:
    payload = asdict(matrix)
    for key in ("matrix_id", "created_at", "matrix_digest"):
        payload.pop(key, None)
    return payload


def _digest(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _json_default(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"Unsupported Compatibility Matrix value: {type(value).__name__}")


def _valid_raw_matrix(data: dict[str, object]) -> bool:
    decisions = data.get("decisions")
    return bool(
        type(data.get("schema_version")) is int
        and data.get("schema_version") in {1, 2}
        and all(
            isinstance(data.get(key), str)
            for key in (
                "matrix_id",
                "project_id",
                "device_dna_digest",
                "created_at",
                "matrix_digest",
            )
        )
        and isinstance(decisions, list)
        and 1 <= len(decisions) <= 32
        and all(_valid_raw_decision(item) for item in decisions)
        and type(data.get("community_telemetry_used")) is bool
        and type(data.get("guardian_advisory_only")) is bool
        and type(data.get("bootloader_relock_permitted")) is bool
    )


def _valid_raw_decision(item: object) -> bool:
    evidence_fields = {field.name for field in fields(CompatibilityEvidence)}
    return bool(
        isinstance(item, dict)
        and set(item) == {field.name for field in fields(CompatibilityDecision)}
        and all(
            isinstance(item.get(key), str)
            for key in (
                "capability_id",
                "label",
                "status",
                "confidence",
                "freshness",
                "scope",
                "summary",
            )
        )
        and type(item.get("technically_possible")) is bool
        and type(item.get("proven_compatible")) is bool
        and isinstance(item.get("evidence"), list)
        and len(item["evidence"]) <= 64
        and all(
            isinstance(value, dict)
            and set(value) == evidence_fields
            and all(isinstance(value.get(key), str) for key in evidence_fields)
            for value in item["evidence"]
        )
        and isinstance(item.get("warnings"), list)
        and len(item["warnings"]) <= 64
        and all(isinstance(value, str) for value in item["warnings"])
    )


def _from_mapping(data: dict[str, object]) -> CompatibilityMatrix:
    decisions = tuple(_decision_from_mapping(item) for item in _mapping_list(data.pop("decisions")))
    return CompatibilityMatrix(
        schema_version=data["schema_version"],  # type: ignore[arg-type]
        matrix_id=data["matrix_id"],  # type: ignore[arg-type]
        project_id=data["project_id"],  # type: ignore[arg-type]
        device_dna_digest=data["device_dna_digest"],  # type: ignore[arg-type]
        created_at=data["created_at"],  # type: ignore[arg-type]
        decisions=decisions,
        community_telemetry_used=data["community_telemetry_used"],  # type: ignore[arg-type]
        guardian_advisory_only=data["guardian_advisory_only"],  # type: ignore[arg-type]
        bootloader_relock_permitted=data["bootloader_relock_permitted"],  # type: ignore[arg-type]
        matrix_digest=data["matrix_digest"],  # type: ignore[arg-type]
    )


def _decision_from_mapping(item: dict[str, object]) -> CompatibilityDecision:
    evidence = tuple(
        _evidence_from_mapping(value) for value in _mapping_list(item.get("evidence", []))
    )
    return CompatibilityDecision(
        capability_id=item["capability_id"],  # type: ignore[arg-type]
        label=item["label"],  # type: ignore[arg-type]
        status=CompatibilityStatus(item["status"]),  # type: ignore[arg-type]
        confidence=EvidenceConfidence(item["confidence"]),  # type: ignore[arg-type]
        freshness=EvidenceFreshness(item["freshness"]),  # type: ignore[arg-type]
        scope=item["scope"],  # type: ignore[arg-type]
        summary=item["summary"],  # type: ignore[arg-type]
        technically_possible=item["technically_possible"],  # type: ignore[arg-type]
        proven_compatible=item["proven_compatible"],  # type: ignore[arg-type]
        evidence=evidence,
        warnings=tuple(item["warnings"]),  # type: ignore[arg-type]
    )


def _evidence_from_mapping(item: dict[str, object]) -> CompatibilityEvidence:
    return CompatibilityEvidence(
        evidence_id=item["evidence_id"],  # type: ignore[arg-type]
        source_type=item["source_type"],  # type: ignore[arg-type]
        source_ref=item["source_ref"],  # type: ignore[arg-type]
        detail=item["detail"],  # type: ignore[arg-type]
        confidence=EvidenceConfidence(item["confidence"]),  # type: ignore[arg-type]
        freshness=EvidenceFreshness(item["freshness"]),  # type: ignore[arg-type]
        scope=item["scope"],  # type: ignore[arg-type]
    )


def _mapping_list(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise TypeError("Compatibility Matrix entries must be a list of objects")
    return tuple(value)  # type: ignore[return-value]
