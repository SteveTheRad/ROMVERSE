from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from romverse.core.settings import AppSettings
from romverse.device.models import AndroidDevice, DeviceState
from romverse.ui.device_center import DeviceCenter
from romverse.ui.main_window import MainWindow


def _devices() -> list[AndroidDevice]:
    return [
        AndroidDevice(
            "PRIVATE-A",
            DeviceState.DEVICE,
            manufacturer="Google",
            model="Pixel A",
            product="akita",
            codename="akita",
            android_version="16",
        ),
        AndroidDevice(
            "PRIVATE-B",
            DeviceState.DEVICE,
            manufacturer="Samsung",
            model="Galaxy B",
            product="b0q",
            codename="b0q",
            android_version="16",
        ),
    ]


def test_device_center_requires_an_explicit_choice_for_multiple_transports(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    center = DeviceCenter(tmp_path)
    selected: list[str] = []
    center.device_selected.connect(selected.append)

    center.set_devices(_devices())

    assert center._selected_index == -1
    assert center.selector.currentIndex() == 0
    assert center.status_badge.text() == "SELECT ONE DEVICE"
    assert center._next_action_key == "Choose Device"
    assert not center.next_button.isEnabled()
    center.selector.setCurrentIndex(2)
    app.processEvents()
    assert center._selected_index == 1
    assert center._next_action_key == "Start ROM Project"
    assert center.next_button.isEnabled()
    assert selected == ["PRIVATE-B"]
    center.close()


def test_main_window_binds_every_action_surface_to_the_same_selected_device(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    first, second = _devices()
    try:
        window._scan_complete([first, second])
        app.processEvents()

        assert window._selected_device_serial == ""
        assert window.rom_studio.devices == []
        assert window.diagnostics_center.devices == []
        assert window.apk_installer.devices == []
        assert window.connection_state.text() == "⌁  Select a device"

        window.device_center.selector.setCurrentIndex(2)
        app.processEvents()

        assert window._selected_device_serial == second.serial
        assert window.rom_studio.devices == [second]
        assert window.diagnostics_center.devices == [second]
        assert window.apk_installer.devices == [second]
        assert "Galaxy B" in window.connection_device.text()

        window._scan_complete([second, first])
        app.processEvents()
        assert window._selected_device_serial == second.serial
        assert window.rom_studio.devices == [second]
        assert window.device_center.selector.currentData() == second.serial
    finally:
        window.companion_center.transport.close()
        window.close()


def test_main_window_empty_scan_settles_on_actionable_waiting_state(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    try:
        window._scan_complete([])
        app.processEvents()

        assert window.connection_state.text() == "⌁  Waiting for device"
        assert window.sidebar_device_state.text() == "●  Waiting for device"
        assert window.device_center._device_engine_error == ""
        assert window.device_center.status_badge.text() == "NOT CONNECTED"
        assert window.device_center.next_button.text() == "Scan for device"
        assert window.device_center.next_button.isEnabled()
    finally:
        window.companion_center.transport.close()
        window.close()
