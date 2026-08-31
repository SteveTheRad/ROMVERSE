from __future__ import annotations

import platform
import shlex
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from romverse.companion.raw_terminal import RawTerminalFeed
from romverse.device.models import AndroidDevice, DeviceState
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.models import OperationClass, OperationRequest
from romverse.ui.background import ManagedRunnable, start_background
from romverse.ui.process_progress import ProcessProgressBar


class TerminalSignals(QObject):
    complete = Signal(str)


class TerminalWorker(ManagedRunnable):
    def __init__(
        self,
        command: list[str],
        gateway: ExecutionGateway | None,
        adb_executable: Path | None,
        device_serial: str,
        device_command: bool,
    ) -> None:
        super().__init__()
        self.command = command
        self.gateway = gateway
        self.adb_executable = adb_executable
        self.device_serial = device_serial
        self.device_command = device_command
        self.signals = TerminalSignals()

    @Slot()
    def execute(self) -> None:
        try:
            if self.command == ["host", "platform"]:
                self.signals.complete.emit(f"$ host platform\n{platform.platform()}")
                return
            if self.command == ["host", "python-version"]:
                self.signals.complete.emit(f"$ host python-version\n{sys.version}")
                return
            if self.gateway is None or self.adb_executable is None:
                self.signals.complete.emit(
                    "$ adb <approved read-only probe>\n"
                    "Command Console unavailable: verified ADB and Guardian are not ready."
                )
                return
            adb_args = tuple(self.command[1:])
            display_args = adb_args
            target = "host"
            if self.device_command:
                if not self.device_serial:
                    self.signals.complete.emit(
                        "$ adb -s <selected-device> <approved read-only probe>\n"
                        "No authorized Android device is selected. Connect and authorize a device, then refresh."
                    )
                    return
                adb_args = ("-s", self.device_serial, *adb_args)
                display_args = ("-s", "<selected-device>", *display_args)
                target = self.device_serial
            request = OperationRequest(
                operation_id="console.read",
                category=OperationClass.READ_ONLY,
                executable=str(self.adb_executable),
                arguments=adb_args,
                purpose="Command Console approved read-only inspection",
                target=target,
            )
            result = self.gateway.execute(request, timeout=15)
            output = result.stdout.strip() or result.stderr.strip() or "(no output)"
            self.signals.complete.emit(
                f"$ adb {shlex.join(display_args)}\n{output}\n\nExit code: {result.returncode}"
            )
        except Exception as exc:  # UI boundary converts policy/adapter failures to visible state
            self.signals.complete.emit(
                f"$ <approved read-only probe>\nCommand Console error: {exc}"
            )


class TerminalCenter(QWidget):
    """Guardian-bounded terminal for safe host and read-only ADB inspection."""

    _PRESETS = {
        "ADB devices": ["adb", "devices", "-l"],
        "ADB version": ["adb", "version"],
        "Device model": ["adb", "shell", "getprop", "ro.product.model"],
        "Android version": ["adb", "shell", "getprop", "ro.build.version.release"],
        "Battery details": ["adb", "shell", "dumpsys", "battery"],
        "Storage details": ["adb", "shell", "df", "-k", "/data"],
        "Verified Boot state": ["adb", "shell", "getprop", "ro.boot.verifiedbootstate"],
        "Host platform": ["host", "platform"],
        "Python version": ["host", "python-version"],
    }
    _ALLOWED = {tuple(command) for command in _PRESETS.values()}
    _DEVICE_COMMANDS = {
        tuple(command) for command in _PRESETS.values() if command[:2] == ["adb", "shell"]
    }
    _LINK_PROBES = {
        ("adb", "version"): "adb-version",
        ("adb", "shell", "getprop", "ro.product.model"): "device-model",
        ("adb", "shell", "getprop", "ro.build.version.release"): "android-version",
        ("adb", "shell", "dumpsys", "battery"): "battery-details",
        ("adb", "shell", "df", "-k", "/data"): "storage-details",
        ("adb", "shell", "getprop", "ro.boot.verifiedbootstate"): "verified-boot-state",
    }

    def __init__(
        self,
        gateway: ExecutionGateway | None = None,
        adb_executable: Path | None = None,
        raw_terminal_feed: RawTerminalFeed | None = None,
    ) -> None:
        super().__init__()
        self.gateway = gateway
        self.adb_executable = adb_executable
        self.raw_terminal_feed = raw_terminal_feed
        self._device_serial = ""
        self._active_probe_id = ""
        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 30)
        page.setSpacing(16)
        eyebrow = QLabel("COMMAND CONSOLE  •  GUARDIAN-BOUNDED")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("Command Console")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Run approved host and read-only ADB checks without leaving ROMVERSE. Destructive commands are blocked."
        )
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        page.addWidget(eyebrow)
        page.addWidget(title)
        page.addWidget(subtitle)

        controls = QFrame()
        controls.setObjectName("Card")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(18, 16, 18, 16)
        row = QHBoxLayout()
        self.preset = QComboBox()
        self.preset.addItems(self._PRESETS)
        self.preset.currentTextChanged.connect(self._preset_changed)
        self.command = QLineEdit()
        self.command.setPlaceholderText("Choose an approved check or type an exact safe command")
        self.command.returnPressed.connect(self.run_command)
        self.run_button = QPushButton("Run check")
        self.run_button.setObjectName("Primary")
        self.run_button.clicked.connect(self.run_command)
        row.addWidget(self.preset)
        row.addWidget(self.command, 1)
        row.addWidget(self.run_button)
        clear = QPushButton("Clear")
        clear.setToolTip("Clear the local terminal output; no device data is changed.")
        clear.clicked.connect(self.output_clear)
        copy = QPushButton("Copy")
        copy.setToolTip("Copy the visible output for troubleshooting or support.")
        copy.clicked.connect(self.output_copy)
        row.addWidget(clear)
        row.addWidget(copy)
        controls_layout.addLayout(row)
        note = QLabel(
            "Allowed: ADB identity, battery, storage, Verified Boot, host platform, and version checks.\n"
            "Phone-changing commands, shells, pipes, redirects, and package/flash operations are rejected."
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        controls_layout.addWidget(note)
        self.progress = ProcessProgressBar()
        self.progress.setAccessibleName("Command Console probe progress")
        controls_layout.addWidget(self.progress)
        page.addWidget(controls)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Command output will appear here…")
        self.output.setMinimumHeight(360)
        self.output.setStyleSheet(
            "background:#050812; border:1px solid #253462; border-radius:12px; "
            "padding:14px; font-family:monospace; font-size:13px; color:#D8E7FF;"
        )
        page.addWidget(self.output, 1)
        self._worker: TerminalWorker | None = None
        self._preset_changed(self.preset.currentText())

    def set_runtime(
        self,
        gateway: ExecutionGateway | None,
        adb_executable: Path | None,
    ) -> None:
        self.gateway = gateway
        self.adb_executable = adb_executable

    def set_devices(self, devices: list[AndroidDevice]) -> None:
        authorized = next(
            (device for device in devices if device.state is DeviceState.DEVICE),
            None,
        )
        self._device_serial = authorized.serial if authorized is not None else ""

    def _preset_changed(self, name: str) -> None:
        self.command.setText(shlex.join(self._PRESETS[name]))

    def run_command(self) -> None:
        if self._worker is not None:
            self.output.append(
                "A Guardian-approved check is already running. Wait for its verified result."
            )
            return
        try:
            command = shlex.split(self.command.text().strip())
        except ValueError as exc:
            self.output.append(f"Input error: {exc}")
            return
        if not command:
            return
        if tuple(command) not in self._ALLOWED:
            self.output.append(
                "Guardian blocked this command. Use one of the approved read-only checks."
            )
            return
        is_device_command = tuple(command) in self._DEVICE_COMMANDS
        if is_device_command and not self._device_serial:
            self.output.append(
                "No authorized Android device is selected. Connect and authorize a device, then refresh."
            )
            return
        display = command
        if is_device_command:
            display = ["adb", "-s", "<selected-device>", *command[1:]]
        self.output.append(f"Running {shlex.join(display)} …")
        self._worker = TerminalWorker(
            command,
            self.gateway,
            self.adb_executable,
            self._device_serial,
            is_device_command,
        )
        self._active_probe_id = self._LINK_PROBES.get(tuple(command), "")
        self._worker.signals.complete.connect(self._complete)
        self._set_busy(True)
        start_background(self._worker)

    def _set_busy(self, busy: bool) -> None:
        self.preset.setEnabled(not busy)
        self.command.setEnabled(not busy)
        self.run_button.setEnabled(not busy)
        if busy:
            self.run_button.setText("Running approved check …")
            self.progress.begin()
        else:
            self.run_button.setText("Run check")
            self.progress.stop()

    def output_clear(self) -> None:
        self.output.clear()
        if self.raw_terminal_feed is not None:
            self.raw_terminal_feed.clear()

    def output_copy(self) -> None:
        QApplication.clipboard().setText(self.output.toPlainText())

    @Slot(str)
    def _complete(self, output: str) -> None:
        self.output.append(output)
        if self.raw_terminal_feed is not None and self._active_probe_id:
            self.raw_terminal_feed.publish(
                self._active_probe_id,
                output,
                private_values=(self._device_serial,),
            )
        self._active_probe_id = ""
        self._worker = None
        self._set_busy(False)
