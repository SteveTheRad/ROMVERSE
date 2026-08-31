from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from romverse.nexus.events import LiveConsoleEventStore, MissionConfidence, MissionState
from romverse.ui.live_console import LiveConsoleCenter
from romverse.ui.main_window import MainWindow


def test_live_console_renders_real_events_and_filters_active_work(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    store = LiveConsoleEventStore(tmp_path)
    store.note(
        source="Device DNA",
        stage="capability-map",
        title="Device DNA compiled",
        summary="The evidence profile was created without guessing.",
        explanation="Unknown values remain explicitly unconfirmed.",
        next_action="Review capability warnings.",
        state=MissionState.ATTENTION,
        confidence=MissionConfidence.UNCONFIRMED,
        evidence_refs=("projects/example/device-dna.romverse",),
    )
    running = store.start(
        source="ROM Studio",
        stage="firmware-inspection",
        title="Inspect firmware",
        summary="Bounded inspection started.",
        explanation="ROMVERSE is identifying the package structure.",
        next_action="Wait for inspection evidence.",
    )
    store.progress(running.mission_id, 35)

    center = LiveConsoleCenter(store)
    center.refresh()
    assert center.table.rowCount() == 2
    assert "2 genuine events" in center.status.text()
    assert "Inspect firmware" in center.detail_title.text()
    assert "WHY" in center.detail.text()
    assert center.progress.value() == 35

    center.filter.setCurrentText("Active")
    app.processEvents()
    assert center.table.rowCount() == 1
    assert center.table.item(0, 3).text() == "RUNNING"


def test_live_console_exposes_tamper_failure_instead_of_fabricating_events(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    store = LiveConsoleEventStore(tmp_path)
    store.note(
        source="Nexus",
        stage="startup",
        title="Nexus ready",
        summary="The local event ledger is ready.",
        explanation="Live Console has a trusted local data source.",
        next_action="Start a ROMVERSE operation.",
    )
    store.path.write_text("{}", encoding="utf-8")

    center = LiveConsoleCenter(store)
    center.refresh()
    assert center.table.rowCount() == 0
    assert "needs attention" in center.status.text().casefold()


def test_main_window_routes_real_rom_studio_progress_to_live_console(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window._live_operation_started("inspect")
        window._live_operation_progress("inspect", 55)
        window._live_operation_completed("inspect", object())
        app.processEvents()

        events = window.nexus_events.list_recent()
        assert [item.state for item in events] == [
            MissionState.SUCCEEDED,
            MissionState.RUNNING,
        ]
        assert events[0].progress_percent == 100
        assert events[1].progress_percent == 55
        assert window.live_console.table.rowCount() == 2
    finally:
        window.companion_center.transport.close()
        window.close()
