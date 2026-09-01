from __future__ import annotations

import pytest

from romverse.intelligence.gateway import (
    AIGateway,
    AIProviderResponse,
    IntelligenceEvidence,
    IntelligenceRequest,
    IntelligenceRoute,
    request_context_digest,
)
from romverse.intelligence.governor import AIGovernorPolicy, AIUsageGovernor


class Clock:
    def __init__(self) -> None:
        self.value = 1_800_000_000.0

    def __call__(self) -> float:
        return self.value


class Resolver:
    route = IntelligenceRoute.DETERMINISTIC

    def __init__(self, confidence: int = 92) -> None:
        self.confidence = confidence

    def resolve(self, _request):
        return IntelligenceEvidence(
            self.route,
            "A source-bound deterministic rule matched.",
            self.confidence,
            ("projects/project/device-dna.romverse",),
            "current",
            "exact firmware",
            True,
            True,
        )


class Provider:
    name = "server-provider"

    def __init__(self) -> None:
        self.calls = 0

    def reason(self, request):
        self.calls += 1
        assert not hasattr(request, "api_key")
        return AIProviderResponse(
            "openai",
            "reasoning-model",
            "A new hypothesis that still needs evidence validation.",
            ("https://source.android.com/docs/core/ota/ab",),
            71,
            300,
        )


def _request(tokens: int = 500) -> IntelligenceRequest:
    return IntelligenceRequest.create(
        task="diagnose-payload",
        question="Why did the source inspection stop?",
        context_digest=request_context_digest({"source": "payload.bin"}),
        estimated_tokens=tokens,
        member_key="member-anonymous-1",
    )


def test_gateway_prefers_validated_deterministic_evidence_without_using_ai() -> None:
    provider = Provider()
    gateway = AIGateway(
        AIUsageGovernor(),
        resolvers=(Resolver(),),
        provider=provider,
    )

    decision = gateway.resolve(_request())

    assert decision.route is IntelligenceRoute.DETERMINISTIC
    assert decision.evidence_validated
    assert decision.execution_authority == "guidance-only"
    assert decision.guardian_review_required
    assert not decision.bootloader_relock_allowed
    assert provider.calls == 0


def test_gateway_ai_output_remains_unvalidated_guidance() -> None:
    provider = Provider()
    governor = AIUsageGovernor()
    decision = AIGateway(governor, provider=provider).resolve(_request())

    assert decision.route is IntelligenceRoute.AI
    assert not decision.evidence_validated
    assert decision.guardian_review_required
    assert decision.execution_authority == "guidance-only"
    assert governor.active_requests == 0
    assert provider.calls == 1


def test_gateway_stops_when_no_evidence_or_provider_exists() -> None:
    decision = AIGateway(AIUsageGovernor()).resolve(_request())

    assert decision.route is IntelligenceRoute.STOPPED
    assert decision.confidence == 0
    assert "insufficient" in decision.stopped_reason


def test_governor_enforces_concurrency_fair_use_and_budget_without_weakening_safety() -> None:
    clock = Clock()
    governor = AIUsageGovernor(
        AIGovernorPolicy(
            daily_token_budget=1_000,
            maximum_request_tokens=500,
            maximum_concurrency=1,
            requests_per_minute=2,
            member_requests_per_minute=1,
        ),
        clock=clock,
    )
    first = governor.reserve(estimated_tokens=400, member_key="member-one")
    busy = governor.reserve(estimated_tokens=100, member_key="member-two")
    governor.release(first.lease_id, actual_tokens=300)
    fair_use = governor.reserve(estimated_tokens=100, member_key="member-one")
    clock.value += 61
    second = governor.reserve(estimated_tokens=500, member_key="member-one")
    governor.release(second.lease_id)
    exhausted = governor.reserve(estimated_tokens=500, member_key="member-two")

    assert first.allowed
    assert not busy.allowed and "stopped" in busy.reason
    assert not fair_use.allowed and "Fair-use" in fair_use.reason
    assert second.allowed
    assert not exhausted.allowed and "exhausted" in exhausted.reason


def test_gateway_rejects_credentials_before_provider_routing() -> None:
    with pytest.raises(ValueError, match="credential"):
        IntelligenceRequest.create(
            task="diagnose",
            question="api_key=do-not-send",
            context_digest="a" * 64,
        )
