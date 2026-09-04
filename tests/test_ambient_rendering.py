from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from romverse.ui.main_window import CosmicBackground, MainWindow, WebsiteBrandCrest


class TrackedCosmicBackground(CosmicBackground):
    def __init__(self, logo_path: Path) -> None:
        self.dirty_updates: list[QRect] = []
        super().__init__(logo_path)

    def update(self, *args) -> None:  # type: ignore[no-untyped-def]
        if args and isinstance(args[0], QRect):
            self.dirty_updates.append(QRect(args[0]))
        super().update(*args)


def _logo_path() -> Path:
    return Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"


def test_sidebar_crest_keeps_exact_motion_timing_with_bounded_repaint_cadence() -> None:
    QApplication.instance() or QApplication([])
    crest = WebsiteBrandCrest(_logo_path())
    try:
        assert crest.FLOAT_SECONDS == 6.2
        assert crest.ORBIT_SECONDS == 34.0
        assert crest.SCAN_SECONDS == 5.5
        assert crest._motion_timer.interval() == 50
    finally:
        crest.deleteLater()


def test_shooting_star_is_diagonal_and_repaints_only_its_local_region() -> None:
    app = QApplication.instance() or QApplication([])
    background = TrackedCosmicBackground(_logo_path())
    background.resize(1_200, 800)
    try:
        background._star_timer.stop()
        background._start_shooting_star()

        delta = background._star_end - background._star_start
        assert delta.x() >= background.width() * 0.30
        assert delta.y() >= background.height() * 0.38

        background._star_progress = 0.20
        background.dirty_updates.clear()
        background._advance_star()
        app.processEvents()
        assert background.dirty_updates
        dirty = background.dirty_updates[-1]
        assert 0 < dirty.width() < background.width() * 0.15
        assert 0 < dirty.height() < background.height() * 0.15
        assert dirty.width() * dirty.height() < background.width() * background.height() * 0.02
    finally:
        background.hide()
        background.deleteLater()
        app.processEvents()


def test_cosmic_background_tracks_real_command_deck_activity_states() -> None:
    QApplication.instance() or QApplication([])
    background = CosmicBackground(_logo_path())
    try:
        background.resize(1_200, 800)
        background._render_background()
        assert not background._background.isNull()

        background.set_activity_state("recovery")

        assert background._activity_state == "recovery"
        assert background._background.isNull()
        background.set_activity_state("not-a-real-state")
        assert background._activity_state == "idle"
    finally:
        background.hide()
        background.deleteLater()


def test_main_window_projects_real_operation_progress_into_command_deck_and_nebula(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(None, _logo_path(), tmp_path, app_icon_path=_logo_path())
    try:
        window._live_operation_started("fixture-build")
        window._live_operation_progress("fixture-build", 61)

        assert window.device_center._next_action_key == "Live Operations"
        assert window.device_center.mission_progress.value() == 61
        assert window.cosmic_background._activity_state == "running"

        window._live_operation_completed("fixture-build", object())

        assert window.device_center._next_action_key == "Resolve Platform Tools"
        assert window.cosmic_background._activity_state == "attention"
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_only_the_visible_telemetry_page_animates_during_a_scan(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(None, _logo_path(), tmp_path, app_icon_path=_logo_path())
    try:
        window.scanning = True

        window._navigate(window.stack.indexOf(window.device_center))
        assert not window.device_center.scan_progress.isHidden()
        assert window.device_center.scan_progress.minimum() == 0
        assert window.device_center.scan_progress.maximum() == 0
        assert window.diagnostics_center.scan_progress.isHidden()
        assert window.diagnostics_center.scan_progress.maximum() == 100

        window._navigate(window.stack.indexOf(window.diagnostics_center))
        assert window.device_center.scan_progress.isHidden()
        assert window.device_center.scan_progress.maximum() == 100
        assert not window.diagnostics_center.scan_progress.isHidden()
        assert window.diagnostics_center.scan_progress.minimum() == 0
        assert window.diagnostics_center.scan_progress.maximum() == 0

        window._navigate(window.stack.indexOf(window.rom_studio))
        assert window.device_center.scan_progress.isHidden()
        assert window.diagnostics_center.scan_progress.isHidden()
        assert window.device_center.scan_progress.maximum() == 100
        assert window.diagnostics_center.scan_progress.maximum() == 100
    finally:
        window.scanning = False
        window.close()
        window.deleteLater()
        app.processEvents()
