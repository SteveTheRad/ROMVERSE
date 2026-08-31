from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolButton,
    QWidget,
)

from romverse.device.models import AndroidDevice, DeviceState, StorageInfo
from romverse.ui.device_center import DeviceCenter
from romverse.ui.main_window import AboutPage, ThanksPortal
from romverse.ui.origin_story import ORIGIN_SCENES, origin_total_duration_ms


def test_connected_dashboard_builds_all_reference_quick_actions(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = DeviceCenter(tmp_path)
    center.set_devices(
        [
            AndroidDevice(
                serial="device-1",
                state=DeviceState.DEVICE,
                manufacturer="Xiaomi",
                model="Test Phone",
                codename="test",
                android_version="17",
                battery_percent=78,
                battery_temperature_c=36.0,
                storage=StorageInfo(512, 209, 303, 41),
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
    assert [button.text() for button in actions] == [
        "ROM Forge",
        "Command Console",
        "App Cleanse",
        "Quantum Tune",
        "Module Forge",
        "Time Snapshot",
        "Time Restore",
    ]
    assert all(not button.icon().isNull() for button in actions)
    labels = [label.text() for label in center.findChildren(QLabel)]
    assert "Device scan completed" in labels
    assert "Guardian verification active" not in labels


def test_command_deck_scan_shows_honest_indeterminate_progress(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = DeviceCenter(tmp_path)
    center.show()

    center.set_scanning(True)
    app.processEvents()

    assert center.scan_progress.isVisible()
    assert center.scan_progress.minimum() == 0
    assert center.scan_progress.maximum() == 0
    assert not center.scan_progress.isTextVisible()

    center.set_scanning(False)
    app.processEvents()
    assert not center.scan_progress.isVisible()
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
    assert scroll is not None and scroll.widgetResizable()
    assert content is not None and content.maximumWidth() == 1120
    assert facebook_card is not None and facebook_card.minimumHeight() == 78
    assert reddit_card is not None and reddit_card.minimumHeight() == 78
    assert romverse_website_card is not None and romverse_website_card.minimumHeight() == 118
    assert radforge_website_card is not None and radforge_website_card.minimumHeight() == 118
    assert page.logo.width() == page.logo.height() == 224
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
