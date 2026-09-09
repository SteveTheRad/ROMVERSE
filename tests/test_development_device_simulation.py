from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from romverse.app import development_simulated_device
from romverse.device_packs.registry import DevicePackRegistry
from romverse.ui.main_window import MainWindow


class RejectingDeviceEngine:
    """A transport spy that fails if the development simulation invokes hardware."""

    def __init__(self) -> None:
        self.calls = 0

    def scan_reconnect_safe(self):
        self.calls += 1
        raise AssertionError("development simulation invoked the physical device engine")


def test_development_simulation_scan_is_visible_and_rom_studio_only(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    engine = RejectingDeviceEngine()
    simulated = development_simulated_device()
    window = MainWindow(
        engine,
        logo,
        tmp_path,
        app_icon_path=logo,
        pack_registry=DevicePackRegistry(()),
        development_simulated_device=simulated,
    )
    messages: list[tuple[bool, str]] = []
    window.rom_studio.device_scan_finished.connect(
        lambda succeeded, message: messages.append((succeeded, message))
    )
    try:
        assert not window.timer.isActive()
        assert "Development simulation" in window.connection_state.text()
        assert "SIMULATION ONLY" in window.connection_android.text()
        assert window.device_center.device_name.text() == "No Android device detected"
        assert window.device_center.status_badge.text() == "NOT CONNECTED"
        assert window.device_center.refresh.text() == "Scan now"

        window.scan()
        app.processEvents()

        assert engine.calls == 0
        assert window.device_center.device_name.text() == "No Android device detected"
        assert window.device_center.status_badge.text() == "NOT CONNECTED"
        assert window.device_center.refresh.text() == "Scan now"
        assert window._observed_devices == []
        assert window.rom_studio.devices == [simulated]
        assert window.rom_studio.observed_devices == []
        assert window.apk_installer.devices == []
        assert window.terminal_center._device_serial == ""
        assert messages == [
            (
                True,
                "Deterministic ROM Studio simulation completed; no hardware was scanned.",
            )
        ]
    finally:
        window.close()
