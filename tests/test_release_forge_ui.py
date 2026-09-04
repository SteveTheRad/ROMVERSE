from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from romverse.rom.release_forge import (
    ReleaseForgeAssessment,
    ReleaseGate,
    ReleaseGateState,
    ReleasePackageKind,
    ReleaseSecurityScan,
    ReleaseTier,
)
from romverse.ui.release_forge import ReleaseForgeDialog


def _assessment(*, blocked: bool = False) -> ReleaseForgeAssessment:
    gates = (
        ReleaseGate(
            "source",
            "Exact source and Device Pack",
            ReleaseGateState.PASS,
            "Protected source agrees with the pack.",
            "No action required.",
        ),
        ReleaseGate(
            "simulation",
            "Successful unmodified Digital Twin rehearsal",
            ReleaseGateState.BLOCKED if blocked else ReleaseGateState.PASS,
            "No current mission." if blocked else "Current mission verified.",
            "Run Simulation Lab." if blocked else "No action required.",
        ),
    )
    security = ReleaseSecurityScan(4, 256, 1, True, True, (), (), "a" * 64)
    return ReleaseForgeAssessment(
        "project",
        ReleaseTier.DEVELOPMENT,
        ReleasePackageKind.FULL,
        gates,
        security,
        ("super.img",),
        "b" * 64,
        "c" * 64,
        "",
    )


class FakeService:
    CERTIFICATE_REQUEST_NAME = "romverse-release-certificate-request.json"

    def __init__(self, blocked: bool = False) -> None:
        self.blocked = blocked

    def load_plan(self, _project_id):
        return None

    def load_bundle_receipt(self, _project_id):
        return None

    def assess(self, *_args, **_kwargs):
        return _assessment(blocked=self.blocked)

    def verify_bundle(self, _receipt):
        return None


def test_release_forge_presents_truthful_release_gates_and_no_publish_action():
    app = QApplication.instance() or QApplication([])
    dialog = ReleaseForgeDialog(
        FakeService(),
        "project",
        reduced_motion=True,
    )
    dialog.resize(1280, 820)
    dialog.show()
    app.processEvents()

    labels = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "Turn proven build evidence into a sealed release capsule" in labels
    assert "Exact source and Device Pack" in labels
    assert "PUBLISHING AUTHORITY: NONE" in dialog.status.text()
    assert dialog.plan_button.isEnabled()
    assert not dialog.forge.timer.isActive()
    assert all(
        "publish" not in button.text().casefold() for button in dialog.findChildren(QPushButton)
    )
    dialog.close()


def test_release_forge_disables_planning_while_real_evidence_is_blocked():
    QApplication.instance() or QApplication([])
    dialog = ReleaseForgeDialog(FakeService(blocked=True), "project")

    assert dialog.readiness_badge.text() == "1 BLOCKER(S)"
    assert not dialog.plan_button.isEnabled()
    assert "PHONE CHANGED: NO" in dialog.status.text()
    dialog.close()
