"""Full desktop Guided handoff and preparation lifecycle; all phone transports inert."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from romverse.core.settings import AppSettings, ExperienceMode
from romverse.infrastructure.tools import ToolStatus
from romverse.repair.autopilot import RecoveryTrigger
from romverse.rom.project_flash import BoundProjectFlashService
from romverse.ui.main_window import MainWindow
from romverse.ui.project_flash import ProjectFlashDialog, ProjectPreparationDialog
from tests.test_project_flash_integration import project_context as project_context


@pytest.fixture
def project_desktop(project_context, monkeypatch):
    app = QApplication.instance() or QApplication([])
    context = project_context
    tool = context.local_service.fastboot_path
    monkeypatch.setattr(
        "romverse.ui.toolchain_center.ToolVerifier.verify_extended",
        lambda _self: (ToolStatus("Fastboot", True, str(tool), "inert simulation"),),
    )
    monkeypatch.setattr(
        "romverse.ui.project_flash.start_background", lambda worker: worker.execute()
    )
    monkeypatch.setattr("romverse.ui.local_flash.start_background", lambda worker: worker.execute())
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        context.store.workspace,
        runner=context.runner,
        fastboot_executable=tool,
        app_icon_path=logo,
        app_settings=AppSettings(
            experience_mode=ExperienceMode.GUIDED,
            online_intelligence_enabled=False,
            desktop_notifications_enabled=False,
            reduced_motion=True,
        ),
    )
    window.rom_studio.current_project = context.store.get(context.project_id)
    window._observed_devices = [context.device]
    window.rom_studio.set_devices([context.device])
    window.show()
    app.processEvents()
    yield app, window, context
    if window._local_flash_dialog is not None:
        window._local_flash_dialog.worker = None
        window._local_flash_dialog.monitoring = False
        window._local_flash_dialog.reject()
        window._local_flash_dialog = None
    window.companion_center.transport.close()
    window.close()
    app.processEvents()


def test_guided_rom_studio_opens_real_source_bound_workflow_and_decline_sends_no_write(
    project_desktop,
):
    app, window, context = project_desktop
    phases = []
    errors = []
    timer = QTimer()
    timeout = QTimer()
    timeout.setSingleShot(True)

    def decline_confirmation():
        question = app.activeModalWidget()
        if isinstance(question, QMessageBox):
            phases.append("declined")
            question.button(QMessageBox.StandardButton.Cancel).click()

    def interact():
        modal = app.activeModalWidget()
        try:
            if isinstance(modal, ProjectPreparationDialog) and "prepare" not in phases:
                phases.append("prepare")
                assert window._local_flash_dialog is modal
                assert context.runner.calls == []
                modal.choice.setCurrentIndex(modal.choice.findData("protected"))
                modal.prepare_button.click()
            elif isinstance(modal, ProjectFlashDialog) and "images" not in phases:
                phases.append("images")
                assert isinstance(modal.service, BoundProjectFlashService)
                assert window._experience_mode is ExperienceMode.GUIDED
                assert modal.images.rowCount() == 0
                modal.add_button.click()
                assert modal.images.item(0, 0).text() == ""
                modal.images.item(0, 0).setText("boot_a")
                modal.review_button.click()
                assert modal.plan is not None
                assert context.prepare().source_sha256 in modal.review.toPlainText()
                QTimer.singleShot(0, decline_confirmation)
                modal.flash_button.click()
                assert "declined" in phases
                assert context.runner.writes == []
                modal.reject()
            elif isinstance(modal, QMessageBox):
                phases.append("declined")
                assert modal.windowTitle() == "Confirm exact image writes"
                modal.button(QMessageBox.StandardButton.Cancel).click()
        except BaseException as exc:
            errors.append(exc)
            timer.stop()
            if modal is not None:
                modal.reject()

    def expired():
        errors.append(AssertionError(f"The actual Guided modal journey did not finish: {phases}"))
        if app.activeModalWidget() is not None:
            app.activeModalWidget().reject()

    timer.timeout.connect(interact)
    timer.start(1)
    timeout.timeout.connect(expired)
    timeout.start(5000)
    assert window.rom_studio._request_project_flash(context.project_id)
    timer.stop()
    timeout.stop()
    if errors:
        raise errors[0]
    assert phases == ["prepare", "images", "declined"]
    assert window._local_flash_dialog is None
    assert context.runner.writes == []
    assert window._experience_mode is ExperienceMode.GUIDED


def test_guided_preparation_cancellation_never_constructs_image_executor(project_desktop):
    app, window, context = project_desktop
    opened = []

    def cancel():
        modal = app.activeModalWidget()
        opened.append(modal)
        if isinstance(modal, ProjectPreparationDialog):
            modal.close_button.click()

    QTimer.singleShot(0, cancel)
    window.rom_studio._request_project_flash(context.project_id)
    assert len(opened) == 1 and isinstance(opened[0], ProjectPreparationDialog)
    assert context.runner.calls == []
    assert window._local_flash_dialog is None


def test_project_changed_while_waiting_for_scan_abandons_pending_handoff(
    project_desktop, monkeypatch
):
    _app, window, context = project_desktop
    original = window.rom_studio.current_project
    scheduled = []
    monkeypatch.setattr(QTimer, "singleShot", lambda _wait, action: scheduled.append(action))
    window.scanning = True
    window._open_project_flash(context.project_id)
    assert window._expert_flash_pending
    window.rom_studio.current_project = context.store.create("Different project")
    window.scanning = False
    window._continue_project_flash_open(context.project_id, original.original.sha256)
    assert not window._expert_flash_pending
    assert window._local_flash_dialog is None
    assert context.runner.calls == []


def test_preparation_failure_keeps_explicit_choice_and_can_retry(project_context, monkeypatch):
    app = QApplication.instance() or QApplication([])
    choices = []

    def prepare(project_id, *, candidate_choice):
        choices.append(candidate_choice)
        if candidate_choice == "built":
            raise ValueError("No current built images; choose protected images explicitly.")
        return project_context.prepare()

    monkeypatch.setattr(
        "romverse.ui.project_flash.start_background", lambda worker: worker.execute()
    )
    dialog = ProjectPreparationDialog(SimpleNamespace(prepare=prepare), project_context.project_id)
    dialog.show()
    dialog.prepare_button.click()
    assert dialog.preparation is None and dialog.worker is None
    assert dialog.choice.currentData() == "built"
    assert dialog.prepare_button.isEnabled()
    assert "explicitly" in dialog.status.text()
    dialog.choice.setCurrentIndex(dialog.choice.findData("protected"))
    dialog.prepare_button.click()
    assert dialog.preparation is not None
    assert choices == ["built", "protected"]
    assert project_context.runner.calls == []
    dialog.close()
    app.processEvents()


def test_preparation_cannot_close_during_worker_and_ignores_stale_callbacks(
    project_context, monkeypatch
):
    app = QApplication.instance() or QApplication([])
    pending = []
    monkeypatch.setattr("romverse.ui.project_flash.start_background", pending.append)
    dialog = ProjectPreparationDialog(project_context.preparer, project_context.project_id)
    dialog.choice.setCurrentIndex(dialog.choice.findData("protected"))
    dialog.show()
    dialog.prepare_button.click()
    worker = pending.pop()
    dialog.reject()
    assert dialog.isVisible() and dialog.worker is worker
    worker.execute()
    assert dialog.preparation is not None and dialog.worker is None
    outcome = dialog.preparation
    worker.signals.failed.emit("stale error")
    assert dialog.preparation is outcome
    assert "stale error" not in dialog.status.text()
    dialog.close()
    app.processEvents()


def test_preparation_scheduler_failure_does_not_trap_dialog(project_context, monkeypatch):
    app = QApplication.instance() or QApplication([])

    def fail(_worker):
        raise RuntimeError("Background scheduler is closing")

    monkeypatch.setattr("romverse.ui.project_flash.start_background", fail)
    dialog = ProjectPreparationDialog(project_context.preparer, project_context.project_id)
    dialog.show()
    dialog.prepare_button.click()
    assert dialog.worker is None and dialog.close_button.isEnabled()
    assert "scheduler" in dialog.status.text()
    dialog.reject()
    assert not dialog.isVisible()
    app.processEvents()


@pytest.mark.parametrize("changed_source", [False, True])
def test_recovery_attributes_original_project_only_while_its_source_matches(
    project_desktop,
    monkeypatch,
    changed_source,
):
    _app, window, context = project_desktop
    project = context.store.get(context.project_id)
    calls = []
    monkeypatch.setattr(
        window.repair_center,
        "open_recovery_incident",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    window._pending_local_flash_recovery = (context.device, "Simulated partial local operation")
    window._pending_local_flash_recovery_trigger = RecoveryTrigger.FLASH_FAILURE
    window._pending_local_flash_recovery_project = (
        context.project_id,
        "0" * 64 if changed_source else project.original.sha256,
    )
    window._finish_local_flash_recovery([])
    assert len(calls) == 1
    assert calls[0][1]["project_id"] == ("" if changed_source else context.project_id)
    assert calls[0][1]["target_device"].serial == context.device.serial
    assert window._pending_local_flash_recovery_project is None
