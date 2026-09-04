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
from romverse.ui.vocabulary import (
    EXPERT_ONLY_NESTED_FEATURES,
    NESTED_FEATURE_OWNERS,
    feature,
)


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


def test_guided_command_palette_routes_to_visible_pages_and_nested_features(
    tmp_path: Path,
) -> None:
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
        assert dialog.search.accessibleName() == "Search ROMVERSE features"
        commands = window._navigation_commands()
        guided_nested = set(NESTED_FEATURE_OWNERS) - EXPERT_ONLY_NESTED_FEATURES
        assert len(commands) == len(window.nav_buttons) - 3 + len(guided_nested)
        routes = {command.route for command in commands}
        assert {
            "device_nexus",
            "device_engine",
            "system_scan",
            "health_review",
            "genesis_sequence",
            "ascension_protocol",
            "recipe_forge",
            "device_dna",
            "compatibility_matrix",
            "prebuild_simulation",
            "recovery_autopilot",
            "romverse_intelligence",
            "romverse_synapse",
        } <= routes
        assert not routes & EXPERT_ONLY_NESTED_FEATURES
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
        if window._command_palette is not None:
            window._command_palette.reject()
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
        assert len(commands) == len(window.nav_buttons) + len(NESTED_FEATURE_OWNERS)
        assert {command.route for command in commands} >= {
            "command_console",
            "nexus",
            "forge_arsenal",
            "guardian_core",
            *NESTED_FEATURE_OWNERS,
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
        if window._command_palette is not None:
            window._command_palette.reject()
        window.companion_center.transport.close()
        window.close()


def test_command_palette_opens_exact_nested_feature_without_starting_work(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window._open_command_palette()
        app.processEvents()
        dialog = window._command_palette
        assert dialog is not None

        dialog.search.setText("Automatic Guided Setup")
        app.processEvents()
        assert dialog.result_count.text() == "1 destination"
        assert dialog.results.item(0).data(Qt.ItemDataRole.UserRole) == "genesis_sequence"
        dialog.search.returnPressed.emit()
        app.processEvents()

        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.dashboard_handoff.isVisibleTo(window.rom_studio)
        assert window.rom_studio.dashboard_handoff_title.text() == (
            "Find Anything → Genesis Sequence"
        )
        assert window.rom_studio.worker is None
        assert window.guardian_center.worker is None
        assert not window.scanning
        assert not QApplication.activeModalWidget()
    finally:
        if window._command_palette is not None:
            window._command_palette.reject()
        window.companion_center.transport.close()
        window.close()


def test_every_nested_feature_has_an_exact_owner_destination_without_side_effects(
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
    owner_widgets = {
        "command_deck": window.device_center,
        "quantum_optimizer": window.diagnostics_center,
        "rom_studio": window.rom_studio,
        "recovery_bay": window.repair_center,
        "archives": window.knowledge_center,
        "nexus": window.nexus_center,
    }
    try:
        for route, owner_route in NESTED_FEATURE_OWNERS.items():
            assert window._navigate_feature_route(route)
            app.processEvents()
            assert window.stack.currentWidget() is owner_widgets[owner_route]
            if route in {"device_nexus", "device_engine"}:
                assert window.device_center.feature_handoff.isVisibleTo(window.device_center)
                assert feature(route).title in window.device_center.feature_handoff_title.text()
            elif owner_route == "quantum_optimizer":
                assert window.diagnostics_center.dashboard_handoff.isVisibleTo(
                    window.diagnostics_center
                )
                assert window.diagnostics_center.dashboard_handoff_title.text().startswith(
                    feature(route).title
                )
            elif owner_route == "rom_studio":
                assert window.rom_studio.dashboard_handoff.isVisibleTo(window.rom_studio)
                assert feature(route).title in window.rom_studio.dashboard_handoff_title.text()
            elif owner_route == "recovery_bay":
                assert window.repair_center.feature_handoff.isVisibleTo(window.repair_center)
                assert feature(route).title in window.repair_center.feature_handoff_title.text()
            elif owner_route == "archives":
                assert route == "romverse_synapse"
                assert "ROMVERSE SYNAPSE" in window.knowledge_center.learning_eyebrow.text()
            else:
                assert owner_route == "nexus"
                assert window.nexus_center.evidence_handoff.isVisibleTo(window.nexus_center)
                assert feature(route).title in window.nexus_center.evidence_handoff_title.text()

        assert window.rom_studio.worker is None
        assert window.guardian_center.worker is None
        assert window.repair_center.host_repair_worker is None
        assert window.repair_center.online_worker is None
        assert not window.scanning
        assert not QApplication.activeModalWidget()
    finally:
        if window._command_palette is not None:
            window._command_palette.reject()
        window.companion_center.transport.close()
        window.close()


def test_every_command_deck_launch_card_is_discoverable_by_its_visible_name(
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
    expected = {
        "Build ROM": "genesis_sequence",
        "Pre-Build Simulation": "prebuild_simulation",
        "Device DNA": "device_dna",
        "Recipes": "recipe_forge",
        "Health Review": "health_review",
        "Repair Phone": "recovery_bay",
        "Guardian": "guardian_core",
        "Rescue & Backup": "time_machine",
        "Timeline": "health_timeline",
        "Live Operations": "live_console",
        "Wireless Transfer": "companion_link",
        "ROMVERSE Lab": "nexus",
    }
    try:
        commands = window._navigation_commands()
        assert set(window.device_center.quick_action_buttons) == set(expected)
        for visible_name, route in expected.items():
            matches = match_navigation_commands(commands, visible_name)
            assert matches
            assert matches[0].route == route
    finally:
        window.companion_center.transport.close()
        window.close()


def test_rom_studio_architect_control_changes_and_persists_the_real_desktop_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    saved: list[AppSettings] = []
    monkeypatch.setattr(
        "romverse.ui.rom_studio.confirm_expert_mode",
        lambda _parent=None: True,
    )
    window.settings_changed.connect(saved.append)
    by_route = {button.property("route_key"): button for button in window.nav_buttons}
    try:
        assert window._navigate_route("rom_studio")
        assert not window.rom_studio.expert_button.isChecked()
        window.rom_studio.expert_button.click()
        app.processEvents()

        assert window.app_settings.experience_mode is ExperienceMode.EXPERT
        assert saved[-1].experience_mode is ExperienceMode.EXPERT
        assert window.rom_studio.expert_button.isChecked()
        assert window.rom_studio.expert_button.text() == "Return to Guided Mode"
        assert window.rom_studio.command_tabs.currentIndex() == 1
        assert window.rom_studio.dashboard_handoff_title.text().startswith("Architect Mode")
        assert all(
            not by_route[route].isHidden()
            for route in ("command_console", "nexus", "forge_arsenal")
        )

        window.rom_studio.expert_button.click()
        app.processEvents()

        assert window.app_settings.experience_mode is ExperienceMode.GUIDED
        assert saved[-1].experience_mode is ExperienceMode.GUIDED
        assert not window.rom_studio.expert_button.isChecked()
        assert window.rom_studio.expert_button.text() == "Enter Architect Mode"
        assert window.rom_studio.command_tabs.currentIndex() == 0
        assert window.rom_studio.dashboard_handoff_title.text().startswith("Guided Mode")
        assert all(
            by_route[route].isHidden() for route in ("command_console", "nexus", "forge_arsenal")
        )
        assert window.rom_studio.worker is None
        assert window.guardian_center.worker is None
        assert not QApplication.activeModalWidget()
    finally:
        if window._command_palette is not None:
            window._command_palette.reject()
        window.companion_center.transport.close()
        window.close()


def test_rom_studio_declined_expert_warning_keeps_guided_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    saved: list[AppSettings] = []
    window.settings_changed.connect(saved.append)
    monkeypatch.setattr(
        "romverse.ui.rom_studio.confirm_expert_mode",
        lambda _parent=None: False,
    )
    try:
        assert window._navigate_route("rom_studio")
        window.rom_studio.expert_button.click()
        app.processEvents()

        assert window.app_settings.experience_mode is ExperienceMode.GUIDED
        assert not saved
        assert not window.rom_studio.expert_button.isChecked()
        assert window.rom_studio.expert_button.text() == "Enter Architect Mode"
        assert window.rom_studio.command_tabs.currentIndex() == 0
    finally:
        window.companion_center.transport.close()
        window.close()
