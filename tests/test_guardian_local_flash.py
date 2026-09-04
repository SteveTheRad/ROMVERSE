from __future__ import annotations

import json
import os
import struct
from dataclasses import replace

import pytest

from romverse.device.models import AndroidDevice, DeviceState
from romverse.guardian.local_flash import (
    LocalFlashError,
    LocalFlashSelection,
    LocalFlashService,
    LocalFlashState,
)
from romverse.infrastructure.process import CommandResult


class FakeFastboot:
    def __init__(self):
        self.serial = "private-phone-1234"
        self.second_serial = ""
        self.product = "popsicle"
        self.mode = "no"
        self.unlocked = "yes"
        self.slot = "a"
        self.partition_size = "0x1000"
        self.logical = "no"
        self.has_slot = "yes"
        self.unsupported: set[str] = set()
        self.calls: list[tuple[str, ...]] = []
        self.fail_partition = ""
        self.timeout_partition = ""
        self.on_write = None

    @property
    def writes(self):
        return [command for command in self.calls if "flash" in command]

    def run(self, args, timeout=10, cwd=None):
        del timeout, cwd
        command = tuple(str(item) for item in args)
        self.calls.append(command)
        if command[1:] == ("devices", "-l"):
            extra = f"{self.second_serial} fastboot usb:2-2\n" if self.second_serial else ""
            return CommandResult(command, 0, f"{self.serial} fastboot usb:1-1\n{extra}", "")
        if command[1:3] != ("-s", self.serial):
            return CommandResult(command, 1, "", "Wrong target")
        if command[3] == "getvar":
            variable = command[4]
            if variable in self.unsupported:
                return CommandResult(command, 1, "", "FAILED (remote: 'GetVar Variable Not found')")
            value = {
                "product": self.product,
                "is-userspace": self.mode,
                "unlocked": self.unlocked,
                "current-slot": self.slot,
            }.get(variable)
            if variable.startswith("partition-size:"):
                value = self.partition_size
            elif variable.startswith("is-logical:"):
                value = self.logical
            elif variable.startswith("has-slot:"):
                value = self.has_slot
            return CommandResult(
                command,
                0,
                "",
                f"(bootloader) {variable}: {value or ''}\nFinished. Total time: 0.1s\n",
            )
        if command[3] == "flash":
            if self.on_write:
                self.on_write(command)
            partition = command[4]
            output = f"Writing {partition} to serial={self.serial} from {command[5]}\n"
            return CommandResult(
                command,
                124
                if partition == self.timeout_partition
                else 1
                if partition == self.fail_partition
                else 0,
                "",
                output,
                timed_out=partition == self.timeout_partition,
            )
        raise AssertionError(f"Unexpected command: {command}")


@pytest.fixture
def local_flash(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = tmp_path / "fastboot"
    tool.write_bytes(b"fixture tool")
    tool.chmod(0o700)
    image = tmp_path / "boot.img"
    image.write_bytes(b"genuine fixture image bytes")
    runner = FakeFastboot()
    device = AndroidDevice(
        serial=runner.serial,
        state=DeviceState.BOOTLOADER,
        manufacturer="Xiaomi",
        model="Test phone",
        product="popsicle",
        codename="popsicle",
        ab_update=True,
    )
    service = LocalFlashService(workspace, runner, tool)
    return service, runner, device, image


def _inspect(context, *, partitions=("boot_a",)):
    service, _runner, device, image = context
    return service.inspect(
        device, tuple(LocalFlashSelection(partition, image) for partition in partitions)
    )


def _execute(service, plan, **kwargs):
    return service.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True, **kwargs)


def test_local_flash_inspection_is_read_only_and_execution_records_transport_only(local_flash):
    service, runner, device, image = local_flash
    plan = _inspect(local_flash, partitions=("boot_a", "boot_b"))
    assert runner.writes == []
    assert plan.product == "popsicle"
    assert plan.mode == "bootloader"
    assert plan.writes[0].partition_size_bytes == 4096
    progress = []
    result = _execute(service, plan, progress=lambda *entry: progress.append(entry))
    assert result.state is LocalFlashState.COMPLETED
    assert result.completed_count == 2
    assert result.phone_change_attempted and result.phone_state_uncertain
    assert result.boot_verified is False
    assert [command[3:5] for command in runner.writes] == [("flash", "boot_a"), ("flash", "boot_b")]
    assert all(command[1:3] == ("-s", device.serial) for command in runner.writes)
    assert progress[-1][0:2] == (2, 2)
    stored = result.receipt_path.read_text()
    assert device.serial not in stored
    assert str(image) not in stored
    assert str(image.parent) not in stored
    document = json.loads(stored)
    assert document["boot_verified"] is False
    assert document["readback_verified"] is False
    assert document["external_certification"] is False
    assert document["record_digest"]
    assert service.audit.verify().valid
    audit = service.audit.path.read_text()
    assert device.serial not in audit and str(image) not in audit
    if os.name != "nt":
        assert result.receipt_path.stat().st_mode & 0o777 == 0o600


def test_exact_confirmation_and_original_live_service_required(local_flash):
    service, runner, _device, _image = local_flash
    plan = _inspect(local_flash)
    with pytest.raises(LocalFlashError, match="Confirm"):
        service.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=False)
    with pytest.raises(LocalFlashError, match="Confirm"):
        service.execute(plan, accepted_digest="wrong", risk_accepted=True)
    tampered = replace(plan, writes=(replace(plan.writes[0], partition="boot_b"),))
    with pytest.raises(LocalFlashError, match="preview changed"):
        _execute(service, tampered)
    other = LocalFlashService(service.workspace, runner, service.fastboot_path)
    with pytest.raises(LocalFlashError, match="preview changed"):
        _execute(other, plan)
    assert runner.writes == []


@pytest.mark.parametrize("change", ["serial", "product", "mode", "unlocked", "slot", "partition"])
def test_changed_target_or_partition_never_writes(local_flash, change):
    service, runner, _device, _image = local_flash
    plan = _inspect(local_flash)
    if change == "partition":
        runner.partition_size = "0x2000"
    else:
        setattr(
            runner,
            change,
            {
                "serial": "other-phone",
                "product": "different",
                "mode": "yes",
                "unlocked": "no",
                "slot": "b",
            }[change],
        )
    result = _execute(service, plan)
    assert result.state is LocalFlashState.REJECTED
    assert not result.phone_change_attempted
    assert runner.writes == []


@pytest.mark.parametrize("changed", ["image", "tool", "symlink"])
def test_changed_file_is_rejected_before_write(local_flash, changed):
    service, runner, _device, image = local_flash
    plan = _inspect(local_flash)
    if changed == "tool":
        service.fastboot_path.write_bytes(b"modified tool")
    elif changed == "image":
        image.write_bytes(b"changed image")
    else:
        renamed = image.with_name("moved.img")
        image.rename(renamed)
        image.symlink_to(renamed)
    result = _execute(service, plan)
    assert result.state is LocalFlashState.REJECTED
    assert not result.phone_change_attempted
    assert runner.writes == []


def test_confirmation_single_use_but_new_review_allows_explicit_retry(local_flash):
    service, runner, _device, _image = local_flash
    plan = _inspect(local_flash)
    runner.fail_partition = "boot_a"
    assert _execute(service, plan).state is LocalFlashState.FAILED
    with pytest.raises(LocalFlashError, match="already used"):
        _execute(service, plan)
    refreshed = _inspect(local_flash)
    assert refreshed.plan_digest != plan.plan_digest
    assert refreshed.plan_id != plan.plan_id
    runner.fail_partition = ""
    assert _execute(service, refreshed).state is LocalFlashState.COMPLETED
    assert len(runner.writes) == 2


@pytest.mark.parametrize("timed_out", [False, True])
def test_failed_write_stops_remaining_plan_and_retains_uncertainty(local_flash, timed_out):
    service, runner, _device, _image = local_flash
    plan = _inspect(local_flash, partitions=("boot_a", "boot_b"))
    if timed_out:
        runner.timeout_partition = "boot_a"
    else:
        runner.fail_partition = "boot_a"
    result = _execute(service, plan)
    assert result.state is LocalFlashState.FAILED
    assert result.phone_state_uncertain and result.phone_change_attempted
    assert len(runner.writes) == 1
    assert result.results[0].timed_out is timed_out
    assert not result.boot_verified


def test_cancel_is_observed_only_between_writes(local_flash):
    service, runner, _device, _image = local_flash
    plan = _inspect(local_flash, partitions=("boot_a", "boot_b"))
    result = _execute(service, plan, should_cancel=lambda: bool(runner.writes))
    assert result.state is LocalFlashState.CANCELLED
    assert result.completed_count == 1
    assert result.phone_state_uncertain
    assert len(runner.writes) == 1
    fresh = _inspect(local_flash)
    result = _execute(service, fresh, should_cancel=lambda: True)
    assert result.state is LocalFlashState.CANCELLED
    assert not result.phone_change_attempted


@pytest.mark.parametrize(
    "problem", ["mismatch", "locked", "adb", "identity", "implicit-slot", "oversize", "logical"]
)
def test_inspection_identifies_actionable_real_conflicts(local_flash, problem):
    service, runner, device, image = local_flash
    partition = "boot_a"
    if problem == "mismatch":
        runner.product = "another-phone"
    elif problem == "locked":
        runner.unlocked = "no"
    elif problem == "adb":
        device = replace(device, state=DeviceState.DEVICE)
    elif problem == "identity":
        device = replace(device, product="", codename="")
    elif problem == "implicit-slot":
        partition = "boot"
    elif problem == "oversize":
        runner.partition_size = "0x1"
    elif problem == "logical":
        runner.logical = "yes"
    with pytest.raises(LocalFlashError):
        service.inspect(device, (LocalFlashSelection(partition, image),))
    assert runner.writes == []


def test_unsupported_optional_partition_evidence_is_visible_warning(local_flash):
    service, runner, _device, _image = local_flash
    runner.unsupported = {"partition-size:boot_a", "is-logical:boot_a", "has-slot:boot", "unlocked"}
    plan = _inspect(local_flash)
    assert plan.writes[0].partition_size_bytes is None
    assert plan.writes[0].has_slot is None
    assert plan.unlocked is None
    assert any("partition-size:boot_a" in warning for warning in plan.warnings)
    assert any("unlocked" in warning for warning in plan.warnings)
    assert _execute(service, plan).state is LocalFlashState.COMPLETED


def test_explicit_unslotted_and_fastbootd_logical_partition_supported(local_flash):
    service, runner, _device, _image = local_flash
    runner.has_slot = "no"
    runner.mode = "yes"
    runner.logical = "yes"
    plan = _inspect(local_flash, partitions=("vendor",))
    assert plan.mode == "fastbootd"
    assert _execute(service, plan).state is LocalFlashState.COMPLETED
    assert runner.writes[0][3:5] == ("flash", "vendor")


def test_sparse_expanded_size_used_and_malformed_chunks_rejected(local_flash):
    _service, runner, _device, image = local_flash
    sparse_header = struct.pack("<I4H4I", 0xED26FF3A, 1, 0, 28, 12, 4096, 4, 1, 0)
    skip_chunk = struct.pack("<2H2I", 0xCAC3, 0, 4, 12)
    image.write_bytes(sparse_header + skip_chunk)
    with pytest.raises(LocalFlashError, match="too large"):
        _inspect(local_flash)
    runner.partition_size = "0x4000"
    plan = _inspect(local_flash)
    assert plan.writes[0].size_bytes == 40
    assert plan.writes[0].expanded_size_bytes == 16384
    image.write_bytes(sparse_header + struct.pack("<2H2I", 0xCAC1, 0, 4, 12))
    with pytest.raises(LocalFlashError, match="chunk geometry"):
        _inspect(local_flash)


def test_in_flight_journal_precedes_command_and_concurrent_operation_is_refused(local_flash):
    service, runner, device, image = local_flash
    plan = _inspect(local_flash)
    second = LocalFlashService(service.workspace, runner, service.fastboot_path)

    def on_write(_command):
        journal = json.loads((service.root / f"{plan.plan_id}.json").read_text())
        assert journal["state"] == "writing"
        assert journal["in_flight_partition"] == "boot_a"
        assert journal["phone_state_uncertain"]
        with pytest.raises(LocalFlashError, match="Another local image operation"):
            second.inspect(device, (LocalFlashSelection("boot_b", image),))

    runner.on_write = on_write
    result = _execute(service, plan)
    assert result.state is LocalFlashState.COMPLETED


def test_process_interruption_leaves_uncertain_in_flight_journal(local_flash):
    service, runner, _device, _image = local_flash
    plan = _inspect(local_flash)

    def crash(_command):
        raise KeyboardInterrupt

    runner.on_write = crash
    with pytest.raises(KeyboardInterrupt):
        _execute(service, plan)
    journal = json.loads((service.root / f"{plan.plan_id}.json").read_text())
    assert journal["state"] == "writing"
    assert journal["in_flight_partition"] == "boot_a"
    assert journal["phone_state_uncertain"]
    assert not journal["boot_verified"]


def test_external_image_replacement_cannot_change_reviewed_execution_bytes(local_flash):
    service, runner, _device, image = local_flash
    approved_bytes = image.read_bytes()
    plan = _inspect(local_flash)
    flashed = []

    def progress(_done, _total, message):
        if message.startswith("Writing "):
            image.write_bytes(b"new image from concurrent build")

    def measure_snapshot(command):
        snapshot = (
            service.workspace
            / json.loads((service.root / f"{plan.plan_id}.json").read_text())["image_snapshots"][0][
                "relative_path"
            ]
        )
        assert command[-1] == str(snapshot)
        flashed.append(snapshot.read_bytes())
        if os.name != "nt":
            assert snapshot.stat().st_mode & 0o777 == 0o400

    runner.on_write = measure_snapshot
    result = _execute(service, plan, progress=progress)
    assert result.state is LocalFlashState.COMPLETED
    assert flashed == [approved_bytes]
    assert image.read_bytes() != approved_bytes
    record = json.loads(result.receipt_path.read_text())
    assert record["snapshots_verified"] is True
    assert (service.workspace / record["image_snapshots"][0]["relative_path"]).exists()


def test_cancellation_while_preparing_next_write_never_starts_that_write(local_flash):
    service, runner, _device, _image = local_flash
    plan = _inspect(local_flash)
    stopped = False

    def progress(_done, _total, message):
        nonlocal stopped
        if message.startswith("Writing "):
            stopped = True

    result = _execute(service, plan, should_cancel=lambda: stopped, progress=progress)
    assert result.state is LocalFlashState.CANCELLED
    assert not result.phone_change_attempted
    assert runner.writes == []


def test_changed_device_during_prewrite_preparation_is_rechecked(local_flash):
    service, runner, _device, _image = local_flash
    plan = _inspect(local_flash)

    def progress(_done, _total, message):
        if message.startswith("Writing "):
            runner.product = "different-device"

    result = _execute(service, plan, progress=progress)
    assert result.state is LocalFlashState.REJECTED
    assert runner.writes == []


def test_staged_file_tampering_after_command_is_reported_as_uncertain_failure(local_flash):
    service, runner, _device, _image = local_flash
    plan = _inspect(local_flash, partitions=("boot_a", "boot_b"))

    def tamper_snapshot(command):
        from pathlib import Path

        snapshot = Path(command[-1])
        snapshot.chmod(0o600)
        snapshot.write_bytes(b"unexpected changed snapshot")

    runner.on_write = tamper_snapshot
    result = _execute(service, plan)
    assert result.state is LocalFlashState.FAILED
    assert result.phone_state_uncertain
    assert len(runner.writes) == 1
    assert not result.boot_verified


def test_insufficient_snapshot_space_rejects_before_phone_write(local_flash, monkeypatch):
    from collections import namedtuple

    service, runner, _device, _image = local_flash
    plan = _inspect(local_flash)
    usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(
        "romverse.guardian.local_flash.shutil.disk_usage", lambda _path: usage(100, 99, 1)
    )
    result = _execute(service, plan)
    assert result.state is LocalFlashState.REJECTED
    assert "free bytes" in result.summary
    assert not result.phone_change_attempted
    assert runner.writes == []


def test_zero_partition_size_is_reported_as_image_too_large(local_flash):
    _service, runner, _device, _image = local_flash
    runner.partition_size = "0x0"
    with pytest.raises(LocalFlashError, match="too large"):
        _inspect(local_flash)
    assert runner.writes == []


def test_unrecognised_optional_values_stay_explicit_warnings(local_flash):
    _service, runner, _device, _image = local_flash
    runner.mode = runner.unlocked = runner.logical = runner.has_slot = "unrecognised"
    plan = _inspect(local_flash)
    assert plan.mode == "unknown"
    assert plan.unlocked is None
    assert plan.writes[0].is_logical is None
    assert plan.writes[0].has_slot is None
    assert sum("not recognised" in warning for warning in plan.warnings) >= 4


def test_another_phone_may_remain_connected_but_every_operation_targets_selected_phone(local_flash):
    service, runner, device, _image = local_flash
    runner.second_serial = "other-connected-phone"
    plan = _inspect(local_flash)
    result = _execute(service, plan)
    assert result.state is LocalFlashState.COMPLETED
    targeted = [command for command in runner.calls if command[1:] != ("devices", "-l")]
    assert targeted
    assert all(command[1:3] == ("-s", device.serial) for command in targeted)
    assert all(runner.second_serial not in command for command in targeted)


def test_duplicate_selected_serial_is_ambiguous_and_cannot_be_used(local_flash):
    _service, runner, _device, _image = local_flash
    runner.second_serial = runner.serial
    with pytest.raises(LocalFlashError, match="serial is ambiguous"):
        _inspect(local_flash)
    assert runner.writes == []
