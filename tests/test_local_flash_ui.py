from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from romverse.core.settings import ExperienceMode
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.local_flash import (
    LocalFlashPlan,
    LocalFlashResult,
    LocalFlashState,
    LocalFlashWrite,
)
from romverse.repair.autopilot import RecoveryTrigger
from romverse.rom.projects import RomProjectStore
from romverse.ui.background import start_background
from romverse.ui.local_flash import LocalFlashDialog
from romverse.ui.main_window import MainWindow
from romverse.ui.rom_studio import RomStudio
from romverse.ui.theme import STYLESHEET


def _plan(tmp_path: Path) -> LocalFlashPlan:
    """An inert UI fixture. Never send this plan to a real Fastboot runner."""
    return LocalFlashPlan(
        plan_digest="a" * 64,
        plan_id="ui-plan",
        inspected_at="2026-09-05T00:00:00+00:00",
        device_name="Example Test Phone",
        masked_serial="••••0001",
        product="example-device",
        mode="fastboot",
        current_slot="a",
        unlocked=True,
        writes=(
            LocalFlashWrite(
                "boot_a",
                tmp_path / "boot.img",
                "boot.img",
                4096,
                4096,
                "b" * 64,
                8192,
                False,
                True,
            ),
        ),
        warnings=("Boot and readback remain unverified.",),
        device_key="private-ui-key",
        serial="test-serial-0001",
        fastboot_path=tmp_path / "inert-fastboot",
        fastboot_sha256="c" * 64,
    )


def _accept(question: QMessageBox) -> int:
    next(
        button
        for button in question.buttons()
        if question.buttonRole(button) is QMessageBox.ButtonRole.AcceptRole
    ).click()
    return 0


def _pump_until(app: QApplication, condition: Callable[[], bool]) -> None:
    deadline = monotonic() + 3
    while not condition() and monotonic() < deadline:
        app.processEvents()
        sleep(0.005)
    assert condition()


@pytest.fixture
def flash_dialog(tmp_path: Path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    plan = _plan(tmp_path)
    started = []
    service = SimpleNamespace(inspect=lambda *_args: plan)
    monkeypatch.setattr("romverse.ui.local_flash.start_background", started.append)
    devices = (
        AndroidDevice(plan.serial, DeviceState.FASTBOOT, model="Test Phone 1"),
        AndroidDevice("test-serial-0002", DeviceState.FASTBOOT, model="Test Phone 2"),
    )
    dialog = LocalFlashDialog(service, devices)
    dialog.add_image(plan.writes[0].image_path, "boot_a")
    dialog.review_button.click()
    assert len(started) == 1
    started.pop().execute()
    app.processEvents()
    assert dialog.flash_button.isEnabled()
    yield app, dialog, started, plan
    dialog.worker = None
    dialog.close()


def test_declining_image_confirmation_starts_no_flash(flash_dialog, monkeypatch) -> None:
    _app, dialog, started, plan = flash_dialog

    def decline(question: QMessageBox) -> int:
        assert question.defaultButton() is question.button(QMessageBox.StandardButton.Cancel)
        question.button(QMessageBox.StandardButton.Cancel).click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", decline)
    dialog.flash_button.click()

    assert started == []
    assert dialog.worker is None
    assert dialog.plan is plan


@pytest.mark.parametrize("change", ["partition", "target", "add-image", "remove-image"])
def test_editing_reviewed_target_or_mappings_requires_a_new_review(
    flash_dialog,
    change: str,
    tmp_path: Path,
) -> None:
    _app, dialog, started, _plan_value = flash_dialog
    if change == "partition":
        dialog.images.item(0, 0).setText("boot_b")
    elif change == "target":
        dialog.target.setCurrentIndex(1)
    elif change == "add-image":
        dialog.add_image(tmp_path / "vendor.img", "vendor_a")
    else:
        dialog.remove_button.click()

    assert dialog.plan is None
    assert not dialog.flash_button.isEnabled()
    assert not dialog.review.toPlainText()
    assert started == []


def test_selection_invalidated_during_confirmation_cannot_execute_old_plan(
    flash_dialog,
    monkeypatch,
) -> None:
    _app, dialog, started, _plan_value = flash_dialog

    def change_then_accept(question: QMessageBox) -> int:
        dialog.target.setCurrentIndex(1)
        return _accept(question)

    monkeypatch.setattr(QMessageBox, "exec", change_then_accept)
    dialog.flash_button.click()

    assert started == []
    assert dialog.worker is None
    assert not dialog.flash_button.isEnabled()


def test_every_dialog_exit_is_blocked_while_a_write_worker_is_live(
    flash_dialog,
    monkeypatch,
    tmp_path: Path,
) -> None:
    app, dialog, started, _plan_value = flash_dialog
    monkeypatch.setattr(QMessageBox, "exec", _accept)
    dialog.show()
    app.processEvents()
    dialog._complete(
        LocalFlashResult(
            LocalFlashState.FAILED,
            "The earlier write did not complete.",
            tmp_path / "earlier-result.json",
            (),
            True,
            True,
        )
    )
    assert dialog.recovery_button.isVisible()
    dialog.review_button.click()
    started.pop().execute()
    app.processEvents()
    dialog.flash_button.click()
    assert len(started) == 1
    worker = started[0]

    dialog.reject()
    dialog.close()
    dialog._open_recovery()
    dialog.accept()
    dialog.done(0)
    app.processEvents()

    assert dialog.isVisible()
    assert dialog.worker is worker
    assert not dialog.recovery_requested
    assert not dialog.close_button.isEnabled()
    assert not dialog.recovery_button.isEnabled()
    assert not dialog.target.isEnabled()
    assert not dialog.images.isEnabled()


def test_cancel_keeps_dialog_busy_until_current_operation_returns(
    flash_dialog,
    monkeypatch,
    tmp_path: Path,
) -> None:
    app, dialog, _started, plan = flash_dialog
    entered = Event()
    release = Event()
    observed = {}

    def execute(reviewed, *, accepted_digest, risk_accepted, should_cancel, progress):
        observed["plan"] = reviewed
        observed["accepted_digest"] = accepted_digest
        observed["risk_accepted"] = risk_accepted
        entered.set()
        if not release.wait(3):
            raise TimeoutError("The inert test operation was not released")
        observed["cancelled"] = should_cancel()
        return LocalFlashResult(
            LocalFlashState.CANCELLED,
            "Stopped between writes at your request. Boot remains unverified.",
            tmp_path / "inert-result.json",
            (),
            True,
            True,
        )

    dialog.service.execute = execute
    monkeypatch.setattr("romverse.ui.local_flash.start_background", start_background)
    monkeypatch.setattr(QMessageBox, "exec", _accept)
    dialog.show()
    dialog.flash_button.click()
    try:
        _pump_until(app, entered.is_set)
        dialog.cancel_button.click()
        assert dialog.worker is not None
        assert not dialog.cancel_button.isEnabled()
        dialog.close()
        assert dialog.isVisible()
        assert dialog.result is None
    finally:
        release.set()
        _pump_until(app, lambda: dialog.worker is None)

    assert observed == {
        "plan": plan,
        "accepted_digest": plan.plan_digest,
        "risk_accepted": True,
        "cancelled": True,
    }
    assert dialog.result.state is LocalFlashState.CANCELLED
    assert not dialog.result.boot_verified
    assert dialog.recovery_button.isVisible()
    assert dialog.close_button.isEnabled()
    assert not dialog.flash_button.isEnabled()


def test_execution_exception_preserves_uncertainty_and_offers_recovery(
    flash_dialog,
    monkeypatch,
) -> None:
    app, dialog, started, _plan_value = flash_dialog

    def execute(*_args, **_kwargs):
        raise OSError("The operation record could not be updated")

    dialog.service.execute = execute
    monkeypatch.setattr(QMessageBox, "exec", _accept)
    dialog.show()
    dialog.flash_button.click()
    started.pop().execute()
    app.processEvents()

    assert dialog.worker is None
    assert dialog.result is None
    assert dialog.execution_error
    assert dialog.recovery_button.isVisible()
    assert dialog.recovery_button.isEnabled()
    assert not dialog.flash_button.isEnabled()


def test_flash_dialog_fits_available_screen_and_keeps_review_readable(flash_dialog) -> None:
    app, dialog, _started, _plan_value = flash_dialog
    dialog.setStyleSheet(STYLESHEET)
    dialog.show()
    app.processEvents()

    available = dialog.screen().availableGeometry()
    assert dialog.width() <= available.width()
    assert dialog.height() <= available.height()
    assert dialog.images.viewport().height() >= 42
    assert dialog.review.viewport().height() >= 80
    assert dialog.flash_button.geometry().bottom() < dialog.height()
    assert dialog.review.isReadOnly()


def test_recovery_remembers_attempted_phone_after_display_selection_changes(
    flash_dialog,
    monkeypatch,
    tmp_path: Path,
) -> None:
    app, dialog, started, _plan_value = flash_dialog
    attempted = dialog.devices[0]
    result = LocalFlashResult(
        LocalFlashState.FAILED,
        "Inert fixture write failed; boot is unverified.",
        tmp_path / "inert-result.json",
        (),
        True,
        True,
    )
    dialog.service.execute = lambda *_args, **_kwargs: result
    monkeypatch.setattr(QMessageBox, "exec", _accept)

    dialog.flash_button.click()
    started.pop().execute()
    app.processEvents()
    dialog.target.setCurrentIndex(1)

    assert dialog.result is result
    assert dialog.last_attempt_device is attempted
    assert dialog.last_attempt_device.serial != dialog.devices[dialog.target.currentIndex()].serial


@pytest.mark.parametrize("freshness", ["matching", "absent", "unrelated-only"])
def test_local_flash_recovery_uses_attempted_identity_and_fresh_state_without_project_assumptions(
    freshness: str,
) -> None:
    attempted = AndroidDevice(
        "attempted-device",
        DeviceState.FASTBOOT,
        manufacturer="Example OEM",
        model="Attempted phone",
        product="attempted-product",
        codename="attempted-codename",
        battery_percent=100,
        boot_completed=True,
        build_id="OLD.1",
    )
    unrelated = AndroidDevice(
        "unrelated-device",
        DeviceState.DEVICE,
        manufacturer="Other OEM",
        model="Other phone",
        boot_completed=True,
    )
    fresh = replace(attempted, state=DeviceState.RECOVERY, boot_completed=False, build_id="NEW.2")
    devices = (
        [unrelated, fresh]
        if freshness == "matching"
        else [unrelated]
        if freshness == "unrelated-only"
        else []
    )
    calls = []
    routes = []

    def open_incident(trigger, **context):
        calls.append((trigger, context))
        return True

    window = SimpleNamespace(
        _pending_local_flash_recovery=(attempted, "Selected image write did not complete."),
        rom_studio=SimpleNamespace(
            current_project=SimpleNamespace(project_id="unrelated-project"),
            devices=[unrelated],
        ),
        repair_center=SimpleNamespace(open_recovery_incident=open_incident),
        _navigate_route=routes.append,
    )

    MainWindow._finish_local_flash_recovery(window, devices)
    MainWindow._finish_local_flash_recovery(window, devices)

    assert len(calls) == 1
    trigger, context = calls[0]
    target = context["target_device"]
    assert trigger is RecoveryTrigger.FLASH_FAILURE
    assert context["project_id"] == ""
    assert not context.get("recovery_evidence")
    assert target.serial == attempted.serial
    assert routes == ["recovery_bay"]
    assert window._pending_local_flash_recovery is None
    if freshness == "matching":
        assert target is fresh
        assert target.state is DeviceState.RECOVERY
        assert target.build_id == "NEW.2"
    else:
        assert target.state is DeviceState.UNKNOWN
        assert target.manufacturer == attempted.manufacturer
        assert target.model == attempted.model
        assert target.product == attempted.product
        assert target.codename == attempted.codename
        assert target.boot_completed is None
        assert target.battery_percent is None
        assert target.build_id == ""


def test_rom_studio_expert_flash_entry_is_visible_and_emits_only_in_expert_mode(
    tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    studio = RomStudio(RomProjectStore(tmp_path / "workspace"), DevicePackRegistry(()))
    requests = []
    studio.expert_flash_requested.connect(lambda: requests.append("open-review"))
    try:
        for mode in (item for item in ExperienceMode if item is not ExperienceMode.EXPERT):
            studio.set_experience_mode(mode)
            assert studio.expert_flash_button.isHidden()
            studio.expert_flash_button.click()
            assert requests == []

        studio.set_experience_mode(ExperienceMode.EXPERT)
        assert not studio.expert_flash_button.isHidden()
        assert studio.expert_flash_button.isEnabled()
        studio.expert_flash_button.click()
        assert requests == ["open-review"]
        assert studio.worker is None

        studio.set_experience_mode(ExperienceMode.GUIDED)
        studio.expert_flash_button.click()
        assert requests == ["open-review"]
    finally:
        studio.close()
