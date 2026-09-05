"""Simulate the complete source-declared installation with production Qt/services.

Only a NEW output directory is accepted. Every image, device and tool is inert;
the accelerated boot clock is simulated, not physical-device validation.
The optional --declaration input is bounded script DATA, verified but never run.
A source checkout defaults to its exact reviewed declaration fixture; an installed
ROMVERSE can use this script with that explicit fixture. No tests are imported.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from romverse.core.settings import ExperienceMode
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.local_flash import LocalFlashService
from romverse.guardian.source_installation import SourceInstallationExecutor
from romverse.infrastructure.process import CommandResult
from romverse.rom.local_boot import LocalBootService
from romverse.rom.project_flash import ProjectFlashPreparationService
from romverse.rom.projects import RomProjectStore
from romverse.rom.source_installation import (
    POPSICLE_PHYSICAL_PARTITIONS,
    POPSICLE_SCRIPT_SHA256,
    SourceInstallationService,
)
from romverse.rom.source_installation_history import load_latest_source_installation
from romverse.ui.project_flash import ProjectPreparationDialog
from romverse.ui.source_installation import SourceInstallationDialog
from romverse.ui.source_installation_history import SourceInstallationHistoryDialog
from romverse.ui.source_operation_session import SourceOperationSession
from romverse.ui.theme import STYLESHEET, apply_dark_palette

if __package__:
    from .simulate_expert_lifecycle import SimulatedAndroid, confirm_next, pump
else:
    from simulate_expert_lifecycle import SimulatedAndroid, confirm_next, pump


class InstallationPhone(SimulatedAndroid):
    """A deliberately tiny phone model; unrecognized commands fail the test."""

    product = "popsicle"

    def __init__(self):
        super().__init__()
        self.mode = "bootloader"
        self.slot = "b"
        self.unlocked = True
        self.critical_unlocked = True
        self.fail_partition = ""
        self.timeout_partition = ""
        self.fail_change_index = -1
        self.on_change = None
        self.changes: list[tuple[str, ...]] = []
        self.written: list[tuple[str, bytes]] = []

    def device(self):
        return replace(super().device(), manufacturer="Xiaomi", model="SIMULATED popsicle")

    def properties(self):
        return {
            **super().properties(),
            "ro.product.manufacturer": "Xiaomi",
            "ro.boot.slot_suffix": "_" + self.slot,
            "ro.build.fingerprint": "Xiaomi/popsicle/popsicle:17/SIM.2/2:userdebug/test-keys",
        }

    def run(self, args, timeout=10, cwd=None):
        command = tuple(str(value) for value in args)
        if Path(command[0]).name != "fastboot" or command[1:] == ("devices", "-l"):
            return super().run(args, timeout=timeout, cwd=cwd)
        assert command[1:3] == ("-s", self.serial), "Only the reviewed phone may be addressed"
        operation = command[3:]
        sparse = operation[:2] == ("-S", "700M")
        if sparse:
            operation = operation[2:]
        if operation == ("oem", "device-info"):
            self.calls.append(command)
            output = (
                f"(bootloader) Device unlocked: {str(self.unlocked).lower()}\n"
                f"(bootloader) Device critical unlocked: {str(self.critical_unlocked).lower()}\n"
            )
            return CommandResult(command, 0, "", output)
        if operation[0] == "getvar":
            self.calls.append(command)
            variable = operation[1]
            values = {
                "product": self.product,
                "is-userspace": "yes" if self.mode == "fastbootd" else "no",
                "unlocked": "yes" if self.unlocked else "no",
                "current-slot": self.slot,
                "anti": "0",
            }
            if variable.startswith("partition-size:"):
                value = "0x320000000" if variable.endswith(":super") else "0x100000"
            elif variable.startswith("has-slot:"):
                value = "no" if variable.endswith(":super") else "yes"
            elif variable.startswith("is-logical:"):
                value = "no"
            else:
                assert variable in values, f"Unexpected read-only probe {variable}"
                value = values[variable]
            return CommandResult(command, 0, "", f"(bootloader) {variable}: {value}\n")
        assert operation[0] in {"flash", "erase", "set_active", "reboot"}, operation
        self.calls.append(command)
        self.changes.append(command[3:])
        partition = operation[1] if len(operation) > 1 else ""
        if operation[0] == "flash":
            assert sparse == (partition == "super"), "Only the super step declares -S 700M"
            contents = Path(operation[2]).read_bytes()
            assert contents.startswith(b"INERT SOURCE INSTALLATION IMAGE ")
            self.written.append((partition, contents))
        failed = (
            partition in {self.fail_partition, self.timeout_partition} and bool(partition)
        ) or len(self.changes) - 1 == self.fail_change_index
        if not failed and operation[0] == "set_active":
            assert partition == "a", "This source declares only slot A"
            self.slot = "a"
        elif not failed and operation[0] == "reboot":
            assert operation == ("reboot",)
            self.mode = "android"
        elif operation[0] == "erase":
            assert partition in {"metadata", "userdata"}
        if self.on_change:
            self.on_change(command)
        return CommandResult(
            command,
            124 if partition == self.timeout_partition and partition else 1 if failed else 0,
            "",
            "SIMULATION ONLY: inert transport result",
            timed_out=bool(partition and partition == self.timeout_partition),
        )


def synthetic_package(path: Path, declaration: bytes) -> None:
    """Construct only tiny synthetic images; the declaration remains inert data."""
    assert hashlib.sha256(declaration).hexdigest() == POPSICLE_SCRIPT_SHA256
    members = {"flash_all.sh": declaration}
    members.update(
        {
            f"images/{name}.img": f"INERT SOURCE INSTALLATION IMAGE {name}\n".encode() * 4
            for name in (*POPSICLE_PHYSICAL_PARTITIONS, "super", "vbmeta_system", "vbmeta")
        }
    )
    checksums = "".join(
        f"{hashlib.sha256(contents).hexdigest()}  ./{name}\n" for name, contents in members.items()
    )
    with zipfile.ZipFile(path, "w") as archive:
        for name, contents in members.items():
            archive.writestr("SIMULATED_PACKAGE/" + name, contents)
        archive.writestr("SIMULATED_PACKAGE/SHA256SUMS", checksums)


def click(button) -> None:
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)


def screenshot(app, dialog, path) -> None:
    app.processEvents()
    assert dialog.grab().save(str(path))


def compact_layout(dialog) -> bool:
    widgets = (dialog.review, dialog.progress, dialog.boundary, dialog.close_button)
    bounds = [(widget.mapTo(dialog, QPoint(0, 0)).y(), widget.height()) for widget in widgets]
    return all(widget.isVisible() for widget in widgets) and all(
        top + height - 1 < next_top
        for (top, height), (next_top, _height) in zip(bounds[:-1], bounds[1:], strict=True)
    )


def label_fits(label) -> bool:
    needed = QFontMetrics(label.font()).boundingRect(
        QRect(0, 0, label.contentsRect().width(), 10000),
        int(Qt.TextFlag.TextWordWrap),
        label.text(),
    )
    return label.isVisible() and needed.height() <= label.contentsRect().height()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--declaration",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "tests/fixtures/source-installation/flash_all.sh",
    )
    options = parser.parse_args(argv)
    if not 0 < options.declaration.stat().st_size <= 128 * 1024:
        parser.error("The inert declaration fixture exceeds its size limit.")
    declaration = options.declaration.read_bytes()
    if hashlib.sha256(declaration).hexdigest() != POPSICLE_SCRIPT_SHA256:
        parser.error("Use the exact reviewed declaration fixture; no script is ever executed.")
    root = options.output.absolute()
    root.mkdir(parents=False, exist_ok=False)
    store = RomProjectStore(root / "workspace")
    for name in ("adb", "fastboot"):
        tool = root / name
        tool.write_bytes(b"INERT SIMULATION TOOL - NOT EXECUTABLE CODE\n")
        tool.chmod(0o700)
    source = root / "HyperOS4-Xiaomi17ProMax-SIMULATION.zip"
    synthetic_package(source, declaration)
    project = store.import_original(
        store.create("SIMULATED complete source installation").project_id, source
    )
    source_service = SourceInstallationService(store)
    runner = InstallationPhone()
    flash = LocalFlashService(store.workspace, runner, root / "fastboot")
    executor = SourceInstallationExecutor(source_service, flash, root / "adb")
    start = datetime.now(UTC)
    boot = LocalBootService(
        flash,
        root / "adb",
        monotonic_clock=lambda: runner.seconds,
        utc_clock=lambda: start + timedelta(seconds=runner.seconds),
    )
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    apply_dark_palette(app)
    app.setStyleSheet(STYLESHEET)
    preparer = ProjectFlashPreparationService(store, DevicePackRegistry(()))
    operation_session = SourceOperationSession(
        None,
        (runner.device(),),
        project_id=project.project_id,
        source_sha256=project.original.sha256,
        preparation_service=preparer,
        source_service=source_service,
        installation_factory=lambda _preparation: executor,
        boot_service=boot,
    )
    chooser = ProjectPreparationDialog(
        preparer,
        project.project_id,
        source_service=source_service,
        session=operation_session,
        source_sha256=project.original.sha256,
    )
    chooser.findChild(QLabel, "Eyebrow").setText("SIMULATION ONLY  •  NO PHYSICAL PHONE")
    chooser.show()
    chooser.choice.setFocus()
    QTest.keyClick(chooser.choice, Qt.Key.Key_End)
    assert chooser.choice.currentData() == "source-installation"
    assert not chooser.wipe.isChecked() and chooser.reboot.isChecked()
    app.processEvents()
    preparation_readable = label_fits(chooser.limits)
    assert preparation_readable, "The source preparation warning is clipped."
    screenshot(app, chooser, root / "simulation-source-preparation.png")
    click(chooser.prepare_button)
    pump(app, lambda: chooser.preparation is not None and chooser.worker is None)
    assert runner.calls == []
    recipe = chooser.preparation
    assert len(recipe.images) == 50 and len(recipe.steps) == 53
    dialog = SourceInstallationDialog(
        executor,
        (runner.device(),),
        recipe=recipe,
        session=operation_session,
        boot_service=boot,
    )
    dialog.eyebrow.setText("SIMULATION ONLY  •  NO PHYSICAL PHONE")
    dialog.setWindowTitle("ROMVERSE · SIMULATED full procedure · no physical phone")
    dialog.resize(760, 720)
    dialog.show()
    app.processEvents()
    assert dialog.guided_primary.isVisible()
    assert not dialog.review_button.isVisible() and not dialog.flash_button.isVisible()
    click(dialog.guided_primary)
    pump(app, lambda: dialog.plan is not None and dialog.worker is None)
    assert runner.changes == []
    screenshot(app, dialog, root / "simulation-source-review.png")
    confirmation = confirm_next(app, accept=False)
    click(dialog.guided_primary)
    assert not confirmation.isActive() and dialog.worker is None
    assert runner.changes == []
    confirmation = confirm_next(app)
    click(dialog.guided_primary)
    pump(app, lambda: dialog.boot_report is not None and dialog.worker is None)
    assert not confirmation.isActive()
    assert dialog.result.state == "completed" and not dialog.result.boot_verified
    assert len(runner.changes) == 53 and len(runner.written) == 50
    assert not any(operation[0] == "erase" for operation in runner.changes)
    installation_record = dialog.result.receipt_path.read_bytes()
    while dialog.monitoring:
        dialog.boot_timer.stop()
        runner.seconds += 6
        dialog._poll_boot()
        pump(app, lambda: dialog.worker is None)
        assert runner.seconds <= 100, dialog.status.text()
    assert dialog.boot_report.status == "stable"
    assert dialog.result.receipt_path.read_bytes() == installation_record
    assert not dialog.result.boot_verified
    assert store.verify_original(project.project_id).valid
    assert flash.audit.verify().valid
    retained_session = dialog.session
    retained_result = dialog.result
    retained_changes = tuple(runner.changes)
    dialog.set_experience_mode(ExperienceMode.EXPERT)
    app.processEvents()
    assert dialog.session is retained_session
    assert dialog.result is retained_result
    assert tuple(runner.changes) == retained_changes
    readable = compact_layout(dialog)
    assert readable, (
        "The compact installation results overlap their progress, warning or Close controls."
    )
    screenshot(app, dialog, root / "simulation-source-stable-boot.png")
    original_boot_report = dialog.boot_report
    changes_before_history = tuple(runner.changes)
    calls_before_history = len(runner.calls)
    dialog.close()
    app.processEvents()
    outcome = load_latest_source_installation(store, project.project_id)
    assert outcome is not None and outcome.result is not None
    assert outcome.boot_receipt_path == original_boot_report.receipt_path
    history = SourceInstallationHistoryDialog(
        flash, (runner.device(),), outcome=outcome, boot_service=boot
    )
    history.eyebrow.setText("SIMULATION ONLY  •  REOPENED READ-ONLY HISTORY")
    history.setWindowTitle("ROMVERSE · SIMULATED saved history · no physical phone")
    history.resize(760, 720)
    history.show()
    app.processEvents()
    assert history.images.isHidden()
    assert not history.monitoring and len(runner.calls) == calls_before_history
    assert history.boot_button.isEnabled()
    screenshot(app, history, root / "simulation-source-history.png")
    click(history.boot_button)
    pump(app, lambda: history.boot_report is not None and history.worker is None)
    while history.monitoring:
        history.boot_timer.stop()
        runner.seconds += 6
        history._poll_boot()
        pump(app, lambda: history.worker is None)
        assert runner.seconds <= 180, history.status.text()
    assert history.boot_report.status == "stable"
    assert history.boot_report.elapsed_seconds == 60
    assert tuple(runner.changes) == changes_before_history
    assert outcome.receipt_path.read_bytes() == installation_record
    assert not history.result.boot_verified
    history_boot_record = json.loads(history.boot_report.receipt_path.read_text())
    assert (
        history_boot_record["flash_binding"]["relative_path"]
        == outcome.receipt_path.relative_to(store.workspace).as_posix()
    )
    history_readable = compact_layout(history)
    assert history_readable, "The compact history results overlap progress, warning or Close."
    screenshot(app, history, root / "simulation-source-history-stable-boot.png")
    assert flash.audit.verify().valid
    report = {
        "simulation_only": True,
        "physical_phone_changed": False,
        "production_certified": False,
        "clock": "injected accelerated simulation clock",
        "source_procedure_explicitly_selected": True,
        "decline_sent_no_mutating_command": True,
        "source_declared_complete_procedure": True,
        "simulated_action_count": len(runner.changes),
        "simulated_image_write_count": len(runner.written),
        "simulated_actions": [
            list(operation[:-1] if "flash" in operation else operation)
            for operation in runner.changes
        ],
        "explicit_wipe_selected": recipe.wipe,
        "initial_slot": "b",
        "final_simulated_slot": runner.slot,
        "android_reboot_requested": dialog.result.reboot_requested,
        "android_arrival_observed": dialog.result.android_arrival_verified,
        "installation_result_boot_verified": dialog.result.boot_verified,
        "separate_observed_boot_status": dialog.boot_report.status.value,
        "simulated_boot_window_seconds": original_boot_report.elapsed_seconds,
        "boot_sample_count": original_boot_report.sample_count,
        "installation_receipt_unchanged": True,
        "installation_receipt_sha256": hashlib.sha256(installation_record).hexdigest(),
        "source_sha256": recipe.source_sha256,
        "script_sha256": recipe.script_sha256,
        "source_unchanged": True,
        "audit_valid": True,
        "compact_layout_readable": readable,
        "preparation_warning_readable": preparation_readable,
        "preparation_and_installation_same_session": dialog.session is operation_session,
        "history_reopened_from_saved_receipt": True,
        "history_open_sent_no_phone_command": True,
        "history_boot_explicitly_requested": True,
        "history_additional_changing_action_count": len(runner.changes)
        - len(changes_before_history),
        "history_boot_window_seconds": history.boot_report.elapsed_seconds,
        "history_boot_sample_count": history.boot_report.sample_count,
        "history_boot_status": history.boot_report.status.value,
        "history_boot_linked_to_original_installation": True,
        "history_installation_receipt_unchanged": True,
        "history_compact_layout_readable": history_readable,
        "history_dialog_size": [history.width(), history.height()],
        "dialog_size": [dialog.width(), dialog.height()],
        "output": str(root),
    }
    (root / "simulation-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    history.close()
    dialog.close()
    chooser.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
