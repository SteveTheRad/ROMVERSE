from __future__ import annotations

from dataclasses import replace

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton

from romverse.core.settings import ExperienceMode
from romverse.rom.guided import (
    VERIFIED_ROM_INSTALLATION_ACTION,
    GuidedContext,
    GuidedMissionEngine,
    GuidedStageStatus,
)
from romverse.rom.project_flash import ProjectFlashOutcome, ProjectFlashPreparationService
from romverse.rom.readiness import BuildGate, GateStatus
from romverse.rom.source_installation_history import SourceInstallationOutcome
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
    assert control.autopilot_button.text() == VERIFIED_ROM_INSTALLATION_ACTION
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
    _answer_next_dialog(VERIFIED_ROM_INSTALLATION_ACTION)
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
        VERIFIED_ROM_INSTALLATION_ACTION,
        before_click=lambda: studio.refresh(other.project_id),
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
    assert control.autopilot_button.text() == VERIFIED_ROM_INSTALLATION_ACTION
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


@pytest.mark.parametrize("state,count", [("completed", 53), ("failed", 9), ("attention", 0)])
@pytest.mark.parametrize("stage_index", [13, 14])
def test_source_procedure_outcome_routes_failure_directly_to_diagnosis_never_reinstallation(
    tmp_path, state, count, stage_index
):
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    mission = GuidedBuildMission(studio)
    context = GuidedContext(
        install_requested=True,
        source_installation_state=state,
        source_installation_summary="Historical inert-source procedure outcome.",
        source_installation_completed_count=count,
        source_installation_expected_count=53,
        source_installation_boot_status="stable" if state == "completed" else "unverified",
    )
    mission._context = lambda: context
    mission.selected_index = stage_index
    mission._refresh()
    flash, boot = GuidedMissionEngine().assess(context)[13:]
    assert (flash.status is GuidedStageStatus.COMPLETE) == (state == "completed")
    assert boot.status is GuidedStageStatus.ATTENTION
    assert not context.flash_complete and not context.first_boot_verified
    needs_diagnosis = state in {"failed", "attention"}
    assert (
        "needs diagnosis" if needs_diagnosis else "Historical Android boot"
    ) in mission.status_text.text()
    assert mission.action_button.text() == (
        "Diagnose interrupted installation…"
        if needs_diagnosis
        else "Review installation and boot results…"
    )
    assert mission.action_button.isEnabled()
    history, recovery, installation, atlas = [], [], [], []
    studio.source_installation_history_requested.connect(history.append)
    studio.source_installation_recovery_requested.connect(
        lambda project_id, source_sha256: recovery.append((project_id, source_sha256))
    )
    studio.project_flash_requested.connect(installation.append)
    studio.device_packs_requested.connect(atlas.append)
    mission.action_button.click()
    app.processEvents()
    if needs_diagnosis:
        assert history == []
        assert recovery == [
            (studio.current_project.project_id, studio.current_project.original.sha256)
        ]
    else:
        assert history == [studio.current_project.project_id]
        assert recovery == []
    assert installation == atlas == []
    assert not mission.isVisible()
    studio.close()


def test_genesis_automatically_enters_read_only_diagnosis_for_interrupted_installation(
    tmp_path,
):
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    mission = GuidedBuildMission(studio)
    context = GuidedContext(
        install_requested=True,
        source_installation_state="failed",
        source_installation_summary="Sealed interrupted-installation fixture.",
        source_installation_completed_count=9,
        source_installation_expected_count=53,
    )
    mission._context = lambda: context
    recovery, installation, history = [], [], []
    studio.source_installation_recovery_requested.connect(
        lambda project_id, source_sha256: recovery.append((project_id, source_sha256))
    )
    studio.project_flash_requested.connect(installation.append)
    studio.source_installation_history_requested.connect(history.append)

    mission.show()
    assert "Checking what happened" in mission.status_text.text()
    app.processEvents()
    app.processEvents()

    assert recovery == [
        (studio.current_project.project_id, studio.current_project.original.sha256)
    ]
    assert installation == history == []
    assert not mission.isVisible()
    studio.close()


def test_genesis_automatic_diagnosis_is_one_shot_and_rechecks_sealed_binding(tmp_path):
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    mission = GuidedBuildMission(studio)
    context = GuidedContext(
        install_requested=True,
        source_installation_state="attention",
        source_installation_summary="Sealed attention fixture.",
        source_installation_completed_count=0,
        source_installation_expected_count=53,
    )
    mission._context = lambda: context
    recovery = []
    studio.source_installation_recovery_requested.connect(
        lambda project_id, source_sha256: recovery.append((project_id, source_sha256))
    )

    mission.show()
    mission._schedule_automatic_source_recovery()
    context = replace(context, source_installation_state="completed")
    app.processEvents()

    assert recovery == []
    assert mission.isVisible()
    assert "did not attribute or retry" in mission.status_text.text()
    mission.close()
    studio.close()


def test_genesis_waits_until_busy_work_finishes_before_automatic_diagnosis(tmp_path):
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    mission = GuidedBuildMission(studio)
    context = GuidedContext(
        install_requested=True,
        source_installation_state="cancelled",
        source_installation_summary="Sealed partial cancellation fixture.",
        source_installation_completed_count=1,
        source_installation_expected_count=53,
    )
    mission._context = lambda: context
    recovery = []
    studio.source_installation_recovery_requested.connect(
        lambda project_id, source_sha256: recovery.append((project_id, source_sha256))
    )
    studio.worker = object()

    mission.show()
    app.processEvents()
    assert recovery == []
    assert mission.isVisible()

    studio.worker = None
    mission._refresh(select_current=True)
    app.processEvents()
    app.processEvents()
    assert len(recovery) == 1
    assert not mission.isVisible()
    studio.close()


def test_genesis_does_not_auto_route_completed_installation_history(tmp_path):
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    mission = GuidedBuildMission(studio)
    context = GuidedContext(
        install_requested=True,
        source_installation_state="completed",
        source_installation_summary="Completed historical fixture.",
        source_installation_completed_count=53,
        source_installation_expected_count=53,
        source_installation_boot_status="stable",
    )
    mission._context = lambda: context
    recovery = []
    studio.source_installation_recovery_requested.connect(
        lambda project_id, source_sha256: recovery.append((project_id, source_sha256))
    )

    mission.show()
    app.processEvents()

    assert recovery == []
    assert mission.isVisible()
    mission.selected_index = 13
    mission._refresh()
    assert mission.action_button.text() == "Review installation and boot results…"
    mission.close()
    studio.close()


def test_source_completed_label_without_complete_measured_action_count_is_not_green():
    context = GuidedContext(
        install_requested=True,
        source_installation_state="completed",
        source_installation_completed_count=52,
        source_installation_expected_count=53,
    )
    assert GuidedMissionEngine().assess(context)[13].status is GuidedStageStatus.ATTENTION


@pytest.mark.parametrize("drift", ["project", "source", "worker"])
def test_queued_source_history_rechecks_project_source_and_worker(tmp_path, drift):
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    mission = GuidedBuildMission(studio)
    history = []
    studio.source_installation_history_requested.connect(history.append)
    project = studio.current_project
    mission._handoff_source_installation_history()
    if drift == "project":
        studio.refresh(studio.store.create("Other history").project_id)
    elif drift == "source":
        get = studio.store.get
        studio.store.get = lambda identity: replace(
            get(identity), original=replace(project.original, sha256="f" * 64)
        )
    else:
        studio.worker = object()
    app.processEvents()
    assert history == []
    studio.worker = None
    studio.close()


@pytest.mark.parametrize("drift", ["project", "source", "worker"])
def test_queued_source_recovery_rechecks_project_source_and_worker(tmp_path, drift):
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    mission = GuidedBuildMission(studio)
    recovery = []
    studio.source_installation_recovery_requested.connect(
        lambda project_id, source_sha256: recovery.append((project_id, source_sha256))
    )
    project = studio.current_project
    mission._handoff_source_installation_recovery()
    if drift == "project":
        studio.refresh(studio.store.create("Other diagnosis").project_id)
    elif drift == "source":
        get = studio.store.get
        studio.store.get = lambda identity: replace(
            get(identity), original=replace(project.original, sha256="f" * 64)
        )
    else:
        studio.worker = object()
    app.processEvents()
    assert recovery == []
    studio.worker = None
    studio.close()


@pytest.mark.parametrize("binding", ["current", "other-project", "other-source", "untyped"])
def test_studio_context_uses_only_typed_current_source_procedure_history(
    tmp_path, monkeypatch, binding
):
    QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    project = studio.current_project
    outcome = SourceInstallationOutcome(
        state="completed",
        summary="Historical UI fixture only.",
        receipt_path=tmp_path / "fixture.json",
        source_sha256=project.original.sha256,
        completed_count=53,
        expected_count=53,
        boot_status="Historical stable boot fixture",
        project_id=project.project_id,
    )
    if binding == "other-project":
        outcome = replace(outcome, project_id="unrelated-project")
    elif binding == "other-source":
        outcome = replace(outcome, source_sha256="f" * 64)
    elif binding == "untyped":
        outcome = {"state": "completed"}
    monkeypatch.setattr(
        "romverse.ui.rom_studio.load_latest_source_installation", lambda *_args: outcome
    )
    context = studio.guided_context()
    assert context.source_installation_state == ("completed" if binding == "current" else "")
    assert context.source_installation_completed_count == (53 if binding == "current" else 0)
    assert not context.flash_complete and not context.first_boot_verified
    assert not context.boot_observation_stable
    studio.close()
