"""Candidate preparation UI; inert build fixture, no device or external commands."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QScrollArea

from romverse.rom.source_installation import SourceInstallationService
from romverse.ui.project_flash import ProjectPreparationDialog, ProjectPreparationWorker
from tests.test_candidate_installation import _fixture


@pytest.fixture
def prepared_ui(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    context = _fixture(tmp_path)
    monkeypatch.setattr(
        "romverse.ui.project_flash.start_background", lambda worker: worker.execute()
    )
    dialog = ProjectPreparationDialog(
        context.service.built,
        context.project.project_id,
        source_service=SourceInstallationService(context.store),
        candidate_service=context.service,
    )
    dialog.show()
    app.processEvents()
    yield app, dialog, context
    dialog.close()
    app.processEvents()


def test_complete_candidate_preparation_is_available_without_manual_partition_entry(prepared_ui):
    app, dialog, context = prepared_ui
    assert dialog.choice.currentData() == "candidate-installation"
    assert dialog.base_controls.isVisible() and dialog.source_controls.isVisible()
    assert not dialog.wipe.isChecked() and dialog.reboot.isChecked()
    dialog.base_choice.setCurrentIndex(dialog.base_choice.findData(context.procedure.project_id))
    dialog.prepare_button.click()
    app.processEvents()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.preparation is not None
    assert len(dialog.preparation.steps) == 53
    assert sum(origin.source_kind == "rebuilt" for origin in dialog.preparation.origins) == 2


def test_missing_base_has_direct_in_place_action_and_starts_no_worker(prepared_ui):
    _app, dialog, _context = prepared_ui
    dialog.base_choice.setCurrentIndex(0)
    dialog.prepare_button.click()
    assert dialog.preparation is None and dialog.worker is None
    assert "Choose the base package below" in dialog.status.text()
    assert dialog.base_file_button.isEnabled()
    assert dialog.prepare_button.isEnabled()


def test_user_can_switch_from_selected_zip_back_to_imported_package(prepared_ui, monkeypatch):
    _app, dialog, context = prepared_ui
    source = context.store.original_path(context.procedure.project_id)
    monkeypatch.setattr(
        "romverse.ui.project_flash.QFileDialog.getOpenFileName", lambda *_args: (str(source), "")
    )
    dialog.base_file_button.click()
    assert dialog.procedure_path == source
    assert dialog.base_choice.isEnabled()
    dialog.base_choice.setCurrentIndex(dialog.base_choice.findData(context.procedure.project_id))
    assert dialog.procedure_path is None
    assert dialog.base_file_button.text() == "Choose a base package ZIP…"


def test_imported_identical_base_reuses_project_and_never_duplicates_original(
    prepared_ui, tmp_path
):
    _app, dialog, context = prepared_ui
    selected = tmp_path / "same-package-new-name.zip"
    selected.write_bytes(context.store.original_path(context.procedure.project_id).read_bytes())
    before_projects = context.store.list_projects()
    before_originals = set(context.store.originals_root.iterdir())
    dialog.procedure_path = selected
    dialog.prepare_button.click()
    assert dialog.preparation.procedure_project_id == context.procedure.project_id
    assert context.store.list_projects() == before_projects
    assert set(context.store.originals_root.iterdir()) == before_originals


def test_prepare_failure_keeps_inputs_and_next_action_in_same_dialog(prepared_ui, monkeypatch):
    _app, dialog, context = prepared_ui
    dialog.base_choice.setCurrentIndex(dialog.base_choice.findData(context.procedure.project_id))

    def unavailable(*_args, **_kwargs):
        raise ValueError("The base boot image does not match. Choose the exact build base package.")

    monkeypatch.setattr(context.service, "prepare", unavailable)
    dialog.prepare_button.click()
    assert dialog.isVisible() and dialog.worker is None
    assert dialog.preparation is None and dialog.prepare_button.isEnabled()
    assert dialog.base_choice.currentData() == context.procedure.project_id
    assert "Choose the exact build base package" in dialog.status.text()


def test_candidate_worker_does_not_silently_return_source_recipe(prepared_ui, monkeypatch):
    _app, dialog, context = prepared_ui
    dialog.base_choice.setCurrentIndex(dialog.base_choice.findData(context.procedure.project_id))
    # Project ID alone is insufficient: a buggy service must not change routes.
    from dataclasses import replace

    wrong = replace(context.recipe, project_id=context.project.project_id)
    monkeypatch.setattr(context.service, "prepare", lambda *_args, **_kwargs: wrong)
    dialog.prepare_button.click()
    assert dialog.preparation is None
    assert "mismatched project evidence" in dialog.status.text()
    assert dialog.prepare_button.isEnabled()


def test_preparation_body_scrolls_while_actions_remain_available(prepared_ui):
    app, dialog, _context = prepared_ui
    dialog.setMinimumHeight(0)
    dialog.resize(540, 420)
    app.processEvents()
    scroll = dialog.findChild(QScrollArea)
    assert scroll is not None and scroll.widgetResizable()
    assert scroll.verticalScrollBar().maximum() > 0
    assert dialog.prepare_button.isVisible() and dialog.close_button.isVisible()
    assert (
        dialog.prepare_button.mapTo(dialog, dialog.prepare_button.rect().bottomRight()).y()
        < dialog.height()
    )


def test_candidate_worker_without_service_fails_without_falling_back():
    class NoPreparation:
        def prepare(self, *_args, **_kwargs):
            pytest.fail("A missing candidate service must never invoke the manual/source route.")

    worker = ProjectPreparationWorker(NoPreparation(), "fixture", "candidate-installation")
    errors = []
    worker.signals.failed.connect(errors.append)
    worker.execute()
    assert errors == ["Rebuilt installation is unavailable in this context."]


def test_unselected_base_file_does_not_import_anything(prepared_ui, monkeypatch):
    _app, dialog, context = prepared_ui
    before = context.store.list_projects()
    monkeypatch.setattr(
        "romverse.ui.project_flash.QFileDialog.getOpenFileName", lambda *_args: ("", "")
    )
    dialog.base_file_button.click()
    assert dialog.procedure_path is None
    assert context.store.list_projects() == before


def test_base_import_rejects_linked_file_before_creating_project(prepared_ui, tmp_path):
    _app, _dialog, context = prepared_ui
    link = tmp_path / "linked.zip"
    try:
        link.symlink_to(context.store.original_path(context.procedure.project_id))
    except OSError as exc:
        if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows runner lacks privilege for this real symlink fixture")
        raise
    before = context.store.list_projects()
    from romverse.rom.models import ProjectError

    with pytest.raises(ProjectError, match="missing, linked or unsafe"):
        context.service.import_procedure(Path(link))
    assert context.store.list_projects() == before


def test_missing_saved_project_during_base_lookup_stays_an_actionable_dialog(
    prepared_ui, monkeypatch
):
    _app, dialog, context = prepared_ui
    from romverse.rom.models import ProjectError

    def missing(_project_id):
        raise ProjectError("Project was removed while setup was open")

    monkeypatch.setattr(context.service.base, "load", missing)
    other = ProjectPreparationDialog(
        context.service.built,
        context.project.project_id,
        source_service=context.service.sources,
        candidate_service=context.service,
    )
    assert "saved project/base selection could not be read" in other.status.text()
    assert other.prepare_button.isEnabled() and other.close_button.isEnabled()
    other.close()
    dialog.base_choice.setCurrentIndex(0)
    dialog._show_error("Current project needs checking; no phone action started.")
    assert "Current project needs checking" in dialog.status.text()
    assert dialog.prepare_button.isEnabled() and dialog.close_button.isEnabled()
