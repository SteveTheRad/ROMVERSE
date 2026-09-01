from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from romverse.core.settings import AppSettings, ExperienceMode
from romverse.ui.command_palette import NavigationCommand, match_navigation_commands
from romverse.ui.main_window import MainWindow


def test_navigation_search_uses_canonical_and_legacy_vocabulary_with_stable_ranking() -> None:
    commands = (
        NavigationCommand("command_deck", "Command Deck", "Device overview", ("Dashboard",)),
        NavigationCommand(
            "device_nexus",
            "Device Portal",
            "Connected Android device",
            ("Device Center", "Device Nexus"),
        ),
        NavigationCommand(
            "app_launchpad",
            "App Launchpad",
            "Install Android applications",
            ("APK Installer",),
        ),
    )

    assert match_navigation_commands(commands, "") == commands
    assert [item.route for item in match_navigation_commands(commands, "device")] == [
        "device_nexus",
        "command_deck",
    ]
    assert [item.route for item in match_navigation_commands(commands, "APK installer")] == [
        "app_launchpad"
    ]
    assert match_navigation_commands(commands, "missing destination") == ()


def test_guided_command_palette_routes_only_to_visible_canonical_pages(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window.command_palette_shortcut.activated.emit()
        app.processEvents()

        dialog = window._command_palette
        assert dialog is not None
        assert dialog.isVisible()
        assert dialog.search.maxLength() == 120
        assert "no device or build operation will run" in dialog.boundary.text()
        assert dialog.search.accessibleName() == "Search ROMVERSE pages"
        assert len(window._navigation_commands()) == len(window.nav_buttons) - 3
        assert dialog.results.currentRow() == 0
        QTest.keyClick(dialog.search, Qt.Key.Key_Down)
        assert dialog.results.currentRow() == 1

        dialog.search.setText("Terminal")
        app.processEvents()
        assert dialog.result_count.text() == "0 destinations"
        assert dialog.results.item(0).data(Qt.ItemDataRole.UserRole) is None

        dialog.search.setText("Mission Console")
        app.processEvents()
        assert dialog.result_count.text() == "1 destination"
        assert dialog.results.item(0).data(Qt.ItemDataRole.UserRole) == "live_console"
        dialog.search.returnPressed.emit()
        app.processEvents()

        assert window.stack.currentWidget() is window.live_console
        assert window._command_palette is None
        assert not window.scanning
    finally:
        window.companion_center.transport.close()
        window.close()


def test_expert_command_palette_reveals_specialist_routes_without_changing_authority(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(experience_mode=ExperienceMode.EXPERT),
    )
    try:
        commands = window._navigation_commands()
        assert len(commands) == len(window.nav_buttons)
        assert {command.route for command in commands} >= {
            "command_console",
            "nexus",
            "forge_arsenal",
            "guardian_core",
        }

        window._open_command_palette()
        app.processEvents()
        dialog = window._command_palette
        assert dialog is not None
        dialog.search.setText("Terminal")
        app.processEvents()
        assert dialog.results.item(0).data(Qt.ItemDataRole.UserRole) == "command_console"
        dialog.search.returnPressed.emit()
        app.processEvents()

        assert window.stack.currentWidget() is window.terminal_center
        assert window.guardian_center.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()
