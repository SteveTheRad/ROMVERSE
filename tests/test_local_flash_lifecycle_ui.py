"""User journeys through real Qt controls with inert device-service substitutes."""

from __future__ import annotations

import os
from collections import deque
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from romverse.core.activity import ActivityStore
from romverse.device.models import AndroidDevice, DeviceState
from romverse.guardian.local_flash import LocalFlashResult, LocalFlashState
from romverse.guardian.local_transition import (
    LocalTransitionPlan,
    LocalTransitionResult,
    LocalTransitionTarget,
)
from romverse.repair.autopilot import RecoveryTrigger
from romverse.rom.local_boot import LocalBootReport, LocalBootSession, LocalBootStatus
from romverse.ui.local_flash import LocalFlashDialog
from romverse.ui.main_window import MainWindow
from tests.test_local_flash_ui import _plan


def _report(
    tmp_path: Path,
    status: LocalBootStatus,
    device: AndroidDevice | None,
) -> LocalBootReport:
    terminal = status in {
        LocalBootStatus.STABLE,
        LocalBootStatus.ATTENTION,
        LocalBootStatus.CANCELLED,
    }
    boot_observed = status in {LocalBootStatus.SETTLING, LocalBootStatus.STABLE}
    if boot_observed and device is not None:
        device = replace(device, state=DeviceState.DEVICE, boot_completed=True)
    return LocalBootReport(
        status=status,
        summary=f"Inert UI observation: {status.value}. Readback and subsystems remain unverified.",
        receipt_path=tmp_path / f"inert-boot-{status.value}.json",
        sample_count=14 if status is LocalBootStatus.STABLE else 1,
        elapsed_seconds=65 if status is LocalBootStatus.STABLE else 5,
        boot_observed=boot_observed,
        terminal=terminal,
        failure_kind="boot-timeout" if status is LocalBootStatus.ATTENTION else "",
        latest_device=device,
    )


class InertBootService:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.begin_calls = []
        self.observe_calls = []
        self.stop_calls = []
        self.reports = deque()

    def begin(self, device, flash_result=None):
        self.begin_calls.append((device, flash_result))
        return LocalBootSession(
            f"inert-session-{len(self.begin_calls)}", device.display_name, device.masked_serial()
        )

    def observe(self, session):
        self.observe_calls.append(session)
        return self.reports.popleft()

    def stop(self, session):
        self.stop_calls.append(session)
        return _report(self.tmp_path, LocalBootStatus.CANCELLED, None)


class InertTransitionService:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.inspect_calls = []
        self.execute_calls = []

    def inspect(self, device, target):
        self.inspect_calls.append((device, target))
        return LocalTransitionPlan(
            plan_digest="d" * 64,
            plan_id="inert-transition",
            created_at="2026-09-05T00:00:00+00:00",
            expires_at="2026-09-05T00:02:00+00:00",
            device_name=device.display_name,
            masked_serial=device.masked_serial(),
            source_mode=device.state.value,
            target=target,
            warnings=("Transport arrival is not Android boot verification.",),
            command=("inert-reboot-fixture",),
            device_key="inert-key",
            tools=(),
            source_device=device,
        )

    def execute(self, plan, *, accepted_digest, risk_accepted, should_cancel):
        self.execute_calls.append((plan, accepted_digest, risk_accepted, should_cancel()))
        state = {
            LocalTransitionTarget.ANDROID: DeviceState.DEVICE,
            LocalTransitionTarget.BOOTLOADER: DeviceState.BOOTLOADER,
            LocalTransitionTarget.FASTBOOTD: DeviceState.FASTBOOTD,
        }[plan.target]
        return LocalTransitionResult(
            LocalFlashState.COMPLETED,
            "Inert transport arrival observed; Android boot remains unverified.",
            True,
            self.tmp_path / "inert-transition.json",
            observed_device=replace(plan.source_device, state=state, boot_completed=False),
            arrival_verified=True,
            boot_verified=False,
        )


@pytest.fixture
def lifecycle_dialog(tmp_path: Path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    device = AndroidDevice(
        "inert-phone-0001",
        DeviceState.FASTBOOT,
        manufacturer="Example",
        model="Phone One",
        product="phone-one",
    )
    other = AndroidDevice("inert-phone-0002", DeviceState.FASTBOOT, model="Phone Two")
    boot = InertBootService(tmp_path)
    started = []
    flash = SimpleNamespace(
        inspect=lambda selected, *_args: replace(
            _plan(tmp_path),
            serial=selected.serial,
            product=selected.product,
            device_name=selected.display_name,
            masked_serial=selected.masked_serial(),
        )
    )
    monkeypatch.setattr("romverse.ui.local_flash.start_background", started.append)
    dialog = LocalFlashDialog(
        flash,
        (device, other),
        discover=lambda: [device, other],
        boot_service=boot,
        transition_service=InertTransitionService(tmp_path),
    )
    dialog.show()
    app.processEvents()
    yield app, dialog, boot, started, device
    dialog.boot_timer.stop()
    dialog.monitoring = False
    dialog.worker = None
    dialog.close()


def _click(button) -> None:
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)


def _finish_next(app: QApplication, started: list) -> None:
    assert started, "The user action did not schedule its expected background operation"
    started.pop(0).execute()
    app.processEvents()


def _answer_modal(monkeypatch, *, accept: bool, before_answer=None):
    original_exec = QMessageBox.exec
    answers = []

    def execute(question: QMessageBox):
        def answer():
            if before_answer is not None:
                before_answer()
            button = (
                next(
                    item
                    for item in question.buttons()
                    if question.buttonRole(item) is QMessageBox.ButtonRole.AcceptRole
                )
                if accept
                else question.button(QMessageBox.StandardButton.Cancel)
            )
            answers.append(
                (
                    question.isVisible(),
                    question.defaultButton() is question.button(QMessageBox.StandardButton.Cancel),
                )
            )
            _click(button)

        QTimer.singleShot(0, answer)
        return original_exec(question)

    monkeypatch.setattr(QMessageBox, "exec", execute)
    return answers


def test_completed_image_write_does_not_claim_or_automatically_measure_android_boot(
    lifecycle_dialog,
    tmp_path: Path,
) -> None:
    _app, dialog, boot, started, _device = lifecycle_dialog
    completed = LocalFlashResult(
        LocalFlashState.COMPLETED,
        "Inert write accepted; Android boot is unverified.",
        tmp_path / "inert-flash.json",
        (),
        True,
        True,
    )
    boot_events = []
    dialog.boot_finished.connect(boot_events.append)

    dialog._complete(completed)

    assert dialog.result is completed
    assert not dialog.result.boot_verified
    assert dialog.boot_report is None
    assert not dialog.monitoring
    assert not dialog.boot_timer.isActive()
    assert boot.begin_calls == []
    assert started == []
    assert boot_events == []


def test_boot_polling_locks_competing_actions_and_stop_prevents_late_timer_work(
    lifecycle_dialog,
    tmp_path: Path,
) -> None:
    app, dialog, boot, started, device = lifecycle_dialog
    boot.reports.append(_report(tmp_path, LocalBootStatus.WAITING, device))
    _click(dialog.boot_button)
    _finish_next(app, started)

    assert dialog.worker is None
    assert dialog.monitoring
    assert dialog.boot_timer.isActive()
    for button in (
        dialog.flash_button,
        dialog.mode_button,
        dialog.review_button,
        dialog.refresh_button,
    ):
        assert not button.isEnabled()
        _click(button)
    assert not dialog.target.isEnabled()
    assert started == []

    _click(dialog.cancel_button)
    assert dialog.worker is not None
    assert not dialog.boot_timer.isActive()
    assert dialog.monitoring
    _finish_next(app, started)
    assert len(boot.stop_calls) == 1
    assert not dialog.monitoring
    assert dialog.boot_report.status is LocalBootStatus.CANCELLED

    dialog.boot_timer.timeout.emit()
    app.processEvents()
    assert started == []
    assert len(boot.observe_calls) == 1


@pytest.mark.parametrize("probe_in_flight", [False, True])
def test_closing_boot_check_waits_for_current_probe_and_persists_stop(
    lifecycle_dialog,
    tmp_path: Path,
    probe_in_flight: bool,
) -> None:
    app, dialog, boot, started, device = lifecycle_dialog
    boot.reports.append(_report(tmp_path, LocalBootStatus.WAITING, device))
    _click(dialog.boot_button)
    if not probe_in_flight:
        _finish_next(app, started)
    dialog.close()
    app.processEvents()
    assert dialog.isVisible()
    assert not dialog.boot_timer.isActive()
    assert dialog.worker is not None
    if probe_in_flight:
        _finish_next(app, started)
        assert dialog.isVisible()
        assert dialog.worker is not None
    _finish_next(app, started)

    assert not dialog.isVisible()
    assert not dialog.monitoring
    assert not dialog.boot_timer.isActive()
    assert len(boot.stop_calls) == 1
    assert dialog.boot_report.status is LocalBootStatus.CANCELLED
    dialog.boot_timer.timeout.emit()
    assert started == []


def test_stable_boot_report_is_separate_from_flash_result_and_waits_for_terminal_evidence(
    lifecycle_dialog,
    tmp_path: Path,
) -> None:
    app, dialog, boot, started, device = lifecycle_dialog
    boot.reports.extend(
        (
            _report(tmp_path, LocalBootStatus.SETTLING, device),
            _report(tmp_path, LocalBootStatus.STABLE, device),
        )
    )
    events = []
    dialog.boot_finished.connect(events.append)

    _click(dialog.boot_button)
    _finish_next(app, started)
    assert dialog.monitoring
    assert dialog.boot_report.boot_observed
    assert events == []
    dialog.boot_timer.timeout.emit()
    _finish_next(app, started)

    assert not dialog.monitoring
    assert not dialog.boot_timer.isActive()
    assert len(events) == 1
    assert events[0].status is LocalBootStatus.STABLE
    assert events[0].terminal
    assert dialog.result is None
    assert "not image readback" in dialog.review.toPlainText()


def test_boot_failure_opens_recovery_and_preserves_the_monitored_phone(
    lifecycle_dialog,
    tmp_path: Path,
) -> None:
    app, dialog, boot, started, device = lifecycle_dialog
    boot.reports.append(_report(tmp_path, LocalBootStatus.ATTENTION, device))
    events = []
    dialog.boot_finished.connect(events.append)
    _click(dialog.boot_button)
    # A stale external selection update cannot redefine the existing boot session.
    dialog.target.setCurrentIndex(1)
    _finish_next(app, started)

    assert dialog.boot_device is device
    assert boot.begin_calls[0][0] is device
    assert dialog.recovery_requested
    assert not dialog.isVisible()
    assert not dialog.boot_timer.isActive()
    assert len(events) == 1
    assert events[0].failure_kind == "boot-timeout"


def test_after_stopping_boot_monitor_new_flash_still_has_stop_after_current_write(
    lifecycle_dialog,
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, dialog, boot, started, device = lifecycle_dialog
    boot.reports.append(_report(tmp_path, LocalBootStatus.WAITING, device))
    _click(dialog.boot_button)
    _finish_next(app, started)
    _click(dialog.cancel_button)
    _finish_next(app, started)
    dialog.add_image(tmp_path / "boot.img", "boot_a")
    _click(dialog.review_button)
    _finish_next(app, started)
    answers = _answer_modal(monkeypatch, accept=True)

    _click(dialog.flash_button)

    assert answers == [(True, True)]
    assert len(started) == 1
    assert dialog.cancel_button.isEnabled()
    _click(dialog.cancel_button)
    assert started[0].cancel_requested.is_set()


def test_declining_real_mode_dialog_sends_no_reboot_and_invalidates_image_review(
    lifecycle_dialog,
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, dialog, _boot, started, device = lifecycle_dialog
    dialog.add_image(tmp_path / "boot.img", "boot_a")
    _click(dialog.review_button)
    _finish_next(app, started)
    assert dialog.plan is not None
    answers = _answer_modal(monkeypatch, accept=False)

    _click(dialog.mode_button)
    _finish_next(app, started)

    assert answers == [(True, True)]
    assert dialog.transition_service.inspect_calls == [(device, LocalTransitionTarget.BOOTLOADER)]
    assert dialog.transition_service.execute_calls == []
    assert started == []
    assert dialog.plan is None
    assert not dialog.flash_button.isEnabled()
    assert dialog.transition_result is None


@pytest.mark.parametrize("change", ["phone", "destination"])
def test_mode_confirmation_cannot_dispatch_when_target_changes_in_modal_loop(
    lifecycle_dialog,
    monkeypatch,
    change: str,
) -> None:
    app, dialog, _boot, started, _device = lifecycle_dialog

    def drift():
        (dialog.target if change == "phone" else dialog.mode_target).setCurrentIndex(1)

    answers = _answer_modal(monkeypatch, accept=True, before_answer=drift)
    _click(dialog.mode_button)
    _finish_next(app, started)

    assert answers == [(True, True)]
    assert started == []
    assert dialog.transition_service.execute_calls == []
    assert dialog.transition_attempt_device is None


def test_approved_fastbootd_transition_binds_exact_confirmation_and_observed_device(
    lifecycle_dialog,
    monkeypatch,
) -> None:
    app, dialog, _boot, started, device = lifecycle_dialog
    dialog.mode_target.setCurrentIndex(dialog.mode_target.findData(LocalTransitionTarget.FASTBOOTD))
    answers = _answer_modal(monkeypatch, accept=True)
    _click(dialog.mode_button)
    _finish_next(app, started)
    assert not dialog.boot_button.isEnabled()
    assert not dialog.target.isEnabled()
    assert not dialog.mode_button.isEnabled()
    _finish_next(app, started)

    assert answers == [(True, True)]
    plan, accepted, risk, cancelled = dialog.transition_service.execute_calls[0]
    assert accepted == plan.plan_digest
    assert risk is True
    assert cancelled is False
    assert plan.source_device is device
    assert plan.target is LocalTransitionTarget.FASTBOOTD
    assert dialog.devices[0].serial == device.serial
    assert dialog.devices[0].state is DeviceState.FASTBOOTD
    assert dialog.result is None
    assert dialog.boot_report is None
    assert not dialog.transition_result.boot_verified
    assert not dialog.boot_timer.isActive()


def test_android_mode_arrival_starts_separate_exact_phone_boot_observation(
    lifecycle_dialog,
    monkeypatch,
    tmp_path: Path,
) -> None:
    app, dialog, boot, started, device = lifecycle_dialog
    dialog.mode_target.setCurrentIndex(dialog.mode_target.findData(LocalTransitionTarget.ANDROID))
    boot.reports.append(_report(tmp_path, LocalBootStatus.WAITING, device))
    _answer_modal(monkeypatch, accept=True)
    _click(dialog.mode_button)
    _finish_next(app, started)
    _finish_next(app, started)

    assert dialog.transition_result.arrival_verified
    assert not dialog.transition_result.boot_verified
    assert dialog.boot_report is None
    assert dialog.monitoring
    assert len(started) == 1
    _finish_next(app, started)
    assert boot.begin_calls[0][0].serial == device.serial
    assert dialog.boot_report.status is LocalBootStatus.WAITING
    assert not dialog.boot_report.boot_observed


def test_late_callbacks_from_prior_boot_worker_cannot_replace_new_session(
    lifecycle_dialog,
    tmp_path: Path,
) -> None:
    app, dialog, boot, started, device = lifecycle_dialog
    boot.reports.append(_report(tmp_path, LocalBootStatus.WAITING, device))
    _click(dialog.boot_button)
    previous = started[0]
    _finish_next(app, started)
    _click(dialog.cancel_button)
    _finish_next(app, started)
    dialog.target.setCurrentIndex(1)
    _click(dialog.boot_button)
    current = started[0]

    previous.signals.complete.emit(_report(tmp_path, LocalBootStatus.STABLE, device))
    previous.signals.failed.emit("Late failure from the old worker")
    previous.signals.progress.emit(10, 10, "Late old-worker progress")
    app.processEvents()

    assert dialog.worker is current
    assert dialog.boot_device.serial != device.serial
    assert dialog.boot_report is None
    assert dialog.boot_error == ""
    assert "Late" not in dialog.status.text()


def test_boot_binding_retains_preflash_alias_when_new_rom_changes_product_name(
    lifecycle_dialog, tmp_path: Path
) -> None:
    app, dialog, boot, started, device = lifecycle_dialog
    baseline = replace(device, product="phone-one_global", codename="phone-one")
    observed = replace(
        device, product="phone-one_cn", codename="phone-one", state=DeviceState.DEVICE
    )
    result = LocalFlashResult(
        LocalFlashState.COMPLETED, "Writes complete", tmp_path / "operation.json", (), True, True
    )
    dialog.last_flash_device = baseline
    dialog.result = result
    boot.reports.append(_report(tmp_path, LocalBootStatus.WAITING, observed))

    dialog._start_boot(observed)
    _finish_next(app, started)

    assert boot.begin_calls == [(baseline, result)]
    assert dialog.boot_device is baseline
    assert dialog.devices[0].product == "phone-one_cn"


def test_unsupported_boot_result_stops_monitor_without_enabling_flash(lifecycle_dialog) -> None:
    app, dialog, boot, started, _device = lifecycle_dialog
    boot.reports.append(object())
    _click(dialog.boot_button)
    _finish_next(app, started)

    assert dialog.worker is None
    assert not dialog.monitoring
    assert not dialog.boot_timer.isActive()
    assert dialog.boot_error
    assert dialog.boot_report is None
    assert not dialog.flash_button.isEnabled()


def test_foreign_phone_boot_report_is_rejected_without_success_signal(
    lifecycle_dialog,
    tmp_path: Path,
) -> None:
    app, dialog, boot, started, device = lifecycle_dialog
    boot.reports.append(_report(tmp_path, LocalBootStatus.STABLE, dialog.devices[1]))
    events = []
    dialog.boot_finished.connect(events.append)
    _click(dialog.boot_button)
    _finish_next(app, started)

    assert dialog.boot_device is device
    assert dialog.boot_report is None
    assert dialog.boot_error
    assert not dialog.monitoring
    assert not dialog.boot_timer.isActive()
    assert events == []


@pytest.mark.parametrize(
    "failure_kind,trigger",
    [("reboot_loop", RecoveryTrigger.BOOTLOOP), ("boot-timeout", RecoveryTrigger.BOOT_ATTENTION)],
)
def test_terminal_boot_failure_queues_monitored_phone_recovery_before_fresh_scan(
    tmp_path: Path,
    failure_kind: str,
    trigger: RecoveryTrigger,
) -> None:
    target = AndroidDevice("monitored-phone", DeviceState.UNKNOWN)
    unrelated = AndroidDevice("previously-selected-phone", DeviceState.FASTBOOT)
    report = replace(
        _report(tmp_path, LocalBootStatus.ATTENTION, target),
        failure_kind=failure_kind,
    )
    dialog = SimpleNamespace(
        result=None,
        last_attempt_device=unrelated,
        boot_report=report,
        boot_device=target,
    )
    routes = []
    window = SimpleNamespace(_pending_local_flash_recovery=None, _navigate_route=routes.append)

    MainWindow._finish_expert_dialog(window, dialog)

    assert window._pending_local_flash_recovery == (target, report.summary)
    assert window._pending_local_flash_recovery_trigger is trigger
    assert window._selected_device_serial == target.serial
    assert routes == []


def test_brief_boot_followed_by_terminal_attention_is_not_recorded_as_success(
    tmp_path: Path,
) -> None:
    report = replace(
        _report(tmp_path, LocalBootStatus.ATTENTION, None),
        boot_observed=True,
        failure_kind="reboot_loop",
    )
    activities = []
    window = SimpleNamespace(
        _record_activity=lambda *args, **kwargs: activities.append((args, kwargs)),
        rom_studio=SimpleNamespace(operation_status=SimpleNamespace(setText=lambda _value: None)),
    )

    MainWindow._record_local_boot_result(window, report)

    assert len(activities) == 1
    assert activities[0][0][3] == "attention"


def test_write_mode_and_boot_callbacks_persist_distinct_truthful_activity_history(
    tmp_path: Path,
) -> None:
    store = ActivityStore(tmp_path / "workspace")
    window = SimpleNamespace(
        activity_store=store,
        rom_studio=SimpleNamespace(operation_status=SimpleNamespace(setText=lambda _value: None)),
    )
    window._record_activity = lambda *args, **kwargs: MainWindow._record_activity(
        window, *args, **kwargs
    )
    flash = LocalFlashResult(
        LocalFlashState.COMPLETED,
        "Inert history fixture: write command completed; boot remains unverified.",
        tmp_path / "inert-flash.json",
        (),
        True,
        True,
    )
    mode = LocalTransitionResult(
        LocalFlashState.COMPLETED,
        "Inert history fixture: requested mode observed; boot remains unverified.",
        True,
        tmp_path / "inert-mode.json",
        arrival_verified=True,
    )
    stable = _report(tmp_path, LocalBootStatus.STABLE, None)
    attention = replace(
        _report(tmp_path, LocalBootStatus.ATTENTION, None),
        boot_observed=True,
        failure_kind="reboot_loop",
    )

    MainWindow._record_local_flash_result(window, flash)
    MainWindow._record_local_transition_result(window, mode)
    MainWindow._record_local_boot_result(window, stable)
    MainWindow._record_local_boot_result(window, attention)
    reloaded = ActivityStore(store.workspace).list_recent()

    assert len(reloaded) == 4
    by_detail = {event.detail: event for event in reloaded}
    assert by_detail[flash.summary].outcome == "attention"
    assert "boot unverified" in by_detail[flash.summary].title
    assert by_detail[mode.summary].outcome == "attention"
    assert by_detail[stable.summary].outcome == "success"
    assert "subsystem tests pending" in by_detail[stable.summary].title
    assert by_detail[attention.summary].outcome == "attention"
    assert not flash.boot_verified
    assert not mode.boot_verified


@pytest.mark.parametrize(
    "state,command_completed,monitors",
    [
        (LocalFlashState.FAILED, True, True),
        (LocalFlashState.CANCELLED, True, False),
        (LocalFlashState.REJECTED, False, False),
    ],
)
def test_android_reboot_acknowledgement_can_continue_observation_but_never_overrides_cancel(
    lifecycle_dialog,
    monkeypatch,
    state: LocalFlashState,
    command_completed: bool,
    monitors: bool,
) -> None:
    app, dialog, boot, started, device = lifecycle_dialog
    service = dialog.transition_service
    original_execute = service.execute

    def execute(plan, **kwargs):
        return replace(
            original_execute(plan, **kwargs),
            state=state,
            command_completed=command_completed,
            observed_device=None,
            arrival_verified=False,
        )

    service.execute = execute
    dialog.mode_target.setCurrentIndex(dialog.mode_target.findData(LocalTransitionTarget.ANDROID))
    _answer_modal(monkeypatch, accept=True)
    _click(dialog.mode_button)
    _finish_next(app, started)
    _finish_next(app, started)

    assert dialog.monitoring is monitors
    assert len(started) == int(monitors)
    assert dialog.transition_result.command_completed is command_completed
    assert not dialog.transition_result.arrival_verified
    assert not dialog.transition_result.boot_verified
    assert dialog.boot_report is None
    assert boot.begin_calls == []
    if monitors:
        assert started[0].device.serial == device.serial


def test_android_arrival_timeout_followed_by_stable_boot_does_not_loop_back_to_recovery(
    lifecycle_dialog,
    monkeypatch,
    tmp_path: Path,
) -> None:
    app, dialog, boot, started, device = lifecycle_dialog
    service = dialog.transition_service
    original_execute = service.execute

    def execute(plan, **kwargs):
        return replace(
            original_execute(plan, **kwargs),
            state=LocalFlashState.FAILED,
            summary="Inert reboot was accepted; Android arrival exceeded the initial observation window.",
            command_completed=True,
            observed_device=None,
            arrival_verified=False,
        )

    service.execute = execute
    boot.reports.append(_report(tmp_path, LocalBootStatus.STABLE, device))
    dialog.mode_target.setCurrentIndex(dialog.mode_target.findData(LocalTransitionTarget.ANDROID))
    _answer_modal(monkeypatch, accept=True)
    _click(dialog.mode_button)
    _finish_next(app, started)
    _finish_next(app, started)
    assert dialog.monitoring
    _finish_next(app, started)
    routes = []
    window = SimpleNamespace(_pending_local_flash_recovery=None, _navigate_route=routes.append)

    MainWindow._finish_expert_dialog(window, dialog)

    assert dialog.boot_report.status is LocalBootStatus.STABLE
    assert dialog.transition_result.state is LocalFlashState.FAILED
    assert window._pending_local_flash_recovery is None
    assert routes == []
