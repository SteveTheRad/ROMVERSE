from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import struct
import zipfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from romverse.ascension.assessment import AscensionAssessmentService
from romverse.ascension.binding import AscensionSourceBindingService
from romverse.ascension.build_handoff import RootRomBuildHandoffService
from romverse.ascension.companion import AscensionCompanionStatusService
from romverse.ascension.evidence import AscensionEvidenceService, inspect_android_boot_image
from romverse.ascension.handoff import RootPatchHandoffService
from romverse.ascension.integration import RootRomIntegrationService
from romverse.ascension.journey import build_journey_brief, build_journey_checkpoints
from romverse.ascension.manifest import AscensionGuardianManifestService, ManifestState
from romverse.ascension.models import (
    AscensionMethod,
    GateState,
    OfficialRootAsset,
    OfficialRootRelease,
)
from romverse.ascension.planning import AscensionRootPlanService
from romverse.ascension.preparation import RootPatchPreparationService
from romverse.ascension.releases import (
    OfficialRootConnectivityError,
    OfficialRootReleaseService,
)
from romverse.ascension.route import AscensionRouteRecordService
from romverse.ascension.support import KernelSuSupportEvidenceService
from romverse.backup.handoff import BackupHandoffService, CloudBackupProvider
from romverse.device.apk_install import inspect_apk
from romverse.device.dna import CapabilityState, DeviceDnaService, DeviceDnaStore
from romverse.device.models import AndroidDevice, DeviceState, StorageInfo
from romverse.device_packs.models import DevicePack, FirmwareSourceContract
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.process import CommandResult
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.guided import GuidedMissionState, GuidedMissionStore
from romverse.rom.inspection import RomInspectionService
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.recovery_evidence import RecoveryEvidenceService
from romverse.rom.source_intelligence import FirmwareSourceIntelligenceService
from tests._ascension_trust import ExplicitTestRootReleaseService


class _Stream(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def _pack(source_sha256: str) -> DevicePack:
    from romverse.device_packs.models import DeviceBuildContract

    contract = DeviceBuildContract(
        "test-contract",
        1,
        FirmwareSourceContract("OS3.0.318.0.WPBCNXM", source_sha256, "0" * 64),
        1,
        1,
        2,
        True,
        (),
        (),
        (),
        "1" * 64,
        "2" * 64,
        (),
    )
    return DevicePack(
        "xiaomi.popsicle.test",
        "1",
        "Xiaomi popsicle test",
        100,
        ("xiaomi",),
        ("*",),
        ("popsicle",),
        (),
        (),
        "3" * 64,
        contract,
    )


def _project(tmp_path: Path) -> tuple[RomProjectStore, str, str]:
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Ascension")
    source = tmp_path / "popsicle_images_OS3.0.318.0.WPBCNXM_20260804.0000.00_16.0_cn_test.tgz"
    source.write_bytes(b"exact firmware")
    project = store.import_original(project.project_id, source)
    RomInspectionService(store).inspect_project(project.project_id)
    return store, project.project_id, project.original.sha256


def test_ascension_journey_brief_exposes_one_plain_language_next_action() -> None:
    blocked = build_journey_brief(
        AscensionMethod.MAGISK,
        blocked=True,
        manager_verified=False,
        capsule_ready=False,
        handoff_ready=False,
        patched_ready=False,
        integration_ready=False,
        build_handoff_ready=False,
        plan_ready=False,
        manifest_ready=False,
    )
    phone_patch = build_journey_brief(
        AscensionMethod.MAGISK,
        blocked=False,
        manager_verified=True,
        capsule_ready=True,
        handoff_ready=True,
        patched_ready=False,
        integration_ready=False,
        build_handoff_ready=False,
        plan_ready=False,
        manifest_ready=False,
    )
    review = build_journey_brief(
        AscensionMethod.KERNELSU_LKM,
        blocked=False,
        manager_verified=True,
        capsule_ready=True,
        handoff_ready=True,
        patched_ready=True,
        integration_ready=True,
        build_handoff_ready=True,
        plan_ready=True,
        manifest_ready=True,
        review_ready=True,
    )
    opened_manager = build_journey_brief(
        AscensionMethod.MAGISK,
        blocked=False,
        manager_verified=True,
        capsule_ready=True,
        handoff_ready=True,
        patched_ready=False,
        integration_ready=False,
        build_handoff_ready=False,
        plan_ready=False,
        manifest_ready=False,
        manager_opened=True,
    )

    assert blocked.stage_number == 1
    assert blocked.verified_checkpoints == 0
    assert blocked.progress_percent == 0
    assert "highlighted action" in blocked.user_action
    assert "unbootable" in blocked.why
    assert phone_patch.stage_number == 5
    assert phone_patch.verified_checkpoints == 4
    assert phone_patch.progress_percent == 44
    assert "Magisk" in phone_patch.user_action
    assert "recheck the installed package" in phone_patch.user_action
    assert "is open" in opened_manager.user_action
    assert review.stage_number == 9
    assert review.verified_checkpoints == 8
    assert review.progress_percent == 89
    assert "final consent" in review.user_action
    assert "wrong phone" in review.why


def test_ascension_tracker_uses_the_same_authoritative_nine_stage_order() -> None:
    stages = build_journey_checkpoints(
        blocked=False,
        manager_verified=True,
        capsule_ready=True,
        handoff_ready=True,
        patched_ready=False,
        integration_ready=False,
        build_handoff_ready=False,
        plan_ready=False,
        manifest_ready=False,
        final_handoff_ready=False,
    )

    assert tuple(stage.stage_number for stage in stages) == tuple(range(1, 10))
    assert tuple(stage.title for stage in stages) == (
        "Prerequisites",
        "Official manager",
        "Patch capsule",
        "Phone handoff",
        "Patched image",
        "ROM integration",
        "Build seal",
        "Device binding",
        "Guardian review",
    )
    assert tuple(stage.complete for stage in stages) == (
        True,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
        False,
    )


def test_manual_verified_patch_completes_handoff_without_inventing_later_evidence() -> None:
    stages = build_journey_checkpoints(
        blocked=False,
        manager_verified=True,
        capsule_ready=True,
        handoff_ready=False,
        patched_ready=True,
        integration_ready=False,
        build_handoff_ready=False,
        plan_ready=False,
        manifest_ready=False,
        final_handoff_ready=False,
    )

    assert stages[3].title == "Phone handoff"
    assert stages[3].complete
    assert stages[4].complete
    assert not stages[5].complete
    assert not stages[8].complete


def test_guardian_review_checkpoint_requires_the_exact_final_handoff() -> None:
    common = dict(
        blocked=False,
        manager_verified=True,
        capsule_ready=True,
        handoff_ready=True,
        patched_ready=True,
        integration_ready=True,
        build_handoff_ready=True,
        plan_ready=True,
        manifest_ready=True,
    )

    pending = build_journey_checkpoints(**common, final_handoff_ready=False)
    complete = build_journey_checkpoints(**common, final_handoff_ready=True)

    assert all(stage.complete for stage in pending[:8])
    assert not pending[8].complete
    assert all(stage.complete for stage in complete)


@pytest.mark.parametrize(
    ("state", "expected_stage"),
    (
        ({"blocked": True}, 1),
        ({"manager_verified": False}, 2),
        ({"capsule_ready": False}, 3),
        ({"handoff_ready": False, "patched_ready": False}, 4),
        ({"patched_ready": False}, 5),
        ({"integration_ready": False}, 6),
        ({"build_handoff_ready": False}, 7),
        ({"plan_ready": False, "manifest_ready": False}, 8),
        ({}, 9),
    ),
)
def test_beginner_brief_matches_first_incomplete_authoritative_checkpoint(
    state: dict[str, bool],
    expected_stage: int,
) -> None:
    evidence = {
        "blocked": False,
        "manager_verified": True,
        "capsule_ready": True,
        "handoff_ready": True,
        "patched_ready": True,
        "integration_ready": True,
        "build_handoff_ready": True,
        "plan_ready": True,
        "manifest_ready": True,
    }
    evidence.update(state)
    brief = build_journey_brief(AscensionMethod.MAGISK, **evidence)
    checkpoints = build_journey_checkpoints(
        **evidence,
        final_handoff_ready=False,
    )

    first_pending = next(stage.stage_number for stage in checkpoints if not stage.complete)
    assert brief.stage_number == expected_stage == first_pending


def test_companion_reports_explicit_unrooted_genesis_choice(tmp_path: Path) -> None:
    store, project_id, _digest = _project(tmp_path)
    GuidedMissionStore(store.projects_root / project_id).save(
        GuidedMissionState(root_choice="skip")
    )

    status = AscensionCompanionStatusService(store, DevicePackRegistry(())).snapshot(project_id)

    assert status.state == "skipped"
    assert status.method == "none"
    assert status.stage_title == "Unrooted ROM selected"
    assert "standard unrooted build" in status.next_action
    assert "verified stock boot input" in status.romverse_action


def test_assessment_is_exact_source_bound_and_finds_init_boot(tmp_path: Path) -> None:
    store, project_id, digest = _project(tmp_path)
    tree = store.working_root / project_id / "tree" / "images"
    tree.mkdir(parents=True)
    (tree / "boot.img").write_bytes(_boot_v4(b"boot ramdisk"))
    (tree / "init_boot.img").write_bytes(_boot_v4(b"init ramdisk"))
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="Xiaomi 17 Pro Max",
        codename="popsicle",
        bootloader_locked=False,
    )

    report = AscensionAssessmentService(store, DevicePackRegistry((_pack(digest),))).assess(
        project_id, AscensionMethod.MAGISK, device
    )

    assert report.patch_target == "images/init_boot.img"
    states = {gate.gate_id: gate.state for gate in report.gates}
    assert states["source-contract"] is GateState.PASS
    assert states["device-match"] is GateState.PASS
    assert states["recovery"] is GateState.PASS
    assert report.execution_locked is True


def test_assessment_collapses_identical_root_targets_to_one_canonical_partition(
    tmp_path: Path,
) -> None:
    store, project_id, digest = _project(tmp_path)
    tree = store.working_root / project_id / "tree" / "images"
    partitions = store.working_root / project_id / "partitions"
    tree.mkdir(parents=True)
    partitions.mkdir(parents=True)
    image = _boot_v4(b"same source-bound init boot")
    (tree / "init_boot.img").write_bytes(image)
    (partitions / "init_boot.img").write_bytes(image)
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        codename="popsicle",
        bootloader_locked=False,
    )

    report = AscensionAssessmentService(store, DevicePackRegistry((_pack(digest),))).assess(
        project_id,
        AscensionMethod.MAGISK,
        device,
    )
    gate = next(item for item in report.gates if item.gate_id == "patch-target")

    assert report.patch_target == "partitions/init_boot.img"
    assert gate.state is GateState.PASS
    assert "2 byte-identical" in gate.detail
    assert "canonical" in gate.detail


def test_assessment_blocks_byte_distinct_duplicate_root_targets(tmp_path: Path) -> None:
    store, project_id, digest = _project(tmp_path)
    tree = store.working_root / project_id / "tree" / "images"
    partitions = store.working_root / project_id / "partitions"
    tree.mkdir(parents=True)
    partitions.mkdir(parents=True)
    (tree / "init_boot.img").write_bytes(_boot_v4(b"fastboot source copy"))
    (partitions / "init_boot.img").write_bytes(_boot_v4(b"different payload copy"))
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        codename="popsicle",
        bootloader_locked=False,
    )

    report = AscensionAssessmentService(store, DevicePackRegistry((_pack(digest),))).assess(
        project_id,
        AscensionMethod.MAGISK,
        device,
    )
    gate = next(item for item in report.gates if item.gate_id == "patch-target")

    assert report.patch_target == ""
    assert gate.state is GateState.BLOCKED
    assert "byte-distinct init_boot.img" in gate.detail
    assert "stopped instead of guessing" in gate.detail


def test_assessment_rejects_unreasonably_large_root_target_before_hashing(tmp_path: Path) -> None:
    store, project_id, digest = _project(tmp_path)
    tree = store.working_root / project_id / "tree" / "images"
    tree.mkdir(parents=True)
    target = tree / "init_boot.img"
    with target.open("wb") as stream:
        stream.truncate(AscensionAssessmentService.MAX_PATCH_TARGET_BYTES + 1)
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        codename="popsicle",
        bootloader_locked=False,
    )

    report = AscensionAssessmentService(store, DevicePackRegistry((_pack(digest),))).assess(
        project_id,
        AscensionMethod.MAGISK,
        device,
    )
    gate = next(item for item in report.gates if item.gate_id == "patch-target")

    assert report.patch_target == ""
    assert gate.state is GateState.BLOCKED
    assert "invalid root-target size" in gate.detail


def test_single_root_target_defers_hashing_to_existing_rollback_gate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store, project_id, _digest = _project(tmp_path)
    tree = store.working_root / project_id / "tree" / "images"
    tree.mkdir(parents=True)
    (tree / "init_boot.img").write_bytes(_boot_v4(b"one authoritative candidate"))
    service = AscensionAssessmentService(store, DevicePackRegistry(()))
    monkeypatch.setattr(
        service,
        "_sha256",
        lambda _path: pytest.fail("single-candidate selection must not duplicate hashing"),
    )

    selected, detail = service._resolve_patch_target(
        project_id,
        ("images/init_boot.img",),
        AscensionMethod.MAGISK,
    )

    assert selected == "images/init_boot.img"
    assert "rollback evidence gate" in detail


def test_magisk_automatically_falls_back_from_ramdiskless_init_boot_to_boot(
    tmp_path: Path,
) -> None:
    store, project_id, digest = _project(tmp_path)
    images = store.working_root / project_id / "tree" / "images"
    images.mkdir(parents=True)
    (images / "init_boot.img").write_bytes(_boot_v4(b""))
    (images / "boot.img").write_bytes(_boot_v4(b"patchable boot ramdisk"))
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        codename="popsicle",
        bootloader_locked=False,
        root_detected=False,
    )

    report = AscensionAssessmentService(store, DevicePackRegistry((_pack(digest),))).assess(
        project_id,
        AscensionMethod.MAGISK,
        device,
    )
    gate = next(item for item in report.gates if item.gate_id == "patch-target")

    assert report.patch_target == "images/boot.img"
    assert gate.state is GateState.PASS
    assert "Higher-priority candidates were skipped safely" in gate.detail
    assert "contains no patchable ramdisk" in gate.detail


def test_magisk_automatically_falls_back_to_recovery_when_boot_has_no_ramdisk(
    tmp_path: Path,
) -> None:
    store, project_id, digest = _project(tmp_path)
    images = store.working_root / project_id / "tree" / "images"
    images.mkdir(parents=True)
    (images / "boot.img").write_bytes(_boot_v4(b""))
    (images / "recovery.img").write_bytes(_boot_v4(b"recovery-mode ramdisk"))
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        codename="popsicle",
        bootloader_locked=False,
        root_detected=False,
    )

    report = AscensionAssessmentService(store, DevicePackRegistry((_pack(digest),))).assess(
        project_id,
        AscensionMethod.MAGISK,
        device,
    )

    assert report.patch_target == "images/recovery.img"
    assert any(
        gate.gate_id == "patch-target" and gate.state is GateState.PASS for gate in report.gates
    )


def test_kernelsu_never_falls_back_to_recovery_patch_mode(tmp_path: Path) -> None:
    store, project_id, digest = _project(tmp_path)
    images = store.working_root / project_id / "tree" / "images"
    images.mkdir(parents=True)
    (images / "recovery.img").write_bytes(_boot_v4(b"recovery-only ramdisk"))
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        codename="popsicle",
        bootloader_locked=False,
        root_detected=False,
        kernel_version="6.12.23-android16-popsicle",
    )

    report = AscensionAssessmentService(store, DevicePackRegistry((_pack(digest),))).assess(
        project_id,
        AscensionMethod.KERNELSU_LKM,
        device,
    )
    gate = next(item for item in report.gates if item.gate_id == "patch-target")

    assert report.patch_target == ""
    assert gate.state is GateState.BLOCKED
    assert "KernelSU LKM supports only an exact boot or init_boot target" in gate.detail


@pytest.mark.parametrize("bootloader_locked", (True, None))
def test_locked_or_unknown_bootloader_allows_only_local_root_preparation(
    tmp_path: Path,
    bootloader_locked: bool | None,
) -> None:
    store, project_id, digest = _project(tmp_path)
    images = store.working_root / project_id / "tree" / "images"
    images.mkdir(parents=True)
    (images / "init_boot.img").write_bytes(_boot_v4(b"local preparation ramdisk"))
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        codename="popsicle",
        bootloader_locked=bootloader_locked,
        root_detected=False,
    )
    service = AscensionAssessmentService(store, DevicePackRegistry((_pack(digest),)))

    report = service.assess(project_id, AscensionMethod.MAGISK, device)
    recommendation = service.recommend(project_id, device)
    gate = next(item for item in report.gates if item.gate_id == "bootloader")

    assert gate.state is GateState.ATTENTION
    assert "Safe local rooted-ROM preparation may continue" in gate.detail
    assert "Guardian will block every device-write handoff" in gate.detail
    assert report.ready_for_offline_preparation
    assert report.execution_locked
    assert recommendation.ready
    assert recommendation.method is AscensionMethod.MAGISK
    assert any("Guardian will block" in item for item in recommendation.evidence)


def test_assessment_refuses_model_guess_without_exact_digest(tmp_path: Path) -> None:
    store, project_id, _digest = _project(tmp_path)
    device = AndroidDevice("serial", DeviceState.DEVICE, manufacturer="Xiaomi", codename="popsicle")
    report = AscensionAssessmentService(store, DevicePackRegistry(())).assess(
        project_id, AscensionMethod.KERNELSU_LKM, device
    )
    gate = next(item for item in report.gates if item.gate_id == "source-contract")
    assert gate.state is GateState.BLOCKED
    assert "exact protected source" in gate.detail.casefold()


def test_ascension_binding_uses_exact_source_pack_for_opaque_firmware(
    tmp_path: Path,
) -> None:
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Opaque exact source")
    source = tmp_path / "mystery-build.zip"
    source.write_bytes(b"exact but opaquely named firmware")
    project = store.import_original(project.project_id, source)
    pack = _pack(project.original.sha256)
    registry = DevicePackRegistry((pack,))
    store.associate_device_pack(
        project.project_id,
        pack.pack_id,
        evidence_sha256=project.original.sha256,
        reason="Exact source contract matched during automatic detection.",
    )
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="Xiaomi 17 Pro Max",
        codename="popsicle",
        bootloader_locked=False,
    )
    dna = DeviceDnaService(store, registry).refresh(project.project_id, device)

    binding = AscensionSourceBindingService(store, registry).resolve(project.project_id)
    report = AscensionAssessmentService(store, registry).assess(
        project.project_id, AscensionMethod.MAGISK, device
    )
    gates = {gate.gate_id: gate for gate in report.gates}

    assert binding.confirmed
    assert binding.codename == "popsicle"
    assert binding.authority == "exact-device-pack"
    assert binding.source_sha256 == project.original.sha256
    assert binding.device_dna_digest == dna.profile_digest
    assert binding.device_dna_state is CapabilityState.SUPPORTED
    assert binding.matches(device)
    assert gates["device-dna"].state is GateState.PASS
    assert gates["device-match"].state is GateState.PASS


def test_ascension_binding_blocks_conflicting_exact_source_identities(tmp_path: Path) -> None:
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Conflicting source identity")
    source = tmp_path / "wrongdevice_images_OS3.0.318.0.WPBCNXM_20260804.0000.00_16.0_cn_test.tgz"
    source.write_bytes(b"conflicting firmware identity")
    project = store.import_original(project.project_id, source)
    registry = DevicePackRegistry((_pack(project.original.sha256),))
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="Xiaomi 17 Pro Max",
        codename="popsicle",
        bootloader_locked=False,
    )

    binding = AscensionSourceBindingService(store, registry).resolve(project.project_id)
    report = AscensionAssessmentService(store, registry).assess(
        project.project_id, AscensionMethod.MAGISK, device
    )
    match = next(gate for gate in report.gates if gate.gate_id == "device-match")

    assert not binding.confirmed
    assert binding.codename == ""
    assert binding.conflicts
    assert not binding.matches(device)
    assert match.state is GateState.BLOCKED
    assert "conflicting source codenames" in match.detail.casefold()


def test_assessment_accepts_source_bound_local_blueprint_for_safe_preparation(
    tmp_path: Path,
) -> None:
    store, project_id, _digest = _project(tmp_path)
    images = store.working_root / project_id / "tree" / "images"
    images.mkdir(parents=True)
    (images / "super.img").write_bytes(b"raw-super")
    (images / "init_boot.img").write_bytes(_boot_v4(b"blueprint ramdisk"))
    lpdump = tmp_path / "lpdumps"
    lpdump.write_bytes(b"tool")

    class Runner:
        def run(self, args, timeout=10, cwd=None):
            command = tuple(map(str, args))
            return CommandResult(
                command,
                0,
                json.dumps(
                    {
                        "partitions": [
                            {"name": "product_a", "group_name": "dynamic_a", "size": "4"}
                        ],
                        "groups": [{"name": "dynamic_a", "maximum_size": "8"}],
                        "super_device": {"used_size": "4", "total_size": "16"},
                    }
                ),
                "",
            )

    FirmwareSourceIntelligenceService(
        store,
        (ToolStatus("LP Dump", True, str(lpdump), "test"),),
        Runner(),
    ).prepare(project_id)
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        codename="popsicle",
        bootloader_locked=False,
    )

    report = AscensionAssessmentService(store, DevicePackRegistry(())).assess(
        project_id, AscensionMethod.MAGISK, device
    )
    gate = next(item for item in report.gates if item.gate_id == "source-contract")

    assert gate.state is GateState.PASS
    assert "fastboot-super" in gate.detail


def test_assessment_uses_authenticated_companion_as_read_only_evidence(tmp_path: Path) -> None:
    from types import SimpleNamespace

    store, project_id, digest = _project(tmp_path)
    tree = store.working_root / project_id / "tree"
    tree.mkdir(parents=True)
    (tree / "init_boot.img").write_bytes(_boot_v4(b"companion evidence ramdisk"))
    companion = SimpleNamespace(
        manufacturer="Xiaomi",
        model="Xiaomi 17 Pro Max",
        device_codename="popsicle",
        android_version="16",
        bootloader_state="unknown",
        root_signal="not_observed",
        kernel_release="6.12.23-popsicle",
        kernelsu_support="unknown",
    )
    report = AscensionAssessmentService(store, DevicePackRegistry((_pack(digest),))).assess(
        project_id, AscensionMethod.KERNELSU_LKM, companion=companion
    )
    live = next(gate for gate in report.gates if gate.gate_id == "live-device")
    kernel = next(gate for gate in report.gates if gate.gate_id == "kernel")
    assert live.state is GateState.ATTENTION
    assert "Companion" in live.detail
    assert kernel.state is GateState.BLOCKED


def test_root_route_recommendation_requires_explicit_kernelsu_support(
    tmp_path: Path,
) -> None:
    from types import SimpleNamespace

    store, project_id, digest = _project(tmp_path)
    images = store.working_root / project_id / "tree" / "images"
    images.mkdir(parents=True)
    (images / "init_boot.img").write_bytes(_boot_v4(b"route ramdisk"))
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        codename="popsicle",
        bootloader_locked=False,
        kernel_version="6.12.23-android16-0-popsicle",
    )
    registry = DevicePackRegistry((_pack(digest),))
    release_service = _release_service(store.workspace)
    service = AscensionAssessmentService(store, registry, release_service)

    unknown = service.recommend(
        project_id,
        device,
        SimpleNamespace(
            kernelsu_support="unknown",
            device_codename="popsicle",
            kernel_release=device.kernel_version,
        ),
    )
    supported = service.recommend(
        project_id,
        device,
        SimpleNamespace(
            kernelsu_support="supported",
            device_codename="popsicle",
            kernel_release=device.kernel_version,
        ),
    )
    unsupported = service.recommend(
        project_id,
        device,
        SimpleNamespace(
            kernelsu_support="unsupported",
            device_codename="popsicle",
            kernel_release=device.kernel_version,
        ),
    )
    mismatched_companion = service.recommend(
        project_id,
        device,
        SimpleNamespace(
            kernelsu_support="supported",
            device_codename="another-phone",
            kernel_release=device.kernel_version,
        ),
    )

    assert unknown.method is AscensionMethod.MAGISK
    assert unknown.ready
    assert "will not guess" in unknown.reason
    assert supported.method is AscensionMethod.MAGISK
    assert supported.ready
    assert any("telemetry cannot authorize" in item for item in supported.evidence)
    assert unsupported.method is AscensionMethod.MAGISK
    assert any("Companion reports unsupported" in item for item in unsupported.evidence)
    assert any("telemetry cannot authorize" in item for item in unsupported.evidence)
    assert mismatched_companion.method is AscensionMethod.MAGISK

    mobile_ready = AscensionCompanionStatusService(store, registry).snapshot(
        project_id,
        device,
        SimpleNamespace(
            kernelsu_support="unknown",
            device_codename="popsicle",
            kernel_release=device.kernel_version,
        ),
    )
    assert mobile_ready.state == "not_started"
    assert mobile_ready.method == "magisk"
    assert mobile_ready.target_partition == "init_boot"
    assert mobile_ready.blocker_count == 0
    assert mobile_ready.stage_number in range(1, 8)
    assert mobile_ready.stage_title
    assert mobile_ready.next_action
    assert mobile_ready.why
    assert mobile_ready.romverse_action
    route_record = AscensionRouteRecordService(store, registry).load(project_id)
    assert route_record is not None
    assert route_record.recommended_method is AscensionMethod.MAGISK
    assert route_record.execution_authority == "none"
    assert not route_record.bootloader_relock_allowed

    evidence_service = KernelSuSupportEvidenceService(store, release_service)
    manager_tag, manager_sha256 = _vault_kernelsu_manager(store.workspace)
    evidence = evidence_service.record(
        project_id,
        device,
        manager_tag,
        manager_sha256,
        "supported",
    )
    from_local_evidence = service.recommend(
        project_id,
        device,
        SimpleNamespace(
            kernelsu_support="unknown",
            device_codename="popsicle",
            kernel_release=device.kernel_version,
        ),
    )
    assert evidence.root_applied is False
    assert from_local_evidence.method is AscensionMethod.KERNELSU_LKM

    changed_kernel = AndroidDevice(
        device.serial,
        DeviceState.DEVICE,
        manufacturer=device.manufacturer,
        codename=device.codename,
        bootloader_locked=False,
        kernel_version="6.12.24-android16-0-popsicle",
    )
    assert evidence_service.load(project_id, changed_kernel) is None

    rooted_device = replace(
        device,
        root_detected=True,
        root_signal_source="adb-shell-uid-0",
        root_manager_candidate="magisk",
        root_manager_evidence="allowlisted-package-presence",
    )
    rooted = service.recommend(project_id, rooted_device)
    assert rooted.method is AscensionMethod.MAGISK
    assert rooted.title == "Existing root detected — review first"
    assert "second root method" in rooted.reason
    assert not rooted.ready
    mobile_blocked = AscensionCompanionStatusService(store, registry).snapshot(
        project_id,
        rooted_device,
    )
    assert mobile_blocked.state == "blocked"
    assert mobile_blocked.method == "magisk"
    assert mobile_blocked.blocker_count >= 1
    assert "Magisk Manager candidate" in mobile_blocked.stage_title
    assert "does not prove" in mobile_blocked.why

    manager_only = service.assess(
        project_id,
        AscensionMethod.MAGISK,
        replace(
            device,
            root_detected=False,
            root_signal_source="adb-shell-id",
            root_manager_candidate="magisk",
            root_manager_evidence="allowlisted-package-presence",
        ),
    )
    manager_gate = next(gate for gate in manager_only.gates if gate.gate_id == "root-state")
    assert manager_gate.state is GateState.ATTENTION
    assert "does not prove" in manager_gate.detail

    with pytest.raises(ProjectError, match="live kernel identity"):
        evidence_service.record(
            project_id,
            replace(device, kernel_version=""),
            manager_tag,
            manager_sha256,
            "supported",
        )


def test_ascension_automatically_vaults_rollback_and_proves_v4_ramdisk(
    tmp_path: Path,
) -> None:
    store, project_id, digest = _project(tmp_path)
    images = store.working_root / project_id / "tree" / "images"
    images.mkdir(parents=True)
    (images / "init_boot.img").write_bytes(_boot_v4(b"r" * 4096))
    (images / "recovery.img").write_bytes(b"stock recovery")
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        codename="popsicle",
        bootloader_locked=False,
    )

    report = AscensionAssessmentService(store, DevicePackRegistry((_pack(digest),))).assess(
        project_id, AscensionMethod.MAGISK, device
    )

    states = {gate.gate_id: gate.state for gate in report.gates}
    assert states["recovery"] is GateState.PASS
    assert states["user-backup"] is GateState.ATTENTION
    assert states["ramdisk"] is GateState.PASS
    record = AscensionEvidenceService(store).load(project_id)
    assert record is not None
    assert record.patch_target.sha256
    assert record.stock_recovery is not None
    assert record.boot_image.ramdisk_size_bytes == 4096
    assert record.phone_changed is False


def test_boot_evidence_rejects_truncated_image_with_claimed_ramdisk(tmp_path: Path) -> None:
    image = tmp_path / "init_boot.img"
    header = bytearray(64)
    header[:8] = b"ANDROID!"
    struct.pack_into("<I", header, 12, 4096)
    struct.pack_into("<I", header, 20, 1584)
    struct.pack_into("<I", header, 40, 4)
    image.write_bytes(header)

    with pytest.raises(ProjectError, match="sections exceed"):
        inspect_android_boot_image(image, tmp_path)


def test_rollback_collapses_identical_tree_and_partition_recovery_copies(
    tmp_path: Path,
) -> None:
    store, project_id, _digest = _project(tmp_path)
    images = store.working_root / project_id / "tree" / "images"
    partitions = store.working_root / project_id / "partitions"
    images.mkdir(parents=True)
    partitions.mkdir(parents=True)
    (images / "init_boot.img").write_bytes(_boot_v4(b"root target"))
    recovery = b"same protected stock recovery bytes"
    (images / "recovery.img").write_bytes(recovery)
    (partitions / "recovery.img").write_bytes(recovery)

    record = AscensionEvidenceService(store).ensure(project_id, "images/init_boot.img")

    assert record.stock_recovery is not None
    assert record.stock_recovery.source_relative_path == "partitions/recovery.img"
    assert record.stock_recovery.sha256 == hashlib.sha256(recovery).hexdigest()


def test_rollback_blocks_byte_distinct_recovery_candidates(tmp_path: Path) -> None:
    store, project_id, _digest = _project(tmp_path)
    images = store.working_root / project_id / "tree" / "images"
    partitions = store.working_root / project_id / "partitions"
    images.mkdir(parents=True)
    partitions.mkdir(parents=True)
    (images / "init_boot.img").write_bytes(_boot_v4(b"root target"))
    (images / "recovery.img").write_bytes(b"fastboot recovery")
    (partitions / "recovery.img").write_bytes(b"different payload recovery")

    with pytest.raises(ProjectError, match="byte-distinct recovery.img"):
        AscensionEvidenceService(store).ensure(project_id, "images/init_boot.img")


def test_existing_sealed_rollback_remains_valid_if_working_tree_later_changes(
    tmp_path: Path,
) -> None:
    store, project_id, _digest = _project(tmp_path)
    images = store.working_root / project_id / "tree" / "images"
    partitions = store.working_root / project_id / "partitions"
    images.mkdir(parents=True)
    partitions.mkdir(parents=True)
    (images / "init_boot.img").write_bytes(_boot_v4(b"root target"))
    (images / "recovery.img").write_bytes(b"sealed recovery")
    service = AscensionEvidenceService(store)
    original = service.ensure(project_id, "images/init_boot.img")
    (partitions / "recovery.img").write_bytes(b"later unrelated workspace copy")

    assert service.ensure(project_id, "images/init_boot.img") == original
    assert service.load(project_id) == original


def test_rollback_load_rederives_boot_facts_even_if_digest_is_recomputed(
    tmp_path: Path,
) -> None:
    store, project_id, _digest = _project(tmp_path)
    images = store.working_root / project_id / "tree" / "images"
    images.mkdir(parents=True)
    (images / "init_boot.img").write_bytes(_boot_v4(b"verified ramdisk facts"))
    service = AscensionEvidenceService(store)
    service.ensure(project_id, "images/init_boot.img")
    receipt = store.projects_root / project_id / "ascension" / service.RECEIPT_NAME
    payload = json.loads(receipt.read_text())
    payload["boot_image"]["ramdisk_size_bytes"] += 1
    unsigned = {
        key: value for key, value in payload.items() if key not in {"format", "record_digest"}
    }
    payload["record_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    receipt.write_text(json.dumps(payload))

    assert service.load(project_id) is None


def test_rollback_load_rejects_matching_bytes_outside_exact_project_vault(
    tmp_path: Path,
) -> None:
    store, project_id, _digest = _project(tmp_path)
    images = store.working_root / project_id / "tree" / "images"
    images.mkdir(parents=True)
    (images / "init_boot.img").write_bytes(_boot_v4(b"verified vault boundary"))
    service = AscensionEvidenceService(store)
    record = service.ensure(project_id, "images/init_boot.img")
    receipt = store.projects_root / project_id / "ascension" / service.RECEIPT_NAME
    payload = json.loads(receipt.read_text())
    outside = store.workspace / "tools" / f"{record.patch_target.sha256[:16]}-init_boot.img"
    outside.parent.mkdir(parents=True)
    outside.write_bytes((store.workspace / record.patch_target.vault_relative_path).read_bytes())
    payload["patch_target"]["vault_relative_path"] = outside.relative_to(store.workspace).as_posix()
    unsigned = {
        key: value for key, value in payload.items() if key not in {"format", "record_digest"}
    }
    payload["record_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    receipt.write_text(json.dumps(payload))

    assert service.load(project_id) is None


def test_ascension_accepts_exact_cloud_backup_without_claiming_content_inspection(
    tmp_path: Path,
) -> None:
    store, project_id, digest = _project(tmp_path)
    images = store.working_root / project_id / "tree" / "images"
    images.mkdir(parents=True)
    (images / "init_boot.img").write_bytes(_boot_v4(b"cloud handoff ramdisk"))
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="17 Pro Max",
        marketing_name="Xiaomi 17 Pro Max",
        codename="popsicle",
        bootloader_locked=False,
    )
    receipt = BackupHandoffService(store).confirm_cloud(
        project_id,
        device,
        CloudBackupProvider.GOOGLE,
        "Completed today at 15:42",
        backup_completed=True,
        restore_access_confirmed=True,
        critical_data_scope_reviewed=True,
        limitations_acknowledged=True,
    )

    report = AscensionAssessmentService(store, DevicePackRegistry((_pack(digest),))).assess(
        project_id, AscensionMethod.MAGISK, device
    )
    gate = next(item for item in report.gates if item.gate_id == "user-backup")

    assert gate.state is GateState.PASS
    assert "cloud contents were not inspected" in gate.detail.casefold()
    assert receipt.cloud_contents_inspected is False

    wrong_device = replace(device, serial="other-serial")
    wrong_report = AscensionAssessmentService(store, DevicePackRegistry((_pack(digest),))).assess(
        project_id, AscensionMethod.MAGISK, wrong_device
    )
    wrong_gate = next(item for item in wrong_report.gates if item.gate_id == "user-backup")
    assert wrong_gate.state is GateState.ATTENTION


def test_assessment_accepts_verified_payload_partition_outputs(tmp_path: Path) -> None:
    store, project_id, digest = _project(tmp_path)
    partitions = store.working_root / project_id / "partitions"
    partitions.mkdir(parents=True)
    (partitions / "init_boot.img").write_bytes(_boot_v4(b"payload ramdisk"))
    (partitions / "recovery.img").write_bytes(b"payload stock recovery")
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        codename="popsicle",
        bootloader_locked=False,
    )

    report = AscensionAssessmentService(store, DevicePackRegistry((_pack(digest),))).assess(
        project_id, AscensionMethod.MAGISK, device
    )

    assert report.patch_target == "partitions/init_boot.img"
    gates = {gate.gate_id: gate for gate in report.gates}
    assert gates["patch-target"].state is GateState.PASS
    assert gates["recovery"].state is GateState.PASS
    record = AscensionEvidenceService(store).load(project_id)
    assert record is not None
    assert record.patch_target.source_relative_path == "partitions/init_boot.img"
    assert record.stock_recovery is not None
    assert record.stock_recovery.source_relative_path == "partitions/recovery.img"


def _release_payload(name: str, content: bytes, digest: str | None = None) -> dict[str, object]:
    return {
        "draft": False,
        "prerelease": False,
        "tag_name": "v30.7",
        "published_at": "2026-02-23T00:00:00Z",
        "html_url": "https://github.com/topjohnwu/Magisk/releases/tag/v30.7",
        "assets": [
            {
                "name": name,
                "state": "uploaded",
                "content_type": "application/vnd.android.package-archive",
                "size": len(content),
                "digest": "sha256:" + (digest or hashlib.sha256(content).hexdigest()),
                "browser_download_url": "https://github.com/topjohnwu/Magisk/releases/download/v30.7/"
                + name,
            }
        ],
    }


def _manager_apk_bytes() -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"binary-manifest-placeholder")
        archive.writestr("classes.dex", b"dex\n035\0")
        archive.writestr("META-INF/ROOT.RSA", b"certificate-placeholder")
    return stream.getvalue()


def _test_manager_inspector(path: Path, asset: OfficialRootAsset):
    """Give synthetic test APKs an explicit fake trust boundary.

    Production never uses this callback; it invokes APK Signer and requires the
    pinned official certificate.
    """

    inspection = inspect_apk(path)
    return replace(
        inspection,
        package_name=OfficialRootReleaseService.OFFICIAL_PACKAGES[asset.provider],
        signature_verified=True,
        signer_sha256=OfficialRootReleaseService.OFFICIAL_SIGNERS[asset.provider],
        signer_subject="CN=ROMVERSE test signer",
    )


def _release_service(*args, **kwargs) -> OfficialRootReleaseService:
    kwargs.setdefault("apk_inspector", _test_manager_inspector)
    return OfficialRootReleaseService(*args, **kwargs)


def _vault_kernelsu_manager(workspace: Path) -> tuple[str, str]:
    content = _manager_apk_bytes()
    tag = "v3.3.0"
    name = "KernelSU_v3.3.0_32601-release.apk"
    digest = hashlib.sha256(content).hexdigest()
    payload: dict[str, object] = {
        "draft": False,
        "prerelease": False,
        "tag_name": tag,
        "published_at": "2026-08-28T14:49:30Z",
        "html_url": f"https://github.com/tiann/KernelSU/releases/tag/{tag}",
        "assets": [
            {
                "name": name,
                "state": "uploaded",
                "content_type": "application/vnd.android.package-archive",
                "size": len(content),
                "digest": f"sha256:{digest}",
                "browser_download_url": (
                    f"https://github.com/tiann/KernelSU/releases/download/{tag}/{name}"
                ),
            }
        ],
    }
    service = _release_service(
        workspace,
        json_loader=lambda _url: payload,
        stream_loader=lambda url: (_Stream(content), len(content), url),
    )
    release = service.resolve_latest(AscensionMethod.KERNELSU_LKM)
    service.acquire(release)
    return release.tag, release.asset.sha256


def _kernelsu_test_device() -> AndroidDevice:
    return AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="Xiaomi 17 Pro Max",
        codename="popsicle",
        bootloader_locked=False,
        kernel_version="6.12.23-android16-0-popsicle",
    )


def test_kernelsu_support_requires_and_tracks_the_exact_vaulted_manager(
    tmp_path: Path,
) -> None:
    store, project_id, source_digest = _project(tmp_path)
    images = store.working_root / project_id / "tree" / "images"
    images.mkdir(parents=True)
    (images / "init_boot.img").write_bytes(_boot_v4(b"companion route evidence"))
    AscensionEvidenceService(store).ensure(project_id, "images/init_boot.img")
    release_service = _release_service(store.workspace)
    evidence_service = KernelSuSupportEvidenceService(store, release_service)
    device = _kernelsu_test_device()

    with pytest.raises(ProjectError, match="revalidated official Manager"):
        evidence_service.record(project_id, device, "v3.3.0", "a" * 64, "supported")

    manager_tag, manager_sha256 = _vault_kernelsu_manager(store.workspace)
    evidence_service.record(
        project_id,
        device,
        manager_tag,
        manager_sha256,
        "supported",
    )
    assert evidence_service.load(project_id, device) is not None

    mobile = AscensionCompanionStatusService(
        store,
        DevicePackRegistry((_pack(source_digest),)),
        release_service=release_service,
    ).snapshot(project_id, device)
    assert mobile.method == AscensionMethod.KERNELSU_LKM.value
    assert mobile.stage_number == 3
    assert "patch capsule" in mobile.stage_title.casefold()
    assert mobile.manager_state == "verified"
    assert mobile.manager_repository == "tiann/KernelSU"
    assert mobile.manager_tag == manager_tag
    assert mobile.manager_asset.startswith("KernelSU_v3.3.0")
    assert mobile.manager_sha256_ref == manager_sha256[:16]

    loaded = release_service.load_verified(AscensionMethod.KERNELSU_LKM)
    assert loaded is not None
    _release, manager_path = loaded
    manager_path.write_bytes(manager_path.read_bytes() + b"tampered")

    assert evidence_service.load(project_id, device) is None
    assessment_service = AscensionAssessmentService(
        store,
        DevicePackRegistry((_pack(source_digest),)),
        release_service,
    )
    recommendation = assessment_service.recommend(project_id, device)
    assert recommendation.method is AscensionMethod.MAGISK
    kernelsu = assessment_service.assess(project_id, AscensionMethod.KERNELSU_LKM, device)
    kernel_gate = next(gate for gate in kernelsu.gates if gate.gate_id == "kernel")
    assert "no authoritative local support evidence" in kernel_gate.detail


def test_official_release_is_digest_verified_and_receipted(tmp_path: Path) -> None:
    content = _manager_apk_bytes()
    service = _release_service(
        tmp_path,
        json_loader=lambda _url: _release_payload("Magisk-v30.7.apk", content),
        stream_loader=lambda url: (_Stream(content), len(content), url),
    )
    release = service.resolve_latest(AscensionMethod.MAGISK)
    progress: list[tuple[int, int]] = []
    receipt_state = []

    def report_progress(done: int, total: int) -> None:
        progress.append((done, total))
        if done >= total:
            root = tmp_path / "tools" / "ascension" / "magisk" / "v30.7"
            receipt_state.append((root / "official-root-artifact.romverse").is_file())

    path = service.acquire(release, report_progress)

    assert path.read_bytes() == content
    assert progress[-1] == (len(content), len(content))
    assert receipt_state == [True]
    receipt = json.loads((path.parent / "official-root-artifact.romverse").read_text())
    assert receipt["schema_version"] == 2
    assert len(receipt["receipt_digest"]) == 64
    assert receipt["execution_authority"] == "none"
    assert receipt["device_modified"] is False
    assert receipt["apk_structure"]["valid"] is True
    assert receipt["apk_structure"]["manifest_present"] is True
    assert receipt["apk_structure"]["dex_count"] == 1
    assert receipt["apk_identity"]["signature_verified"] is True
    assert (
        receipt["apk_identity"]["signer_sha256"]
        == OfficialRootReleaseService.OFFICIAL_SIGNERS[AscensionMethod.MAGISK]
    )
    if os.name != "nt":
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert (
            stat.S_IMODE((path.parent / "official-root-artifact.romverse").stat().st_mode) == 0o600
        )


def test_official_release_vault_rejects_a_redirected_ascension_directory(
    tmp_path: Path,
) -> None:
    content = _manager_apk_bytes()
    outside = tmp_path.parent / f"{tmp_path.name}-redirect-target"
    outside.mkdir()
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "ascension").symlink_to(outside, target_is_directory=True)
    service = _release_service(
        tmp_path,
        json_loader=lambda _url: _release_payload("Magisk-v30.7.apk", content),
        stream_loader=lambda url: (_Stream(content), len(content), url),
    )

    with pytest.raises(OSError, match="unsafe"):
        service.acquire(service.resolve_latest(AscensionMethod.MAGISK))

    assert not tuple(outside.iterdir())


@pytest.mark.parametrize(
    "mutation",
    (
        "top-extra",
        "release-extra",
        "asset-extra",
        "structure-extra",
        "identity-extra",
        "schema-bool",
        "digest-wrong-type",
    ),
)
def test_vaulted_manager_rejects_resealed_noncanonical_receipt_shapes(
    tmp_path: Path,
    mutation: str,
) -> None:
    content = _manager_apk_bytes()
    service = _release_service(
        tmp_path,
        json_loader=lambda _url: _release_payload("Magisk-v30.7.apk", content),
        stream_loader=lambda url: (_Stream(content), len(content), url),
    )
    manager = service.acquire(service.resolve_latest(AscensionMethod.MAGISK))
    receipt_path = manager.parent / "official-root-artifact.romverse"
    receipt = json.loads(receipt_path.read_text())

    if mutation == "top-extra":
        receipt["unexpected"] = "rejected"
    elif mutation == "release-extra":
        receipt["release"]["unexpected"] = "rejected"
    elif mutation == "asset-extra":
        receipt["release"]["asset"]["unexpected"] = "rejected"
    elif mutation == "structure-extra":
        receipt["apk_structure"]["unexpected"] = False
    elif mutation == "identity-extra":
        receipt["apk_identity"]["unexpected"] = "rejected"
    elif mutation == "schema-bool":
        receipt["schema_version"] = True
    elif mutation == "digest-wrong-type":
        receipt["receipt_digest"] = 7
    if mutation != "digest-wrong-type":
        receipt["receipt_digest"] = service._receipt_digest(receipt)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    assert service.load_verified(AscensionMethod.MAGISK) is None


def test_vaulted_manager_receipt_cannot_rebind_equal_bytes_outside_exact_vault_path(
    tmp_path: Path,
) -> None:
    content = _manager_apk_bytes()
    service = _release_service(
        tmp_path,
        json_loader=lambda _url: _release_payload("Magisk-v30.7.apk", content),
        stream_loader=lambda url: (_Stream(content), len(content), url),
    )
    manager = service.acquire(service.resolve_latest(AscensionMethod.MAGISK))
    replacement = tmp_path / "tools" / "same-manager-different-path.apk"
    replacement.write_bytes(manager.read_bytes())
    receipt_path = manager.parent / "official-root-artifact.romverse"
    receipt = json.loads(receipt_path.read_text())
    receipt["workspace_path"] = replacement.relative_to(tmp_path).as_posix()
    receipt["receipt_digest"] = service._receipt_digest(receipt)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    assert service.load_verified(AscensionMethod.MAGISK) is None


def test_vaulted_manager_ignores_linked_tag_directories_and_candidate_floods(
    tmp_path: Path,
) -> None:
    content = _manager_apk_bytes()
    service = _release_service(
        tmp_path,
        json_loader=lambda _url: _release_payload("Magisk-v30.7.apk", content),
        stream_loader=lambda url: (_Stream(content), len(content), url),
    )
    manager = service.acquire(service.resolve_latest(AscensionMethod.MAGISK))
    original_tag = manager.parent
    relocated = tmp_path / "relocated-tag"
    original_tag.rename(relocated)
    original_tag.symlink_to(relocated, target_is_directory=True)

    assert service.load_verified(AscensionMethod.MAGISK) is None

    original_tag.unlink()
    relocated.rename(original_tag)
    provider_root = original_tag.parent
    for index in range(service.MAX_RECEIPTS + 1):
        (provider_root / f"v-flood-{index}").mkdir()

    assert service.load_verified(AscensionMethod.MAGISK) is None


def test_official_release_rejects_future_published_metadata(tmp_path: Path) -> None:
    content = _manager_apk_bytes()
    payload = _release_payload("Magisk-v30.7.apk", content)
    payload["published_at"] = "2099-01-01T00:00:00Z"
    service = _release_service(
        tmp_path,
        json_loader=lambda _url: payload,
        clock=lambda: datetime(2026, 8, 30, tzinfo=UTC),
    )

    with pytest.raises(ProjectError, match="future"):
        service.resolve_latest(AscensionMethod.MAGISK)


def test_official_release_rejects_boolean_size_in_caller_supplied_metadata(
    tmp_path: Path,
) -> None:
    content = _manager_apk_bytes()
    service = _release_service(
        tmp_path,
        json_loader=lambda _url: _release_payload("Magisk-v30.7.apk", content),
    )
    release = service.resolve_latest(AscensionMethod.MAGISK)
    invalid = replace(release, asset=replace(release.asset, size_bytes=True))

    with pytest.raises(ProjectError, match="size or SHA-256"):
        service.acquire(invalid)


def test_official_release_rejects_wrong_android_signing_certificate(tmp_path: Path) -> None:
    content = _manager_apk_bytes()

    def wrong_signer(path: Path, asset: OfficialRootAsset):
        return replace(
            _test_manager_inspector(path, asset),
            signer_sha256="f" * 64,
            signer_subject="CN=Untrusted replacement",
        )

    service = OfficialRootReleaseService(
        tmp_path,
        json_loader=lambda _url: _release_payload("Magisk-v30.7.apk", content),
        stream_loader=lambda url: (_Stream(content), len(content), url),
        apk_inspector=wrong_signer,
    )

    with pytest.raises(ProjectError, match="signer"):
        service.acquire(service.resolve_latest(AscensionMethod.MAGISK))

    assert not tuple((tmp_path / "tools" / "ascension").rglob("*.apk"))


def test_official_release_accepts_github_release_asset_cdn_redirect(tmp_path: Path) -> None:
    content = _manager_apk_bytes()
    service = _release_service(
        tmp_path,
        json_loader=lambda _url: _release_payload("Magisk-v30.7.apk", content),
        stream_loader=lambda _url: (
            _Stream(content),
            len(content),
            "https://release-assets.githubusercontent.com/github-production-release-asset/file",
        ),
    )

    path = service.acquire(service.resolve_latest(AscensionMethod.MAGISK))

    assert path.read_bytes() == content


def test_official_release_loads_only_a_still_verified_vaulted_artifact(
    tmp_path: Path,
) -> None:
    content = _manager_apk_bytes()
    service = _release_service(
        tmp_path,
        json_loader=lambda _url: _release_payload("Magisk-v30.7.apk", content),
        stream_loader=lambda url: (_Stream(content), len(content), url),
    )
    expected = service.acquire(service.resolve_latest(AscensionMethod.MAGISK))

    loaded = service.load_verified(AscensionMethod.MAGISK)

    assert loaded is not None
    release, path = loaded
    assert release.tag == "v30.7"
    assert path == expected
    expected.write_bytes(b"tampered artifact")
    assert service.load_verified(AscensionMethod.MAGISK) is None


def test_vaulted_manager_reruns_pinned_signature_check_on_every_reuse(tmp_path: Path) -> None:
    content = _manager_apk_bytes()
    inspections: list[str] = []

    def counting_inspector(path: Path, asset: OfficialRootAsset):
        inspections.append(hashlib.sha256(path.read_bytes()).hexdigest())
        return _test_manager_inspector(path, asset)

    service = OfficialRootReleaseService(
        tmp_path,
        json_loader=lambda _url: _release_payload("Magisk-v30.7.apk", content),
        stream_loader=lambda url: (_Stream(content), len(content), url),
        apk_inspector=counting_inspector,
    )
    service.acquire(service.resolve_latest(AscensionMethod.MAGISK))
    inspections.clear()

    assert service.load_verified(AscensionMethod.MAGISK) is not None
    assert inspections == [hashlib.sha256(content).hexdigest()]


def test_vaulted_manager_is_not_trusted_without_a_signature_verifier(
    tmp_path: Path,
    monkeypatch,
) -> None:
    content = _manager_apk_bytes()
    online = _release_service(
        tmp_path,
        json_loader=lambda _url: _release_payload("Magisk-v30.7.apk", content),
        stream_loader=lambda url: (_Stream(content), len(content), url),
    )
    online.acquire(online.resolve_latest(AscensionMethod.MAGISK))
    monkeypatch.setattr("romverse.ascension.releases.shutil.which", lambda _name: None)

    assert OfficialRootReleaseService(tmp_path).load_verified(AscensionMethod.MAGISK) is None


def test_official_release_uses_reverified_cache_when_online_refresh_fails(
    tmp_path: Path,
) -> None:
    content = _manager_apk_bytes()
    online = _release_service(
        tmp_path,
        json_loader=lambda _url: _release_payload("Magisk-v30.7.apk", content),
        stream_loader=lambda url: (_Stream(content), len(content), url),
    )
    expected = online.acquire(online.resolve_latest(AscensionMethod.MAGISK))

    def offline(_url: str) -> dict[str, object]:
        raise OSError("network unavailable")

    result = _release_service(
        tmp_path,
        json_loader=offline,
    ).acquire_latest_or_verified(AscensionMethod.MAGISK)

    assert result.mode == "verified-cache"
    assert result.path == expected
    assert result.release.repository == "topjohnwu/Magisk"
    assert "network unavailable" in result.explanation
    assert "revalidated" in result.explanation


def test_official_release_never_masks_rejected_upstream_trust_with_cache(
    tmp_path: Path,
) -> None:
    content = _manager_apk_bytes()
    online = _release_service(
        tmp_path,
        json_loader=lambda _url: _release_payload("Magisk-v30.7.apk", content),
        stream_loader=lambda url: (_Stream(content), len(content), url),
    )
    online.acquire(online.resolve_latest(AscensionMethod.MAGISK))
    rejected = _release_payload("Magisk-v30.7.apk", content)
    rejected["html_url"] = "https://github.com/example/not-magisk/releases/tag/v30.7"

    with pytest.raises(ProjectError, match="expected repository") as rejected_error:
        _release_service(
            tmp_path,
            json_loader=lambda _url: rejected,
        ).acquire_latest_or_verified(AscensionMethod.MAGISK)
    assert not isinstance(rejected_error.value, OfficialRootConnectivityError)


def test_official_release_refuses_stale_cache_when_freshness_service_is_offline(
    tmp_path: Path,
) -> None:
    content = _manager_apk_bytes()
    acquired_at = datetime(2026, 7, 1, tzinfo=UTC)
    online = _release_service(
        tmp_path,
        json_loader=lambda _url: _release_payload("Magisk-v30.7.apk", content),
        stream_loader=lambda url: (_Stream(content), len(content), url),
        clock=lambda: acquired_at,
    )
    online.acquire(online.resolve_latest(AscensionMethod.MAGISK))

    def offline(_url: str) -> dict[str, object]:
        raise OSError("network unavailable")

    with pytest.raises(OfficialRootConnectivityError, match="31 days old"):
        _release_service(
            tmp_path,
            json_loader=offline,
            clock=lambda: acquired_at + timedelta(days=31),
        ).acquire_latest_or_verified(AscensionMethod.MAGISK)


def test_legacy_root_receipt_remains_loadable_but_cannot_claim_offline_freshness(
    tmp_path: Path,
) -> None:
    content = _manager_apk_bytes()
    online = _release_service(
        tmp_path,
        json_loader=lambda _url: _release_payload("Magisk-v30.7.apk", content),
        stream_loader=lambda url: (_Stream(content), len(content), url),
    )
    manager = online.acquire(online.resolve_latest(AscensionMethod.MAGISK))
    receipt_path = manager.parent / "official-root-artifact.romverse"
    receipt = json.loads(receipt_path.read_text())
    receipt["schema_version"] = 1
    receipt.pop("receipt_digest")
    receipt_path.write_text(json.dumps(receipt))
    assert online.load_verified(AscensionMethod.MAGISK) is not None

    def offline(_url: str) -> dict[str, object]:
        raise OSError("network unavailable")

    with pytest.raises(
        OfficialRootConnectivityError,
        match="predates ROMVERSE freshness receipts",
    ):
        _release_service(
            tmp_path,
            json_loader=offline,
        ).acquire_latest_or_verified(AscensionMethod.MAGISK)


def test_root_freshness_receipt_tampering_invalidates_the_vault_record(tmp_path: Path) -> None:
    content = _manager_apk_bytes()
    service = _release_service(
        tmp_path,
        json_loader=lambda _url: _release_payload("Magisk-v30.7.apk", content),
        stream_loader=lambda url: (_Stream(content), len(content), url),
    )
    manager = service.acquire(service.resolve_latest(AscensionMethod.MAGISK))
    receipt_path = manager.parent / "official-root-artifact.romverse"
    receipt = json.loads(receipt_path.read_text())
    receipt["retrieved_at"] = "2099-01-01T00:00:00+00:00"
    receipt_path.write_text(json.dumps(receipt))

    assert service.load_verified(AscensionMethod.MAGISK) is None


def test_vaulted_release_cannot_rebind_itself_to_another_github_repository(
    tmp_path: Path,
) -> None:
    content = _manager_apk_bytes()
    service = _release_service(
        tmp_path,
        json_loader=lambda _url: _release_payload("Magisk-v30.7.apk", content),
        stream_loader=lambda url: (_Stream(content), len(content), url),
    )
    path = service.acquire(service.resolve_latest(AscensionMethod.MAGISK))
    receipt_path = path.parent / "official-root-artifact.romverse"
    receipt = json.loads(receipt_path.read_text())
    receipt["release"]["repository"] = "example/Magisk"
    receipt["release"]["source_url"] = "https://github.com/example/Magisk/releases/tag/v30.7"
    receipt["release"]["asset"]["repository"] = "example/Magisk"
    receipt["release"]["asset"]["download_url"] = (
        "https://github.com/example/Magisk/releases/download/v30.7/Magisk-v30.7.apk"
    )
    receipt_path.write_text(json.dumps(receipt))

    assert service.load_verified(AscensionMethod.MAGISK) is None


def test_official_release_rejects_unpinned_or_wrong_artifact(tmp_path: Path) -> None:
    payload = _release_payload("Magisk-v30.7-debug.apk", b"debug")
    service = _release_service(tmp_path, json_loader=lambda _url: payload)
    with pytest.raises(ProjectError, match="exactly one"):
        service.resolve_latest(AscensionMethod.MAGISK)

    content = _manager_apk_bytes()
    service = _release_service(
        tmp_path,
        json_loader=lambda _url: _release_payload("Magisk-v30.7.apk", content),
        stream_loader=lambda url: (_Stream(b"tampered"), len(content), url),
    )
    with pytest.raises(ProjectError, match="SHA-256"):
        service.acquire(service.resolve_latest(AscensionMethod.MAGISK))

    wrong_repository = _release_payload("Magisk-v30.7.apk", content)
    wrong_repository["html_url"] = "https://github.com/example/not-magisk/releases/tag/v30.7"
    service = _release_service(
        tmp_path,
        json_loader=lambda _url: wrong_repository,
    )
    with pytest.raises(ProjectError, match="expected repository"):
        service.resolve_latest(AscensionMethod.MAGISK)

    mismatched_tag = _release_payload("Magisk-v30.7.apk", content)
    mismatched_tag["assets"][0]["browser_download_url"] = (
        "https://github.com/topjohnwu/Magisk/releases/download/v30.6/Magisk-v30.7.apk"
    )
    service = _release_service(
        tmp_path,
        json_loader=lambda _url: mismatched_tag,
    )
    with pytest.raises(ProjectError, match="exact release tag"):
        service.resolve_latest(AscensionMethod.MAGISK)

    wrong_content_type = _release_payload("Magisk-v30.7.apk", content)
    wrong_content_type["assets"][0]["content_type"] = "application/octet-stream"
    service = _release_service(
        tmp_path,
        json_loader=lambda _url: wrong_content_type,
    )
    with pytest.raises(ProjectError, match="exactly one"):
        service.resolve_latest(AscensionMethod.MAGISK)

    oversized = _release_payload("Magisk-v30.7.apk", content)
    oversized["assets"][0]["size"] = OfficialRootReleaseService.MAX_ASSET_BYTES + 1
    service = _release_service(
        tmp_path,
        json_loader=lambda _url: oversized,
    )
    with pytest.raises(ProjectError, match="exactly one"):
        service.resolve_latest(AscensionMethod.MAGISK)


def test_official_release_rejects_digest_pinned_non_apk_bytes(tmp_path: Path) -> None:
    content = b"not actually an Android package"
    service = _release_service(
        tmp_path,
        json_loader=lambda _url: _release_payload("Magisk-v30.7.apk", content),
        stream_loader=lambda url: (_Stream(content), len(content), url),
    )

    with pytest.raises(ProjectError, match="structure validation"):
        service.acquire(service.resolve_latest(AscensionMethod.MAGISK))

    assert not tuple((tmp_path / "tools" / "ascension").rglob("*.apk"))


def _boot_v4(ramdisk: bytes = b"ramdisk", kernel: bytes = b"") -> bytes:
    header = bytearray(1584)
    header[:8] = b"ANDROID!"
    struct.pack_into("<I", header, 8, len(kernel))
    struct.pack_into("<I", header, 12, len(ramdisk))
    struct.pack_into("<I", header, 20, len(header))
    struct.pack_into("<I", header, 40, 4)
    image = bytes(header).ljust(4096, b"\0") + kernel
    image = image.ljust((len(image) + 4095) // 4096 * 4096, b"\0")
    return image + ramdisk


def _magisk_release(path: Path, tag: str) -> OfficialRootRelease:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    asset = OfficialRootAsset(
        AscensionMethod.MAGISK,
        "topjohnwu/Magisk",
        tag,
        "2026-02-23T00:00:00Z",
        path.name,
        path.stat().st_size,
        digest,
        f"https://github.com/topjohnwu/Magisk/releases/download/{tag}/{path.name}",
    )
    return OfficialRootRelease(
        AscensionMethod.MAGISK,
        asset.repository,
        tag,
        asset.published_at,
        asset,
        f"https://github.com/topjohnwu/Magisk/releases/tag/{tag}",
    )


def test_new_official_manager_rebuilds_capsule_and_invalidates_old_patch(
    tmp_path: Path,
) -> None:
    store, project_id, _source_digest = _project(tmp_path)
    images = store.working_root / project_id / "tree" / "images"
    images.mkdir(parents=True)
    (images / "init_boot.img").write_bytes(_boot_v4(b"pristine"))
    (images / "recovery.img").write_bytes(b"recovery")
    AscensionEvidenceService(store).ensure(project_id, "images/init_boot.img")
    managers = store.workspace / "tools" / "test"
    managers.mkdir(parents=True)
    old_manager = managers / "Magisk-v30.7.apk"
    old_manager.write_bytes(b"old verified manager")
    new_manager = managers / "Magisk-v30.8.apk"
    new_manager.write_bytes(b"new verified manager")
    old_release = _magisk_release(old_manager, "v30.7")
    new_release = _magisk_release(new_manager, "v30.8")
    trust = ExplicitTestRootReleaseService(old_release, old_manager)
    service = RootPatchPreparationService(store, trust)

    old_capsule = service.prepare(
        project_id,
        AscensionMethod.MAGISK,
        old_release,
        old_manager,
    )
    patched = tmp_path / "magisk_patched.img"
    patched.write_bytes(_boot_v4(b"patched"))
    assert service.import_patched(project_id, AscensionMethod.MAGISK, patched) is not None
    assert not service.matches_release(old_capsule, new_release)

    trust.set_verified(new_release, new_manager)
    new_capsule = service.prepare(
        project_id,
        AscensionMethod.MAGISK,
        new_release,
        new_manager,
    )

    assert service.matches_release(new_capsule, new_release)
    assert new_capsule.capsule_digest != old_capsule.capsule_digest
    assert new_capsule.manager_tag == "v30.8"
    assert service.load_patched(project_id, AscensionMethod.MAGISK) is None


def test_root_patch_capsule_and_patched_image_are_source_bound_and_reloadable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store, project_id, _source_digest = _project(tmp_path)
    images = store.working_root / project_id / "tree" / "images"
    images.mkdir(parents=True)
    pristine = _boot_v4(b"pristine ramdisk")
    (images / "init_boot.img").write_bytes(pristine)
    (images / "recovery.img").write_bytes(b"stock recovery")
    AscensionEvidenceService(store).ensure(project_id, "images/init_boot.img")

    manager = store.workspace / "tools" / "test" / "Magisk-v30.7.apk"
    manager.parent.mkdir(parents=True)
    manager.write_bytes(b"verified official manager")
    manager_digest = hashlib.sha256(manager.read_bytes()).hexdigest()
    asset = OfficialRootAsset(
        AscensionMethod.MAGISK,
        "topjohnwu/Magisk",
        "v30.7",
        "2026-02-23T00:00:00Z",
        manager.name,
        manager.stat().st_size,
        manager_digest,
        "https://github.com/topjohnwu/Magisk/releases/download/v30.7/Magisk-v30.7.apk",
    )
    release = OfficialRootRelease(
        AscensionMethod.MAGISK,
        asset.repository,
        asset.tag,
        asset.published_at,
        asset,
        "https://github.com/topjohnwu/Magisk/releases/tag/v30.7",
    )
    trust = ExplicitTestRootReleaseService(release, manager)
    with pytest.raises(ProjectError, match="signature-verified official Manager"):
        RootPatchPreparationService(store).prepare(
            project_id,
            AscensionMethod.MAGISK,
            release,
            manager,
        )
    service = RootPatchPreparationService(store, trust)
    progress: list[int] = []

    capsule = service.prepare(
        project_id,
        AscensionMethod.MAGISK,
        release,
        manager,
        progress.append,
    )

    assert progress[0] == 0
    assert progress[-1] == 100
    assert progress == sorted(progress)
    assert any(0 < value < 100 for value in progress)
    assert capsule.authority == "verified-root-patch-inputs-only"
    assert capsule.phone_changed is False
    assert service.load(project_id, AscensionMethod.MAGISK) == capsule

    patched = tmp_path / "magisk_patched.img"
    patched.write_bytes(_boot_v4(b"patched ramdisk"))
    patched_progress: list[int] = []
    receipt = service.import_patched(
        project_id,
        AscensionMethod.MAGISK,
        patched,
        patched_progress.append,
    )

    assert patched_progress[0] == 0
    assert patched_progress[-1] == 100
    assert patched_progress == sorted(set(patched_progress))
    assert any(0 < value < 100 for value in patched_progress)
    assert receipt.schema_version == 2
    assert receipt.source_image_sha256 == capsule.input_image_sha256
    assert receipt.verification_scope == "source-capsule-and-immutable-lineage-consistency"
    assert receipt.lineage_scope == "normalized-header-kernelless"
    assert receipt.lineage_confidence == "limited"
    assert len(receipt.normalized_header_sha256) == 64
    assert receipt.flash_authority == "none"
    assert receipt.phone_changed is False
    assert service.load_patched(project_id, AscensionMethod.MAGISK) == receipt

    patched_receipt_path = (
        store.projects_root
        / project_id
        / "ascension"
        / "patched"
        / AscensionMethod.MAGISK.value
        / service.PATCHED_NAME
    )
    legacy_document = json.loads(patched_receipt_path.read_text(encoding="utf-8"))
    legacy_payload = {
        key: value
        for key, value in legacy_document.items()
        if key
        not in {
            "format",
            "receipt_digest",
            "lineage_scope",
            "lineage_confidence",
            "normalized_header_sha256",
            "source_kernel_size_bytes",
            "patched_kernel_size_bytes",
            "source_kernel_sha256",
            "patched_kernel_sha256",
        }
    }
    legacy_payload["schema_version"] = 1
    legacy_payload["verification_scope"] = "source-bound-structural-patch-candidate"
    patched_receipt_path.write_text(
        json.dumps(
            {
                "format": service.PATCHED_FORMAT,
                **legacy_payload,
                "receipt_digest": hashlib.sha256(
                    json.dumps(
                        legacy_payload,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    assert service.load_patched(project_id, AscensionMethod.MAGISK) == receipt

    device = AndroidDevice(
        "exact-serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="17 Pro Max",
        codename="popsicle",
        slot_suffix="_a",
        bootloader_locked=False,
    )
    planning = AscensionRootPlanService(store)
    with pytest.raises(ProjectError, match="Integrate and seal"):
        planning.create(project_id, AscensionMethod.MAGISK, device)

    integration = RootRomIntegrationService(store).integrate(project_id, AscensionMethod.MAGISK)
    build_handoff = RootRomBuildHandoffService(store).seal(project_id, AscensionMethod.MAGISK)
    assert build_handoff.integration_digest == integration.integration_digest

    plan = planning.create(project_id, AscensionMethod.MAGISK, device)

    assert plan.target_partition == "init_boot"
    assert plan.patched_image_sha256 == receipt.patched_image_sha256
    assert plan.build_handoff_digest == build_handoff.handoff_digest
    assert plan.root_image_artifact_sha256 == receipt.patched_image_sha256
    assert plan.execution_authority == "guardian-review-only"
    assert plan.command_manifest == ()
    assert not plan.bootloader_relock_allowed
    assert not plan.phone_changed
    dna = DeviceDnaStore(store).load(project_id)
    assert dna is not None
    assert plan.device_dna_digest == dna.profile_digest
    assert plan.device_dna_identity_state == CapabilityState.SUPPORTED.value
    assert planning.load(project_id, AscensionMethod.MAGISK) == plan
    assert planning.matches_device(plan, device)

    DeviceDnaService(store, DevicePackRegistry(())).refresh(
        project_id,
        replace(device, model="unexpected-model-change"),
    )
    assert planning.load(project_id, AscensionMethod.MAGISK) is None
    DeviceDnaService(store, DevicePackRegistry(())).refresh(project_id, device)
    plan = planning.create(project_id, AscensionMethod.MAGISK, device)
    assert planning.load(project_id, AscensionMethod.MAGISK) == plan

    manifest_service = AscensionGuardianManifestService(
        store, DevicePackRegistry((_pack(plan.source_original_sha256),))
    )
    manifest = manifest_service.prepare(project_id, AscensionMethod.MAGISK, device)
    states = {check.check_id: check.state for check in manifest.checks}
    actions = {check.check_id: check.action_id for check in manifest.checks}
    assert states["root-plan"] is ManifestState.PASS
    assert states["patch-lineage"] is ManifestState.ATTENTION
    assert states["exact-device"] is ManifestState.PASS
    assert states["flash-policy"] is ManifestState.BLOCKED
    assert states["user-backup"] is ManifestState.BLOCKED
    assert actions["user-backup"] == "open-backup-guide"
    assert actions["flash-policy"] == "open-device-atlas"
    assert manifest.command_manifest == ()
    assert manifest.execution_authority == "none"
    assert manifest.final_consent_required
    assert not manifest.bootloader_relock_allowed
    assert not manifest.phone_changed
    assert "Bootloader relock" in manifest.prohibited_actions
    assert manifest_service.load(project_id, AscensionMethod.MAGISK) == manifest
    assert manifest_service.matches_device(manifest, device)

    companion_status = AscensionCompanionStatusService(
        store,
        DevicePackRegistry((_pack(plan.source_original_sha256),)),
    ).snapshot(project_id)
    assert companion_status.state == "blocked"
    assert companion_status.project_name == "Ascension"
    assert companion_status.method == "magisk"
    assert companion_status.target_partition == "init_boot"
    assert companion_status.blocker_count == len(manifest.blockers)
    assert companion_status.phone_changed is False
    assert companion_status.execution_authority == "none"

    wrong_phone_status = AscensionCompanionStatusService(
        store,
        DevicePackRegistry((_pack(plan.source_original_sha256),)),
    ).snapshot(
        project_id,
        replace(device, serial="different-authorized-phone"),
    )
    assert wrong_phone_status.state == "blocked"
    assert wrong_phone_status.method == "magisk"
    assert wrong_phone_status.blocker_count == 1

    manifest_path = (
        store.projects_root / project_id / "ascension" / "guardian" / manifest_service.RECEIPT_NAME
    )
    tampered_manifest = json.loads(manifest_path.read_text())
    tampered_manifest["command_manifest"] = [["fastboot", "flash", "init_boot", "unknown.img"]]
    manifest_path.write_text(json.dumps(tampered_manifest))
    assert manifest_service.load(project_id, AscensionMethod.MAGISK) is None

    BackupHandoffService(store).confirm_cloud(
        project_id,
        device,
        CloudBackupProvider.GOOGLE,
        "Completed today at 15:42",
        backup_completed=True,
        restore_access_confirmed=True,
        critical_data_scope_reviewed=True,
        limitations_acknowledged=True,
    )
    assert planning.load(project_id, AscensionMethod.MAGISK) is None
    cloud_plan = planning.create(project_id, AscensionMethod.MAGISK, device)
    assert not cloud_plan.external_backup_verified
    assert cloud_plan.backup_handoff_ready
    assert cloud_plan.backup_evidence_kind == "user-confirmed-cloud"
    cloud_manifest = manifest_service.prepare(
        project_id,
        AscensionMethod.MAGISK,
        device,
    )
    cloud_backup_check = next(
        check for check in cloud_manifest.checks if check.check_id == "user-backup"
    )
    assert cloud_backup_check.state is ManifestState.PASS
    assert "did not inspect" in cloud_backup_check.evidence

    backup = tmp_path / "phone-backup.zip"
    backup.write_bytes(b"independently readable phone backup")
    RecoveryEvidenceService(store).register(project_id, "external_backup", backup)
    assert planning.load(project_id, AscensionMethod.MAGISK) is None
    refreshed_plan = planning.create(project_id, AscensionMethod.MAGISK, device)
    assert refreshed_plan.external_backup_verified
    assert refreshed_plan.backup_handoff_ready
    assert refreshed_plan.backup_evidence_kind == "verified-local-file"

    from types import SimpleNamespace

    from romverse.rom.source_intelligence import FirmwareSourceIntelligenceService

    blueprint = SimpleNamespace(
        source_kind="ota-payload",
        source_archive_sha256=refreshed_plan.source_original_sha256,
        codename="popsicle",
        baseline_candidate_ready=True,
    )
    monkeypatch.setattr(FirmwareSourceIntelligenceService, "load", lambda *_args: blueprint)
    private_review = manifest_service.prepare(
        project_id,
        AscensionMethod.MAGISK,
        device,
    )
    private_states = {check.check_id: check.state for check in private_review.checks}
    assert private_states["source-contract"] is ManifestState.PASS
    assert private_states["flash-policy"] is ManifestState.ATTENTION
    assert private_states["slot-policy"] is ManifestState.ATTENTION
    assert private_states["user-backup"] is ManifestState.PASS
    assert private_review.review_ready
    assert private_review.command_manifest == ()
    assert private_review.execution_authority == "none"
    assert not private_review.bootloader_relock_allowed

    plan_path = store.projects_root / project_id / "ascension" / "plan" / planning.RECEIPT_NAME
    tampered = json.loads(plan_path.read_text())
    tampered["command_manifest"] = ["fastboot flash init_boot unknown.img"]
    plan_path.write_text(json.dumps(tampered))
    assert planning.load(project_id, AscensionMethod.MAGISK) is None


def test_root_patch_import_rejects_unmodified_or_invalid_output(tmp_path: Path) -> None:
    store, project_id, _source_digest = _project(tmp_path)
    images = store.working_root / project_id / "tree" / "images"
    images.mkdir(parents=True)
    pristine = _boot_v4()
    (images / "init_boot.img").write_bytes(pristine)
    AscensionEvidenceService(store).ensure(project_id, "images/init_boot.img")
    manager = store.workspace / "tools" / "test" / "Magisk.apk"
    manager.parent.mkdir(parents=True)
    manager.write_bytes(b"manager")
    digest = hashlib.sha256(manager.read_bytes()).hexdigest()
    asset = OfficialRootAsset(
        AscensionMethod.MAGISK,
        "topjohnwu/Magisk",
        "v1",
        "2026-01-01T00:00:00Z",
        manager.name,
        manager.stat().st_size,
        digest,
        "https://github.com/topjohnwu/Magisk/releases/download/v1/Magisk.apk",
    )
    release = OfficialRootRelease(
        AscensionMethod.MAGISK,
        asset.repository,
        asset.tag,
        asset.published_at,
        asset,
        "https://github.com/topjohnwu/Magisk/releases/tag/v1",
    )
    service = RootPatchPreparationService(
        store,
        ExplicitTestRootReleaseService(release, manager),
    )
    service.prepare(project_id, AscensionMethod.MAGISK, release, manager)
    identical = tmp_path / "identical.img"
    identical.write_bytes(pristine)
    invalid = tmp_path / "invalid.img"
    invalid.write_bytes(b"not an Android boot image" * 4)
    wrong_manager = tmp_path / "KernelSU_patched-android16.img"
    wrong_manager.write_bytes(_boot_v4(b"different manager output"))
    wrong_header = bytearray(_boot_v4(b"different source output"))
    wrong_header[44] = 1
    wrong_source = tmp_path / "magisk_patched-wrong-source.img"
    wrong_source.write_bytes(wrong_header)

    with pytest.raises(ProjectError, match="byte-identical"):
        service.import_patched(project_id, AscensionMethod.MAGISK, identical)
    with pytest.raises(ProjectError, match="recognized Android boot image"):
        service.import_patched(project_id, AscensionMethod.MAGISK, invalid)
    with pytest.raises(ProjectError, match="KernelSU LKM output.*Magisk route"):
        service.import_patched(project_id, AscensionMethod.MAGISK, wrong_manager)
    with pytest.raises(ProjectError, match="immutable Android header lineage"):
        service.import_patched(project_id, AscensionMethod.MAGISK, wrong_source)


def test_guardian_approved_ascension_handoff_installs_and_transfers_only(
    tmp_path: Path,
) -> None:
    from romverse.ascension.output import RootPatchedOutputService
    from romverse.guardian.approval import ApprovalStore
    from romverse.guardian.gateway import ExecutionGateway
    from romverse.guardian.models import GuardianDeniedError
    from romverse.guardian.policy import GuardianPolicy

    store, project_id, _source_digest = _project(tmp_path)
    images = store.working_root / project_id / "tree" / "images"
    images.mkdir(parents=True)
    (images / "init_boot.img").write_bytes(_boot_v4(b"pristine root patch input"))
    (images / "recovery.img").write_bytes(b"stock recovery")
    AscensionEvidenceService(store).ensure(project_id, "images/init_boot.img")
    manager = store.workspace / "tools" / "test" / "Magisk-v30.7.apk"
    manager.parent.mkdir(parents=True)
    with zipfile.ZipFile(manager, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"manifest")
        archive.writestr("classes.dex", b"dex\n035\0")
        archive.writestr("META-INF/TEST.RSA", b"signature")
    manager_digest = hashlib.sha256(manager.read_bytes()).hexdigest()
    asset = OfficialRootAsset(
        AscensionMethod.MAGISK,
        "topjohnwu/Magisk",
        "v30.7",
        "2026-02-23T00:00:00Z",
        manager.name,
        manager.stat().st_size,
        manager_digest,
        "https://github.com/topjohnwu/Magisk/releases/download/v30.7/Magisk-v30.7.apk",
    )
    release = OfficialRootRelease(
        AscensionMethod.MAGISK,
        asset.repository,
        asset.tag,
        asset.published_at,
        asset,
        "https://github.com/topjohnwu/Magisk/releases/tag/v30.7",
    )
    manager_bytes = manager.read_bytes()
    release_service = _release_service(
        store.workspace,
        stream_loader=lambda url: (_Stream(manager_bytes), len(manager_bytes), url),
    )
    manager = release_service.acquire(release)
    RootPatchPreparationService(store, release_service).prepare(
        project_id,
        AscensionMethod.MAGISK,
        release,
        manager,
    )
    device = AndroidDevice(
        "PRIVATE-SERIAL",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="17 Pro Max",
        codename="popsicle",
        battery_percent=90,
        storage=StorageInfo(512 * 1024**3, 100 * 1024**3, 400 * 1024**3, 20),
    )

    class Runner:
        def __init__(self) -> None:
            self.calls: list[tuple[str, ...]] = []
            self.scan_stdout = (
                "notes.txt\n"
                "magisk_patched-31000_new.img\n"
                "KernelSU_patched-android16.img\n"
                "magisk_patched-27000_abcd.img\n"
                "magisk_patched-unsafe.zip\n"
            )

        def run(self, args, timeout=10, cwd=None):
            call = tuple(map(str, args))
            self.calls.append(call)
            if "install" in call:
                stdout = "Performing Streamed Install\nSuccess\n"
            elif "ls" in call:
                stdout = self.scan_stdout
            elif "pull" in call:
                Path(call[-1]).write_bytes(_boot_v4(b"manager patched output"))
                stdout = "1 file pulled\n"
            else:
                stdout = "1 file pushed\n"
            return CommandResult(call, 0, stdout, "")

    approvals = ApprovalStore(store.workspace)
    runner = Runner()
    gateway = ExecutionGateway(GuardianPolicy(store.workspace), runner)
    handoff = RootPatchHandoffService(
        store,
        Path("/usr/bin/adb"),
        gateway,
        approvals,
        release_service=release_service,
    )
    plan = handoff.plan(project_id, AscensionMethod.MAGISK, device)

    assert plan.safety_ready
    with pytest.raises(GuardianDeniedError, match="explicitly approved"):
        handoff.execute(plan)
    assert runner.calls == []

    rogue_manager = store.workspace / "rogue-manager.apk"
    rogue_manager.write_bytes(manager.read_bytes())
    forged_plan = replace(
        plan,
        manager_path=str(rogue_manager),
        apk_plan=replace(
            plan.apk_plan,
            request=replace(plan.apk_plan.request, apk_path=str(rogue_manager)),
        ),
    )
    with pytest.raises(GuardianDeniedError, match="Manager plan changed"):
        handoff.execute(forged_plan)
    assert runner.calls == []

    approvals.issue(plan.apk_plan.digest, plan.device_key)
    approvals.issue(plan.transfer_digest, plan.device_key)
    progress: list[int] = []
    receipt = handoff.execute(plan, progress.append)

    assert progress == []
    assert receipt.manager_installed
    assert receipt.input_transferred
    assert not receipt.root_applied
    assert not receipt.image_flashed
    assert receipt.phone_changed
    assert handoff.load(project_id, AscensionMethod.MAGISK) == receipt
    handoff_root = store.projects_root / project_id / "ascension" / "handoff"
    handoff_path = handoff_root / handoff.RECEIPT_NAME
    handoff_history = handoff_root / f"phone-handoff-{receipt.receipt_id[:12]}.romverse"
    assert stat.S_IMODE(handoff_root.stat().st_mode) == 0o700
    assert stat.S_IMODE(handoff_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(handoff_history.stat().st_mode) == 0o600
    handoff_original = handoff_path.read_bytes()
    handoff_document = json.loads(handoff_original)
    handoff_document["unexpected_field"] = "must fail closed"
    handoff_path.write_text(json.dumps(handoff_document), encoding="utf-8")
    assert handoff.load(project_id, AscensionMethod.MAGISK) is None
    handoff_document = json.loads(handoff_original)
    handoff_document["manager_installed"] = 1
    handoff_unsigned = {
        key: value
        for key, value in handoff_document.items()
        if key not in {"format", "receipt_digest"}
    }
    handoff_document["receipt_digest"] = hashlib.sha256(
        json.dumps(handoff_unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    handoff_path.write_text(json.dumps(handoff_document), encoding="utf-8")
    assert handoff.load(project_id, AscensionMethod.MAGISK) is None
    handoff_path.write_bytes(handoff_original)
    with handoff_path.open("r+b") as stream:
        stream.truncate(handoff.MAX_RECEIPT_BYTES + 1)
    assert handoff.load(project_id, AscensionMethod.MAGISK) is None
    handoff_path.write_bytes(handoff_original)
    outside_handoff = tmp_path / "outside-phone-handoff.romverse"
    outside_handoff.write_bytes(handoff_original)
    handoff_path.unlink()
    handoff_path.symlink_to(outside_handoff)
    assert handoff.load(project_id, AscensionMethod.MAGISK) is None
    handoff_path.unlink()
    handoff_path.write_bytes(handoff_original)
    assert handoff.load(project_id, AscensionMethod.MAGISK) == receipt
    assert len(runner.calls) == 2
    assert runner.calls[0][3] == "install"
    assert runner.calls[1][3] == "push"
    assert all("fastboot" not in part for call in runner.calls for part in call)

    companion_handoff = AscensionCompanionStatusService(
        store,
        DevicePackRegistry(()),
        release_service=release_service,
    ).snapshot(project_id, device)
    assert companion_handoff.stage_number == 5
    assert companion_handoff.target_partition == "init_boot"
    assert "patched image" in companion_handoff.stage_title.casefold()
    assert "select the ROMVERSE image" in companion_handoff.next_action

    outputs = RootPatchedOutputService(store, Path("/usr/bin/adb"), gateway, approvals)
    list_digest = outputs.list_digest(device.serial)
    approvals.issue(list_digest, plan.device_key)
    assert outputs.find(project_id, AscensionMethod.MAGISK, device.serial) == (
        "magisk_patched-31000_new.img",
        "magisk_patched-27000_abcd.img",
    )
    discovery = outputs.load_discovery(
        project_id,
        AscensionMethod.MAGISK,
        device.serial,
    )
    assert discovery is not None
    assert discovery.state == "found"
    assert discovery.candidate_count == 2
    assert discovery.recommended_name_ref == discovery.candidate_refs[0]
    assert not discovery.truncated
    assert discovery.data_scope == "filenames-only"
    assert not discovery.phone_changed
    assert discovery.execution_authority == "none"
    discovery_path = (
        store.projects_root
        / project_id
        / "ascension"
        / "phone-output"
        / AscensionMethod.MAGISK.value
        / outputs.DISCOVERY_NAME
    )
    discovery_document = discovery_path.read_text(encoding="utf-8")
    assert "PRIVATE-SERIAL" not in discovery_document
    assert "magisk_patched-31000_new.img" not in discovery_document
    assert "magisk_patched-27000_abcd.img" not in discovery_document
    discovery_history = discovery_path.parent / f"discovery-{discovery.discovery_id[:12]}.romverse"
    assert stat.S_IMODE(discovery_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(discovery_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(discovery_history.stat().st_mode) == 0o600
    discovery_original = discovery_path.read_bytes()
    hostile_discovery = json.loads(discovery_original)
    hostile_discovery["unexpected_field"] = "must fail closed"
    discovery_path.write_text(json.dumps(hostile_discovery), encoding="utf-8")
    assert outputs.load_discovery(project_id, AscensionMethod.MAGISK, device.serial) is None
    hostile_discovery = json.loads(discovery_original)
    hostile_discovery["candidate_count"] = True
    discovery_unsigned = {
        key: value
        for key, value in hostile_discovery.items()
        if key not in {"format", "receipt_digest"}
    }
    hostile_discovery["receipt_digest"] = hashlib.sha256(
        json.dumps(discovery_unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    discovery_path.write_text(json.dumps(hostile_discovery), encoding="utf-8")
    assert outputs.load_discovery(project_id, AscensionMethod.MAGISK, device.serial) is None
    discovery_path.write_bytes(discovery_original)
    with discovery_path.open("r+b") as stream:
        stream.truncate(outputs.MAX_RECEIPT_BYTES + 1)
    assert outputs.load_discovery(project_id, AscensionMethod.MAGISK, device.serial) is None
    discovery_path.write_bytes(discovery_original)
    outside_discovery = tmp_path / "outside-discovery.romverse"
    outside_discovery.write_bytes(discovery_original)
    discovery_path.unlink()
    discovery_path.symlink_to(outside_discovery)
    assert outputs.load_discovery(project_id, AscensionMethod.MAGISK, device.serial) is None
    discovery_path.unlink()
    discovery_path.write_bytes(discovery_original)
    assert outputs.load_discovery(project_id, AscensionMethod.MAGISK, device.serial) == discovery
    with pytest.raises(ProjectError, match="selected Magisk route"):
        outputs.plan(
            project_id,
            AscensionMethod.MAGISK,
            device.serial,
            "KernelSU_patched-android16.img",
        )
    output_plan = outputs.plan(
        project_id,
        AscensionMethod.MAGISK,
        device.serial,
        "magisk_patched-27000_abcd.img",
    )
    assert output_plan.discovery_digest == discovery.receipt_digest
    forged_output = replace(
        output_plan,
        remote_path="/sdcard/Download/KernelSU_patched-android16.img",
        local_path=str(Path(output_plan.local_path).with_name("KernelSU_patched-android16.img")),
    )
    with pytest.raises(ProjectError, match="selected Magisk route"):
        outputs.retrieve_and_import(forged_output)
    with pytest.raises(ProjectError, match="discovery evidence changed"):
        outputs.retrieve_and_import(replace(output_plan, discovery_digest="0" * 64))
    approvals.issue(output_plan.approval_digest, output_plan.device_key)
    output_progress: list[int] = []
    patched = outputs.retrieve_and_import(output_plan, output_progress.append)

    assert output_progress[0] == 0
    assert output_progress[-1] == 100
    assert output_progress == sorted(set(output_progress))
    assert patched.source_image_sha256 == plan.input_image_sha256
    assert patched.flash_authority == "none"
    assert not Path(output_plan.local_path).exists()
    assert all("fastboot" not in part for call in runner.calls for part in call)

    runner.scan_stdout = "notes.txt\nordinary-boot.img\n"
    assert outputs.find(project_id, AscensionMethod.MAGISK, device.serial) == ()
    empty_discovery = outputs.load_discovery(
        project_id,
        AscensionMethod.MAGISK,
        device.serial,
    )
    assert empty_discovery is not None
    assert empty_discovery.state == "none"
    assert empty_discovery.candidate_count == 0
    assert empty_discovery.candidate_refs == ()
    assert empty_discovery.recommended_name_ref == ""
    with pytest.raises(ProjectError, match="not present in the latest approved phone scan"):
        outputs.plan(
            project_id,
            AscensionMethod.MAGISK,
            device.serial,
            "magisk_patched-27000_abcd.img",
        )

    tampered = json.loads(discovery_path.read_text(encoding="utf-8"))
    tampered["candidate_count"] = 1
    discovery_path.write_text(json.dumps(tampered), encoding="utf-8")
    assert outputs.load_discovery(project_id, AscensionMethod.MAGISK, device.serial) is None

    runner.scan_stdout = "x" * (outputs.MAX_SCAN_OUTPUT_BYTES + 1)
    with pytest.raises(ProjectError, match="bounded Ascension scan limit"):
        outputs.find(project_id, AscensionMethod.MAGISK, device.serial)
