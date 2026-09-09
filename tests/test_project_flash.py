from __future__ import annotations

import json
import os
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.local_flash import LocalFlashSelection, LocalFlashService
from romverse.guardian.local_transition import LocalDeviceTransitionService, LocalTransitionTarget
from romverse.infrastructure.process import CommandResult
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.build_contracts import DeviceBuildContractService
from romverse.rom.build_execution import LocalDeviceBuildExecutor
from romverse.rom.inspection import RomInspectionService
from romverse.rom.local_boot import LocalBootService
from romverse.rom.models import ProjectError
from romverse.rom.payloads import PayloadService
from romverse.rom.project_flash import (
    BoundProjectFlashService,
    BoundProjectTransitionService,
    ProjectFlashPreparationService,
)
from romverse.rom.projects import RomProjectStore
from romverse.rom.source_intelligence import FirmwareSourceIntelligenceService
from tests.test_build_contracts import _BuildRunner, _executable_tools, _fixture
from tests.test_guardian_local_flash import FakeFastboot
from tests.test_guardian_local_transition import Clock as TransitionClock
from tests.test_guardian_local_transition import TransitionRunner
from tests.test_local_boot import AndroidTransport
from tests.test_local_boot import Clock as BootClock


class PayloadRunner:
    def run(self, args, timeout=10, cwd=None):
        del timeout, cwd
        command = tuple(str(value) for value in args)
        if "-l" in command:
            return CommandResult(command, 0, "boot:32\n", "")
        assert "-m" in command and "-o" in command
        output = Path(command[command.index("-o") + 1])
        (output / "boot.img").write_bytes(b"ANDROID!" + b"\0" * 24)
        return CommandResult(command, 0, "", "")


@pytest.fixture
def protected(tmp_path):
    source = tmp_path / "popsicle_images_OS4.0.0.25.XPBCNXM_20260804.0000.00_17.0_cn_test.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("images/boot.img", b"ANDROID!" + b"\0" * 24)
        archive.writestr("images/vbmeta.img", b"AVB0" + b"\0" * 28)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Protected subset").project_id, source)
    RomInspectionService(store).extract_project_tree(project.project_id)
    FirmwareSourceIntelligenceService(store, (), PayloadRunner()).prepare(project.project_id)
    return store, project, ProjectFlashPreparationService(store, DevicePackRegistry(()))


@pytest.fixture
def built(tmp_path):
    store, project, registry, _tools, _metadata, partitions = _fixture(tmp_path)
    tools = _executable_tools(tmp_path / "tools")
    DeviceBuildContractService(store, registry, tools).create_plan(project.project_id)
    receipt = LocalDeviceBuildExecutor(
        store, registry, tools, _BuildRunner(partitions / "system.img")
    ).execute(project.project_id)
    return store, project, ProjectFlashPreparationService(store, registry), receipt


def _local(protected, tmp_path):
    store, project, preparer = protected
    preparation = preparer.prepare(project.project_id, candidate_choice="protected")
    runner = FakeFastboot()
    tool = tmp_path / "fastboot"
    tool.write_bytes(b"inert fixture tool")
    tool.chmod(0o700)
    device = AndroidDevice(
        runner.serial,
        DeviceState.BOOTLOADER,
        manufacturer="Xiaomi",
        product=runner.product,
        codename=runner.product,
    )
    bound = BoundProjectFlashService(
        preparer, preparation, LocalFlashService(store.workspace, runner, tool)
    )
    selection = (LocalFlashSelection("boot_a", preparation.images[0].path),)
    return bound, runner, device, selection


def test_built_candidate_uses_current_build_receipt_outputs_without_source_fallback(built):
    store, project, preparer, receipt = built
    preparation = preparer.prepare(project.project_id, candidate_choice="built")
    assert preparation.candidate_choice == "built"
    assert {item.path for item in preparation.images} == {
        store.workspace / item.path for item in receipt.outputs
    }
    assert {item.sha256 for item in preparation.images} == {item.sha256 for item in receipt.outputs}
    assert preparation.expected_products == ("product",)
    assert all("build-candidates" in item.path.parts for item in preparation.images)
    assert not any(hasattr(item, "partition") for item in preparation.images)


def test_built_image_tamper_with_restored_mtime_fails_fresh_hash_check(built):
    store, project, preparer, receipt = built
    path = store.workspace / receipt.outputs[0].path
    before = path.stat()
    path.write_bytes(b"x" * before.st_size)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    preparation = None
    with pytest.raises(ProjectError) as captured:
        preparation = preparer.prepare(project.project_id, candidate_choice="built")
    assert preparation is None
    failure = str(captured.value).casefold()
    invalid_current_receipt = all(
        phrase in failure
        for phrase in (
            "no current verified local build outputs exist",
            "complete the build",
            "explicitly choose protected-source images",
        )
    )
    changed_receipt_bytes = all(
        phrase in failure
        for phrase in (
            "selected source/build receipt",
            "prepare fresh verified evidence",
        )
    )
    assert invalid_current_receipt or changed_receipt_bytes


def test_changed_build_tree_cannot_select_old_successful_build(built):
    store, project, preparer, _receipt = built
    (store.working_root / project.project_id / "tree" / "new-edit.txt").write_text("new edit")
    with pytest.raises(ProjectError, match="tree or recipe changed"):
        preparer.prepare(project.project_id, candidate_choice="built")


def test_explicit_built_selection_never_silently_uses_existing_protected_images(protected):
    _store, project, preparer = protected
    assert preparer.prepare(project.project_id, candidate_choice="protected").images
    with pytest.raises(ProjectError, match="No protected-source fallback"):
        preparer.prepare(project.project_id, candidate_choice="built")


def test_ota_protected_images_require_current_saved_extraction_manifest(tmp_path):
    source = tmp_path / "popsicle-ota_full-OS4.0.0.25.XPBCNXM-user-17.0-test.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"CrAU payload fixture")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("OTA subset").project_id, source)
    RomInspectionService(store).extract_project_tree(project.project_id)
    dumper = tmp_path / "payload-dumper-go"
    dumper.write_bytes(b"inert tool")
    runner = PayloadRunner()
    source_service = FirmwareSourceIntelligenceService(
        store, (ToolStatus("Payload Dumper", True, str(dumper)),), runner
    )
    source_service.prepare(project.project_id)
    preparer = ProjectFlashPreparationService(store, DevicePackRegistry(()))
    with pytest.raises(ProjectError, match="no extracted .img"):
        preparer.prepare(project.project_id, candidate_choice="protected")
    PayloadService(store, dumper, runner).extract(project.project_id, ("boot",))
    preparation = preparer.prepare(project.project_id, candidate_choice="protected")
    assert [image.name for image in preparation.images] == ["boot.img"]
    assert preparation.images[0].path.parent.name == "partitions"
    manifest = store.projects_root / project.project_id / PayloadService.MANIFEST_NAME
    manifest.rename(manifest.with_suffix(".retained-test"))
    with pytest.raises(ProjectError, match="manifest"):
        preparer.prepare(project.project_id, candidate_choice="protected")


def test_bound_receipt_and_latest_historical_outcome_do_not_claim_complete_firmware(
    protected, tmp_path
):
    bound, runner, device, selections = _local(protected, tmp_path)
    plan = bound.inspect(device, selections)
    result = bound.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True)
    record = json.loads(bound.project_receipt_path.read_text())
    assert record["reviewed_plan_digest"] == plan.plan_digest
    assert record["local_plan_digest"] != plan.plan_digest
    assert record["selected_image_count"] == 1
    assert not record["production_certified"] and not record["full_firmware_install"]
    assert not record["boot_verified"] and not record["readback_verified"]
    assert (
        record["child_receipt_path"] == result.receipt_path.relative_to(bound.workspace).as_posix()
    )
    assert device.serial not in bound.project_receipt_path.read_text()
    assert len(runner.writes) == 1
    outcome = bound.preparer.load_latest(bound.preparation.project_id)
    assert outcome.state == "completed" and outcome.selected_image_count == 1
    assert outcome.historical and not outcome.current_artifact_bytes_verified
    assert outcome.boot_status == "No linked boot-check record"
    child = result.receipt_path.read_text()
    result.receipt_path.write_text(child.replace('"boot_verified": false', '"boot_verified": true'))
    assert bound.preparer.load_latest(bound.preparation.project_id) is None


def test_parent_journal_failure_before_delegation_never_writes(protected, tmp_path, monkeypatch):
    bound, runner, device, selections = _local(protected, tmp_path)
    plan = bound.inspect(device, selections)

    def fail(*_args, **_kwargs):
        raise OSError("fixture journal unavailable")

    monkeypatch.setattr("romverse.rom.project_flash.exclusive_create_json", fail)
    with pytest.raises(OSError, match="journal unavailable"):
        bound.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True)
    assert not runner.writes


def test_parent_journal_failure_after_write_is_not_swallowed(protected, tmp_path, monkeypatch):
    bound, runner, device, selections = _local(protected, tmp_path)
    plan = bound.inspect(device, selections)

    def fail(*_args, **_kwargs):
        raise OSError("fixture result linkage unavailable")

    monkeypatch.setattr("romverse.rom.project_flash.atomic_write_json", fail)
    with pytest.raises(OSError, match="linkage unavailable"):
        bound.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True)
    assert len(runner.writes) == 1
    assert json.loads(bound.project_receipt_path.read_text())["state"] == "delegation-pending"
    assert bound.preparer.load_latest(bound.preparation.project_id) is None


def test_known_manufacturer_contradiction_blocks_but_known_xiaomi_brand_alias_is_allowed(protected):
    _store, project, preparer = protected
    preparation = preparer.prepare(project.project_id, candidate_choice="protected")
    device = AndroidDevice(
        "fixture-serial",
        DeviceState.DEVICE,
        manufacturer="Google",
        product="popsicle",
        codename="popsicle",
    )
    with pytest.raises(ProjectError, match="manufacturer"):
        preparer.verify(preparation, device)
    preparer.verify(preparation, replace(device, manufacturer="Redmi"))


@pytest.mark.parametrize("cancel", [False, True])
def test_bound_transition_has_real_child_and_parent_journals_without_flash_claim(
    protected, tmp_path, cancel
):
    bound, _runner, device, _selections = _local(protected, tmp_path)
    runner = TransitionRunner()
    clock = TransitionClock()
    bound.local_service.runner = runner
    device = replace(device, serial=runner.serial)
    adb = tmp_path / "adb"
    adb.write_bytes(b"inert tool")
    adb.chmod(0o700)
    transition = BoundProjectTransitionService(
        bound.preparer,
        bound.preparation,
        LocalDeviceTransitionService(
            bound.local_service,
            adb,
            clock=clock.now,
            monotonic=clock.monotonic,
            sleeper=clock.sleep,
            arrival_timeout_seconds=2,
        ),
    )
    plan = transition.inspect(device, LocalTransitionTarget.FASTBOOTD)
    result = transition.execute(
        plan, accepted_digest=plan.plan_digest, risk_accepted=True, should_cancel=lambda: cancel
    )
    assert result.state == ("cancelled" if cancel else "completed")
    assert result.phone_change_attempted is not cancel
    assert len(runner.reboots) == (0 if cancel else 1)
    assert not result.boot_verified
    parent = json.loads(transition.project_receipt_path.read_text())
    assert parent["operation_kind"] == "manual-mode-transition"
    assert parent["selected_image_count"] == 0
    assert (
        parent["child_receipt_path"] == result.receipt_path.relative_to(bound.workspace).as_posix()
    )
    assert parent["state"] == result.state
    assert bound.preparer.load_latest(bound.preparation.project_id) is None


def test_later_interrupted_subset_suppresses_previous_success(protected, tmp_path):
    bound, _runner, device, selections = _local(protected, tmp_path)
    plan = bound.inspect(device, selections)
    bound.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True)
    assert bound.preparer.load_latest(bound.preparation.project_id).state == "completed"
    older = bound.project_receipt_path
    interrupted = json.loads(older.read_text())
    interrupted.pop("record_digest")
    interrupted["state"] = "delegation-interrupted"
    new = older.with_name("later-interrupted.json")
    bound._save(new, interrupted)
    assert bound.preparer.load_latest(bound.preparation.project_id) is None


def test_bound_service_rejects_a_different_workspace_before_any_phone_operation(
    protected, tmp_path
):
    bound, runner, _device, _selections = _local(protected, tmp_path)
    other = tmp_path / "different-workspace"
    other.mkdir()
    local = LocalFlashService(other, runner, bound.fastboot_path)
    with pytest.raises(ProjectError, match="different project workspace"):
        BoundProjectFlashService(bound.preparer, bound.preparation, local)
    assert not runner.calls


def test_linked_historical_boot_result_is_displayed_without_new_boot_authority(protected, tmp_path):
    bound, _runner, device, selections = _local(protected, tmp_path)
    clock = BootClock()
    runner = AndroidTransport(clock)
    bound.local_service.runner = runner
    plan = bound.inspect(device, selections)
    result = bound.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True)
    adb = tmp_path / "adb"
    adb.write_bytes(b"inert tool")
    adb.chmod(0o700)
    monitor = LocalBootService(
        bound.local_service, adb, monotonic_clock=clock.tick, utc_clock=clock.utc
    )
    session = monitor.begin(device, result)
    for _ in range(13):
        report = monitor.observe(session)
        clock.advance()
    assert report.status == "stable"
    outcome = bound.preparer.load_latest(bound.preparation.project_id)
    assert outcome.boot_status.startswith("Historical Android boot observed")
    assert outcome.boot_receipt_path == report.receipt_path
    assert outcome.historical and not outcome.current_artifact_bytes_verified
    later = monitor.begin(device, result)
    stopped = monitor.stop(later)
    outcome = bound.preparer.load_latest(bound.preparation.project_id)
    assert outcome.boot_status == "Historical boot check: stopped"
    assert outcome.boot_receipt_path == stopped.receipt_path
    stopped.receipt_path.write_text(
        stopped.receipt_path.read_text().replace('"cancelled"', '"stable"')
    )
    assert (
        bound.preparer.load_latest(bound.preparation.project_id).boot_status
        == "See separate boot-check record"
    )
