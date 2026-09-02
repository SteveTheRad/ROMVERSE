from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from romverse.core.settings import AppSettings, ExperienceMode
from romverse.nexus.events import LiveConsoleEventStore, MissionConfidence, MissionState
from romverse.rom.projects import RomProjectStore
from romverse.ui.backup_center import BackupCenter
from romverse.ui.live_console import LiveConsoleCenter
from romverse.ui.main_window import MainWindow
from romverse.ui.theme import STYLESHEET


def test_live_console_renders_real_events_and_filters_active_work(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLESHEET)
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
        project_id="example-project",
    )
    store.progress(running.mission_id, 35)

    center = LiveConsoleCenter(store)
    center.refresh()
    assert center.table.rowCount() == 2
    assert center.table.item(0, 0).background().color().name() == "#060b16"
    assert center.table.item(1, 0).background().color().name() == "#0b1322"
    assert "2 genuine events" in center.status.text()
    assert "Inspect firmware" in center.detail_title.text()
    assert "WHY" in center.detail.text()
    assert center.progress.value() == 35
    assert center.open_source_button.text() == "Open ROM Studio"
    assert center.open_source_button.isEnabled()
    assert "exact project example-project" in center.source_feedback.text()
    routes: list[tuple[str, str]] = []
    center.source_requested.connect(lambda route, project_id: routes.append((route, project_id)))
    center.open_source_button.click()
    assert routes == [("rom_studio", "example-project")]

    center.filter.setCurrentText("Active")
    app.processEvents()
    assert center.table.rowCount() == 1
    assert center.table.item(0, 3).text() == "RUNNING"
    assert center.table.objectName() == "LiveConsoleTable"
    assert center.table.horizontalHeader().objectName() == "LiveConsoleHeader"
    assert center.table.alternatingRowColors()
    assert center.table.showGrid()
    assert center.table.palette().color(QPalette.ColorRole.Base).name() == "#060b16"
    assert center.table.viewport().palette().color(QPalette.ColorRole.Base).name() == "#060b16"
    assert center.table.item(0, 0).background().color().name() == "#060b16"
    assert "background-color: #0D1729" in center.table.horizontalHeader().styleSheet()


def test_live_console_rendered_cells_and_header_stay_dark(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    store = LiveConsoleEventStore(tmp_path)
    for index in range(3):
        store.note(
            source=f"Visual evidence {index}",
            stage="contrast-check",
            title=f"Contrast event {index}",
            summary="Rendered colors must remain readable.",
            explanation="The host theme cannot own this evidence surface.",
            next_action="Keep the table dark.",
            state=MissionState.ATTENTION,
        )

    center = LiveConsoleCenter(store)
    center.resize(1_300, 800)
    center.show()
    app.processEvents()
    try:
        viewport_image = center.table.viewport().grab().toImage()
        alternate_rect = center.table.visualItemRect(center.table.item(1, 2))
        alternate_pixel = viewport_image.pixelColor(
            alternate_rect.right() - 3,
            alternate_rect.center().y(),
        )

        header = center.table.horizontalHeader()
        header_image = header.viewport().grab().toImage()
        header_x = header.sectionViewportPosition(2) + header.sectionSize(2) - 3
        header_pixel = header_image.pixelColor(header_x, header.height() // 2)

        assert alternate_pixel.name() == "#0b1322"
        assert header_pixel.name() == "#0d1729"
        assert alternate_pixel.lightness() < 32
        assert header_pixel.lightness() < 40
    finally:
        center.close()


def test_live_console_disables_source_action_for_unregistered_producer(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    store = LiveConsoleEventStore(tmp_path)
    store.note(
        source="External fixture",
        stage="observation",
        title="External observation",
        summary="A bounded fixture event was recorded.",
        explanation="It has no registered ROMVERSE source surface.",
        next_action="Review the event text only.",
    )

    center = LiveConsoleCenter(store)

    assert not center.open_source_button.isEnabled()
    assert center.open_source_button.text() == "Source page unavailable"
    assert "did not report a registered" in center.source_feedback.text()


def test_live_console_returns_synapse_evidence_to_archives_not_nexus(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    store = LiveConsoleEventStore(tmp_path)
    store.note(
        source="ROMVERSE Synapse",
        stage="verified-resolution-memory",
        title="Typed fix learned locally",
        summary="An integrity-verified local outcome updated private guidance.",
        explanation="The record has no upload or execution authority.",
        next_action="Review its exact scope in Archives.",
        state=MissionState.INFORMATION,
        confidence=MissionConfidence.VERIFIED,
    )

    center = LiveConsoleCenter(store)
    requested: list[tuple[str, str]] = []
    center.source_requested.connect(lambda route, project_id: requested.append((route, project_id)))
    center.refresh()

    assert center.open_source_button.text() == "Open ROMVERSE Synapse"
    assert center.open_source_button.isEnabled()
    center.open_source_button.click()
    assert requested == [("romverse_synapse", "")]


def test_live_console_restores_exact_project_and_nested_producer_without_running_it(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(experience_mode=ExperienceMode.GUIDED),
    )
    try:
        project = window.rom_studio.store.create("Exact Forge source")
        window.nexus_events.note(
            source="Forge Control",
            stage="readiness-review",
            title="Forge evidence needs review",
            summary="The project has a current bounded readiness result.",
            explanation="No build or phone operation was authorized.",
            next_action="Review the exact Forge Control evidence.",
            state=MissionState.ATTENTION,
            project_id=project.project_id,
        )

        window._navigate_route("live_console")
        window.live_console.refresh()
        app.processEvents()

        assert window.live_console.open_source_button.text() == "Open Forge Control"
        assert f"exact project {project.project_id}" in window.live_console.source_feedback.text()
        window.live_console.open_source_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.current_project is not None
        assert window.rom_studio.current_project.project_id == project.project_id
        assert "Forge Control" in window.rom_studio.dashboard_handoff_title.text()
        assert window.rom_studio.app_settings.experience_mode is ExperienceMode.GUIDED
        assert window.rom_studio.worker is None
        assert not QApplication.activeModalWidget()
    finally:
        window.companion_center.transport.close()
        window.close()


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


def test_live_console_opens_exact_current_nexus_project(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        project = window.rom_studio.store.create("Console Nexus project")
        window.rom_studio.refresh(project.project_id)
        window.nexus_events.note(
            source="ROMVERSE Nexus",
            stage="pathfinder-route",
            title="Nexus route ready for review",
            summary="A project-bound route was recorded.",
            explanation="The plan retained zero execution authority.",
            next_action="Open its exact Nexus project.",
            project_id=project.project_id,
        )
        window.live_console.refresh()
        window._navigate_route("live_console")
        app.processEvents()

        assert "exact project" in window.live_console.source_feedback.text()
        window.live_console.open_source_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.nexus_center
        assert window.nexus_center.project_selector.currentData() == project.project_id
        assert window.nexus_center.current_plan is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_live_console_keeps_stale_project_source_failure_in_page(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window.nexus_events.note(
            source="Forge Control",
            stage="readiness-review",
            title="Stale Forge Control review",
            summary="The former project is no longer present.",
            explanation="The event remains an honest historical record.",
            next_action="Do not infer a replacement project.",
            project_id="missing-project-1234",
        )
        window.live_console.refresh()
        window._navigate_route("live_console")
        app.processEvents()
        previous = window.stack.currentWidget()

        assert window.live_console.open_source_button.text() == "Open Forge Control"
        window.live_console.open_source_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is previous
        assert "SOURCE HANDOFF STOPPED" in window.live_console.source_feedback.text()
        assert "project evidence is no longer available" in (
            window.live_console.source_feedback.text()
        )
        assert "NO ACTION STARTED" in window.live_console.source_feedback.text()
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
