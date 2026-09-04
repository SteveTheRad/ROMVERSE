from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from romverse.knowledge.lookup import OfflineKnowledgeService
from romverse.knowledge.models import (
    KnowledgeEvidenceLabel,
    KnowledgeEvidenceStatus,
    KnowledgeOperation,
    KnowledgeQuery,
    KnowledgeRiskClass,
)
from romverse.knowledge.store import (
    KnowledgeArchiveError,
    KnowledgeArchiveStore,
    archive_mapping,
    load_packaged_archive,
    parse_archive,
    seal_archive,
)
from romverse.knowledge.updates import (
    KnowledgeUpdateError,
    KnowledgeUpdateService,
    signed_update_document,
)
from tests.test_knowledge_updates import _archive as _update_archive
from tests.test_knowledge_updates import _service
from tests.test_offline_knowledge import _archive, _record, _source

_METADATA_FIELDS = {
    "evidence_status",
    "confidence_score",
    "status_reason",
    "updated_at",
    "failure_count",
    "moderation_required",
}


def _seal_raw(raw):
    raw["bundle_digest"] = ""
    raw["bundle_digest"] = hashlib.sha256(KnowledgeUpdateService.canonical_bytes(raw)).hexdigest()
    return raw


def _raw(archive):
    return json.loads(KnowledgeUpdateService.canonical_bytes(archive_mapping(archive)))


def _legacy_raw(archive):
    raw = _raw(archive)
    for record in raw["records"]:
        for field in _METADATA_FIELDS:
            record.pop(field, None)
        for operation in record["operations"]:
            operation.pop("risk_class", None)
        if record["record_id"].startswith("catalog."):
            record["revision"] = 1
    return _seal_raw(raw)


@pytest.mark.parametrize("status", list(KnowledgeEvidenceStatus))
def test_explicit_evidence_state_survives_save_reload_and_repeated_save(tmp_path, status) -> None:
    record = replace(
        _record(),
        evidence_status=status,
        confidence_score=43,
        failure_count=2,
        status_reason="Preserved explicit review state.",
        moderation_required=True,
    )
    store = KnowledgeArchiveStore(tmp_path / "workspace")

    saved = store.save(_archive(_source(), record))
    original = store.path.read_bytes()
    loaded = store.load()
    second = store.save(loaded)

    assert saved == loaded == second
    assert loaded.records == (record,)
    assert store.path.read_bytes() == original
    assert parse_archive(json.loads(original)).bundle_digest == seal_archive(loaded).bundle_digest


@pytest.mark.parametrize(
    "field,value",
    [
        ("evidence_status", None),
        ("evidence_status", "invented"),
        ("confidence_score", True),
        ("confidence_score", 101),
        ("failure_count", -1),
        ("failure_count", "5"),
        ("moderation_required", "false"),
        ("moderation_required", []),
        ("status_reason", False),
        ("updated_at", ""),
    ],
)
def test_malformed_evidence_metadata_is_rejected_instead_of_becoming_safe_defaults(
    field, value
) -> None:
    raw = _raw(_archive(_source(), _record()))
    raw["records"][0][field] = value

    with pytest.raises(KnowledgeArchiveError):
        parse_archive(_seal_raw(raw))


def test_legacy_risk_is_derived_but_explicit_invalid_risk_is_rejected() -> None:
    operation = KnowledgeOperation(
        "fixture.restore",
        "Restore partition image",
        "restore",
        True,
        ("boot",),
        ("verified-stock-image",),
        "official-stock-restore",
    )
    raw = _legacy_raw(_archive(_source(), _record(operation=operation)))

    parsed = parse_archive(raw)
    assert parsed.records[0].operations[0].risk_class is KnowledgeRiskClass.HIGH
    raw["records"][0]["operations"][0]["risk_class"] = "unknown-risk"
    with pytest.raises(KnowledgeArchiveError, match="risk class"):
        parse_archive(_seal_raw(raw))


def test_pre_metadata_catalog_upgrades_once_without_same_revision_conflicts(tmp_path) -> None:
    packaged = load_packaged_archive()
    legacy = _legacy_raw(packaged)
    store = KnowledgeArchiveStore(tmp_path / "workspace")
    store.root.mkdir(parents=True)
    store.path.write_bytes(KnowledgeUpdateService.canonical_bytes(legacy))

    assert store.load().bundle_digest == legacy["bundle_digest"]
    upgraded = store.ensure_seeded()
    assert store.ensure_seeded() == upgraded
    assert len(upgraded.records) == len(packaged.records)
    assert all(
        record.revision == 2
        for record in upgraded.records
        if record.record_id.startswith("catalog.")
    )
    assert store.load().bundle_digest == seal_archive(upgraded).bundle_digest


def test_catalog_enrichment_keeps_local_moderation_and_remains_reloadable(tmp_path) -> None:
    packaged = load_packaged_archive()
    original = next(
        record for record in packaged.records if record.record_id.startswith("catalog.")
    )
    moderated = replace(
        original,
        revision=1,
        evidence_status=KnowledgeEvidenceStatus.DISPUTED,
        failure_count=3,
        moderation_required=True,
        status_reason="Local device failures recorded.",
    )
    local = replace(packaged, records=(moderated,))
    store = KnowledgeArchiveStore(tmp_path / "workspace")
    store.save(seal_archive(local))

    upgraded = store.ensure_seeded()
    preserved = next(
        record for record in upgraded.records if record.record_id == moderated.record_id
    )
    assert preserved.revision == 2
    assert preserved.evidence_status is KnowledgeEvidenceStatus.DISPUTED
    assert preserved.failure_count == 3
    assert preserved.moderation_required
    assert preserved.status_reason == moderated.status_reason
    assert store.ensure_seeded() == upgraded


def test_legacy_signed_update_verifies_original_signature_then_saves_valid_local_migration(
    tmp_path,
) -> None:
    key = Ed25519PrivateKey.generate()
    now = datetime.now(UTC)
    archive = _update_archive()
    unsigned = signed_update_document(
        archive,
        update_id="legacy-update-1",
        signer_id="fixture-publisher",
        issued_at=(now - timedelta(minutes=1)).isoformat(),
        expires_at=(now + timedelta(days=1)).isoformat(),
    )
    unsigned["archive"] = _legacy_raw(archive)
    signature = key.sign(
        KnowledgeUpdateService.DOMAIN + KnowledgeUpdateService.canonical_bytes(unsigned)
    )
    envelope = {**unsigned, "signature": base64.b64encode(signature).decode("ascii")}
    source = tmp_path / "legacy-signed.json"
    original = KnowledgeUpdateService.canonical_bytes(envelope)
    source.write_bytes(original)
    service = _service(tmp_path / "workspace", key)

    preview = service.inspect(source)
    assert preview.incoming_archive_digest == unsigned["archive"]["bundle_digest"]
    receipt = service.apply(preview)
    installed = service.store.load()
    assert receipt.incoming_archive_digest == unsigned["archive"]["bundle_digest"]
    assert receipt.installed_archive_digest == installed.bundle_digest
    assert installed.bundle_digest == seal_archive(installed).bundle_digest
    assert source.read_bytes() == original
    added = next(
        record for record in installed.records if record.record_id == archive.records[0].record_id
    )
    assert added.evidence_status is KnowledgeEvidenceStatus.DRAFT

    # Even a hash-correct metadata addition needs its own signature.
    envelope["archive"]["records"][0]["evidence_status"] = "official"
    envelope["archive"] = _seal_raw(envelope["archive"])
    source.write_bytes(KnowledgeUpdateService.canonical_bytes(envelope))
    with pytest.raises(KnowledgeUpdateError, match="signature verification failed"):
        service.inspect(source)


def test_new_signing_document_from_parsed_legacy_archive_has_matching_content_digest() -> None:
    legacy = parse_archive(_legacy_raw(_update_archive()))
    document = signed_update_document(
        legacy,
        update_id="prepared-update-2",
        signer_id="fixture-publisher",
        issued_at="2026-09-05T00:00:00+00:00",
        expires_at="2026-09-06T00:00:00+00:00",
    )

    parsed = parse_archive(document["archive"])
    assert parsed.bundle_digest == seal_archive(parsed).bundle_digest
    assert "signature" not in document


@pytest.mark.parametrize(
    "status",
    [
        KnowledgeEvidenceStatus.UNSAFE,
        KnowledgeEvidenceStatus.RETIRED,
        KnowledgeEvidenceStatus.DISPUTED,
    ],
)
def test_negative_status_is_visible_and_never_recommended_as_the_repair_lead(
    tmp_path, status
) -> None:
    record = replace(
        _record("fixture.exact-negative"),
        evidence_status=status,
        confidence_score=100,
        corroboration_count=10,
    )
    service = OfflineKnowledgeService(tmp_path / "workspace")
    service.store.save(_archive(_source(), record))

    report = service.lookup(
        KnowledgeQuery(
            models=("RP1",),
            codenames=("rad",),
            build_ids=("RAD.2026.0904",),
            error_codes=("E_BOOT_42",),
        ),
        trigger="negative-test",
    )
    match = next(match for match in report.matches if match.record.record_id == record.record_id)
    assert match.safety.startswith("WITHHELD")
    expected_label = (
        KnowledgeEvidenceLabel.OUTDATED
        if status is KnowledgeEvidenceStatus.RETIRED
        else KnowledgeEvidenceLabel.DISPUTED
    )
    assert expected_label in match.evidence_labels
    assert KnowledgeEvidenceLabel.VERIFIED not in match.evidence_labels
    assert not report.safest_answer.startswith(f"Start with {record.title}")
