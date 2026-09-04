"""Real desktop/ROM Studio/Recovery Bay wiring with exclusively inert transports."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from romverse.core.activity import ActivityStore
from romverse.core.settings import AppSettings, ExperienceMode
from romverse.device.models import DeviceState
from romverse.guardian.local_flash import LocalFlashService
from romverse.guardian.local_transition import LocalDeviceTransitionService
from romverse.infrastructure.tools import ToolStatus
from romverse.repair.autopilot import RecoveryTrigger
from romverse.rom.local_boot import (
    LocalBootReport,
    LocalBootService,
    LocalBootSession,
    LocalBootStatus,
)
from romverse.ui.local_flash import LocalFlashDialog
from romverse.ui.main_window import MainWindow
from scripts.simulate_expert_lifecycle import SimulatedAndroid


class InertScanEngine:
    def __init__(self, devices):
        self.devices = devices
        self.scan_calls = 0

    def scan(self):
        self.scan_calls += 1
        return list(self.devices)

    def scan_reconnect_safe(self):
        return self.scan()


class InertBootOutcome:
    """Typed boot outcome injection; no commands, timing claims, or real receipt."""

    def __init__(self, flash, adb, *, status):
        self.flash = flash
        self.adb_path = adb
        self.status = status
        self.device = None

    def begin(self, device, flash_result=None):
        assert flash_result is None
        self.device = device
        return LocalBootSession(
            "inert-desktop-session", device.display_name, device.masked_serial()
        )

    def observe(self, session):
        assert session.session_id == "inert-desktop-session"
        return self._report(self.status)

    def stop(self, session):
        assert session.session_id == "inert-desktop-session"
        return self._report(LocalBootStatus.CANCELLED)

    def _report(self, status):
        return LocalBootReport(
            status,
            "SIMULATION ONLY: boot observation outcome; no physical phone was checked.",
            self.flash.workspace / "inert-ui-boot-outcome.json",
            1,
            5,
            status is LocalBootStatus.SETTLING,
            status is not LocalBootStatus.SETTLING,
            "reboot_loop" if status is LocalBootStatus.ATTENTION else "",
            self.device,
        )


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    runner = SimulatedAndroid()
    tools = tmp_path / "inert-tools"
    tools.mkdir()
    for name in ("adb", "fastboot"):
        path = tools / name
        path.write_bytes(b"INERT FIXTURE; NOT EXECUTABLE CODE\n")
        path.chmod(0o700)
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(
        "romverse.ui.toolchain_center.ToolVerifier.verify_extended",
        lambda _self: (
            ToolStatus("ADB", True, str(tools / "adb"), "simulation"),
            ToolStatus("Fastboot", True, str(tools / "fastboot"), "simulation"),
        ),
    )
    window = MainWindow(
        None,
        logo,
        workspace,
        runner=runner,
        adb_executable=tools / "adb",
        fastboot_executable=tools / "fastboot",
        app_icon_path=logo,
        app_settings=AppSettings(
            experience_mode=ExperienceMode.EXPERT,
            online_intelligence_enabled=False,
            desktop_notifications_enabled=False,
            reduced_motion=True,
        ),
    )
    # Only scheduling is made synchronous; the real worker execute/signals and
    # the real MainWindow scan-completion/recovery paths still run.
    monkeypatch.setattr("romverse.ui.local_flash.start_background", lambda worker: worker.execute())
    monkeypatch.setattr("romverse.ui.main_window.start_background", lambda worker: worker.execute())
    device = runner.device()
    window._observed_devices = [device]
    window._selected_device_serial = device.serial
    window.rom_studio.set_devices([device])
    window.show()
    app.processEvents()
    yield app, window, runner, workspace
    if window._local_flash_dialog is not None:
        window._local_flash_dialog.monitoring = False
        window._local_flash_dialog.worker = None
        window._local_flash_dialog.reject()
        window._local_flash_dialog = None
    window.companion_center.transport.close()
    window.close()
    app.processEvents()


def _open_from_rom_studio(app, window, action):
    errors = []
    opened = []
    cancel_questions = QTimer()

    def decline_questions():
        modal = app.activeModalWidget()
        if isinstance(modal, QMessageBox):
            cancel = modal.button(QMessageBox.StandardButton.Cancel)
            if cancel is not None:
                cancel.click()

    def interact():
        dialog = window._local_flash_dialog
        opened.append(dialog)
        try:
            assert isinstance(dialog, LocalFlashDialog)
            action(dialog)
        except BaseException as exc:
            errors.append(exc)
        finally:
            if isinstance(dialog, LocalFlashDialog):
                if dialog.monitoring:
                    dialog._stop_boot()
                dialog.reject()

    cancel_questions.timeout.connect(decline_questions)
    cancel_questions.start(5)
    QTimer.singleShot(0, interact)
    window.rom_studio.expert_flash_requested.emit()
    cancel_questions.stop()
    app.processEvents()
    assert len(opened) == 1, "ROM Studio did not open the desktop-owned Expert dialog"
    if errors:
        raise errors[0]
    assert window._local_flash_dialog is None
    return opened[0]


def test_rom_studio_opens_real_services_and_declining_mode_change_sends_no_reboot(desktop):
    app, window, runner, _workspace = desktop

    def interact(dialog):
        assert isinstance(dialog.service, LocalFlashService)
        assert isinstance(dialog.transition_service, LocalDeviceTransitionService)
        assert isinstance(dialog.boot_service, LocalBootService)
        assert dialog.service.runner is runner
        assert dialog.service.audit is window._audit_store
        assert dialog.transition_service.flash_service is dialog.service
        assert dialog.boot_service.flash is dialog.service
        assert dialog.devices[0].serial == runner.serial
        assert not window._reconnect_timer.isActive()
        dialog.mode_button.click()
        assert dialog.worker is None
        assert "cancelled" in dialog.status.text().casefold()
        assert dialog.transition_result is None

    _open_from_rom_studio(app, window, interact)
    assert runner.calls, "The production transition service did not inspect the virtual phone"
    assert not any("reboot" in command or "flash" in command for command in runner.calls)
    assert window.repair_center.autopilot_incident is None
    assert window._audit_store.verify().valid


def test_monitoring_guards_desktop_close_rescan_and_duplicate_dialog(desktop, monkeypatch):
    app, window, runner, workspace = desktop
    monkeypatch.setattr(
        "romverse.rom.local_boot.LocalBootService",
        lambda flash, adb: InertBootOutcome(flash, adb, status=LocalBootStatus.SETTLING),
    )
    engine = InertScanEngine([runner.device()])
    window.engine = engine

    def interact(dialog):
        dialog.boot_button.click()
        assert dialog.monitoring and dialog.worker is None
        assert dialog.boot_report.status is LocalBootStatus.SETTLING
        assert not window.close(), "The desktop closed during active boot monitoring"
        assert window.isVisible()
        window.scan()
        window.rom_studio.expert_flash_requested.emit()
        assert window._local_flash_dialog is dialog
        assert engine.scan_calls == 0
        dialog.cancel_button.click()
        assert dialog.boot_report.status is LocalBootStatus.CANCELLED
        assert not dialog.monitoring

    _open_from_rom_studio(app, window, interact)
    assert engine.scan_calls == 1, "Closing the session should refresh the selected phone once"
    events = ActivityStore(workspace).list_recent()
    assert any(
        event.title == "Android boot check ended" and event.outcome == "attention"
        for event in events
    )
    assert not any(event.title.startswith("Android boot observed") for event in events)
    assert not runner.calls


def test_terminal_boot_failure_rescans_and_opens_persisted_exact_phone_recovery(
    desktop, monkeypatch
):
    app, window, runner, workspace = desktop
    monkeypatch.setattr(
        "romverse.rom.local_boot.LocalBootService",
        lambda flash, adb: InertBootOutcome(flash, adb, status=LocalBootStatus.ATTENTION),
    )
    fresh = replace(runner.device(), state=DeviceState.BOOTLOADER)
    other = replace(fresh, serial="UNRELATED-SIMULATED-PHONE", model="Unrelated virtual phone")
    engine = InertScanEngine([other, fresh])
    window.engine = engine

    def interact(dialog):
        dialog.boot_button.click()
        assert dialog.boot_report.status is LocalBootStatus.ATTENTION
        assert dialog.recovery_requested
        assert not dialog.isVisible(), "Terminal boot failure should hand back to Recovery Bay"

    _open_from_rom_studio(app, window, interact)
    assert engine.scan_calls == 1
    assert window.stack.currentWidget() is window.repair_center
    assert window._selected_device_serial == runner.serial
    assert window._pending_local_flash_recovery is None
    recovery = window.repair_center.autopilot_service
    incident = window.repair_center.autopilot_incident
    assert incident is not None
    assert incident.trigger is RecoveryTrigger.BOOTLOOP
    assert incident.device_key == recovery.privacy.pseudonym(runner.serial)
    assert incident.device_key != recovery.privacy.pseudonym(other.serial)
    assert incident.mode == fresh.state.value
    assert incident.project_id == ""
    assert not incident.repaired and not incident.verified_reboot and not incident.phone_changed
    assert recovery.load(incident.incident_id) == incident
    events = ActivityStore(workspace).list_recent()
    assert any(
        event.title == "Android boot check ended" and event.outcome == "attention"
        for event in events
    )
    assert any(event.title == "Recovery Autopilot incident opened" for event in events)
    assert not runner.calls, "Opening the recovery incident must not execute a repair"
