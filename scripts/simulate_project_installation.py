"""Capture a Guided installation journey using production UI and inert phone transport.

Only a NEW output directory is accepted. All firmware, device observations and
tools are synthetic. The boot clock is accelerated; this is not hardware proof.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel
from simulate_expert_lifecycle import SimulatedAndroid, confirm_next, pump

from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.local_flash import LocalFlashService
from romverse.guardian.local_transition import LocalDeviceTransitionService, LocalTransitionTarget
from romverse.rom.inspection import RomInspectionService
from romverse.rom.local_boot import LocalBootService
from romverse.rom.project_flash import (
    BoundProjectFlashService,
    BoundProjectTransitionService,
    ProjectFlashPreparationService,
)
from romverse.rom.projects import RomProjectStore
from romverse.rom.source_intelligence import FirmwareSourceIntelligenceService
from romverse.ui.project_flash import ProjectFlashDialog, ProjectPreparationDialog
from romverse.ui.theme import STYLESHEET, apply_dark_palette


class SimulatedPopsicle(SimulatedAndroid):
    product = "popsicle"

    def device(self):
        return replace(
            super().device(), manufacturer="Xiaomi", model="SIMULATED test phone · no hardware"
        )

    def properties(self):
        return {
            **super().properties(),
            "ro.product.manufacturer": "Xiaomi",
            "ro.product.model": "SIMULATED test phone",
            "ro.build.fingerprint": "simulation/popsicle/popsicle:17/SIM.2/2:userdebug/test-keys",
        }


def click(button) -> None:
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)


def screenshot(app, dialog, path) -> None:
    app.processEvents()
    assert dialog.grab().save(str(path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    root = parser.parse_args().output.absolute()
    root.mkdir(parents=False, exist_ok=False)
    store = RomProjectStore(root / "workspace")
    for name in ("adb", "fastboot"):
        tool = root / name
        tool.write_bytes(b"INERT SIMULATION TOOL - NOT EXECUTABLE CODE\n")
        tool.chmod(0o700)
    source = root / ("popsicle_images_OS4.0.0.25.XPBCNXM_20260804.0000.00_17.0_cn_SIMULATION.zip")
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("images/boot.img", b"ROMVERSE INERT SIMULATION IMAGE\n")
        archive.writestr("android-info.txt", "require product=popsicle\n")
    project = store.import_original(
        store.create("SIMULATED Guided installation").project_id, source
    )
    RomInspectionService(store).extract_project_tree(project.project_id)
    runner = SimulatedPopsicle()
    runner.mode = "bootloader"
    FirmwareSourceIntelligenceService(store, (), runner).prepare(project.project_id)
    preparer = ProjectFlashPreparationService(store, DevicePackRegistry(()))
    flash = LocalFlashService(store.workspace, runner, root / "fastboot")
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
    chooser = ProjectPreparationDialog(preparer, project.project_id)
    chooser.findChild(QLabel, "Eyebrow").setText("SIMULATION ONLY  •  NO PHYSICAL PHONE")
    chooser.show()
    chooser.choice.setFocus()
    QTest.keyClick(chooser.choice, Qt.Key.Key_End)
    assert chooser.choice.currentData() == "protected"
    screenshot(app, chooser, root / "simulation-project-preparation.png")
    click(chooser.prepare_button)
    pump(app, lambda: chooser.preparation is not None and chooser.worker is None)
    assert not runner.calls
    preparation = chooser.preparation
    bound = BoundProjectFlashService(preparer, preparation, flash)
    transitions = BoundProjectTransitionService(
        preparer, preparation, LocalDeviceTransitionService(flash, root / "adb")
    )
    dialog = ProjectFlashDialog(
        bound,
        (runner.device(),),
        preparation=preparation,
        transition_service=transitions,
        boot_service=boot,
    )
    dialog.eyebrow.setText("SIMULATION ONLY  •  NO PHYSICAL PHONE")
    dialog.show()
    app.processEvents()
    click(dialog.add_button)
    assert dialog.images.rowCount() == 1 and dialog.images.item(0, 0).text() == ""
    dialog.images.setCurrentCell(0, 0)
    dialog.images.setFocus()
    QTest.keyClick(dialog.images, Qt.Key.Key_F2)
    editor = QApplication.focusWidget()
    assert editor is not None and editor is not dialog.images
    QTest.keyClicks(editor, "boot_a")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    app.processEvents()
    assert dialog.images.item(0, 0).text() == "boot_a"
    click(dialog.review_button)
    pump(app, lambda: dialog.plan is not None and dialog.worker is None)
    assert not any("flash" in command for command in runner.calls)
    screenshot(app, dialog, root / "simulation-project-image-review.png")
    confirmation = confirm_next(app, accept=False)
    click(dialog.flash_button)
    assert not confirmation.isActive() and dialog.worker is None
    assert not any("flash" in command for command in runner.calls)
    confirmation = confirm_next(app)
    click(dialog.flash_button)
    pump(app, lambda: dialog.result is not None and dialog.worker is None)
    assert not confirmation.isActive()
    assert dialog.result.state == "completed" and not dialog.result.boot_verified
    flash_record = dialog.result.receipt_path.read_bytes()
    dialog.mode_target.setCurrentIndex(dialog.mode_target.findData(LocalTransitionTarget.ANDROID))
    confirmation = confirm_next(app)
    click(dialog.mode_button)
    pump(app, lambda: dialog.boot_report is not None and dialog.worker is None)
    assert not confirmation.isActive()
    assert dialog.transition_result.arrival_verified and not dialog.transition_result.boot_verified
    while dialog.monitoring:
        dialog.boot_timer.stop()
        runner.seconds += 6
        dialog._poll_boot()
        pump(app, lambda: dialog.worker is None)
        assert runner.seconds <= 100, dialog.status.text()
    assert dialog.boot_report.status == "stable"
    assert dialog.result.receipt_path.read_bytes() == flash_record
    assert store.verify_original(project.project_id).valid and flash.audit.verify().valid
    app.processEvents()
    widgets = (dialog.review, dialog.progress, dialog.boundary, dialog.close_button)
    # Map every widget to the dialog, including buttons nested inside action layouts.
    bounds = [(widget.mapTo(dialog, QPoint(0, 0)).y(), widget.height()) for widget in widgets]
    compact_layout_readable = all(widget.isVisible() for widget in widgets) and all(
        top + height - 1 < next_top
        for (top, height), (next_top, _next_height) in zip(bounds[:-1], bounds[1:], strict=True)
    )
    assert compact_layout_readable, f"Boot-results widgets overlap: {bounds}"
    screenshot(app, dialog, root / "simulation-project-stable-boot.png")
    report = {
        "simulation_only": True,
        "physical_phone_changed": False,
        "production_certified": False,
        "full_firmware_install": False,
        "clock": "injected accelerated simulation clock",
        "protected_source_explicitly_selected": True,
        "destination_initially_blank": True,
        "destination_manually_entered": "boot_a",
        "decline_sent_no_write": True,
        "confirmed_image_write_count": sum("flash" in command for command in runner.calls),
        "confirmed_android_arrival": dialog.transition_result.arrival_verified,
        "observed_boot_status": dialog.boot_report.status.value,
        "simulated_boot_window_seconds": runner.seconds,
        "boot_sample_count": dialog.boot_report.sample_count,
        "flash_receipt_unchanged": True,
        "flash_receipt_sha256": hashlib.sha256(flash_record).hexdigest(),
        "source_sha256": preparation.source_sha256,
        "source_unchanged": True,
        "audit_valid": True,
        "compact_layout_readable": compact_layout_readable,
        "output": str(root),
    }
    (root / "simulation-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    dialog.close()
    chooser.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
