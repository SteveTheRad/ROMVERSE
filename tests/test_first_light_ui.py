from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from romverse.rom.first_light import (
    FirstLightEvidenceKind,
    FirstLightOverall,
    FirstLightReport,
    FirstLightService,
    FirstLightStatus,
    FirstLightSubsystem,
)
from romverse.ui.first_light import FirstLightDialog


def _report(*, failed: bool = False) -> FirstLightReport:
    subsystems = tuple(
        FirstLightSubsystem(
            subsystem_id,
            label,
            required,
            FirstLightStatus.FAILED
            if failed and subsystem_id == "android_auto"
            else FirstLightStatus.WORKING
            if subsystem_id in FirstLightService.AUTOMATED_IDS
            else FirstLightStatus.UNTESTED,
            FirstLightEvidenceKind.AUTOMATED
            if subsystem_id in FirstLightService.AUTOMATED_IDS
            else FirstLightEvidenceKind.USER,
            "2026-09-05T01:00:00+00:00"
            if subsystem_id in FirstLightService.AUTOMATED_IDS
            or (failed and subsystem_id == "android_auto")
            else "",
            "Projection failed on a known-working vehicle."
            if failed and subsystem_id == "android_auto"
            else "Verified by read-only evidence."
            if subsystem_id in FirstLightService.AUTOMATED_IDS
            else "No observation has been recorded.",
            "",
        )
        for subsystem_id, label, required in FirstLightService.SUBSYSTEMS
    )
    return FirstLightReport(
        1,
        "a" * 32,
        "project",
        "2026-09-05T01:00:00+00:00",
        "2026-09-05T01:00:00+00:00",
        "b" * 20,
        "test.device",
        "c" * 64,
        "d" * 64,
        "e" * 64,
        "TARGET.2",
        "TARGET.2",
        "example/device:16/TARGET.2:user/release-keys",
        "16",
        "_a",
        "",
        (),
        subsystems,
        FirstLightOverall.FAILED if failed else FirstLightOverall.INCOMPLETE,
        ("Android Android Auto vehicle projection failed after ROM flash",) if failed else (),
        False,
        True,
        False,
        "f" * 64,
    )


class FakeService:
    AUTOMATED_IDS = FirstLightService.AUTOMATED_IDS

    def __init__(self, report) -> None:
        self.report = report

    def load(self, _project_id):
        return self.report


def test_first_light_is_large_truthful_and_motion_safe():
    app = QApplication.instance() or QApplication([])
    report = _report()
    dialog = FirstLightDialog(FakeService(report), report, reduced_motion=True)
    dialog.resize(1280, 820)
    dialog.show()
    app.processEvents()

    labels = " ".join(label.text() for label in dialog.findChildren(QLabel))
    buttons = dialog.findChildren(QPushButton)
    assert dialog.minimumWidth() >= 1080
    assert "Prove the new ROM works beyond the boot animation" in labels
    assert "Unknown stays untested" in labels
    assert "PUBLIC RELEASE READY: NO" in dialog.footer_status.text()
    assert not dialog.diagnose_button.isEnabled()
    assert not dialog.orbit.timer.isActive()
    assert sum(button.text() == "Verified automatically" for button in buttons) == len(
        FirstLightService.AUTOMATED_IDS
    )
    assert sum(button.text() == "Record result" for button in buttons) == len(
        report.subsystems
    ) - len(FirstLightService.AUTOMATED_IDS)
    dialog.close()


def test_first_light_routes_failed_subsystem_to_offline_archives():
    QApplication.instance() or QApplication([])
    report = _report(failed=True)
    calls = []

    def lookup(failure):
        calls.append(failure)
        return SimpleNamespace(matches=(object(), object()))

    dialog = FirstLightDialog(
        FakeService(report),
        report,
        reduced_motion=True,
        knowledge_lookup=lookup,
    )

    assert dialog.diagnose_button.isEnabled()
    dialog._diagnose()
    assert calls[0].phase == "first-light"
    assert calls[0].finding_ids == ("first-light.android_auto",)
    assert "2 compatible match(es)" in dialog.footer_status.text()
    dialog.close()


def test_first_light_reload_rejects_missing_evidence_without_changing_report(monkeypatch):
    QApplication.instance() or QApplication([])
    report = _report()
    service = FakeService(report)
    dialog = FirstLightDialog(service, report, reduced_motion=True)
    service.report = None
    monkeypatch.setattr(
        "romverse.ui.first_light.QMessageBox.warning",
        lambda *_args, **_kwargs: None,
    )

    dialog._reload()

    assert dialog.report == report
    dialog.close()
