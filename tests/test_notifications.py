from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QWidget

from romverse.core.settings import AppSettings
from romverse.ui.main_window import MainWindow
from romverse.ui.notifications import DesktopNotificationCenter, NotificationKind


def _logo_path() -> Path:
    return Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"


def test_notification_center_sanitizes_deduplicates_and_respects_disable() -> None:
    app = QApplication.instance() or QApplication([])
    surface = QWidget()
    surface.resize(900, 700)
    surface.show()
    center = DesktopNotificationCenter(surface, QIcon(str(_logo_path())))
    try:
        assert center.notify(
            "rom-studio.inspect.completed",
            "  Stage\ncomplete  ",
            "  Verified\x00 evidence\nwas saved.  ",
            NotificationKind.SUCCESS,
        )
        app.processEvents()
        assert center.delivery_count == 1
        assert center.last_notification is not None
        assert center.last_notification.title == "Stage complete"
        assert center.last_notification.message == "Verified evidence was saved."
        assert center.toast.isVisible()
        assert center.toast.x() + center.toast.width() <= surface.width() - 22
        assert center.toast.y() + center.toast.height() <= surface.height() - 66

        assert not center.notify(
            "rom-studio.inspect.completed",
            "Stage complete",
            "Verified evidence was saved.",
            NotificationKind.SUCCESS,
        )
        assert not center.notify("Invalid Key", "Title", "Message")

        center.set_enabled(False)
        assert not center.notify("rom-studio.next.completed", "Next", "Done")
        assert center.delivery_count == 1
    finally:
        center.shutdown()
        surface.close()
        surface.deleteLater()
        app.processEvents()


def test_main_window_reports_real_rom_studio_terminal_outcomes(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(
        None,
        _logo_path(),
        tmp_path,
        app_icon_path=_logo_path(),
        app_settings=AppSettings(onboarding_complete=True),
    )
    try:
        window._live_operation_started("inspect")
        window._live_operation_completed("inspect", object())
        app.processEvents()
        completed = window.notification_center.last_notification
        assert completed is not None
        assert completed.kind is NotificationKind.SUCCESS
        assert completed.key == "rom-studio.inspect.completed"

        window._live_operation_started("extract")
        window._live_operation_failed("extract", "Archive format was not recognized.")
        app.processEvents()
        failed = window.notification_center.last_notification
        assert failed is not None
        assert failed.kind is NotificationKind.ATTENTION
        assert failed.key == "rom-studio.extract.attention"
        assert "not recognized" in failed.message
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
