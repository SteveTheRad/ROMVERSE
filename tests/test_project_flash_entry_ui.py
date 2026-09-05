from __future__ import annotations

from dataclasses import replace

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton

from romverse.core.settings import ExperienceMode
from romverse.rom.guided import GuidedContext, GuidedMissionEngine, GuidedStageStatus
from romverse.rom.project_flash import ProjectFlashOutcome, ProjectFlashPreparationService
from romverse.rom.readiness import BuildGate, GateStatus
from romverse.ui.build_control import BuildControlCenter
from romverse.ui.guided_mission import GuidedBuildMission
from tests.test_build_control_ui import _studio


def _prepared_control(studio, parent=None):
    control = BuildControlCenter(studio, parent, auto_start=False)
    # UI-only candidate fixture. It is not evidence of a real build or phone operation.
    report = replace(
        control.report,
        local_candidate_ready=True,
        signing_ready=True,
        flash_ready=False,
        gates=(
            BuildGate(
                "device-pack-flash",
                "Production flash contract",
                "Recovery",
                GateStatus.ATTENTION,
                "Fixture: no production certificate",
                "flash",
            ),
            BuildGate(
                "physical-validation",
                "Physical certification",
                "Guardian",
                GateStatus.ATTENTION,
                "Fixture: no physical test",
                "release",
            ),
        ),
    )
    control.service.assess = lambda *args, **kwargs: report
    control.refresh(report)
    return control


def _answer_next_dialog(label, *, before_click=None):
    def answer():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        if before_click is not None:
            before_click()
        button = next(button for button in dialog.buttons() if button.text() == label)
        button.click()

    QTimer.singleShot(0, answer)


def test_guided_primary_opens_project_image_preparation_without_certificate_or_atlas(tmp_path):
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    control = _prepared_control(studio)
    requested, atlas = [], []
    studio.project_flash_requested.connect(requested.append)
    studio.device_packs_requested.connect(atlas.append)
    control.show()
    app.processEvents()

    assert studio.app_settings.experience_mode is ExperienceMode.GUIDED
    assert not control.report.guardian_handoff_ready
    assert control.autopilot_button.text() == "Prepare local image installation…"
    control.autopilot_button.click()
    assert requested == []
    assert not control.isVisible()
    app.processEvents()

    assert requested == [control.project.project_id]
    assert atlas == []
    assert studio.worker is None
    assert studio.app_settings.experience_mode is ExperienceMode.GUIDED
    studio.close()


@pytest.mark.parametrize("drift", ["project", "source", "worker"])
def test_queued_project_handoff_rechecks_identity_and_busy_state(tmp_path, drift):
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    control = _prepared_control(studio)
    requested = []
    studio.project_flash_requested.connect(requested.append)
    control.autopilot_button.click()
    if drift == "project":
        other = studio.store.create("Unrelated project")
        studio.refresh(other.project_id)
    elif drift == "source":
        # The callback must reload the authoritative project, not trust its old UI snapshot.
        existing_get = studio.store.get
        studio.store.get = lambda identity: replace(
            existing_get(identity), original=replace(control.project.original, sha256="f" * 64)
        )
    else:
        studio.worker = object()
    app.processEvents()

    assert requested == []
    studio.worker = None
    studio.close()


def test_forge_waits_for_active_worker_before_project_image_handoff(tmp_path):
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    control = _prepared_control(studio)
    requested = []
    studio.project_flash_requested.connect(requested.append)
    control.online_worker = object()
    control.autopilot_button.click()
    app.processEvents()
    assert requested == []
    assert "Wait for the current operation" in control.status.text()
    control.online_worker = None
    control.close()
    studio.close()


def test_forge_closes_enclosing_genesis_before_dispatching_project_images(tmp_path):
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    mission = GuidedBuildMission(studio)
    mission.selected_index = 13
    control = _prepared_control(studio, mission)
    observed = []
    studio.project_flash_requested.connect(
        lambda identity: observed.append((identity, mission.isVisible(), control.isVisible()))
    )
    mission.show()
    control.show()
    app.processEvents()
    control.autopilot_button.click()
    app.processEvents()

    assert observed == [(control.project.project_id, False, False)]
    assert mission.state.install_requested
    assert mission.result() == QDialog.DialogCode.Accepted
    studio.close()


@pytest.mark.parametrize("choice", ["Cancel", "Finish local build • Recommended"])
def test_genesis_declining_local_installation_dispatches_nothing(tmp_path, choice):
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    mission = GuidedBuildMission(studio)
    mission.selected_index = 13
    requested = []
    studio.project_flash_requested.connect(requested.append)
    _answer_next_dialog(choice)
    mission._prompt_flash_choice()
    app.processEvents()

    assert requested == []
    assert not mission.state.install_requested
    mission.close()
    studio.close()


def test_genesis_confirmed_setup_closes_then_emits_exact_project_without_mode_change(tmp_path):
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    mission = GuidedBuildMission(studio)
    mission.selected_index = 13
    requested = []
    studio.project_flash_requested.connect(requested.append)
    _answer_next_dialog("Prepare local image installation…")
    mission._prompt_flash_choice()
    app.processEvents()

    assert requested == [studio.current_project.project_id]
    assert mission.state.install_requested
    assert mission.result() == QDialog.DialogCode.Accepted
    assert studio.app_settings.experience_mode is ExperienceMode.GUIDED
    assert studio.worker is None
    studio.close()


def test_genesis_project_changed_during_setup_confirmation_is_not_dispatched(tmp_path):
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    mission = GuidedBuildMission(studio)
    mission.selected_index = 13
    requested = []
    studio.project_flash_requested.connect(requested.append)
    other = studio.store.create("Different project")
    _answer_next_dialog(
        "Prepare local image installation…", before_click=lambda: studio.refresh(other.project_id)
    )
    mission._prompt_flash_choice()
    app.processEvents()

    assert requested == []
    assert not mission.state.install_requested
    assert "changed" in mission.status_text.text()
    mission.close()
    studio.close()


def test_prepared_forge_does_not_start_installation_or_certificate_resolution_automatically(
    tmp_path,
):
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    control = _prepared_control(studio)
    requested = []
    studio.project_flash_requested.connect(requested.append)
    control._start_autopilot()
    app.processEvents()

    assert not control.autopilot_active
    assert requested == []
    assert control.autopilot_button.text() == "Prepare local image installation…"
    assert control.resolve_buttons["physical-validation"].text() == "Review release evidence"
    assert not any(
        "consent" in button.text().casefold() for button in control.findChildren(QPushButton)
    )
    control.close()
    studio.close()


@pytest.mark.parametrize("state", ["completed", "failed", "cancelled", "delegation-interrupted"])
def test_local_subset_outcome_is_visible_without_becoming_production_or_first_boot_proof(
    tmp_path, state
):
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    mission = GuidedBuildMission(studio)
    context = GuidedContext(
        install_requested=True,
        local_image_state=state,
        local_image_summary="Inert fixture: one selected image operation was recorded.",
        local_image_count=1,
        local_image_boot_status="unverified",
    )
    mission._context = lambda: context
    mission.selected_index = 13
    mission._refresh()
    assert f"Local image operation: {state}" in mission.status_text.text()
    assert mission.action_button.text() == "Continue local image workflow…"
    assert "not full-ROM" in mission.status_text.text()
    flash, boot = GuidedMissionEngine().assess(context)[13:]
    assert flash.status is not GuidedStageStatus.COMPLETE
    assert boot.status is not GuidedStageStatus.COMPLETE
    assert "independent image readback" in " ".join(flash.evidence)
    assert "full-ROM first boot" in " ".join(boot.evidence)
    assert not context.flash_complete and not context.first_boot_verified
    assert not context.guardian_handoff_ready

    requested = []
    studio.project_flash_requested.connect(requested.append)
    mission.selected_index = 14
    mission._refresh()
    assert mission.action_button.isEnabled()
    assert mission.action_button.text() == "Review separate Android boot check…"
    mission.action_button.click()
    app.processEvents()
    assert requested == [studio.current_project.project_id]
    studio.close()


@pytest.mark.parametrize("binding", ["current", "other-project", "other-source", "untyped"])
def test_studio_context_uses_only_typed_exact_source_historical_subset_outcome(
    tmp_path, monkeypatch, binding
):
    QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    project = studio.current_project
    outcome = ProjectFlashOutcome(
        project.project_id,
        project.original.sha256,
        "completed",
        "Historical fixture only: selected writes completed, boot not checked.",
        1,
        tmp_path / "fixture-receipt.json",
    )
    if binding == "other-project":
        outcome = replace(outcome, project_id="different-project")
    elif binding == "other-source":
        outcome = replace(outcome, source_sha256="f" * 64)
    elif binding == "untyped":
        outcome = {"state": "completed"}
    monkeypatch.setattr(ProjectFlashPreparationService, "load_latest", lambda *_args: outcome)

    context = studio.guided_context()

    assert context.local_image_state == ("completed" if binding == "current" else "")
    assert context.local_image_count == (1 if binding == "current" else 0)
    assert not context.flash_complete and not context.first_boot_verified
    assert not context.boot_observation_stable
    if binding == "current":
        assert context.local_image_boot_status == "unverified"
    studio.close()
