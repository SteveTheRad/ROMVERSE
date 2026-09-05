"""Full source-declared installation journeys using only inert synthetic firmware.

These tests execute production services, never a subprocess or a physical device.
The ordered expectation is independent of the production recipe definition.
"""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from romverse.core.settings import AppSettings, ExperienceMode
from romverse.device.models import DeviceState
from romverse.guardian.local_flash import LocalFlashError, LocalFlashService, LocalFlashState
from romverse.guardian.local_transition import (
    LocalTransitionPlan,
    LocalTransitionResult,
    LocalTransitionTarget,
)
from romverse.guardian.source_installation import SourceInstallationExecutor
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.local_boot import LocalBootError, LocalBootService
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.source_installation import SourceInstallationService
from romverse.ui.main_window import MainWindow
from romverse.ui.project_flash import ProjectPreparationDialog
from romverse.ui.source_installation import SourceInstallationDialog
from romverse.ui.source_operation_session import SourceOperationPhase, SourceOperationSession
from scripts.simulate_source_installation import InstallationPhone
from scripts.simulate_source_installation import main as simulate_source_installation

PHYSICAL = [
    "abl",
    "aop",
    "aop_config",
    "bluetooth",
    "boot",
    "cpucp",
    "cpucp_dtb",
    "dcp",
    "devcfg",
    "dsp",
    "dtbo",
    "featenabler",
    "hyp",
    "hyp_ac_config",
    "idmanager",
    "imagefv",
    "init_boot",
    "keymaster",
    "modem",
    "modemfirmware",
    "multiimgqti",
    "pdp",
    "pdp_cdb",
    "pvmfw",
    "qtvm_dtbo",
    "qupfw",
    "recovery",
    "secretkeeper",
    "shrm",
    "soccp",
    "soccp_dcd",
    "soccp_debug",
    "spuservice",
    "tme_config",
    "tme_fw",
    "tme_seq_patch",
    "tz",
    "tz_ac_config",
    "tz_qti_config",
    "uefi",
    "uefisecapp",
    "vendor_boot",
    "vm-bootsys",
    "xbl",
    "xbl_ac_config",
    "xbl_config",
    "xbl_ramdump",
]
IMAGE_NAMES = (*PHYSICAL, "super", "vbmeta_system", "vbmeta")
PACKAGE_ROOT = "outputs/popsicle_OS4.0.0.23_SIMULATION_ONLY"
SCRIPT_FIXTURE = Path(__file__).parent / "fixtures" / "source-installation" / "flash_all.sh"
SCRIPT_SHA256 = "589afffba7bc1e3528f936caeb9fe3bfd43da8d4017d0b5d4562c6f9e2be41ac"


def _mutate_same_stat(path: Path) -> None:
    previous = path.stat()
    contents = path.read_bytes()
    path.chmod(0o600)
    path.write_bytes(bytes((contents[0] ^ 1,)) + contents[1:])
    os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    assert path.stat().st_size == previous.st_size
    assert path.stat().st_mtime_ns == previous.st_mtime_ns


def _expected_changes(wipe=False, reboot=True):
    operations = [("set_active", "a")]
    operations.extend(("flash", name + "_a") for name in PHYSICAL)
    operations.extend(
        (("-S", "700M", "flash", "super"), ("flash", "vbmeta_system_a"), ("flash", "vbmeta_a"))
    )
    if wipe:
        operations.extend((("erase", "metadata"), ("erase", "userdata")))
    operations.append(("set_active", "a"))
    if reboot:
        operations.append(("reboot",))
    return operations


def _actual_changes(phone):
    return [operation[:-1] if "flash" in operation else operation for operation in phone.changes]


@dataclass
class InstallationContext:
    source: SourceInstallationService
    project_id: str
    phone: InstallationPhone
    flash: LocalFlashService
    adb: Path
    image_bytes: dict[str, bytes]

    def recipe(self, **kwargs):
        return self.source.prepare(self.project_id, **kwargs)


def _synthetic_package(path, *, change_script=False, missing_image="", member_prefix=""):
    script = SCRIPT_FIXTURE.read_bytes()
    assert hashlib.sha256(script).hexdigest() == SCRIPT_SHA256
    members = {"flash_all.sh": script + (b"\n# changed\n" if change_script else b"")}
    image_bytes = {
        f"images/{name}.img": f"INERT SOURCE INSTALLATION IMAGE {name}\n".encode() * 4
        for name in IMAGE_NAMES
        if name != missing_image
    }
    members.update(image_bytes)
    checksums = "".join(
        f"{hashlib.sha256(contents).hexdigest()}  ./{name}\n" for name, contents in members.items()
    )
    with zipfile.ZipFile(path, "w") as archive:
        for name, contents in members.items():
            archive.writestr(f"{member_prefix}{PACKAGE_ROOT}/{name}", contents)
        archive.writestr(f"{member_prefix}{PACKAGE_ROOT}/SHA256SUMS", checksums)
    return image_bytes


@pytest.fixture
def installation(tmp_path, request):
    package = tmp_path / "HyperOS4-Xiaomi17ProMax-SIMULATION.zip"
    image_bytes = _synthetic_package(package, member_prefix=getattr(request, "param", ""))
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(
        store.create("SIMULATION full installation").project_id, package
    )
    phone = InstallationPhone()
    for name in ("adb", "fastboot"):
        tool = tmp_path / name
        tool.write_bytes(b"INERT TOOL BYTES - NEVER EXECUTED\n")
        tool.chmod(0o700)
    flash = LocalFlashService(store.workspace, phone, tmp_path / "fastboot")
    return InstallationContext(
        SourceInstallationService(store),
        project.project_id,
        phone,
        flash,
        tmp_path / "adb",
        image_bytes,
    )


def _recipe_operations(recipe):
    operations = []
    for step in recipe.steps:
        if step.action == "flash":
            operation = ("flash", step.partition)
            if step.chunk_size:
                operation = ("-S", step.chunk_size, *operation)
        elif step.action == "set_active":
            operation = (step.action, step.slot)
        elif step.action == "erase":
            operation = (step.action, step.partition)
        else:
            operation = (step.action,)
        operations.append(operation)
    return operations


@pytest.mark.parametrize(
    "wipe,reboot", [(False, True), (True, True), (False, False), (True, False)]
)
def test_real_parser_derives_every_source_declared_step_without_running_anything(
    installation, wipe, reboot
):
    recipe = installation.recipe(wipe=wipe, reboot=reboot)
    assert len(recipe.images) == 50
    assert _recipe_operations(recipe) == _expected_changes(wipe=wipe, reboot=reboot)
    assert recipe.expected_product == "popsicle"
    assert recipe.target_slot == "a"
    assert recipe.requires_critical_unlock
    assert recipe.script_sha256 == SCRIPT_SHA256
    assert installation.source.verify(recipe) == recipe
    assert installation.phone.calls == []
    assert all(
        image.sha256
        == hashlib.sha256(
            installation.image_bytes[image.member.removeprefix(PACKAGE_ROOT + "/")]
        ).hexdigest()
        for image in recipe.images
    )


@pytest.mark.parametrize("change", ["changed-script", "missing-super", "missing-vbmeta"])
def test_unsupported_or_incomplete_package_is_not_a_partial_automatic_recipe(tmp_path, change):
    package = tmp_path / "HyperOS4-Xiaomi17ProMax-SIMULATION.zip"
    _synthetic_package(
        package,
        change_script=change == "changed-script",
        missing_image=change.removeprefix("missing-") if change.startswith("missing-") else "",
    )
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Incomplete SIMULATION").project_id, package)
    with pytest.raises(ProjectError):
        SourceInstallationService(store).prepare(project.project_id)


def test_source_bytes_changed_with_restored_size_and_mtime_cannot_revalidate(installation):
    recipe = installation.recipe()
    _mutate_same_stat(recipe.archive_path)
    with pytest.raises(ProjectError, match="SHA-256 changed"):
        installation.source.verify(recipe)
    assert installation.phone.calls == []


@pytest.mark.parametrize("change", ["wipe", "slot", "image", "order"])
def test_forged_preview_cannot_widen_source_declared_actions(installation, change):
    recipe = installation.recipe()
    if change == "wipe":
        forged = replace(recipe, wipe=True)
    elif change == "slot":
        forged = replace(recipe, steps=(replace(recipe.steps[0], slot="b"), *recipe.steps[1:]))
    elif change == "image":
        forged = replace(
            recipe, images=(replace(recipe.images[0], sha256="0" * 64), *recipe.images[1:])
        )
    else:
        forged = replace(recipe, steps=(recipe.steps[1], recipe.steps[0], *recipe.steps[2:]))
    with pytest.raises(ProjectError):
        installation.source.verify(forged)
    assert installation.phone.calls == []


def _executor(context):
    return SourceInstallationExecutor(context.source, context.flash, context.adb)


def _execute(executor, plan, **kwargs):
    return executor.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True, **kwargs)


@pytest.mark.parametrize("wipe,reboot", [(False, True), (True, True), (False, False)])
def test_complete_production_sequence_matches_source_and_is_transport_evidence_only(
    installation, wipe, reboot
):
    context = installation
    executor = _executor(context)
    recipe = context.recipe(wipe=wipe, reboot=reboot)
    plan = executor.inspect(context.phone.device(), recipe)
    assert context.phone.changes == []
    assert plan.current_slot == "b"
    result = _execute(executor, plan)
    assert result.state is LocalFlashState.COMPLETED, result.summary
    assert _actual_changes(context.phone) == _expected_changes(wipe=wipe, reboot=reboot)
    assert len(context.phone.written) == 50
    assert len(result.results) == len(recipe.steps)
    assert result.phone_change_attempted and result.phone_state_uncertain
    assert not result.boot_verified
    assert result.reboot_requested is reboot
    assert context.phone.mode == ("android" if reboot else "bootloader")
    assert context.phone.slot == "a"
    for image, (partition, written) in zip(recipe.images, context.phone.written, strict=True):
        assert hashlib.sha256(written).hexdigest() == image.sha256, partition
    document = json.loads(result.receipt_path.read_text())
    assert document["recipe_digest"] == recipe.recipe_digest
    assert document["source_sha256"] == recipe.source_sha256
    assert document["boot_verified"] is False
    assert document["readback_verified"] is False
    assert document["production_certification"] is False
    assert context.phone.serial not in result.receipt_path.read_text()
    assert context.flash.audit.verify().valid


@pytest.mark.parametrize("condition", ["wrong-product", "critical-locked", "locked", "fastbootd"])
def test_known_wrong_target_or_missing_required_source_conditions_never_change_phone(
    installation, condition
):
    context = installation
    device = context.phone.device()
    if condition == "wrong-product":
        context.phone.product = "other-phone"
    elif condition == "critical-locked":
        context.phone.critical_unlocked = False
    elif condition == "locked":
        context.phone.unlocked = False
    else:
        context.phone.mode = "fastbootd"
    with pytest.raises(LocalFlashError):
        _executor(context).inspect(device, context.recipe())
    # The simulated other phone reports the same super capacity as popsicle.
    assert context.phone.changes == []


@pytest.mark.parametrize("risk,digest", [(False, "correct"), (True, "wrong")])
def test_invalid_confirmation_does_not_even_activate_slot(installation, risk, digest):
    context = installation
    executor = _executor(context)
    plan = executor.inspect(context.phone.device(), context.recipe())
    with pytest.raises(LocalFlashError):
        executor.execute(
            plan,
            accepted_digest=plan.plan_digest if digest == "correct" else "not-reviewed",
            risk_accepted=risk,
        )
    assert context.phone.changes == []
    assert context.phone.slot == "b"


@pytest.mark.parametrize("count", [0, 1, 2, 48, 50, 52])
def test_stop_between_steps_never_runs_the_next_change_or_implicitly_reboots(installation, count):
    context = installation
    executor = _executor(context)
    plan = executor.inspect(context.phone.device(), context.recipe())
    result = _execute(executor, plan, should_cancel=lambda: len(context.phone.changes) >= count)
    assert result.state is LocalFlashState.CANCELLED, result.summary
    assert _actual_changes(context.phone) == _expected_changes()[:count]
    assert result.phone_change_attempted is bool(count)
    assert result.phone_state_uncertain is bool(count)
    assert not result.reboot_requested and not result.boot_verified
    assert context.phone.mode == "bootloader"
    assert not any(operation[0] == "erase" for operation in context.phone.changes)


@pytest.mark.parametrize("index", [0, 1, 47, 48, 49, 50, 51, 52, 53, 54])
def test_failed_command_stops_the_exact_full_wipe_sequence_without_automatic_retry(
    installation, index
):
    context = installation
    executor = _executor(context)
    plan = executor.inspect(context.phone.device(), context.recipe(wipe=True))
    context.phone.fail_change_index = index
    result = _execute(executor, plan)
    assert result.state is LocalFlashState.FAILED, result.summary
    assert _actual_changes(context.phone) == _expected_changes(wipe=True)[: index + 1]
    assert result.phone_change_attempted and result.phone_state_uncertain
    assert not result.boot_verified
    assert len(result.results) == index + 1
    assert not result.results[-1].completed
    with pytest.raises(LocalFlashError):
        _execute(executor, plan)
    assert len(context.phone.changes) == index + 1


@pytest.mark.parametrize("change", ["source", "target", "tool"])
def test_changes_after_review_prevent_initial_slot_change(installation, change):
    context = installation
    executor = _executor(context)
    plan = executor.inspect(context.phone.device(), context.recipe())
    if change == "source":
        _mutate_same_stat(plan.recipe.archive_path)
    elif change == "target":
        context.phone.product = "wrong-product"
    else:
        _mutate_same_stat(context.flash.fastboot_path)
    result = _execute(executor, plan)
    assert result.state is LocalFlashState.REJECTED
    assert not result.phone_change_attempted
    assert not result.boot_verified
    assert context.phone.changes == []


@pytest.mark.parametrize("conflict", ["manufacturer", "codename"])
def test_known_device_identity_contradiction_cannot_be_hidden_by_matching_product(
    installation, conflict
):
    context = installation
    device = replace(
        context.phone.device(),
        **({"manufacturer": "Samsung"} if conflict == "manufacturer" else {"codename": "komodo"}),
    )
    with pytest.raises(LocalFlashError):
        _executor(context).inspect(device, context.recipe())
    assert context.phone.changes == []


@pytest.mark.parametrize("installation", ["./"], indirect=True)
def test_safe_dot_prefixed_archive_can_install_and_bind_real_boot_receipt(installation):
    context = installation
    executor = _executor(context)
    plan = executor.inspect(context.phone.device(), context.recipe())
    result = _execute(executor, plan)
    assert result.state is LocalFlashState.COMPLETED, result.summary
    monitor = LocalBootService(context.flash, context.adb)
    session = monitor.begin(context.phone.device(), result)
    report = monitor.stop(session)
    assert report.status == "cancelled"
    assert not report.boot_observed
    assert _actual_changes(context.phone) == _expected_changes()


def test_other_phone_or_tampered_installation_receipt_cannot_supply_boot_binding(installation):
    context = installation
    executor = _executor(context)
    plan = executor.inspect(context.phone.device(), context.recipe())
    result = _execute(executor, plan)
    assert result.state is LocalFlashState.COMPLETED
    monitor = LocalBootService(context.flash, context.adb)
    before = tuple(context.phone.calls)
    with pytest.raises(LocalBootError):
        monitor.begin(replace(context.phone.device(), serial="UNRELATED-PHONE-0002"), result)
    document = json.loads(result.receipt_path.read_text())
    document["source_sha256"] = "0" * 64
    result.receipt_path.write_text(json.dumps(document))
    with pytest.raises(LocalBootError):
        monitor.begin(context.phone.device(), result)
    assert tuple(context.phone.calls) == before


@pytest.fixture
def installation_dialog(installation, monkeypatch, request):
    context = installation
    app = QApplication.instance() or QApplication([])
    workers = []
    monkeypatch.setattr("romverse.ui.local_flash.start_background", workers.append)
    wrong = replace(
        context.phone.device(), serial="OTHER-SIMULATED-0002", product="komodo", codename="komodo"
    )
    boot = LocalBootService(
        context.flash,
        context.adb,
        monotonic_clock=lambda: context.phone.seconds,
        utc_clock=lambda: (
            datetime(2026, 9, 5, tzinfo=UTC) + timedelta(seconds=context.phone.seconds)
        ),
    )
    dialog = SourceInstallationDialog(
        _executor(context),
        (context.phone.device(), wrong),
        recipe=context.recipe(wipe=bool(getattr(request, "param", False))),
        boot_service=boot,
    )
    dialog.show()
    app.processEvents()
    yield app, dialog, workers, context
    dialog.boot_timer.stop()
    dialog.monitoring = False
    dialog.worker = None
    dialog.close()
    app.processEvents()


def _click(button):
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)


def _finish_worker(app, workers):
    assert len(workers) == 1, "Expected one bounded production worker from the user's click"
    workers.pop(0).execute()
    app.processEvents()


def _review(dialog, app, workers):
    _click(dialog.guided_primary if dialog.guided_primary.isVisible() else dialog.review_button)
    _finish_worker(app, workers)
    assert dialog.plan is not None, dialog.status.text()
    assert dialog.flash_button.isEnabled()


def _answer(monkeypatch, *, accept, before_answer=None):
    original = QMessageBox.exec
    questions = []

    def execute(question):
        questions.append(question.text() + "\n" + question.informativeText())

        def answer():
            if before_answer:
                before_answer()
            button = (
                next(
                    item
                    for item in question.buttons()
                    if question.buttonRole(item) is QMessageBox.ButtonRole.AcceptRole
                )
                if accept
                else question.button(QMessageBox.StandardButton.Cancel)
            )
            _click(button)

        QTimer.singleShot(0, answer)
        return original(question)

    monkeypatch.setattr(QMessageBox, "exec", execute)
    return questions


def test_user_sees_all_declared_actions_but_declining_sends_no_mutating_command(
    installation_dialog, monkeypatch
):
    app, dialog, workers, context = installation_dialog
    assert dialog.images.rowCount() == 53
    assert not dialog.flash_button.isEnabled()
    assert all(
        not dialog.images.item(row, column).flags() & Qt.ItemFlag.ItemIsEditable
        for row in range(53)
        for column in range(2)
    )
    _review(dialog, app, workers)
    text = dialog.review.toPlainText()
    assert dialog.recipe.source_sha256 in text
    assert "700M" in text and "super" in text
    assert "No data erase requested" in text
    assert "data preservation and compatibility unproven" in text
    questions = _answer(monkeypatch, accept=False)
    _click(dialog.flash_button)
    assert "changes the active slot" in questions[0]
    assert "full super container" in questions[0]
    assert "53" in questions[0]
    assert context.phone.changes == []
    assert workers == []


def test_user_target_change_prevents_review_of_other_phone(installation_dialog):
    app, dialog, workers, context = installation_dialog
    dialog.target.setFocus()
    QTest.keyClick(dialog.target, Qt.Key.Key_Down)
    assert dialog.target.currentIndex() == 1
    _click(dialog.review_button)
    _finish_worker(app, workers)
    assert dialog.plan is None
    assert not dialog.flash_button.isEnabled()
    assert context.phone.changes == []


def test_source_changed_while_reading_confirmation_never_activates_slot(
    installation_dialog, monkeypatch
):
    app, dialog, workers, context = installation_dialog
    _review(dialog, app, workers)
    _answer(
        monkeypatch,
        accept=True,
        before_answer=lambda: _mutate_same_stat(dialog.recipe.archive_path),
    )
    _click(dialog.flash_button)
    _finish_worker(app, workers)
    assert context.phone.changes == []
    assert dialog.result is None or dialog.result.state is LocalFlashState.REJECTED
    assert not dialog.monitoring


def test_target_changed_inside_confirmation_does_not_consume_the_old_approval(
    installation_dialog, monkeypatch
):
    app, dialog, workers, context = installation_dialog
    _review(dialog, app, workers)
    _answer(monkeypatch, accept=True, before_answer=lambda: dialog.target.setCurrentIndex(1))
    _click(dialog.flash_button)
    assert workers == []
    assert context.phone.changes == []
    assert dialog.plan is None


def test_user_stops_after_slot_change_and_gets_incomplete_recovery_handoff(
    installation_dialog, monkeypatch
):
    app, dialog, workers, context = installation_dialog
    _review(dialog, app, workers)
    _answer(monkeypatch, accept=True)
    _click(dialog.flash_button)
    assert dialog.cancel_button.isVisible() and dialog.cancel_button.isEnabled()
    monkeypatch.setattr(context.phone, "on_change", lambda _command: _click(dialog.cancel_button))
    _finish_worker(app, workers)
    assert dialog.result.state is LocalFlashState.CANCELLED
    assert _actual_changes(context.phone) == [("set_active", "a")]
    assert not context.phone.written
    assert dialog.result.phone_change_attempted
    assert dialog.recovery_requested
    assert not dialog.monitoring


@pytest.mark.parametrize("installation_dialog", [True], indirect=True)
def test_wipe_variant_requires_explicit_data_loss_confirmation(installation_dialog, monkeypatch):
    app, dialog, workers, context = installation_dialog
    _review(dialog, app, workers)
    assert dialog.images.rowCount() == 55
    assert "DATA WILL BE ERASED" in dialog.boundary.text()
    _answer(monkeypatch, accept=False)
    _click(dialog.flash_button)
    assert context.phone.changes == []
    assert workers == []


def test_app_owned_session_survives_view_and_mode_changes_without_duplicate_execution(
    installation,
    monkeypatch,
):
    context = installation
    app = QApplication.instance() or QApplication([])
    workers = []
    monkeypatch.setattr("romverse.ui.local_flash.start_background", workers.append)
    session = SourceOperationSession(
        _executor(context),
        (context.phone.device(),),
        recipe=context.recipe(),
    )
    first = SourceInstallationDialog(
        session.service,
        session.devices,
        recipe=session.recipe,
        session=session,
        experience_mode=ExperienceMode.GUIDED,
    )
    first.show()
    app.processEvents()

    _click(first.guided_primary)
    _finish_worker(app, workers)
    reviewed_plan = session.plan
    assert reviewed_plan is not None
    reviewed_revision = session.revision
    questions = _answer(monkeypatch, accept=True)
    _click(first.flash_button)
    assert questions and len(workers) == 1
    active_worker = session.worker
    assert active_worker is workers[0]
    active_status = session.status

    first.set_experience_mode(ExperienceMode.EXPERT)
    first.set_experience_mode(ExperienceMode.GUIDED)
    assert session.worker is active_worker
    assert session.plan is reviewed_plan
    assert session.revision == reviewed_revision
    assert context.phone.changes == []
    assert not session.accept_installation(reviewed_revision, reviewed_plan.plan_digest)
    assert session.status == active_status
    assert len(workers) == 1

    _click(first.close_button)
    app.processEvents()
    assert not first.isVisible()
    assert session.busy and session.worker is active_worker

    second = SourceInstallationDialog(
        session.service,
        session.devices,
        recipe=session.recipe,
        session=session,
        experience_mode=ExperienceMode.EXPERT,
    )
    second.show()
    app.processEvents()
    assert second.session is session
    assert second.plan is reviewed_plan
    assert second.worker is active_worker
    assert len(workers) == 1

    _finish_worker(app, workers)
    assert session.result is not None
    assert session.result.state == "completed"
    assert _actual_changes(context.phone) == _expected_changes()
    assert not session.busy
    assert not session.snapshot().recovery_available
    assert not second.recovery_button.isVisible()
    second.close()
    first.deleteLater()
    second.deleteLater()
    session.dispose()
    app.processEvents()


def test_app_owned_preparation_survives_view_replacement_with_exact_inputs(
    installation,
    monkeypatch,
):
    context = installation
    app = QApplication.instance() or QApplication([])
    workers = []
    monkeypatch.setattr("romverse.ui.project_flash.start_background", workers.append)
    executor = _executor(context)
    session = SourceOperationSession(
        None,
        (context.phone.device(),),
        project_id=context.project_id,
        source_sha256=context.source.store.get(context.project_id).original.sha256,
        preparation_service=object(),
        source_service=context.source,
        installation_factory=lambda _preparation: executor,
    )
    first = ProjectPreparationDialog(
        session.preparation_service,
        context.project_id,
        source_service=context.source,
        session=session,
        source_sha256=session.source_sha256,
    )
    first.choice.setCurrentIndex(first.choice.findData("source-installation"))
    first.show()
    app.processEvents()
    _click(first.prepare_button)

    assert session.phase is SourceOperationPhase.PREPARING
    assert session.preparation_request is not None
    assert session.preparation_request.candidate_choice == "source-installation"
    assert session.worker is workers[0]
    assert first.close_button.text() == "Hide preparation"
    _click(first.close_button)
    app.processEvents()
    assert not first.isVisible() and session.busy

    second = ProjectPreparationDialog(
        session.preparation_service,
        context.project_id,
        source_service=context.source,
        session=session,
        source_sha256=session.source_sha256,
    )
    second.show()
    app.processEvents()
    assert second.choice.currentData() == "source-installation"
    assert second.worker is session.worker is workers[0]
    assert second.close_button.text() == "Hide preparation"

    _finish_worker(app, workers)
    assert second.result() == QDialog.DialogCode.Accepted
    assert session.recipe is session.preparation
    assert session.service is executor
    assert session.phase is SourceOperationPhase.READY
    assert not session.busy
    assert context.phone.changes == []
    first.deleteLater()
    second.deleteLater()
    session.dispose()
    app.processEvents()


def test_hidden_preparation_rejects_changed_consequences_and_reopens_for_retry(
    installation,
    monkeypatch,
):
    context = installation
    app = QApplication.instance() or QApplication([])
    workers = []
    monkeypatch.setattr("romverse.ui.project_flash.start_background", workers.append)
    requested_recipe = context.recipe(wipe=False, reboot=True)

    class MismatchedSource:
        def prepare(self, *_args, **_kwargs):
            return replace(requested_recipe, wipe=True)

    session = SourceOperationSession(
        None,
        (context.phone.device(),),
        project_id=context.project_id,
        source_sha256=requested_recipe.source_sha256,
        preparation_service=object(),
        source_service=MismatchedSource(),
        installation_factory=lambda _preparation: _executor(context),
    )
    first = ProjectPreparationDialog(
        session.preparation_service,
        context.project_id,
        source_service=session.source_service,
        session=session,
        source_sha256=session.source_sha256,
    )
    first.choice.setCurrentIndex(first.choice.findData("source-installation"))
    first.show()
    app.processEvents()
    _click(first.prepare_button)
    _click(first.close_button)
    _finish_worker(app, workers)

    assert session.recipe is None and session.preparation is None
    assert session.phase is SourceOperationPhase.ATTENTION
    assert "mismatched project evidence" in session.preparation_error
    assert context.phone.changes == []

    session.source_service = context.source
    second = ProjectPreparationDialog(
        session.preparation_service,
        context.project_id,
        source_service=session.source_service,
        session=session,
        source_sha256=session.source_sha256,
    )
    second.show()
    app.processEvents()
    assert second.choice.currentData() == "source-installation"
    assert not second.wipe.isChecked() and second.reboot.isChecked()
    assert "mismatched project evidence" in second.status.text()
    assert second.prepare_button.isEnabled()
    _click(second.prepare_button)
    _finish_worker(app, workers)
    assert session.recipe is session.preparation
    assert session.recipe.wipe is False and session.recipe.reboot is True
    assert session.phase is SourceOperationPhase.READY
    assert context.phone.changes == []
    first.deleteLater()
    second.deleteLater()
    session.dispose()
    app.processEvents()


def test_guided_read_only_check_failure_offers_a_bounded_retry(installation, monkeypatch):
    context = installation
    app = QApplication.instance() or QApplication([])
    workers = []
    monkeypatch.setattr("romverse.ui.local_flash.start_background", workers.append)
    executor = _executor(context)
    inspect = executor.inspect

    def fail_read_only_check(*_args, **_kwargs):
        raise RuntimeError("The package could not be read completely")

    monkeypatch.setattr(executor, "inspect", fail_read_only_check)
    session = SourceOperationSession(
        executor,
        (context.phone.device(),),
        recipe=context.recipe(),
    )
    dialog = SourceInstallationDialog(
        executor,
        session.devices,
        recipe=session.recipe,
        session=session,
        experience_mode=ExperienceMode.GUIDED,
    )
    dialog.show()
    app.processEvents()

    _click(dialog.guided_primary)
    _finish_worker(app, workers)
    snapshot = session.snapshot()
    assert snapshot.phase.value == "attention"
    assert snapshot.can_review and not snapshot.recovery_available
    assert dialog.guided_primary.text() == "Check readiness again"
    assert dialog.guided_primary.isEnabled()
    assert not dialog.recovery_button.isVisible()
    assert context.phone.changes == []

    monkeypatch.setattr(executor, "inspect", inspect)
    _click(dialog.guided_primary)
    _finish_worker(app, workers)
    assert session.plan is not None
    assert dialog.guided_primary.text() == "Install ROM…"
    assert context.phone.changes == []
    dialog.close()
    session.dispose()
    app.processEvents()


def test_completed_bootloader_transition_returns_to_same_installation_journey(
    installation,
    monkeypatch,
    tmp_path,
):
    context = installation
    app = QApplication.instance() or QApplication([])
    workers = []
    monkeypatch.setattr("romverse.ui.local_flash.start_background", workers.append)

    class TransitionService:
        def inspect(self, device, target):
            return LocalTransitionPlan(
                plan_digest="1" * 64,
                plan_id="transition-plan",
                created_at="2026-09-05T00:00:00+00:00",
                expires_at="2026-09-05T00:02:00+00:00",
                device_name=device.display_name,
                masked_serial=device.masked_serial(),
                source_mode="android",
                target=target,
                warnings=(),
                command=("adb", "reboot", "bootloader"),
                device_key="device-key",
                tools=(),
                source_device=device,
            )

        def execute(self, plan, **_kwargs):
            return LocalTransitionResult(
                state=LocalFlashState.COMPLETED,
                summary="The exact phone arrived in bootloader Fastboot.",
                phone_change_attempted=True,
                receipt_path=tmp_path / "transition-receipt.json",
                observed_device=plan.source_device,
                arrival_verified=True,
                command_completed=True,
            )

    session = SourceOperationSession(
        _executor(context),
        (context.phone.device(),),
        recipe=context.recipe(),
        transition_service=TransitionService(),
    )
    assert session.review_transition(LocalTransitionTarget.BOOTLOADER)
    _finish_worker(app, workers)
    review = session.transition_review
    assert review is not None
    assert session.accept_transition(review)
    _finish_worker(app, workers)

    snapshot = session.snapshot()
    assert snapshot.phase.value == "ready"
    assert snapshot.can_review
    assert "Continue with installation preparation" in snapshot.status
    assert session.transition_result is not None
    assert not snapshot.recovery_available
    assert context.phone.changes == []
    session.dispose()
    app.processEvents()


def test_guided_android_route_confirms_bootloader_once_then_continues_read_only(
    installation,
    monkeypatch,
    tmp_path,
):
    context = installation
    app = QApplication.instance() or QApplication([])
    workers = []
    transition_calls = []
    monkeypatch.setattr("romverse.ui.local_flash.start_background", workers.append)
    android = replace(
        context.phone.device(),
        state=DeviceState.DEVICE,
        transport="usb",
        connection_note="Connected over authorized ADB",
    )

    class TransitionService:
        def inspect(self, device, target):
            transition_calls.append(("inspect", device.serial, target))
            return LocalTransitionPlan(
                plan_digest="2" * 64,
                plan_id="guided-transition-plan",
                created_at="2026-09-05T00:00:00+00:00",
                expires_at="2026-09-05T00:02:00+00:00",
                device_name=device.display_name,
                masked_serial=device.masked_serial(),
                source_mode="android",
                target=target,
                warnings=(),
                command=("adb", "reboot", "bootloader"),
                device_key="device-key",
                tools=(),
                source_device=device,
            )

        def execute(self, plan, **_kwargs):
            transition_calls.append(("execute", plan.source_device.serial, plan.target))
            return LocalTransitionResult(
                state=LocalFlashState.COMPLETED,
                summary="The exact phone arrived in bootloader Fastboot.",
                phone_change_attempted=True,
                receipt_path=tmp_path / "guided-transition-receipt.json",
                observed_device=replace(
                    plan.source_device,
                    state=DeviceState.BOOTLOADER,
                    transport="usb-fastboot",
                    connection_note="Observed in bootloader Fastboot",
                ),
                arrival_verified=True,
                command_completed=True,
            )

    session = SourceOperationSession(
        _executor(context),
        (android,),
        recipe=context.recipe(),
        transition_service=TransitionService(),
        guided_automation=True,
    )
    dialog = SourceInstallationDialog(
        session.service,
        session.devices,
        recipe=session.recipe,
        session=session,
        experience_mode=ExperienceMode.GUIDED,
        transition_service=session.transition_service,
    )
    dialog.show()
    app.processEvents()

    assert dialog.guided_primary.text() == "Restart phone to bootloader…"
    assert dialog.guided_primary.isEnabled()
    assert "connected in Android" in dialog.status.text()
    questions = _answer(monkeypatch, accept=True)
    _click(dialog.guided_primary)
    _finish_worker(app, workers)
    assert len(workers) == 1 and session.phase is SourceOperationPhase.TRANSITIONING
    _finish_worker(app, workers)
    assert len(workers) == 1 and session.phase is SourceOperationPhase.REVIEWING
    _finish_worker(app, workers)

    assert len(questions) == 1
    assert "bootloader" in questions[0]
    assert transition_calls == [
        ("inspect", android.serial, LocalTransitionTarget.BOOTLOADER),
        ("execute", android.serial, LocalTransitionTarget.BOOTLOADER),
    ]
    assert session.plan is not None
    assert session.phase is SourceOperationPhase.REVIEW_READY
    assert dialog.guided_primary.text() == "Install ROM…"
    assert context.phone.changes == []
    dialog.close()
    session.dispose()
    app.processEvents()


def test_guided_usb_watch_continues_after_authorization_without_manual_refresh(
    installation,
    monkeypatch,
):
    context = installation
    app = QApplication.instance() or QApplication([])
    workers = []
    monkeypatch.setattr("romverse.ui.local_flash.start_background", workers.append)
    unauthorized = replace(
        context.phone.device(),
        state=DeviceState.UNAUTHORIZED,
        transport="usb",
        connection_note="Unlock the phone and accept the USB debugging prompt.",
    )
    discoveries = [(unauthorized,), (context.phone.device(),)]

    def discover():
        return list(discoveries.pop(0))

    session = SourceOperationSession(
        _executor(context),
        (unauthorized,),
        recipe=context.recipe(),
        discover=discover,
        guided_automation=True,
    )
    dialog = SourceInstallationDialog(
        session.service,
        session.devices,
        recipe=session.recipe,
        session=session,
        experience_mode=ExperienceMode.GUIDED,
        discover=discover,
    )
    dialog.show()
    app.processEvents()
    assert dialog.guided_primary.text() == "Approve USB debugging on phone"
    assert not dialog.guided_primary.isEnabled()
    assert session.connection_watch_timer.isActive()

    QTest.qWait(2100)
    assert session.phase is SourceOperationPhase.REFRESHING
    assert len(workers) == 1
    _finish_worker(app, workers)
    assert session.phase is SourceOperationPhase.READY
    assert "approve its USB debugging prompt" in session.status
    assert session.connection_watch_timer.isActive()

    session.connection_watch_timer.stop()
    session._watch_connection()
    _finish_worker(app, workers)
    assert session.phase is SourceOperationPhase.REVIEWING
    assert len(workers) == 1
    _finish_worker(app, workers)
    assert session.phase is SourceOperationPhase.REVIEW_READY
    assert session.plan is not None
    assert discoveries == []
    assert context.phone.changes == []
    dialog.close()
    session.dispose()
    app.processEvents()


def test_guided_usb_watch_backs_off_repeated_detection_errors_without_recovery(
    installation,
    monkeypatch,
):
    context = installation
    app = QApplication.instance() or QApplication([])
    workers = []
    monkeypatch.setattr("romverse.ui.local_flash.start_background", workers.append)

    def discover():
        raise RuntimeError("ADB transport is temporarily unavailable")

    session = SourceOperationSession(
        _executor(context),
        (context.phone.device(),),
        recipe=context.recipe(),
        discover=discover,
        guided_automation=True,
    )
    for attempt in range(3):
        session.connection_watch_timer.stop()
        session._watch_connection()
        _finish_worker(app, workers)
        assert session.phase is SourceOperationPhase.READY
        assert not session.snapshot().recovery_available
        assert session.connection_watch_timer.isActive()
        assert session._connection_watch_failures == attempt + 1

    assert session.connection_watch_timer.interval() == 5000
    assert "repeatedly failed" in session.status
    assert "ADB transport is temporarily unavailable" in session.details
    assert context.phone.changes == []
    session.connection_watch_timer.stop()
    session.dispose()
    app.processEvents()


def test_guided_never_guesses_between_multiple_unmatched_phones(installation):
    context = installation
    app = QApplication.instance() or QApplication([])
    devices = (
        replace(
            context.phone.device(),
            serial="OTHER-SIMULATED-0002",
            product="komodo",
            codename="komodo",
        ),
        replace(
            context.phone.device(),
            serial="OTHER-SIMULATED-0003",
            product="e3q",
            codename="e3q",
        ),
    )
    session = SourceOperationSession(
        _executor(context),
        devices,
        recipe=context.recipe(),
        guided_automation=True,
    )
    dialog = SourceInstallationDialog(
        session.service,
        session.devices,
        recipe=session.recipe,
        session=session,
        experience_mode=ExperienceMode.GUIDED,
    )
    dialog.show()
    app.processEvents()

    assert session.selected_serial == ""
    assert session.selected_device() is None
    assert "will not guess" in session.status
    assert dialog.guided_primary.text() == "Choose the intended phone"
    assert not dialog.guided_primary.isEnabled()
    assert not session.review_installation()
    assert context.phone.changes == []
    dialog.close()
    session.dispose()
    app.processEvents()


@pytest.mark.parametrize("conflict", ["product", "manufacturer"])
def test_guided_wrong_phone_keeps_watching_and_adopts_one_exact_match(
    installation,
    monkeypatch,
    conflict,
):
    context = installation
    app = QApplication.instance() or QApplication([])
    workers = []
    monkeypatch.setattr("romverse.ui.local_flash.start_background", workers.append)
    wrong = replace(
        context.phone.device(),
        serial="OTHER-SIMULATED-0002",
        **(
            {"product": "komodo", "codename": "komodo"}
            if conflict == "product"
            else {"manufacturer": "Samsung"}
        ),
    )

    def discover():
        return [wrong, context.phone.device()]

    session = SourceOperationSession(
        _executor(context),
        (wrong,),
        recipe=context.recipe(),
        discover=discover,
        guided_automation=True,
    )
    dialog = SourceInstallationDialog(
        session.service,
        session.devices,
        recipe=session.recipe,
        session=session,
        experience_mode=ExperienceMode.GUIDED,
        discover=discover,
    )
    dialog.show()
    app.processEvents()

    assert session.selected_identity_conflicts()
    assert "does not match popsicle" in session.status
    assert dialog.guided_primary.text() == "Connect the matching phone"
    assert not dialog.guided_primary.isEnabled()
    assert dialog.target.isVisible()
    assert session.connection_watch_timer.isActive()

    session.connection_watch_timer.stop()
    session._watch_connection()
    _finish_worker(app, workers)
    assert session.selected_serial == context.phone.serial
    assert session.phase is SourceOperationPhase.REVIEWING
    assert len(workers) == 1
    _finish_worker(app, workers)
    assert session.phase is SourceOperationPhase.REVIEW_READY
    assert session.plan is not None
    assert context.phone.changes == []
    dialog.close()
    session.dispose()
    app.processEvents()


def test_user_confirmed_complete_installation_then_measures_boot_separately(
    installation_dialog, monkeypatch
):
    app, dialog, workers, context = installation_dialog
    _review(dialog, app, workers)
    _answer(monkeypatch, accept=True)
    _click(dialog.flash_button)
    assert not dialog.target.isEnabled()
    _finish_worker(app, workers)
    assert dialog.result.state is LocalFlashState.COMPLETED, dialog.status.text()
    assert _actual_changes(context.phone) == _expected_changes()
    assert not dialog.result.boot_verified
    original_receipt = dialog.result.receipt_path.read_bytes()
    _finish_worker(app, workers)
    assert dialog.boot_report is not None, dialog.status.text()
    assert dialog.boot_report.status == "settling"
    assert not dialog.boot_report.terminal
    for _ in range(10):
        dialog.boot_timer.stop()
        context.phone.seconds += 6
        dialog._poll_boot()
        _finish_worker(app, workers)
    assert dialog.boot_report.status == "stable", dialog.status.text()
    assert dialog.boot_report.elapsed_seconds == 60
    assert dialog.boot_report.boot_observed
    assert not dialog.result.boot_verified
    assert dialog.result.receipt_path.read_bytes() == original_receipt
    assert _actual_changes(context.phone) == _expected_changes()
    assert context.flash.audit.verify().valid


def test_reusable_script_uses_actual_managed_workers_and_truthful_compact_artifacts(
    tmp_path, capsys
):
    output = tmp_path / "new-simulation"
    assert simulate_source_installation([str(output), "--declaration", str(SCRIPT_FIXTURE)]) == 0
    report = json.loads((output / "simulation-report.json").read_text())
    assert report["simulation_only"] is True
    assert report["physical_phone_changed"] is False
    assert report["production_certified"] is False
    assert report["simulated_action_count"] == 53
    assert report["simulated_image_write_count"] == 50
    assert report["simulated_actions"] == [list(item) for item in _expected_changes()]
    assert report["initial_simulated_mode"] == "android"
    assert report["bootloader_restart_explicitly_confirmed"] is True
    assert report["bootloader_arrival_observed"] is True
    assert report["read_only_review_continued_automatically"] is True
    assert report["decline_sent_no_mutating_command"] is True
    assert report["explicit_wipe_selected"] is False
    assert report["installation_result_boot_verified"] is False
    assert report["separate_observed_boot_status"] == "stable"
    assert report["simulated_boot_window_seconds"] == 60
    assert report["boot_sample_count"] == 11
    assert report["installation_receipt_unchanged"] is True
    assert report["compact_layout_readable"] is True
    assert report["preparation_warning_readable"] is True
    assert report["preparation_and_installation_same_session"] is True
    assert report["dialog_size"] == [760, 720]
    assert report["audit_valid"] is True
    assert report["history_reopened_from_saved_receipt"] is True
    assert report["history_open_sent_no_phone_command"] is True
    assert report["history_boot_explicitly_requested"] is True
    assert report["history_additional_changing_action_count"] == 0
    assert report["history_boot_window_seconds"] == 60
    assert report["history_boot_sample_count"] == 11
    assert report["history_boot_status"] == "stable"
    assert report["history_boot_linked_to_original_installation"] is True
    assert report["history_installation_receipt_unchanged"] is True
    assert report["history_compact_layout_readable"] is True
    assert report["history_dialog_size"] == [760, 720]
    for name in (
        "preparation",
        "android-handoff",
        "review",
        "stable-boot",
        "history",
        "history-stable-boot",
    ):
        captured = QImage(str(output / f"simulation-source-{name}.png"))
        assert not captured.isNull()
    assert json.loads(capsys.readouterr().out)["simulation_only"] is True
    before = (output / "simulation-report.json").read_bytes()
    with pytest.raises(FileExistsError):
        simulate_source_installation([str(output), "--declaration", str(SCRIPT_FIXTURE)])
    assert (output / "simulation-report.json").read_bytes() == before


@pytest.fixture
def installation_desktop(installation, monkeypatch):
    context = installation
    app = QApplication.instance() or QApplication([])
    tool = context.flash.fastboot_path
    monkeypatch.setattr(
        "romverse.ui.toolchain_center.ToolVerifier.verify_extended",
        lambda _self: (ToolStatus("Fastboot", True, str(tool), "INERT SIMULATION"),),
    )
    monkeypatch.setattr(
        "romverse.ui.project_flash.start_background", lambda worker: worker.execute()
    )
    monkeypatch.setattr("romverse.ui.local_flash.start_background", lambda worker: worker.execute())

    def accelerated_boot(flash, adb, **kwargs):
        return LocalBootService(
            flash,
            adb,
            monotonic_clock=lambda: context.phone.seconds,
            utc_clock=lambda: (
                datetime(2026, 9, 5, tzinfo=UTC) + timedelta(seconds=context.phone.seconds)
            ),
            **kwargs,
        )

    monkeypatch.setattr("romverse.rom.local_boot.LocalBootService", accelerated_boot)
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        context.source.store.workspace,
        runner=context.phone,
        fastboot_executable=tool,
        app_icon_path=logo,
        app_settings=AppSettings(
            experience_mode=ExperienceMode.GUIDED,
            online_intelligence_enabled=False,
            desktop_notifications_enabled=False,
            reduced_motion=True,
        ),
    )
    window._device_adb_executable = context.adb
    window.rom_studio.current_project = context.source.store.get(context.project_id)
    window._observed_devices = [context.phone.device()]
    window.rom_studio.set_devices([context.phone.device()])
    window.show()
    app.processEvents()
    yield app, window, context
    if window._local_flash_dialog is not None:
        window._local_flash_dialog.worker = None
        window._local_flash_dialog.monitoring = False
        window._local_flash_dialog.reject()
        window._local_flash_dialog = None
    window.companion_center.transport.close()
    window.close()
    app.processEvents()


@pytest.mark.parametrize("outcome", ["completed", "failed"])
def test_guided_main_window_runs_source_route_and_records_exact_outcome(
    installation_desktop, outcome
):
    app, window, context = installation_desktop
    phases = []
    errors = []
    results = []
    incidents = []
    if outcome == "failed":
        context.phone.fail_partition = "super"
        window.repair_center.open_recovery_incident = lambda *args, **kwargs: incidents.append(
            (args, kwargs)
        )
    timer = QTimer()
    timeout = QTimer()
    timeout.setSingleShot(True)

    def confirm():
        modal = app.activeModalWidget()
        if isinstance(modal, QMessageBox):
            phases.append("confirmed")
            _click(
                next(
                    item
                    for item in modal.buttons()
                    if modal.buttonRole(item) is QMessageBox.ButtonRole.AcceptRole
                )
            )

    def interact():
        modal = app.activeModalWidget()
        try:
            if isinstance(modal, ProjectPreparationDialog) and "prepared" not in phases:
                phases.append("prepared")
                assert window._local_flash_dialog is modal
                assert context.phone.changes == []
                modal.choice.setFocus()
                QTest.keyClick(modal.choice, Qt.Key.Key_End)
                assert modal.choice.currentData() == "source-installation"
                assert not modal.wipe.isChecked()
                _click(modal.prepare_button)
            elif isinstance(modal, SourceInstallationDialog) and "reviewed" not in phases:
                phases.append("reviewed")
                assert isinstance(modal.service, SourceInstallationExecutor)
                assert window._experience_mode is ExperienceMode.GUIDED
                assert modal.images.rowCount() == 53
                if modal.plan is None:
                    _click(modal.guided_primary)
                assert modal.plan is not None
                assert context.phone.changes == []
                QTimer.singleShot(0, confirm)
                _click(modal.guided_primary)
                assert "confirmed" in phases
                assert modal.result.state == outcome, modal.status.text()
                results.append(modal.result)
                if outcome == "completed":
                    assert modal.boot_report.status == "settling"
                    for _ in range(10):
                        modal.boot_timer.stop()
                        context.phone.seconds += 6
                        modal._poll_boot()
                    assert modal.boot_report.status == "stable", modal.status.text()
                    assert not modal.result.boot_verified
                    _click(modal.close_button)
                else:
                    assert modal.recovery_requested and not modal.monitoring
        except BaseException as exc:
            errors.append(exc)
            timer.stop()
            if modal is not None:
                modal.reject()

    def expired():
        errors.append(AssertionError(f"MainWindow source installation did not finish: {phases}"))
        if app.activeModalWidget() is not None:
            app.activeModalWidget().reject()

    timer.timeout.connect(interact)
    timer.start(1)
    timeout.timeout.connect(expired)
    timeout.start(5000)
    assert window.rom_studio._request_project_flash(context.project_id)
    timer.stop()
    timeout.stop()
    if errors:
        raise errors[0]
    assert phases == ["prepared", "reviewed", "confirmed"]
    assert len(results) == 1 and not results[0].boot_verified
    assert window._local_flash_dialog is None
    assert window._source_operation_session is None
    assert window._experience_mode is ExperienceMode.GUIDED
    if outcome == "completed":
        assert _actual_changes(context.phone) == _expected_changes()
        assert "60 measured seconds" in window.rom_studio.operation_status.text()
        assert incidents == []
    else:
        assert _actual_changes(context.phone) == _expected_changes()[:49]
        assert len(incidents) == 1
        assert incidents[0][1]["project_id"] == context.project_id
        assert incidents[0][1]["target_device"].serial == context.phone.serial


def test_main_window_retains_hidden_installation_across_experience_switch(
    installation_desktop,
    monkeypatch,
):
    app, window, context = installation_desktop
    workers = []
    monkeypatch.setattr("romverse.ui.local_flash.start_background", workers.append)
    _answer(monkeypatch, accept=True)
    phases = []
    errors = []
    timer = QTimer()
    timeout = QTimer()
    timeout.setSingleShot(True)

    def interact():
        modal = app.activeModalWidget()
        try:
            if isinstance(modal, ProjectPreparationDialog) and "prepared" not in phases:
                phases.append("prepared")
                modal.choice.setFocus()
                QTest.keyClick(modal.choice, Qt.Key.Key_End)
                _click(modal.prepare_button)
            elif isinstance(modal, SourceInstallationDialog):
                session = modal.session
                if "reviewed" not in phases:
                    if session.worker is None and session.plan is None:
                        _click(modal.guided_primary)
                    if session.worker is not None and session.plan is None and workers:
                        workers.pop(0).execute()
                        app.processEvents()
                    if session.plan is not None:
                        phases.append("reviewed")
                elif session.plan is not None and "hidden" not in phases:
                    phases.append("hidden")
                    _click(modal.guided_primary)
                    assert session.worker is not None and len(workers) == 1
                    _click(modal.close_button)
        except BaseException as exc:
            errors.append(exc)
            timer.stop()
            if modal is not None:
                modal.reject()

    def expired():
        errors.append(AssertionError(f"App-owned session did not detach: {phases}"))
        if app.activeModalWidget() is not None:
            app.activeModalWidget().reject()

    timer.timeout.connect(interact)
    timer.start(1)
    timeout.timeout.connect(expired)
    timeout.start(5000)
    assert window.rom_studio._request_project_flash(context.project_id)
    timer.stop()
    timeout.stop()
    if errors:
        raise errors[0]

    session = window._source_operation_session
    assert phases == ["prepared", "reviewed", "hidden"]
    assert session is not None and session.busy
    assert window._local_flash_dialog is None
    retained_worker = session.worker
    retained_plan = session.plan
    retained_revision = session.revision
    window._apply_experience_mode(ExperienceMode.EXPERT)
    assert session.worker is retained_worker
    assert session.plan is retained_plan
    assert session.revision == retained_revision
    assert context.phone.changes == []
    reopened = []
    show_source_operation = window._show_source_operation_session
    monkeypatch.setattr(window, "_show_source_operation_session", reopened.append)
    window._open_expert_flash()
    window._open_source_installation_history(context.project_id)
    assert reopened == [session, session]
    assert window._source_operation_session is session
    assert len(workers) == 1
    monkeypatch.setattr(window, "_show_source_operation_session", show_source_operation)

    session.boot_service = None
    workers.pop(0).execute()
    app.processEvents()
    assert session.result is not None and session.result.state == "completed"
    assert not session.busy
    assert _actual_changes(context.phone) == _expected_changes()
    assert window._source_operation_session is session

    QTimer.singleShot(
        0,
        lambda: (
            app.activeModalWidget().close_button.click()
            if isinstance(app.activeModalWidget(), SourceInstallationDialog)
            else None
        ),
    )
    window._show_source_operation_session(session)
    assert window._source_operation_session is None


def test_main_window_continues_hidden_preparation_in_the_same_mission(
    installation_desktop,
    monkeypatch,
):
    app, window, context = installation_desktop
    workers = []
    monkeypatch.setattr("romverse.ui.project_flash.start_background", workers.append)
    phases = []
    errors = []
    retained = []
    timer = QTimer()
    timeout = QTimer()
    timeout.setSingleShot(True)

    def interact():
        modal = app.activeModalWidget()
        try:
            if isinstance(modal, ProjectPreparationDialog) and "hidden" not in phases:
                modal.choice.setFocus()
                QTest.keyClick(modal.choice, Qt.Key.Key_End)
                assert modal.choice.currentData() == "source-installation"
                _click(modal.prepare_button)
                session = window._source_operation_session
                assert session is not None and session.busy
                assert session.preparation_request.candidate_choice == "source-installation"
                retained.append(session)
                phases.append("hidden")
                _click(modal.close_button)
            elif isinstance(modal, SourceInstallationDialog) and "continued" not in phases:
                assert retained and modal.session is retained[0]
                assert modal.recipe is retained[0].preparation
                assert modal.worker is None and modal.plan is retained[0].plan
                assert modal.plan is not None
                assert window._experience_mode is ExperienceMode.EXPERT
                assert context.phone.changes == []
                phases.append("continued")
                _click(modal.close_button)
        except BaseException as exc:
            errors.append(exc)
            timer.stop()
            if modal is not None:
                modal.reject()

    def expired():
        errors.append(AssertionError(f"Hidden preparation did not continue: {phases}"))
        if app.activeModalWidget() is not None:
            app.activeModalWidget().reject()

    timer.timeout.connect(interact)
    timer.start(1)
    timeout.timeout.connect(expired)
    timeout.start(5000)
    assert window.rom_studio._request_project_flash(context.project_id)
    assert phases == ["hidden"]
    session = retained[0]
    worker = session.worker
    request = session.preparation_request
    window._apply_experience_mode(ExperienceMode.EXPERT)
    assert session.worker is worker and session.preparation_request is request
    assert len(workers) == 1

    workers.pop(0).execute()
    app.processEvents()
    assert phases == ["hidden"]
    assert window._source_operation_session is session
    assert session.recipe is session.preparation and not session.busy
    assert "Preparation verified and retained" in window.rom_studio.operation_status.text()
    assert app.activeModalWidget() is None

    assert window.rom_studio._request_project_flash(context.project_id)
    timer.stop()
    timeout.stop()
    if errors:
        raise errors[0]
    assert phases == ["hidden", "continued"]
    assert context.phone.changes == []
    assert window._source_operation_session is None


def test_hidden_preparation_failure_is_actionable_and_reopens_exact_choice(
    installation_desktop,
    monkeypatch,
):
    app, window, context = installation_desktop
    workers = []
    monkeypatch.setattr("romverse.ui.project_flash.start_background", workers.append)

    def fail_preparation(*_args, **_kwargs):
        raise ProjectError("The protected source changed during verification.")

    monkeypatch.setattr(SourceInstallationService, "prepare", fail_preparation)

    def start_and_hide():
        modal = app.activeModalWidget()
        if isinstance(modal, ProjectPreparationDialog):
            modal.choice.setFocus()
            QTest.keyClick(modal.choice, Qt.Key.Key_End)
            _click(modal.prepare_button)
            _click(modal.close_button)

    QTimer.singleShot(0, start_and_hide)
    assert window.rom_studio._request_project_flash(context.project_id)
    session = window._source_operation_session
    assert session is not None and session.busy and len(workers) == 1
    workers.pop(0).execute()
    app.processEvents()
    assert session.phase is SourceOperationPhase.ATTENTION and not session.busy
    assert session.preparation_request.candidate_choice == "source-installation"
    assert "Preparation needs attention" in window.rom_studio.operation_status.text()
    assert "protected source changed" in window.rom_studio.operation_status.text()
    assert context.phone.changes == []

    reopened = []

    def inspect_and_close():
        modal = app.activeModalWidget()
        if isinstance(modal, ProjectPreparationDialog):
            reopened.append(modal.choice.currentData())
            assert "protected source changed" in modal.status.text()
            assert modal.prepare_button.isEnabled()
            _click(modal.close_button)

    QTimer.singleShot(0, inspect_and_close)
    assert window.rom_studio._request_project_flash(context.project_id)
    assert reopened == ["source-installation"]
    assert window._source_operation_session is None
    assert context.phone.changes == []
