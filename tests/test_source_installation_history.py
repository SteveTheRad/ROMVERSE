"""Historical records must never authorize installation or hide a later failure."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta

import pytest

from romverse.guardian.local_flash import LocalFlashState
from romverse.guardian.source_installation import (
    SourceInstallationExecutor,
    SourceInstallationResult,
    validate_source_installation_boot_binding,
)
from romverse.rom.local_boot import LocalBootService, LocalBootStatus
from romverse.rom.source_installation_history import (
    _digest,
    load_latest_source_installation,
)
from tests.test_source_installation_integration import installation as installation


def _execute(fixture, *, reboot=False, cancel=False):
    executor = SourceInstallationExecutor(fixture.source, fixture.flash, fixture.adb)
    recipe = fixture.recipe(reboot=reboot)
    plan = executor.inspect(fixture.phone.device(), recipe)
    result = executor.execute(
        plan, accepted_digest=plan.plan_digest, risk_accepted=True, should_cancel=lambda: cancel
    )
    return executor, plan, result


def _load(fixture):
    return load_latest_source_installation(fixture.source.store, fixture.project_id)


def _document(path):
    return json.loads(path.read_text())


def _save(path, document, *, seal=True):
    document.pop("record_digest", None)
    if seal:
        document["record_digest"] = _digest(document)
    path.write_text(json.dumps(document))


def test_empty_history_is_read_only_and_none(installation):
    files = set(installation.source.store.workspace.rglob("*"))
    assert _load(installation) is None
    assert files == set(installation.source.store.workspace.rglob("*"))


def test_valid_terminal_result_rehydrates_for_separate_exact_phone_boot_validation(installation):
    _executor, _plan, result = _execute(installation)
    outcome = _load(installation)
    assert outcome.state == "completed"
    assert outcome.project_id == installation.project_id
    assert outcome.completed_count == outcome.expected_count == 52
    assert outcome.historical and not outcome.current_artifact_bytes_verified
    assert outcome.device_key == installation.flash.privacy.pseudonym(installation.phone.serial)
    assert outcome.product == "popsicle"
    assert outcome.operation_device_key == outcome.device_key
    assert outcome.operation_product == outcome.product
    assert outcome.matches_operation_device(
        installation.flash.privacy, installation.phone.device()
    )
    assert outcome.boot_status == "No linked boot-check record"
    assert isinstance(outcome.result, SourceInstallationResult)
    assert outcome.result == result
    assert outcome.result.boot_verified is False
    assert (
        validate_source_installation_boot_binding(
            installation.flash, installation.phone.device(), outcome.result
        )["record_digest"]
        == _document(result.receipt_path)["record_digest"]
    )


def test_history_never_rehashes_firmware_or_calls_phone_or_changes_files(installation, monkeypatch):
    _execute(installation)
    files = {
        path: path.stat().st_mtime_ns
        for path in installation.source.store.workspace.rglob("*")
        if path.is_file()
    }

    def forbidden(*_args, **_kwargs):
        raise AssertionError(
            "History cannot perform preparation, firmware verification or device commands"
        )

    monkeypatch.setattr(installation.source, "prepare", forbidden)
    monkeypatch.setattr(installation.source.store, "verify_original", forbidden)
    monkeypatch.setattr(installation.phone, "run", forbidden)
    assert _load(installation).state == "completed"
    assert files == {
        path: path.stat().st_mtime_ns
        for path in installation.source.store.workspace.rglob("*")
        if path.is_file()
    }


def test_later_valid_failed_installation_replaces_old_success(installation):
    _execute(installation)
    installation.phone.fail_partition = "abl_a"
    _executor, _plan, failed = _execute(installation)
    outcome = _load(installation)
    assert outcome.state == "failed"
    assert outcome.receipt_path == failed.receipt_path
    assert outcome.result == failed
    assert outcome.completed_count < outcome.expected_count
    assert len(outcome.actions("failed")) == 1
    assert outcome.actions("failed")[0].target == "abl_a"
    assert not outcome.actions("uncertain")
    assert outcome.actions("unattempted")
    assert outcome.record_digest == _document(failed.receipt_path)["record_digest"]
    assert outcome.receipt_relative_path.startswith("guardian/source-installation/")
    assert str(installation.source.store.workspace) not in outcome.recovery_summary()


def test_runner_exception_preserves_unknown_inflight_action_without_calling_it_failed(
    installation, monkeypatch
):
    executor = SourceInstallationExecutor(
        installation.source, installation.flash, installation.adb
    )
    plan = executor.inspect(installation.phone.device(), installation.recipe(reboot=False))
    original_run = executor._run

    def interrupted(command, **kwargs):
        if "super" in command:
            raise OSError("simulated transport vanished during command")
        return original_run(command, **kwargs)

    monkeypatch.setattr(executor, "_run", interrupted)
    result = executor.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True)
    outcome = _load(installation)

    assert result.state is LocalFlashState.FAILED
    assert outcome.matches_result(result)
    assert not outcome.actions("failed")
    assert len(outcome.actions("uncertain")) == 1
    assert outcome.actions("uncertain")[0].target == "super"
    assert outcome.actions("unattempted")[0].index > outcome.actions("uncertain")[0].index
    assert "uncertain in-flight step" in outcome.recovery_summary()


def test_restart_rehydrates_sealed_inflight_ledger_instead_of_zero_of_zero(installation):
    _executor, _plan, completed = _execute(installation)
    document = _document(completed.receipt_path)
    document["state"] = "command-in-flight"
    document["results"] = document["results"][:5]
    document["in_flight_step"] = 5
    document["phone_change_attempted"] = True
    document["phone_state_uncertain"] = True
    document["reboot_requested"] = False
    document["android_arrival_verified"] = False
    document.pop("completed_at")
    document.pop("summary")
    _save(completed.receipt_path, document)

    outcome = _load(installation)

    assert outcome.state == "attention" and outcome.result is None
    assert outcome.device_key == "" and outcome.product == ""
    assert outcome.operation_device_key == installation.flash.privacy.pseudonym(
        installation.phone.serial
    )
    assert outcome.operation_product == "popsicle"
    assert outcome.matches_operation_device(
        installation.flash.privacy, installation.phone.device()
    )
    assert outcome.completed_count == 5
    assert outcome.expected_count == 52
    assert tuple(item.index for item in outcome.actions("completed")) == tuple(range(5))
    assert tuple(item.index for item in outcome.actions("uncertain")) == (5,)
    assert tuple(item.index for item in outcome.actions("unattempted")) == tuple(range(6, 52))
    assert "phone outcome is unconfirmed" in outcome.summary


def test_touching_old_success_cannot_hide_later_failed_installation(installation):
    _executor, _plan, old = _execute(installation)
    installation.phone.fail_partition = "abl_a"
    _executor, _plan, failed = _execute(installation)
    touched = failed.receipt_path.stat().st_mtime_ns + 10_000_000_000
    os.utime(old.receipt_path, ns=(touched, touched))
    outcome = _load(installation)
    assert outcome.state == "failed"
    assert outcome.result == failed
    assert outcome.receipt_path == failed.receipt_path


def test_later_valid_attempt_supersedes_older_sealed_interruption_despite_mtime(installation):
    executor = SourceInstallationExecutor(installation.source, installation.flash, installation.adb)
    plan = executor.inspect(installation.phone.device(), installation.recipe(reboot=False))
    old = executor.root / f"{plan.plan_id}.json"
    _save(old, executor._journal(plan))
    _executor, _plan, completed = _execute(installation)
    touched = completed.receipt_path.stat().st_mtime_ns + 10_000_000_000
    os.utime(old, ns=(touched, touched))
    outcome = _load(installation)
    assert outcome.state == "completed"
    assert outcome.result == completed


def test_touching_old_success_cannot_hide_later_sealed_interruption(installation):
    executor, _plan, old = _execute(installation)
    plan = executor.inspect(installation.phone.device(), installation.recipe(reboot=False))
    interrupted = executor.root / f"{plan.plan_id}.json"
    _save(interrupted, executor._journal(plan))
    touched = interrupted.stat().st_mtime_ns + 10_000_000_000
    os.utime(old.receipt_path, ns=(touched, touched))
    outcome = _load(installation)
    assert outcome.state == "attention"
    assert outcome.receipt_path == interrupted
    assert outcome.result is None


def test_cancelled_before_first_command_preserves_exact_nonmutating_result(installation):
    _executor, _plan, result = _execute(installation, cancel=True)
    assert result.state is LocalFlashState.CANCELLED
    outcome = _load(installation)
    assert outcome.state == "cancelled"
    assert outcome.result == result
    assert not outcome.result.phone_change_attempted
    assert outcome.completed_count == 0


@pytest.mark.parametrize("state", ["preparing", "staging", "prepared", "command-in-flight"])
def test_newer_interrupted_record_never_falls_back_to_older_success(installation, state):
    executor, _plan, old = _execute(installation)
    plan = executor.inspect(installation.phone.device(), installation.recipe(reboot=False))
    document = executor._journal(plan)
    document["state"] = state
    newer = executor.root / f"{plan.plan_id}.json"
    _save(newer, document, seal=state != "preparing")
    os.utime(
        newer,
        ns=(
            old.receipt_path.stat().st_mtime_ns + 1_000_000,
            old.receipt_path.stat().st_mtime_ns + 1_000_000,
        ),
    )
    outcome = _load(installation)
    assert outcome.state == "attention"
    assert outcome.project_id == installation.project_id
    assert outcome.receipt_path == newer
    assert outcome.result is None
    assert outcome.device_key == ""
    assert "unconfirmed" in outcome.summary
    if state == "preparing":
        assert outcome.operation_device_key == ""
        assert not outcome.matches_operation_device(
            installation.flash.privacy, installation.phone.device()
        )
        assert "No verified ordered action ledger" in outcome.recovery_summary()
    else:
        assert outcome.operation_device_key == installation.flash.privacy.pseudonym(
            installation.phone.serial
        )
        assert outcome.matches_operation_device(
            installation.flash.privacy, installation.phone.device()
        )
        assert outcome.action_evidence


@pytest.mark.parametrize(
    "mutation",
    [
        "digest",
        "source",
        "success-count",
        "ordered-command",
        "flags",
        "snapshot",
        "timestamp",
        "types",
    ],
)
def test_tampered_latest_record_does_not_rehydrate_or_expose_older_success(installation, mutation):
    _execute(installation)
    _executor, _plan, current = _execute(installation)
    document = _document(current.receipt_path)
    if mutation == "digest":
        document["summary"] += " altered"
        current.receipt_path.write_text(json.dumps(document))
    elif mutation == "source":
        document["source_sha256"] = "f" * 64
        current.receipt_path.write_text(json.dumps(document))
    else:
        if mutation == "success-count":
            document["results"].pop()
        elif mutation == "ordered-command":
            document["results"][1]["command"][-2] = "persist"
        elif mutation == "flags":
            document["boot_verified"] = True
        elif mutation == "snapshot":
            document["image_snapshots"][0]["relative_path"] = "../../outside.img"
        elif mutation == "timestamp":
            document["results"][0]["started_at"] = "2099-01-01T00:00:00+00:00"
        elif mutation == "types":
            document["results"][0]["returncode"] = False
        _save(current.receipt_path, document)
    outcome = _load(installation)
    assert outcome.state == "attention"
    assert outcome.result is None
    assert outcome.receipt_path == current.receipt_path


def test_unsafe_newer_json_symlink_suppresses_older_success(installation, tmp_path):
    executor, _plan, _result = _execute(installation)
    unrelated = tmp_path / "outside-record"
    unrelated.write_text("{}")
    try:
        (executor.root / ("f" * 32 + ".json")).symlink_to(unrelated)
    except OSError as exc:
        if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows runner lacks the privilege to create this real symlink fixture")
        raise
    assert _load(installation).state == "attention"
    assert _load(installation).result is None


def test_different_current_project_source_does_not_show_previous_installation(
    installation, monkeypatch
):
    _execute(installation)
    from dataclasses import replace

    original_get = installation.source.store.get
    monkeypatch.setattr(
        installation.source.store,
        "get",
        lambda project_id: replace(
            original_get(project_id),
            original=replace(original_get(project_id).original, sha256="f" * 64),
        ),
    )
    assert _load(installation) is None


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def utc(self):
        return datetime(2026, 9, 5, tzinfo=UTC) + timedelta(seconds=self.value)


def _boot(fixture, result, *, stable=False):
    fixture.phone.mode = "android"
    clock = Clock()
    service = LocalBootService(
        fixture.flash, fixture.adb, monotonic_clock=clock, utc_clock=clock.utc
    )
    session = service.begin(fixture.phone.device(), flash_result=result)
    if stable:
        for moment in range(0, 61, 5):
            clock.value = float(moment)
            fixture.phone.seconds = float(moment)
            report = service.observe(session)
        assert report.status is LocalBootStatus.STABLE
    else:
        report = service.stop(session)
    return service, session, report


def test_separate_cancelled_boot_record_is_linked_without_rerunning_installation(installation):
    _executor, _plan, result = _execute(installation)
    calls = len(installation.phone.changes)
    _service, _session, report = _boot(installation, result)
    outcome = _load(installation)
    assert outcome.boot_receipt_path == report.receipt_path
    assert "stopped" in outcome.boot_status
    assert outcome.result == result
    assert len(installation.phone.changes) == calls


def test_real_recorded_stable_boot_is_historical_and_keeps_installation_unverified(installation):
    _executor, _plan, result = _execute(installation)
    _service, _session, report = _boot(installation, result, stable=True)
    outcome = _load(installation)
    assert "Historical Android boot observed" in outcome.boot_status
    assert outcome.boot_receipt_path == report.receipt_path
    assert outcome.result.boot_verified is False


def test_new_boot_monitor_supersedes_old_stable_record(installation):
    _executor, _plan, result = _execute(installation)
    _boot(installation, result, stable=True)
    service = LocalBootService(installation.flash, installation.adb)
    service.begin(installation.phone.device(), flash_result=result)
    assert "waiting" in _load(installation).boot_status


@pytest.mark.parametrize("status", ["waiting", "attention"])
def test_touching_old_stable_record_cannot_hide_later_boot_session(installation, status):
    _executor, _plan, result = _execute(installation)
    _service, _session, old = _boot(installation, result, stable=True)
    clock = Clock()
    clock.value = 120.0
    installation.phone.seconds = 120.0
    service = LocalBootService(
        installation.flash, installation.adb, monotonic_clock=clock, utc_clock=clock.utc
    )
    session = service.begin(installation.phone.device(), flash_result=result)
    latest_path = (
        installation.flash.workspace / "guardian" / "local-boot" / f"{session.session_id}.json"
    )
    if status == "attention":
        installation.phone.mode = "bootloader"
        latest_path = service.observe(session).receipt_path
    touched = latest_path.stat().st_mtime_ns + 10_000_000_000
    os.utime(old.receipt_path, ns=(touched, touched))
    outcome = _load(installation)
    assert outcome.boot_receipt_path == latest_path
    assert status in outcome.boot_status
    assert "stable" not in outcome.boot_status
    assert "boot observed" not in outcome.boot_status


@pytest.mark.parametrize("mutation", ["digest", "binding", "sample", "health", "window"])
def test_invalid_newest_boot_record_does_not_display_old_stable_success(installation, mutation):
    _executor, _plan, result = _execute(installation)
    _boot(installation, result, stable=True)
    _service, _session, latest = _boot(installation, result, stable=True)
    document = _document(latest.receipt_path)
    if mutation in {"digest", "binding"}:
        if mutation == "digest":
            document["summary"] += " altered"
        else:
            document["flash_binding"]["record_digest"] = "f" * 64
        latest.receipt_path.write_text(json.dumps(document))
    else:
        if mutation == "sample":
            document["samples"][-1]["uptime_seconds"] = 0
        elif mutation == "health":
            document["subsystems_verified"] = True
        elif mutation == "window":
            document["samples"] = document["samples"][-2:]
            document["sample_count"] = 2
        _save(latest.receipt_path, document)
    outcome = _load(installation)
    assert outcome.state == "completed"
    assert "needs review" in outcome.boot_status
    assert "observed" not in outcome.boot_status
