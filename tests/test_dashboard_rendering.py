from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolButton,
    QWidget,
)

from romverse.core.activity import ActivityStore
from romverse.device.models import AndroidDevice, DeviceState, MemoryInfo, StorageInfo
from romverse.knowledge.lookup import OfflineKnowledgeService
from romverse.nexus.events import LiveConsoleEventStore, MissionConfidence, MissionState
from romverse.rom.guided import GenesisFlightPlan, GuidedStageStatus
from romverse.ui.device_center import DeviceCenter, PhoneMockup, RingGauge, RomStudioDeviceContext
from romverse.ui.main_window import (
    AboutPage,
    AboutRuntimeEvidence,
    ThanksPortal,
    WebsiteBrandCrest,
)
from romverse.ui.mini_chart import MiniChart
from romverse.ui.origin_story import ORIGIN_SCENES, origin_total_duration_ms


def test_empty_command_deck_header_does_not_claim_a_live_device_or_project(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    center = DeviceCenter(tmp_path)

    assert center.deck_subtitle.text() == (
        "Current device, project, and evidence-derived next action at a glance."
    )
    assert "One live device" not in center.deck_subtitle.text()
    assert "one active project" not in center.deck_subtitle.text()

    center.close()


def test_connected_dashboard_builds_all_approved_contextual_mission_cards(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = DeviceCenter(tmp_path)
    center.set_workspace_context(
        "Project Orion",
        True,
        GenesisFlightPlan(
            project_name="Project Orion",
            stage_number=5,
            stage_total=15,
            stage_title="Confirm device identity and capabilities",
            status=GuidedStageStatus.ATTENTION,
            progress_percent=27,
            verified_stages=4,
            blockers=("A compatible Device Pack must identify the exact target.",),
            recommendation="Connect the target phone and refresh Device DNA.",
            action_label="Scan device & refresh DNA",
            root_route="Decision pending",
            recovery_ready=False,
            guardian_ready=False,
        ),
        prebuild_simulation_ready=True,
    )
    center.set_devices(
        [
            AndroidDevice(
                serial="device-1",
                state=DeviceState.DEVICE,
                manufacturer="Xiaomi",
                model="Test Phone",
                codename="test",
                android_version="17",
                abi="arm64-v8a",
                build_id="TEST.2026",
                security_patch="2026-08-01",
                battery_percent=78,
                battery_temperature_c=36.0,
                storage=StorageInfo(512, 209, 303, 41),
                memory=MemoryInfo(128, 64, 50),
                bootloader_locked=False,
                verified_boot="orange",
                root_detected=False,
                slot_suffix="_a",
                soc_platform="qcom-test",
                encryption_state="encrypted",
                ab_update=True,
                virtual_ab=True,
                uptime_seconds=9_000,
                connection_note="Connected over ADB",
            )
        ]
    )
    app.processEvents()
    actions = [
        button
        for button in center.findChildren(QToolButton)
        if button.objectName() == "QuickAction"
    ]
    assert [button.text().replace("&&", "&").splitlines()[0] for button in actions] == [
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
    ]
    status_by_label = {
        button.text().replace("&&", "&").splitlines()[0]: button.text().splitlines()[1]
        for button in actions
    }
    assert status_by_label["Health Review"] == "DEVICE READY"
    assert status_by_label["Repair Phone"] == "DEVICE READY"
    assert status_by_label["Pre-Build Simulation"] == "RUN CHECK"
    assert status_by_label["Guardian"] == "VERIFY REQUIRED"
    guardian = center.quick_action_buttons["Guardian"]
    assert guardian.property("guardianState") == "unverified"
    assert guardian.property("evidenceReady") is False
    assert "has not yet been verified" in guardian.toolTip()

    center.set_guardian_state(
        "verified",
        "SHA-256 audit chain verified across 12 operation records.",
        True,
    )

    assert guardian.text().splitlines()[1] == "INTEGRITY VERIFIED"
    assert guardian.property("guardianState") == "verified"
    assert guardian.property("evidenceReady") is True
    assert guardian.accessibleDescription() == (
        "SHA-256 audit chain verified across 12 operation records."
    )
    assert all(not button.icon().isNull() for button in actions)
    labels = [label.text() for label in center.findChildren(QLabel)]
    assert "SYSTEM HEALTH" not in labels
    assert "GENESIS FLIGHT PLAN" in labels
    assert "Confirm device identity and capabilities" in labels
    assert "Project Orion" in labels
    assert "Device scan completed" in labels
    assert "Guardian verification active" not in labels
    assert "TELEMETRY & READINESS" in labels
    assert "Battery history" in labels
    assert "Thermal history" in labels
    assert "Connection history" in labels
    assert "Storage history" in labels
    evidence = next(gauge for gauge in center.findChildren(RingGauge) if gauge.label == "Evidence")
    assert evidence.value == 100
    assert evidence.detail == "12 of 12 signals"
    telemetry = center.findChild(QFrame, "TelemetryHistory")
    assert telemetry is not None
    assert len(telemetry.findChildren(MiniChart)) == 4
    assert any("Slot A • A/B • Virtual A/B" in label for label in labels)
    assert any("Bootloader Unlocked" in label for label in labels)
    gauges = center.findChildren(RingGauge)
    assert len(gauges) == 5
    assert sum(gauge.label == "Battery" for gauge in gauges) == 1
    assert sum(gauge.label == "Thermal" for gauge in gauges) == 1
    requested: list[str] = []
    center.action_requested.connect(requested.append)
    manage_storage = next(
        button for button in center.findChildren(QPushButton) if "Manage Storage" in button.text()
    )
    manage_storage.click()
    assert requested == ["Optimize"]


def test_command_deck_projects_one_exact_action_and_five_primary_mission_routes(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    missions = LiveConsoleEventStore(tmp_path)
    center = DeviceCenter(tmp_path, ActivityStore(tmp_path), missions)
    center.show()
    app.processEvents()

    assert not center.next_action_card.isHidden()
    assert tuple(center.primary_action_buttons) == (
        "Connect Device",
        "Start ROM Project",
        "Resume Mission",
        "Diagnose Problem",
        "Recover Device",
    )
    assert center._next_action_key == "Connect Device"
    assert center.primary_action_buttons["Connect Device"].property("recommended") is True
    assert not center.primary_action_buttons["Resume Mission"].isEnabled()
    assert center.primary_action_buttons["Diagnose Problem"].isEnabled()
    assert not center.primary_action_buttons["Recover Device"].isEnabled()

    refreshes: list[bool] = []
    center.refresh_requested.connect(lambda: refreshes.append(True))
    center.primary_action_buttons["Connect Device"].click()
    assert refreshes == [True]

    center.set_devices(
        [
            AndroidDevice(
                "private-device",
                DeviceState.DEVICE,
                manufacturer="RadForge",
                model="Reference Phone",
            )
        ]
    )
    assert center._next_action_key == "Start ROM Project"
    assert center.primary_action_buttons["Diagnose Problem"].isEnabled()
    assert center.primary_action_buttons["Recover Device"].isEnabled()

    center.set_workspace_context(
        "Project Aurora",
        True,
        GenesisFlightPlan(
            project_name="Project Aurora",
            stage_number=6,
            stage_total=15,
            stage_title="Review Device DNA",
            status=GuidedStageStatus.READY,
            progress_percent=33,
            verified_stages=5,
            blockers=(),
            recommendation="Confirm the exact capability map.",
            action_label="Review Device DNA",
            root_route="Unrooted build",
            recovery_ready=False,
            guardian_ready=False,
        ),
    )
    assert center._next_action_key == "Continue Genesis"
    assert center.next_button.text() == "Resume mission"
    assert "Project Aurora" in center.mission_context.text()
    assert center.primary_action_buttons["Resume Mission"].property("recommended") is True
    center.close()


def test_command_deck_live_progress_warnings_and_accomplishments_need_real_ledgers(
    tmp_path,
) -> None:
    _app = QApplication.instance() or QApplication([])
    activity = ActivityStore(tmp_path)
    missions = LiveConsoleEventStore(tmp_path)
    center = DeviceCenter(tmp_path, activity, missions)
    started = missions.start(
        source="ROM Studio",
        stage="build",
        title="Build verified candidate",
        summary="The source-bound build worker is running.",
        explanation="A real worker reported this state.",
        next_action="Keep ROMVERSE open.",
        project_id="project-1",
    )
    missions.progress(started.mission_id, 47)
    center.set_workspace_context("Project One", True, project_id="project-1")

    center.refresh_mission_control()

    assert center._next_action_key == "Live Operations"
    assert center.next_title.text() == "Build verified candidate"
    assert center.mission_progress.isVisibleTo(center)
    assert center.mission_progress.value() == 47
    assert center.mission_visual_state == "running"
    requested: list[str] = []
    center.action_requested.connect(requested.append)
    center.primary_action_buttons["Resume Mission"].click()
    assert requested == ["Resume Live Operations"]

    missions.finish(
        started.mission_id,
        MissionState.SUCCEEDED,
        summary="Candidate completed with producer evidence.",
        explanation="Completion came from the build service result.",
        next_action="Review its manifest.",
        confidence=MissionConfidence.VERIFIED,
    )
    activity.record(
        "rom-studio",
        "Firmware source inspected",
        "The producing service saved the inspection report.",
        outcome="success",
        source="ROM Studio",
    )
    center.refresh_activity()
    pulse = center.findChild(QFrame, "CommandDeckMissionPulse")
    labels = [label.text() for label in pulse.findChildren(QLabel)]

    assert not center.mission_progress.isVisibleTo(center)
    assert "GENUINE ACCOMPLISHMENTS • RECORDED OUTCOMES" in labels
    assert any("Build verified candidate" in label for label in labels)
    assert any("Firmware source inspected" in label for label in labels)
    assert not any("No verified completion" in label for label in labels)

    failed = missions.start(
        source="Recovery Autopilot",
        stage="reconnect-check",
        title="Verify Android reconnect",
        summary="Recovery verification is checking the exact target.",
        explanation="A real recovery checkpoint started.",
        next_action="Keep the target connected.",
    )
    missions.finish(
        failed.mission_id,
        MissionState.ATTENTION,
        summary="Android did not reconnect.",
        explanation="The expected boot proof was not observed.",
        next_action="Open Recovery Autopilot and review the next ranked route.",
        confidence=MissionConfidence.VERIFIED,
    )
    center.refresh_activity()
    pulse = center.findChild(QFrame, "CommandDeckMissionPulse")
    labels = [label.text() for label in pulse.findChildren(QLabel)]
    assert "URGENT WARNINGS" in labels
    assert any("Verify Android reconnect" in label for label in labels)
    assert center.mission_visual_state == "attention"
    center.close()


def test_command_deck_exposes_a_modified_live_ledger_without_guessing_state(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    missions = LiveConsoleEventStore(tmp_path)
    missions.path.parent.mkdir(parents=True)
    missions.path.write_text("{}", encoding="utf-8")

    center = DeviceCenter(tmp_path, ActivityStore(tmp_path), missions)

    assert "Live mission history needs attention" in center.next_note.text()
    assert center.mission_visual_state == "attention"
    pulse = center.findChild(QFrame, "CommandDeckMissionPulse")
    labels = [label.text() for label in pulse.findChildren(QLabel)]
    assert "LEDGER NEEDS ATTENTION" in labels
    assert not any(label == "RUNNING" for label in labels)
    center.close()


def test_command_deck_mission_pulse_keeps_a_warning_after_newer_information(
    tmp_path,
) -> None:
    QApplication.instance() or QApplication([])
    missions = LiveConsoleEventStore(tmp_path)
    warning = missions.note(
        source="Recovery Autopilot",
        stage="reconnect-check",
        title="Exact reconnect was not observed",
        summary="Recovery verification needs attention.",
        explanation="The expected current-device observation is absent.",
        next_action="Open Recovery Bay and review the existing incident.",
        state=MissionState.ATTENTION,
        confidence=MissionConfidence.VERIFIED,
    )
    newer_information = missions.note(
        source="Device Engine",
        stage="read-only-scan",
        title="Read-only catalog refresh recorded",
        summary="A newer informational event was retained.",
        explanation="Information must not conceal the existing warning.",
        next_action="No action is required for this information.",
        state=MissionState.INFORMATION,
    )
    center = DeviceCenter(tmp_path, ActivityStore(tmp_path), missions)

    pulse = center.findChild(QFrame, "CommandDeckMissionPulse")
    labels = [label.text() for label in pulse.findChildren(QLabel)]

    assert missions.list_recent()[:2] == (newer_information, warning)
    assert "URGENT WARNINGS" in labels
    assert any(warning.title in label for label in labels)
    assert not any("No unresolved warning" in label for label in labels)
    center.close()


def test_command_deck_repair_card_reflects_exact_diagnostic_context(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    center = DeviceCenter(tmp_path)
    center.set_devices(
        [
            AndroidDevice(
                serial="device-1",
                state=DeviceState.DEVICE,
                manufacturer="RadForge",
                model="Reference Phone",
                battery_percent=75,
                storage=StorageInfo(percent_used=98),
            )
        ]
    )

    center.set_repair_context("storage.capacity", "Device storage is nearly full")
    repair = center.quick_action_buttons["Repair Phone"]

    assert repair.text().splitlines()[1] == "STORAGE PLAN READY"
    assert repair.property("diagnosticFinding") == "storage.capacity"
    assert repair.property("evidenceReady") is True
    assert "Device storage is nearly full" in repair.toolTip()
    assert repair.accessibleDescription() == "Device storage is nearly full"

    center.set_repair_context()
    repair = center.quick_action_buttons["Repair Phone"]
    assert repair.text().splitlines()[1] == "DEVICE READY"
    assert not repair.property("diagnosticFinding")
    center.close()


def test_command_deck_shows_compact_automatic_offline_brain_match(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = DeviceCenter(tmp_path)
    device = AndroidDevice(
        "private-s24-serial",
        DeviceState.DEVICE,
        manufacturer="Samsung",
        brand="samsung",
        model="SM-S928B",
        marketing_name="Galaxy S24 Ultra",
        product="e3q",
        codename="e3q",
        android_version="16",
        bootloader_locked=True,
        verified_boot="green",
        ab_update=True,
        virtual_ab=True,
        dynamic_partitions=True,
    )
    center.set_devices([device])
    report = OfflineKnowledgeService(tmp_path).scan_after_device_snapshot(device, limit=5)
    requested: list[str] = []
    center.knowledge_requested.connect(requested.append)

    center.set_knowledge_lookup(device.serial, report)
    app.processEvents()

    strip = center.findChild(QFrame, "KnowledgeBrainStrip")
    assert strip is not None
    labels = [label.text() for label in strip.findChildren(QLabel)]
    assert "OFFLINE ARCHIVES BRAIN  •  AUTOMATIC PRIVATE MATCH" in labels
    assert report.matches[0].record.title in labels
    assert "NOTHING UPLOADED  •  AUTHORITY: NONE" in labels
    assert not any(report.matches[1].record.summary in label for label in labels)
    button = strip.findChild(QPushButton, "KnowledgeBrainAction")
    assert button is not None
    button.click()
    assert requested == [report.matches[0].record.title]
    center.close()


def test_command_deck_stacks_without_horizontal_overflow_at_compact_width(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = DeviceCenter(tmp_path)
    center.resize(780, 650)
    device = AndroidDevice(
        "private-serial",
        DeviceState.DEVICE,
        manufacturer="Samsung",
        model="SM-S928B",
        marketing_name="Galaxy S24 Ultra",
        codename="e3q",
        android_version="16",
    )
    center.set_devices([device])
    report = OfflineKnowledgeService(tmp_path).scan_after_device_snapshot(device, limit=5)
    center.set_knowledge_lookup(device.serial, report)
    center.show()
    app.processEvents()

    assert center._compact_layout
    assert center.body.horizontalScrollBar().maximum() == 0
    illustration = center.findChild(PhoneMockup)
    assert illustration is not None
    assert illustration.accessibleName() == "Brand-neutral Android device illustration"
    center.close()


def test_command_deck_telemetry_keeps_unknown_readings_explicit(tmp_path) -> None:
    _app = QApplication.instance() or QApplication([])
    center = DeviceCenter(tmp_path)

    labels = [label.text() for label in center.findChildren(QLabel)]
    gauges = {gauge.label: gauge for gauge in center.findChildren(RingGauge)}

    assert "TELEMETRY & READINESS" in labels
    assert gauges["Device link"].value is None
    assert gauges["Device evidence"].value is None
    assert gauges["Guardian policy"].value == 100
    assert gauges["Guardian policy"].detail == "Always enforced"
    assert "UNCONFIRMED" in labels
    assert "No scans recorded" in labels
    telemetry = center.findChild(QFrame, "TelemetryHistory")
    assert telemetry is not None
    assert len(telemetry.findChildren(MiniChart)) == 4
    center.close()


def test_command_deck_turns_fastboot_identity_into_a_safe_device_atlas_handoff(
    tmp_path,
) -> None:
    QApplication.instance() or QApplication([])
    center = DeviceCenter(tmp_path)
    requested: list[str] = []
    center.action_requested.connect(requested.append)

    center.set_devices(
        [
            AndroidDevice(
                "boot-serial",
                DeviceState.BOOTLOADER,
                transport="usb-fastboot",
                model="popsicle",
                product="popsicle",
                codename="popsicle",
                slot_suffix="_a",
                bootloader_locked=False,
                fastboot_capability="Observed bootloader fastboot transport",
                connection_note="Connected in bootloader fastboot mode; read-only identity only.",
            )
        ]
    )

    labels = [label.text() for label in center.findChildren(QLabel)]
    assert center.status_badge.text() == "BOOTLOADER • READ ONLY"
    assert "BOOTLOADER IDENTITY  •  GUARDIAN READ ONLY" in labels
    assert "popsicle" in labels
    assert "Unlocked" in labels
    assert center.next_button.text() == "Open Device Atlas"
    center.next_button.click()
    assert requested == ["Device DNA"]
    center.close()


def test_command_deck_scan_shows_honest_indeterminate_progress(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = DeviceCenter(tmp_path)
    center.show()
    app.processEvents()
    assert center.scan_status_row.isHidden()

    center.set_scanning(True)
    app.processEvents()

    assert not center.scan_status_row.isHidden()
    assert center.scan_status_row.height() == 34
    assert center.scan_status_label.text() == "DEVICE SCAN"
    assert center.scan_progress.isVisible()
    assert center.scan_progress.width() == 108
    assert center.scan_progress.minimum() == 0
    assert center.scan_progress.maximum() == 0
    assert not center.scan_progress.isTextVisible()

    center.set_scanning(False)
    app.processEvents()
    assert center.scan_status_row.isHidden()
    assert not center.scan_progress.isVisible()
    center.close()


def test_command_deck_keeps_exact_studio_project_through_device_refresh(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = DeviceCenter(tmp_path)
    context = RomStudioDeviceContext(
        project_id="exact-project-1234",
        project_name="Exact HyperOS Project",
        source_sha256="a" * 64,
        device_pack_id="xiaomi.popsicle.hyperos4.os4.0.0.23",
        expected_model="2509FPN0BC",
        expected_codename="popsicle",
        intent="ascension-refresh",
    )
    scans: list[bool] = []
    returned: list[tuple[str, str, str]] = []
    center.refresh_requested.connect(lambda: scans.append(True))
    center.rom_studio_requested.connect(lambda *values: returned.append(values))

    assert center.open_rom_studio_context(context)
    center.show()
    app.processEvents()
    assert center.studio_handoff.isVisibleTo(center)
    assert center.studio_handoff_badge.text() == "SCAN TARGET"
    assert context.project_id in center.studio_handoff_detail.text()
    assert context.source_sha256[:16] in center.studio_handoff_detail.text()
    center.studio_scan_button.click()
    assert scans == [True]

    center.set_devices(
        [
            AndroidDevice(
                "private-exact-target",
                DeviceState.DEVICE,
                manufacturer="Xiaomi",
                model=context.expected_model,
                product="popsicle_global",
                codename=context.expected_codename,
            )
        ]
    )
    app.processEvents()
    assert center.studio_handoff_badge.text() == "TARGET MATCH • READ ONLY"
    assert "EXACT TARGET PRESENT" in center.studio_handoff_detail.text()
    assert "NO REBOOT, UNLOCK, ROOT, BUILD, FLASH, WIPE, OR RELOCK ACTION STARTED" in (
        center.studio_handoff_detail.text()
    )
    center.studio_return_button.click()
    assert returned == [(context.project_id, context.source_sha256, context.intent)]
    center.close()


def test_command_deck_adb_error_offers_in_place_runtime_resolution(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = DeviceCenter(tmp_path)
    requested = []
    center.runtime_tools_requested.connect(lambda: requested.append(True))

    center.show_error("Verified Android Platform Tools are not active yet.")
    assert center._next_action_key == "Resolve Platform Tools"
    assert center.mission_visual_state == "attention"
    assert center.next_button.text() == "Resolve Platform Tools"
    button = next(
        item for item in center.findChildren(QPushButton) if item.text() == "Resolve Platform Tools"
    )
    button.click()
    app.processEvents()

    assert requested == [True]
    assert "Platform Tools" in center.device_note.text()
    assert "device-changing command" in next(
        label.text()
        for label in center.findChildren(QLabel)
        if "device-changing command" in label.text()
    )
    center.close()


def test_about_and_supporter_sequence_use_new_app_icon() -> None:
    app = QApplication.instance() or QApplication([])
    icon_path = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    page = AboutPage(icon_path, app_icon_path=icon_path)
    assert not page.logo.pixmap().isNull()

    dialog = ThanksPortal(icon_path)
    dialog.show()
    dialog._portal_timer.stop()
    dialog._progress = 0.995
    dialog._advance_portal()
    app.processEvents()

    assert dialog.portal.logo.cacheKey() != 0
    assert dialog.title_effect.opacity() == 1.0
    assert dialog.message_effect.opacity() == 1.0
    assert dialog.return_button.isEnabled()
    assert dialog.skip_button.isEnabled()
    assert dialog.sound_button.isEnabled()
    assert dialog.reduced_effects.isEnabled()
    assert dialog.pause_button.isEnabled()
    assert dialog.story_progress.maximum() == 1000
    assert dialog.message_scroll.widgetResizable()
    assert dialog.message_scroll.widget() is dialog.message
    assert dialog.comic_stage.objectName() == "OriginComicStage"
    assert dialog.issue_badge.text() == "ROMVERSE ORIGIN  •  THE LIVING CHRONICLE"
    assert dialog.portal.accessibleName() == "Illustrated ROMVERSE living chronicle"
    assert not dialog.portal.chronicle.isNull()
    assert dialog.portal.chronicle.width() >= 1600
    assert dialog.portal.chronicle.height() >= 900
    dialog._render_scene(2)
    assert dialog.chapter.text().startswith("PANEL 03")
    assert dialog.comic_burst.text() == "VERIFY!"
    assert dialog.portal.scene_index == 2
    dialog.portal.set_reduced_motion(False)
    dialog.portal.set_progress(1.0)
    dialog.portal.set_story_scene(0, 0.0)
    app.processEvents()
    beginning_frame = dialog.portal.grab().toImage()
    dialog.portal.set_story_scene(6, 0.5)
    app.processEvents()
    assert dialog.portal.grab().toImage() != beginning_frame
    dialog.portal.set_story_scene(2, 0.5)
    assert dialog.portal.scene_progress == 0.5
    dialog.portal.set_reduced_motion(True)
    assert dialog.portal.scene_progress == 0.0
    dialog.close()


def test_about_uses_the_full_website_logo_and_honours_reduced_motion() -> None:
    app = QApplication.instance() or QApplication([])
    assets = Path(__file__).parents[1] / "src/romverse/assets"
    page = AboutPage(
        assets / "romverse-mark.svg",
        brand_path=assets / "romverse-brand.png",
        app_icon_path=assets / "romverse-app-icon.png",
    )
    page.resize(1200, 900)
    page.show()
    app.processEvents()

    expected = WebsiteBrandCrest(assets / "romverse-brand.png")
    assert page.logo.pixmap().toImage() == expected.pixmap().toImage()
    assert page.logo.motion_running
    first_frame = page.logo.grab().toImage()
    page.logo._started -= WebsiteBrandCrest.FLOAT_SECONDS / 2
    page.logo.update()
    app.processEvents()
    assert page.logo.grab().toImage() != first_frame

    page.logo.set_reduced_motion(True)
    assert page.logo.reduced_motion
    assert not page.logo.motion_running
    reduced_frame = page.logo.grab().toImage()
    page.logo._started -= WebsiteBrandCrest.FLOAT_SECONDS / 2
    page.logo.update()
    app.processEvents()
    assert page.logo.grab().toImage() == reduced_frame
    page.logo.set_reduced_motion(False)
    assert page.logo.motion_running
    expected.close()
    page.close()


def test_origin_story_follows_the_approved_public_scene_contract() -> None:
    assert [scene.key for scene in ORIGIN_SCENES] == [
        "beginning",
        "vision",
        "promise",
        "founder",
        "community",
        "future",
        "finale",
    ]
    story = "\n".join(f"{scene.title}\n{scene.body}" for scene in ORIGIN_SCENES)
    assert "What if Android ROM development could be powerful without being intimidating?" in story
    assert "Never hide uncertainty behind a green tick." in story
    assert "ROMVERSE started as an idea I wanted to see exist." in story
    assert "Personal recognition appears only when genuine account evidence" in story
    assert "Your time, trust, patience, and belief are part of this universe." in story
    assert "From the bottom of my heart—thank you for stepping into the Verse." in story
    assert "Made for the people who refuse to stop tinkering." in story
    assert "27.08.2026" in story
    assert origin_total_duration_ms() >= 100_000


def test_origin_cinematic_ambience_is_packaged_for_both_apps() -> None:
    root = Path(__file__).parents[1]
    desktop = root / "src/romverse/assets/origin-ambient.wav"
    companion = root / "companion/app/src/main/res/raw/origin_ambient.wav"
    assert desktop.read_bytes().startswith(b"RIFF")
    assert desktop.read_bytes() == companion.read_bytes()


def test_about_page_uses_wide_responsive_grid_and_crisp_social_actions() -> None:
    app = QApplication.instance() or QApplication([])
    icon_path = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    page = AboutPage(icon_path, app_icon_path=icon_path)
    page.resize(1200, 900)
    page.show()
    app.processEvents()

    scroll = page.findChild(QScrollArea, "AboutScroll")
    content = page.findChild(QWidget, "AboutContent")
    facebook_card = page.findChild(QWidget, "FacebookCard")
    reddit_card = page.findChild(QWidget, "RedditCard")
    github_card = page.findChild(QWidget, "GitHubCard")
    founder_spotlight = page.findChild(QWidget, "FounderSpotlight")
    romverse_website_card = page.findChild(QWidget, "RomverseWebsiteCard")
    radforge_website_card = page.findChild(QWidget, "RadForgeWebsiteCard")
    radforge_studio_identity = page.findChild(QWidget, "RadForgeStudioIdentity")
    radforge_company_logo = page.findChild(QLabel, "RadForgeOfficialLogo")
    assert scroll is not None and scroll.widgetResizable()
    assert content is not None and content.maximumWidth() == 1120
    assert radforge_studio_identity is not None
    assert radforge_studio_identity.minimumHeight() == 360
    assert radforge_company_logo is page.radforge_company_logo
    assert radforge_company_logo.size().width() == 400
    assert radforge_company_logo.size().height() == 255
    assert not radforge_company_logo.pixmap().isNull()
    assert radforge_company_logo.accessibleName() == "Official RadForge Labs company logo"
    assert facebook_card is not None and facebook_card.minimumHeight() == 78
    assert reddit_card is not None and reddit_card.minimumHeight() == 78
    assert github_card is not None and github_card.minimumHeight() == 78
    assert founder_spotlight is page.founder_spotlight
    assert page.founder_title.wordWrap()
    assert romverse_website_card is not None and romverse_website_card.minimumHeight() == 118
    assert radforge_website_card is not None and radforge_website_card.minimumHeight() == 118
    assert page.logo.width() == page.logo.height() == 310
    assert page.logo.accessibleName() == "Official ROMVERSE website logo"
    assert page.logo.FLOAT_SECONDS == 6.2
    assert page.logo.ORBIT_SECONDS == 34.0
    assert page.logo.SCAN_SECONDS == 5.5
    assert not page.facebook_icon.pixmap().isNull()
    assert page.facebook_icon.accessibleName() == "Facebook"
    assert isinstance(page.facebook_link, QPushButton)
    assert page.facebook_link.minimumHeight() >= 42
    assert page.facebook_link.accessibleName() == "Open ROMVERSE on Facebook"
    assert not page.reddit_icon.pixmap().isNull()
    assert page.reddit_icon.accessibleName() == "Reddit"
    assert page.reddit_link.minimumHeight() >= 42
    assert page.reddit_link.accessibleName() == "Open ROMVERSE on Reddit"
    assert not page.github_icon.pixmap().isNull()
    assert page.github_icon.accessibleName() == "GitHub"
    assert page.github_link.minimumHeight() >= 42
    assert page.github_link.accessibleName() == ("Open the official ROMVERSE GitHub repository")
    assert not page.romverse_website_icon.pixmap().isNull()
    assert page.romverse_website_link.minimumHeight() >= 44
    assert page.romverse_website_link.accessibleName() == "Open the official ROMVERSE website"
    assert not page.radforge_website_icon.pixmap().isNull()
    assert page.radforge_website_link.minimumHeight() >= 44
    assert page.radforge_website_link.accessibleName() == "Open the official RadForge Labs website"
    assert set(page.family_buttons) == {
        "rom_studio",
        "guardian_core",
        "companion_link",
        "galaxy",
    }
    assert all(button.minimumHeight() >= 78 for button in page.family_buttons.values())
    assert page.origin_replay.isHidden()

    page.resize(800, 700)
    app.processEvents()
    assert radforge_studio_identity.minimumHeight() == 280
    assert page.logo.width() == page.logo.height() == 220
    assert page.brand_bridge.width() == 120
    assert radforge_company_logo.size().width() == 260
    assert radforge_company_logo.size().height() == 166
    page.close()


def test_about_uses_the_byte_exact_approved_radforge_company_logo() -> None:
    asset = (
        Path(__file__).parents[1]
        / "src/romverse/assets/radforge-labs-official-logo-transparent.png"
    )

    assert sha256(asset.read_bytes()).hexdigest() == (
        "d82ff146aab1f18474005d1a2d9ce0c3944467ae30ff7cb4fb3284387daa95cb"
    )


def test_about_official_website_actions_use_clean_approved_destinations() -> None:
    app = QApplication.instance() or QApplication([])
    icon_path = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    page = AboutPage(icon_path, app_icon_path=icon_path)

    with patch("romverse.ui.main_window.QDesktopServices.openUrl") as open_url:
        page.romverse_website_link.click()
        page.radforge_website_link.click()
        page.github_link.click()
        app.processEvents()

    assert [call.args[0].toString() for call in open_url.call_args_list] == [
        "https://romverse.app/",
        "https://radforgelabs.com/",
        "https://github.com/SteveTheRad/ROMVERSE",
    ]
    page.close()


def test_about_product_family_routes_and_external_failure_are_visible() -> None:
    app = QApplication.instance() or QApplication([])
    icon_path = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    page = AboutPage(icon_path, app_icon_path=icon_path)
    routes: list[str] = []
    page.route_requested.connect(routes.append)

    page.family_buttons["guardian_core"].click()
    with patch("romverse.ui.main_window.QDesktopServices.openUrl", return_value=False):
        page.romverse_website_link.click()
    app.processEvents()

    assert routes == ["guardian_core"]
    assert not page.external_status.isHidden()
    assert "Could not open ROMVERSE" in page.external_status.text()
    assert "No Desktop or device state changed" in page.external_status.text()
    page.close()


def test_about_runtime_evidence_is_explicit_and_routes_to_its_owning_features() -> None:
    app = QApplication.instance() or QApplication([])
    icon_path = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    page = AboutPage(icon_path, app_icon_path=icon_path)
    routes: list[str] = []
    articles: list[str] = []
    page.route_requested.connect(routes.append)
    page.knowledge_article_requested.connect(articles.append)

    page.set_runtime_evidence(
        AboutRuntimeEvidence(
            device_pack_count=21,
            device_pack_issue_count=0,
            catalog_valid=True,
            catalog_fresh=True,
            catalog_entry_count=12_345,
            catalog_reason="Official Android IDs are integrity checked",
            archive_guide_count=117,
            archive_known_fix_count=67,
            archive_category_count=10,
            project_count=3,
            tool_ready_count=17,
            tool_count=19,
            live_ledger_valid=True,
            live_event_count=200,
            live_active_count=38,
            guardian_state="verified",
            guardian_detail=("SHA-256 audit chain verified across current operation evidence"),
            guardian_verified=True,
        )
    )
    app.processEvents()

    assert page.runtime_scope.text() == (
        "READ-ONLY  •  CURRENT WORKSPACE  •  NO EXECUTION AUTHORITY"
    )
    assert page.evidence_values["device"].text() == ("21 DEVICE PACKS  •  12,345 OFFICIAL IDS")
    assert page.evidence_values["knowledge"].text() == ("117 VERIFIED GUIDES  •  67 KNOWN FIXES")
    assert page.evidence_values["build"].text() == ("3 LOCAL PROJECTS  •  17/19 HOST TOOLS READY")
    assert page.evidence_values["live"].text() == ("200 GENUINE EVENTS  •  38 ACTIVE")
    assert page.evidence_values["guardian"].text() == "AUDIT + APPROVAL EVIDENCE"
    assert page.evidence_states["guardian"].text() == "INTEGRITY VERIFIED"
    assert page.evidence_cards["guardian"].property("evidenceState") == "verified"
    assert page.evidence_cards["device"].property("evidenceState") == "verified"
    assert page.evidence_cards["build"].property("evidenceState") == "attention"
    assert set(page.evidence_buttons) == {
        "device_atlas",
        "archives",
        "rom_studio",
        "forge_arsenal",
        "live_console",
        "guardian_core",
    }

    page.evidence_buttons["guardian_core"].click()
    page.evidence_buttons["device_atlas"].click()
    page.evidence_buttons["forge_arsenal"].click()
    page.evidence_buttons["live_console"].click()
    page.evidence_guide.click()
    app.processEvents()

    assert routes == ["guardian_core", "device_atlas", "forge_arsenal", "live_console"]
    assert articles == ["about-live-evidence-unavailable"]
    page.close()


def test_about_runtime_evidence_rejects_untrusted_counts() -> None:
    with pytest.raises(ValueError, match="Rejected Live Console evidence"):
        AboutRuntimeEvidence(
            device_pack_count=0,
            device_pack_issue_count=0,
            catalog_valid=False,
            catalog_fresh=False,
            catalog_entry_count=0,
            catalog_reason="Unavailable",
            archive_guide_count=117,
            archive_known_fix_count=67,
            archive_category_count=10,
            project_count=0,
            tool_ready_count=0,
            tool_count=0,
            live_ledger_valid=False,
            live_event_count=1,
            live_active_count=0,
            guardian_state="unverified",
            guardian_detail="Guardian evidence has not been verified",
            guardian_verified=False,
        )

    with pytest.raises(ValueError, match="contradictory Guardian verification"):
        AboutRuntimeEvidence(
            device_pack_count=0,
            device_pack_issue_count=0,
            catalog_valid=False,
            catalog_fresh=False,
            catalog_entry_count=0,
            catalog_reason="Unavailable",
            archive_guide_count=137,
            archive_known_fix_count=87,
            archive_category_count=10,
            project_count=0,
            tool_ready_count=0,
            tool_count=0,
            live_ledger_valid=True,
            live_event_count=0,
            live_active_count=0,
            guardian_state="verified",
            guardian_detail="No full verification was performed",
            guardian_verified=False,
        )


def test_about_origin_discovery_persists_and_enables_replay(tmp_path) -> None:
    _app = QApplication.instance() or QApplication([])
    icon_path = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    page = AboutPage(icon_path, app_icon_path=icon_path, workspace=tmp_path)
    requests: list[bool] = []
    page.logo_double_clicked.connect(lambda: requests.append(True))

    page._request_origin()

    assert requests == [True]
    assert page.origin_discovered
    state = json.loads(
        (tmp_path / "about" / "origin-discovery.romverse").read_text(encoding="utf-8")
    )
    assert state == {
        "award": "beyond-the-verse",
        "discovered": True,
        "format": "romverse.about.origin",
        "schema_version": 1,
    }
    page.close()

    reopened = AboutPage(icon_path, app_icon_path=icon_path, workspace=tmp_path)
    assert reopened.origin_discovered
    assert not reopened.origin_replay.isHidden()
    reopened.close()


def test_device_snapshot_exports_string_verified_boot_without_crashing(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    destination = tmp_path / "device-snapshot.json"
    center = DeviceCenter(tmp_path)
    center.set_devices(
        [
            AndroidDevice(
                serial="private-serial",
                state=DeviceState.DEVICE,
                manufacturer="Sony",
                model="Test Phone",
                verified_boot="green",
            )
        ]
    )

    with patch(
        "romverse.ui.device_center.QFileDialog.getSaveFileName",
        return_value=(str(destination), "JSON (*.json)"),
    ):
        center._export_snapshot()
    app.processEvents()

    exported = json.loads(destination.read_text(encoding="utf-8"))
    assert exported["verified_boot"] == "green"
    assert "private-serial" not in destination.read_text(encoding="utf-8")
    center.close()
