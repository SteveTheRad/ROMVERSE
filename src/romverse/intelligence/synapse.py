from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4


class SynapseStoreError(RuntimeError):
    """Raised when the local Synapse evidence mirror cannot be trusted."""


class SynapseKnowledgeState(StrEnum):
    CANDIDATE = "candidate"
    VERIFIED_SUCCESS = "verified-success"
    STRONG = "strong-corroborated"
    TRUSTED = "trusted"
    RETIRED = "retired"


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
        phone_changed: bool = False,
    ) -> SynapseContribution:
        if phone_changed:
            raise ValueError("Synapse V1 accepts host/read-only verification outcomes only")
        if successful and not locally_verified:
            raise ValueError("A successful Synapse contribution needs local verification")
        return cls(
            contribution_id=uuid4().hex,
            recorded_at=datetime.now(UTC).isoformat(),
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
    execution_authority: str = "guidance-only"


@dataclass(frozen=True, slots=True)
class SynapseMatch:
    knowledge: SynapseKnowledge
    scope_match: str
    confidence: int
    explanation: str
    execution_authority: str = "guidance-only"


class SynapseStore:
    """Tamper-detecting local mirror of privacy-safe Synapse knowledge.

    This is the client-side evidence contract and cache. It does not claim that a
    production Synapse service exists, and it never grants execution authority.
    """

    FORMAT = "romverse.synapse-cache"
    SCHEMA_VERSION = 1
    MAX_CONTRIBUTIONS = 5_000

    def __init__(self, workspace: Path) -> None:
        self.path = workspace / "knowledge" / "synapse-cache-v1.json"

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
            for item in self._load()
            if item.fingerprint_id == fingerprint
            and item.solution_id == solution
            and item.scope.scope_digest == scope_id
        )
        if not matching:
            raise SynapseStoreError("No Synapse knowledge matches that exact scope")
        return _compile_knowledge(matching)

    def query(
        self,
        *,
        fingerprint_id: str,
        scope: SynapseScope,
        limit: int = 8,
    ) -> tuple[SynapseMatch, ...]:
        fingerprint = _digest(fingerprint_id, "fingerprint id")
        requested = _validated_scope(scope)
        grouped: dict[tuple[str, str], list[SynapseContribution]] = {}
        for item in self._load():
            if item.fingerprint_id != fingerprint:
                continue
            grouped.setdefault((item.solution_id, item.scope.scope_digest), []).append(item)
        matches = []
        for items in grouped.values():
            knowledge = _compile_knowledge(tuple(items))
            if knowledge.state is SynapseKnowledgeState.RETIRED:
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
        grouped: dict[tuple[str, str, str], list[SynapseContribution]] = {}
        for item in self._load():
            grouped.setdefault(
                (item.fingerprint_id, item.solution_id, item.scope.scope_digest), []
            ).append(item)
        state_rank = {
            SynapseKnowledgeState.TRUSTED: 0,
            SynapseKnowledgeState.STRONG: 1,
            SynapseKnowledgeState.VERIFIED_SUCCESS: 2,
            SynapseKnowledgeState.CANDIDATE: 3,
            SynapseKnowledgeState.RETIRED: 4,
        }
        compiled = tuple(_compile_knowledge(tuple(items)) for items in grouped.values())
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

    def _load(self) -> tuple[SynapseContribution, ...]:
        if not self.path.exists():
            return ()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
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
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise SynapseStoreError(f"Synapse cache is unreadable: {exc}") from exc

    def _save(self, contributions: tuple[SynapseContribution, ...]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = [asdict(item) for item in contributions]
        payload = {
            "format": self.FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "privacy": "redacted",
            "execution_authority": "guidance-only",
            "ledger_digest": _hexdigest(raw),
            "contributions": raw,
        }
        temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            raise SynapseStoreError(f"Could not preserve Synapse knowledge: {exc}") from exc
        finally:
            temporary.unlink(missing_ok=True)


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
    return SynapseKnowledge(
        knowledge_id=hashlib.sha256(_canonical(knowledge_key)).hexdigest(),
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
    return replace(
        contribution,
        contribution_id=_identifier(contribution.contribution_id, "contribution id"),
        recorded_at=_timestamp(contribution.recorded_at),
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
    text = re.sub(
        r"\b(?:token|password|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+",
        "<credential>",
        text,
        flags=re.I,
    )
    text = re.sub(r"\b[0-9a-f]{32,}\b", "<digest>", text, flags=re.I)
    text = re.sub(r"\b[A-Z0-9]{14,}\b", "<identifier>", text)
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
    return text


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _hexdigest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()
