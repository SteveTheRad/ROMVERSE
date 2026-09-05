"""Read-only post-installation user journeys with real Qt/services and an inert phone."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from romverse.guardian.source_installation import SourceInstallationExecutor
from romverse.rom.local_boot import LocalBootService, LocalBootStatus
from romverse.rom.source_installation_history import load_latest_source_installation
from romverse.ui.local_flash import LocalFlashWorker
from romverse.ui.source_installation_history import SourceInstallationHistoryDialog
from tests.test_source_installation_integration import installation as installation


@pytest.fixture
def history(installation, monkeypatch):
    context = installation
    executor = SourceInstallationExecutor(context.source, context.flash, context.adb)
    recipe = context.recipe()
    plan = executor.inspect(context.phone.device(), recipe)
    result = executor.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True)
    assert result.state == "completed"
    outcome = load_latest_source_installation(context.source.store, context.project_id)
    assert outcome is not None and outcome.result is not None
    app = QApplication.instance() or QApplication([])
    workers = []
    monkeypatch.setattr("romverse.ui.local_flash.start_background", workers.append)
    other = replace(context.phone.device(), serial="UNRELATED-SIMULATED-PHONE")
    boot = LocalBootService(
        context.flash,
        context.adb,
        monotonic_clock=lambda: context.phone.seconds,
        utc_clock=lambda: (
            datetime(2026, 9, 5, tzinfo=UTC) + timedelta(seconds=context.phone.seconds)
        ),
    )
    dialog = SourceInstallationHistoryDialog(
        context.flash,
        (other, context.phone.device()),
        outcome=outcome,
        boot_service=boot,
        discover=lambda: [other, context.phone.device()],
    )
    before = len(context.phone.changes)
    dialog.show()
    app.processEvents()
    yield app, dialog, workers, context, before
    dialog.boot_timer.stop()
    dialog.monitoring = False
    dialog.worker = None
    dialog.close()
    app.processEvents()


def _click(widget):
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)


def _finish(app, workers):
    assert len(workers) == 1
    workers.pop(0).execute()
    app.processEvents()


def test_opening_history_never_autostarts_observation_or_installation(history):
    _app, dialog, workers, context, before = history
    assert workers == []
    assert not dialog.monitoring
    assert len(context.phone.changes) == before
    assert dialog._selected_device().serial == context.phone.serial
    assert dialog.preparation is dialog.outcome
    assert "HISTORICAL" in dialog.review.toPlainText()
    assert "Sealed installation evidence" in dialog.review.toPlainText()
    assert "known failed none" in dialog.review.toPlainText()
    assert "not fresh" in dialog.boundary.text()
    assert dialog.width() >= 720 and dialog.height() >= 620


def test_no_image_or_mode_controls_or_hidden_method_can_execute(history, tmp_path):
    _app, dialog, workers, context, before = history
    for widget in (
        dialog.images,
        dialog.mode_target,
        dialog.mode_button,
        dialog.add_button,
        dialog.remove_button,
        dialog.review_button,
        dialog.flash_button,
    ):
        assert widget.isHidden()
        assert not widget.isEnabled()
    dialog.add_image(tmp_path / "never-read.img", "boot_a")
    dialog._choose_image()
    dialog._remove_image()
    dialog._inspect()
    dialog._confirm_flash()
    dialog._change_mode()
    dialog._confirm_transition(None, None, None)
    dialog._start(LocalFlashWorker(context.flash, context.phone.device(), ()))
    assert workers == []
    assert dialog.images.rowCount() == 0
    assert len(context.phone.changes) == before


def test_explicit_boot_click_measures_real_stable_interval_without_changing_phone(history):
    app, dialog, workers, context, before = history
    reports = []
    dialog.boot_finished.connect(reports.append)
    _click(dialog.boot_button)
    assert dialog.monitoring
    assert workers[0].flash_result is dialog.outcome.result
    _finish(app, workers)
    assert dialog.boot_report.status is LocalBootStatus.SETTLING
    assert not reports
    for _ in range(12):
        dialog.boot_timer.stop()
        context.phone.seconds += 5
        dialog._poll_boot()
        _finish(app, workers)
    assert len(reports) == 1
    assert reports[0].status is LocalBootStatus.STABLE
    assert reports[0].boot_observed
    assert reports[0].elapsed_seconds == 60
    assert not dialog.monitoring and not dialog.boot_timer.isActive()
    assert len(context.phone.changes) == before
    record = json.loads(reports[0].receipt_path.read_text())
    assert record["flash_binding"]["relative_path"].startswith("guardian/source-installation/")
    assert record["readback_verified"] is False


def test_wrong_phone_selection_blocks_click_and_direct_boot_method(history):
    app, dialog, workers, context, before = history
    dialog.target.setCurrentIndex(0)
    app.processEvents()
    assert not dialog.boot_button.isEnabled()
    _click(dialog.boot_button)
    dialog._start_boot(dialog._selected_device())
    assert workers == []
    assert not dialog.monitoring
    assert "same recorded phone" in dialog.status.text()
    assert len(context.phone.changes) == before


def test_absent_phone_never_starts_an_unlinked_boot_check(history):
    app, dialog, workers, context, before = history
    dialog.devices = ()
    dialog.target.clear()
    app.processEvents()
    assert not dialog.boot_button.isEnabled()
    dialog._start_boot(None)
    assert workers == []
    assert dialog.boot_report is None and not dialog.monitoring
    assert len(context.phone.changes) == before


def test_receipt_modified_after_history_open_cannot_create_unlinked_boot_success(history):
    _app, dialog, workers, context, before = history
    receipt = dialog.outcome.result.receipt_path
    document = json.loads(receipt.read_text())
    document["summary"] = "CHANGED HISTORICAL EVIDENCE"
    receipt.write_text(json.dumps(document))
    _click(dialog.boot_button)
    assert workers == []
    assert not dialog.monitoring
    assert "no longer validates" in dialog.status.text()
    assert dialog.boot_report is None
    assert len(context.phone.changes) == before


def test_missing_typed_result_displays_history_and_recovery_but_never_starts_boot(history):
    _app, dialog, workers, context, before = history
    dialog.outcome = replace(
        dialog.outcome,
        state="attention",
        result=None,
        device_key="",
        product="",
    )
    dialog.preparation = dialog.outcome
    dialog._invalidate()
    assert not dialog.boot_button.isEnabled()
    assert dialog.recovery_button.isVisible()
    assert "exact interrupted-operation target" in dialog.status.text()
    dialog._start_boot(context.phone.device())
    assert workers == []
    _click(dialog.recovery_button)
    assert dialog.recovery_requested
    assert dialog.last_attempt_device.serial == context.phone.serial
    assert dialog.last_flash_device.serial == context.phone.serial
    assert len(context.phone.changes) == before


def test_close_waits_for_current_read_only_probe_then_persists_stop(history):
    app, dialog, workers, context, before = history
    _click(dialog.boot_button)
    assert dialog.worker is not None
    dialog.close()
    app.processEvents()
    assert dialog.isVisible()
    assert dialog._boot_stop_requested
    _finish(app, workers)
    assert len(workers) == 1  # A persisted stop report follows the already-started probe.
    _finish(app, workers)
    assert not dialog.isVisible()
    assert dialog.boot_report.status is LocalBootStatus.CANCELLED
    assert not dialog.boot_timer.isActive()
    assert len(context.phone.changes) == before


def test_refresh_is_read_only_and_cannot_assign_recovery_to_unrelated_phone(history):
    app, dialog, workers, context, before = history
    _click(dialog.refresh_button)
    _finish(app, workers)
    dialog.target.setCurrentIndex(0)
    app.processEvents()
    _click(dialog.recovery_button)
    assert dialog.recovery_requested
    assert dialog.last_attempt_device is None
    assert dialog.last_flash_device is None
    assert len(context.phone.changes) == before
