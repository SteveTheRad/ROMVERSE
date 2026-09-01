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

from romverse.device.models import AndroidDevice, DeviceState, MemoryInfo, StorageInfo
from romverse.rom.guided import GenesisFlightPlan, GuidedStageStatus
from romverse.ui.device_center import DeviceCenter, RingGauge, RomStudioDeviceContext
from romverse.ui.main_window import (
    AboutPage,
    AboutRuntimeEvidence,
    ThanksPortal,
    WebsiteBrandCrest,
)
from romverse.ui.mini_chart import MiniChart
from romverse.ui.origin_story import ORIGIN_SCENES, origin_total_duration_ms


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
    assert status_by_label["Pre-Build Simulation"] == "READY"
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
        app.processEvents()

    assert [call.args[0].toString() for call in open_url.call_args_list] == [
        "https://romverse.app/",
        "https://radforgelabs.com/",
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
    assert page.evidence_cards["device"].property("evidenceState") == "verified"
    assert page.evidence_cards["build"].property("evidenceState") == "attention"
    assert set(page.evidence_buttons) == {
        "device_atlas",
        "archives",
        "rom_studio",
        "forge_arsenal",
        "live_console",
    }

    page.evidence_buttons["device_atlas"].click()
    page.evidence_buttons["forge_arsenal"].click()
    page.evidence_buttons["live_console"].click()
    page.evidence_guide.click()
    app.processEvents()

    assert routes == ["device_atlas", "forge_arsenal", "live_console"]
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
