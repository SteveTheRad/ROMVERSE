from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

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
from romverse.ui.device_center import DeviceCenter, RingGauge
from romverse.ui.main_window import AboutPage, ThanksPortal, WebsiteBrandCrest
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
    assert status_by_label["Guardian"] == "SAFETY ACTIVE"
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
    _app = QApplication.instance() or QApplication([])
    icon_path = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    page = AboutPage(icon_path, app_icon_path=icon_path)

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
    assert radforge_studio_identity.minimumHeight() == 410
    assert radforge_company_logo is page.radforge_company_logo
    assert radforge_company_logo.size().width() == 520
    assert radforge_company_logo.size().height() == 332
    assert not radforge_company_logo.pixmap().isNull()
    assert radforge_company_logo.accessibleName() == "Official RadForge Labs company logo"
    assert facebook_card is not None and facebook_card.minimumHeight() == 78
    assert reddit_card is not None and reddit_card.minimumHeight() == 78
    assert romverse_website_card is not None and romverse_website_card.minimumHeight() == 118
    assert radforge_website_card is not None and radforge_website_card.minimumHeight() == 118
    assert page.logo.width() == page.logo.height() == 380
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
    assert page.origin_replay.isHidden()
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
