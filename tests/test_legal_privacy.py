from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtWidgets import QApplication

from romverse.core.settings import AppSettings
from romverse.legal import PRIVACY_STATUS, PRIVACY_VERSION, load_privacy_document
from romverse.ui.main_window import AboutPage, PrivacyDialog


def test_packaged_privacy_notice_is_versioned_bounded_and_describes_real_flows() -> None:
    document = load_privacy_document()
    normalized = document.text.casefold()

    assert document.document_id == "romverse-privacy-notice"
    assert document.version == PRIVACY_VERSION == "draft-2026-09-04"
    assert document.status == PRIVACY_STATUS
    assert re.fullmatch(r"[0-9a-f]{64}", document.sha256)
    assert "local-first" in normalized
    assert "raw serial may exist briefly in memory" in normalized
    assert "synapse contribution is off by default" in normalized
    assert "automated technical decisions" in normalized
    assert "privacy act 1988" in normalized
    assert "starts no network request" in normalized
    assert "complete one-button inventory/export/delete workflow" in normalized


def test_about_privacy_view_shows_current_controls_without_changing_state(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    icon = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    marker = tmp_path / "existing-record.romverse"
    marker.write_text("unchanged", encoding="utf-8")
    settings = AppSettings(
        online_intelligence_enabled=False,
        community_research_enabled=False,
        auto_download_verified_tools=False,
        synapse_contributions_enabled=False,
    )
    page = AboutPage(
        icon,
        app_icon_path=icon,
        workspace=tmp_path,
        privacy_settings=settings,
    )
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    page.show()
    page.privacy_button.click()
    app.processEvents()

    assert isinstance(page.privacy_dialog, PrivacyDialog)
    assert page.privacy_dialog.isVisible()
    assert "ROMVERSE Privacy Notice" in page.privacy_dialog.content.toPlainText()
    assert page.privacy_dialog.document.sha256 in page.privacy_dialog.status.text()
    assert page.privacy_dialog.control_values["Device identifiers"].text() == (
        "MASKED + LOCAL PSEUDONYM"
    )
    assert page.privacy_dialog.control_values["Official online research"].text() == "LOCAL ONLY"
    assert page.privacy_dialog.control_values["Community research"].text() == "DISABLED"
    assert page.privacy_dialog.control_values["Synapse contribution"].text() == "OFF"
    assert page.privacy_dialog.control_values["Verified tool downloads"].text() == "ASK / MANUAL"
    assert "DRAFT TERMS + PRIVACY" in page.legal_state.text()
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before
    page.privacy_dialog.close()
    page.close()


def test_about_uses_new_settings_for_next_privacy_view(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    icon = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    page = AboutPage(icon, app_icon_path=icon, workspace=tmp_path)
    page.set_privacy_settings(
        AppSettings(
            online_intelligence_enabled=False,
            community_research_enabled=True,
        )
    )
    page.privacy_button.click()
    app.processEvents()

    assert page.privacy_dialog.control_values["Community research"].text() == (
        "PAUSED • LOCAL ONLY"
    )
    page.privacy_dialog.close()

    page.set_privacy_settings(
        AppSettings(
            online_intelligence_enabled=True,
            community_research_enabled=True,
            auto_download_verified_tools=True,
            synapse_contributions_enabled=True,
        )
    )
    page.privacy_button.click()
    app.processEvents()

    assert page.privacy_dialog.control_values["Official online research"].text() == "ENABLED"
    assert page.privacy_dialog.control_values["Community research"].text() == "ENABLED"
    assert page.privacy_dialog.control_values["Synapse contribution"].text() == (
        "OPTED IN • SERVICE UNAVAILABLE"
    )
    assert page.privacy_dialog.control_values["Verified tool downloads"].text() == "ENABLED"
    page.privacy_dialog.close()
    page.close()
