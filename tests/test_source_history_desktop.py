"""Saved-installation desktop follow-up stays read-only and exact-phone bound."""

from __future__ import annotations

import json
import os
import zipfile
from dataclasses import replace
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest

from romverse.guardian.source_installation import SourceInstallationExecutor
from romverse.rom.source_installation_history import (
    _digest,
    load_latest_source_installation,
)
from romverse.ui.guided_mission import GuidedBuildMission
from romverse.ui.source_installation_history import SourceInstallationHistoryDialog
from tests.test_source_installation_integration import installation as installation
from tests.test_source_installation_integration import installation_desktop as installation_desktop


@pytest.fixture
def saved_history(installation_desktop, monkeypatch, request):
    app, window, context = installation_desktop
    state = getattr(request, "param", "completed")
    if state == "failed":
        context.phone.fail_partition = "super"
    executor = SourceInstallationExecutor(context.source, context.flash, context.adb)
    recipe = context.recipe()
    plan = executor.inspect(context.phone.device(), recipe)
    result = executor.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True)
    assert result.state == state
    window._observed_devices = [context.phone.device()]
    window.rom_studio.set_devices([context.phone.device()])
    outcome = load_latest_source_installation(context.source.store, context.project_id)
    assert outcome is not None and outcome.result is not None
    calls = tuple(context.phone.calls)
    changes = tuple(context.phone.changes)

    def no_installation(*_args, **_kwargs):
        pytest.fail("A historical follow-up tried to inspect or execute a fresh installation")

    monkeypatch.setattr(SourceInstallationExecutor, "inspect", no_installation)
    monkeypatch.setattr(SourceInstallationExecutor, "execute", no_installation)
    return app, window, context, outcome, calls, changes


def _click(widget):
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)


def _seal_interrupted_command(path, *, completed_count=5):
    document = json.loads(path.read_text())
    document["state"] = "command-in-flight"
    document["results"] = document["results"][:completed_count]
    document["in_flight_step"] = completed_count
    document["phone_change_attempted"] = True
    document["phone_state_uncertain"] = True
    document["reboot_requested"] = False
    document["android_arrival_verified"] = False
    document.pop("completed_at")
    document.pop("summary")
    document.pop("record_digest")
    document["record_digest"] = _digest(document)
    path.write_text(json.dumps(document))


def _open(saved, action):
    app, window, context, outcome, _calls, _changes = saved
    dialogs = []
    errors = []

    def interact():
        dialog = app.activeModalWidget()
        try:
            assert isinstance(dialog, SourceInstallationHistoryDialog), type(dialog)
            assert window._local_flash_dialog is dialog
            dialogs.append(dialog)
            action(dialog)
        except BaseException as exc:
            errors.append(exc)
            if dialog is not None:
                dialog.reject()

    QTimer.singleShot(0, interact)
    assert window.rom_studio._request_source_installation_history(
        context.project_id, outcome.source_sha256
    )
    if errors:
        raise errors[0]
    assert len(dialogs) == 1
    assert window._local_flash_dialog is None
    return dialogs[0]


def test_real_guided_source_context_opens_saved_results_and_close_sends_no_commands(saved_history):
    _app, window, context, outcome, calls, changes = saved_history
    evidence = window.rom_studio.guided_context()
    assert evidence.source_installation_state == "completed"
    assert evidence.source_installation_completed_count == 53
    assert evidence.source_installation_expected_count == 53
    assert not evidence.first_boot_verified

    def close(dialog):
        assert dialog.outcome.receipt_path == outcome.receipt_path
        assert dialog.outcome.historical
        assert not dialog.outcome.current_artifact_bytes_verified
        assert "HISTORICAL" in dialog.review.toPlainText()
        assert "not fresh" in dialog.boundary.text()
        for button in (dialog.flash_button, dialog.review_button, dialog.mode_button):
            assert button.isHidden() and not button.isEnabled()
        assert not dialog.monitoring
        _click(dialog.close_button)

    _open(saved_history, close)
    assert tuple(context.phone.calls) == calls
    assert tuple(context.phone.changes) == changes


def test_matching_phone_boot_check_links_saved_installation_without_reinstalling(saved_history):
    _app, window, context, outcome, _calls, changes = saved_history
    original = outcome.receipt_path.read_bytes()
    other = replace(context.phone.device(), serial="UNRELATED-HISTORY-PHONE")
    window._observed_devices = [other, context.phone.device()]
    reports = []

    def check(dialog):
        assert dialog._selected_device().serial == context.phone.serial
        assert dialog.boot_button.isEnabled()
        _click(dialog.boot_button)
        assert dialog.boot_report.status == "settling"
        assert dialog.monitoring
        for _ in range(12):
            dialog.boot_timer.stop()
            context.phone.seconds += 5
            dialog._poll_boot()
        assert dialog.boot_report.status == "stable", dialog.status.text()
        assert dialog.boot_report.elapsed_seconds == 60
        assert not dialog.result.boot_verified
        reports.append(dialog.boot_report)
        _click(dialog.close_button)

    _open(saved_history, check)
    assert tuple(context.phone.changes) == changes
    assert outcome.receipt_path.read_bytes() == original
    document = json.loads(reports[0].receipt_path.read_text())
    assert (
        document["flash_binding"]["relative_path"]
        == outcome.receipt_path.relative_to(context.source.store.workspace).as_posix()
    )
    assert document["flash_binding"]["device_key"] == outcome.device_key
    assert document["readback_verified"] is False
    updated = load_latest_source_installation(context.source.store, context.project_id)
    assert updated.boot_receipt_path == reports[0].receipt_path
    assert updated.boot_status == "Historical Android boot observed · subsystem checks pending"


@pytest.mark.parametrize("missing", ["adb", "fastboot", "both"])
def test_missing_platform_tools_do_not_hide_saved_history(saved_history, missing):
    _app, window, context, _outcome, calls, changes = saved_history
    if missing in {"adb", "both"}:
        window._device_adb_executable = None
    if missing in {"fastboot", "both"}:
        window._device_fastboot_executable = None

    def view(dialog):
        assert "HISTORICAL" in dialog.review.toPlainText()
        assert dialog.recovery_button.isEnabled()
        assert not dialog.boot_button.isEnabled()
        _click(dialog.close_button)

    _open(saved_history, view)
    assert tuple(context.phone.calls) == calls
    assert tuple(context.phone.changes) == changes


@pytest.mark.parametrize("drift", ["project", "source", "project-worker"])
def test_stale_context_cannot_dispatch_saved_result_for_changed_selection(
    saved_history, drift, tmp_path
):
    _app, window, context, outcome, calls, changes = saved_history
    project = window.rom_studio.current_project
    old_worker = window.rom_studio.worker
    try:
        if drift == "project":
            window.rom_studio.current_project = context.source.store.create(
                "Unrelated history project"
            )
        elif drift == "source":
            replacement = tmp_path / "different-protected-source.zip"
            with zipfile.ZipFile(replacement, "w") as archive:
                archive.writestr("README.txt", "Different synthetic source; no executable images")
            alternate = context.source.store.import_original(
                context.source.store.create("Different source association").project_id, replacement
            )
            context.source.store._save(replace(project, original=alternate.original))
        else:
            window.rom_studio.worker = object()
        assert not window.rom_studio._request_source_installation_history(
            context.project_id, outcome.source_sha256
        )
        assert window._local_flash_dialog is None
    finally:
        window.rom_studio.worker = old_worker
        window.rom_studio.current_project = project
    assert tuple(context.phone.calls) == calls
    assert tuple(context.phone.changes) == changes


@pytest.mark.parametrize("saved_history", ["failed"], indirect=True)
def test_closing_failed_saved_result_does_not_retry_or_open_an_unrequested_incident(
    saved_history, monkeypatch
):
    _app, window, context, _outcome, calls, changes = saved_history
    incidents = []
    routes = []
    monkeypatch.setattr(window, "_navigate_route", routes.append)
    monkeypatch.setattr(
        window.repair_center,
        "open_recovery_incident",
        lambda *args, **kwargs: incidents.append((args, kwargs)),
    )
    _open(saved_history, lambda dialog: _click(dialog.close_button))
    assert incidents == []
    assert routes == []
    assert tuple(context.phone.calls) == calls
    assert tuple(context.phone.changes) == changes


@pytest.mark.parametrize(
    "busy", ["scanning", "apk", "backup", "repair", "terminal", "dialog", "pending"]
)
def test_main_window_busy_guard_blocks_history_handoff_without_commands(saved_history, busy):
    _app, window, context, _outcome, calls, changes = saved_history
    target, attribute = {
        "scanning": (window, "scanning"),
        "apk": (window.apk_installer, "active_worker"),
        "backup": (window.backup_center, "media_backup_worker"),
        "repair": (window.repair_center, "host_repair_worker"),
        "terminal": (window.terminal_center, "_worker"),
        "dialog": (window, "_local_flash_dialog"),
        "pending": (window, "_expert_flash_pending"),
    }[busy]
    old = getattr(target, attribute)
    try:
        setattr(target, attribute, True if busy in {"scanning", "pending"} else object())
        window._open_source_installation_history(context.project_id)
        assert getattr(target, attribute) is not None
    finally:
        setattr(target, attribute, old)
    assert tuple(context.phone.calls) == calls
    assert tuple(context.phone.changes) == changes


@pytest.mark.parametrize("saved_history", ["completed", "failed"], indirect=True)
@pytest.mark.parametrize("presence", ["absent", "other-phone"])
def test_recovery_without_exact_phone_never_creates_incident_for_other_phone(
    saved_history, presence, monkeypatch
):
    _app, window, context, _outcome, calls, changes = saved_history
    other = replace(context.phone.device(), serial="ANOTHER-USB-PHONE")
    window._observed_devices = [] if presence == "absent" else [other]
    routes = []
    incidents = []
    monkeypatch.setattr(window, "_navigate_route", routes.append)
    monkeypatch.setattr(
        window.repair_center,
        "open_recovery_incident",
        lambda *args, **kwargs: incidents.append((args, kwargs)),
    )

    def recover(dialog):
        assert not dialog.boot_button.isEnabled()
        _click(dialog.recovery_button)
        assert dialog.recovery_requested
        assert dialog.last_attempt_device is None
        assert dialog.last_flash_device is None

    _open(saved_history, recover)
    assert "recovery_bay" in routes
    assert incidents == []
    assert window._pending_local_flash_recovery is None
    assert tuple(context.phone.calls) == calls
    assert tuple(context.phone.changes) == changes


@pytest.mark.parametrize("saved_history", ["failed"], indirect=True)
def test_failed_history_recovery_with_exact_phone_keeps_project_and_device_attribution(
    saved_history, monkeypatch
):
    _app, window, context, outcome, calls, changes = saved_history
    incidents = []
    monkeypatch.setattr(
        window.repair_center,
        "open_recovery_incident",
        lambda *args, **kwargs: incidents.append((args, kwargs)),
    )
    _open(saved_history, lambda dialog: _click(dialog.recovery_button))
    assert len(incidents) == 1
    assert incidents[0][1]["project_id"] == context.project_id
    assert incidents[0][1]["target_device"].serial == context.phone.serial
    assert outcome.source_sha256 == context.source.store.get(context.project_id).original.sha256
    assert tuple(context.phone.calls) == calls
    assert tuple(context.phone.changes) == changes


def test_restart_interruption_goes_directly_to_exact_phone_diagnosis_without_retry(
    installation_desktop, monkeypatch
):
    _app, window, context = installation_desktop
    executor = SourceInstallationExecutor(context.source, context.flash, context.adb)
    plan = executor.inspect(context.phone.device(), context.recipe())
    completed = executor.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True)
    _seal_interrupted_command(completed.receipt_path)
    window._observed_devices = [context.phone.device()]
    window.rom_studio.set_devices([context.phone.device()])
    calls = tuple(context.phone.calls)
    changes = tuple(context.phone.changes)
    incidents = []
    routes = []
    source_sha256 = context.source.store.get(context.project_id).original.sha256
    monkeypatch.setattr(
        window.repair_center,
        "open_recovery_incident",
        lambda *args, **kwargs: incidents.append((args, kwargs)),
    )
    monkeypatch.setattr(window, "_navigate_route", routes.append)

    assert window.rom_studio._request_source_installation_recovery(
        context.project_id, source_sha256
    )

    assert len(incidents) == 1
    _args, incident = incidents[0]
    assert incident["project_id"] == context.project_id
    assert incident["target_device"].serial == context.phone.serial
    assert incident["allow_current_device_fallback"] is False
    outcome = load_latest_source_installation(context.source.store, context.project_id)
    assert incident["expected_device_key"] == outcome.operation_device_key
    assert incident["failure"].phase == "source-installation"
    assert incident["failure"].finding_ids == ("source.installation.command_outcome_unknown",)
    assert "uncertain in-flight step 6" in incident["message"]
    assert "exact operation target is attached" in incident["message"]
    assert routes == ["recovery_bay"]
    assert tuple(context.phone.calls) == calls
    assert tuple(context.phone.changes) == changes


def test_opening_genesis_automatically_diagnoses_sealed_interruption_without_retry(
    installation_desktop, monkeypatch
):
    app, window, context = installation_desktop
    executor = SourceInstallationExecutor(context.source, context.flash, context.adb)
    plan = executor.inspect(context.phone.device(), context.recipe())
    completed = executor.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True)
    _seal_interrupted_command(completed.receipt_path)
    outcome = load_latest_source_installation(context.source.store, context.project_id)
    window._observed_devices = [context.phone.device()]
    window.rom_studio.set_devices([context.phone.device()])
    calls = tuple(context.phone.calls)
    changes = tuple(context.phone.changes)
    incidents = []
    routes = []
    monkeypatch.setattr(
        window.repair_center,
        "open_recovery_incident",
        lambda *args, **kwargs: incidents.append((args, kwargs)),
    )
    monkeypatch.setattr(window, "_navigate_route", routes.append)

    mission = GuidedBuildMission(window.rom_studio)
    mission.show()
    assert "Checking what happened" in mission.status_text.text()
    app.processEvents()
    app.processEvents()

    assert len(incidents) == 1
    assert incidents[0][1]["project_id"] == context.project_id
    assert incidents[0][1]["expected_device_key"] == outcome.operation_device_key
    assert incidents[0][1]["target_device"].serial == context.phone.serial
    assert routes == ["recovery_bay"]
    assert not mission.isVisible()
    assert tuple(context.phone.calls) == calls
    assert tuple(context.phone.changes) == changes


@pytest.mark.parametrize("presence", ["absent", "unrelated"])
def test_restart_interruption_never_borrows_another_phone_for_diagnosis(
    installation_desktop, monkeypatch, presence
):
    _app, window, context = installation_desktop
    executor = SourceInstallationExecutor(context.source, context.flash, context.adb)
    plan = executor.inspect(context.phone.device(), context.recipe())
    completed = executor.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True)
    _seal_interrupted_command(completed.receipt_path)
    outcome = load_latest_source_installation(context.source.store, context.project_id)
    other = replace(context.phone.device(), serial="UNRELATED-RESTART-PHONE")
    window._observed_devices = [] if presence == "absent" else [other]
    window.rom_studio.set_devices(window._observed_devices)
    calls = tuple(context.phone.calls)
    changes = tuple(context.phone.changes)
    incidents = []
    source_sha256 = context.source.store.get(context.project_id).original.sha256
    monkeypatch.setattr(
        window.repair_center,
        "open_recovery_incident",
        lambda *args, **kwargs: incidents.append((args, kwargs)),
    )

    window._open_source_installation_recovery(context.project_id, source_sha256)

    assert len(incidents) == 1
    incident = incidents[0][1]
    assert incident["project_id"] == context.project_id
    assert incident["target_device"] is None
    assert incident["allow_current_device_fallback"] is False
    assert incident["expected_device_key"] == outcome.operation_device_key
    assert "not currently verified as attached" in incident["message"]
    assert tuple(context.phone.calls) == calls
    assert tuple(context.phone.changes) == changes


def test_same_model_phone_cannot_capture_targetless_incident_before_original_returns(
    installation_desktop,
):
    _app, window, context = installation_desktop
    executor = SourceInstallationExecutor(context.source, context.flash, context.adb)
    plan = executor.inspect(context.phone.device(), context.recipe())
    completed = executor.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True)
    _seal_interrupted_command(completed.receipt_path)
    outcome = load_latest_source_installation(context.source.store, context.project_id)
    source_sha256 = context.source.store.get(context.project_id).original.sha256
    original = context.phone.device()
    other = replace(original, serial="SAME-MODEL-DIFFERENT-PHYSICAL-PHONE")
    window._observed_devices = [other]
    window.rom_studio.set_devices([other])
    calls = tuple(context.phone.calls)
    changes = tuple(context.phone.changes)

    window._open_source_installation_recovery(context.project_id, source_sha256)

    incident = window.repair_center.autopilot_incident
    assert incident is not None
    incident_id = incident.incident_id
    assert incident.device_key == outcome.operation_device_key
    assert incident.mode == "disconnected"
    window.repair_center.set_devices([other])
    assert window.repair_center.autopilot_incident.incident_id == incident_id
    assert window.repair_center.autopilot_incident.mode == "disconnected"
    assert "waiting for the phone involved" in window.repair_center.digest.text()

    window.repair_center.set_devices([original])
    rebound = window.repair_center.autopilot_incident
    assert rebound.incident_id == incident_id
    assert rebound.device_key == outcome.operation_device_key
    assert rebound.mode == "adb"
    assert len(window.repair_center.autopilot_service.list_recent()) == 1
    assert tuple(context.phone.calls) == calls
    assert tuple(context.phone.changes) == changes


def test_history_recovery_for_interruption_uses_the_direct_diagnosis_handoff(
    installation_desktop, monkeypatch
):
    _app, window, context = installation_desktop
    executor = SourceInstallationExecutor(context.source, context.flash, context.adb)
    plan = executor.inspect(context.phone.device(), context.recipe())
    completed = executor.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True)
    _seal_interrupted_command(completed.receipt_path)
    outcome = load_latest_source_installation(context.source.store, context.project_id)
    source_sha256 = context.source.store.get(context.project_id).original.sha256
    requested = []
    monkeypatch.setattr(
        window,
        "_open_source_installation_recovery",
        lambda project_id, source_sha256: requested.append((project_id, source_sha256)),
    )
    dialog = SimpleNamespace(
        result=None,
        preparation=outcome,
        last_attempt_device=context.phone.device(),
        last_flash_device=context.phone.device(),
        boot_report=None,
        boot_error="",
        execution_error="",
        transition_error="",
        transition_attempt_device=None,
        recovery_requested=True,
    )

    window._finish_expert_dialog(dialog)

    assert requested == [(context.project_id, source_sha256)]
    assert window._pending_local_flash_recovery is None


def test_restart_diagnosis_waits_for_active_scan_then_opens_once(installation_desktop, monkeypatch):
    _app, window, context = installation_desktop
    executor = SourceInstallationExecutor(context.source, context.flash, context.adb)
    plan = executor.inspect(context.phone.device(), context.recipe())
    completed = executor.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True)
    _seal_interrupted_command(completed.receipt_path)
    source_sha256 = context.source.store.get(context.project_id).original.sha256
    window._observed_devices = [context.phone.device()]
    incidents = []
    monkeypatch.setattr(
        window.repair_center,
        "open_recovery_incident",
        lambda *args, **kwargs: incidents.append((args, kwargs)),
    )
    window.scanning = True

    window._open_source_installation_recovery(context.project_id, source_sha256)

    assert window._pending_source_installation_recovery == (
        context.project_id,
        source_sha256,
    )
    assert incidents == []
    window.scanning = False
    window._resume_pending_source_installation_recovery()
    window._resume_pending_source_installation_recovery()
    assert len(incidents) == 1
    assert incidents[0][1]["target_device"].serial == context.phone.serial
    assert window._pending_source_installation_recovery is None


def test_direct_restart_diagnosis_rejects_a_stale_loaded_source_binding(
    installation_desktop, monkeypatch
):
    _app, window, context = installation_desktop
    executor = SourceInstallationExecutor(context.source, context.flash, context.adb)
    plan = executor.inspect(context.phone.device(), context.recipe())
    completed = executor.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True)
    _seal_interrupted_command(completed.receipt_path)
    outcome = load_latest_source_installation(context.source.store, context.project_id)
    source_sha256 = context.source.store.get(context.project_id).original.sha256
    monkeypatch.setattr(
        "romverse.rom.source_installation_history.load_latest_source_installation",
        lambda *_args, **_kwargs: replace(outcome, source_sha256="f" * 64),
    )
    incidents = []
    monkeypatch.setattr(
        window.repair_center,
        "open_recovery_incident",
        lambda *args, **kwargs: incidents.append((args, kwargs)),
    )

    window._open_source_installation_recovery(context.project_id, source_sha256)

    assert incidents == []
    assert "no longer matches" in window.rom_studio.operation_status.text()
