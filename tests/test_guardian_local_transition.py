from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from romverse.device.models import AndroidDevice, DeviceState
from romverse.guardian.local_flash import LocalFlashError, LocalFlashService, LocalFlashState
from romverse.guardian.local_transition import (
    LocalDeviceTransitionService,
    LocalTransitionTarget,
)
from romverse.infrastructure.process import CommandResult


class Clock:
    def __init__(self):
        self.elapsed = 0.0

    def monotonic(self):
        return self.elapsed

    def now(self):
        return datetime(2026, 9, 5, tzinfo=UTC) + timedelta(seconds=self.elapsed)

    def sleep(self, duration):
        self.elapsed += duration


class TransitionRunner:
    def __init__(self, mode="bootloader"):
        self.mode = mode
        self.serial = "private-transition-phone-3210"
        self.product = "popsicle"
        self.codename = None
        self.boot_mode = "normal"
        self.pending = ""
        self.departure_polls = 1
        self.discovery_count = 0
        self.acknowledge_only = False
        self.never_arrive = False
        self.wrong_arrival_serial = ""
        self.wrong_arrival_product = ""
        self.unrelated_serial = ""
        self.duplicate = False
        self.authorized = True
        self.fail_reboot = False
        self.timeout_reboot = False
        self.fail_getprop = False
        self.fail_discovery = False
        self.calls = []
        self.on_reboot = None

    @property
    def reboots(self):
        return [command for command in self.calls if "reboot" in command]

    def _advance(self):
        if not self.pending:
            return
        self.discovery_count += 1
        if self.never_arrive or self.discovery_count <= self.departure_polls:
            self.mode = "disconnected"
            return
        self.mode = self.pending
        self.pending = ""
        if self.wrong_arrival_serial:
            self.serial = self.wrong_arrival_serial
        if self.wrong_arrival_product:
            self.product = self.wrong_arrival_product

    def run(self, args, timeout=10, cwd=None):
        del timeout, cwd
        command = tuple(str(item) for item in args)
        self.calls.append(command)
        tool = Path(command[0]).name
        if command[1:] == ("devices", "-l"):
            self._advance()
            if self.fail_discovery:
                return CommandResult(command, 1, "", "fixture discovery failure")
            rows = []
            if (tool == "adb" and self.mode == "android") or (
                tool == "fastboot" and self.mode in {"bootloader", "fastbootd"}
            ):
                state = (
                    "fastboot"
                    if tool == "fastboot"
                    else "device"
                    if self.authorized
                    else "unauthorized"
                )
                rows.append(f"{self.serial} {state} usb:1-1")
                if self.duplicate:
                    rows.append(f"{self.serial} {state} usb:2-2")
            if self.unrelated_serial:
                state = "device" if tool == "adb" else "fastboot"
                rows.append(f"{self.unrelated_serial} {state} usb:3-3")
            header = "List of devices attached\n" if tool == "adb" else ""
            return CommandResult(command, 0, header + "\n".join(rows) + "\n", "")
        if command[1:3] != ("-s", self.serial):
            return CommandResult(command, 1, "", "fixture wrong serial")
        if command[3:5] == ("shell", "getprop"):
            if self.fail_getprop:
                return CommandResult(command, 1, "", "fixture property failure")
            props = {
                "ro.product.name": self.product,
                "ro.product.device": self.product if self.codename is None else self.codename,
                "ro.product.manufacturer": "Xiaomi",
                "ro.product.model": "Test phone",
                "ro.build.version.release": "17",
                "ro.build.id": "TEST-1",
                "ro.build.fingerprint": "fixture/popsicle/build-1",
                "ro.boot.slot_suffix": "_a",
                "ro.bootmode": self.boot_mode,
                "sys.boot_completed": "0",
            }
            return CommandResult(
                command, 0, "\n".join(f"[{key}]: [{value}]" for key, value in props.items()), ""
            )
        if command[3] == "getvar":
            variable = command[4]
            value = (
                self.product
                if variable == "product"
                else "yes"
                if self.mode == "fastbootd"
                else "no"
            )
            return CommandResult(command, 0, "", f"(bootloader) {variable}: {value}\n")
        if command[3] == "reboot":
            if self.on_reboot:
                self.on_reboot(command)
            if self.fail_reboot or self.timeout_reboot:
                return CommandResult(
                    command,
                    124 if self.timeout_reboot else 1,
                    "",
                    "fixture reboot failure",
                    self.timeout_reboot,
                )
            target = (
                "bootloader"
                if command[4:] == ("bootloader",)
                else "fastbootd"
                if command[4:] == ("fastboot",)
                else "android"
            )
            if not self.acknowledge_only:
                self.pending = target
                self.discovery_count = 0
            return CommandResult(
                command, 0, "", f"Reboot requested for serial={self.serial} from {command[0]}\n"
            )
        raise AssertionError(f"Unexpected command: {command}")


@pytest.fixture
def transition(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    adb, fastboot = tmp_path / "adb", tmp_path / "fastboot"
    for path in (adb, fastboot):
        path.write_bytes(b"fixture tool")
        path.chmod(0o700)
    runner = TransitionRunner()
    clock = Clock()
    flash = LocalFlashService(workspace, runner, fastboot)
    service = LocalDeviceTransitionService(
        flash,
        adb,
        clock=clock.now,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
        arrival_timeout_seconds=2,
    )
    return service, runner, clock


def _device(runner):
    state = {
        "android": DeviceState.DEVICE,
        "bootloader": DeviceState.BOOTLOADER,
        "fastbootd": DeviceState.FASTBOOTD,
    }[runner.mode]
    return AndroidDevice(
        serial=runner.serial,
        state=state,
        transport="usb" if state is DeviceState.DEVICE else "usb-fastboot",
        manufacturer="Xiaomi",
        model="Test phone",
        product=runner.product,
        codename=runner.product,
    )


def _execute(service, plan, **kwargs):
    return service.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True, **kwargs)


@pytest.mark.parametrize(
    "source,target,tool,suffix",
    [
        ("android", LocalTransitionTarget.BOOTLOADER, "adb", ("bootloader",)),
        ("android", LocalTransitionTarget.FASTBOOTD, "adb", ("fastboot",)),
        ("android", LocalTransitionTarget.ANDROID, "adb", ()),
        ("bootloader", LocalTransitionTarget.FASTBOOTD, "fastboot", ("fastboot",)),
        ("bootloader", LocalTransitionTarget.ANDROID, "fastboot", ()),
        ("fastbootd", LocalTransitionTarget.BOOTLOADER, "fastboot", ("bootloader",)),
        ("fastbootd", LocalTransitionTarget.ANDROID, "fastboot", ()),
    ],
)
def test_each_reviewed_transition_observes_exact_arrival_without_claiming_boot(
    transition, source, target, tool, suffix
):
    service, runner, _clock = transition
    runner.mode = source
    device = _device(runner)
    plan = service.inspect(device, target)
    assert runner.reboots == []
    assert plan.source_mode == source
    result = _execute(service, plan)
    assert result.state is LocalFlashState.COMPLETED
    assert result.phone_change_attempted and result.arrival_verified
    assert result.command_completed
    assert result.observed_device.serial == device.serial
    assert result.boot_verified is False
    assert result.observed_device.boot_completed is None
    assert len(runner.reboots) == 1
    assert Path(runner.reboots[0][0]).name == tool
    assert runner.reboots[0][1:] == ("-s", device.serial, "reboot", *suffix)
    document = json.loads(result.receipt_path.read_text())
    assert document["arrival_verified"]
    assert document["boot_verified"] is False
    assert document["record_digest"]
    assert not document["phone_state_uncertain"]
    assert device.serial not in result.receipt_path.read_text()
    assert str(service.adb_path.parent) not in result.receipt_path.read_text()
    assert service.flash_service.audit.verify().valid
    if os.name != "nt":
        assert result.receipt_path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "source,target",
    [
        ("bootloader", LocalTransitionTarget.FASTBOOTD),
        ("android", LocalTransitionTarget.ANDROID),
    ],
)
def test_reboot_exit_zero_without_requested_arrival_cannot_report_completion(
    transition, source, target
):
    service, runner, clock = transition
    runner.mode = source
    runner.acknowledge_only = True
    plan = service.inspect(_device(runner), target)
    result = _execute(service, plan)
    assert result.state is LocalFlashState.FAILED
    assert result.phone_change_attempted
    assert result.command_completed
    assert not result.arrival_verified and not result.boot_verified
    assert result.observed_device is None
    assert clock.elapsed == 2
    if source == "bootloader":
        assert (
            json.loads(result.receipt_path.read_text())["last_seen_device"]["mode"] == "bootloader"
        )


def test_disconnection_without_arrival_times_out_with_retained_journal(transition):
    service, runner, clock = transition
    runner.never_arrive = True
    plan = service.inspect(_device(runner), LocalTransitionTarget.ANDROID)
    result = _execute(service, plan)
    assert result.state is LocalFlashState.FAILED
    assert clock.elapsed == 2
    record = json.loads(result.receipt_path.read_text())
    assert record["arrival_observation_count"] > 0
    assert record["phone_state_uncertain"]
    assert record["command_result"]["returncode"] == 0


@pytest.mark.parametrize("change", ["product", "serial"])
def test_arrival_as_a_different_phone_is_never_assumed(transition, change):
    service, runner, _clock = transition
    setattr(runner, f"wrong_arrival_{change}", "different-phone")
    plan = service.inspect(_device(runner), LocalTransitionTarget.ANDROID)
    result = _execute(service, plan)
    assert result.state is LocalFlashState.FAILED
    assert not result.arrival_verified and result.observed_device is None


def test_another_connected_phone_does_not_prevent_exact_target_operation(transition):
    service, runner, _clock = transition
    runner.unrelated_serial = "second-phone"
    device = _device(runner)
    plan = service.inspect(device, LocalTransitionTarget.ANDROID)
    assert _execute(service, plan).state is LocalFlashState.COMPLETED
    targeted = [command for command in runner.calls if command[1:] != ("devices", "-l")]
    assert all(command[1:3] == ("-s", device.serial) for command in targeted)


@pytest.mark.parametrize("source", ["android", "bootloader"])
def test_duplicate_selected_serial_is_rejected(transition, source):
    service, runner, _clock = transition
    runner.mode = source
    runner.duplicate = True
    with pytest.raises(LocalFlashError, match="ambiguous|more than one"):
        service.inspect(_device(runner), LocalTransitionTarget.FASTBOOTD)
    assert runner.reboots == []


def test_missing_confirmation_tampered_preview_and_foreign_service_never_reboot(transition):
    service, runner, clock = transition
    plan = service.inspect(_device(runner), LocalTransitionTarget.ANDROID)
    with pytest.raises(LocalFlashError, match="Confirm"):
        service.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=False)
    with pytest.raises(LocalFlashError, match="Confirm"):
        service.execute(plan, accepted_digest="wrong", risk_accepted=True)
    with pytest.raises(LocalFlashError, match="preview changed"):
        _execute(service, replace(plan, target=LocalTransitionTarget.FASTBOOTD))
    other = LocalDeviceTransitionService(service.flash_service, service.adb_path, clock=clock.now)
    with pytest.raises(LocalFlashError, match="already used"):
        _execute(other, plan)
    assert runner.reboots == []


def test_confirmation_expires_and_is_single_use_but_new_review_can_retry(transition):
    service, runner, clock = transition
    device = _device(runner)
    expired = service.inspect(device, LocalTransitionTarget.ANDROID)
    clock.elapsed = 121
    with pytest.raises(LocalFlashError, match="expired"):
        _execute(service, expired)
    plan = service.inspect(device, LocalTransitionTarget.ANDROID)
    runner.fail_reboot = True
    assert _execute(service, plan).state is LocalFlashState.FAILED
    with pytest.raises(LocalFlashError, match="already used"):
        _execute(service, plan)
    fresh = service.inspect(device, LocalTransitionTarget.ANDROID)
    assert fresh.plan_digest != plan.plan_digest
    runner.fail_reboot = False
    assert _execute(service, fresh).state is LocalFlashState.COMPLETED


@pytest.mark.parametrize("change", ["tool", "product", "mode", "serial"])
def test_changed_tool_or_source_identity_stops_before_command(transition, change):
    service, runner, _clock = transition
    plan = service.inspect(_device(runner), LocalTransitionTarget.ANDROID)
    if change == "tool":
        service.adb_path.write_bytes(b"changed tool")
    elif change == "mode":
        runner.mode = "fastbootd"
    else:
        setattr(runner, change, "different")
    result = _execute(service, plan)
    assert result.state is LocalFlashState.REJECTED
    assert not result.phone_change_attempted
    assert runner.reboots == []


def test_cancel_before_command_and_while_observing_have_different_honest_results(transition):
    service, runner, _clock = transition
    device = _device(runner)
    plan = service.inspect(device, LocalTransitionTarget.ANDROID)
    stopped = False

    def progress(_done, _total, _message):
        nonlocal stopped
        stopped = True

    result = _execute(service, plan, should_cancel=lambda: stopped, progress=progress)
    assert result.state is LocalFlashState.CANCELLED
    assert not result.phone_change_attempted
    assert runner.reboots == []
    fresh = service.inspect(device, LocalTransitionTarget.ANDROID)
    result = _execute(service, fresh, should_cancel=lambda: bool(runner.reboots))
    assert result.state is LocalFlashState.CANCELLED
    assert result.phone_change_attempted
    assert len(runner.reboots) == 1
    assert not result.arrival_verified


def test_in_flight_journal_exists_before_reboot_and_lock_excludes_image_operation(transition):
    service, runner, _clock = transition
    plan = service.inspect(_device(runner), LocalTransitionTarget.ANDROID)

    def inspect_journal(_command):
        record = json.loads((service.root / f"{plan.plan_id}.json").read_text())
        assert record["state"] == "command-in-flight"
        assert record["phone_change_attempted"] and record["phone_state_uncertain"]
        with (
            pytest.raises(LocalFlashError, match="Another local image operation"),
            service.flash_service._device_lock(runner.serial),
        ):
            raise AssertionError("Concurrent operation acquired device lock")

    runner.on_reboot = inspect_journal
    assert _execute(service, plan).state is LocalFlashState.COMPLETED


def test_interruption_preserves_uncertain_in_flight_transition(transition):
    service, runner, _clock = transition
    plan = service.inspect(_device(runner), LocalTransitionTarget.ANDROID)

    def interrupt(_command):
        raise KeyboardInterrupt

    runner.on_reboot = interrupt
    with pytest.raises(KeyboardInterrupt):
        _execute(service, plan)
    record = json.loads((service.root / f"{plan.plan_id}.json").read_text())
    assert record["state"] == "command-in-flight"
    assert record["phone_state_uncertain"]
    assert record["boot_verified"] is False


def test_unauthorized_android_missing_identity_and_non_usb_target_rejected(transition):
    service, runner, _clock = transition
    runner.mode = "android"
    device = _device(runner)
    runner.authorized = False
    with pytest.raises(LocalFlashError):
        service.inspect(device, LocalTransitionTarget.BOOTLOADER)
    runner.authorized = True
    with pytest.raises(LocalFlashError, match="product identity"):
        service.inspect(replace(device, product="", codename=""), LocalTransitionTarget.BOOTLOADER)
    with pytest.raises(LocalFlashError, match="by USB"):
        service.inspect(replace(device, transport="network"), LocalTransitionTarget.BOOTLOADER)
    assert runner.reboots == []


def test_adb_is_required_to_verify_android_arrival_before_rebooting(transition):
    service, runner, _clock = transition
    service.adb_path = None
    with pytest.raises(LocalFlashError, match="Verify ADB"):
        service.inspect(_device(runner), LocalTransitionTarget.ANDROID)
    assert runner.reboots == []


def test_android_reboot_does_not_treat_failed_discovery_as_observed_departure(transition):
    service, runner, _clock = transition
    runner.mode = "android"
    runner.acknowledge_only = True
    plan = service.inspect(_device(runner), LocalTransitionTarget.ANDROID)
    runner.on_reboot = lambda _command: setattr(runner, "fail_discovery", True)
    result = _execute(service, plan)
    assert result.state is LocalFlashState.FAILED
    assert not result.arrival_verified
    assert not json.loads(result.receipt_path.read_text())["source_departure_observed"]


def test_already_in_requested_fastboot_mode_is_actionable_without_command(transition):
    service, runner, _clock = transition
    with pytest.raises(LocalFlashError, match="already in bootloader"):
        service.inspect(_device(runner), LocalTransitionTarget.BOOTLOADER)
    assert runner.reboots == []


def test_matching_product_does_not_hide_a_known_contradictory_android_codename(transition):
    service, runner, _clock = transition
    plan = service.inspect(_device(runner), LocalTransitionTarget.ANDROID)
    runner.on_reboot = lambda _command: setattr(runner, "codename", "other-phone")
    result = _execute(service, plan)
    assert result.state is LocalFlashState.FAILED
    assert result.command_completed and result.phone_change_attempted
    assert not result.arrival_verified and result.observed_device is None


def test_source_android_codename_conflict_rejects_before_any_reboot(transition):
    service, runner, _clock = transition
    runner.mode = "android"
    device = _device(runner)
    runner.codename = "other-phone"
    with pytest.raises(LocalFlashError, match="differs"):
        service.inspect(device, LocalTransitionTarget.BOOTLOADER)
    assert runner.reboots == []


def test_android_product_region_variant_with_matching_codename_is_allowed(transition):
    service, runner, _clock = transition
    plan = service.inspect(_device(runner), LocalTransitionTarget.ANDROID)
    runner.wrong_arrival_product = "popsicle_global"
    runner.codename = "popsicle"
    result = _execute(service, plan)
    assert result.state is LocalFlashState.COMPLETED
    assert result.observed_device.product == "popsicle_global"
    assert result.observed_device.codename == "popsicle"


def test_fastboot_product_can_match_reviewed_android_product_alias(transition):
    service, runner, _clock = transition
    runner.mode = "android"
    runner.product = "popsicle_global"
    runner.codename = "popsicle"
    device = replace(_device(runner), codename="popsicle")
    plan = service.inspect(device, LocalTransitionTarget.BOOTLOADER)
    result = _execute(service, plan)
    assert result.state is LocalFlashState.COMPLETED
    assert result.observed_device.product == "popsicle_global"
    assert result.observed_device.codename == "popsicle"
    back_to_android = service.inspect(result.observed_device, LocalTransitionTarget.ANDROID)
    returned = _execute(service, back_to_android)
    assert returned.state is LocalFlashState.COMPLETED
    assert returned.observed_device.codename == "popsicle"


@pytest.mark.parametrize("boot_mode", ["recovery", "sideload", "rescue"])
def test_recovery_exposing_device_adb_row_is_not_android_arrival(transition, boot_mode):
    service, runner, clock = transition
    plan = service.inspect(_device(runner), LocalTransitionTarget.ANDROID)
    runner.on_reboot = lambda _command: setattr(runner, "boot_mode", boot_mode)
    result = _execute(service, plan)
    assert result.state is LocalFlashState.FAILED
    assert result.command_completed and result.phone_change_attempted
    assert not result.arrival_verified and result.observed_device is None
    assert clock.elapsed == 2


def test_recovery_exposing_device_adb_row_cannot_be_reviewed_as_android_source(transition):
    service, runner, _clock = transition
    runner.mode = "android"
    runner.boot_mode = "recovery"
    with pytest.raises(LocalFlashError):
        service.inspect(_device(runner), LocalTransitionTarget.BOOTLOADER)
    assert runner.reboots == []
