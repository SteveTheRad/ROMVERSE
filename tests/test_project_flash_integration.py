"""Project-to-phone journeys using production services and an inert transport.

The ZIPs and image bytes here are synthetic test inputs, never real firmware.
"""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.local_flash import (
    LocalFlashError,
    LocalFlashSelection,
    LocalFlashService,
    LocalFlashState,
)
from romverse.rom.build_execution import LocalDeviceBuildExecutor
from romverse.rom.inspection import RomInspectionService
from romverse.rom.local_boot import LocalBootService, LocalBootStatus
from romverse.rom.models import ProjectError
from romverse.rom.project_flash import (
    BoundProjectFlashService,
    ProjectFlashPreparationService,
)
from romverse.rom.projects import RomProjectStore
from romverse.rom.source_intelligence import FirmwareSourceIntelligenceService
from romverse.ui.project_flash import ProjectFlashDialog
from tests.test_guardian_local_flash import FakeFastboot


@dataclass
class ProjectContext:
    store: RomProjectStore
    project_id: str
    tree: Path
    runner: FakeFastboot
    device: AndroidDevice
    local_service: LocalFlashService
    preparer: ProjectFlashPreparationService
    protected_bytes: dict[str, bytes]

    def prepare(self):
        return self.preparer.prepare(self.project_id, candidate_choice="protected")

    def bind(self, preparation):
        return BoundProjectFlashService(self.preparer, preparation, self.local_service)


@pytest.fixture
def project_context(tmp_path: Path, request) -> ProjectContext:
    store = RomProjectStore(tmp_path / "workspace")
    source = tmp_path / ("popsicle_images_OS4.0.0.25.XPBCNXM_20260804.0000.00_17.0_cn_fixture.zip")
    protected_bytes = {
        "images/boot.img": b"inert stock boot image\0" * 16,
        "images/vendor_boot.img": b"inert stock vendor boot image\0" * 16,
    }
    member_prefix = getattr(request, "param", "")
    with zipfile.ZipFile(source, "w") as archive:
        for name, contents in protected_bytes.items():
            archive.writestr(member_prefix + name, contents)
        archive.writestr("android-info.txt", "require product=popsicle\n")
    project = store.import_original(store.create("Inert project flash journey").project_id, source)
    tree = RomInspectionService(store).extract_project_tree(project.project_id)
    runner = FakeFastboot()
    tool = tmp_path / "fastboot"
    tool.write_bytes(b"non-executable fixture tool; runner is strictly inert")
    tool.chmod(0o700)
    device = AndroidDevice(
        runner.serial,
        DeviceState.BOOTLOADER,
        manufacturer="Xiaomi",
        model="Inert phone",
        product="popsicle",
        codename="popsicle",
        ab_update=True,
    )
    FirmwareSourceIntelligenceService(store, (), runner).prepare(project.project_id)
    local_service = LocalFlashService(store.workspace, runner, tool)
    return ProjectContext(
        store,
        project.project_id,
        tree,
        runner,
        device,
        local_service,
        ProjectFlashPreparationService(store, DevicePackRegistry(())),
        protected_bytes,
    )


def _selection(preparation, name: str = "boot.img", partition: str = "boot_a"):
    image = next(item for item in preparation.images if item.path.name == name)
    return LocalFlashSelection(partition, image.path)


def _mutate_preserving_stat(path: Path) -> None:
    before = path.stat()
    contents = path.read_bytes()
    path.chmod(0o600)
    path.write_bytes(bytes((contents[0] ^ 1,)) + contents[1:])
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_size == before.st_size
    assert path.stat().st_mtime_ns == before.st_mtime_ns


def _execute(bound, plan, **kwargs):
    return bound.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True, **kwargs)


def test_real_protected_subset_has_explicit_mapping_and_transport_only_result(project_context):
    context = project_context
    preparation = context.prepare()
    assert preparation.candidate_choice == "protected"
    assert len(preparation.images) == 2
    assert context.runner.calls == []
    assert all(not hasattr(image, "partition") for image in preparation.images)
    assert all(
        image.sha256 == hashlib.sha256(image.path.read_bytes()).hexdigest()
        for image in preparation.images
    )
    bound = context.bind(preparation)
    selections = (_selection(preparation),)
    plan = bound.inspect(context.device, selections)
    assert [write.partition for write in plan.writes] == ["boot_a"]
    assert context.runner.writes == []
    result = _execute(bound, plan)
    assert result.state is LocalFlashState.COMPLETED
    assert result.completed_count == 1
    assert not result.boot_verified
    assert result.phone_state_uncertain
    assert len(context.runner.writes) == 1
    flashed = context.runner.writes[0]
    assert flashed[1:5] == ("-s", context.device.serial, "flash", "boot_a")
    assert Path(flashed[5]).read_bytes() == context.protected_bytes["images/boot.img"]
    record = json.loads(result.receipt_path.read_text())
    assert record["boot_verified"] is False
    assert record["readback_verified"] is False
    assert record["external_certification"] is False
    assert context.device.serial not in result.receipt_path.read_text()
    parent = json.loads(bound.project_receipt_path.read_text())
    assert parent["source_sha256"] == preparation.source_sha256
    assert parent["preparation_digest"] == preparation.preparation_digest
    assert parent["child_record_digest"] == record["record_digest"]
    assert parent["full_firmware_install"] is False
    assert parent["production_certified"] is False


@pytest.mark.parametrize("project_context", ["./"], indirect=True)
def test_normalized_safe_zip_member_names_keep_protected_provenance(project_context):
    context = project_context
    preparation = context.prepare()
    plan = context.bind(preparation).inspect(context.device, (_selection(preparation),))
    assert len(plan.writes) == 1
    assert context.runner.writes == []


def test_project_result_can_bind_real_boot_monitor_without_promoting_flash_proof(
    project_context, tmp_path
):
    context = project_context
    preparation = context.prepare()
    bound = context.bind(preparation)
    plan = bound.inspect(context.device, (_selection(preparation),))
    result = _execute(bound, plan)
    original_record = result.receipt_path.read_bytes()
    calls = tuple(context.runner.calls)
    adb = tmp_path / "adb"
    adb.write_bytes(b"inert tool; boot observation is not started")
    adb.chmod(0o700)
    monitor = LocalBootService(context.local_service, adb)
    session = monitor.begin(context.device, result)
    report = monitor.stop(session)
    assert report.status is LocalBootStatus.CANCELLED
    assert not report.boot_observed
    assert not result.boot_verified
    assert result.receipt_path.read_bytes() == original_record
    assert tuple(context.runner.calls) == calls


@pytest.mark.parametrize("partition", ["", "boot"])
def test_project_inventory_never_supplies_an_implicit_partition_or_slot(project_context, partition):
    context = project_context
    preparation = context.prepare()
    with pytest.raises((LocalFlashError, ProjectError)):
        context.bind(preparation).inspect(
            context.device, (_selection(preparation, partition=partition),)
        )
    assert context.runner.writes == []


@pytest.mark.parametrize("when", ["before-prepare", "before-review", "before-confirm"])
@pytest.mark.parametrize("target", ["protected-archive", "working-image"])
def test_same_size_same_mtime_byte_changes_never_write(project_context, when, target):
    context = project_context
    preparation = None if when == "before-prepare" else context.prepare()
    bound = context.bind(preparation) if preparation is not None else None
    plan = (
        bound.inspect(context.device, (_selection(preparation),))
        if when == "before-confirm"
        else None
    )
    path = (
        context.store.original_path(context.project_id)
        if target == "protected-archive"
        else context.tree / "images" / "boot.img"
    )
    _mutate_preserving_stat(path)
    if when == "before-prepare":
        with pytest.raises((LocalFlashError, ProjectError)):
            context.prepare()
    elif when == "before-review":
        with pytest.raises((LocalFlashError, ProjectError)):
            bound.inspect(context.device, (_selection(preparation),))
    else:
        try:
            result = _execute(bound, plan)
        except (LocalFlashError, ProjectError):
            pass
        else:
            assert result.state is LocalFlashState.REJECTED
            assert not result.phone_change_attempted
    assert context.runner.writes == []


def test_fresh_blueprint_cannot_launder_modified_tree_as_protected_images(project_context):
    context = project_context
    _mutate_preserving_stat(context.tree / "images" / "boot.img")
    # The inventory really is refreshed by the production adapter. It cannot
    # replace byte-level comparison with the protected archive's image members.
    FirmwareSourceIntelligenceService(context.store, (), context.runner).prepare(context.project_id)
    with pytest.raises((LocalFlashError, ProjectError)):
        context.prepare()
    assert context.runner.writes == []


@pytest.mark.parametrize(
    "changes",
    [
        {"codename": "komodo", "product": "komodo"},
        {"codename": "komodo", "product": "popsicle"},
        {"manufacturer": "Google"},
    ],
)
def test_known_source_device_conflict_blocks_before_any_write(project_context, changes):
    context = project_context
    preparation = context.prepare()
    with pytest.raises((LocalFlashError, ProjectError)):
        context.bind(preparation).inspect(
            replace(context.device, **changes), (_selection(preparation),)
        )
    assert context.runner.writes == []


def test_protected_choice_does_not_consult_stale_custom_build(project_context, monkeypatch):
    context = project_context

    def unexpected_build_lookup(*_args, **_kwargs):
        pytest.fail("Explicit protected choice consulted an unrelated custom build")

    monkeypatch.setattr(LocalDeviceBuildExecutor, "load_receipt", unexpected_build_lookup)
    preparation = context.prepare()
    assert preparation.candidate_choice == "protected"
    assert {item.sha256 for item in preparation.images} == {
        hashlib.sha256(contents).hexdigest() for contents in context.protected_bytes.values()
    }


def test_missing_built_candidate_never_silently_selects_protected(project_context):
    context = project_context
    with pytest.raises((LocalFlashError, ProjectError)):
        context.preparer.prepare(context.project_id, candidate_choice="built")
    assert context.runner.writes == []


def test_external_image_not_in_reviewed_project_inventory_is_rejected(project_context, tmp_path):
    context = project_context
    preparation = context.prepare()
    outside = tmp_path / "boot.img"
    outside.write_bytes(context.protected_bytes["images/boot.img"])
    with pytest.raises((LocalFlashError, ProjectError)):
        context.bind(preparation).inspect(context.device, (LocalFlashSelection("boot_a", outside),))
    assert context.runner.writes == []


@pytest.fixture
def project_dialog(project_context, monkeypatch):
    context = project_context
    app = QApplication.instance() or QApplication([])
    preparation = context.prepare()
    workers = []
    monkeypatch.setattr("romverse.ui.local_flash.start_background", workers.append)
    wrong_phone = replace(
        context.device, serial="unrelated-phone-9876", codename="komodo", product="komodo"
    )
    dialog = ProjectFlashDialog(
        context.bind(preparation),
        (context.device, wrong_phone),
        preparation=preparation,
    )
    dialog.show()
    app.processEvents()
    yield app, dialog, workers, context
    dialog.boot_timer.stop()
    dialog.monitoring = False
    dialog.worker = None
    dialog.close()
    app.processEvents()


def _click(button) -> None:
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)


def _finish_worker(app, workers) -> None:
    assert len(workers) == 1, "The click did not schedule exactly one bounded worker"
    workers.pop(0).execute()
    app.processEvents()


def _type_partition(app, dialog, partition: str, row: int = 0) -> None:
    dialog.images.setCurrentCell(row, 0)
    dialog.images.setFocus()
    QTest.keyClick(dialog.images, Qt.Key.Key_F2)
    editor = QApplication.focusWidget()
    assert editor is not None and editor is not dialog.images
    QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(editor, partition)
    QTest.keyClick(editor, Qt.Key.Key_Return)
    app.processEvents()
    assert dialog.images.item(row, 0).text() == partition


def _add_and_review(app, dialog, workers) -> None:
    _click(dialog.add_button)
    assert dialog.images.rowCount() == 1
    assert dialog.images.item(0, 0).text() == ""
    _type_partition(app, dialog, "boot_a")
    _click(dialog.review_button)
    _finish_worker(app, workers)
    assert dialog.plan is not None
    assert dialog.flash_button.isEnabled()


def _answer_confirmation(monkeypatch, *, accept: bool, before_answer=None):
    original_exec = QMessageBox.exec
    questions = []

    def execute(question):
        questions.append(question.text() + "\n" + question.informativeText())

        def answer():
            if before_answer is not None:
                before_answer()
            button = (
                next(
                    candidate
                    for candidate in question.buttons()
                    if question.buttonRole(candidate) is QMessageBox.ButtonRole.AcceptRole
                )
                if accept
                else question.button(QMessageBox.StandardButton.Cancel)
            )
            _click(button)

        QTimer.singleShot(0, answer)
        return original_exec(question)

    monkeypatch.setattr(QMessageBox, "exec", execute)
    return questions


def test_user_adds_image_but_must_enter_partition_before_review(project_dialog):
    app, dialog, workers, context = project_dialog
    assert dialog.images.rowCount() == 0
    assert not dialog.flash_button.isEnabled()
    assert "not a verified complete-ROM" in dialog.mapping_hint.text()
    _click(dialog.add_button)
    assert dialog.images.item(0, 0).text() == ""
    _click(dialog.review_button)
    _finish_worker(app, workers)
    assert dialog.plan is None
    assert not dialog.flash_button.isEnabled()
    assert context.runner.writes == []
    _type_partition(app, dialog, "boot_a")
    _click(dialog.review_button)
    _finish_worker(app, workers)
    assert dialog.plan is not None
    rendered = dialog.review.toPlainText()
    assert dialog.preparation.source_sha256 in rendered
    assert "not a complete-ROM or production certificate" in rendered


def test_user_can_decline_then_confirm_one_source_bound_image(project_dialog, monkeypatch):
    app, dialog, workers, context = project_dialog
    _add_and_review(app, dialog, workers)
    questions = _answer_confirmation(monkeypatch, accept=False)
    _click(dialog.flash_button)
    assert questions
    assert workers == []
    assert context.runner.writes == []
    monkeypatch.undo()
    monkeypatch.setattr("romverse.ui.local_flash.start_background", workers.append)
    questions = _answer_confirmation(monkeypatch, accept=True)
    _click(dialog.flash_button)
    assert questions
    assert not dialog.images.isEnabled()
    assert not dialog.image_choice.isEnabled()
    _finish_worker(app, workers)
    assert dialog.result is not None
    assert dialog.result.state is LocalFlashState.COMPLETED
    assert not dialog.result.boot_verified
    assert context.runner.writes[0][4] == "boot_a"
    assert len(context.runner.writes) == 1
    assert "unverified" in dialog.review.toPlainText().casefold()


def test_file_change_while_user_reads_confirmation_cannot_flash(project_dialog, monkeypatch):
    app, dialog, workers, context = project_dialog
    _add_and_review(app, dialog, workers)
    _answer_confirmation(
        monkeypatch,
        accept=True,
        before_answer=lambda: _mutate_preserving_stat(context.tree / "images" / "boot.img"),
    )
    _click(dialog.flash_button)
    _finish_worker(app, workers)
    assert context.runner.writes == []
    assert dialog.result is None or dialog.result.state is LocalFlashState.REJECTED
    assert dialog.result is None or not dialog.result.phone_change_attempted


def test_user_selecting_other_phone_cannot_review_source_as_compatible(project_dialog):
    app, dialog, workers, context = project_dialog
    dialog.target.setFocus()
    QTest.keyClick(dialog.target, Qt.Key.Key_Down)
    assert dialog.target.currentIndex() == 1
    _click(dialog.add_button)
    _type_partition(app, dialog, "boot_a")
    _click(dialog.review_button)
    _finish_worker(app, workers)
    assert dialog.plan is None
    assert not dialog.flash_button.isEnabled()
    assert context.runner.writes == []


def test_user_sees_recovery_after_partial_subset_failure(project_dialog, monkeypatch):
    app, dialog, workers, context = project_dialog
    _add_and_review(app, dialog, workers)
    dialog.image_choice.setFocus()
    QTest.keyClick(dialog.image_choice, Qt.Key.Key_Down)
    assert dialog.image_choice.currentIndex() == 1
    _click(dialog.add_button)
    _type_partition(app, dialog, "vendor_boot_a", row=1)
    _click(dialog.review_button)
    _finish_worker(app, workers)
    context.runner.fail_partition = "boot_a"
    _answer_confirmation(monkeypatch, accept=True)
    _click(dialog.flash_button)
    _finish_worker(app, workers)
    assert dialog.result is not None
    assert dialog.result.state is LocalFlashState.FAILED
    assert dialog.result.phone_state_uncertain
    assert not dialog.result.boot_verified
    assert len(context.runner.writes) == 1
    assert dialog.recovery_button.isVisible()
