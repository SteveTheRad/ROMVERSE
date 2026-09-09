from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import replace

import pytest

from romverse.intelligence.synapse import (
    SynapseContribution,
    SynapseContributionEnvelope,
    SynapseContributionEnvelopeError,
    SynapseContributionEnvelopeService,
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
    solution: str = "inspect-payload-source",
    quarantined: bool = False,
    supersedes: str = "",
    expires_at: str = "",
) -> SynapseContribution:
    return SynapseContribution.create(
        fingerprint_id="a" * 64,
        solution_id=solution,
        scope=scope,
        source_family=source,
        summary="Verified in /home/private/project without exposing token=private.",
        successful=success,
        locally_verified=True,
        action_receipt_digest="b" * 64,
        verification_evidence_digest="c" * 64,
        version_drift=drift,
        quarantined=quarantined,
        supersedes_knowledge_id=supersedes,
        expires_at=expires_at,
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


def test_synapse_quarantine_is_hidden_from_query_but_retained_for_archives(tmp_path) -> None:
    store = SynapseStore(tmp_path)
    scope = SynapseScope.create(operation="payload inspection")

    knowledge = store.contribute(_contribution(scope, source="official", quarantined=True))

    assert knowledge.state is SynapseKnowledgeState.QUARANTINED
    assert knowledge.confidence == 0
    assert knowledge.execution_authority == "guidance-only"
    assert store.query(fingerprint_id="a" * 64, scope=scope) == ()
    assert store.list_knowledge() == (knowledge,)
    assert "Archives" in knowledge.lifecycle_explanation


def test_synapse_expiry_is_hidden_from_query_but_retained_for_archives(tmp_path) -> None:
    store = SynapseStore(tmp_path)
    scope = SynapseScope.create(operation="payload inspection")
    expired = replace(
        _contribution(scope, source="official"),
        recorded_at="2025-01-01T00:00:00+00:00",
        expires_at="2025-01-02T00:00:00+00:00",
    )

    knowledge = store.contribute(expired)

    assert knowledge.state is SynapseKnowledgeState.EXPIRED
    assert knowledge.confidence == 0
    assert store.query(fingerprint_id="a" * 64, scope=scope) == ()
    assert store.list_knowledge() == (knowledge,)


def test_synapse_supersession_hides_only_exact_prior_knowledge(tmp_path) -> None:
    store = SynapseStore(tmp_path)
    scope = SynapseScope.create(operation="payload inspection")
    prior = store.contribute(
        _contribution(scope, source="official", solution="old-inspection-route")
    )

    current = store.contribute(
        _contribution(
            scope,
            source="maintainer",
            solution="current-inspection-route",
            supersedes=prior.knowledge_id,
        )
    )
    archived = {item.knowledge_id: item for item in store.list_knowledge()}

    assert current.state is SynapseKnowledgeState.VERIFIED_SUCCESS
    assert archived[prior.knowledge_id].state is SynapseKnowledgeState.SUPERSEDED
    assert archived[prior.knowledge_id].confidence == 0
    assert [
        item.knowledge.solution_id for item in store.query(fingerprint_id="a" * 64, scope=scope)
    ] == ["current-inspection-route"]


def test_synapse_self_supersession_quarantines_exact_record(tmp_path) -> None:
    store = SynapseStore(tmp_path)
    scope = SynapseScope.create(operation="payload inspection")
    first = store.contribute(_contribution(scope, source="official"))
    store.contribute(_contribution(scope, source="maintainer", supersedes=first.knowledge_id))

    knowledge = store.list_knowledge()[0]

    assert knowledge.state is SynapseKnowledgeState.QUARANTINED
    assert store.query(fingerprint_id="a" * 64, scope=scope) == ()


def test_synapse_lifecycle_fields_are_backward_compatible_and_chronological(tmp_path) -> None:
    store = SynapseStore(tmp_path)
    scope = SynapseScope.create(operation="payload inspection")
    store.contribute(_contribution(scope, source="official"))
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    legacy = payload["contributions"][0]
    legacy.pop("quarantined")
    legacy.pop("supersedes_knowledge_id")
    legacy.pop("expires_at")
    payload["ledger_digest"] = hashlib.sha256(
        json.dumps(payload["contributions"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    store.path.write_text(json.dumps(payload), encoding="utf-8")

    assert store.list_knowledge()[0].state is SynapseKnowledgeState.VERIFIED_SUCCESS

    invalid = replace(
        _contribution(scope, source="official"),
        recorded_at="2025-01-02T00:00:00+00:00",
        expires_at="2025-01-01T00:00:00+00:00",
    )
    with pytest.raises(ValueError, match="expiry cannot precede"):
        store.contribute(invalid)


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


def test_synapse_cache_is_private_and_rejects_symbolic_links(tmp_path) -> None:
    scope = SynapseScope.create(operation="inspect")
    store = SynapseStore(tmp_path / "private")
    store.contribute(_contribution(scope, source="official"))

    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(store.path.parent.stat().st_mode) == 0o700

    linked = SynapseStore(tmp_path / "linked")
    linked.path.parent.mkdir(parents=True)
    target = tmp_path / "outside-cache.json"
    target.write_text("{}", encoding="utf-8")
    linked.path.symlink_to(target)
    with pytest.raises(SynapseStoreError, match="unreadable"):
        linked.list_knowledge()


def test_synapse_contribution_passport_previews_exact_redacted_bytes_before_export(
    tmp_path,
) -> None:
    store = SynapseStore(tmp_path)
    scope = SynapseScope.create(
        operation="payload extraction",
        source_kind="payload-bin",
        device_codename="popsicle",
        build_family="os4-xpbcnxm",
        tool_name="payload-dumper-go",
        tool_version="2.0.2",
    )
    knowledge = store.contribute(
        SynapseContribution.create(
            fingerprint_id="a" * 64,
            solution_id="inspect-payload-source",
            scope=scope,
            source_family="official-aosp",
            summary=(
                "Verified at C:\\Users\\Steve\\ROMVERSE for owner@example.com from "
                "192.168.1.20 using token=private and serial ABCDEF123456789."
            ),
            successful=True,
            locally_verified=True,
            action_receipt_digest="b" * 64,
            verification_evidence_digest="c" * 64,
        )
    )
    service = SynapseContributionEnvelopeService(tmp_path)

    envelope = service.prepare(knowledge)
    document = json.loads(envelope.preview)

    assert not service.output_dir.exists()
    assert document["status"] == "private-review-only"
    assert document["upload_authorized"] is False
    assert document["phone_action_allowed"] is False
    assert document["records"][0]["scope"]["device_codename"] == "popsicle"
    assert document["records"][0]["scope"]["build_family"] == "os4-xpbcnxm"
    assert "fingerprint_id" not in envelope.preview
    assert "knowledge_id" not in envelope.preview
    assert "receipt_digest" not in envelope.preview
    assert "Steve" not in envelope.preview
    assert "owner@example.com" not in envelope.preview
    assert "192.168.1.20" not in envelope.preview
    assert "token=private" not in envelope.preview
    assert "ABCDEF123456789" not in envelope.preview

    exported = service.export(envelope)

    assert exported.output_path.read_bytes() == envelope.payload
    assert exported.sha256 == envelope.sha256
    assert exported.record_count == 1

    changed = SynapseContributionEnvelope(
        payload=envelope.payload.replace(
            b'"upload_authorized": false', b'"upload_authorized": true'
        ),
        sha256=envelope.sha256,
        envelope_digest=envelope.envelope_digest,
        record_count=envelope.record_count,
    )
    with pytest.raises(SynapseContributionEnvelopeError, match="bytes changed"):
        service.export(changed)

    injected = json.loads(envelope.preview)
    injected.pop("envelope_digest")
    injected["records"][0]["serial"] = "ABCDEF123456789"
    injected["envelope_digest"] = hashlib.sha256(
        json.dumps(injected, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    injected_payload = (
        json.dumps(injected, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode()
    reconstructed = SynapseContributionEnvelope(
        payload=injected_payload,
        sha256=hashlib.sha256(injected_payload).hexdigest(),
        envelope_digest=injected["envelope_digest"],
        record_count=1,
    )
    with pytest.raises(SynapseContributionEnvelopeError, match="record shape"):
        service.export(reconstructed)
