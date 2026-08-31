from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from romverse.core.settings import AppSettings, ExperienceMode
from romverse.device.models import AndroidDevice, DeviceState
from romverse.ui.main_window import (
    MainWindow,
    _device_scan_failure_copy,
    _sidebar_device_art_kind,
)


def test_every_desktop_navigation_label_opens_and_highlights_its_own_page(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        labels = [button.text().replace("&&", "&") for button in window.nav_buttons]
        assert labels == [
            "Command Deck",
            "ROM Studio",
            "Quantum Optimizer",
            "Device Atlas",
            "Recovery Bay",
            "Guardian Core",
            "App Launchpad",
            "Time Machine",
            "Health Timeline",
            "ROMVERSE Archives",
            "Command Console",
            "Live Console",
            "ROMVERSE Nexus",
            "Forge Arsenal",
            "ROMVERSE Link",
            "ROMVERSE Members",
            "ROMVERSE Galaxy",
            "About ROMVERSE",
        ]
        routes = [int(button.property("page_index")) for button in window.nav_buttons]
        assert len(routes) == len(set(routes))

        by_label = {button.text().replace("&&", "&"): button for button in window.nav_buttons}
        assert window.experience_badge.text() == "GUIDED  •  ARCANA"
        assert by_label["Command Console"].isHidden()
        assert by_label["ROMVERSE Nexus"].isHidden()
        assert by_label["Forge Arsenal"].isHidden()
        assert not by_label["Live Console"].isHidden()
        assert not by_label["Guardian Core"].isHidden()

        active_route = window.stack.currentIndex()
        window._apply_experience_mode(ExperienceMode.EXPERT)
        assert window.stack.currentIndex() == active_route
        assert window.experience_badge.text() == "EXPERT  •  ARCHITECT"
        assert not by_label["Command Console"].isHidden()
        assert not by_label["ROMVERSE Nexus"].isHidden()
        assert not by_label["Forge Arsenal"].isHidden()

        for button, route in zip(window.nav_buttons, routes, strict=True):
            window._navigate(route)
            app.processEvents()
            active = [item for item in window.nav_buttons if item.property("active")]
            assert window.stack.currentIndex() == route
            assert active == [button]
            assert button.toolTip()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_expert_mode_is_applied_from_persisted_settings_without_changing_guardian(
    tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(experience_mode=ExperienceMode.EXPERT),
    )
    try:
        by_label = {button.text().replace("&&", "&"): button for button in window.nav_buttons}
        assert not by_label["Command Console"].isHidden()
        assert not by_label["ROMVERSE Nexus"].isHidden()
        assert not by_label["Forge Arsenal"].isHidden()
        assert not by_label["Guardian Core"].isHidden()
        assert "Guardian" in window.experience_badge.toolTip()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_genesis_learning_route_opens_archives_with_the_exact_guide(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window.rom_studio.knowledge_requested.emit("firmware source")
        app.processEvents()

        assert window.stack.currentIndex() == window.knowledge_index
        assert window.knowledge_center.search.text() == "firmware source"
        assert "payload.bin" in window.knowledge_center.detail.toPlainText().casefold()
        active = [item for item in window.nav_buttons if item.property("active")]
        assert len(active) == 1
        assert active[0].text().replace("&&", "&") == "ROMVERSE Archives"
    finally:
        window.companion_center.transport.close()
        window.close()


def test_failed_device_refresh_clears_stale_rom_studio_identity(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    finished = []
    window.rom_studio.device_scan_finished.connect(
        lambda succeeded, message: finished.append((succeeded, message))
    )
    window.rom_studio.set_devices(
        [AndroidDevice("stale-serial", DeviceState.DEVICE, model="Stale phone")]
    )

    try:
        window._scan_failed("ADB transport failed during refresh")

        assert window.device_center.devices == []
        assert window.diagnostics_center.devices == []
        assert window.rom_studio.devices == []
        assert finished == [(False, "ADB transport failed during refresh")]
        assert window.connection_state.text() == "⌁  Device scan needs attention"
        assert "automatic retry" in window.sidebar_device_detail.text()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_device_scan_failure_copy_names_the_real_subsystem() -> None:
    assert _device_scan_failure_copy("Guardian audit integrity check failed: record capacity") == (
        "⌁  Guardian evidence needs attention",
        "●  Guardian ledger needs attention",
        "Evidence verification paused the scan • ROMVERSE will retry safely",
    )
    assert (
        "ADB service is restarting"
        in _device_scan_failure_copy("ADB server version mismatch; daemon restarted")[0]
    )
    assert "USB permission" in _device_scan_failure_copy("permission denied opening USB")[0]


def test_sidebar_product_art_never_mislabels_another_android_device(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    samsung = AndroidDevice(
        "private-serial",
        DeviceState.DEVICE,
        manufacturer="Samsung",
        model="SM-S938B",
        marketing_name="Galaxy S25 Ultra",
        codename="pa3q",
    )
    xiaomi = AndroidDevice(
        "private-serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        marketing_name="Xiaomi 17 Pro Max",
        codename="popsicle",
    )
    try:
        assert _sidebar_device_art_kind(samsung) == "generic-android"
        window._set_sidebar_device_art(samsung)
        assert "Generic Android" in window.sidebar_device_image.accessibleName()
        assert "Samsung Galaxy S25 Ultra" in window.sidebar_device_image.toolTip()
        assert "unconfirmed" in window.sidebar_device_image.toolTip()

        assert _sidebar_device_art_kind(xiaomi) == "xiaomi-17-pro-max"
        window._set_sidebar_device_art(xiaomi)
        assert "Verified product image" in window.sidebar_device_image.accessibleName()
        assert "Xiaomi 17 Pro Max" in window.sidebar_device_image.toolTip()
        assert "exact Device DNA artwork" in window.sidebar_device_image.toolTip()
    finally:
        window.companion_center.transport.close()
        window.close()
