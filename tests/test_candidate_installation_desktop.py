"""Actual Guided desktop clicks with real candidate evidence and inert transport.

Only tool transport and the background scheduler are replaced. Source, build,
base compatibility, AVB, composition, review and execution services are real;
the tiny simulation container is not Android firmware or a physical-device test.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from romverse.core.settings import AppSettings, ExperienceMode
from romverse.guardian.local_flash import LocalFlashState
from romverse.guardian.source_installation import SourceInstallationExecutor
from romverse.rom.base_image_compatibility import BaseImageCompatibilityService
from romverse.rom.candidate_avb import CandidateAvbService
from romverse.rom.candidate_installation import (
    CandidateInstallationRecipe,
    CandidateInstallationService,
)
from romverse.ui.main_window import MainWindow
from romverse.ui.project_flash import ProjectPreparationDialog
from romverse.ui.source_installation import SourceInstallationDialog
from tests.test_candidate_installation_integration import InertCandidatePhone, _fixture
from tests.test_candidate_installation_integration import signing_key as signing_key
from tests.test_source_installation_integration import _actual_changes, _expected_changes


class InertDesktopTransport:
    """No subprocess fallback: route each allowed tool to an inert implementation."""

    def __init__(self, build_tools, phone):
        self.build_tools = build_tools
        self.phone = phone

    def run(self, args, timeout=10, cwd=None):
        if Path(args[0]).name == "fastboot":
            return self.phone.run(args, timeout=timeout, cwd=cwd)
        return self.build_tools.run(args, timeout=timeout, cwd=cwd)


@pytest.fixture
def candidate_desktop(tmp_path, signing_key, monkeypatch):
    context = _fixture(tmp_path, signing_key)
    candidates = {
        row.name: (context.store.workspace / row.path).read_bytes() for row in context.build.outputs
    }
    # The expected bytes are independently derived from the pre-existing build
    # outputs and protected inputs, before the UI has prepared its composition.
    expected = {
        step.partition: (
            candidates[Path(step.image_member).name]
            if step.partition in {"super", "vbmeta_system_a"}
            else context.images[f"images/{Path(step.image_member).name}"]
        )
        for step in context.recipe.steps
        if step.action == "flash"
    }
    phone = InertCandidatePhone(expected)
    transport = InertDesktopTransport(context.runner, phone)
    fastboot = next(Path(tool.path) for tool in context.tools if tool.name == "Fastboot")
    fastboot.chmod(0o700)
    monkeypatch.setattr(
        "romverse.ui.toolchain_center.ToolVerifier.verify_extended",
        lambda _self: context.tools,
    )
    monkeypatch.setattr(
        "romverse.ui.project_flash.start_background", lambda worker: worker.execute()
    )
    monkeypatch.setattr("romverse.ui.local_flash.start_background", lambda worker: worker.execute())
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        context.store.workspace,
        pack_registry=context.registry,
        runner=transport,
        tool_statuses=context.tools,
        fastboot_executable=fastboot,
        app_icon_path=logo,
        app_settings=AppSettings(
            experience_mode=ExperienceMode.GUIDED,
            online_intelligence_enabled=False,
            desktop_notifications_enabled=False,
            reduced_motion=True,
        ),
    )
    window.rom_studio.current_project = context.store.get(context.project.project_id)
    window._observed_devices = [phone.device()]
    window.rom_studio.set_devices([phone.device()])
    routes = []
    navigate = window._navigate_route

    def track_route(route):
        routes.append(route)
        return navigate(route)

    monkeypatch.setattr(window, "_navigate_route", track_route)
    window.show()
    app.processEvents()
    yield SimpleNamespace(
        app=app,
        window=window,
        context=context,
        phone=phone,
        expected=expected,
        candidates=candidates,
        routes=routes,
    )
    if window._local_flash_dialog is not None:
        window._local_flash_dialog.worker = None
        window._local_flash_dialog.monitoring = False
        window._local_flash_dialog.reject()
        window._local_flash_dialog = None
    window.companion_center.transport.close()
    window.close()
    app.processEvents()


@pytest.mark.parametrize("accept", [False, True], ids=["decline", "install"])
def test_guided_desktop_keeps_real_candidate_authority_through_confirmation(
    candidate_desktop, accept
):
    desktop = candidate_desktop
    app, window, context, phone = desktop.app, desktop.window, desktop.context, desktop.phone
    phases, errors, outcomes = [], [], []
    before_build_calls = len(context.runner.calls)
    timer, timeout = QTimer(), QTimer()
    timeout.setSingleShot(True)

    def answer_confirmation():
        question = app.activeModalWidget()
        if not isinstance(question, QMessageBox):
            return
        assert question.windowTitle() == "Confirm source-declared installation"
        assert "53 declared actions" in question.text()
        assert "No data erase requested" in question.informativeText()
        assert question.defaultButton() is question.button(QMessageBox.StandardButton.Cancel)
        phases.append("confirmed" if accept else "declined")
        if accept:
            next(
                button
                for button in question.buttons()
                if question.buttonRole(button) == QMessageBox.ButtonRole.AcceptRole
            ).click()
        else:
            question.button(QMessageBox.StandardButton.Cancel).click()

    def interact():
        modal = app.activeModalWidget()
        try:
            if isinstance(modal, ProjectPreparationDialog) and "prepare" not in phases:
                phases.append("prepare")
                assert window._local_flash_dialog is modal
                assert modal.choice.currentData() == "candidate-installation"
                assert type(modal.candidate_service) is CandidateInstallationService
                assert type(modal.candidate_service.base) is BaseImageCompatibilityService
                assert type(modal.candidate_service.avb) is CandidateAvbService
                assert not phone.changes
                assert not modal.wipe.isChecked() and modal.reboot.isChecked()
                index = modal.base_choice.findData(context.procedure.project_id)
                assert index > 0, "The existing protected base must be selectable"
                modal.base_choice.setCurrentIndex(index)
                modal.prepare_button.click()
                assert modal.preparation is not None, modal.status.text()
            elif isinstance(modal, SourceInstallationDialog) and "review" not in phases:
                phases.append("review")
                assert window._local_flash_dialog is modal
                assert type(modal.service) is SourceInstallationExecutor
                assert type(modal.service.source_service) is CandidateInstallationService
                recipe = modal.recipe
                assert type(recipe) is CandidateInstallationRecipe
                assert recipe.project_id == context.project.project_id
                assert recipe.source_sha256 == context.project.original.sha256
                assert len(recipe.images) == 50 and len(recipe.steps) == 53
                assert sum(row.source_kind == "signed-final" for row in recipe.origins) == 2
                assert sum(row.source_kind == "base-package" for row in recipe.origins) == 48
                assert not recipe.wipe and recipe.reboot
                assert modal.images.rowCount() == 53
                assert modal.add_button.isHidden() and modal.remove_button.isHidden()
                assert window._experience_mode is ExperienceMode.GUIDED
                modal.review_button.click()
                assert modal.plan is not None, modal.status.text()
                assert not phone.changes
                review = modal.review.toPlainText()
                assert "2 rebuilt images + 48 exact-base images" in review
                assert "not OEM-trusted" in review
                assert recipe.procedure_source_sha256 in review
                assert recipe.build_receipt_digest in review
                assert recipe.composition_digest in review
                QTimer.singleShot(0, interact)
                modal.flash_button.click()
                assert phases[-1] == ("confirmed" if accept else "declined")
                outcomes.append((recipe, modal.result))
                if accept:
                    assert modal.result is not None, modal.status.text()
                    assert modal.result.state is LocalFlashState.COMPLETED, modal.result.summary
                    assert not modal.result.boot_verified
                    assert not modal.monitoring and modal.boot_report is None
                    assert modal.progress.value() == 53
                else:
                    assert modal.result is None
                    assert "cancelled" in modal.status.text().lower()
                    assert not phone.changes
                modal.close_button.click()
            elif isinstance(modal, QMessageBox):
                answer_confirmation()
        except BaseException as exc:
            errors.append(exc)
            timer.stop()
            if modal is not None:
                modal.reject()

    def expired():
        errors.append(AssertionError(f"Guided candidate journey did not finish: {phases}"))
        if app.activeModalWidget() is not None:
            app.activeModalWidget().reject()

    timer.timeout.connect(interact)
    timeout.timeout.connect(expired)
    timer.start(1)
    timeout.start(10000)
    try:
        assert window.rom_studio._request_project_flash(context.project.project_id)
    finally:
        timer.stop()
        timeout.stop()
        timer.timeout.disconnect(interact)
        timeout.timeout.disconnect(expired)
    if errors:
        raise errors[0]
    assert phases == ["prepare", "review", "confirmed" if accept else "declined"]
    assert window._local_flash_dialog is None
    assert window._experience_mode is ExperienceMode.GUIDED
    assert window.rom_studio.current_project.project_id == context.project.project_id
    assert desktop.routes == [], "This operation must not detour to certificates or Device Atlas"
    assert all(command[1] == "info_image" for command in context.runner.calls[before_build_calls:])
    recipe, result = outcomes[0]
    if not accept:
        assert not phone.changes and not phone.written
        return
    assert _actual_changes(phone) == _expected_changes()
    assert len(phone.written) == 50 and len(result.results) == 53
    assert dict(phone.written) == desktop.expected
    assert dict(phone.written)["super"] == desktop.candidates["super.img"]
    assert dict(phone.written)["super"] != context.images["images/super.img"]
    assert dict(phone.written)["vbmeta_system_a"] == desktop.candidates["vbmeta_system.img"]
    assert dict(phone.written)["vbmeta_system_a"] != context.images["images/vbmeta_system.img"]
    document = json.loads(result.receipt_path.read_text())
    assert document["format"] == "romverse.candidate-installation"
    assert document["candidate_provenance"]["base_receipt_digest"] == recipe.base_receipt_digest
    assert document["candidate_provenance"]["avb_receipt_digest"] == recipe.avb_receipt_digest
    assert document["candidate_provenance"]["build_receipt_digest"] == context.build.receipt_digest
    assert not document["readback_verified"] and not document["production_certification"]


def test_guided_candidate_preparation_cancel_never_prepares_or_contacts_phone(candidate_desktop):
    desktop = candidate_desktop
    opened = []
    before_build_calls = len(desktop.context.runner.calls)

    def cancel():
        modal = desktop.app.activeModalWidget()
        if isinstance(modal, ProjectPreparationDialog):
            opened.append(modal.choice.currentData())
            modal.close_button.click()

    QTimer.singleShot(0, cancel)
    assert desktop.window.rom_studio._request_project_flash(desktop.context.project.project_id)
    assert opened == ["candidate-installation"]
    assert not desktop.phone.calls and not desktop.phone.changes
    assert len(desktop.context.runner.calls) == before_build_calls
    assert desktop.context.service.base.load(desktop.context.project.project_id) is None
    assert desktop.context.service.avb.load(desktop.context.project.project_id) is None
    assert desktop.window._local_flash_dialog is None
    assert desktop.window._experience_mode is ExperienceMode.GUIDED
    assert not desktop.routes


def test_guided_no_phone_final_signed_preparation_reloads_and_waits(candidate_desktop):
    desktop = candidate_desktop
    app, window, context, phone = desktop.app, desktop.window, desktop.context, desktop.phone
    window._observed_devices = []
    window.rom_studio.set_devices([])
    phases, errors = [], []
    timer, timeout = QTimer(), QTimer()
    timeout.setSingleShot(True)

    def interact():
        modal = app.activeModalWidget()
        try:
            if isinstance(modal, ProjectPreparationDialog) and "prepare" not in phases:
                phases.append("prepare")
                modal.base_choice.setCurrentIndex(
                    modal.base_choice.findData(context.procedure.project_id)
                )
                modal.prepare_button.click()
            elif isinstance(modal, SourceInstallationDialog) and "wait" not in phases:
                phases.append("wait")
                recipe = modal.recipe
                reconstructed = CandidateInstallationService(
                    context.store,
                    context.registry,
                    context.tools,
                    context.runner,
                ).prepare(context.project.project_id, context.procedure.project_id)
                assert reconstructed == recipe
                assert recipe.signing_receipt_digest == context.signing.receipt_digest
                assert recipe.signed_assembly_receipt_digest == context.assembly.receipt_digest
                assert all(
                    "build-candidates" not in origin.relative_path
                    for origin in recipe.origins
                    if origin.source_kind == "signed-final"
                )
                assert modal.session.selected_device() is None
                assert modal.session.plan is None and modal.session.result is None
                assert "Connect the intended phone by USB" in modal.status.text()
                assert modal.guided_primary.text() == "Connect phone by USB"
                assert not modal.guided_primary.isEnabled()
                modal.close_button.click()
        except BaseException as exc:
            errors.append(exc)
            timer.stop()
            if modal is not None:
                modal.reject()

    def expired():
        errors.append(AssertionError(f"No-phone final-signed journey did not finish: {phases}"))
        modal = app.activeModalWidget()
        if modal is not None:
            modal.reject()

    timer.timeout.connect(interact)
    timeout.timeout.connect(expired)
    timer.start(1)
    timeout.start(10000)
    try:
        assert window.rom_studio._request_project_flash(context.project.project_id)
    finally:
        timer.stop()
        timeout.stop()
        timer.timeout.disconnect(interact)
        timeout.timeout.disconnect(expired)
    if errors:
        raise errors[0]
    assert phases == ["prepare", "wait"]
    assert not phone.calls and not phone.changes and not phone.written
    assert window._local_flash_dialog is None
