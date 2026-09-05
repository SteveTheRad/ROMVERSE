from __future__ import annotations

import hashlib
import json
import stat
import struct
import zipfile
from dataclasses import replace
from types import SimpleNamespace

import pytest

from romverse.device.dna import (
    CapabilityState,
    DeviceDnaService,
    DeviceDnaStore,
    EvidenceConfidence,
)
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.models import (
    DeviceBuildContract,
    DevicePack,
    DynamicPartitionGroup,
    FirmwareSourceContract,
    PartitionBuildRule,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.rom.inspection import ContainerKind, RomInspectionService
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


def _source(tmp_path, name="popsicle-ota_full-OS4.0.0.23.XPBCNXM-user-17.0-test.zip"):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("payload.bin", b"CrAU test payload")
        archive.writestr("META-INF/com/android/metadata", b"ota-type=AB")
    return path


def _pack(source_sha256: str) -> DevicePack:
    contract = DeviceBuildContract(
        "popsicle-test-contract",
        1,
        FirmwareSourceContract("OS4.0.0.23.XPBCNXM", source_sha256, "0" * 64),
        12_884_901_888,
        65_536,
        3,
        True,
        (
            DynamicPartitionGroup("popsicle_dynamic_partitions_a", 6_000_000_000),
            DynamicPartitionGroup("popsicle_dynamic_partitions_b", 6_000_000_000),
        ),
        (
            PartitionBuildRule(
                "product",
                2_000_000_000,
                2_100_000_000,
                "popsicle_dynamic_partitions_a",
                "erofs",
                "rebuild",
                "1" * 64,
            ),
        ),
        ("product",),
        "2" * 64,
        "3" * 64,
        ("product.img",),
    )
    return DevicePack(
        "xiaomi.popsicle.test",
        "1",
        "Xiaomi 17 Pro Max",
        500,
        ("xiaomi",),
        ("2509fpn0bc",),
        ("popsicle",),
        (),
        (),
        "4" * 64,
        contract,
    )


def _device(**changes) -> AndroidDevice:
    return replace(
        AndroidDevice(
            "PRIVATE-SERIAL",
            DeviceState.DEVICE,
            manufacturer="Xiaomi",
            brand="Xiaomi",
            model="2509FPN0BC",
            marketing_name="Xiaomi 17 Pro Max",
            product="popsicle",
            codename="popsicle",
            android_version="17",
            build_id="BP1A",
            rom_display="OS4.0.0.23.XPBCNXM",
            security_patch="2026-08-01",
            bootloader_locked=False,
            verified_boot="orange",
            root_detected=False,
            slot_suffix="_a",
            kernel_version="6.12.23-popsicle",
            soc_platform="Snapdragon 8 Elite Gen 5",
            encryption_state="encrypted",
            encryption_type="file",
            ab_update=True,
            virtual_ab=True,
            dynamic_partitions=True,
            fastboot_capability="fastbootd reported by Android",
        ),
        **changes,
    )


def _project(tmp_path, *, exact=True):
    source = _source(tmp_path)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Device DNA", "xiaomi.popsicle.test" if exact else "")
    project = store.import_original(project.project_id, source)
    pack = _pack(project.original.sha256)
    registry = DevicePackRegistry((pack,)) if exact else DevicePackRegistry(())
    report = RomInspectionService(store).inspect_project(project.project_id)
    return store, registry, project, report


def test_device_dna_combines_live_source_inspection_and_exact_pack_evidence(tmp_path):
    store, registry, project, report = _project(tmp_path)

    profile = DeviceDnaService(store, registry).refresh(project.project_id, _device(), report)

    assert profile.fact("identity.marketing_name").value == "Xiaomi 17 Pro Max"
    assert profile.fact("identity.brand").value == "Xiaomi"
    assert profile.fact("soc.platform").value == "Snapdragon 8 Elite Gen 5"
    assert profile.fact("firmware.upgrade_relationship").value == (
        "SAME FIRMWARE VERSION • OS4.0.0.23.XPBCNXM → OS4.0.0.23.XPBCNXM"
    )
    assert profile.fact("partition.ab_scheme").value == "Virtual A/B"
    assert profile.fact("security.encryption").value == "encrypted / file"
    assert profile.fact("capability.fastboot").confidence is EvidenceConfidence.HIGH
    assert profile.partitions[0].name == "product"
    assert profile.partitions[0].size_bytes == 2_100_000_000
    assert profile.capability("device_identity").state is CapabilityState.SUPPORTED
    assert profile.capability("firmware_detection").state is CapabilityState.SUPPORTED
    assert profile.capability("partition_mapping").state is CapabilityState.SUPPORTED
    assert profile.capability("rom_build").state is CapabilityState.SUPPORTED
    assert profile.capability("guardian_flash").state is CapabilityState.UNCONFIRMED
    assert profile.capability("root_state").state is CapabilityState.UNCONFIRMED
    assert profile.fact("root.state").value == "Active root was not confirmed"
    assert profile.capability("bootloader_relock").state is CapabilityState.UNSUPPORTED
    assert profile.bootloader_relock_permitted is False


def test_device_dna_keeps_manager_presence_separate_from_active_root(tmp_path):
    store, registry, project, report = _project(tmp_path)
    device = _device(
        root_manager_candidate="magisk",
        root_manager_evidence="allowlisted-package-presence",
        root_signal_source="adb-shell-id",
    )

    profile = DeviceDnaService(store, registry).refresh(project.project_id, device, report)

    assert profile.capability("root_state").state is CapabilityState.CAUTION
    assert "does not prove" in profile.capability("root_state").detail
    assert profile.fact("root.manager_candidate").value == "Magisk Manager candidate"
    assert profile.fact("root.state").value.endswith("active root unconfirmed")


def test_recognized_source_without_exact_contract_is_caution_not_build_authority(tmp_path):
    store, registry, project, report = _project(tmp_path, exact=False)

    profile = DeviceDnaService(store, registry).refresh(project.project_id, _device(), report)

    assert profile.capability("rom_build").state is CapabilityState.CAUTION
    assert profile.capability("guardian_flash").state is CapabilityState.UNCONFIRMED
    assert "execution contract" in profile.capability("guardian_flash").detail
    assert not profile.partitions
    assert any("exact source-bound" in warning for warning in profile.warnings)


def test_device_dna_identifies_newer_same_device_firmware_as_candidate_only(tmp_path):
    store, registry, _project_record, _report = _project(
        tmp_path,
        exact=False,
    )
    newer_source = _source(
        tmp_path,
        "popsicle-ota_full-OS4.0.0.25.XPBCNXM-user-17.0-newer.zip",
    )
    newer_project = store.import_original(store.create("Newer candidate").project_id, newer_source)
    newer_report = RomInspectionService(store).inspect_project(newer_project.project_id)

    profile = DeviceDnaService(store, registry).refresh(
        newer_project.project_id,
        _device(),
        newer_report,
    )

    relationship = profile.fact("firmware.upgrade_relationship")
    assert relationship is not None
    assert relationship.value == ("UPGRADE CANDIDATE • OS4.0.0.23.XPBCNXM → OS4.0.0.25.XPBCNXM")
    assert relationship.confidence is EvidenceConfidence.HIGH
    assert any("version relationship only" in warning for warning in profile.warnings)
    assert profile.capability("guardian_flash").state is CapabilityState.UNCONFIRMED


def test_device_dna_uses_standard_ota_metadata_for_an_unknown_android_brand(tmp_path):
    source = tmp_path / "official-update.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"CrAU test payload")
        archive.writestr(
            "META-INF/com/android/metadata",
            b"\n".join(
                (
                    b"ota-type=AB",
                    b"pre-device=rad",
                    b"pre-build-incremental=100",
                    b"post-build=radforge/rad/rad:15/AP4A.260901.001/200:user/release-keys",
                    b"post-build-incremental=200",
                    b"post-sdk-level=35",
                    b"post-security-patch-level=2026-09-01",
                    b"post-timestamp=200",
                )
            ),
        )
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Generic OTA").project_id, source)
    report = RomInspectionService(store).inspect_project(project.project_id)
    device = AndroidDevice(
        "PRIVATE-GENERIC",
        DeviceState.DEVICE,
        manufacturer="RadForge",
        model="Universal One",
        product="rad_global",
        codename="rad",
        vendor_device="rad",
        api_level="35",
        build_id="AP4A",
        build_incremental="100",
        build_timestamp_utc=100,
    )

    profile = DeviceDnaService(store, DevicePackRegistry(())).refresh(
        project.project_id, device, report
    )

    assert profile.fact("identity.product").value == "rad_global"
    assert profile.fact("identity.vendor_device").value == "rad"
    assert profile.fact("software.live_incremental").value == "100"
    assert profile.fact("software.build").value == "200"
    assert profile.fact("software.android_version").value == "15"
    assert profile.fact("firmware.ota_post_brand").value == "radforge"
    assert profile.fact("firmware.ota_post_product").value == "rad"
    assert profile.fact("firmware.ota_post_device").value == "rad"
    assert profile.fact("firmware.ota_post_android").value == "15"
    assert profile.fact("firmware.ota_post_build_id").value == "AP4A.260901.001"
    assert profile.fact("firmware.ota_post_sdk").value == "35"
    assert profile.fact("firmware.ota_post_security_patch").value == "2026-09-01"
    assert profile.fact("firmware.upgrade_relationship").value == ("UPGRADE CANDIDATE • AP4A → 200")
    assert any(item.evidence_id == "source.ota_metadata" for item in profile.evidence)
    assert profile.capability("firmware_detection").state is CapabilityState.SUPPORTED
    assert profile.capability("guardian_flash").state is CapabilityState.UNCONFIRMED


def test_missing_pack_does_not_soften_proven_ota_target_mismatch(tmp_path):
    source = tmp_path / "wrong-target-update.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"CrAU test payload")
        archive.writestr(
            "META-INF/com/android/metadata",
            b"pre-device=another-device\npost-build-incremental=200",
        )
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Wrong OTA target").project_id, source)
    report = RomInspectionService(store).inspect_project(project.project_id)

    profile = DeviceDnaService(store, DevicePackRegistry(())).refresh(
        project.project_id,
        _device(),
        report,
    )

    assert profile.fact("firmware.upgrade_relationship").value == "INCOMPATIBLE FIRMWARE"
    assert profile.capability("device_identity").state is CapabilityState.UNSUPPORTED
    assert profile.capability("guardian_flash").state is CapabilityState.UNSUPPORTED
    assert "proves" in profile.capability("guardian_flash").detail


def test_device_dna_preserves_conflicting_ota_evidence_for_offline_diagnosis(tmp_path):
    source = tmp_path / "conflicting-update.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"CrAU test payload")
        archive.writestr(
            "META-INF/com/android/metadata",
            b"\n".join(
                (
                    b"pre-device=rad",
                    b"pre-build-incremental=100",
                    b"post-build-incremental=200",
                    b"post-sdk-level=34",
                    b"post-security-patch-level=2026-09-01",
                    b"post-timestamp=300",
                )
            ),
        )
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Conflicting OTA").project_id, source)
    report = RomInspectionService(store).inspect_project(project.project_id)
    device = AndroidDevice(
        "PRIVATE-GENERIC",
        DeviceState.DEVICE,
        manufacturer="RadForge",
        model="Universal One",
        product="rad",
        codename="rad",
        api_level="35",
        build_id="AP4A",
        build_incremental="100",
        build_timestamp_utc=200,
        security_patch="2026-08-01",
    )

    profile = DeviceDnaService(store, DevicePackRegistry(())).refresh(
        project.project_id, device, report
    )

    assert profile.fact("firmware.upgrade_relationship").value.endswith("VERSION EVIDENCE CONFLICT")
    assert any("will not guess" in warning for warning in profile.warnings)
    assert any("Android SDK: live 35; OTA 34 (older)" in warning for warning in profile.warnings)
    assert any(
        "Build timestamp: live 200; OTA 300 (newer)" in warning for warning in profile.warnings
    )
    assert profile.capability("guardian_flash").state is CapabilityState.UNCONFIRMED


def test_device_dna_consumes_current_project_local_source_blueprint_without_flash_authority(
    tmp_path,
    monkeypatch,
):
    source = _source(tmp_path)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Blueprint DNA").project_id, source)
    blueprint = SimpleNamespace(
        project_id=project.project_id,
        source_archive_sha256=project.original.sha256,
        source_kind="ota-payload",
        baseline_candidate_ready=True,
        phone_changed=False,
        authority="project-local-build-evidence-only",
        blueprint_digest="a" * 64,
        plan_digest="b" * 64,
        manufacturer="Xiaomi",
        codename="popsicle",
        build_id="OS4.0.0.23.XPBCNXM",
        android_version="17",
        region="CN",
        partitions=(
            SimpleNamespace(name="product", estimated_bytes=2_000_000, image_format="unknown"),
            SimpleNamespace(name="system", estimated_bytes=3_000_000, image_format="unknown"),
        ),
    )
    monkeypatch.setattr(
        "romverse.device.dna.FirmwareSourceIntelligenceService.load",
        lambda _self, _project_id: blueprint,
    )

    profile = DeviceDnaService(store, DevicePackRegistry(())).refresh(
        project.project_id,
        _device(),
    )

    source_evidence = next(
        item for item in profile.evidence if item.evidence_id == "source.blueprint"
    )
    assert source_evidence.confidence is EvidenceConfidence.VERIFIED
    assert source_evidence.source_ref == "a" * 64
    assert profile.fact("firmware.adapter").value == "Android OTA payload"
    assert profile.fact("firmware.adapter").evidence_ids == ("source.blueprint",)
    assert profile.fact("software.build").confidence is EvidenceConfidence.VERIFIED
    assert profile.fact("software.build").evidence_ids == ("source.blueprint",)
    assert profile.fact("software.region").value == "China"
    assert profile.fact("software.region").evidence_ids == ("source.blueprint",)
    assert profile.capability("device_identity").evidence_ids == (
        "device.live",
        "source.blueprint",
    )
    assert profile.fact("firmware.tool_profile").value == "Python, Payload Dumper, AVBTool"
    assert tuple(item.name for item in profile.partitions) == ("product", "system")
    assert profile.capability("source_adapter").state is CapabilityState.SUPPORTED
    assert profile.capability("tool_resolution").state is CapabilityState.SUPPORTED
    assert profile.capability("partition_mapping").state is CapabilityState.CAUTION
    assert profile.capability("rom_build").state is CapabilityState.SUPPORTED
    assert "local baseline" in profile.capability("rom_build").detail
    assert profile.capability("guardian_flash").state is CapabilityState.UNCONFIRMED
    assert any("Flash authority remains unavailable" in item for item in profile.warnings)
    assert profile.bootloader_relock_permitted is False


def test_device_dna_rejects_blueprint_that_is_not_bound_to_the_exact_project_source(
    tmp_path,
    monkeypatch,
):
    source = _source(tmp_path)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Wrong blueprint DNA").project_id, source)
    blueprint = SimpleNamespace(
        project_id="another-project-12345678",
        source_archive_sha256="0" * 64,
        source_kind="ota-payload",
        baseline_candidate_ready=True,
        phone_changed=False,
        authority="project-local-build-evidence-only",
        blueprint_digest="a" * 64,
        plan_digest="b" * 64,
        partitions=(SimpleNamespace(name="product", estimated_bytes=2_000_000),),
    )
    monkeypatch.setattr(
        "romverse.device.dna.FirmwareSourceIntelligenceService.load",
        lambda _self, _project_id: blueprint,
    )

    profile = DeviceDnaService(store, DevicePackRegistry(())).refresh(
        project.project_id,
        _device(),
    )

    assert all(item.evidence_id != "source.blueprint" for item in profile.evidence)
    assert profile.capability("source_adapter").state is CapabilityState.UNCONFIRMED
    assert profile.capability("tool_resolution").state is CapabilityState.UNCONFIRMED
    assert profile.capability("rom_build").state is CapabilityState.CAUTION
    assert profile.capability("guardian_flash").state is CapabilityState.UNCONFIRMED


def test_unknown_named_payload_is_detected_after_structure_inspection_without_guessing_phone(
    tmp_path,
):
    source = _source(tmp_path, "mystery-build.zip")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Unknown DNA").project_id, source)
    report = RomInspectionService(store).inspect_project(project.project_id)

    profile = DeviceDnaService(store, DevicePackRegistry(())).refresh(
        project.project_id,
        inspection=report,
    )

    assert profile.fact("identity.model").value == "Unconfirmed"
    assert profile.fact("identity.model").confidence is EvidenceConfidence.UNCONFIRMED
    assert profile.capability("device_identity").state is CapabilityState.UNCONFIRMED
    assert profile.fact("firmware.package_format").value.startswith("Android OTA payload")
    assert profile.fact("firmware.adapter").value == "Android OTA payload"
    assert profile.fact("partition.discovered").value == "ota_payload"
    assert profile.capability("firmware_detection").state is CapabilityState.SUPPORTED
    assert profile.capability("source_adapter").state is CapabilityState.SUPPORTED
    assert profile.capability("tool_resolution").state is CapabilityState.SUPPORTED
    assert "Payload Dumper" in profile.fact("firmware.tool_profile").value
    assert profile.capability("rom_build").state is CapabilityState.UNCONFIRMED


def test_readable_non_android_zip_never_becomes_confirmed_firmware(tmp_path):
    source = tmp_path / "ordinary-download.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("notes/readme.txt", "not Android firmware")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Not firmware").project_id, source)
    report = RomInspectionService(store).inspect_project(project.project_id)

    profile = DeviceDnaService(store, DevicePackRegistry(())).refresh(
        project.project_id,
        inspection=report,
    )

    assert profile.fact("firmware.package_format").value == "Unconfirmed"
    assert profile.fact("firmware.adapter").value == "Unconfirmed"
    assert profile.capability("firmware_detection").state is CapabilityState.UNCONFIRMED
    assert profile.capability("source_adapter").state is CapabilityState.UNCONFIRMED
    assert profile.capability("tool_resolution").state is CapabilityState.UNCONFIRMED
    assert profile.fact("firmware.tool_profile").value == "Unconfirmed"
    assert any("no supported Android" in warning for warning in profile.warnings)


def test_unknown_named_super_archive_selects_fastboot_adapter_without_build_authority(tmp_path):
    source = tmp_path / "vendor-package.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("images/super.img", b"unextracted super image")
        archive.writestr("android-info.txt", "require board=test")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Super source").project_id, source)
    report = RomInspectionService(store).inspect_project(project.project_id)

    profile = DeviceDnaService(store, DevicePackRegistry(())).refresh(
        project.project_id,
        inspection=report,
    )

    assert profile.fact("firmware.adapter").value == "Android fastboot / super source"
    assert profile.capability("firmware_detection").state is CapabilityState.SUPPORTED
    assert profile.capability("source_adapter").state is CapabilityState.SUPPORTED
    assert profile.capability("tool_resolution").state is CapabilityState.SUPPORTED
    assert "LP Dump" in profile.fact("firmware.tool_profile").value
    assert profile.capability("rom_build").state is CapabilityState.UNCONFIRMED
    assert profile.capability("guardian_flash").state is CapabilityState.UNCONFIRMED


def test_direct_sparse_super_uses_original_filename_for_adapter_and_tools(tmp_path):
    source = tmp_path / "super.img"
    source.write_bytes(struct.pack("<I", 0xED26FF3A) + b"s" * 4096)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Direct super DNA").project_id, source)
    report = RomInspectionService(store).inspect_project(project.project_id)

    profile = DeviceDnaService(store, DevicePackRegistry(())).refresh(
        project.project_id,
        inspection=report,
    )

    assert report.source_name == "super.img"
    assert profile.fact("firmware.adapter").value == "Android fastboot / super source"
    assert profile.capability("source_adapter").state is CapabilityState.SUPPORTED
    assert profile.capability("tool_resolution").state is CapabilityState.SUPPORTED
    assert "LP Dump" in profile.fact("firmware.tool_profile").value
    assert profile.capability("guardian_flash").state is CapabilityState.UNCONFIRMED


def test_partition_bundle_is_recognized_but_automatic_adapter_stays_caution(tmp_path):
    source = tmp_path / "partition-files.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("boot.img", b"ANDROID! test")
        archive.writestr("vendor_boot.img", b"ANDROID! vendor")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Partition bundle").project_id, source)
    report = RomInspectionService(store).inspect_project(project.project_id)

    profile = DeviceDnaService(store, DevicePackRegistry(())).refresh(
        project.project_id,
        inspection=report,
    )

    assert profile.fact("firmware.adapter").value == "Android partition image bundle"
    assert profile.fact("partition.discovered").value == "boot, vendor_boot"
    assert profile.capability("firmware_detection").state is CapabilityState.SUPPORTED
    assert profile.capability("source_adapter").state is CapabilityState.CAUTION
    assert profile.capability("tool_resolution").state is CapabilityState.CAUTION
    assert "not yet available" in profile.capability("source_adapter").detail


def test_critical_archive_structure_blocks_detected_payload_adapter(tmp_path):
    source = tmp_path / "unsafe-payload.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"CrAU test payload")
        archive.writestr("../escape.img", b"unsafe")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Unsafe payload").project_id, source)
    report = RomInspectionService(store).inspect_project(project.project_id)

    profile = DeviceDnaService(store, DevicePackRegistry(())).refresh(
        project.project_id,
        inspection=report,
    )

    assert profile.fact("firmware.adapter").value == "Android OTA payload"
    assert profile.capability("firmware_detection").state is CapabilityState.UNSUPPORTED
    assert profile.capability("source_adapter").state is CapabilityState.UNSUPPORTED
    assert profile.capability("tool_resolution").state is CapabilityState.UNSUPPORTED
    assert profile.capability("guardian_flash").state is CapabilityState.UNSUPPORTED
    assert any("Critical firmware structure" in warning for warning in profile.warnings)


def test_codename_mismatch_is_unsupported_and_visible(tmp_path):
    store, registry, project, report = _project(tmp_path)

    profile = DeviceDnaService(store, registry).refresh(
        project.project_id, _device(codename="wrong-device"), report
    )

    assert profile.capability("device_identity").state is CapabilityState.UNSUPPORTED
    assert profile.capability("guardian_flash").state is CapabilityState.UNSUPPORTED
    assert any("does not match" in warning for warning in profile.warnings)


def test_opaque_exact_source_requires_live_phone_to_match_its_pack(tmp_path):
    source = _source(tmp_path, "opaque-firmware.zip")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Opaque exact", "xiaomi.popsicle.test")
    project = store.import_original(project.project_id, source)
    pack = _pack(project.original.sha256)
    registry = DevicePackRegistry((pack,))

    matching = DeviceDnaService(store, registry).refresh(project.project_id, _device())
    assert matching.capability("device_identity").state is CapabilityState.SUPPORTED

    wrong = DeviceDnaService(store, registry).refresh(
        project.project_id,
        _device(
            manufacturer="Google",
            model="Pixel 9 Pro XL",
            product="komodo",
            codename="komodo",
        ),
    )
    assert wrong.capability("device_identity").state is CapabilityState.UNSUPPORTED
    assert wrong.capability("guardian_flash").state is CapabilityState.UNSUPPORTED
    assert any("exact source-bound Pack" in warning for warning in wrong.warnings)


def test_device_dna_store_detects_tampering_and_reuses_unchanged_profile(tmp_path):
    store, registry, project, report = _project(tmp_path)
    service = DeviceDnaService(store, registry)
    first = service.refresh(project.project_id, _device(), report)
    second = service.refresh(project.project_id, _device(), report)
    assert second.profile_id == first.profile_id

    path = store.projects_root / project.project_id / DeviceDnaStore.NAME
    data = json.loads(path.read_text())
    assert data["schema_version"] == 2
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    data["facts"][0]["value"] = "Wrong phone"
    path.write_text(json.dumps(data))
    assert service.profiles.load(project.project_id) is None


def test_device_dna_store_rejects_extra_oversized_and_linked_records(tmp_path):
    store, registry, project, report = _project(tmp_path)
    service = DeviceDnaService(store, registry)
    service.refresh(project.project_id, _device(), report)
    path = store.projects_root / project.project_id / DeviceDnaStore.NAME
    original = path.read_bytes()

    data = json.loads(original)
    data["unexpected"] = True
    path.write_text(json.dumps(data), encoding="utf-8")
    assert service.profiles.load(project.project_id) is None

    data = json.loads(original)
    data["facts"][0]["unexpected"] = True
    path.write_text(json.dumps(data), encoding="utf-8")
    assert service.profiles.load(project.project_id) is None

    data = json.loads(original)
    data["facts"][0]["evidence_ids"] = ["missing.evidence"]
    unsigned = {
        key: value for key, value in data.items() if key not in {"format", "profile_digest"}
    }
    data["profile_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    path.write_text(json.dumps(data), encoding="utf-8")
    assert service.profiles.load(project.project_id) is None

    data = json.loads(original)
    data["bootloader_relock_permitted"] = "false"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert service.profiles.load(project.project_id) is None

    path.write_bytes(b"{" + b" " * DeviceDnaStore.MAX_BYTES + b"}")
    assert service.profiles.load(project.project_id) is None

    outside = tmp_path / "outside-device-dna.json"
    outside.write_bytes(original)
    path.unlink()
    path.symlink_to(outside)
    assert service.profiles.load(project.project_id) is None
    assert outside.read_bytes() == original


def test_legacy_device_dna_is_readable_and_refresh_upgrades_schema(tmp_path):
    store, registry, project, report = _project(tmp_path)
    service = DeviceDnaService(store, registry)
    service.refresh(project.project_id, _device(), report)
    path = store.projects_root / project.project_id / DeviceDnaStore.NAME
    data = json.loads(path.read_text())
    data["schema_version"] = 1
    unsigned = {
        key: value for key, value in data.items() if key not in {"format", "profile_digest"}
    }
    data["profile_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    path.write_text(json.dumps(data), encoding="utf-8")

    legacy = service.profiles.load(project.project_id)
    assert legacy is not None
    assert legacy.schema_version == 1

    upgraded = service.refresh(project.project_id, _device(), report)
    stored = json.loads(path.read_text())

    assert upgraded.schema_version == 2
    assert stored["schema_version"] == 2
    assert service.profiles.load(project.project_id) == upgraded


def test_device_dna_ignores_unpersisted_inspection_lookalike(tmp_path):
    store, registry, project, report = _project(tmp_path)
    service = DeviceDnaService(store, registry)
    forged = replace(
        report,
        container=ContainerKind.ANDROID_BOOT,
        partition_signals=("boot",),
        record_digest="0" * 64,
    )

    profile = service.refresh(project.project_id, _device(), forged)

    assert profile.fact("firmware.adapter").value == "Android OTA payload"
    assert profile.capability("source_adapter").state is CapabilityState.SUPPORTED


def test_device_dna_store_rejects_any_relock_authority(tmp_path):
    store, registry, project, report = _project(tmp_path)
    service = DeviceDnaService(store, registry)
    profile = service.refresh(project.project_id, _device(), report)

    with pytest.raises(ProjectError, match="never authorize"):
        service.profiles.save(replace(profile, bootloader_relock_permitted=True))

    path = store.projects_root / project.project_id / DeviceDnaStore.NAME
    data = json.loads(path.read_text())
    relock = next(
        item for item in data["capabilities"] if item["capability_id"] == "bootloader_relock"
    )
    relock["state"] = "SUPPORTED"
    unsigned = {
        key: value for key, value in data.items() if key not in {"format", "profile_digest"}
    }
    data["profile_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    path.write_text(json.dumps(data), encoding="utf-8")

    assert service.profiles.load(project.project_id) is None
