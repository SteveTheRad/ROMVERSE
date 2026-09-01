from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from romverse.core.settings import AppSettings, ExperienceMode
from romverse.device.models import AndroidDevice, DeviceState, StorageInfo
from romverse.infrastructure.tools import ToolStatus
from romverse.nexus.planning import NexusObjective, NexusPlanner
from romverse.repair.templates import RepairConcern
from romverse.ui.main_window import (
    MainWindow,
    _device_scan_failure_copy,
    _device_scan_failure_is_transient,
    _sidebar_device_art_kind,
    _sidebar_nav_tooltip,
)
from tests.test_device_dna import _device, _project


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
            "Activity Center",
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
        assert [heading.text() for heading in window.nav_section_labels] == [
            "HOME",
            "ROM WORKSHOP",
            "DEVICE",
            "GUARDIAN & RECOVERY",
            "ACTIVITY & KNOWLEDGE",
            "LIVE OPERATIONS",
            "CONNECTED ROMVERSE",
            "SYSTEM",
        ]
        routes = [int(button.property("page_index")) for button in window.nav_buttons]
        assert len(routes) == len(set(routes))
        assert window.page_routes == {
            "command_deck": window.stack.indexOf(window.device_center),
            "quantum_optimizer": window.stack.indexOf(window.diagnostics_center),
            "health_timeline": window.stack.indexOf(window.history_center),
            "activity_center": window.stack.indexOf(window.activity_center),
            "guardian_core": window.stack.indexOf(window.guardian_center),
            "recovery_bay": window.stack.indexOf(window.repair_center),
            "device_atlas": window.stack.indexOf(window.device_packs_center),
            "rom_studio": window.stack.indexOf(window.rom_studio),
            "app_launchpad": window.stack.indexOf(window.apk_installer),
            "time_machine": window.stack.indexOf(window.backup_center),
            "archives": window.stack.indexOf(window.knowledge_center),
            "command_console": window.stack.indexOf(window.terminal_center),
            "live_console": window.stack.indexOf(window.live_console),
            "nexus": window.stack.indexOf(window.nexus_center),
            "forge_arsenal": window.stack.indexOf(window.toolchain_center),
            "companion_link": window.stack.indexOf(window.companion_center),
            "members": window.stack.indexOf(window.members_center),
            "galaxy": routes[-2],
            "about": window.stack.indexOf(window.about_page),
        }

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
        active_route = window.stack.currentIndex()
        assert not window._navigate_route("missing internal route")
        assert window.stack.currentIndex() == active_route
        assert window.notification_center.last_notification is not None
        assert window.notification_center.last_notification.key.startswith("navigation.missing.")

        window._navigate_route("about")
        window.about_page.family_buttons["guardian_core"].click()
        app.processEvents()
        assert window.stack.currentWidget() is window.guardian_center
        assert by_label["Guardian Core"].property("active") is True
        assert window.guardian_center.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_command_deck_cards_are_context_aware_and_route_to_canonical_pages(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        actions = window.device_center.quick_action_buttons
        assert set(actions) == {
            "Build ROM",
            "Device DNA",
            "Pre-Build Simulation",
            "Recipes",
            "Health Review",
            "Repair Phone",
            "Guardian",
            "Rescue & Backup",
            "Timeline",
            "Live Operations",
            "Wireless Transfer",
            "ROMVERSE Lab",
        }
        assert "CREATE PROJECT" in actions["Build ROM"].text()
        assert "NEEDS FIRMWARE" in actions["Pre-Build Simulation"].text()
        assert not actions["ROMVERSE Lab"].isHidden()

        window.device_center.set_workspace_context("Project Orion", True)
        actions = window.device_center.quick_action_buttons
        assert "CONTINUE PROJECT" in actions["Build ROM"].text()
        assert "READY" in actions["Pre-Build Simulation"].text()
        assert any(
            "Project Orion" in label.text()
            for label in window.device_center.body_content.findChildren(
                type(window.device_center.next_title)
            )
        )

        genesis_opened = []
        monkeypatch.setattr(
            window.rom_studio,
            "_open_guided_setup",
            lambda: genesis_opened.append(True),
        )
        window.device_center.flight_plan_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert genesis_opened == [True]

        window._navigate(0)
        window._handle_dashboard_action("Optimize")
        app.processEvents()
        assert window.stack.currentWidget() is window.diagnostics_center

        window._navigate(0)
        actions["Guardian"].click()
        app.processEvents()
        assert window.stack.currentIndex() == 3
        window._navigate(0)
        window.device_center.quick_action_buttons["Wireless Transfer"].click()
        app.processEvents()
        assert window.stack.currentIndex() == window.companion_index

        window._navigate(0)
        window._handle_dashboard_action("View Activity Center")
        app.processEvents()
        assert window.stack.currentWidget() is window.activity_center

        window._navigate(0)
        lab = window.device_center.quick_action_buttons["ROMVERSE Lab"]
        lab.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.nexus_center
    finally:
        window.companion_center.transport.close()
        window.close()


def test_ready_nexus_plan_opens_exact_zero_authority_guardian_context(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, _report = _project(tmp_path)
    window = MainWindow(None, logo, store.workspace, app_icon_path=logo, pack_registry=registry)
    try:
        window.rom_studio.set_devices([_device()])
        app.processEvents()
        profile = window.rom_studio.device_dna.profiles.load(project.project_id)
        matrix = window.rom_studio.compatibility.matrices.load(project.project_id)
        assert profile is not None
        assert matrix is not None
        plan = NexusPlanner(store).plan(profile, matrix, NexusObjective.BUILD_ROM)
        assert plan.ready_for_guardian_review
        window.nexus_center.refresh()
        assert window.nexus_center.current_plan == plan
        window._navigate_route("nexus")
        window.nexus_center.guardian_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.guardian_center
        assert not window.guardian_center.nexus_review.isHidden()
        assert plan.plan_digest[:16] in window.guardian_center.nexus_review_detail.text()
        assert "Device DNA" in window.guardian_center.nexus_review_title.text()
        assert window.guardian_center.nexus_review_badge.text() == "ZERO AUTHORITY"
        assert window.guardian_center.worker is None

        window.guardian_center.nexus_return_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.nexus_center
        assert window.nexus_center.current_plan == plan
    finally:
        window.companion_center.transport.close()
        window.close()


def test_nexus_guardian_route_rejects_mismatched_plan_identity_in_page(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, _report = _project(tmp_path)
    window = MainWindow(None, logo, store.workspace, app_icon_path=logo, pack_registry=registry)
    try:
        profile = window.rom_studio.device_dna.profiles.load(project.project_id)
        matrix = window.rom_studio.compatibility.matrices.load(project.project_id)
        assert profile is not None
        assert matrix is not None
        plan = NexusPlanner(store).plan(profile, matrix, NexusObjective.BUILD_ROM)
        window.nexus_center.refresh()
        window._navigate_route("nexus")
        window.nexus_center.guardian_requested.emit(plan.project_id, "0" * 64)
        app.processEvents()

        assert window.stack.currentWidget() is window.nexus_center
        assert window.guardian_center.nexus_review.isHidden()
        assert "GUARDIAN HANDOFF STOPPED" in window.nexus_center.status.text()
        assert "no approval or execution" in window.nexus_center.status.text().casefold()
        assert window.guardian_center.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_guardian_expires_retained_nexus_context_when_plan_changes(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, _report = _project(tmp_path)
    window = MainWindow(None, logo, store.workspace, app_icon_path=logo, pack_registry=registry)
    try:
        window.rom_studio.set_devices([_device()])
        app.processEvents()
        profile = window.rom_studio.device_dna.profiles.load(project.project_id)
        matrix = window.rom_studio.compatibility.matrices.load(project.project_id)
        assert profile is not None
        assert matrix is not None
        plan = NexusPlanner(store).plan(profile, matrix, NexusObjective.BUILD_ROM)
        window.nexus_center.refresh()
        window.nexus_center.guardian_button.click()
        app.processEvents()
        assert window.guardian_center.nexus_review_identity == (
            plan.project_id,
            plan.plan_digest,
        )

        NexusPlanner(store).plan(profile, matrix, NexusObjective.ROOT_ROM)
        window._navigate_route("nexus")
        window._navigate_route("guardian_core")
        app.processEvents()

        assert window.guardian_center.nexus_review_identity is None
        assert window.guardian_center.nexus_review_badge.text() == "CONTEXT REFUSED"
        assert "no longer matches" in window.guardian_center.nexus_review_detail.text()
        assert "No action started" in window.guardian_center.nexus_review_detail.text()
        assert window.guardian_center.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_command_deck_repair_uses_exact_current_diagnostic_plan(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    snapshot = AndroidDevice(
        "private-command-device",
        DeviceState.DEVICE,
        manufacturer="RadForge",
        model="Reference Phone",
        battery_percent=75,
        storage=StorageInfo(percent_used=98),
        security_patch="2026-07-01",
        bootloader_locked=True,
        verified_boot="green",
        root_detected=False,
    )
    try:
        window.device_center.set_devices([snapshot])
        window.repair_center.set_devices([snapshot])
        window.diagnostics_center.set_devices([snapshot])
        app.processEvents()
        repair = window.device_center.quick_action_buttons["Repair Phone"]
        assert "STORAGE PLAN READY" in repair.text()
        assert repair.property("diagnosticFinding") == "storage.capacity"
        assert repair.property("evidenceReady") is True

        repair.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.repair_center
        assert window.repair_center.current_concern is RepairConcern.STORAGE
        assert "STORAGE.CAPACITY" in window.repair_center.diagnostic_context.text()
        assert not window.repair_center.diagnostic_source_button.isHidden()
        assert window.repair_center.active_session is None
        assert window.repair_center.host_repair_worker is None
        assert window.repair_center.online_worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_command_deck_repair_uses_honest_general_intake_without_warning(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    snapshot = AndroidDevice(
        "private-healthy-device",
        DeviceState.DEVICE,
        battery_percent=75,
        storage=StorageInfo(percent_used=45),
        security_patch="2026-07-01",
        bootloader_locked=True,
        verified_boot="green",
        root_detected=False,
    )
    try:
        window.device_center.set_devices([snapshot])
        window.repair_center.set_devices([snapshot])
        window.diagnostics_center.set_devices([snapshot])
        app.processEvents()
        repair = window.device_center.quick_action_buttons["Repair Phone"]
        assert "DEVICE READY" in repair.text()

        repair.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.repair_center
        assert "NO CURRENT ACTIONABLE DIAGNOSTIC" in (
            window.repair_center.diagnostic_context.text()
        )
        assert window.repair_center.diagnostic_source_button.isHidden()
        assert window.repair_center.active_session is None
        assert window.repair_center.host_repair_worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_command_deck_repair_refuses_mismatched_recovery_evidence(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    warning = AndroidDevice(
        "private-command-device",
        DeviceState.DEVICE,
        battery_percent=75,
        storage=StorageInfo(percent_used=98),
        security_patch="2026-07-01",
        bootloader_locked=True,
        verified_boot="green",
        root_detected=False,
    )
    healthy = AndroidDevice(
        "private-command-device",
        DeviceState.DEVICE,
        battery_percent=75,
        storage=StorageInfo(percent_used=45),
        security_patch="2026-07-01",
        bootloader_locked=True,
        verified_boot="green",
        root_detected=False,
    )
    try:
        window.device_center.set_devices([warning])
        window.repair_center.set_devices([healthy])
        window.diagnostics_center.set_devices([warning])
        app.processEvents()

        window.device_center.quick_action_buttons["Repair Phone"].click()
        app.processEvents()

        assert window.stack.currentWidget() is window.repair_center
        assert "EXACT DIAGNOSTIC NEEDS FRESH EVIDENCE" in (
            window.repair_center.diagnostic_context.text()
        )
        assert window.repair_center.diagnostic_source_button.isHidden()
        assert window.repair_center.active_session is None
        assert window.repair_center.host_repair_worker is None
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


def test_typed_advisor_handoff_opens_the_exact_archives_identity(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window.diagnostics_center.knowledge_article_requested.emit("device-battery-low")
        app.processEvents()

        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.list.count() == 1
        assert window.knowledge_center.search.text() == (
            "Device battery is below the safe maintenance threshold"
        )
        assert "CHARGING IS USER CONTROLLED" in window.knowledge_center.detail.toPlainText()
        active = [item for item in window.nav_buttons if item.property("active")]
        assert len(active) == 1
        assert active[0].text().replace("&&", "&") == "ROMVERSE Archives"
    finally:
        window.companion_center.transport.close()
        window.close()


def test_optimizer_exact_finding_opens_matching_recovery_plan(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    snapshot = AndroidDevice(
        "private-storage-device",
        DeviceState.DEVICE,
        manufacturer="RadForge",
        model="Reference Phone",
        battery_percent=75,
        battery_temperature_c=31.0,
        storage=StorageInfo(percent_used=98),
        security_patch="2026-07-01",
        bootloader_locked=True,
        verified_boot="green",
        root_detected=False,
        connection_note="Connected",
    )
    try:
        window.diagnostics_center.set_devices([snapshot])
        window.repair_center.set_devices([snapshot])
        window._navigate_route("quantum_optimizer")
        app.processEvents()
        button = next(
            item
            for item in window.diagnostics_center.findChildren(QPushButton)
            if item.text() == "Open guided fix in Recovery Bay"
        )

        button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.repair_center
        assert window.repair_center.current_concern is RepairConcern.STORAGE
        assert "STORAGE.CAPACITY" in window.repair_center.diagnostic_context.text()
        assert "NO ACTION STARTED" in window.repair_center.diagnostic_context.text()
        assert window.repair_center.active_session is None
        assert window.repair_center.host_repair_worker is None
        assert window.repair_center.online_worker is None

        window.repair_center.diagnostic_source_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.diagnostics_center
        source_card = window.diagnostics_center.finding_cards["storage.capacity"]
        assert source_card.property("diagnosticFocus") is True
        assert not source_card.source_context.isHidden()
        assert "Recovery Bay source" in window.diagnostics_center.saved_label.text()
        assert window.repair_center.active_session is None
        assert window.repair_center.host_repair_worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_optimizer_recovery_handoff_fails_closed_on_stale_evidence(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window._navigate_route("quantum_optimizer")
        previous_page = window.stack.currentWidget()

        window.diagnostics_center.repair_requested.emit("storage.capacity")
        app.processEvents()

        assert window.stack.currentWidget() is previous_page
        assert window.notification_center.last_notification is not None
        assert window.notification_center.last_notification.key == (
            "repair.handoff.storage.capacity"
        )
        assert "fresh evidence" in window.notification_center.last_notification.title.casefold()
        assert "Recovery handoff stopped" in window.diagnostics_center.saved_label.text()
        assert "nothing started" in window.diagnostics_center.saved_label.text()
        assert window.repair_center.active_session is None
        assert window.repair_center.host_repair_worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_recovery_source_handoff_fails_closed_when_finding_is_stale(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window._navigate_route("recovery_bay")
        previous_page = window.stack.currentWidget()

        window.repair_center.diagnostic_requested.emit("storage.capacity")
        app.processEvents()

        assert window.stack.currentWidget() is previous_page
        assert window.notification_center.last_notification is not None
        assert window.notification_center.last_notification.key == (
            "diagnostics.handoff.storage.capacity"
        )
        assert "fresh evidence" in window.notification_center.last_notification.title.casefold()
        assert "SOURCE RETURN STOPPED" in window.repair_center.diagnostic_context.text()
        assert "NO ACTION STARTED" in window.repair_center.diagnostic_context.text()
        assert window.repair_center.active_session is None
        assert window.repair_center.host_repair_worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_handoff_failures_remain_visible_when_desktop_notifications_are_disabled(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        app_settings=AppSettings(desktop_notifications_enabled=False),
    )
    try:
        window._navigate_route("quantum_optimizer")
        window.diagnostics_center.repair_requested.emit("storage.capacity")
        app.processEvents()

        assert window.stack.currentWidget() is window.diagnostics_center
        assert window.notification_center.last_notification is None
        assert "storage.capacity needs fresh evidence" in (
            window.diagnostics_center.saved_label.text()
        )
        assert "nothing started" in window.diagnostics_center.saved_label.text()

        window._navigate_route("recovery_bay")
        window.repair_center.diagnostic_requested.emit("storage.capacity")
        app.processEvents()

        assert window.stack.currentWidget() is window.repair_center
        assert window.notification_center.last_notification is None
        assert "SOURCE RETURN STOPPED" in window.repair_center.diagnostic_context.text()
        assert "REFRESH DEVICE EVIDENCE" in window.repair_center.diagnostic_context.text()
        assert window.repair_center.active_session is None
        assert window.repair_center.host_repair_worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_fresh_repair_comparison_refreshes_exact_local_archives_memory(
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
    initial = AndroidDevice(
        "private-learning-device",
        DeviceState.DEVICE,
        manufacturer="RadForge",
        model="Reference Phone",
        battery_percent=8,
        battery_temperature_c=31.0,
        connection_note="Connected",
    )
    improved = AndroidDevice(
        "private-learning-device",
        DeviceState.DEVICE,
        manufacturer="RadForge",
        model="Reference Phone",
        battery_percent=70,
        battery_temperature_c=31.0,
        connection_note="Connected",
    )
    try:
        window.repair_center.set_devices([initial])
        window.repair_center._start_session()
        assert window.repair_center.active_session is not None
        window.repair_center._pending_verification_session = (
            window.repair_center.active_session.session_id
        )

        window.repair_center.set_devices([improved])
        app.processEvents()

        assert window.repair_center.active_session is not None
        assert window.repair_center.active_session.verification_direction == "improved"
        window.repair_center.knowledge_article_requested.emit("device-battery-low")
        app.processEvents()

        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.resolution_status.isVisibleTo(window.knowledge_center)
        assert "1 IMPROVED" in window.knowledge_center.resolution_status.text()
        assert "INTERPRETATION BOUNDARY" in window.knowledge_center.detail.toPlainText()
        assert "does not prove" in window.knowledge_center.detail.toPlainText()
        assert "private-learning-device" not in window.knowledge_center.detail.toPlainText()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_recovery_bay_archives_handoff_and_canonical_fix_route_are_connected(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window.repair_center.symptom_input.setText("adb unauthorized")
        window.repair_center.archives_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.search.text() == "adb unauthorized"
        assert window.knowledge_center.open_route.property("route") == "command_deck"
        window.knowledge_center.open_route.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.device_center
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
    window.device_center.set_repair_context("storage.capacity", "Device storage is nearly full")

    try:
        window._scan_failed("ADB transport failed during refresh")

        assert window.device_center.devices == []
        assert window.diagnostics_center.devices == []
        assert window.repair_center.devices == []
        assert window.rom_studio.devices == []
        assert finished == [(False, "ADB transport failed during refresh")]
        assert window.connection_state.text() == "⌁  Reconnecting Device Engine"
        assert window.connection_state.objectName() == "Warning"
        assert window.sidebar_device_state.objectName() == "Warning"
        assert window._reconnect_timer.isActive()
        assert "automatic retry" in window.sidebar_device_detail.text()
        assert any(
            button.text() == "Resolve Platform Tools"
            for button in window.device_center.findChildren(QPushButton)
        )
    finally:
        window.companion_center.transport.close()
        window.close()


def test_adb_tool_refresh_activates_and_revokes_every_dependent_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    scans: list[bool] = []
    monkeypatch.setattr(window, "scan", lambda: scans.append(True))
    available = (ToolStatus("ADB", True, "/bin/true", "test", "Ready"),)
    missing = (ToolStatus("ADB", False, detail="Missing"),)
    device = AndroidDevice("device-serial", DeviceState.DEVICE, model="Test phone")
    runtime_requests = []

    def resolve_runtime(required, **options):
        runtime_requests.append((required, options))
        return False

    monkeypatch.setattr(window.rom_studio, "_resolve_required_tools", resolve_runtime)

    try:
        window.apk_installer.runtime_tools_requested.emit()
        assert runtime_requests[0][0] == ("ADB",)
        assert runtime_requests[0][1]["parent"] is window

        window.device_center.runtime_tools_requested.emit()
        window.terminal_center.runtime_tools_requested.emit()
        window.repair_center.runtime_tools_requested.emit()
        window.backup_center.runtime_tools_requested.emit()
        assert [request[0] for request in runtime_requests] == [
            ("ADB",),
            ("ADB",),
            ("ADB",),
            ("ADB",),
            ("ADB",),
        ]

        window.rom_studio.tool_statuses_resolved.emit(available)

        assert window.engine is not None
        assert window.timer.isActive()
        assert scans == [True]
        resolved_adb = Path("/bin/true").resolve()
        assert window.rom_studio.adb_executable == resolved_adb
        assert window.rom_studio.device_scan_available
        assert window.apk_installer.install_service is not None
        assert window.backup_center.media_backup_service is not None
        assert window.terminal_center.adb_executable == resolved_adb
        assert window.repair_center.host_repair_service is not None

        window._scan_complete([device])
        assert window.repair_center.devices

        window._tool_statuses_changed(missing)

        assert window.engine is None
        assert not window.timer.isActive()
        assert not window._reconnect_timer.isActive()
        assert window.rom_studio.adb_executable is None
        assert not window.rom_studio.device_scan_available
        assert window.apk_installer.install_service is None
        assert window.backup_center.media_backup_service is None
        assert window.terminal_center.adb_executable is None
        assert window.repair_center.host_repair_service is None
        assert window.device_center.devices == []
        assert window.diagnostics_center.devices == []
        assert window.repair_center.devices == []
        assert window.rom_studio.devices == []
        assert "Platform Tools" in window.device_center.device_note.text()
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
    assert _device_scan_failure_is_transient("ADB transport failed during refresh")
    assert _device_scan_failure_is_transient("probe timed out")
    assert not _device_scan_failure_is_transient("Guardian audit integrity failed")


def test_sidebar_navigation_tooltip_is_compact_wrapped_and_escaped() -> None:
    tooltip = _sidebar_nav_tooltip("App <Launchpad>", "Install Android apps & packages.")

    assert tooltip.startswith("<qt>")
    assert "width='220'" in tooltip
    assert tooltip.count("<tr>") == 2
    assert "App &lt;Launchpad&gt;" in tooltip
    assert "apps &amp; packages" in tooltip


def test_sidebar_reserves_navigation_space_and_folds_optional_connection_fields(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window.resize(1080, 700)
        window.show()
        app.processEvents()

        assert window._brand_card.height() <= 190
        assert not window._brand_logo.pixmap().isNull()
        assert window._brand_logo.accessibleName() == (
            "Official ROMVERSE website icon in the app sidebar"
        )
        assert window.nav_scroll.minimumHeight() == 150
        assert window.sidebar_device_state.wordWrap()
        assert not window.connection_uptime.isVisible()
        assert not window.connection_clock.isVisible()

        window.resize(1440, 900)
        app.processEvents()
        assert window._brand_card.height() <= 250
        assert window.connection_uptime.isVisible()
        assert window.connection_clock.isVisible()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_workspace_chrome_collapses_focuses_and_restores_without_changing_page_state(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window.resize(1200, 760)
        window.show()
        window._navigate_route("about")
        app.processEvents()
        page_index = window.stack.currentIndex()
        page = window.stack.currentWidget()

        assert window.workspace_section.text() == "SYSTEM"
        assert window.workspace_route_title.text() == "About ROMVERSE"
        assert window.workspace_route_title.accessibleName() == (
            "Current Desktop page: About ROMVERSE"
        )
        assert window.workspace_search_button.toolTip().startswith("Find any ROMVERSE page")

        window.navigation_toggle.click()
        app.processEvents()

        assert window._workspace_shell_state.navigation_collapsed
        assert window.sidebar.width() == 78
        assert window._brand_card.height() == 68
        assert window._brand_logo.width() == window._brand_logo.height() == 58
        assert all(label.isHidden() for label in window.nav_section_labels)
        assert window.sidebar_device_card.isHidden()
        assert window.sidebar_version.isHidden()
        assert all(not button.text() for button in window.nav_buttons)
        assert all(button.accessibleName().startswith("Open ") for button in window.nav_buttons)
        assert window.stack.currentIndex() == page_index
        assert window.stack.currentWidget() is page
        assert window.sidebar.isVisible()
        assert window.connection_bar.isVisible()

        window.focus_button.click()
        app.processEvents()

        assert window._workspace_shell_state.focus_mode
        assert window.sidebar.isHidden()
        assert window.connection_bar.isHidden()
        assert window.workspace_bar.isVisible()
        assert not window.navigation_toggle.isEnabled()
        assert window.navigation_toggle.isHidden()
        assert window.focus_exit_shortcut.isEnabled()
        assert window.focus_button.text().startswith("EXIT FOCUS")
        assert window.workspace_section.text() == "FOCUS WORKSPACE  •  SYSTEM"
        assert window.stack.currentIndex() == page_index
        assert window.stack.currentWidget() is page

        window.workspace_search_button.click()
        app.processEvents()
        assert window._command_palette is not None and window._command_palette.isVisible()
        window._command_palette.reject()
        app.processEvents()
        assert window._command_palette is None

        window._leave_focus_mode()
        app.processEvents()

        assert not window._workspace_shell_state.focus_mode
        assert window._workspace_shell_state.navigation_collapsed
        assert window.sidebar.isVisible() and window.sidebar.width() == 78
        assert window.connection_bar.isVisible()
        assert window.workspace_section.text() == "SYSTEM"

        window.navigation_toggle.click()
        app.processEvents()
        assert window.sidebar.width() == 263
        assert [button.text().replace("&&", "&") for button in window.nav_buttons][0] == (
            "Command Deck"
        )
        assert not any(label.isHidden() for label in window.nav_section_labels)
        assert window.sidebar_device_card.isVisible()
    finally:
        window.companion_center.transport.close()
        window.close()


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
