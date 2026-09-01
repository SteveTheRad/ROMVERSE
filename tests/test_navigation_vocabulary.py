from __future__ import annotations

import os
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from romverse.core.settings import AppSettings, ExperienceMode
from romverse.device.catalog import (
    DeviceCatalogError,
    DeviceCatalogStatus,
    GooglePlayDeviceCatalog,
)
from romverse.device.identity import IdentityAuthority
from romverse.device.models import AndroidDevice, DeviceState, StorageInfo
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.manifest_review import GuardianManifestReviewService
from romverse.infrastructure.process import CommandResult
from romverse.infrastructure.tools import ToolStatus
from romverse.intelligence.synapse import (
    SynapseContribution,
    SynapseKnowledgeState,
    SynapseScope,
    SynapseStore,
)
from romverse.nexus.events import MissionConfidence
from romverse.nexus.planning import NexusObjective, NexusPlanner
from romverse.repair.templates import RepairConcern
from romverse.ui.main_window import (
    MainWindow,
    _device_scan_failure_copy,
    _device_scan_failure_is_transient,
    _sidebar_device_art_kind,
    _sidebar_nav_tooltip,
)
from tests.test_apk_center_ui import _device as _apk_device
from tests.test_apk_center_ui import _ready_plan as _apk_ready_plan
from tests.test_device_catalog import _payload, _sync
from tests.test_device_dna import _device, _project
from tests.test_guardian_manifest_review import _prepared as _prepared_guardian_manifest


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


def test_about_recalculates_real_workspace_evidence_and_returns_from_its_exact_guide(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(GooglePlayDeviceCatalog, "MINIMUM_ENTRIES", 1)
    _sync(
        GooglePlayDeviceCatalog(tmp_path),
        _payload(("Example", "Example Nebula", "nebula", "EX-100")),
    )
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    tools = (
        ToolStatus("Python", True, "/verified/python", "3.14", "Ready"),
        ToolStatus("ADB", False, detail="Not ready"),
    )
    window = MainWindow(
        None,
        logo,
        tmp_path,
        pack_registry=registry,
        tool_statuses=tools,
        app_icon_path=logo,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    try:
        window.rom_studio.store.create("About evidence project")
        window.nexus_events.start(
            source="ROM Studio",
            stage="about-evidence-test",
            title="Genuine local mission",
            summary="A producing subsystem wrote this event.",
            explanation="The About page may count it but cannot execute it.",
            next_action="Inspect the owning feature.",
        )

        window._navigate_route("about")
        app.processEvents()

        assert window.about_page.evidence_values["device"].text() == (
            f"{len(registry.packs)} DEVICE PACKS  •  1 OFFICIAL IDS"
        )
        assert window.about_page.evidence_values["knowledge"].text() == (
            "123 VERIFIED GUIDES  •  73 KNOWN FIXES"
        )
        ready_tools = sum(status.available for status in window.toolchain_center.statuses)
        tool_count = len(window.toolchain_center.statuses)
        assert window.about_page.evidence_values["build"].text() == (
            f"1 LOCAL PROJECT  •  {ready_tools}/{tool_count} HOST TOOLS READY"
        )
        assert window.about_page.evidence_values["live"].text() == ("1 GENUINE EVENT  •  1 ACTIVE")

        owners = {
            "device_atlas": window.device_packs_center,
            "archives": window.knowledge_center,
            "rom_studio": window.rom_studio,
            "forge_arsenal": window.toolchain_center,
            "live_console": window.live_console,
        }
        for route, owner in owners.items():
            window._navigate_route("about")
            window.about_page.evidence_buttons[route].click()
            app.processEvents()
            assert window.stack.currentWidget() is owner

        window._navigate_route("about")
        window.about_page.evidence_guide.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.list.currentItem().text() == (
            "About runtime evidence is stale or unavailable"
        )
        assert window.knowledge_center.source_context.property("source_route") == "about"
        assert not window.knowledge_center.source_context.isHidden()
        window.knowledge_center.source_return.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.about_page
        assert window.guardian_center.worker is None

        window.nexus_events.path.write_text("{}", encoding="utf-8")
        window._navigate_route("about")
        app.processEvents()
        assert window.about_page.evidence_values["live"].text() == ("EVENT COUNTS UNAVAILABLE")
        assert window.about_page.evidence_cards["live"].property("evidenceState") == ("unavailable")
        assert "rejected the local ledger" in window.about_page.evidence_details["live"].text()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_opening_archives_reloads_new_private_synapse_learning(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        store = window.knowledge_center.synapse_store
        assert isinstance(store, SynapseStore)
        scope = SynapseScope.create(
            operation="payload extraction",
            source_kind="payload-bin",
            device_codename="popsicle",
            tool_name="payload-dumper-go",
            tool_version="2.0.2",
        )

        def add(source: str) -> None:
            store.contribute(
                SynapseContribution.create(
                    fingerprint_id="a" * 64,
                    solution_id="inspect-payload-source",
                    scope=scope,
                    source_family=source,
                    summary="Verified typed payload inspection.",
                    successful=True,
                    locally_verified=True,
                    action_receipt_digest="b" * 64,
                    verification_evidence_digest="c" * 64,
                )
            )

        add("official-aosp")
        assert window.knowledge_center.synapse_knowledge == ()
        window._navigate_route("archives")
        app.processEvents()
        assert len(window.knowledge_center.synapse_knowledge) == 1
        assert window.knowledge_center.synapse_knowledge[0].state is (
            SynapseKnowledgeState.VERIFIED_SUCCESS
        )

        window._navigate_route("about")
        add("maintainer-tool")
        window._navigate_route("archives")
        app.processEvents()
        assert window.knowledge_center.synapse_knowledge[0].state is (SynapseKnowledgeState.STRONG)
        assert "1 USABLE" in window.knowledge_center.learning_status.text()
        window.knowledge_center.learning_button.click()
        app.processEvents()
        assert window.knowledge_center.learning_dialog is not None
        assert "2 successful verification(s)" in (
            window.knowledge_center.learning_dialog.detail.toPlainText()
        )
        assert window.guardian_center.worker is None
    finally:
        if window.knowledge_center.learning_dialog is not None:
            window.knowledge_center.learning_dialog.close()
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
        assert not window.rom_studio.dashboard_handoff.isHidden()
        assert window.rom_studio.dashboard_handoff_title.text() == (
            "Build ROM → Genesis Sequence"
        )
        assert "NO BUILD OR PHONE ACTION STARTED" in (
            window.rom_studio.dashboard_handoff_detail.text()
        )

        window._navigate(0)
        actions["Build ROM"].click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert genesis_opened == [True, True]

        window._navigate(0)
        actions["Pre-Build Simulation"].click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.command_tabs.currentIndex() == 1
        assert window.rom_studio.dashboard_handoff_title.text() == (
            "Pre-Build Simulation → Build & Proof"
        )
        assert window.rom_studio.dashboard_handoff_badge.text() == "PREREQUISITE"
        assert "NO BUILD OR PHONE ACTION STARTED" in (
            window.rom_studio.dashboard_handoff_detail.text()
        )
        assert window.rom_studio.worker is None

        window._navigate(0)
        actions["Recipes"].click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.command_tabs.currentIndex() == 2
        assert window.rom_studio.dashboard_handoff_title.text() == "Recipes → Recipe Forge"
        assert "NO RECIPE OR PHONE ACTION STARTED" in (
            window.rom_studio.dashboard_handoff_detail.text()
        )
        assert window.rom_studio.worker is None

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


def test_command_deck_evidence_handoffs_preserve_current_owner_state(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    owners = (
        ("Device DNA", window.device_packs_center),
        ("Health Review", window.diagnostics_center),
        ("Rescue & Backup", window.backup_center),
    )
    try:
        for action, owner in owners:
            window._navigate(0)
            window._handle_dashboard_action(action)
            app.processEvents()
            assert window.stack.currentWidget() is owner
            assert not owner.dashboard_handoff.isHidden()
            assert owner.dashboard_handoff_badge.text() == "EVIDENCE NEEDED"
            assert "NO " in owner.dashboard_handoff_detail.text()
            assert not owner.open_dashboard_intent("Unknown workflow")

        device = _device()
        window._scan_complete([device])
        app.processEvents()
        assert window.device_packs_center.active_report is not None
        assert window.diagnostics_center.current_report is not None
        assert window.backup_center.device is not None

        window._navigate(0)
        window._handle_dashboard_action("Device DNA")
        app.processEvents()
        report = window.device_packs_center.active_report
        assert report is not None
        assert window.stack.currentWidget() is window.device_packs_center
        assert window.device_packs_center.dashboard_handoff_badge.text() == "CURRENT EVIDENCE"
        assert report.report_digest[:16] in (
            window.device_packs_center.dashboard_handoff_detail.text()
        )
        assert "NO SCAN, APPROVAL, BUILD, FLASH, OR PHONE ACTION STARTED" in (
            window.device_packs_center.dashboard_handoff_detail.text()
        )

        window._navigate(0)
        window._handle_dashboard_action("Health Review")
        app.processEvents()
        diagnostic = window.diagnostics_center.current_report
        assert diagnostic is not None
        assert window.stack.currentWidget() is window.diagnostics_center
        assert str(diagnostic.health_score) in window.diagnostics_center.dashboard_handoff_title.text()
        assert "Recommended Action Plan" in (
            window.diagnostics_center.dashboard_handoff_detail.text()
        )
        assert "NO NEW SCAN, OPTIMIZATION, CLEANUP, OR PHONE ACTION STARTED" in (
            window.diagnostics_center.dashboard_handoff_detail.text()
        )

        window._navigate(0)
        window._handle_dashboard_action("Rescue & Backup")
        app.processEvents()
        assert window.stack.currentWidget() is window.backup_center
        assert window.backup_center.dashboard_handoff_badge.text() == "PLAN RECOVERY"
        assert window.backup_center.device.display_name in (
            window.backup_center.dashboard_handoff_title.text()
        )
        assert "NO BACKUP, COPY, RESTORE, OR PHONE ACTION STARTED" in (
            window.backup_center.dashboard_handoff_detail.text()
        )
        assert window.active_worker is None
        assert window.backup_center.worker is None
        assert window.backup_center.evidence_worker is None
        assert window.backup_center.media_backup_worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_device_atlas_and_nexus_preserve_exact_context_into_rom_studio(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    genesis_opened: list[bool] = []
    monkeypatch.setattr(
        window.rom_studio,
        "_open_guided_setup",
        lambda: genesis_opened.append(True),
    )
    try:
        window._scan_complete([_device()])
        app.processEvents()
        report = window.device_packs_center.active_report
        assert report is not None and report.build_contract_ready

        window.device_packs_center.continue_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert genesis_opened == [True]
        assert window.rom_studio.dashboard_handoff_eyebrow.text().startswith(
            "DEVICE ATLAS HANDOFF"
        )
        assert report.report_digest[:16] in window.rom_studio.dashboard_handoff_detail.text()
        assert "NO BUILD, APPROVAL, FLASH, OR PHONE ACTION STARTED" in (
            window.rom_studio.dashboard_handoff_detail.text()
        )
        assert window.rom_studio.worker is None

        window._navigate_route("device_atlas")
        window.device_packs_center.requirement_buttons["build"].click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert genesis_opened == [True]
        assert window.rom_studio.command_tabs.currentIndex() == 1
        assert window.rom_studio.dashboard_handoff_title.text() == (
            "Device Atlas → Build & Proof"
        )
        assert window.rom_studio.worker is None

        project = window.rom_studio.store.create("Nexus exact project")
        window.nexus_center.refresh()
        window._navigate_route("nexus")
        window.nexus_center.evidence_studio_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.current_project is not None
        assert window.rom_studio.current_project.project_id == project.project_id
        assert window.rom_studio.dashboard_handoff_eyebrow.text().startswith(
            "ROMVERSE NEXUS HANDOFF"
        )
        assert project.project_id in window.rom_studio.dashboard_handoff_detail.text()
        assert "NO PROJECT WORKER, PLAN, BUILD, OR PHONE ACTION STARTED" in (
            window.rom_studio.dashboard_handoff_detail.text()
        )
        assert window.rom_studio.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_rom_studio_preserves_exact_project_into_time_machine_and_device_atlas(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, registry, project, _report = _project(tmp_path)
    store.create_working_copy(project.project_id)
    snapshot = store.create_snapshot(project.project_id)
    window = MainWindow(
        None,
        logo,
        store.workspace,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    try:
        window._scan_complete([_device()])
        app.processEvents()
        window.rom_studio.refresh(project.project_id)
        assert window.rom_studio.current_project is not None

        window.rom_studio.rollback_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.backup_center
        assert str(window.backup_center.project_selector.currentData()) == project.project_id
        assert window.backup_center.snapshot_list.currentItem() is not None
        assert snapshot.snapshot_id in window.backup_center.snapshot_list.currentItem().text()
        assert window.backup_center.dashboard_handoff_eyebrow.text().startswith(
            "ROM STUDIO HANDOFF"
        )
        assert project.project_id in window.backup_center.dashboard_handoff_detail.text()
        assert project.original.sha256[:16] in window.backup_center.dashboard_handoff_detail.text()
        assert "NO BACKUP, COPY, RESTORE, BUILD, FLASH, OR PHONE ACTION STARTED" in (
            window.backup_center.dashboard_handoff_detail.text()
        )
        assert window.backup_center.worker is None

        window._navigate_route("rom_studio")
        assert window.rom_studio.request_device_atlas()
        app.processEvents()
        assert window.stack.currentWidget() is window.device_packs_center
        assert window.device_packs_center.dashboard_handoff_eyebrow.text().startswith(
            "ROM STUDIO HANDOFF"
        )
        assert project.project_id in window.device_packs_center.dashboard_handoff_detail.text()
        assert project.original.sha256[:16] in (
            window.device_packs_center.dashboard_handoff_detail.text()
        )
        assert window.device_packs_center.dashboard_handoff_badge.text() == (
            "CURRENT • GATES REMAIN"
        )
        assert window.device_packs_center.active_report.report_digest[:16] in (
            window.device_packs_center.dashboard_handoff_detail.text()
        )
        assert "build LOCKED" in window.device_packs_center.dashboard_handoff_detail.text()
        assert "NO SCAN, BUILD, APPROVAL, FLASH, OR PHONE ACTION STARTED" in (
            window.device_packs_center.dashboard_handoff_detail.text()
        )

        window._navigate_route("rom_studio")
        window._open_time_machine("missing-project")
        assert window.stack.currentWidget() is window.rom_studio
        assert "TIME MACHINE HANDOFF STOPPED" in window.rom_studio.operation_status.text()
        window._open_device_atlas_from_studio("missing-project")
        assert window.stack.currentWidget() is window.rom_studio
        assert "DEVICE ATLAS HANDOFF STOPPED" in window.rom_studio.operation_status.text()
    finally:
        window.companion_center.transport.close()
        window.close()


def test_studio_manifest_opens_persistent_guardian_context_and_returns_exactly(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    store, project, registry, report, device = _prepared_guardian_manifest(tmp_path)
    manifest = GuardianManifestReviewService(store, registry).compile(
        project.project_id,
        report,
        device,
    )
    window = MainWindow(
        None,
        logo,
        store.workspace,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    monkeypatch.setattr(
        "romverse.ui.main_window.BuildReadinessService.assess",
        lambda *_args, **_kwargs: report,
    )
    try:
        window.rom_studio.set_devices([device])
        window.rom_studio.guardian_review_requested.emit(
            project.project_id,
            manifest.manifest_digest,
        )
        app.processEvents()

        assert window.stack.currentWidget() is window.guardian_center
        assert window.guardian_center.studio_review_identity == (
            project.project_id,
            manifest.manifest_digest,
        )
        assert manifest.manifest_digest[:16] in (
            window.guardian_center.studio_review_detail.text()
        )
        assert window.guardian_center.studio_review_badge.text() == "ZERO AUTHORITY"
        assert window.guardian_center.worker is None

        window.guardian_center.studio_return_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.current_project is not None
        assert window.rom_studio.current_project.project_id == project.project_id
        assert window.rom_studio.dashboard_handoff_eyebrow.text().startswith(
            "GUARDIAN CORE HANDOFF"
        )
        assert manifest.manifest_digest[:16] in window.rom_studio.dashboard_handoff_detail.text()
        assert "Execution authority: NONE" in window.rom_studio.dashboard_handoff_detail.text()

        window.rom_studio.set_devices([])
        window._navigate_route("guardian_core")
        app.processEvents()
        assert window.guardian_center.studio_review_identity is None
        assert window.guardian_center.studio_review_badge.text() == "CONTEXT REFUSED"
        assert "No action started" in window.guardian_center.studio_review_detail.text()
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
        window.guardian_center.nexus_return_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.guardian_center
        assert window.guardian_center.nexus_review_identity is None
        assert window.guardian_center.nexus_review_badge.text() == "CONTEXT REFUSED"
        assert "no longer matches" in window.guardian_center.nexus_review_detail.text()
        assert "No action started" in window.guardian_center.nexus_review_detail.text()
        assert window.guardian_center.worker is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_time_machine_opens_exact_guardian_context_and_expires_superseded_plan(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    device = AndroidDevice(
        "private-backup-device",
        DeviceState.DEVICE,
        manufacturer="RadForge",
        model="Reference Phone",
        battery_percent=84,
        storage=StorageInfo(percent_used=37),
        bootloader_locked=True,
        verified_boot="green",
    )
    try:
        window.backup_center.set_devices([device])
        with patch("romverse.ui.backup_center.QMessageBox.information"):
            window.backup_center.plan_button.click()
        loaded = window.backup_center.plan_store.load_latest()
        assert loaded.data is not None

        window.backup_center.guardian_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.guardian_center
        assert not window.guardian_center.backup_review.isHidden()
        assert window.guardian_center.nexus_review.isHidden()
        assert window.guardian_center.backup_review_identity == (
            loaded.data["plan_id"],
            loaded.data["plan_digest"],
        )
        assert window.guardian_center.backup_review_badge.text() == "ZERO AUTHORITY"
        assert "Reference Phone" in window.guardian_center.backup_review_title.text()
        assert window.guardian_center.worker is None

        window.guardian_center.backup_return_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.backup_center
        assert window.backup_center._selected_plan_id == loaded.data["plan_id"]

        replacement = window.backup_center.plan_store.create(device)
        window._open_backup_guardian_review(
            replacement.plan_id,
            replacement.plan_digest,
        )
        window.backup_center.plan_store.create(device)
        window.guardian_center.backup_return_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.guardian_center
        assert window.guardian_center.backup_review_identity is None
        assert window.guardian_center.backup_review_badge.text() == "CONTEXT REFUSED"
        assert "no longer matches" in window.guardian_center.backup_review_detail.text()
        assert "No action started" in window.guardian_center.backup_review_detail.text()
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


def test_nexus_missing_evidence_opens_exact_guide_then_rom_studio(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        assert window.nexus_center.current_plan is None
        assert not window.nexus_center.generate_button.isEnabled()
        window.nexus_center.evidence_guide_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.list.count() == 1
        assert window.knowledge_center.search.text() == (
            "Nexus cannot generate a plan because project evidence is missing"
        )
        assert window.knowledge_center.open_route.property("route") == "rom_studio"
        assert "NO PLAN, APPROVAL, OR EXECUTION" in (window.knowledge_center.detail.toPlainText())
        window.knowledge_center.open_route.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.rom_studio
        assert window.nexus_center.current_plan is None
    finally:
        window.companion_center.transport.close()
        window.close()


def test_apk_failure_opens_exact_guide_and_returns_to_unchanged_launchpad(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    try:
        window._navigate_route("app_launchpad")
        window.apk_installer.set_devices([_apk_device()])
        plan = _apk_ready_plan(tmp_path)
        window.apk_installer._plan_ready(plan)
        with patch("romverse.ui.apk_center.QMessageBox.warning"):
            window.apk_installer._install_complete(
                CommandResult(
                    ("adb",),
                    1,
                    "",
                    "Failure [INSTALL_FAILED_VERSION_DOWNGRADE: older version]",
                )
            )
        window.apk_installer.failure_guide_button.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.list.count() == 1
        assert window.knowledge_center.search.text() == (
            "APK install error: INSTALL_FAILED_VERSION_DOWNGRADE"
        )
        assert window.knowledge_center.source_return.text() == "Return to App Launchpad"
        assert window.apk_installer.current_plan is plan
        assert window.apk_installer.active_worker is None

        window.knowledge_center.source_return.click()
        app.processEvents()

        assert window.stack.currentWidget() is window.apk_installer
        assert window.apk_installer.current_plan is plan
        assert not window.apk_installer.failure_guidance.isHidden()
        assert window.apk_installer.active_worker is None
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


def test_fresh_scan_connects_exact_official_device_identity_to_every_desktop_consumer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(GooglePlayDeviceCatalog, "MINIMUM_ENTRIES", 1)
    catalog = GooglePlayDeviceCatalog(tmp_path)
    _sync(
        catalog,
        _payload(("Example", "Example Nebula", "nebula", "EX-100")),
    )
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    device = AndroidDevice(
        "private-catalog-device",
        DeviceState.DEVICE,
        brand="Example",
        manufacturer="Example Industries",
        model="EX-100",
        codename="nebula",
        android_version="16",
    )
    try:
        window._scan_complete([device])
        app.processEvents()

        assert window.device_center.devices[0].marketing_name == "Example Nebula"
        assert window.diagnostics_center.devices[0].marketing_name == "Example Nebula"
        assert window.rom_studio.devices[0].marketing_name == "Example Nebula"
        assert window.sidebar_device_name.text() == "Example Industries Example Nebula"
        assert window.connection_device.text() == (
            "Device: Example Industries Example Nebula (nebula)"
        )
        assert window.device_packs_center.identity_catalog_badge.text() == ("EXACT ID • READ ONLY")
        receipt = window.device_identity.load(window.device_center.devices[0])
        assert receipt is not None
        assert receipt.authority is IdentityAuthority.GOOGLE_PLAY_CATALOG
        assert window.device_catalog_worker is None

        readiness = next(
            event for event in window.nexus_events.list_recent() if event.source == "Device Atlas"
        )
        assert readiness.stage == "device-pack-readiness"
        assert "build is locked and flash is locked" in readiness.summary
        assert readiness.next_action == "Confirm the exact model contract"
        assert readiness.confidence is MissionConfidence.VERIFIED
        assert "identity=verified" in readiness.explanation
        assert "compile=locked" in readiness.explanation

        window._navigate_route("live_console")
        app.processEvents()
        readiness_row = next(
            row
            for row in range(window.live_console.table.rowCount())
            if window.live_console.table.item(row, 1).text() == "Device Atlas"
        )
        window.live_console.table.selectRow(readiness_row)
        app.processEvents()
        assert window.live_console.open_source_button.text() == "Open Device Atlas"
        window.live_console.open_source_button.click()
        assert window.stack.currentWidget() is window.device_packs_center

        action = window.device_packs_center.active_next_action
        report = window.device_packs_center.active_report
        assert action is not None and report is not None
        window._open_device_pack_next_action(
            action.route,
            action.article_key,
            action.check_id,
            "0" * 64,
        )
        assert window.stack.currentWidget() is window.device_packs_center
        assert "NEXT ACTION STOPPED" in window.device_packs_center.next_action_feedback.text()

        window.device_packs_center.next_action_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.knowledge_center
        assert "Recognize an Android model" in window.knowledge_center.list.currentItem().text()
        window.knowledge_center.source_return.click()
        assert window.stack.currentWidget() is window.device_packs_center

        window._open_device_requirement(
            "compile",
            "archives",
            "device-build-requirements-blueprint",
            "0" * 64,
        )
        assert window.stack.currentWidget() is window.device_packs_center
        assert "COMPILE HANDOFF STOPPED" in (
            window.device_packs_center.requirements_feedback.text()
        )

        window.device_packs_center.requirement_buttons["compile"].click()
        app.processEvents()
        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.list.currentItem().text() == (
            "Determine what a recognized Android device needs to build, compile, and flash"
        )
        assert window.knowledge_center.source_return.text() == "Return to Device Atlas"
    finally:
        window.companion_center.transport.close()
        window.close()


def test_device_atlas_runs_official_id_sync_in_managed_worker_and_keeps_failure_visible(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    started = []
    monkeypatch.setattr("romverse.ui.main_window.start_background", started.append)
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(None, logo, tmp_path, app_icon_path=logo)
    status = DeviceCatalogStatus(
        True,
        True,
        "Official IDs current",
        53_575,
        "2026-09-01T00:00:00+00:00",
        "a" * 64,
    )
    try:
        monkeypatch.setattr(window.device_catalog, "sync", lambda: status)
        window.device_packs_center.identity_catalog_button.click()

        assert len(started) == 1
        assert window.device_catalog_worker is started[0]
        assert "CHECKING" in window.device_packs_center.identity_catalog_badge.text()
        started.pop().execute()
        app.processEvents()

        assert window.device_catalog_worker is None
        assert "53,575" in window.device_packs_center.identity_catalog_title.text()
        assert window.device_packs_center.identity_catalog_badge.text() == "CURRENT • READ ONLY"

        def fail():
            raise DeviceCatalogError("Official device catalog returned an unexpected route")

        monkeypatch.setattr(window.device_catalog, "sync", fail)
        window.device_packs_center.identity_catalog_button.click()
        assert len(started) == 1
        started.pop().execute()
        app.processEvents()

        assert window.device_catalog_worker is None
        assert "sync stopped safely" in (
            window.device_packs_center.identity_catalog_title.text().casefold()
        )
        assert "No build, flash, approval, or phone action" in (
            window.device_packs_center.identity_catalog_detail.text()
        )
    finally:
        window.companion_center.transport.close()
        window.close()


def test_device_atlas_stock_gate_opens_time_machine_with_exact_context(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    try:
        window._scan_complete(
            [
                AndroidDevice(
                    "private-xiaomi",
                    DeviceState.DEVICE,
                    brand="Xiaomi",
                    manufacturer="Xiaomi",
                    model="2509FPN0BC",
                    product="popsicle_global",
                    codename="popsicle",
                )
            ]
        )
        app.processEvents()

        assert window.device_packs_center.active_next_action is not None
        assert window.device_packs_center.active_next_action.route == "time_machine"
        assert "FLASH LOCKED" in window.device_packs_center.requirement_badges["flash"].text()
        window.device_packs_center.requirement_buttons["flash"].click()
        app.processEvents()

        assert window.stack.currentWidget() is window.backup_center
        assert window.backup_center.device_atlas_handoff.isVisibleTo(window.backup_center)
        assert "2509FPN0BC / popsicle" in (window.backup_center.device_atlas_handoff_title.text())
        assert "No worker or phone action started" in (
            window.backup_center.device_atlas_handoff_detail.text()
        )
        assert window.backup_center.device_atlas_project_button.isVisibleTo(window.backup_center)

        report = window.device_packs_center.active_report
        assert report is not None
        window.backup_center.device_atlas_project_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.dashboard_handoff_eyebrow.text().startswith(
            "TIME MACHINE HANDOFF"
        )
        assert report.report_digest[:16] in window.rom_studio.dashboard_handoff_detail.text()
        assert window.rom_studio.worker is None

        window._navigate_route("device_atlas")
        window.device_packs_center.requirement_buttons["flash"].click()
        app.processEvents()
        assert window.stack.currentWidget() is window.backup_center
        window._scan_complete([])
        app.processEvents()
        window.backup_center.device_atlas_project_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.backup_center
        assert "expired safely" in window.backup_center.device_atlas_handoff_title.text()
        assert "No project worker, build, approval, or phone action started" in (
            window.backup_center.device_atlas_handoff_detail.text()
        )
    finally:
        window.companion_center.transport.close()
        window.close()


def test_device_atlas_carries_exact_pack_tools_into_forge_and_verified_archives(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    setup_calls = []

    class SetupStatus:
        def setText(self, message):
            setup_calls.append(("status", message))

    class SetupDialog:
        def __init__(self, _host, statuses, _workspace, _parent, **options):
            self.status = SetupStatus()
            setup_calls.append(("statuses", statuses))
            setup_calls.append(("options", options))

        def setWindowTitle(self, title):
            setup_calls.append(("title", title))

        def exec(self):
            setup_calls.append(("exec", True))

    monkeypatch.setattr("romverse.ui.toolchain_center.ToolchainSetupDialog", SetupDialog)
    try:
        window._scan_complete(
            [
                AndroidDevice(
                    "private-xiaomi-toolchain",
                    DeviceState.DEVICE,
                    brand="Xiaomi",
                    manufacturer="Xiaomi",
                    model="2509FPN0BC",
                    product="popsicle_global",
                    codename="popsicle",
                )
            ]
        )
        app.processEvents()

        pack = window.device_packs_center.active_pack
        report = window.device_packs_center.active_report
        assert pack is not None and pack.build_contract is not None and report is not None
        assert "14 TOOLS DECLARED" in (
            window.device_packs_center.requirement_badges["compile"].text()
        )
        assert "FLASH LOCKED" in window.device_packs_center.requirement_badges["flash"].text()
        window.device_packs_center.requirement_buttons["build"].click()
        assert window.stack.currentWidget() is window.rom_studio
        window._navigate_route("device_atlas")
        app.processEvents()
        window.device_packs_center.requirement_buttons["compile"].click()
        app.processEvents()

        assert window.stack.currentWidget() is window.toolchain_center
        assert not window.scanning
        assert window.active_worker is None
        assert pack.display_name in window.toolchain_center.device_pack_handoff_title.text()
        assert report.report_digest == window.toolchain_center._device_pack_context.report_digest
        assert "FLASH LOCKED" in window.toolchain_center.device_pack_handoff_badge.text()
        assert "FLASH AUTHORITY: NONE" in (
            window.toolchain_center.device_pack_handoff_feedback.text()
        )
        assert all(
            name in window.toolchain_center.device_pack_handoff_detail.text()
            for name in pack.build_contract.required_tools
        )

        window.toolchain_center.context_return_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.device_packs_center
        assert window.device_packs_center.dashboard_handoff_eyebrow.text().startswith(
            "FORGE ARSENAL HANDOFF"
        )
        assert "Forge Arsenal" in window.device_packs_center.dashboard_handoff_title.text()
        assert report.report_digest[:16] in (
            window.device_packs_center.dashboard_handoff_detail.text()
        )
        assert "AUTHORITY NONE" in (
            window.device_packs_center.dashboard_handoff_detail.text()
        )
        assert "NO ACTION STARTED" in window.device_packs_center.dashboard_handoff_detail.text()
        window.device_packs_center.requirement_buttons["compile"].click()
        app.processEvents()
        assert window.stack.currentWidget() is window.toolchain_center

        window.toolchain_center.statuses = tuple(
            ToolStatus(
                name,
                name != "AVBTool",
                "/bin/true" if name != "AVBTool" else "",
                "fixture" if name != "AVBTool" else "",
                "Ready" if name != "AVBTool" else "Missing",
            )
            for name in pack.build_contract.required_tools
        )
        window.toolchain_center._render()
        assert window.toolchain_center.context_setup_button.isEnabled()
        window.toolchain_center.context_setup_button.click()
        app.processEvents()

        options = next(value for kind, value in setup_calls if kind == "options")
        assert options["required_names"] == pack.build_contract.required_tools
        assert ("exec", True) in setup_calls

        window.toolchain_center.context_guide_button.click()
        app.processEvents()
        assert window.stack.currentWidget() is window.knowledge_center
        assert window.knowledge_center.list.currentItem().text() == (
            "Recognized device needs its exact build toolchain"
        )
        assert window.knowledge_center.source_return.text() == "Return to Forge Arsenal"
        window.knowledge_center.source_return.click()
        assert window.stack.currentWidget() is window.toolchain_center
    finally:
        window.companion_center.transport.close()
        window.close()


def test_exact_forge_context_refuses_stale_device_and_separates_build_from_flash(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        tmp_path,
        app_icon_path=logo,
        pack_registry=registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    dialogs = []

    class SetupDialog:
        def __init__(self, *_args, **_kwargs):
            dialogs.append(True)

    monkeypatch.setattr("romverse.ui.toolchain_center.ToolchainSetupDialog", SetupDialog)
    device = AndroidDevice(
        "private-xiaomi-stale",
        DeviceState.DEVICE,
        brand="Xiaomi",
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        product="popsicle_global",
        codename="popsicle",
    )
    try:
        window._scan_complete([device])
        app.processEvents()
        pack = window.device_packs_center.active_pack
        report = window.device_packs_center.active_report
        assert pack is not None and pack.build_contract is not None and report is not None
        assert report.build_contract_ready
        assert not report.flash_contract_ready
        window.device_packs_center.requirement_buttons["compile"].click()
        app.processEvents()

        first_digest = window.toolchain_center._device_pack_context.report_digest
        window._scan_complete([device])
        app.processEvents()
        refreshed_report = window.device_packs_center.active_report
        assert refreshed_report is not None
        assert refreshed_report.report_digest == first_digest
        assert window.toolchain_center._device_pack_context.report_digest == (
            refreshed_report.report_digest
        )
        assert "HANDOFF STOPPED" not in window.toolchain_center.device_pack_handoff_feedback.text()

        window.toolchain_center.statuses = tuple(
            ToolStatus(name, True, "/bin/true", "fixture", "Ready")
            for name in pack.build_contract.required_tools
        )
        window.toolchain_center._render()
        assert window.toolchain_center.context_continue_button.isEnabled()
        assert "FLASH LOCKED" in window.toolchain_center.device_pack_handoff_badge.text()
        window.toolchain_center.context_continue_button.click()
        assert window.stack.currentWidget() is window.rom_studio
        assert window.rom_studio.dashboard_handoff_eyebrow.text().startswith(
            "FORGE ARSENAL HANDOFF"
        )
        assert window.rom_studio.command_tabs.currentIndex() == 1
        assert first_digest[:16] in window.rom_studio.dashboard_handoff_detail.text()
        assert "NO BUILD, APPROVAL, FLASH, OR PHONE ACTION STARTED" in (
            window.rom_studio.dashboard_handoff_detail.text()
        )
        assert window.rom_studio.worker is None

        window.device_packs_center.requirement_buttons["compile"].click()
        app.processEvents()
        window.toolchain_center.statuses = (ToolStatus("Python", False, detail="Missing fixture"),)
        window.toolchain_center._render()
        assert window.toolchain_center.context_setup_button.isEnabled()
        window._scan_complete([])
        app.processEvents()
        window.toolchain_center.context_return_button.click()
        assert window.stack.currentWidget() is window.toolchain_center
        window.toolchain_center.context_setup_button.click()

        assert dialogs == []
        assert window.stack.currentWidget() is window.toolchain_center
        assert "DEVICE PACK HANDOFF STOPPED" in (
            window.toolchain_center.device_pack_handoff_feedback.text()
        )
        assert "NO INSTALL, BUILD, OR PHONE ACTION STARTED" in (
            window.toolchain_center.device_pack_handoff_feedback.text()
        )
        window.toolchain_center._render()
        assert not window.toolchain_center.context_setup_button.isEnabled()
        assert "STALE CONTEXT" in window.toolchain_center.device_pack_handoff_badge.text()
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
