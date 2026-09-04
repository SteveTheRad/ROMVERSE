from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.models import (
    AvbExecutionPolicy,
    AvbPolicyAuthority,
    AvbPolicyMode,
    DeviceBuildContract,
    DeviceMode,
    DeviceModeTransitionRule,
    DevicePack,
    DevicePostWriteVerificationContract,
    DeviceRecoveryActionRule,
    DeviceRecoveryContract,
    DeviceRecoveryOperation,
    DeviceRecoveryStrategy,
    DeviceTransitionOperation,
    DeviceTransitionRecoveryContract,
    DeviceWriteContract,
    DeviceWriteTransport,
    DynamicPartitionGroup,
    FirmwareSourceContract,
    PartitionBuildRule,
    PartitionReadbackRule,
    PartitionVerificationMethod,
    PartitionWriteRule,
    PostBootPropertyRule,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.rom.build_execution import BuildOutputReceipt
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.recovery_evidence import RecoveryEvidenceAssessment
from romverse.rom.simulation import (
    RomSimulationService,
    SimulationPlanEdit,
    SimulationSeverity,
)


def _project_and_pack(tmp_path):
    workspace = tmp_path / "workspace"
    store = RomProjectStore(workspace)
    source = tmp_path / "firmware.zip"
    source.write_bytes(b"exact firmware")
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    project = store.create("Digital Twin", "test.device")
    project = store.import_original(project.project_id, source)
    attestation = "a" * 64
    verification = DevicePostWriteVerificationContract(
        "verify-super",
        1,
        "TEST.2",
        attestation,
        (
            PartitionReadbackRule(
                "super",
                DeviceWriteTransport.FASTBOOTD,
                "none",
                PartitionVerificationMethod.FASTBOOT_FETCH_SHA256,
                4096,
                "b" * 64,
            ),
        ),
        (PostBootPropertyRule("sys.boot_completed", "1"),),
        True,
        300,
    )
    recovery = DeviceRecoveryContract(
        DeviceRecoveryStrategy.RECORDED_SLOT_THEN_STOCK_PACKAGE,
        "test-recovery-adapter",
        source_sha,
        DeviceMode.BOOTLOADER,
        (
            DeviceRecoveryActionRule(
                1,
                DeviceRecoveryOperation.ACTIVATE_RECORDED_SLOT,
                "activate-recorded-slot",
                DeviceMode.BOOTLOADER,
                DeviceMode.BOOTLOADER,
                "recorded",
                30,
                False,
            ),
        ),
        True,
        True,
        True,
        False,
        False,
        False,
    )
    transition = DeviceTransitionRecoveryContract(
        "transition-recovery",
        1,
        "TEST.2",
        attestation,
        DeviceMode.BOOTLOADER,
        (
            DeviceModeTransitionRule(
                1,
                0,
                DeviceTransitionOperation.REBOOT_FASTBOOTD,
                DeviceMode.BOOTLOADER,
                DeviceMode.FASTBOOTD,
                "none",
                60,
            ),
        ),
        DeviceMode.ANDROID,
        recovery,
        True,
        "none",
        False,
    )
    writes = DeviceWriteContract(
        "write-super",
        1,
        "TEST.2",
        attestation,
        True,
        False,
        True,
        False,
        (
            PartitionWriteRule(
                "super",
                "super.img",
                DeviceWriteTransport.FASTBOOTD,
                "none",
                True,
            ),
        ),
        False,
        verification,
        transition,
    )
    contract = DeviceBuildContract(
        "build-test",
        1,
        FirmwareSourceContract("TEST.2", source_sha, "c" * 64),
        8192,
        65536,
        3,
        True,
        (DynamicPartitionGroup("dynamic_a", 4096),),
        (
            PartitionBuildRule(
                "system",
                2048,
                4096,
                "dynamic_a",
                "erofs",
                "passthrough",
                "d" * 64,
            ),
        ),
        ("system",),
        "e" * 64,
        "f" * 64,
        ("super.img",),
        avb_execution_policy=AvbExecutionPolicy(
            AvbPolicyMode.SIGNED_CUSTOM_RECHAIN,
            AvbPolicyAuthority.FLASH_VALIDATED,
            "TEST.2",
            "preserve_exact_source",
            "vbmeta_system",
            "SHA256_RSA2048",
            1,
            0,
            0,
            True,
            False,
            True,
            "b",
            "a",
            attestation,
        ),
        partition_write_contract=writes,
    )
    pack = DevicePack(
        "test.device",
        "1.0.0",
        "Test Device",
        100,
        ("test",),
        ("model",),
        ("product",),
        (),
        (),
        "1" * 64,
        contract,
    )
    return store, project, DevicePackRegistry((pack,))


def _patch_complete_evidence(monkeypatch):
    facts = {
        "identity.marketing_name": "Test Phone",
        "identity.codename": "product",
        "firmware.ota_post_device": "product",
        "software.rom": "TEST.1",
        "software.build": "TEST.2",
        "firmware.upgrade_relationship": "UPGRADE CANDIDATE • TEST.1 → TEST.2",
        "bootloader.state": "unlocked",
        "boot.active_slot": "a",
    }
    dna = SimpleNamespace(
        profile_digest="2" * 64,
        fact=lambda fact_id: SimpleNamespace(value=facts[fact_id]) if fact_id in facts else None,
    )
    monkeypatch.setattr(
        "romverse.rom.simulation.DeviceDnaStore.load",
        lambda _self, _project_id: dna,
    )
    output = BuildOutputReceipt(
        "super.img",
        "working_roms/project/build-candidates/plan/super.img",
        4096,
        1,
        "3" * 64,
    )
    monkeypatch.setattr(
        "romverse.rom.simulation.LocalDeviceBuildExecutor.load_receipt",
        lambda _self, _project_id: SimpleNamespace(outputs=(output,)),
    )
    monkeypatch.setattr(
        "romverse.rom.simulation.DeviceBuildContractService.load",
        lambda _self, _project_id: SimpleNamespace(steps=()),
    )
    monkeypatch.setattr(
        "romverse.rom.simulation.RecoveryEvidenceService.assess",
        lambda _self, _project_id, _device: RecoveryEvidenceAssessment(
            True,
            True,
            True,
            ("backup ready", "stock ready"),
        ),
    )


def test_digital_twin_rehearses_exact_plan_and_creates_inert_mission(tmp_path, monkeypatch):
    store, project, registry = _project_and_pack(tmp_path)
    _patch_complete_evidence(monkeypatch)
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Test",
        model="Model",
        product="product",
        codename="product",
        rom_display="TEST.1",
        battery_percent=91,
        bootloader_locked=False,
        slot_suffix="_a",
    )
    service = RomSimulationService(store, registry)

    receipt = service.rehearse(project.project_id, device)

    assert receipt.successful
    assert receipt.mission_ready
    assert not receipt.phone_changed
    assert receipt.execution_authority == "none"
    assert receipt.confidence_percent <= 92
    assert any(item.name == "super" for item in receipt.partitions)
    assert any(item.phase == "write" for item in receipt.operations)
    assert all(not item.phone_changed for item in receipt.operations)
    assert service.load(project.project_id) == receipt

    mission = service.create_mission(receipt)
    assert mission.status == "prepared-for-rom-studio-review"
    assert not mission.phone_changed
    assert mission.execution_authority == "none"


def test_digital_twin_blocks_missing_dna_write_contract_and_rollback(tmp_path):
    store, project, registry = _project_and_pack(tmp_path)
    pack = registry.packs[0]
    assert pack.build_contract is not None
    registry = DevicePackRegistry(
        (
            replace(
                pack,
                build_contract=replace(
                    pack.build_contract,
                    partition_write_contract=None,
                    avb_execution_policy=None,
                ),
            ),
        )
    )
    receipt = RomSimulationService(store, registry).rehearse(project.project_id)

    blocked = {
        item.finding_id for item in receipt.findings if item.severity is SimulationSeverity.BLOCKED
    }
    assert {"device-dna", "write-contract", "avb", "rollback"} <= blocked
    assert not receipt.successful
    assert not receipt.mission_ready


def test_expert_revision_is_reviewable_but_cannot_inherit_flash_authority(tmp_path, monkeypatch):
    store, project, registry = _project_and_pack(tmp_path)
    _patch_complete_evidence(monkeypatch)
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        product="product",
        codename="product",
        battery_percent=90,
        bootloader_locked=False,
    )
    service = RomSimulationService(store, registry)
    receipt = service.rehearse(project.project_id, device)
    target = next(item for item in receipt.operations if item.phase == "write")

    revised = service.revise(
        receipt,
        (
            SimulationPlanEdit(
                target.operation_id,
                "exclude",
                target.order,
                "Inspect a hypothetical preserve-only route",
            ),
        ),
    )

    assert revised.expert_edits
    assert revised.parent_simulation_digest == receipt.receipt_digest
    assert not revised.successful
    assert not revised.mission_ready
    assert revised.execution_authority == "none"
    with pytest.raises(ProjectError):
        service.create_mission(revised)


def test_tampered_digital_twin_receipt_is_rejected(tmp_path, monkeypatch):
    store, project, registry = _project_and_pack(tmp_path)
    _patch_complete_evidence(monkeypatch)
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        product="product",
        codename="product",
        battery_percent=90,
        bootloader_locked=False,
    )
    service = RomSimulationService(store, registry)
    service.rehearse(project.project_id, device)
    path = store.projects_root / project.project_id / service.RECEIPT_NAME
    data = json.loads(path.read_text(encoding="utf-8"))
    data["mission_ready"] = False
    path.write_text(json.dumps(data), encoding="utf-8")

    assert service.load(project.project_id) is None
