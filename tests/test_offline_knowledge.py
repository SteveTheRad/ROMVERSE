from __future__ import annotations

import json
import stat
from dataclasses import replace

import pytest

from romverse.device.dna import DeviceDnaService
from romverse.knowledge.lookup import OfflineKnowledgeService
from romverse.knowledge.models import (
    DeviceKnowledgeScope,
    KnowledgeArchive,
    KnowledgeConfidence,
    KnowledgeFailure,
    KnowledgeKind,
    KnowledgeOperation,
    KnowledgeQuery,
    KnowledgeRecord,
    KnowledgeSource,
    KnowledgeSourceTier,
    MatchConfidence,
)
from romverse.knowledge.store import (
    ARCHIVE_SCHEMA_VERSION,
    KnowledgeArchiveError,
    KnowledgeArchiveStore,
    archive_mapping,
    load_packaged_archive,
    seal_archive,
)

from .test_device_dna import _device, _project


def _source(
    source_id: str = "official.fixture",
    *,
    tier: KnowledgeSourceTier = KnowledgeSourceTier.OFFICIAL_VENDOR,
) -> KnowledgeSource:
    return KnowledgeSource(
        source_id=source_id,
        label="Official fixture evidence",
        publisher="Fixture vendor",
        url="https://example.com/official/device/recovery",
        tier=tier,
        scope="Exact fixture device recovery evidence.",
        reviewed_on="2026-09-04",
    )


def _record(
    record_id: str = "fixture.exact-boot-repair",
    *,
    source_id: str = "official.fixture",
    operation: KnowledgeOperation | None = None,
    confidence: KnowledgeConfidence = KnowledgeConfidence.VERIFIED,
    corroboration_count: int = 1,
) -> KnowledgeRecord:
    return KnowledgeRecord(
        record_id=record_id,
        revision=1,
        title="Exact radphone build boot repair",
        kind=KnowledgeKind.RECOVERY,
        summary="An exact target/build-scoped fixture repair.",
        symptoms=("boot verification failed",),
        error_codes=("E_BOOT_42",),
        finding_ids=("boot.incomplete",),
        diagnostic_steps=("Confirm the exact target, build, and boot partition.",),
        fix_steps=("Review the declared restore operation.",),
        prerequisites=("Verified stock boot input",),
        expected_outcomes=("The exact build boots and verifies.",),
        compatibility=("RadPhone RP1 / rad / RAD.2026.0904",),
        known_incompatibility=("Every other target or build",),
        recovery_routes=("official-stock-restore",),
        tags=("radphone", "boot", "E_BOOT_42"),
        scope=DeviceKnowledgeScope(
            manufacturers=("RadForge",),
            brands=("RadPhone",),
            models=("RP1",),
            codenames=("rad",),
            build_ids=("RAD.2026.0904",),
            android_versions=("17",),
            bootloader_states=("unlocked",),
            partitions=("boot",),
            scope_note="Exact fixture target and build only.",
        ),
        source_ids=(source_id,),
        confidence=confidence,
        corroboration_count=corroboration_count,
        operations=(operation,) if operation else (),
    )


def _archive(source: KnowledgeSource, record: KnowledgeRecord) -> KnowledgeArchive:
    return seal_archive(
        KnowledgeArchive(
            schema_version=ARCHIVE_SCHEMA_VERSION,
            bundle_id="fixture-bundle",
            updated_at="2026-09-04T10:00:00+00:00",
            sources=(source,),
            records=(record,),
            bundle_digest="",
        )
    )


def _write_bundle(path, archive: KnowledgeArchive) -> None:
    path.write_text(json.dumps(archive_mapping(archive), indent=2), encoding="utf-8")


def test_packaged_archive_promotes_the_existing_broad_multi_oem_brain() -> None:
    archive = load_packaged_archive()
    manufacturers = {value for record in archive.records for value in record.scope.manufacturers}

    assert len(archive.records) >= 280
    assert len(archive.sources) >= 180
    assert {
        "samsung",
        "huawei",
        "google",
        "xiaomi",
        "oneplus",
        "sony",
        "motorola",
        "nothing",
        "oppo",
        "realme",
        "vivo",
        "asus",
        "fairphone",
        "tecno",
        "infinix",
        "itel",
    } <= manufacturers
    assert any(source.tier is KnowledgeSourceTier.COMMUNITY for source in archive.sources)
    assert any(source.tier is KnowledgeSourceTier.OFFICIAL_VENDOR for source in archive.sources)
    assert any(source.tier is KnowledgeSourceTier.OFFICIAL_PLATFORM for source in archive.sources)
    record_ids = {record.record_id for record in archive.records}
    assert {
        "official.motorola-software-fix-boundary",
        "official.sony-post-update-startup-window",
        "community.samsung-g920f-sw-rev-check",
        "community.realme6-volume-button-recovery-loop",
        "community.cph2573-kitsune-init-boot",
        "community.huawei-vnsl31-cross-region-negative",
        "community.nothing-phone1-power-button-loop",
        "platform.update-engine-payload-timestamp-downgrade",
        "platform.avb-restore-consistent-chain",
        "identity.motorola-capri-variants",
        "identity.samsung-klte-models-and-firmware",
        "identity.oneplus8t-kebab-regional-models",
        "community.samsung-m31s-vbmeta-hash-mismatch",
        "platform.fastboot-locked-flashing-refusal",
        "platform.fastboot-not-enough-super-space",
        "platform.adb-unauthorized-state",
        "official.pixel-may2025-bootloader-antirollback",
        "community.oneplus6t-critical-refusal-wrong-mode",
        "community.xiaomi-miflash-lock-checkpoint-wrapper",
        "identity.samsung-beyond0lte-models",
        "identity.oneplus-waffle-models",
        "identity.motorola-dubai-models",
        "identity.sony-pdx203-models",
        "identity.nothing-spacewar-a063",
        "identity.asus-sake-models",
        "identity.xiaomi-surya-models",
        "platform.boot-init-boot-launch-boundary",
        "platform.recovery-partition-presence",
        "platform.system-dlkm-gki-coherence",
        "platform.vendor-odm-dlkm-coherence",
        "official.pixel6-vendor-ramdisk-platform-match",
        "official.pixel7plus-vendor-kernel-boot-layout",
    } <= record_ids


def test_init_boot_failure_uses_launch_architecture_not_current_android_alone(
    tmp_path,
) -> None:
    report = OfflineKnowledgeService(tmp_path / "workspace").lookup(
        KnowledgeQuery(
            android_versions=("15",),
            partitions=("boot", "vendor_boot"),
            error_codes=("No such partition: init_boot",),
            finding_ids=("boot.layout.launch_version_unknown",),
            evidence_terms=("init_boot target uncertain",),
        ),
        trigger="boot-layout-failure",
    )

    match = report.matches[0]
    assert match.record.record_id == "platform.boot-init-boot-launch-boundary"
    assert match.confidence is MatchConfidence.HIGH
    assert "original android launch version" in match.record.diagnostic_steps[0].casefold()
    assert report.execution_authority == "none"


def test_system_dlkm_module_error_ranks_exact_gki_coherence_diagnosis(tmp_path) -> None:
    report = OfflineKnowledgeService(tmp_path / "workspace").lookup(
        KnowledgeQuery(
            partitions=("boot", "system_dlkm", "super"),
            error_codes=("disagrees about version of symbol",),
            finding_ids=("kernel.system_dlkm.gki_mismatch",),
            evidence_terms=("GKI module mismatch after boot image change",),
        ),
        trigger="kernel-boot-failure",
    )

    match = report.matches[0]
    assert match.record.record_id == "platform.system-dlkm-gki-coherence"
    assert match.confidence is MatchConfidence.HIGH
    assert match.record.operations == ()


def test_pixel_partition_generation_records_do_not_cross_match(tmp_path) -> None:
    service = OfflineKnowledgeService(tmp_path / "workspace")
    pixel6 = service.lookup(
        KnowledgeQuery(
            manufacturers=("google",),
            brands=("pixel",),
            models=("Pixel 6a",),
            codenames=("bluejay",),
            bootloader_states=("unlocked",),
            finding_ids=("pixel6.vendor_ramdisk.platform_mismatch",),
        ),
        trigger="kernel-boot-failure",
    )
    pixel7 = service.lookup(
        KnowledgeQuery(
            manufacturers=("google",),
            brands=("pixel",),
            models=("Pixel 7",),
            codenames=("panther",),
            bootloader_states=("unlocked",),
            finding_ids=("pixel.vendor_kernel_boot.layout",),
        ),
        trigger="partition-identification",
    )

    assert pixel6.matches[0].record.record_id == ("official.pixel6-vendor-ramdisk-platform-match")
    assert "official.pixel7plus-vendor-kernel-boot-layout" not in {
        match.record.record_id for match in pixel6.matches
    }
    assert pixel7.matches[0].record.record_id == ("official.pixel7plus-vendor-kernel-boot-layout")
    assert "official.pixel6-vendor-ramdisk-platform-match" not in {
        match.record.record_id for match in pixel7.matches
    }


def test_exact_update_engine_code_ranks_platform_diagnosis_first(tmp_path) -> None:
    report = OfflineKnowledgeService(tmp_path / "workspace").lookup(
        KnowledgeQuery(
            symptoms=("ADB sideload aborted with status 1",),
            error_codes=("PAYLOAD_TIMESTAMP_ERROR",),
        ),
        trigger="ota-failure",
    )

    assert report.matches[0].record.record_id == (
        "platform.update-engine-payload-timestamp-downgrade"
    )
    assert report.matches[0].confidence is MatchConfidence.HIGH
    assert "exact error" in report.matches[0].explanation.casefold()


def test_device_alias_and_codename_find_the_maintained_variant(tmp_path) -> None:
    report = OfflineKnowledgeService(tmp_path / "workspace").lookup(
        KnowledgeQuery(
            manufacturers=("motorola",),
            models=("moto g10 power",),
            codenames=("capri",),
        ),
        trigger="device-dna",
    )

    assert report.matches[0].record.record_id == "identity.motorola-capri-variants"
    assert report.matches[0].confidence is MatchConfidence.MEDIUM
    assert "exact codename" in report.matches[0].explanation.casefold()


def test_exact_samsung_s10_model_excludes_neighboring_codenames(tmp_path) -> None:
    report = OfflineKnowledgeService(tmp_path / "workspace").lookup(
        KnowledgeQuery(
            manufacturers=("samsung",),
            brands=("galaxy",),
            models=("SM-G973F",),
            codenames=("beyond1lte",),
        ),
        trigger="device-dna",
    )

    ids = {match.record.record_id for match in report.matches}
    assert report.matches[0].record.record_id == "identity.samsung-beyond1lte-models"
    assert "identity.samsung-beyond0lte-models" not in ids
    assert "identity.samsung-beyond2lte-models" not in ids
    assert report.matches[0].confidence is MatchConfidence.MEDIUM


def test_nothing_spacewar_model_maps_without_transferring_pong(tmp_path) -> None:
    report = OfflineKnowledgeService(tmp_path / "workspace").lookup(
        KnowledgeQuery(
            manufacturers=("nothing",),
            models=("A063",),
            codenames=("Spacewar",),
        ),
        trigger="device-dna",
    )

    ids = {match.record.record_id for match in report.matches}
    assert report.matches[0].record.record_id == "identity.nothing-spacewar-a063"
    assert "identity.nothing-pong-models" not in ids
    assert report.execution_authority == "none"


def test_generic_fastboot_resize_error_ranks_platform_diagnosis_first(tmp_path) -> None:
    report = OfflineKnowledgeService(tmp_path / "workspace").lookup(
        KnowledgeQuery(
            symptoms=(
                "Resizing 'system_a' FAILED (remote: 'Not enough space to resize partition')",
            ),
            error_codes=("Not enough space to resize partition",),
            partitions=("system_a", "super"),
        ),
        trigger="fastboot-failure",
    )

    assert report.matches[0].record.record_id == "platform.fastboot-not-enough-super-space"
    assert report.matches[0].confidence is MatchConfidence.HIGH
    assert report.execution_authority == "none"
    assert "do not delete" in report.matches[0].record.fix_steps[1].casefold()


def test_exact_pixel3axl_resize_outcome_stays_scoped_and_execution_inert(tmp_path) -> None:
    report = OfflineKnowledgeService(tmp_path / "workspace").lookup(
        KnowledgeQuery(
            manufacturers=("google",),
            brands=("pixel",),
            models=("Pixel 3a XL",),
            codenames=("bonito",),
            android_versions=("11",),
            bootloader_states=("unlocked",),
            partitions=("system_a", "super"),
            error_codes=(
                "Resizing 'system_a' FAILED (remote: 'Not enough space to resize partition')",
            ),
        ),
        trigger="fastboot-failure",
    )

    match = report.matches[0]
    assert match.record.record_id == "community.pixel3axl-resize-android-flash-tool"
    assert match.confidence is MatchConfidence.MEDIUM
    assert match.record.corroboration_count == 1
    assert match.record.operations == ()
    assert report.execution_authority == "none"


def test_adb_unauthorized_is_not_misdiagnosed_as_offline_or_driver_failure(tmp_path) -> None:
    report = OfflineKnowledgeService(tmp_path / "workspace").lookup(
        KnowledgeQuery(
            symptoms=("device unauthorized. Please check the confirmation dialog on your device",),
            error_codes=("unauthorized",),
        ),
        trigger="device-discovery-failure",
    )

    assert report.matches[0].record.record_id == "platform.adb-unauthorized-state"
    assert report.matches[0].confidence is MatchConfidence.HIGH
    assert "owner approval" in report.matches[0].record.summary.casefold()


def test_archive_store_seeds_private_integrity_checked_local_data(tmp_path) -> None:
    store = KnowledgeArchiveStore(tmp_path / "workspace")
    seeded = store.ensure_seeded()
    loaded = store.load()

    assert loaded == seeded
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    raw = json.loads(store.path.read_text(encoding="utf-8"))
    raw["records"][0]["title"] = "tampered"
    store.path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(KnowledgeArchiveError, match="digest mismatch"):
        store.load()


def test_existing_local_archive_receives_new_packaged_records(tmp_path) -> None:
    store = KnowledgeArchiveStore(tmp_path / "workspace")
    store.save(_archive(_source(), _record()))

    upgraded = store.ensure_seeded()

    record_ids = {record.record_id for record in upgraded.records}
    assert "fixture.exact-boot-repair" in record_ids
    assert "platform.update-engine-install-device-open" in record_ids
    assert len(upgraded.records) >= 222
    assert store.load() == upgraded


def test_packaged_upgrade_preserves_a_newer_local_record_revision(tmp_path) -> None:
    packaged = load_packaged_archive()
    original = next(
        record
        for record in packaged.records
        if record.record_id == "platform.update-engine-not-enough-space"
    )
    newer = replace(
        original,
        revision=original.revision + 1,
        title="Locally reviewed update-engine space diagnosis",
    )
    sources = tuple(source for source in packaged.sources if source.source_id in newer.source_ids)
    local = seal_archive(
        KnowledgeArchive(
            schema_version=ARCHIVE_SCHEMA_VERSION,
            bundle_id="local-reviewed-bundle",
            updated_at="2026-09-05T00:00:00+00:00",
            sources=sources,
            records=(newer,),
            bundle_digest="",
        )
    )
    store = KnowledgeArchiveStore(tmp_path / "workspace")
    store.save(local)

    upgraded = store.ensure_seeded()
    retained = next(record for record in upgraded.records if record.record_id == newer.record_id)

    assert retained.revision == newer.revision
    assert retained.title == newer.title


def test_archive_store_rejects_linked_data_without_touching_the_target(tmp_path) -> None:
    store = KnowledgeArchiveStore(tmp_path / "workspace")
    store.ensure_seeded()
    original = store.path.read_bytes()
    outside = tmp_path / "outside-archive.json"
    outside.write_bytes(original)
    store.path.unlink()
    store.path.symlink_to(outside)

    with pytest.raises(KnowledgeArchiveError, match="unavailable"):
        store.load()

    assert outside.read_bytes() == original


def test_imported_exact_record_outranks_broad_guidance_and_explains_safety(tmp_path) -> None:
    operation = KnowledgeOperation(
        operation_id="restore-exact-boot",
        label="Restore the exact verified stock boot image",
        kind="restore-partition-image",
        changes_device=True,
        target_partitions=("boot",),
        verified_input_requirements=("stock-boot-sha256",),
        rollback_route="official-stock-restore",
    )
    incoming = _archive(_source(), _record(operation=operation))
    bundle_path = tmp_path / "exact-device-bundle.json"
    _write_bundle(bundle_path, incoming)
    workspace = tmp_path / "workspace"

    result = KnowledgeArchiveStore(workspace).import_bundle(bundle_path)
    query = KnowledgeQuery(
        manufacturers=("RadForge",),
        brands=("RadPhone",),
        models=("RP1",),
        codenames=("rad",),
        build_ids=("RAD.2026.0904",),
        android_versions=("17",),
        bootloader_states=("unlocked",),
        partitions=("boot",),
        symptoms=("boot verification failed with E_BOOT_42",),
        error_codes=("E_BOOT_42",),
        finding_ids=("boot.incomplete",),
        verified_inputs=("stock-boot-sha256",),
        rollback_routes=("official-stock-restore",),
    )
    report = OfflineKnowledgeService(workspace).lookup(query, trigger="flash-failure")

    assert result.added == 1
    assert report.matches[0].record.record_id == "fixture.exact-boot-repair"
    assert report.matches[0].confidence is MatchConfidence.EXACT
    assert "exact error" in report.matches[0].explanation.casefold()
    assert "separate Guardian review" in report.matches[0].safety
    assert report.execution_authority == "none"


def test_device_change_remains_locked_when_verified_input_or_rollback_is_missing(tmp_path) -> None:
    operation = KnowledgeOperation(
        operation_id="restore-exact-boot",
        label="Restore the exact verified stock boot image",
        kind="restore-partition-image",
        changes_device=True,
        target_partitions=("boot",),
        verified_input_requirements=("stock-boot-sha256",),
        rollback_route="official-stock-restore",
    )
    bundle_path = tmp_path / "exact-device-bundle.json"
    _write_bundle(bundle_path, _archive(_source(), _record(operation=operation)))
    workspace = tmp_path / "workspace"
    KnowledgeArchiveStore(workspace).import_bundle(bundle_path)

    report = OfflineKnowledgeService(workspace).lookup(
        KnowledgeQuery(
            models=("RP1",),
            codenames=("rad",),
            build_ids=("RAD.2026.0904",),
            partitions=("boot",),
            error_codes=("E_BOOT_42",),
        )
    )

    assert report.matches[0].record.record_id == "fixture.exact-boot-repair"
    assert report.matches[0].safety.startswith("LOCKED")
    assert report.execution_authority == "none"


def test_family_level_device_change_is_rejected_at_import_boundary(tmp_path) -> None:
    operation = KnowledgeOperation(
        operation_id="unsafe-family-flash",
        label="Unsafe family-level flash",
        kind="restore-partition-image",
        changes_device=True,
        target_partitions=("boot",),
        verified_input_requirements=("some-image",),
        rollback_route="some-route",
    )
    broad = replace(
        _record(operation=operation),
        scope=DeviceKnowledgeScope(
            manufacturers=("RadForge",),
            partitions=("boot",),
            scope_note="Only a family name is known.",
        ),
    )
    bundle_path = tmp_path / "unsafe-family-bundle.json"
    _write_bundle(bundle_path, _archive(_source(), broad))

    with pytest.raises(KnowledgeArchiveError, match="exact target/build"):
        KnowledgeArchiveStore(tmp_path / "workspace").import_bundle(bundle_path)


def test_one_explicit_community_success_is_usable_evidence(tmp_path) -> None:
    source = _source("community.fixture", tier=KnowledgeSourceTier.COMMUNITY)
    record = _record(
        "community.one-reported-success",
        source_id=source.source_id,
        confidence=KnowledgeConfidence.MEDIUM,
        corroboration_count=1,
    )
    bundle_path = tmp_path / "community-success.json"
    _write_bundle(bundle_path, _archive(source, record))
    workspace = tmp_path / "workspace"

    result = KnowledgeArchiveStore(workspace).import_bundle(bundle_path)
    report = OfflineKnowledgeService(workspace).lookup(
        KnowledgeQuery(
            models=("RP1",),
            codenames=("rad",),
            build_ids=("RAD.2026.0904",),
            error_codes=("E_BOOT_42",),
        )
    )

    assert result.added == 1
    match = report.matches[0]
    assert match.record.record_id == record.record_id
    assert match.record.corroboration_count == 1
    assert match.provenance[0].tier is KnowledgeSourceTier.COMMUNITY
    assert "corroborated outcome/report count: 1" in report.plain_text


def test_device_dna_capture_automatically_queries_the_local_archive(tmp_path) -> None:
    store, registry, project, inspection = _project(tmp_path)
    service = DeviceDnaService(store, registry)

    service.refresh(project.project_id, _device(), inspection)

    assert service.knowledge_lookup_error == ""
    assert service.last_knowledge_lookup is not None
    assert service.last_knowledge_lookup.trigger == "device-dna"
    assert service.last_knowledge_lookup.archive_digest
    assert (store.workspace / "knowledge" / "archive.romverse").is_file()


def test_typed_boot_failure_requeries_device_dna_and_ranks_exact_error(tmp_path) -> None:
    store, registry, project, inspection = _project(tmp_path)
    service = DeviceDnaService(store, registry)
    service.refresh(project.project_id, _device(), inspection)

    report = service.scan_knowledge_after_failure(
        project.project_id,
        KnowledgeFailure(
            phase="boot",
            message="ODIN MODE (AVB FAIL) vbmeta HASH_MISMATCH(3)",
            error_codes=("HASH_MISMATCH(3)",),
            finding_ids=("security.verified_boot", "boot.incomplete"),
            partition="vbmeta",
        ),
    )

    assert report is not None
    assert report.matches[0].record.record_id == "core.verified-boot-red-triage"
    assert "exact error" in report.matches[0].explanation.casefold()
    assert report.execution_authority == "none"
    assert "EXECUTION AUTHORITY • NONE" in report.plain_text


def test_typed_boot_failure_uses_new_boot_chain_pack_through_device_dna_service(
    tmp_path,
) -> None:
    store, registry, project, inspection = _project(tmp_path)
    service = DeviceDnaService(store, registry)
    service.refresh(project.project_id, _device(), inspection)

    report = service.scan_knowledge_after_failure(
        project.project_id,
        KnowledgeFailure(
            phase="boot-layout",
            message="fastboot: FAILED (remote: No such partition: init_boot)",
            error_codes=("No such partition: init_boot",),
            finding_ids=("boot.layout.launch_version_unknown",),
            partition="init_boot",
        ),
    )

    assert report is not None
    assert report.matches[0].record.record_id == "platform.boot-init-boot-launch-boundary"
    assert report.matches[0].confidence is MatchConfidence.HIGH
    assert report.matches[0].record.operations == ()
    assert report.execution_authority == "none"
    assert service.last_knowledge_lookup == report


def test_exact_failure_symptom_outranks_unrelated_device_profile_terms(tmp_path) -> None:
    store, registry, project, inspection = _project(tmp_path)
    service = DeviceDnaService(store, registry)
    service.refresh(project.project_id, _device(), inspection)

    report = service.scan_knowledge_after_failure(
        project.project_id,
        KnowledgeFailure(
            phase="build",
            message="adb: error: more than one device/emulator",
            finding_ids=("build.operation_failed",),
            operation="extract",
        ),
    )

    assert report is not None
    assert report.matches[0].record.record_id == "catalog.adb-multiple-targets"
    assert "failure symptom" in report.matches[0].explanation.casefold()
