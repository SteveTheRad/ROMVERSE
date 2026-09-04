from __future__ import annotations

import base64
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from romverse.device.models import AndroidDevice, DeviceState
from romverse.galaxy.intelligence import (
    GalaxyContributionDraft,
    GalaxyContributionKind,
    GalaxyEvidenceClass,
    GalaxyIntelligenceError,
    GalaxyIntelligenceService,
    GalaxyModerationDecision,
    GalaxyModerationKey,
    GalaxyModerationService,
    GalaxyOutcome,
    galaxy_moderation_document,
)
from romverse.knowledge.models import KnowledgeConfidence, KnowledgeSourceTier
from romverse.knowledge.store import KnowledgeArchiveStore


def _device() -> AndroidDevice:
    return AndroidDevice(
        serial="PRIVATE-DEVICE-SERIAL",
        state=DeviceState.DEVICE,
        manufacturer="Xiaomi",
        brand="Xiaomi",
        model="25128PN0CC",
        marketing_name="Xiaomi 17 Pro Max",
        product="popsicle_cn",
        codename="popsicle",
        android_version="16",
        build_id="OS4.0.0.25.WPBCNXM",
        security_patch="2026-08-01",
        verified_boot="orange",
        ab_update=True,
        virtual_ab=True,
        dynamic_partitions=True,
    )


def _draft(
    *,
    outcome: GalaxyOutcome = GalaxyOutcome.WORKING,
    summary: str = "Android Auto projection connected after the exact-device upgrade.",
    steps: tuple[str, ...] = ("Verify the exact build and repeat the projection test.",),
) -> GalaxyContributionDraft:
    return GalaxyContributionDraft(
        GalaxyContributionKind.COMPATIBILITY,
        outcome,
        "Xiaomi 17 Pro Max Android Auto result",
        summary,
        ("Vehicle projection did not start before the upgrade",),
        steps,
        ("https://example.com/community/android-auto-result",),
        "Fixture contributor",
        "xiaomi-popsicle-os4",
    )


def _moderation_service(
    intelligence: GalaxyIntelligenceService,
    private_key: Ed25519PrivateKey,
) -> GalaxyModerationService:
    public = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return GalaxyModerationService(
        intelligence,
        (
            GalaxyModerationKey(
                "fixture-moderator",
                base64.b64encode(public).decode("ascii"),
            ),
        ),
    )


def _write_moderation(
    path,
    private_key: Ed25519PrivateKey,
    decision: GalaxyModerationDecision,
    *,
    signer_id: str = "fixture-moderator",
) -> None:
    now = datetime.now(UTC)
    unsigned = galaxy_moderation_document(
        (decision,),
        update_id="fixture-moderation-1",
        signer_id=signer_id,
        issued_at=(now - timedelta(minutes=1)).isoformat(),
        expires_at=(now + timedelta(days=1)).isoformat(),
    )
    signature = private_key.sign(
        GalaxyModerationService.DOMAIN
        + json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    )
    path.write_text(
        json.dumps(
            {**unsigned, "signature": base64.b64encode(signature).decode("ascii")},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_galaxy_preview_is_private_and_opted_out_by_default(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    service = GalaxyIntelligenceService(workspace)

    preview = service.preview(_draft(), _device())

    encoded = json.dumps(asdict(preview))
    assert "PRIVATE-DEVICE-SERIAL" not in encoded
    assert preview.device_pattern.model == "25128PN0CC"
    assert preview.device_pattern.region == "China"
    assert preview.upload_authority == "disabled"
    assert preview.eligible_for_queue
    assert not preview.phone_changed
    assert not service.path.exists()
    with pytest.raises(GalaxyIntelligenceError, match="opted out"):
        service.queue(preview, preview.preview_digest)

    poisoned = replace(_device(), product="prefix-PRIVATE-DEVICE-SERIAL-suffix")
    scrubbed = service.preview(_draft(), poisoned)
    assert scrubbed.device_pattern.product == ""
    assert "PRIVATE-DEVICE-SERIAL" not in json.dumps(asdict(scrubbed))


def test_galaxy_queue_and_export_require_exact_preview_without_uploading(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    service = GalaxyIntelligenceService(workspace, sharing_enabled=True)
    preview = service.preview(_draft(), _device())

    with pytest.raises(GalaxyIntelligenceError, match="exact privacy preview"):
        service.queue(preview, "0" * 64)
    contribution = service.queue(preview, preview.preview_digest)

    assert contribution.queued_for_review
    assert not contribution.uploaded
    assert contribution.execution_authority == "none"
    exported = service.export_submission(contribution, tmp_path / "reviewed-submission.json")
    payload = exported.read_text(encoding="utf-8")
    assert "PRIVATE-DEVICE-SERIAL" not in payload
    assert "imei" in payload.casefold()
    assert '"uploaded": false' in payload
    assert '"execution_authority": "none"' in payload

    service.set_sharing_enabled(False)
    with pytest.raises(GalaxyIntelligenceError, match="opted out"):
        service.export_submission(contribution, tmp_path / "blocked-export.json")


def test_galaxy_rejects_private_or_malicious_text_and_detects_duplicates_and_conflicts(
    tmp_path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    service = GalaxyIntelligenceService(workspace, sharing_enabled=True)
    first_preview = service.preview(_draft(), _device())
    service.queue(first_preview, first_preview.preview_digest)

    duplicate = service.preview(_draft(), _device())
    conflict = service.preview(_draft(outcome=GalaxyOutcome.FAILED), _device())
    malicious = service.preview(
        _draft(summary="Run rm -rf / and email owner@example.com before flashing."),
        _device(),
    )

    assert duplicate.duplicate_ids
    assert not duplicate.eligible_for_queue
    assert conflict.conflict_ids
    assert conflict.evidence_class is GalaxyEvidenceClass.DISPUTED
    assert malicious.evidence_class is GalaxyEvidenceClass.REJECTED
    assert not malicious.eligible_for_queue
    assert any("Private data" in warning for warning in malicious.warnings)
    assert any("malicious" in warning for warning in malicious.warnings)
    with pytest.raises(GalaxyIntelligenceError, match="address"):
        service.preview(
            replace(_draft(), evidence_refs=("https://127.0.0.1/private",)),
            _device(),
        )


def test_galaxy_ledger_refuses_tampering_without_replacing_it(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    service = GalaxyIntelligenceService(workspace, sharing_enabled=True)
    preview = service.preview(_draft(), _device())
    service.queue(preview, preview.preview_digest)
    payload = json.loads(service.path.read_text(encoding="utf-8"))
    payload["contributions"][0]["summary"] = "tampered"
    service.path.write_text(json.dumps(payload), encoding="utf-8")
    before = service.path.read_bytes()

    with pytest.raises(GalaxyIntelligenceError, match="digest does not match"):
        service.load()

    assert service.path.read_bytes() == before


def test_signed_moderation_promotes_verified_community_evidence_into_synapse(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    intelligence = GalaxyIntelligenceService(workspace, sharing_enabled=True)
    preview = intelligence.preview(_draft(), _device())
    queued = intelligence.queue(preview, preview.preview_digest)
    decision = GalaxyModerationDecision(
        queued.contribution_id,
        intelligence.contribution_digest(queued),
        GalaxyEvidenceClass.VERIFIED_COMMUNITY,
        "Two independent exact-build reports reproduced this result.",
        2,
        "https://example.com/community/android-auto-result",
    )
    private_key = Ed25519PrivateKey.generate()
    bundle = tmp_path / "moderation.json"
    _write_moderation(bundle, private_key, decision)
    moderation = _moderation_service(intelligence, private_key)

    moderation_preview = moderation.inspect(bundle)
    changed = moderation.apply(moderation_preview)

    assert moderation_preview.execution_authority == "none"
    assert not moderation_preview.phone_changed
    assert moderation_preview.current_ledger_digest != moderation_preview.envelope_sha256
    assert changed[0].evidence_class is GalaxyEvidenceClass.VERIFIED_COMMUNITY
    assert not changed[0].queued_for_review
    dashboard = intelligence.dashboard()
    assert dashboard.verified_community == 1
    assert dashboard.contributors[0].reputation_points == 12

    archive = KnowledgeArchiveStore(workspace).load()
    record = next(
        item for item in archive.records if item.record_id == f"galaxy.{queued.contribution_id}"
    )
    source = next(item for item in archive.sources if item.source_id == record.source_ids[0])
    assert record.confidence is KnowledgeConfidence.HIGH
    assert record.scope.codenames == ("popsicle",)
    assert record.scope.build_ids == ("OS4.0.0.25.WPBCNXM",)
    assert record.corroboration_count == 2
    assert source.tier is KnowledgeSourceTier.COMMUNITY


def test_moderation_rejects_tampering_untrusted_signers_stale_state_and_official_status(
    tmp_path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    intelligence = GalaxyIntelligenceService(workspace, sharing_enabled=True)
    preview = intelligence.preview(_draft(), _device())
    queued = intelligence.queue(preview, preview.preview_digest)
    private_key = Ed25519PrivateKey.generate()
    moderation = _moderation_service(intelligence, private_key)
    decision = GalaxyModerationDecision(
        queued.contribution_id,
        intelligence.contribution_digest(queued),
        GalaxyEvidenceClass.DISPUTED,
        "The submitted result conflicts with another exact-build report.",
        0,
        "",
    )
    bundle = tmp_path / "moderation.json"
    _write_moderation(bundle, private_key, decision)
    signed_preview = moderation.inspect(bundle)

    other = intelligence.preview(
        replace(_draft(), title="Separate local result", summary="Separate evidence summary."),
        _device(),
    )
    intelligence.queue(other, other.preview_digest)
    with pytest.raises(GalaxyIntelligenceError, match="changed after preview"):
        moderation.apply(signed_preview)

    payload = json.loads(bundle.read_text(encoding="utf-8"))
    payload["decisions"][0]["reason"] = "tampered"
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(GalaxyIntelligenceError, match="signature verification failed"):
        moderation.inspect(bundle)

    untrusted = GalaxyModerationService(
        intelligence,
        (
            GalaxyModerationKey(
                "different-moderator",
                base64.b64encode(
                    Ed25519PrivateKey.generate()
                    .public_key()
                    .public_bytes(
                        serialization.Encoding.Raw,
                        serialization.PublicFormat.Raw,
                    )
                ).decode("ascii"),
            ),
        ),
    )
    _write_moderation(bundle, private_key, decision)
    with pytest.raises(GalaxyIntelligenceError, match="signer is not trusted"):
        untrusted.inspect(bundle)

    official = replace(decision, evidence_class=GalaxyEvidenceClass.OFFICIAL)
    _write_moderation(bundle, private_key, official)
    with pytest.raises(GalaxyIntelligenceError, match="cannot grant official"):
        moderation.inspect(bundle)
