from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from romverse.device.models import AndroidDevice, DeviceState
from romverse.guardian.local_flash import LocalFlashSelection, LocalFlashService
from romverse.infrastructure.process import CommandResult
from romverse.rom.local_boot import LocalBootError, LocalBootService, LocalBootStatus
from tests.test_guardian_local_flash import FakeFastboot


class Clock:
    seconds = 1000.0

    def tick(self):
        return self.seconds

    def utc(self):
        return datetime(2026, 9, 5, tzinfo=UTC) + timedelta(seconds=self.seconds)

    def advance(self, seconds=5):
        self.seconds += seconds


class AndroidTransport(FakeFastboot):
    def __init__(self, clock):
        super().__init__()
        self.clock = clock
        self.adb_state = "device"
        self.adb_present = True
        self.duplicate = False
        self.unrelated = True
        self.boot_started = clock.seconds - 30
        self.fixed_uptime = None
        self.uptime_text = None
        self.boot_id = "745b5af6-3abc-4d84-9f14-94c0c03380a5"
        self.properties = {
            "sys.boot_completed": "1",
            "ro.product.device": "popsicle",
            "ro.product.name": "popsicle_cn",
            "ro.build.fingerprint": "Xiaomi/popsicle_cn/popsicle:17/TEST/123:user/release-keys",
            "ro.boot.slot_suffix": "_a",
            "ro.bootmode": "normal",
            "ro.build.version.release": "17",
            "ro.build.id": "TEST-1",
        }
        self.failed_suffix = None
        self.timeout_suffix = None
        self.wrong_args = False
        self.on_adb = None

    @property
    def adb_calls(self):
        return [call for call in self.calls if Path(call[0]).name == "adb"]

    def run(self, args, timeout=10, cwd=None):
        command = tuple(map(str, args))
        if Path(command[0]).name != "adb":
            return super().run(command, timeout=timeout, cwd=cwd)
        self.calls.append(command)
        if self.on_adb:
            self.on_adb(command)
        if command[1:] == ("devices", "-l"):
            rows = ["List of devices attached"]
            if self.adb_present:
                rows += [
                    f"{self.serial} {self.adb_state} product:popsicle_cn model:Test device:popsicle"
                ] * (2 if self.duplicate else 1)
            if self.unrelated:
                rows.append("unrelated-phone device product:other model:Other device:other")
            output = "\n".join(rows) + "\n"
        else:
            assert command[1:3] == ("-s", self.serial)
            suffix = command[3:]
            if suffix == self.timeout_suffix:
                return CommandResult(command, 124, "", "timeout", timed_out=True)
            if suffix == self.failed_suffix:
                return CommandResult(command, 1, "", "Permission denied")
            if suffix[:2] == ("shell", "getprop"):
                assert len(suffix) == 3 and suffix[2] in (
                    LocalBootService.PROPERTIES + LocalBootService.OPTIONAL_PROPERTIES
                )
                output = self.properties[suffix[2]] + "\n"
            elif suffix == ("shell", "cat", "/proc/uptime"):
                uptime = (
                    self.clock.seconds - self.boot_started
                    if self.fixed_uptime is None
                    else self.fixed_uptime
                )
                output = (
                    self.uptime_text if self.uptime_text is not None else f"{uptime:.2f} 200.00\n"
                )
            elif suffix == ("shell", "cat", "/proc/sys/kernel/random/boot_id"):
                output = self.boot_id + "\n"
            else:
                raise AssertionError(f"Unapproved device command: {command}")
        return CommandResult(("wrong",) if self.wrong_args else command, 0, output, "")


@pytest.fixture
def monitor(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for name in ("adb", "fastboot"):
        tool = tmp_path / name
        tool.write_bytes(b"inert test tool")
        tool.chmod(0o700)
    clock = Clock()
    runner = AndroidTransport(clock)
    flash = LocalFlashService(workspace, runner, tmp_path / "fastboot")
    service = LocalBootService(
        flash, tmp_path / "adb", monotonic_clock=clock.tick, utc_clock=clock.utc
    )
    device = AndroidDevice(
        runner.serial,
        DeviceState.BOOTLOADER,
        manufacturer="Xiaomi",
        model="Test phone",
        product="popsicle",
        codename="popsicle",
    )
    return service, flash, runner, clock, device


def test_boot_monitor_requires_a_real_spaced_window_and_never_claims_health(monitor):
    service, flash, runner, clock, device = monitor
    session = service.begin(device)
    assert runner.adb_calls == []
    report = service.observe(session)
    assert report.status is LocalBootStatus.SETTLING
    assert report.boot_observed and not report.terminal
    for _ in range(11):
        clock.advance()
        report = service.observe(session)
        assert report.status is LocalBootStatus.SETTLING
    clock.advance()
    report = service.observe(session)
    assert report.status is LocalBootStatus.STABLE and report.terminal
    assert report.sample_count == 13 and report.elapsed_seconds == 60
    assert report.latest_device.serial == device.serial
    assert report.latest_device.build_fingerprint == runner.properties["ro.build.fingerprint"]
    assert report.latest_device.android_version == "17"
    assert report.latest_device.build_id == "TEST-1"
    assert report.latest_device.battery_percent is None
    data = json.loads(report.receipt_path.read_bytes())
    assert data["readback_verified"] is False and data["subsystems_verified"] is False
    assert data["production_certified"] is False and data["guardian_execution_certified"] is False
    assert data["phone_changed"] is False and data["execution_authority"] == "none"
    assert device.serial not in report.receipt_path.read_text()
    assert runner.boot_id not in report.receipt_path.read_text()
    assert runner.properties["ro.build.fingerprint"] not in report.receipt_path.read_text()
    if os.name != "nt":
        assert report.receipt_path.stat().st_mode & 0o777 == 0o600
    assert flash.audit.verify().valid
    assert runner.writes == []
    commands = len(runner.calls)
    assert service.observe(session) is report
    assert len(runner.calls) == commands


def test_repeated_fast_calls_cannot_manufacture_samples_or_stability(monitor):
    service, _, runner, clock, device = monitor
    session = service.begin(device)
    first = service.observe(session)
    count = len(runner.calls)
    for _ in range(40):
        clock.advance(0.1)
        report = service.observe(session)
        assert report is first
    assert len(runner.calls) == count
    assert report.sample_count == 1 and not report.terminal


@pytest.mark.parametrize(
    "adb_state", ["unauthorized", "offline", "recovery", "sideload", "unknown"]
)
def test_non_android_target_is_attention_without_shell_probes(monitor, adb_state):
    service, _, runner, _, device = monitor
    runner.adb_state = adb_state
    report = service.observe(service.begin(device))
    assert report.status is LocalBootStatus.ATTENTION
    assert not report.boot_observed and not report.terminal
    assert len(runner.adb_calls) == 1
    assert report.latest_device is None


def test_missing_selected_phone_never_adopts_unrelated_phone_and_times_out(monitor):
    service, _, runner, clock, device = monitor
    runner.adb_present = False
    session = service.begin(device)
    report = service.observe(session)
    assert report.failure_kind == "device_unavailable" and not report.boot_observed
    clock.advance(600)
    count = len(runner.calls)
    report = service.observe(session)
    assert report.terminal and report.failure_kind == "boot_timeout"
    assert len(runner.calls) == count


def test_duplicate_selected_serial_is_rejected(monitor):
    service, _, runner, _, device = monitor
    runner.duplicate = True
    report = service.observe(service.begin(device))
    assert report.terminal and report.failure_kind == "ambiguous_target"
    assert not report.boot_observed


@pytest.mark.parametrize(
    "value", ["nan 0", "inf 0", "-1 0", "315360001 0", "1 nan", "123", "bad data"]
)
def test_unusable_uptime_never_counts_as_stability(monitor, value):
    service, _, runner, _, device = monitor
    runner.uptime_text = value
    report = service.observe(service.begin(device))
    assert report.status is LocalBootStatus.ATTENTION
    assert report.failure_kind == "uptime_unavailable"
    assert not report.boot_observed


@pytest.mark.parametrize(
    ("prop", "value"),
    [
        ("sys.boot_completed", "true"),
        ("ro.build.fingerprint", ""),
        ("ro.boot.slot_suffix", "both"),
        ("ro.product.device", "other"),
        ("ro.bootmode", "recovery"),
    ],
)
def test_malformed_or_wrong_identity_cannot_become_boot_success(monitor, prop, value):
    service, _, runner, _, device = monitor
    runner.properties[prop] = value
    report = service.observe(service.begin(device))
    assert report.status is LocalBootStatus.ATTENTION and not report.boot_observed


def test_waiting_for_boot_complete_starts_window_only_when_observed(monitor):
    service, _, runner, clock, device = monitor
    runner.properties["sys.boot_completed"] = "0"
    session = service.begin(device)
    assert service.observe(session).status is LocalBootStatus.WAITING
    clock.advance(60)
    runner.properties["sys.boot_completed"] = "1"
    report = service.observe(session)
    assert report.status is LocalBootStatus.SETTLING and not report.terminal
    assert "0 of 60" in report.summary


def test_frozen_uptime_and_long_gaps_cannot_complete_a_window(monitor):
    service, _, runner, clock, device = monitor
    session = service.begin(device)
    runner.fixed_uptime = 40
    service.observe(session)
    clock.advance(5)
    report = service.observe(session)
    assert report.failure_kind == "uptime_incoherent"
    runner.fixed_uptime = None
    clock.advance(90)
    report = service.observe(session)
    assert report.status is LocalBootStatus.SETTLING and not report.terminal
    assert "0 of 60" in report.summary


def test_restarts_reset_window_and_repeated_restarts_report_loop(monitor):
    service, _, runner, clock, device = monitor
    session = service.begin(device)
    service.observe(session)
    for index in range(2):
        clock.advance(5)
        runner.boot_started = clock.seconds
        runner.boot_id = f"745b5af6-3abc-4d84-9f14-94c0c03380a{index}"
        report = service.observe(session)
        assert report.failure_kind == ("reboot_detected" if index == 0 else "reboot_loop")
    assert report.terminal and report.status is LocalBootStatus.ATTENTION


def test_build_change_after_initial_observation_is_terminal(monitor):
    service, _, runner, clock, device = monitor
    session = service.begin(device)
    service.observe(session)
    clock.advance()
    runner.properties["ro.build.fingerprint"] = (
        "Other/popsicle_cn/popsicle:17/OTHER/456:user/release-keys"
    )
    report = service.observe(session)
    assert report.terminal and report.failure_kind == "identity_changed"


def test_reboots_during_property_collection_never_produce_a_mixed_boot_sample(monitor):
    service, _, runner, clock, device = monitor
    session = service.begin(device)

    def reboot_mid_sample(command):
        if command[-1] == "sys.boot_completed":
            runner.boot_id = str(uuid4())

    runner.on_adb = reboot_mid_sample
    first = service.observe(session)
    assert first.failure_kind == "reboot_during_sample" and not first.boot_observed
    clock.advance()
    report = service.observe(session)
    assert report.failure_kind == "reboot_loop" and report.terminal
    assert not report.boot_observed


def test_one_mid_sample_restart_is_not_counted_again_when_new_boot_arrives(monitor):
    service, _, runner, clock, device = monitor
    session = service.begin(device)
    service.observe(session)
    clock.advance()

    def restart_once(command):
        if command[-1] == "sys.boot_completed":
            runner.boot_id = str(uuid4())
            runner.boot_started = clock.seconds
            runner.on_adb = None

    runner.on_adb = restart_once
    assert service.observe(session).failure_kind == "reboot_during_sample"
    clock.advance()
    report = service.observe(session)
    assert report.status is LocalBootStatus.SETTLING and not report.terminal
    assert json.loads(report.receipt_path.read_text())["restarts_observed"] == 1


def test_boot_complete_loss_then_one_restart_is_not_a_reboot_loop(monitor):
    service, _, runner, clock, device = monitor
    session = service.begin(device)
    service.observe(session)
    clock.advance()
    runner.properties["sys.boot_completed"] = "0"
    assert service.observe(session).failure_kind == "boot_complete_lost"
    clock.advance()
    runner.boot_id = str(uuid4())
    runner.boot_started = clock.seconds
    runner.properties["sys.boot_completed"] = "1"
    report = service.observe(session)
    assert report.failure_kind == "reboot_detected" and not report.terminal
    assert json.loads(report.receipt_path.read_text())["restarts_observed"] == 1


def test_mid_sample_restart_cannot_discard_the_previous_build_identity(monitor):
    service, _, runner, clock, device = monitor
    session = service.begin(device)
    service.observe(session)
    clock.advance()

    def restart_once(command):
        if command[-1] == "sys.boot_completed":
            runner.boot_id = str(uuid4())
            runner.on_adb = None

    runner.on_adb = restart_once
    service.observe(session)
    clock.advance()
    runner.properties["ro.build.fingerprint"] = (
        "Other/popsicle/popsicle:17/OTHER/456:user/release-keys"
    )
    report = service.observe(session)
    assert report.failure_kind == "identity_changed" and report.terminal


@pytest.mark.parametrize("failure", ["denied", "timeout", "wrong_args", "boot_id"])
def test_missing_required_probe_evidence_never_counts_as_boot_success(monitor, failure):
    service, _, runner, _, device = monitor
    if failure == "denied":
        runner.failed_suffix = ("shell", "getprop", "sys.boot_completed")
    elif failure == "timeout":
        runner.timeout_suffix = ("shell", "getprop", "sys.boot_completed")
    elif failure == "wrong_args":
        runner.wrong_args = True
    else:
        runner.boot_id = "not-a-boot-id"
    report = service.observe(service.begin(device))
    assert report.status is LocalBootStatus.ATTENTION and not report.boot_observed


@pytest.mark.parametrize("prop", ["ro.build.version.release", "ro.build.id"])
@pytest.mark.parametrize("failure", ["unsupported", "empty", "malformed"])
def test_optional_version_and_build_id_are_not_stability_gates(monitor, prop, failure):
    service, _, runner, clock, device = monitor
    if failure == "unsupported":
        runner.failed_suffix = ("shell", "getprop", prop)
    else:
        runner.properties[prop] = "" if failure == "empty" else "not a valid field\n"
    session = service.begin(device)
    for _ in range(13):
        report = service.observe(session)
        clock.advance()
    assert report.status is LocalBootStatus.STABLE
    field = "android_version" if prop == "ro.build.version.release" else "build_id"
    assert getattr(report.latest_device, field) == ""


def test_stop_retains_evidence_without_phone_commands_and_stops_active_probe(monitor):
    service, _, runner, clock, device = monitor
    session = service.begin(device)
    service.observe(session)
    clock.advance()
    stopped = []

    def cancel_during_probe(command):
        runner.on_adb = None
        stopped.append(service.stop(session))

    runner.on_adb = cancel_during_probe
    count = len(runner.calls)
    report = service.observe(session)
    assert len(runner.calls) == count + 1
    assert report is stopped[0]
    assert report.status is LocalBootStatus.CANCELLED and report.terminal
    assert report.sample_count == 1
    assert json.loads(report.receipt_path.read_text())["status"] == "cancelled"
    assert service.stop(session) is report


def test_forged_session_and_changed_adb_are_rejected(monitor):
    service, _, _, _, device = monitor
    session = service.begin(device)
    with pytest.raises(LocalBootError, match="not owned"):
        service.observe(replace(session))
    service.adb_path.write_bytes(b"modified tool")
    report = service.observe(session)
    assert report.terminal and report.failure_kind == "tool_changed"


def test_boot_probes_share_the_image_write_device_lock(monitor):
    service, flash, runner, clock, device = monitor
    session = service.begin(device)
    with flash._device_lock(device.serial):
        report = service.observe(session)
    assert report.status is LocalBootStatus.ATTENTION
    assert runner.adb_calls == []
    clock.advance()
    assert service.observe(session).status is LocalBootStatus.SETTLING


def test_temporary_transport_loss_restarts_the_measured_window(monitor):
    service, _, runner, clock, device = monitor
    session = service.begin(device)
    for _ in range(10):
        service.observe(session)
        clock.advance()
    runner.adb_present = False
    assert service.observe(session).failure_kind == "device_unavailable"
    clock.advance()
    runner.adb_present = True
    report = service.observe(session)
    assert report.status is LocalBootStatus.SETTLING and not report.terminal
    assert "0 of 60" in report.summary


def test_naive_timestamp_is_rejected_before_session_or_device_probe(monitor):
    service, _, runner, _, device = monitor
    service.utc_clock = lambda: datetime(2026, 9, 5)
    with pytest.raises(LocalBootError, match="timezone"):
        service.begin(device)
    assert runner.adb_calls == []


def test_failed_persistence_never_returns_stable_success(monitor, monkeypatch):
    service, _, _, clock, device = monitor
    session = service.begin(device)
    for _ in range(12):
        service.observe(session)
        clock.advance()

    def unavailable(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("romverse.rom.local_boot.atomic_write_json", unavailable)
    report = service.observe(session)
    assert report.status is LocalBootStatus.ATTENTION and report.terminal
    assert report.failure_kind == "persistence_failed"


def _flash_result(context):
    _, flash, _, _, device = context
    image = flash.workspace / "input.img"
    image.write_bytes(b"inert image fixture")
    plan = flash.inspect(device, (LocalFlashSelection("boot_a", image),))
    return flash.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True)


def test_optional_local_flash_binding_preserves_original_and_rejects_changes(monitor):
    service, _, runner, clock, device = monitor
    result = _flash_result(monitor)
    original = result.receipt_path.read_bytes()
    session = service.begin(device, result)
    report = service.observe(session)
    data = json.loads(report.receipt_path.read_bytes())
    assert data["flash_binding"]["record_digest"] == json.loads(original)["record_digest"]
    assert result.receipt_path.read_bytes() == original
    changed = json.loads(original)
    changed["summary"] = "changed result"
    result.receipt_path.write_text(json.dumps(changed))
    clock.advance()
    count = len(runner.adb_calls)
    report = service.observe(session)
    assert report.terminal and report.failure_kind == "flash_record_changed"
    assert len(runner.adb_calls) == count


@pytest.mark.parametrize("change", ["target", "results", "digest", "outside", "symlink"])
def test_invalid_flash_binding_cannot_be_attached(monitor, change, tmp_path):
    service, _, _, _, device = monitor
    result = _flash_result(monitor)
    if change == "target":
        device = replace(device, serial="other-phone")
    elif change == "results":
        result = replace(result, results=())
    elif change == "digest":
        data = json.loads(result.receipt_path.read_bytes())
        data["record_digest"] = "0" * 64
        result.receipt_path.write_text(json.dumps(data))
    elif change == "outside":
        result = replace(result, receipt_path=tmp_path / result.receipt_path.name)
    elif change == "symlink":
        payload = result.receipt_path.read_bytes()
        outside = tmp_path / "outside.json"
        outside.write_bytes(payload)
        result.receipt_path.unlink()
        result.receipt_path.symlink_to(outside)
    with pytest.raises((LocalBootError, OSError)):
        service.begin(device, result)


@pytest.mark.parametrize(
    "change", ["extra_field", "size", "timestamp", "plan_digest", "snapshot_path", "write_target"]
)
def test_resealed_malformed_flash_journals_are_not_treated_as_a_valid_binding(monitor, change):
    service, _, _, _, device = monitor
    result = _flash_result(monitor)
    document = json.loads(result.receipt_path.read_bytes())
    if change == "extra_field":
        document["guardian_execution_authority"] = "approved"
    elif change == "size":
        document["writes"][0]["size_bytes"] = True
    elif change == "timestamp":
        document["started_at"] = "2026-09-05T00:00:00"
    elif change == "plan_digest":
        document["plan_digest"] = "not-a-digest"
    elif change == "snapshot_path":
        document["image_snapshots"][0]["relative_path"] = "../outside.img"
    else:
        document["writes"][0]["partition"] = "boot_b"
    document.pop("record_digest")
    document["record_digest"] = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    result.receipt_path.write_text(json.dumps(document))
    with pytest.raises(LocalBootError):
        service.begin(device, result)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -1, True])
def test_invalid_clocks_do_not_create_boot_evidence(monitor, invalid):
    service, _, _, clock, device = monitor
    clock.seconds = invalid
    with pytest.raises(LocalBootError):
        service.begin(device)


def test_monotonic_clock_regression_does_not_count_stability(monitor):
    service, _, _, clock, device = monitor
    session = service.begin(device)
    service.observe(session)
    clock.advance(-1)
    with pytest.raises(LocalBootError, match="backwards"):
        service.observe(session)
