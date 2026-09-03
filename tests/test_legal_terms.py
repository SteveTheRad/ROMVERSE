from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtWidgets import QApplication

from romverse.legal import TERMS_STATUS, TERMS_VERSION, load_terms_document
from romverse.ui.main_window import AboutPage, TermsDialog


def test_packaged_terms_are_versioned_bounded_and_preserve_legal_rights() -> None:
    document = load_terms_document()
    normalized = document.text.casefold()

    assert document.document_id == "romverse-terms-and-conditions"
    assert document.version == TERMS_VERSION == "draft-2026-09-04"
    assert document.status == TERMS_STATUS
    assert re.fullmatch(r"[0-9a-f]{64}", document.sha256)
    assert "misuse and unsupported changes" in normalized
    assert "wrong-device target" in normalized
    assert "a general “use at your own risk” statement is not a substitute" in normalized
    assert "australian consumer law" in normalized
    assert "cannot be signed away" in normalized
    assert "final monetary caps" in normalized
    assert "require professional legal review" in normalized


def test_about_opens_complete_terms_draft_without_recording_acceptance(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    icon = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    page = AboutPage(icon, app_icon_path=icon, workspace=tmp_path)
    page.show()
    page.terms_button.click()
    app.processEvents()

    assert isinstance(page.terms_dialog, TermsDialog)
    assert page.terms_dialog.isVisible()
    assert "ROMVERSE Terms & Conditions" in page.terms_dialog.content.toPlainText()
    assert "not authorise a device-changing operation" in (page.terms_dialog.content.toPlainText())
    assert "DRAFT TERMS • LEGAL REVIEW REQUIRED" in page.legal_state.text()
    assert not any("accept" in path.name.casefold() for path in tmp_path.rglob("*"))
    page.terms_dialog.close()
    page.close()
