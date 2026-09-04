"""Exercise the production Expert UI/services with a strictly inert Android transport.

No subprocess, physical phone, firmware archive, or existing workspace is used.
The output directory must be new. Screenshots and journals are simulation evidence,
not hardware validation. Run with QT_QPA_PLATFORM=offscreen when no display is wanted.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic, sleep

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

from romverse.device.models import AndroidDevice, DeviceState
from romverse.guardian.local_flash import LocalFlashService
from romverse.guardian.local_transition import LocalDeviceTransitionService, LocalTransitionTarget
from romverse.infrastructure.process import CommandResult
from romverse.rom.local_boot import LocalBootService
from romverse.ui.local_flash import LocalFlashDialog
from romverse.ui.theme import STYLESHEET, apply_dark_palette


class SimulatedAndroid:
    """Only known commands produce fixture observations; nothing is executed."""

    serial = "SIMULATED-USB-0001"
    product = "romverse_simulator"

    def __init__(self) -> None:
        self.mode = "android"
        self.product_alias = self.product
        self.seconds = 0.0
        self.restart = 0
        self.calls: list[tuple[str, ...]] = []

    def device(self) -> AndroidDevice:
        return AndroidDevice(
            self.serial,
            {
                "android": DeviceState.DEVICE,
                "bootloader": DeviceState.BOOTLOADER,
                "fastbootd": DeviceState.FASTBOOTD,
            }[self.mode],
            manufacturer="ROMVERSE SIMULATION",
            model="Virtual test phone",
            product=self.product,
            codename=self.product,
            ab_update=True,
        )

    def properties(self) -> dict[str, str]:
        return {
            "sys.boot_completed": "1",
            "ro.product.device": self.product,
            "ro.product.name": self.product_alias,
            "ro.product.manufacturer": "ROMVERSE SIMULATION",
            "ro.product.model": "Virtual test phone",
            "ro.build.id": "SIM.2",
            "ro.build.version.release": "17",
            "ro.build.fingerprint": "simulation/romverse_simulator/romverse_simulator:17/SIM.2/2:userdebug/test-keys",
            "ro.boot.slot_suffix": "_a",
            "ro.bootmode": "normal",
        }

    def run(self, args, timeout=10, cwd=None):
        del timeout, cwd
        command = tuple(str(value) for value in args)
        self.calls.append(command)
        tool = Path(command[0]).name
        assert tool in {"adb", "fastboot"}
        output, error = "", ""
        if command[1:] == ("devices", "-l"):
            if tool == "adb":
                output = "List of devices attached\n" + (
                    f"{self.serial} device usb:1-1 product:{self.product} model:Virtual_test_phone device:{self.product}\n"
                    if self.mode == "android"
                    else ""
                )
            elif self.mode != "android":
                output = f"{self.serial} fastboot usb:1-1\n"
        else:
            assert command[1:3] == ("-s", self.serial), "No other device may be addressed"
            operation = command[3:]
            if operation[0] == "reboot":
                assert operation in {("reboot",), ("reboot", "bootloader"), ("reboot", "fastboot")}
                self.mode = (
                    "android"
                    if len(operation) == 1
                    else "fastbootd"
                    if operation[1] == "fastboot"
                    else "bootloader"
                )
            elif tool == "adb" and operation[:2] == ("shell", "getprop"):
                props = self.properties()
                output = (
                    "\n".join(f"[{key}]: [{value}]" for key, value in props.items())
                    if len(operation) == 2
                    else props[operation[2]]
                )
            elif tool == "adb" and operation == ("shell", "cat", "/proc/uptime"):
                output = f"{100 + self.seconds} 5000.0\n"
            elif tool == "adb" and operation == ("shell", "cat", "/proc/sys/kernel/random/boot_id"):
                output = f"00000000-0000-4000-8000-{self.restart + 1:012d}\n"
            elif tool == "fastboot" and operation[0] == "getvar":
                variable = operation[1]
                values = {
                    "product": self.product,
                    "is-userspace": "yes" if self.mode == "fastbootd" else "no",
                    "current-slot": "a",
                    "unlocked": "yes",
                    "partition-size:boot_a": "0x1000",
                    "has-slot:boot": "yes",
                    "is-logical:boot_a": "no",
                }
                error = f"(bootloader) {variable}: {values[variable]}\n"
            elif tool == "fastboot" and operation[:2] == ("flash", "boot_a"):
                assert Path(operation[2]).read_bytes() == b"ROMVERSE INERT SIMULATION IMAGE\n"
                error = "SIMULATION ONLY: selected image accepted by inert transport.\n"
            else:
                raise AssertionError(f"Unexpected simulated operation: {operation}")
        return CommandResult(command, 0, output, error)


def pump(app: QApplication, condition, timeout: float = 8) -> None:
    deadline = monotonic() + timeout
    while not condition() and monotonic() < deadline:
        app.processEvents()
        sleep(0.005)
    if not condition():
        raise AssertionError("The simulated UI operation did not finish")


def confirm_next(app: QApplication, *, accept: bool = True) -> QTimer:
    timer = QTimer()

    def click() -> None:
        question = app.activeModalWidget()
        if isinstance(question, QMessageBox):
            timer.stop()
            if accept:
                next(
                    button
                    for button in question.buttons()
                    if question.buttonRole(button) is QMessageBox.ButtonRole.AcceptRole
                ).click()
            else:
                question.button(QMessageBox.StandardButton.Cancel).click()

    timer.timeout.connect(click)
    timer.start(5)
    return timer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    options = parser.parse_args()
    root = options.output.absolute()
    root.mkdir(parents=False, exist_ok=False)
    workspace = root / "workspace"
    workspace.mkdir()
    for name in ("adb", "fastboot"):
        path = root / name
        path.write_bytes(b"INERT SIMULATION TOOL - NOT EXECUTABLE CODE\n")
        path.chmod(0o700)
    firmware = root / "boot.img"
    firmware.write_bytes(b"ROMVERSE INERT SIMULATION IMAGE\n")
    runner = SimulatedAndroid()
    flash = LocalFlashService(workspace, runner, root / "fastboot")
    transitions = LocalDeviceTransitionService(flash, root / "adb")
    boot = LocalBootService(
        flash,
        root / "adb",
        monotonic_clock=lambda: runner.seconds,
        utc_clock=lambda: datetime(2026, 9, 5, tzinfo=UTC) + timedelta(seconds=runner.seconds),
    )
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    apply_dark_palette(app)
    app.setStyleSheet(STYLESHEET)
    dialog = LocalFlashDialog(
        flash, (runner.device(),), transition_service=transitions, boot_service=boot
    )
    dialog.setWindowTitle("ROMVERSE · Simulated user journey · no physical phone")
    dialog.findChild(QLabel, "Eyebrow").setText("SIMULATED USER JOURNEY  •  NO PHYSICAL PHONE")
    dialog.show()
    app.processEvents()
    confirmation = confirm_next(app, accept=False)
    dialog.mode_button.click()
    pump(app, lambda: dialog.worker is None and not confirmation.isActive())
    assert not any("reboot" in command for command in runner.calls)
    confirmation = confirm_next(app)
    dialog.mode_button.click()
    pump(app, lambda: dialog.transition_result is not None and dialog.worker is None)
    assert dialog.transition_result.state == "completed" and runner.mode == "bootloader"
    dialog.add_image(firmware, "boot_a")
    dialog.review_button.click()
    pump(app, lambda: dialog.plan is not None and dialog.worker is None)
    assert dialog.grab().save(str(root / "simulation-image-review.png"))
    confirmation = confirm_next(app)
    dialog.flash_button.click()
    pump(app, lambda: dialog.result is not None and dialog.worker is None)
    assert dialog.result.state == "completed" and dialog.result.boot_verified is False
    flash_receipt = dialog.result.receipt_path.read_bytes()
    # Changing a ROM's regional product name must not override its matching hardware identity.
    runner.product_alias = runner.product + "_regional"
    dialog.mode_target.setCurrentIndex(dialog.mode_target.findData(LocalTransitionTarget.ANDROID))
    confirmation = confirm_next(app)
    dialog.mode_button.click()
    pump(app, lambda: dialog.boot_report is not None and dialog.worker is None)
    while dialog.monitoring:
        dialog.boot_timer.stop()
        runner.seconds += 6
        dialog._poll_boot()
        pump(app, lambda: dialog.worker is None)
        assert runner.seconds <= 100, dialog.status.text()
    assert dialog.boot_report.status == "stable"
    assert dialog.result.receipt_path.read_bytes() == flash_receipt
    assert flash.audit.verify().valid
    assert dialog.grab().save(str(root / "simulation-stable-boot.png"))
    dialog.boot_button.click()
    pump(app, lambda: dialog.boot_report is not None and dialog.worker is None)
    for _ in range(2):
        dialog.boot_timer.stop()
        runner.seconds += 6
        runner.restart += 1
        dialog._poll_boot()
        pump(app, lambda: dialog.worker is None)
    assert (
        dialog.boot_report.status == "attention"
        and dialog.boot_report.failure_kind == "reboot_loop"
    )
    assert dialog.recovery_requested and not dialog.monitoring
    assert dialog.result.receipt_path.read_bytes() == flash_receipt
    print(
        json.dumps(
            {
                "simulation_only": True,
                "physical_phone_changed": False,
                "decline_sent_no_reboot": True,
                "confirmed_mode_transition": True,
                "confirmed_image_write": True,
                "matching_hardware_region_variant": True,
                "measured_boot_window_seconds": 60,
                "bootloop_handoff": True,
                "audit_valid": flash.audit.verify().valid,
                "output": str(root),
            },
            indent=2,
        )
    )
    dialog.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
