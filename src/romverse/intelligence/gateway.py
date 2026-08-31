from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from romverse.intelligence.governor import AIUsageGovernor


class IntelligenceRoute(StrEnum):
    DETERMINISTIC = "deterministic"
    SYNAPSE = "synapse"
    CACHE = "verified-cache"
    COMPATIBILITY = "compatibility-matrix"
    AI = "ai-provider"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class IntelligenceRequest:
    request_id: str
    task: str
    question: str
    context_digest: str
    estimated_tokens: int
    member_key: str

    @classmethod
    def create(
        cls,
        *,
        task: str,
        question: str,
        context_digest: str,
        estimated_tokens: int = 1_024,
        member_key: str = "anonymous",
    ) -> IntelligenceRequest:
        clean_task = _token(task, 100)
        clean_question = _privacy_scrub(question, 2_000)
        if not clean_task or not clean_question:
            raise ValueError("AI Gateway request is missing its bounded task or question")
        if _contains_credentials(question):
            raise ValueError("AI Gateway request contains credential-like content")
        return cls(
            uuid4().hex,
            clean_task,
            clean_question,
            _digest(context_digest, "context digest"),
            estimated_tokens,
            _token(member_key, 128),
        )


@dataclass(frozen=True, slots=True)
class IntelligenceEvidence:
    route: IntelligenceRoute
    summary: str
    confidence: int
    evidence_refs: tuple[str, ...]
    source_freshness: str
    source_scope: str
    corroborated: bool
    validated: bool


@dataclass(frozen=True, slots=True)
class AIProviderResponse:
    provider: str
    model: str
    summary: str
    evidence_refs: tuple[str, ...]
    confidence: int
    actual_tokens: int


@dataclass(frozen=True, slots=True)
class IntelligenceDecision:
    request_id: str
    route: IntelligenceRoute
    summary: str
    confidence: int
    evidence_refs: tuple[str, ...]
    provider: str = ""
    model: str = ""
    stopped_reason: str = ""
    evidence_validated: bool = False
    guardian_review_required: bool = True
    execution_authority: str = "guidance-only"
    bootloader_relock_allowed: bool = False


class EvidenceResolver(Protocol):
    route: IntelligenceRoute

    def resolve(self, request: IntelligenceRequest) -> IntelligenceEvidence | None: ...


class AIProvider(Protocol):
    """Server-side adapter boundary; clients never supply API keys."""

    name: str

    def reason(self, request: IntelligenceRequest) -> AIProviderResponse: ...


class AIGateway:
    """Provider-independent evidence router with no direct execution authority."""

    _ORDER = {
        IntelligenceRoute.DETERMINISTIC: 0,
        IntelligenceRoute.SYNAPSE: 1,
        IntelligenceRoute.CACHE: 2,
        IntelligenceRoute.COMPATIBILITY: 3,
    }

    def __init__(
        self,
        governor: AIUsageGovernor,
        *,
        resolvers: tuple[EvidenceResolver, ...] = (),
        provider: AIProvider | None = None,
    ) -> None:
        self.governor = governor
        self.resolvers = tuple(sorted(resolvers, key=lambda item: self._ORDER[item.route]))
        self.provider = provider

    def resolve(self, request: IntelligenceRequest) -> IntelligenceDecision:
        if not isinstance(request, IntelligenceRequest):
            raise TypeError("AI Gateway needs a validated IntelligenceRequest")
        for resolver in self.resolvers:
            evidence = resolver.resolve(request)
            if evidence is None:
                continue
            checked = _validated_evidence(evidence, resolver.route)
            if checked.validated and checked.confidence >= 70:
                return IntelligenceDecision(
                    request.request_id,
                    checked.route,
                    checked.summary,
                    checked.confidence,
                    checked.evidence_refs,
                    evidence_validated=True,
                )
        if self.provider is None:
            return self._stopped(
                request,
                "No configured server-side AI provider was available and existing evidence was insufficient.",
            )
        admission = self.governor.reserve(
            estimated_tokens=request.estimated_tokens,
            member_key=request.member_key,
        )
        if not admission.allowed:
            return self._stopped(request, admission.reason)
        try:
            response = _validated_provider_response(self.provider.reason(request))
            self.governor.release(admission.lease_id, actual_tokens=response.actual_tokens)
        except Exception:
            self.governor.release(admission.lease_id)
            raise
        return IntelligenceDecision(
            request.request_id,
            IntelligenceRoute.AI,
            response.summary,
            response.confidence,
            response.evidence_refs,
            provider=response.provider,
            model=response.model,
            evidence_validated=False,
        )

    @staticmethod
    def _stopped(request: IntelligenceRequest, reason: str) -> IntelligenceDecision:
        return IntelligenceDecision(
            request.request_id,
            IntelligenceRoute.STOPPED,
            "ROMVERSE stopped before proposing an unverified answer.",
            0,
            (),
            stopped_reason=_privacy_scrub(reason, 500),
            evidence_validated=False,
        )


def request_context_digest(value: object) -> str:
    """Create a stable context key without transmitting the underlying evidence."""

    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _validated_evidence(
    evidence: IntelligenceEvidence,
    expected_route: IntelligenceRoute,
) -> IntelligenceEvidence:
    if not isinstance(evidence, IntelligenceEvidence) or evidence.route is not expected_route:
        raise ValueError("Intelligence resolver returned evidence for the wrong route")
    if not 0 <= evidence.confidence <= 100:
        raise ValueError("Intelligence evidence confidence is invalid")
    return IntelligenceEvidence(
        evidence.route,
        _privacy_scrub(evidence.summary, 2_000),
        evidence.confidence,
        _evidence_refs(evidence.evidence_refs),
        _privacy_scrub(evidence.source_freshness, 120),
        _privacy_scrub(evidence.source_scope, 240),
        bool(evidence.corroborated),
        bool(evidence.validated),
    )


def _validated_provider_response(response: AIProviderResponse) -> AIProviderResponse:
    if not isinstance(response, AIProviderResponse):
        raise ValueError("AI provider returned an invalid response")
    provider = _token(response.provider, 80)
    model = _token(response.model, 120)
    if not provider or not model or not 0 <= response.confidence <= 100:
        raise ValueError("AI provider identity or confidence is invalid")
    if (
        isinstance(response.actual_tokens, bool)
        or not isinstance(response.actual_tokens, int)
        or not 0 <= response.actual_tokens <= 32_768
    ):
        raise ValueError("AI provider token usage is invalid")
    return AIProviderResponse(
        provider,
        model,
        _privacy_scrub(response.summary, 2_000),
        _evidence_refs(response.evidence_refs),
        response.confidence,
        response.actual_tokens,
    )


def _evidence_refs(values: object) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)) or len(values) > 20:
        raise ValueError("Intelligence evidence references are invalid")
    output = []
    for value in values:
        text = str(value or "").strip()
        if not text or len(text) > 400 or _contains_credentials(text):
            raise ValueError("Intelligence evidence reference is unsafe")
        output.append(text)
    return tuple(output)


def _privacy_scrub(value: object, maximum: int) -> str:
    text = str(value or "")
    text = re.sub(r"(?:/home|/Users)/[^\s/]+(?:/[^\s]+)*", "<path>", text)
    text = re.sub(r"\b[0-9a-f]{32,}\b", "<digest>", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()[:maximum]


def _contains_credentials(value: object) -> bool:
    return bool(
        re.search(
            r"\b(?:api[_-]?key|password|secret|bearer|access[_-]?token)\b\s*[:=]",
            str(value or ""),
            flags=re.I,
        )
    )


def _token(value: object, maximum: int) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", str(value or "").casefold()).strip("-")[:maximum]


def _digest(value: object, label: str) -> str:
    text = str(value or "").casefold().strip()
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise ValueError(f"AI Gateway {label} is invalid")
    return text
