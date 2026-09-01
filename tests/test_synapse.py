from __future__ import annotations

import json

import pytest

from romverse.intelligence.synapse import (
    SynapseContribution,
    SynapseKnowledgeState,
    SynapseScope,
    SynapseStore,
    SynapseStoreError,
)


def _contribution(
    scope: SynapseScope,
    *,
    source: str,
    success: bool = True,
    drift: bool = False,
) -> SynapseContribution:
    return SynapseContribution.create(
        fingerprint_id="a" * 64,
        solution_id="inspect-payload-source",
        scope=scope,
        source_family=source,
        summary="Verified in /home/private/project without exposing token=private.",
        successful=success,
        locally_verified=True,
        action_receipt_digest="b" * 64,
        verification_evidence_digest="c" * 64,
        version_drift=drift,
    )


def test_synapse_promotes_only_independently_verified_exact_scope(tmp_path) -> None:
    store = SynapseStore(tmp_path)
    scope = SynapseScope.create(
        operation="payload extraction",
        source_kind="payload-bin",
        device_codename="popsicle",
        build_family="os4-xpbcnxm",
        tool_name="payload-dumper-go",
        tool_version="2.0.2",
    )

    one = store.contribute(_contribution(scope, source="official-aosp"))
    two = store.contribute(_contribution(scope, source="maintainer-tool"))
    three = store.contribute(_contribution(scope, source="official-aosp"))

    assert one.state is SynapseKnowledgeState.VERIFIED_SUCCESS
    assert two.state is SynapseKnowledgeState.STRONG
    assert three.state is SynapseKnowledgeState.TRUSTED
    assert three.execution_authority == "guidance-only"
    assert "private" not in three.summary
    assert store.query(fingerprint_id="a" * 64, scope=scope)[0].scope_match == "exact"


def test_synapse_version_drift_retires_knowledge_and_query_hides_it(tmp_path) -> None:
    store = SynapseStore(tmp_path)
    scope = SynapseScope.create(operation="avb inspection", tool_name="avbtool")
    store.contribute(_contribution(scope, source="aosp"))
    retired = store.contribute(_contribution(scope, source="aosp", success=False, drift=True))

    assert retired.state is SynapseKnowledgeState.RETIRED
    assert store.query(fingerprint_id="a" * 64, scope=scope) == ()


def test_synapse_bounded_scope_never_claims_exact_compatibility(tmp_path) -> None:
    store = SynapseStore(tmp_path)
    learned = SynapseScope.create(operation="source inspection", source_kind="ota-zip")
    requested = SynapseScope.create(
        operation="source inspection",
        source_kind="ota-zip",
        device_codename="popsicle",
    )
    store.contribute(_contribution(learned, source="aosp"))

    match = store.query(fingerprint_id="a" * 64, scope=requested)[0]

    assert match.scope_match == "bounded"
    assert match.confidence < match.knowledge.confidence
    assert "exact-device verification" in match.explanation


def test_synapse_lists_compiled_and_retired_local_knowledge_for_archives(tmp_path) -> None:
    store = SynapseStore(tmp_path)
    verified_scope = SynapseScope.create(
        operation="payload extraction",
        source_kind="payload-bin",
        device_codename="popsicle",
        tool_name="payload-dumper-go",
    )
    retired_scope = SynapseScope.create(operation="avb inspection", tool_name="avbtool")
    store.contribute(_contribution(verified_scope, source="official-aosp"))
    store.contribute(_contribution(verified_scope, source="maintainer-tool"))
    store.contribute(
        _contribution(retired_scope, source="official-aosp", success=False, drift=True)
    )

    knowledge = store.list_knowledge()

    assert [item.state for item in knowledge] == [
        SynapseKnowledgeState.STRONG,
        SynapseKnowledgeState.RETIRED,
    ]
    assert knowledge[0].successful_verifications == 2
    assert knowledge[1].failed_verifications == 1
    assert store.list_knowledge(limit=1) == knowledge[:1]
    assert store.list_knowledge(limit=0) == ()


def test_synapse_rejects_phone_changes_unverified_success_and_tampering(tmp_path) -> None:
    scope = SynapseScope.create(operation="inspect")
    common = dict(
        fingerprint_id="a" * 64,
        solution_id="inspect-source",
        scope=scope,
        source_family="official",
        summary="bounded",
        successful=True,
        locally_verified=True,
        action_receipt_digest="b" * 64,
        verification_evidence_digest="c" * 64,
    )
    with pytest.raises(ValueError, match="host/read-only"):
        SynapseContribution.create(**common, phone_changed=True)
    with pytest.raises(ValueError, match="local verification"):
        SynapseContribution.create(**{**common, "locally_verified": False})

    store = SynapseStore(tmp_path)
    store.contribute(SynapseContribution.create(**common))
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    payload["contributions"][0]["successful"] = False
    store.path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SynapseStoreError, match="modified"):
        store.query(fingerprint_id="a" * 64, scope=scope)
