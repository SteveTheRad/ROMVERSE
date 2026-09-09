from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_bytes,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)


class SynapseStoreError(RuntimeError):
    """Raised when the local Synapse evidence mirror cannot be trusted."""


class SynapseContributionEnvelopeError(RuntimeError):
    """Raised when a private Synapse review envelope cannot be trusted."""


class SynapseKnowledgeState(StrEnum):
    CANDIDATE = "candidate"
    VERIFIED_SUCCESS = "verified-success"
    STRONG = "strong-corroborated"
    TRUSTED = "trusted"
    QUARANTINED = "quarantined"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    RETIRED = "retired"


UNUSABLE_KNOWLEDGE_STATES = frozenset(
    {
        SynapseKnowledgeState.QUARANTINED,
        SynapseKnowledgeState.SUPERSEDED,
        SynapseKnowledgeState.EXPIRED,
        SynapseKnowledgeState.RETIRED,
    }
)


@dataclass(frozen=True, slots=True)
class SynapseScope:
    """Privacy-safe compatibility boundary for one solution family."""

    scope_digest: str
    operation: str
    source_kind: str = ""
    device_codename: str = ""
    build_family: str = ""
    tool_name: str = ""
    tool_version: str = ""

    @classmethod
    def create(
        cls,
        *,
        operation: str,
        source_kind: str = "",
        device_codename: str = "",
        build_family: str = "",
        tool_name: str = "",
        tool_version: str = "",
    ) -> SynapseScope:
        values = {
            "operation": _token(operation, 100, required=True),
            "source_kind": _token(source_kind, 80),
            "device_codename": _token(device_codename, 80),
            "build_family": _token(build_family, 120),
            "tool_name": _token(tool_name, 80),
            "tool_version": _token(tool_version, 80),
        }
        digest = hashlib.sha256(_canonical(values)).hexdigest()
        return cls(digest, **values)


@dataclass(frozen=True, slots=True)
class SynapseContribution:
    contribution_id: str
    recorded_at: str
    fingerprint_id: str
    solution_id: str
    scope: SynapseScope
    source_family: str
    summary: str
    successful: bool
    locally_verified: bool
    action_receipt_digest: str
    verification_evidence_digest: str
    version_drift: bool = False
    quarantined: bool = False
    supersedes_knowledge_id: str = ""
    expires_at: str = ""
    privacy: str = "redacted"
    phone_changed: bool = False

    @classmethod
    def create(
        cls,
        *,
        fingerprint_id: str,
        solution_id: str,
        scope: SynapseScope,
        source_family: str,
        summary: str,
        successful: bool,
        locally_verified: bool,
        action_receipt_digest: str,
        verification_evidence_digest: str,
        version_drift: bool = False,
        quarantined: bool = False,
        supersedes_knowledge_id: str = "",
        expires_at: str = "",
        phone_changed: bool = False,
    ) -> SynapseContribution:
        if phone_changed:
            raise ValueError("Synapse V1 accepts host/read-only verification outcomes only")
        if successful and not locally_verified:
            raise ValueError("A successful Synapse contribution needs local verification")
        recorded_at = datetime.now(UTC).isoformat()
        normalized_expiry = _timestamp(expires_at) if expires_at else ""
        if normalized_expiry and normalized_expiry < recorded_at:
            raise ValueError("Synapse expiry cannot precede its contribution")
        return cls(
            contribution_id=uuid4().hex,
            recorded_at=recorded_at,
            fingerprint_id=_digest(fingerprint_id, "fingerprint id"),
            solution_id=_identifier(solution_id, "solution id"),
            scope=_validated_scope(scope),
            source_family=_token(source_family, 100, required=True),
            summary=_privacy_scrub(summary, 500),
            successful=bool(successful),
            locally_verified=bool(locally_verified),
            action_receipt_digest=_digest(action_receipt_digest, "action receipt digest"),
            verification_evidence_digest=_digest(
                verification_evidence_digest, "verification evidence digest"
            ),
            version_drift=bool(version_drift),
            quarantined=bool(quarantined),
            supersedes_knowledge_id=(
                _digest(supersedes_knowledge_id, "superseded knowledge id")
                if supersedes_knowledge_id
                else ""
            ),
            expires_at=normalized_expiry,
            phone_changed=False,
        )


@dataclass(frozen=True, slots=True)
class SynapseKnowledge:
    knowledge_id: str
    fingerprint_id: str
    solution_id: str
    scope: SynapseScope
    state: SynapseKnowledgeState
    confidence: int
    successful_verifications: int
    failed_verifications: int
    independent_source_families: tuple[str, ...]
    last_observed_at: str
    last_verified_at: str
    summary: str
    contribution_digests: tuple[str, ...]
    supersedes_knowledge_id: str = ""
    expires_at: str = ""
    lifecycle_explanation: str = "active"
    execution_authority: str = "guidance-only"


@dataclass(frozen=True, slots=True)
class SynapseMatch:
    knowledge: SynapseKnowledge
    scope_match: str
    confidence: int
    explanation: str
    execution_authority: str = "guidance-only"


@dataclass(frozen=True, slots=True)
class SynapseContributionEnvelope:
    """Exact immutable bytes shown to the user before any future submission."""

    payload: bytes
    sha256: str
    envelope_digest: str
    record_count: int

    @property
    def preview(self) -> str:
        return self.payload.decode("utf-8")


@dataclass(frozen=True, slots=True)
class SynapseContributionEnvelopeExport:
    output_path: Path
    sha256: str
    envelope_digest: str
    size_bytes: int
    record_count: int


class SynapseContributionEnvelopeService:
    """Prepare transparent, local-only payloads for a later moderated service.

    The envelope deliberately excludes the local error fingerprint, knowledge ID,
    contribution IDs, action/evidence receipt digests, filesystem paths, device serials,
    credentials, and provider keys. Preparing or exporting it performs no network action.
    """

    FORMAT = "romverse.synapse.contribution-envelope"
    SCHEMA_VERSION = 1
    MAXIMUM_RECORDS = 64
    MAXIMUM_BYTES = 512 * 1024
    INCLUDED = (
        "bounded operation and compatibility scope",
        "redacted outcome summary",
        "aggregate verification counts and state",
        "source-family labels and observation times",
    )
    EXCLUDED = (
        "device serial, IMEI, account, and user content",
        "local paths, email addresses, credentials, and provider keys",
        "raw error fingerprint and full build fingerprint",
        "local knowledge, contribution, action, and evidence receipt identifiers",
        "firmware bytes, logs, command output, and phone data",
    )
    SUBMISSION_BOUNDARY = (
        "This file is a private preview, not a submission. A production service must "
        "show these exact bytes again and require a separate explicit send choice."
    )

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.output_dir = workspace / "knowledge" / "contribution-previews"

    def prepare(
        self,
        knowledge: SynapseKnowledge | tuple[SynapseKnowledge, ...],
    ) -> SynapseContributionEnvelope:
        records = (knowledge,) if isinstance(knowledge, SynapseKnowledge) else knowledge
        if not records or len(records) > self.MAXIMUM_RECORDS:
            raise SynapseContributionEnvelopeError(
                "A contribution preview needs between 1 and 64 local knowledge records"
            )
        prepared_records = [self._record(item) for item in records]
        document: dict[str, object] = {
            "format": self.FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "status": "private-review-only",
            "prepared_at": datetime.now(UTC).isoformat(),
            "privacy": "redacted",
            "upload_authorized": False,
            "execution_authority": "guidance-only",
            "phone_action_allowed": False,
            "records": prepared_records,
            "privacy_manifest": {
                "included": list(self.INCLUDED),
                "excluded": list(self.EXCLUDED),
            },
            "submission_boundary": self.SUBMISSION_BOUNDARY,
        }
        envelope_digest = hashlib.sha256(_canonical(document)).hexdigest()
        document["envelope_digest"] = envelope_digest
        payload = (
            json.dumps(
                document,
                ensure_ascii=True,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        if len(payload) > self.MAXIMUM_BYTES:
            raise SynapseContributionEnvelopeError(
                "The redacted contribution preview exceeds its size boundary"
            )
        return SynapseContributionEnvelope(
            payload=payload,
            sha256=hashlib.sha256(payload).hexdigest(),
            envelope_digest=envelope_digest,
            record_count=len(prepared_records),
        )

    def export(
        self,
        envelope: SynapseContributionEnvelope,
    ) -> SynapseContributionEnvelopeExport:
        self._validate_envelope(envelope)
        output_path = self.output_dir / (f"synapse-review-{envelope.envelope_digest[:16]}.json")
        try:
            atomic_write_bytes(
                output_path,
                envelope.payload,
                boundary=self.workspace,
                maximum_bytes=self.MAXIMUM_BYTES,
            )
        except LocalStoreError as exc:
            raise SynapseContributionEnvelopeError(
                f"The private contribution preview could not be saved safely: {exc}"
            ) from exc
        return SynapseContributionEnvelopeExport(
            output_path=output_path,
            sha256=envelope.sha256,
            envelope_digest=envelope.envelope_digest,
            size_bytes=len(envelope.payload),
            record_count=envelope.record_count,
        )

    @staticmethod
    def _record(item: SynapseKnowledge) -> dict[str, object]:
        if not isinstance(item, SynapseKnowledge):
            raise SynapseContributionEnvelopeError("Local knowledge record is invalid")
        scope = _validated_scope(item.scope)
        try:
            state = SynapseKnowledgeState(item.state)
            confidence = int(item.confidence)
            successful = int(item.successful_verifications)
            failed = int(item.failed_verifications)
        except (TypeError, ValueError) as exc:
            raise SynapseContributionEnvelopeError(
                "Local knowledge state or verification counts are invalid"
            ) from exc
        if not 0 <= confidence <= 100 or not 0 <= successful <= 5_000 or not 0 <= failed <= 5_000:
            raise SynapseContributionEnvelopeError(
                "Local knowledge confidence or verification counts are invalid"
            )
        if item.execution_authority != "guidance-only":
            raise SynapseContributionEnvelopeError(
                "Local knowledge attempted to exceed guidance-only authority"
            )
        observed_at = _timestamp(item.last_observed_at)
        verified_at = _timestamp(item.last_verified_at) if item.last_verified_at else ""
        return {
            "solution": _identifier(item.solution_id, "solution id"),
            "scope": {
                "operation": scope.operation,
                "source_kind": scope.source_kind,
                "device_codename": scope.device_codename,
                "build_family": scope.build_family,
                "tool_name": scope.tool_name,
                "tool_version": scope.tool_version,
            },
            "outcome": {
                "state": state.value,
                "confidence": confidence,
                "successful_verifications": successful,
                "failed_or_drifted_verifications": failed,
                "summary": _privacy_scrub(item.summary, 500),
                "independent_source_families": [
                    _token(source, 100, required=True)
                    for source in item.independent_source_families[:64]
                ],
                "last_observed_at": observed_at,
                "last_verified_at": verified_at,
            },
        }

    def _validate_envelope(self, envelope: SynapseContributionEnvelope) -> None:
        if not isinstance(envelope, SynapseContributionEnvelope):
            raise SynapseContributionEnvelopeError("Contribution preview is invalid")
        if not 0 < len(envelope.payload) <= self.MAXIMUM_BYTES:
            raise SynapseContributionEnvelopeError("Contribution preview size is invalid")
        if not hmac.compare_digest(envelope.sha256, hashlib.sha256(envelope.payload).hexdigest()):
            raise SynapseContributionEnvelopeError("Contribution preview bytes changed")
        try:
            document = json.loads(envelope.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SynapseContributionEnvelopeError("Contribution preview is unreadable") from exc
        if not isinstance(document, dict):
            raise SynapseContributionEnvelopeError("Contribution preview must be an object")
        claimed = document.pop("envelope_digest", None)
        actual = hashlib.sha256(_canonical(document)).hexdigest()
        expected_fields = {
            "format",
            "schema_version",
            "status",
            "prepared_at",
            "privacy",
            "upload_authorized",
            "execution_authority",
            "phone_action_allowed",
            "records",
            "privacy_manifest",
            "submission_boundary",
        }
        if (
            set(document) != expected_fields
            or document.get("format") != self.FORMAT
            or document.get("schema_version") != self.SCHEMA_VERSION
            or document.get("status") != "private-review-only"
            or document.get("privacy") != "redacted"
            or document.get("upload_authorized") is not False
            or document.get("execution_authority") != "guidance-only"
            or document.get("phone_action_allowed") is not False
            or not hmac.compare_digest(str(claimed or ""), envelope.envelope_digest)
            or not hmac.compare_digest(str(claimed or ""), actual)
        ):
            raise SynapseContributionEnvelopeError(
                "Contribution preview boundary or digest is invalid"
            )
        try:
            _timestamp(document.get("prepared_at"))
        except (TypeError, ValueError) as exc:
            raise SynapseContributionEnvelopeError(
                "Contribution preview timestamp is invalid"
            ) from exc
        if (
            document.get("privacy_manifest")
            != {
                "included": list(self.INCLUDED),
                "excluded": list(self.EXCLUDED),
            }
            or document.get("submission_boundary") != self.SUBMISSION_BOUNDARY
        ):
            raise SynapseContributionEnvelopeError("Contribution preview privacy manifest changed")
        records = document.get("records")
        if (
            not isinstance(records, list)
            or not 0 < len(records) <= self.MAXIMUM_RECORDS
            or len(records) != envelope.record_count
        ):
            raise SynapseContributionEnvelopeError("Contribution preview record count changed")
        for record in records:
            self._validate_record(record)

    @staticmethod
    def _validate_record(record: object) -> None:
        if not isinstance(record, dict) or set(record) != {"solution", "scope", "outcome"}:
            raise SynapseContributionEnvelopeError("Contribution preview record shape is invalid")
        scope = record.get("scope")
        outcome = record.get("outcome")
        scope_fields = {
            "operation",
            "source_kind",
            "device_codename",
            "build_family",
            "tool_name",
            "tool_version",
        }
        outcome_fields = {
            "state",
            "confidence",
            "successful_verifications",
            "failed_or_drifted_verifications",
            "summary",
            "independent_source_families",
            "last_observed_at",
            "last_verified_at",
        }
        if (
            not isinstance(scope, dict)
            or set(scope) != scope_fields
            or not isinstance(outcome, dict)
            or set(outcome) != outcome_fields
        ):
            raise SynapseContributionEnvelopeError(
                "Contribution preview scope or outcome shape is invalid"
            )
        try:
            _identifier(record.get("solution"), "solution id")
            rebuilt_scope = SynapseScope.create(**scope)
            SynapseKnowledgeState(outcome.get("state"))
            confidence = int(outcome.get("confidence"))
            successful = int(outcome.get("successful_verifications"))
            failed = int(outcome.get("failed_or_drifted_verifications"))
            observed_at = _timestamp(outcome.get("last_observed_at"))
            verified_value = outcome.get("last_verified_at")
            verified_at = _timestamp(verified_value) if verified_value else ""
        except (TypeError, ValueError) as exc:
            raise SynapseContributionEnvelopeError(
                "Contribution preview evidence fields are invalid"
            ) from exc
        if asdict(rebuilt_scope) != {"scope_digest": rebuilt_scope.scope_digest, **scope}:
            raise SynapseContributionEnvelopeError(
                "Contribution preview scope normalization changed"
            )
        if (
            not 0 <= confidence <= 100
            or not 0 <= successful <= 5_000
            or not 0 <= failed <= 5_000
            or observed_at != outcome.get("last_observed_at")
            or verified_at != outcome.get("last_verified_at")
        ):
            raise SynapseContributionEnvelopeError(
                "Contribution preview outcome boundaries are invalid"
            )
        summary = outcome.get("summary")
        if not isinstance(summary, str) or _privacy_scrub(summary, 500) != summary:
            raise SynapseContributionEnvelopeError(
                "Contribution preview summary is not fully redacted"
            )
        sources = outcome.get("independent_source_families")
        if (
            not isinstance(sources, list)
            or len(sources) > 64
            or any(
                not isinstance(source, str) or _token(source, 100, required=True) != source
                for source in sources
            )
        ):
            raise SynapseContributionEnvelopeError(
                "Contribution preview source families are invalid"
            )


class SynapseStore:
    """Tamper-detecting local mirror of privacy-safe Synapse knowledge.

    This is the client-side evidence contract and cache. It does not claim that a
    production Synapse service exists, and it never grants execution authority.
    """

    FORMAT = "romverse.synapse-cache"
    SCHEMA_VERSION = 1
    MAX_CONTRIBUTIONS = 5_000
    MAX_CACHE_BYTES = 4 * 1024 * 1024

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.path = self.workspace / "knowledge" / "synapse-cache-v1.json"

    def contribute(self, contribution: SynapseContribution) -> SynapseKnowledge:
        validated = _validated_contribution(contribution)
        contributions = list(self._load())
        if any(item.contribution_id == validated.contribution_id for item in contributions):
            raise SynapseStoreError("Synapse contribution identifier already exists")
        contributions.append(validated)
        contributions = contributions[-self.MAX_CONTRIBUTIONS :]
        self._save(tuple(contributions))
        return self.knowledge_for(
            validated.fingerprint_id,
            validated.solution_id,
            validated.scope.scope_digest,
        )

    def knowledge_for(
        self,
        fingerprint_id: str,
        solution_id: str,
        scope_digest: str,
    ) -> SynapseKnowledge:
        fingerprint = _digest(fingerprint_id, "fingerprint id")
        solution = _identifier(solution_id, "solution id")
        scope_id = _digest(scope_digest, "scope digest")
        matching = tuple(
            item
            for item in self._compiled_knowledge()
            if item.fingerprint_id == fingerprint
            and item.solution_id == solution
            and item.scope.scope_digest == scope_id
        )
        if not matching:
            raise SynapseStoreError("No Synapse knowledge matches that exact scope")
        return matching[0]

    def query(
        self,
        *,
        fingerprint_id: str,
        scope: SynapseScope,
        limit: int = 8,
    ) -> tuple[SynapseMatch, ...]:
        fingerprint = _digest(fingerprint_id, "fingerprint id")
        requested = _validated_scope(scope)
        matches = []
        for knowledge in self._compiled_knowledge():
            if knowledge.fingerprint_id != fingerprint:
                continue
            if knowledge.state in UNUSABLE_KNOWLEDGE_STATES:
                continue
            scope_match = _scope_match(requested, knowledge.scope)
            if scope_match == "incompatible":
                continue
            penalty = 0 if scope_match == "exact" else 24
            confidence = max(0, knowledge.confidence - penalty)
            if confidence < 30:
                continue
            explanation = (
                "Exact privacy-safe device, firmware, operation, and tool scope matched."
                if scope_match == "exact"
                else "Only a bounded compatible scope matched; exact-device verification remains required."
            )
            matches.append(SynapseMatch(knowledge, scope_match, confidence, explanation))
        bounded = max(0, min(int(limit), 20))
        return tuple(
            sorted(
                matches,
                key=lambda item: (
                    item.scope_match != "exact",
                    -item.confidence,
                    item.knowledge.solution_id,
                ),
            )[:bounded]
        )

    def list_knowledge(self, *, limit: int = 256) -> tuple[SynapseKnowledge, ...]:
        """Compile the bounded local evidence bank for read-only Archives inspection.

        Retired records remain visible here so Archives can explain why an older learned
        outcome must not be reused. Query-based automation continues to exclude them.
        """

        bounded = max(0, min(int(limit), 256))
        if not bounded:
            return ()
        state_rank = {
            SynapseKnowledgeState.TRUSTED: 0,
            SynapseKnowledgeState.STRONG: 1,
            SynapseKnowledgeState.VERIFIED_SUCCESS: 2,
            SynapseKnowledgeState.CANDIDATE: 3,
            SynapseKnowledgeState.QUARANTINED: 4,
            SynapseKnowledgeState.SUPERSEDED: 5,
            SynapseKnowledgeState.EXPIRED: 6,
            SynapseKnowledgeState.RETIRED: 7,
        }
        compiled = self._compiled_knowledge()
        return tuple(
            sorted(
                compiled,
                key=lambda item: (
                    state_rank[item.state],
                    -item.confidence,
                    item.scope.operation,
                    item.solution_id,
                    item.knowledge_id,
                ),
            )[:bounded]
        )

    def _compiled_knowledge(self) -> tuple[SynapseKnowledge, ...]:
        grouped: dict[tuple[str, str, str], list[SynapseContribution]] = {}
        for item in self._load():
            grouped.setdefault(
                (item.fingerprint_id, item.solution_id, item.scope.scope_digest), []
            ).append(item)
        compiled = tuple(_compile_knowledge(tuple(items)) for items in grouped.values())
        active_superseder_sets: dict[str, set[str]] = {}
        for item in compiled:
            if item.supersedes_knowledge_id and item.state not in UNUSABLE_KNOWLEDGE_STATES:
                active_superseder_sets.setdefault(item.supersedes_knowledge_id, set()).add(
                    item.knowledge_id
                )
        active_superseders = {
            target: min(replacements) for target, replacements in active_superseder_sets.items()
        }
        return tuple(
            replace(
                item,
                state=SynapseKnowledgeState.SUPERSEDED,
                confidence=0,
                lifecycle_explanation=(
                    f"Superseded by guidance record {active_superseders[item.knowledge_id]}."
                ),
            )
            if item.knowledge_id in active_superseders
            else item
            for item in compiled
        )

    def _load(self) -> tuple[SynapseContribution, ...]:
        if not self.path.exists() and not self.path.is_symlink():
            return ()
        try:
            payload = read_json_object(
                self.path,
                boundary=self.workspace,
                maximum_bytes=self.MAX_CACHE_BYTES,
            )
            raw = payload["contributions"]
            if (
                payload.get("format") != self.FORMAT
                or payload.get("schema_version") != self.SCHEMA_VERSION
                or payload.get("privacy") != "redacted"
                or not isinstance(raw, list)
                or len(raw) > self.MAX_CONTRIBUTIONS
                or payload.get("ledger_digest") != _hexdigest(raw)
            ):
                raise ValueError("unsupported or modified Synapse cache")
            contributions = tuple(
                _validated_contribution(
                    SynapseContribution(
                        **{
                            **item,
                            "scope": SynapseScope(**item["scope"]),
                        }
                    )
                )
                for item in raw
            )
            if len({item.contribution_id for item in contributions}) != len(contributions):
                raise ValueError("duplicate Synapse contribution identifiers")
            return contributions
        except (LocalStoreError, OSError, ValueError, TypeError, KeyError) as exc:
            raise SynapseStoreError(f"Synapse cache is unreadable: {exc}") from exc

    def _save(self, contributions: tuple[SynapseContribution, ...]) -> None:
        raw = [asdict(item) for item in contributions]
        payload = {
            "format": self.FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "privacy": "redacted",
            "execution_authority": "guidance-only",
            "ledger_digest": _hexdigest(raw),
            "contributions": raw,
        }
        try:
            self.workspace.mkdir(parents=True, exist_ok=True)
            ensure_private_directory(self.workspace, boundary=self.workspace)
            ensure_private_directory(self.path.parent, boundary=self.workspace)
            atomic_write_json(
                self.path,
                payload,
                boundary=self.workspace,
                maximum_bytes=self.MAX_CACHE_BYTES,
            )
        except (LocalStoreError, OSError) as exc:
            raise SynapseStoreError(f"Could not preserve Synapse knowledge: {exc}") from exc


def _compile_knowledge(
    contributions: tuple[SynapseContribution, ...],
) -> SynapseKnowledge:
    ordered = tuple(sorted(contributions, key=lambda item: item.recorded_at))
    first = ordered[0]
    successes = tuple(
        item
        for item in ordered
        if item.successful and item.locally_verified and not item.version_drift
    )
    failures = tuple(item for item in ordered if not item.successful or item.version_drift)
    sources = tuple(sorted({item.source_family for item in successes}))
    state = SynapseKnowledgeState.CANDIDATE
    if successes:
        state = SynapseKnowledgeState.VERIFIED_SUCCESS
    if len(successes) >= 2 and len(sources) >= 2 and not failures:
        state = SynapseKnowledgeState.STRONG
    if len(successes) >= 3 and len(sources) >= 2 and not failures:
        state = SynapseKnowledgeState.TRUSTED
    if failures:
        if len(failures) >= max(2, len(successes)) or any(item.version_drift for item in failures):
            state = SynapseKnowledgeState.RETIRED
        elif state is SynapseKnowledgeState.TRUSTED:
            state = SynapseKnowledgeState.STRONG
        elif state is SynapseKnowledgeState.STRONG:
            state = SynapseKnowledgeState.VERIFIED_SUCCESS
        else:
            state = SynapseKnowledgeState.CANDIDATE
    base = {
        SynapseKnowledgeState.CANDIDATE: 28,
        SynapseKnowledgeState.VERIFIED_SUCCESS: 62,
        SynapseKnowledgeState.STRONG: 82,
        SynapseKnowledgeState.TRUSTED: 94,
        SynapseKnowledgeState.RETIRED: 0,
    }[state]
    confidence = max(0, min(100, base + min(4, len(successes)) - 6 * len(failures)))
    summary_source = successes[-1] if successes else ordered[-1]
    last_verified = successes[-1].recorded_at if successes else ""
    digests = tuple(_hexdigest(asdict(item)) for item in ordered)
    knowledge_key = {
        "fingerprint_id": first.fingerprint_id,
        "solution_id": first.solution_id,
        "scope_digest": first.scope.scope_digest,
    }
    knowledge_id = hashlib.sha256(_canonical(knowledge_key)).hexdigest()
    quarantine = any(item.quarantined for item in ordered)
    supersession_targets = {
        item.supersedes_knowledge_id for item in ordered if item.supersedes_knowledge_id
    }
    if len(supersession_targets) > 1:
        quarantine = True
    supersedes = next(iter(supersession_targets), "")
    if supersedes == knowledge_id:
        quarantine = True
    expiries = tuple(item.expires_at for item in ordered if item.expires_at)
    expiry = min(expiries, default="")
    lifecycle_explanation = "Active guidance-only evidence."
    if quarantine:
        state = SynapseKnowledgeState.QUARANTINED
        lifecycle_explanation = "Quarantined evidence is retained for Archives review."
    elif expiry and expiry <= datetime.now(UTC).isoformat():
        state = SynapseKnowledgeState.EXPIRED
        lifecycle_explanation = "Expired evidence is retained for Archives review."
    if state in UNUSABLE_KNOWLEDGE_STATES:
        confidence = 0
    return SynapseKnowledge(
        knowledge_id=knowledge_id,
        fingerprint_id=first.fingerprint_id,
        solution_id=first.solution_id,
        scope=first.scope,
        state=state,
        confidence=confidence,
        successful_verifications=len(successes),
        failed_verifications=len(failures),
        independent_source_families=sources,
        last_observed_at=ordered[-1].recorded_at,
        last_verified_at=last_verified,
        summary=summary_source.summary,
        contribution_digests=digests,
        supersedes_knowledge_id=supersedes,
        expires_at=expiry,
        lifecycle_explanation=lifecycle_explanation,
    )


def _validated_scope(scope: SynapseScope) -> SynapseScope:
    if not isinstance(scope, SynapseScope):
        raise ValueError("Synapse scope is invalid")
    rebuilt = SynapseScope.create(
        operation=scope.operation,
        source_kind=scope.source_kind,
        device_codename=scope.device_codename,
        build_family=scope.build_family,
        tool_name=scope.tool_name,
        tool_version=scope.tool_version,
    )
    if rebuilt != scope:
        raise ValueError("Synapse scope digest does not match its evidence")
    return scope


def _validated_contribution(contribution: SynapseContribution) -> SynapseContribution:
    if not isinstance(contribution, SynapseContribution):
        raise ValueError("Synapse contribution is invalid")
    if contribution.privacy != "redacted" or contribution.phone_changed:
        raise ValueError("Synapse contribution violates the privacy/safety boundary")
    if contribution.successful and not contribution.locally_verified:
        raise ValueError("Unverified outcomes cannot be successful Synapse evidence")
    if not isinstance(contribution.quarantined, bool):
        raise ValueError("Synapse quarantine state is invalid")
    recorded_at = _timestamp(contribution.recorded_at)
    expires_at = _timestamp(contribution.expires_at) if contribution.expires_at else ""
    if expires_at and expires_at < recorded_at:
        raise ValueError("Synapse expiry cannot precede its contribution")
    return replace(
        contribution,
        contribution_id=_identifier(contribution.contribution_id, "contribution id"),
        recorded_at=recorded_at,
        supersedes_knowledge_id=(
            _digest(contribution.supersedes_knowledge_id, "superseded knowledge id")
            if contribution.supersedes_knowledge_id
            else ""
        ),
        expires_at=expires_at,
        fingerprint_id=_digest(contribution.fingerprint_id, "fingerprint id"),
        solution_id=_identifier(contribution.solution_id, "solution id"),
        scope=_validated_scope(contribution.scope),
        source_family=_token(contribution.source_family, 100, required=True),
        summary=_privacy_scrub(contribution.summary, 500),
        action_receipt_digest=_digest(contribution.action_receipt_digest, "action receipt digest"),
        verification_evidence_digest=_digest(
            contribution.verification_evidence_digest,
            "verification evidence digest",
        ),
    )


def _scope_match(requested: SynapseScope, candidate: SynapseScope) -> str:
    if requested.scope_digest == candidate.scope_digest:
        return "exact"
    if requested.operation != candidate.operation:
        return "incompatible"
    for name in ("source_kind", "device_codename", "build_family", "tool_name"):
        left = getattr(requested, name)
        right = getattr(candidate, name)
        if left and right and left != right:
            return "incompatible"
    if (
        requested.tool_version
        and candidate.tool_version
        and requested.tool_version != candidate.tool_version
    ):
        return "incompatible"
    return "bounded"


def _privacy_scrub(value: object, maximum: int) -> str:
    text = str(value or "")
    text = re.sub(r"(?:/home|/Users)/[^\s/]+(?:/[^\s]+)*", "<path>", text)
    text = re.sub(r"\b[A-Za-z]:\\(?:[^\s\\]+\\)*[^\s\\]*", "<path>", text)
    text = re.sub(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b", "<email>", text)
    text = re.sub(
        r"(?<![\d.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\."
        r"(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\d.])",
        "<ip-address>",
        text,
    )
    text = re.sub(
        r"\b(?:token|password|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+",
        "<credential>",
        text,
        flags=re.I,
    )
    text = re.sub(r"\b[0-9a-f]{32,}\b", "<digest>", text, flags=re.I)
    text = re.sub(
        r"\b(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{14,}\b", "<identifier>", text
    )
    return re.sub(r"\s+", " ", text).strip()[:maximum]


def _identifier(value: object, label: str) -> str:
    text = str(value or "").strip().casefold()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,127}", text):
        raise ValueError(f"Synapse {label} is invalid")
    return text


def _token(value: object, maximum: int, *, required: bool = False) -> str:
    text = re.sub(r"[^a-z0-9._-]+", "-", str(value or "").casefold()).strip("-")[:maximum]
    if required and not text:
        raise ValueError("A required Synapse scope value is missing")
    return text


def _digest(value: object, label: str) -> str:
    text = str(value or "").casefold().strip()
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise ValueError(f"Synapse {label} is invalid")
    return text


def _timestamp(value: object) -> str:
    text = str(value or "")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Synapse timestamp needs a timezone")
    return parsed.astimezone(UTC).isoformat()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _hexdigest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()
