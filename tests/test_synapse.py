from __future__ import annotations

import hashlib
import json
import stat

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
