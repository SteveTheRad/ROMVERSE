from __future__ import annotations

from romverse.knowledge.lookup import OfflineKnowledgeService
from romverse.knowledge.models import KnowledgeConfidence, KnowledgeQuery, KnowledgeSourceTier
from romverse.knowledge.store import load_packaged_archive

FIELD_RECORD_IDS = {
    "romverse.popsicle-os303190-fragmented-data-response",
    "romverse.popsicle-os303190-bounded-fastboot-fallback",
    "romverse.popsicle-os303190-complete-write-before-wipe",
}


def test_popsicle_field_case_is_packaged_as_execution_inert_exact_scope() -> None:
    archive = load_packaged_archive()
    records = {record.record_id: record for record in archive.records}
    source = next(
        source
        for source in archive.sources
        if source.source_id == "romverse.field.popsicle-os303190-fastboot-20260909"
    )

    assert records.keys() >= FIELD_RECORD_IDS
    assert source.tier is KnowledgeSourceTier.ROMVERSE_VERIFIED
    assert source.url == ""
    assert "8ed2712d5df930cd5fff1794f4725b2bc743fa23411062e7f68239723d997e64" in (source.scope)
    for record_id in FIELD_RECORD_IDS:
        record = records[record_id]
        assert record.confidence is KnowledgeConfidence.VERIFIED
        assert record.corroboration_count == 1
        assert record.scope.codenames == ("popsicle",)
        assert "OS3.0.319.0.WPBCNXM" in record.scope.build_ids
        assert record.operations == ()


def test_exact_popsicle_fragmented_data_failure_finds_verified_record(tmp_path) -> None:
    report = OfflineKnowledgeService(tmp_path / "workspace").lookup(
        KnowledgeQuery(
            manufacturers=("xiaomi",),
            models=("2509FPN0BC",),
            codenames=("popsicle",),
            build_ids=("OS3.0.319.0.WPBCNXM",),
            android_versions=("16",),
            bootloader_states=("unlocked",),
            partitions=("abl",),
            error_codes=("DATA000520",),
            evidence_terms=("fragmented DATA response",),
        )
    )

    assert report.matches[0].record.record_id == (
        "romverse.popsicle-os303190-fragmented-data-response"
    )
    assert report.matches[0].confidence.value == "exact"
    assert report.execution_authority == "none"


def test_popsicle_field_case_does_not_match_a_different_device(tmp_path) -> None:
    report = OfflineKnowledgeService(tmp_path / "workspace").lookup(
        KnowledgeQuery(
            manufacturers=("google",),
            models=("Pixel 8 Pro",),
            codenames=("husky",),
            build_ids=("AP4A.260805.003",),
            error_codes=("DATA000520",),
        ),
        limit=64,
    )

    assert FIELD_RECORD_IDS.isdisjoint(match.record.record_id for match in report.matches)


def test_cleanup_record_preserves_unknown_and_slot_b_boundaries() -> None:
    record = next(
        record
        for record in load_packaged_archive().records
        if record.record_id == "romverse.popsicle-os303190-complete-write-before-wipe"
    )
    text = " ".join(
        (
            record.summary,
            *record.diagnostic_steps,
            *record.fix_steps,
            *record.prerequisites,
            *record.known_incompatibility,
            *record.tags,
            record.scope.scope_note,
        )
    ).casefold()

    assert "unknown" in text
    assert "automatically retry" in text
    assert "slot b" in text
    assert "explicit full-wipe consent" in text
    assert "never relock" in text
