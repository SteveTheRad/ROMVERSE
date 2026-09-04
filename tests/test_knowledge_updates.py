from __future__ import annotations

import base64
import json
import stat
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from romverse.knowledge.models import (
    DeviceKnowledgeScope,
    KnowledgeArchive,
    KnowledgeConfidence,
    KnowledgeKind,
    KnowledgeRecord,
    KnowledgeSource,
    KnowledgeSourceTier,
)
from romverse.knowledge.store import ARCHIVE_SCHEMA_VERSION, KnowledgeArchiveStore, seal_archive
from romverse.knowledge.updates import (
    KnowledgePublisherKey,
    KnowledgeUpdateError,
    KnowledgeUpdateService,
    signed_update_document,
)


def _archive() -> KnowledgeArchive:
    source = KnowledgeSource(
        "official.fixture.update",
        "Fixture vendor update guide",
        "Fixture Vendor",
        "https://example.com/android/recovery-update",
        KnowledgeSourceTier.OFFICIAL_VENDOR,
        "Exact fixture recovery guidance",
        datetime.now(UTC).date().isoformat(),
    )
    record = KnowledgeRecord(
        "fixture.signed-update",
        1,
        "Signed fixture recovery evidence",
        KnowledgeKind.RECOVERY,
        "A signed exact-device recovery record.",
        ("fixture boot failure",),
        ("FIXTURE_BOOT_1",),
        ("fixture.boot.failure",),
        ("Confirm the exact fixture target.",),
        ("Review the verified fixture recovery route.",),
        ("Verified source package",),
        ("Fresh boot evidence",),
        ("Fixture Phone / fixture / BUILD.1",),
        ("Every other device",),
        ("fixture-stock-route",),
        ("fixture", "signed update"),
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
            "fixture-signed-update",
            datetime.now(UTC).isoformat(),
            (source,),
            (record,),
            "",
        )
    )


def _write_update(path, private_key: Ed25519PrivateKey, archive: KnowledgeArchive) -> None:
    now = datetime.now(UTC)
    unsigned = signed_update_document(
        archive,
        update_id="fixture-update-1",
        signer_id="fixture-publisher",
        issued_at=(now - timedelta(minutes=1)).isoformat(),
        expires_at=(now + timedelta(days=1)).isoformat(),
    )
    signature = private_key.sign(
        KnowledgeUpdateService.DOMAIN + KnowledgeUpdateService.canonical_bytes(unsigned)
    )
    path.write_text(
        json.dumps(
            {**unsigned, "signature": base64.b64encode(signature).decode("ascii")},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _service(workspace, private_key: Ed25519PrivateKey) -> KnowledgeUpdateService:
    public = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return KnowledgeUpdateService(
        workspace,
        (
            KnowledgePublisherKey(
                "fixture-publisher",
                base64.b64encode(public).decode("ascii"),
            ),
        ),
    )


def test_signed_update_preview_is_read_only_and_apply_is_audited(tmp_path) -> None:
    private_key = Ed25519PrivateKey.generate()
    workspace = tmp_path / "workspace"
    source = tmp_path / "knowledge-update.json"
    _write_update(source, private_key, _archive())
    service = _service(workspace, private_key)

    preview = service.inspect(source)

    assert not service.store.path.exists()
    assert preview.signer_id == "fixture-publisher"
    assert preview.result.added == 1
    assert preview.execution_authority == "none"
    assert not preview.phone_action_allowed

    receipt = service.apply(preview)

    installed = KnowledgeArchiveStore(workspace).load()
    assert "fixture.signed-update" in {record.record_id for record in installed.records}
    assert receipt.installed_archive_digest == installed.bundle_digest
    assert receipt.receipt_path.is_file()
    assert stat.S_IMODE(receipt.receipt_path.stat().st_mode) == 0o600
    assert receipt.execution_authority == "none"
    assert not receipt.phone_changed


def test_signed_update_rejects_tampering_unknown_signers_and_stale_previews(tmp_path) -> None:
    private_key = Ed25519PrivateKey.generate()
    source = tmp_path / "knowledge-update.json"
    _write_update(source, private_key, _archive())
    service = _service(tmp_path / "workspace", private_key)
    preview = service.inspect(source)

    document = json.loads(source.read_text(encoding="utf-8"))
    document["archive"]["records"][0]["summary"] = "Tampered after signing"
    source.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(KnowledgeUpdateError, match="signature verification failed"):
        service.inspect(source)
    with pytest.raises(KnowledgeUpdateError, match="changed after the reviewed preview"):
        service.apply(preview)

    unknown_private = Ed25519PrivateKey.generate()
    unknown_public = unknown_private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    unknown = KnowledgeUpdateService(
        tmp_path / "unknown-workspace",
        (
            KnowledgePublisherKey(
                "another-publisher",
                base64.b64encode(unknown_public).decode("ascii"),
            ),
        ),
    )
    _write_update(source, private_key, _archive())
    with pytest.raises(KnowledgeUpdateError, match="not trusted"):
        unknown.inspect(source)


def test_unconfigured_or_revoked_knowledge_trust_fails_closed(tmp_path) -> None:
    private_key = Ed25519PrivateKey.generate()
    public = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    source = tmp_path / "knowledge-update.json"
    _write_update(source, private_key, _archive())

    with pytest.raises(KnowledgeUpdateError, match="No production publisher"):
        KnowledgeUpdateService(
            tmp_path / "empty",
            (),
            unavailable_reason="No production publisher is configured.",
        ).inspect(source)
    with pytest.raises(KnowledgeUpdateError, match="revoked"):
        KnowledgeUpdateService(
            tmp_path / "revoked",
            (
                KnowledgePublisherKey(
                    "fixture-publisher",
                    base64.b64encode(public).decode("ascii"),
                    revoked=True,
                ),
            ),
        )
