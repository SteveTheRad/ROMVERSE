from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from romverse.nexus.planning import NexusObjective
from romverse.ui.nexus_center import NexusCenter
from tests.test_nexus_planning import _evidence


def test_nexus_center_generates_beginner_route_without_execution_authority(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    store, _profile, _matrix = _evidence(tmp_path)
    center = NexusCenter(store)

    assert center.project_selector.count() == 1
    assert center.generate_button.isEnabled()
    center.generate_plan()
    app.processEvents()

    assert center.current_plan is not None
    assert "READY FOR GUARDIAN REVIEW" in center.status.text()
    assert "Execution authority: NONE" in center.status.text()
    assert "Bootloader relock: NEVER" in center.status.text()
    assert center.route_layout.count() == 8
    assert "PROTECTED FIRMWARE" in center.foresight.text()
    assert "Proven compatible" in center.insight.text()
    assert center.guardian_button.isEnabled()
    assert all(button.text() != "Execute" for button in center.findChildren(QPushButton))


def test_nexus_guardian_handoff_emits_only_current_plan_identity(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    store, _profile, _matrix = _evidence(tmp_path)
    center = NexusCenter(store)
    center.generate_plan()
    app.processEvents()
    requested: list[tuple[str, str]] = []
    center.guardian_requested.connect(
        lambda project_id, digest: requested.append((project_id, digest))
    )

    center.guardian_button.click()
    app.processEvents()

    assert center.current_plan is not None
    assert requested == [(center.current_plan.project_id, center.current_plan.plan_digest)]
    assert "Approval: NONE" in center.status.text()
    assert "Execution: NONE" in center.status.text()


def test_nexus_guardian_handoff_fails_closed_for_stale_displayed_plan(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    store, profile, matrix = _evidence(tmp_path)
    center = NexusCenter(store)
    center.generate_plan()
    displayed = center.current_plan
    assert displayed is not None
    center.planner.plan(profile, matrix, NexusObjective.ROOT_ROM)
    requested: list[tuple[str, str]] = []
    center.guardian_requested.connect(
        lambda project_id, digest: requested.append((project_id, digest))
    )

    center.guardian_button.click()
    app.processEvents()

    assert requested == []
    assert "GUARDIAN HANDOFF STOPPED" in center.status.text()
    assert "no action started" in center.status.text().casefold()


def test_nexus_center_flash_route_explains_blocked_evidence_and_data_choice(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    store, _profile, _matrix = _evidence(tmp_path)
    center = NexusCenter(store)
    center.objective.setCurrentText("Prepare Guardian flash review")
    center.flash_mode.setCurrentText("Flash and wipe data • erases user data")
    center.generate_plan()
    app.processEvents()

    assert center.current_plan is not None
    assert "EVIDENCE REQUIRED" in center.status.text()
    assert "erase user data" in center.foresight.text()
    assert "RESEARCH REQUIRED" in center.insight.text()
    assert not center.guardian_button.isEnabled()
