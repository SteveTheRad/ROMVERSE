from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from importlib.resources import files

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from romverse.device.models import AndroidDevice, DeviceState
from romverse.galaxy.intelligence import (
    GalaxyContributionDraft,
    GalaxyContributionKind,
    GalaxyEvidenceClass,
    GalaxyIntelligenceService,
    GalaxyModerationDecision,
    GalaxyModerationKey,
    GalaxyOutcome,
)
from romverse.galaxy.network import (
    GalaxyHttpResponse,
    GalaxyNetworkError,
    GalaxyNetworkService,
    GalaxyReceiptKey,
    GalaxyServiceTrust,
    galaxy_submission_receipt_document,
    load_galaxy_service_trust,
)
from romverse.knowledge.models import (
    DeviceKnowledgeScope,
    KnowledgeArchive,
    KnowledgeConfidence,
    KnowledgeKind,
    KnowledgeRecord,
    KnowledgeSource,
    KnowledgeSourceTier,
)
from romverse.knowledge.store import (
    ARCHIVE_SCHEMA_VERSION,
    KnowledgeArchiveStore,
    seal_archive,
)
from romverse.knowledge.updates import (
    KnowledgePublisherKey,
    KnowledgeUpdateService,
    signed_update_document,
)
from romverse.members.client import MemberProfile, MemberSession


class FakeGalaxyTransport:
    def __init__(self) -> None:
        self.responses: dict[tuple[str, str], bytes] = {}
        self.calls: list[dict[str, object]] = []

    def request(
        self,
        url: str,
        *,
        method: str,
        body: bytes | None,
        headers: dict[str, str],
        maximum_bytes: int,
    ) -> GalaxyHttpResponse:
        self.calls.append(
            {
                "url": url,
                "method": method,
                "body": body,
                "headers": headers,
                "maximum_bytes": maximum_bytes,
            }
        )
        payload = self.responses[(method, url)]
        return GalaxyHttpResponse(200, url, payload)


def _key_bytes(private_key: Ed25519PrivateKey) -> str:
    return base64.b64encode(
        private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
    ).decode("ascii")


def _trust(private_key: Ed25519PrivateKey) -> GalaxyServiceTrust:
    encoded = _key_bytes(private_key)
    return GalaxyServiceTrust(
        True,
        "Fixture Galaxy trust.",
        "https://galaxy.example.test/v1",
        "https://members.example.test",
        (GalaxyReceiptKey("fixture-galaxy", encoded),),
        (GalaxyModerationKey("fixture-galaxy", encoded),),
        (KnowledgePublisherKey("fixture-galaxy", encoded),),
    )


def _session(now: datetime, *, active: bool = True) -> MemberSession:
    return MemberSession(
        "fixture-access-token-which-is-private",
        "Bearer",
        int(now.timestamp()) + 3600,
        MemberProfile(
            "fixture-subject",
            "Fixture member",
            "",
            "Fixture plan",
            "active" if active else "inactive",
        ),
    )


def _device() -> AndroidDevice:
    return AndroidDevice(
        "PRIVATE-GALAXY-SERIAL",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        brand="Xiaomi",
        model="25128PN0CC",
        product="popsicle_cn",
        codename="popsicle",
        android_version="16",
        build_id="OS4.0.0.25.WPBCNXM",
        verified_boot="orange",
        ab_update=True,
        virtual_ab=True,
        dynamic_partitions=True,
    )


def _queued(intelligence: GalaxyIntelligenceService):
    draft = GalaxyContributionDraft(
        GalaxyContributionKind.COMPATIBILITY,
        GalaxyOutcome.WORKING,
        "Exact vehicle projection result",
        "The real vehicle projection test completed on this exact build.",
        ("Projection previously stopped during handshake",),
        ("Repeat with the same exact build and vehicle.",),
        ("https://example.com/reports/exact-projection",),
        "Fixture contributor",
        "xiaomi-popsicle-os4",
    )
    preview = intelligence.preview(draft, _device())
    return intelligence.queue(preview, preview.preview_digest)


def _signed_receipt(
    private_key: Ed25519PrivateKey,
    contribution_id: str,
    contribution_digest: str,
    now: datetime,
) -> bytes:
    unsigned = galaxy_submission_receipt_document(
        receipt_id="fixture-receipt-1",
        contribution_id=contribution_id,
        contribution_digest=contribution_digest,
        received_at=now.isoformat(),
        state="pending-review",
        signer_id="fixture-galaxy",
    )
    signature = private_key.sign(
        GalaxyNetworkService.RECEIPT_DOMAIN
        + json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    )
    return json.dumps(
        {**unsigned, "signature": base64.b64encode(signature).decode("ascii")},
        sort_keys=True,
    ).encode("utf-8")


def _update_archive(now: datetime) -> KnowledgeArchive:
    source = KnowledgeSource(
        "official.galaxy.fixture",
        "Fixture official Android guide",
        "Fixture Vendor",
        "https://example.com/official/android-guide",
        KnowledgeSourceTier.OFFICIAL_VENDOR,
        "Exact fixture update transport test",
        now.date().isoformat(),
    )
    record = KnowledgeRecord(
        "galaxy.fixture.signed-update",
        1,
        "Galaxy-downloaded signed recovery guide",
        KnowledgeKind.RECOVERY,
        "A fixture record delivered through the bounded signed update route.",
        ("fixture boot issue",),
        ("FIXTURE_1",),
        ("fixture.boot",),
        ("Confirm the exact target and build.",),
        ("Use the verified fixture recovery route.",),
        ("Verified fixture package",),
        ("Fresh boot evidence",),
        ("Fixture Phone / fixture / BUILD.1",),
        ("Every other device",),
        ("fixture-stock-recovery",),
        ("galaxy", "signed update", "fixture"),
        DeviceKnowledgeScope(
            manufacturers=("Fixture",),
            models=("Fixture Phone",),
            codenames=("fixture",),
            build_ids=("BUILD.1",),
            scope_note="Exact Fixture Phone BUILD.1 only.",
        ),
        (source.source_id,),
        KnowledgeConfidence.VERIFIED,
        2,
        (),
    )
    return seal_archive(
        KnowledgeArchive(
            ARCHIVE_SCHEMA_VERSION,
            "galaxy-fixture-update",
            now.isoformat(),
            (source,),
            (record,),
            "",
        )
    )


def _signed_update(private_key: Ed25519PrivateKey, now: datetime) -> bytes:
    unsigned = signed_update_document(
        _update_archive(now),
        update_id="galaxy-fixture-update-1",
        signer_id="fixture-galaxy",
        issued_at=(now - timedelta(minutes=1)).isoformat(),
        expires_at=(now + timedelta(days=1)).isoformat(),
    )
    signature = private_key.sign(
        KnowledgeUpdateService.DOMAIN + KnowledgeUpdateService.canonical_bytes(unsigned)
    )
    return json.dumps(
        {**unsigned, "signature": base64.b64encode(signature).decode("ascii")},
        sort_keys=True,
    ).encode("utf-8")


def test_packaged_galaxy_trust_is_honestly_unconfigured(tmp_path) -> None:
    trust_path = files("romverse.assets").joinpath("galaxy_service_trust.json")
    trust = load_galaxy_service_trust(trust_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    intelligence = GalaxyIntelligenceService(workspace, sharing_enabled=True)
    service = GalaxyNetworkService(workspace, intelligence, trust)

    assert not service.configured
    assert "not been enrolled" in service.status_reason
    assert not service.receipt_root.exists()


def test_explicit_authenticated_submission_gets_a_signed_idempotent_receipt(tmp_path) -> None:
    now = datetime.now(UTC)
    private_key = Ed25519PrivateKey.generate()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    intelligence = GalaxyIntelligenceService(workspace, sharing_enabled=True)
    contribution = _queued(intelligence)
    transport = FakeGalaxyTransport()
    service = GalaxyNetworkService(
        workspace,
        intelligence,
        _trust(private_key),
        member_issuer="https://members.example.test",
        transport=transport,
        clock=lambda: now.timestamp(),
    )
    preview = service.preview_submission(contribution)
    outbound = json.loads(preview.payload_json)
    assert set(outbound["submission"]) == {
        "schema_version",
        "contribution_id",
        "created_at",
        "kind",
        "outcome",
        "title",
        "summary",
        "symptoms",
        "solution_steps",
        "evidence_refs",
        "contributor_key",
        "device_pattern",
        "conflict_ids",
        "submitted_evidence_class",
    }
    endpoint = "https://galaxy.example.test/v1/contributions"
    transport.responses[("POST", endpoint)] = _signed_receipt(
        private_key,
        contribution.contribution_id,
        preview.contribution_digest,
        now,
    )

    with pytest.raises(GalaxyNetworkError, match="exact Galaxy network preview"):
        service.submit(preview, "0" * 64, _session(now))
    receipt = service.submit(preview, preview.payload_sha256, _session(now))

    assert receipt.state == "pending-review"
    assert receipt.receipt_path.is_file()
    assert receipt.execution_authority == "none"
    assert not receipt.phone_changed
    request = transport.calls[-1]
    assert request["method"] == "POST"
    assert request["headers"]["Idempotency-Key"] == preview.contribution_digest
    assert request["headers"]["Authorization"].startswith("Bearer ")
    assert "PRIVATE-GALAXY-SERIAL" not in preview.payload_json
    assert "fixture-access-token" not in receipt.receipt_path.read_text(encoding="utf-8")
    assert service.receipt_for(contribution) == receipt
    with pytest.raises(GalaxyNetworkError, match="already has a verified"):
        service.preview_submission(contribution)

    moderated = intelligence.apply_moderation(
        (
            GalaxyModerationDecision(
                contribution.contribution_id,
                preview.contribution_digest,
                GalaxyEvidenceClass.DISPUTED,
                "Fixture moderation preserves the immutable submission binding.",
                0,
                "",
            ),
        ),
        "fixture-galaxy",
    )[0]
    assert service.receipt_for(moderated) == receipt

    original = json.loads(receipt.receipt_path.read_text(encoding="utf-8"))
    stored = dict(original)
    stored["request_sha256"] = "0" * 64
    local_unsigned = dict(stored)
    local_unsigned.pop("local_digest")
    stored["local_digest"] = hashlib.sha256(
        json.dumps(
            local_unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    receipt.receipt_path.write_text(json.dumps(stored), encoding="utf-8")
    with pytest.raises(GalaxyNetworkError, match="binding is invalid"):
        service.receipt_for(moderated)

    stored = original
    stored["receipt"]["state"] = "duplicate"
    local_unsigned = dict(stored)
    local_unsigned.pop("local_digest")
    stored["local_digest"] = hashlib.sha256(
        json.dumps(
            local_unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    receipt.receipt_path.write_text(json.dumps(stored), encoding="utf-8")
    with pytest.raises(GalaxyNetworkError, match="signature verification failed"):
        service.receipt_for(moderated)


def test_submission_requires_opt_in_matching_issuer_active_member_and_valid_signature(
    tmp_path,
) -> None:
    now = datetime.now(UTC)
    private_key = Ed25519PrivateKey.generate()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    intelligence = GalaxyIntelligenceService(workspace, sharing_enabled=True)
    contribution = _queued(intelligence)
    transport = FakeGalaxyTransport()
    service = GalaxyNetworkService(
        workspace,
        intelligence,
        _trust(private_key),
        member_issuer="https://members.example.test",
        transport=transport,
        clock=lambda: now.timestamp(),
    )
    preview = service.preview_submission(contribution)
    endpoint = preview.endpoint
    receipt = json.loads(
        _signed_receipt(
            private_key,
            contribution.contribution_id,
            preview.contribution_digest,
            now,
        )
    )
    receipt["state"] = "duplicate"
    transport.responses[("POST", endpoint)] = json.dumps(receipt).encode("utf-8")

    with pytest.raises(GalaxyNetworkError, match="signature verification failed"):
        service.submit(preview, preview.payload_sha256, _session(now))
    assert not service.receipt_root.exists()

    service.set_member_issuer("https://other.example.test")
    with pytest.raises(GalaxyNetworkError, match="does not match"):
        service.preview_submission(contribution)
    service.set_member_issuer("https://members.example.test")
    with pytest.raises(GalaxyNetworkError, match="active ROMVERSE Members"):
        service.submit(preview, preview.payload_sha256, _session(now, active=False))
    intelligence.set_sharing_enabled(False)
    with pytest.raises(GalaxyNetworkError, match="opted out"):
        service.preview_submission(contribution)


def test_submission_rejects_a_stale_signed_receipt(tmp_path) -> None:
    now = datetime.now(UTC)
    private_key = Ed25519PrivateKey.generate()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    intelligence = GalaxyIntelligenceService(workspace, sharing_enabled=True)
    contribution = _queued(intelligence)
    transport = FakeGalaxyTransport()
    service = GalaxyNetworkService(
        workspace,
        intelligence,
        _trust(private_key),
        member_issuer="https://members.example.test",
        transport=transport,
        clock=lambda: now.timestamp(),
    )
    preview = service.preview_submission(contribution)
    transport.responses[("POST", preview.endpoint)] = _signed_receipt(
        private_key,
        contribution.contribution_id,
        preview.contribution_digest,
        now - timedelta(hours=1),
    )

    with pytest.raises(GalaxyNetworkError, match="not fresh"):
        service.submit(preview, preview.payload_sha256, _session(now))
    assert not service.receipt_root.exists()


def test_packaged_trust_loader_rejects_a_symbolic_link(tmp_path) -> None:
    source = files("romverse.assets").joinpath("galaxy_service_trust.json")
    target = tmp_path / "trust.json"
    target.write_bytes(source.read_bytes())
    link = tmp_path / "linked-trust.json"
    link.symlink_to(target)

    with pytest.raises(GalaxyNetworkError, match="symbolic link"):
        load_galaxy_service_trust(link)


def test_downloaded_knowledge_is_signature_checked_before_explicit_local_apply(tmp_path) -> None:
    now = datetime.now(UTC)
    private_key = Ed25519PrivateKey.generate()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    intelligence = GalaxyIntelligenceService(workspace, sharing_enabled=True)
    key = KnowledgePublisherKey("fixture-galaxy", _key_bytes(private_key))
    updates = KnowledgeUpdateService(workspace, (key,))
    transport = FakeGalaxyTransport()
    endpoint = "https://galaxy.example.test/v1/knowledge/stable/latest"
    transport.responses[("GET", endpoint)] = _signed_update(private_key, now)
    service = GalaxyNetworkService(
        workspace,
        intelligence,
        _trust(private_key),
        member_issuer="https://members.example.test",
        update_service=updates,
        transport=transport,
        clock=lambda: now.timestamp(),
    )

    preview = service.download_signed_update(_session(now))

    assert preview.signer_id == "fixture-galaxy"
    assert preview.result.added == 1
    assert preview.execution_authority == "none"
    assert not preview.phone_action_allowed
    assert not updates.store.path.exists()
    receipt = updates.apply(preview)
    installed = KnowledgeArchiveStore(workspace).load()
    assert receipt.installed_archive_digest == installed.bundle_digest
    assert "galaxy.fixture.signed-update" in {record.record_id for record in installed.records}
