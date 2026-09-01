from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from romverse.nexus.events import LiveConsoleEventStore, MissionConfidence, MissionState
from romverse.rom.projects import RomProjectStore
from romverse.ui.backup_center import BackupCenter
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


def test_time_machine_routes_measured_worker_outcomes_to_live_console(
    tmp_path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "baseline.img"
    source.write_bytes(b"verified baseline" * 100)
    workspace = tmp_path / "workspace"
    rom_store = RomProjectStore(workspace)
    project = rom_store.import_original(rom_store.create("Console recovery").project_id, source)
    rom_store.create_working_copy(project.project_id)
    rom_store.create_snapshot(project.project_id)
    events = LiveConsoleEventStore(workspace)
    center = BackupCenter(workspace, live_console_store=events)
    workers = []
    changed: list[bool] = []
    center.live_console_changed.connect(lambda: changed.append(True))
    monkeypatch.setattr("romverse.ui.backup_center.start_background", workers.append)

    center._start_time_machine("verify")

    assert workers
    assert events.list_recent()[0].state is MissionState.RUNNING
    assert events.list_recent()[0].stage == "time-machine-verify"
    workers.pop().run()
    app.processEvents()

    recent = events.list_recent()
    assert recent[0].state is MissionState.SUCCEEDED
    assert recent[0].progress_percent == 100
    assert recent[0].confidence is MissionConfidence.VERIFIED
    assert recent[0].guardian_protected is True
    assert recent[0].project_id == project.project_id
    assert recent[1].state is MissionState.RUNNING
    assert recent[1].progress_percent == 100
    assert changed
    center.close()


def test_time_machine_live_console_failure_never_copies_private_error_text(
    tmp_path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    source = tmp_path / "baseline.img"
    source.write_bytes(b"verified baseline" * 100)
    workspace = tmp_path / "workspace"
    rom_store = RomProjectStore(workspace)
    project = rom_store.import_original(rom_store.create("Private failure").project_id, source)
    rom_store.create_working_copy(project.project_id)
    rom_store.create_snapshot(project.project_id)
    events = LiveConsoleEventStore(workspace)
    center = BackupCenter(workspace, live_console_store=events)
    workers = []
    monkeypatch.setattr("romverse.ui.backup_center.start_background", workers.append)
    center._start_time_machine("restore")

    center._time_machine_failed("/home/steve/Private/phone-bbb7782c.bin failed for serial bbb7782c")

    terminal = events.list_recent()[0]
    public_copy = " ".join(
        (terminal.title, terminal.summary, terminal.explanation, terminal.next_action)
    )
    assert terminal.state is MissionState.FAILED
    assert terminal.confidence is MissionConfidence.VERIFIED
    assert "/home/steve" not in public_copy
    assert "bbb7782c" not in public_copy
    assert "no phone write" in public_copy.casefold()
    assert "/home/steve" in center.local_result.text()
    center.worker = None
    center.close()
