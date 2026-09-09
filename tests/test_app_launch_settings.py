import inspect
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton

from romverse import DISPLAY_VERSION
from romverse import app as app_module
from romverse.app import (
    build_parser,
    configure_file_dialog_safety,
    launch_settings,
    persist_scan_interval,
)
from romverse.core.settings import AppSettings, ExperienceMode, SettingsStore
from romverse.infrastructure.tools import ToolStatus
from romverse.ui.main_window import MainWindow
from romverse.ui.setup_wizard import SetupWizard


class ConfigHost:
    name = "Test"

    def __init__(self, root):
        self.root = root

    def config_dir(self):
        return self.root / "config"


def test_first_run_tool_inventory_remains_readable_at_supported_dialog_size(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    tools = tuple(
        ToolStatus(
            f"Tool {index:02d}",
            index < 18,
            detail="A deliberately detailed bounded host status that must remain readable",
        )
        for index in range(21)
    )
    wizard = SetupWizard(logo, tmp_path / "workspace", tools)
    wizard.resize(760, 680)
    wizard.show()
    app.processEvents()
    try:
        guided = next(
            button
            for button in wizard.findChildren(QPushButton)
            if button.text() == "Continue in Guided Mode"
        )
        assert wizard.size().width() >= 760
        assert wizard.size().height() >= 680
        assert wizard.tool_summary.text() == "18 / 21 READY"
        assert len(wizard.tool_status_rows) == 21
        assert all(row.height() > 0 for row in wizard.tool_status_rows)
        assert wizard.tool_scroll.widget().height() > wizard.tool_scroll.viewport().height()
        assert wizard.tool_scroll.widget().width() <= wizard.tool_scroll.viewport().width()
        assert guided.isVisibleTo(wizard)
    finally:
        wizard.close()


def test_first_run_explicitly_enters_guided_and_reaches_truthful_host_prerequisite(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    workspace = tmp_path / "fresh-workspace"
    missing = (
        ToolStatus("ADB", False, detail="Not available on the bounded host path"),
        ToolStatus("Fastboot", False, detail="Not available on the bounded host path"),
    )
    wizard = SetupWizard(logo, workspace, missing)
    wizard.show()
    app.processEvents()

    onboarding_text = " ".join(label.text() for label in wizard.findChildren(QLabel))
    guided = next(
        button
        for button in wizard.findChildren(QPushButton)
        if button.text() == "Continue in Guided Mode"
    )
    assert DISPLAY_VERSION in onboarding_text
    assert "INTERNAL DEVELOPMENT" in onboarding_text
    assert "No phone is required" in onboarding_text
    assert guided.accessibleName() == "Choose Guided Mode and open Command Deck"

    guided.click()
    app.processEvents()

    assert wizard.result() == QDialog.DialogCode.Accepted
    assert wizard.selected_experience_mode is ExperienceMode.GUIDED
    assert "experience_mode=wizard.selected_experience_mode" in inspect.getsource(app_module.main)

    calls: list[tuple[str, object]] = []

    class Status:
        def setText(self, message: str) -> None:
            calls.append(("purpose", message))

    class SetupDialog:
        last_message = "Android Platform Tools remain a clear host prerequisite."
        status = Status()

        def __init__(self, _host, _statuses, _workspace, _parent, **options):
            calls.append(("options", options))

        def setWindowTitle(self, title: str) -> None:
            calls.append(("title", title))

        def exec(self) -> None:
            calls.append(("opened", True))

    class MissingVerifier:
        def __init__(self, *_args):
            pass

        def verify_extended(self):
            return missing

    monkeypatch.setattr("romverse.ui.toolchain_center.ToolchainSetupDialog", SetupDialog)
    monkeypatch.setattr(
        "romverse.ui.toolchain_center.activate_verified_managed_tools", lambda _workspace: ()
    )
    monkeypatch.setattr("romverse.ui.rom_studio.ToolVerifier", MissingVerifier)

    selected = AppSettings(
        onboarding_complete=True,
        workspace_path=str(workspace),
        experience_mode=wizard.selected_experience_mode,
        online_intelligence_enabled=False,
        auto_download_verified_tools=False,
    )
    window = MainWindow(
        None,
        logo,
        workspace,
        tool_statuses=missing,
        app_icon_path=logo,
        app_settings=selected,
    )
    try:
        window.show()
        app.processEvents()
        assert window.stack.currentWidget() is window.device_center
        assert window.workspace_route_title.text() == "Command Deck"
        assert window.experience_badge.text() == "GUIDED  •  ARCANA"
        assert window.engine is None
        assert not window.scanning
        assert not window._observed_devices
        assert "Platform Tools" in window.device_center.device_note.text()

        resolve = next(
            button
            for button in window.device_center.findChildren(QPushButton)
            if button.text() == "Resolve Platform Tools"
        )
        resolve.click()
        app.processEvents()

        assert ("opened", True) in calls
        options = next(value for kind, value in calls if kind == "options")
        assert options["required_names"] == ("ADB",)
        assert options["auto_start"] is False
        assert options["auto_close"] is False
        assert window.stack.currentWidget() is window.device_center
        assert "host prerequisite" in window.rom_studio.operation_status.text()

        command_deck = next(
            button
            for button in window.nav_buttons
            if button.property("route_key") == "command_deck"
        )
        command_deck.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.device_center
        assert window.engine is None
        assert not window.scanning
    finally:
        window.companion_center.transport.close()
        window.close()


def test_desktop_launch_opens_without_a_custom_splash_sequence() -> None:
    source = inspect.getsource(app_module.main)

    assert "BrandSplash" not in source
    assert "splash_path" not in source


def test_linux_without_bwrap_uses_the_safe_qt_file_dialog_backend(monkeypatch) -> None:
    previous = QApplication.testAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, False)
    monkeypatch.setattr(app_module.sys, "platform", "linux")
    monkeypatch.setattr(app_module.shutil, "which", lambda _name: None)
    try:
        assert configure_file_dialog_safety()
        assert QApplication.testAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
    finally:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, previous)


def test_non_linux_file_dialog_backend_is_unchanged_without_bwrap(monkeypatch) -> None:
    previous = QApplication.testAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, False)
    monkeypatch.setattr(app_module.sys, "platform", "win32")
    monkeypatch.setattr(app_module.shutil, "which", lambda _name: None)
    try:
        assert not configure_file_dialog_safety()
        assert not QApplication.testAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
    finally:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, previous)


def test_cli_workspace_override_is_ephemeral_and_never_persisted(tmp_path) -> None:
    current = AppSettings(
        onboarding_complete=True,
        workspace_path="/persistent/romverse/workspace",
        scan_interval_seconds=12,
    )
    args = build_parser().parse_args(["--workspace", str(tmp_path / "release-smoke")])

    assert args.workspace == tmp_path / "release-smoke"
    assert (
        launch_settings(
            current,
            args.workspace,
            ephemeral_workspace=True,
        )
        is None
    )


def test_normal_launch_persists_the_verified_workspace_and_preferences(tmp_path) -> None:
    current = AppSettings(scan_interval_seconds=14, mask_device_serials=False)
    workspace = (tmp_path / "workspace").resolve()

    updated = launch_settings(current, workspace, ephemeral_workspace=False)

    assert updated is not None
    assert updated.onboarding_complete
    assert updated.workspace_path == str(workspace)
    assert updated.scan_interval_seconds == 14
    assert updated.mask_device_serials


def test_scan_interval_change_is_persisted_without_overwriting_other_preferences(tmp_path) -> None:
    store = SettingsStore(ConfigHost(tmp_path))
    current = AppSettings(
        onboarding_complete=True,
        workspace_path="/persistent/workspace",
        scan_interval_seconds=8,
        mask_device_serials=True,
    )

    updated = persist_scan_interval(store, current, 45)

    assert updated.scan_interval_seconds == 45
    assert store.load() == updated
    assert store.load().workspace_path == "/persistent/workspace"
