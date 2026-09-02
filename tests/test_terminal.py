import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from romverse.companion.raw_terminal import RawTerminalFeed
from romverse.device.models import AndroidDevice, DeviceState
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.policy import MilestoneOnePolicy
from romverse.infrastructure.process import CommandResult
from romverse.ui.terminal_center import TerminalCenter, TerminalWorker


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, args, timeout=10, cwd=None):
        call = tuple(args)
        self.calls.append(call)
        return CommandResult(call, 0, "Battery level: 100\n", "")


def test_terminal_allowlist_contains_read_only_device_checks() -> None:
    assert ("adb", "shell", "dumpsys", "battery") in TerminalCenter._ALLOWED
    assert ("adb", "shell", "df", "-k", "/data") in TerminalCenter._ALLOWED


def test_terminal_allowlist_rejects_device_changing_commands() -> None:
    assert ("adb", "shell", "rm", "-rf", "/data") not in TerminalCenter._ALLOWED
    assert ("fastboot", "flash", "boot", "boot.img") not in TerminalCenter._ALLOWED


def test_terminal_worker_routes_device_probe_through_guardian_and_masks_serial() -> None:
    runner = RecordingRunner()
    worker = TerminalWorker(
        ["adb", "shell", "dumpsys", "battery"],
        ExecutionGateway(MilestoneOnePolicy(), runner),
        Path("/opt/android/adb"),
        "private-serial",
        True,
    )
    outputs: list[str] = []
    worker.signals.complete.connect(outputs.append)

    worker.run()

    assert runner.calls == [
        ("/opt/android/adb", "-s", "private-serial", "shell", "dumpsys", "battery")
    ]
    assert "private-serial" not in outputs[0]
    assert "<selected-device>" in outputs[0]


def test_terminal_selects_only_authorized_device() -> None:
    app = QApplication.instance() or QApplication([])
    center = TerminalCenter()
    center.set_devices(
        [
            AndroidDevice("offline", DeviceState.OFFLINE),
            AndroidDevice("authorized", DeviceState.DEVICE),
        ]
    )

    assert center._device_serial == "authorized"
    center.close()
    app.processEvents()


def test_command_console_opens_its_exact_local_archives_guide_without_running() -> None:
    app = QApplication.instance() or QApplication([])
    center = TerminalCenter()
    requested: list[str] = []
    center.knowledge_article_requested.connect(requested.append)

    center.guide_button.click()

    assert requested == ["command-console-no-trusted-result"]
    assert center._worker is None
    assert not center.output.toPlainText()
    center.close()
    app.processEvents()


def test_raw_terminal_feed_accepts_only_privacy_filtered_read_only_probes() -> None:
    feed = RawTerminalFeed()
    private_serial = "private-device-serial"
    digest = "a" * 64
    output = (
        "$ adb -s private-device-serial shell dumpsys battery\n"
        "Installed path: /home/steve/private/platform-tools/adb\n"
        f"Digest: {digest}\nToken: secret-value\nExit code: 0"
    )

    record = feed.publish(
        "battery-details",
        output,
        private_values=(private_serial,),
    )

    assert record is not None
    visible = "\n".join(record.lines)
    assert private_serial not in visible
    assert "/home/steve" not in visible
    assert digest not in visible
    assert "secret-value" not in visible
    assert "<private-device>" in visible
    assert "<local-path>" in visible
    assert "<sha256>" in visible
    assert "<private-credential>" in visible
    assert len(record.record_digest) == 64
    assert feed.publish("adb-devices", "serial list") is None
    assert feed.publish("host-platform", "private host") is None
    failed = feed.publish("adb-version", "$ adb version\nfailed\n\nExit code: 1")
    assert failed is not None and not failed.success


def test_command_console_publishes_and_clears_companion_raw_terminal_feed() -> None:
    app = QApplication.instance() or QApplication([])
    feed = RawTerminalFeed()
    center = TerminalCenter(raw_terminal_feed=feed)
    center._device_serial = "private-serial"
    center._active_probe_id = "device-model"

    center._complete(
        "$ adb -s private-serial shell getprop ro.product.model\nXiaomi 17 Pro Max\n\nExit code: 0"
    )

    assert len(feed.snapshot()) == 1
    assert "private-serial" not in "\n".join(feed.snapshot()[0].lines)
    center.output_clear()
    assert feed.snapshot() == ()
    center.close()
    app.processEvents()


def test_command_console_locks_duplicate_probes_and_shows_real_busy_progress(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    center = TerminalCenter()
    started = []
    monkeypatch.setattr(
        "romverse.ui.terminal_center.start_background",
        lambda worker: started.append(worker),
    )
    center.preset.setCurrentText("Host platform")

    center.run_command()

    assert len(started) == 1
    assert center._worker is started[0]
    assert not center.run_button.isEnabled()
    assert not center.command.isEnabled()
    assert not center.preset.isEnabled()
    assert not center.progress.isHidden()
    assert center.progress.minimum() == 0
    assert center.progress.maximum() == 0

    center.run_command()
    assert len(started) == 1
    assert "already running" in center.output.toPlainText()

    center._complete("$ adb devices -l\n(no output)\n\nExit code: 0")
    assert center._worker is None
    assert center.run_button.isEnabled()
    assert center.command.isEnabled()
    assert center.preset.isEnabled()
    assert center.progress.isHidden()

    center.close()
    app.processEvents()


def test_command_console_resolves_missing_adb_before_starting_probe(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    center = TerminalCenter()
    started = []
    requested = []
    runner = RecordingRunner()
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner)
    monkeypatch.setattr(
        "romverse.ui.terminal_center.start_background",
        lambda worker: started.append(worker),
    )
    center.runtime_tools_requested.connect(
        lambda: (
            requested.append(True),
            center.set_runtime(gateway, Path("/opt/android/adb")),
        )
    )

    assert center.run_button.text() == "Resolve Platform Tools"
    center.run_command()

    assert requested == [True]
    assert len(started) == 1
    assert center._worker is started[0]
    assert "checking the managed toolchain" in center.output.toPlainText()
    center._complete("$ adb devices -l\n(no output)\n\nExit code: 0")
    assert center.run_button.text() == "Run check"
    center.close()
    app.processEvents()


def test_command_console_does_not_start_when_adb_resolution_fails(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    center = TerminalCenter()
    started = []
    requested = []
    monkeypatch.setattr(
        "romverse.ui.terminal_center.start_background",
        lambda worker: started.append(worker),
    )
    center.runtime_tools_requested.connect(lambda: requested.append(True))

    center.run_command()

    assert requested == [True]
    assert started == []
    assert center._worker is None
    assert "no phone data changed" in center.output.toPlainText().casefold()
    assert center.run_button.text() == "Resolve Platform Tools"
    center.close()
    app.processEvents()
