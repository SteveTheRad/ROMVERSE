from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from romverse.ui.knowledge_center import KnowledgeCenter, KnowledgeGuideDialog


def test_archives_search_selects_a_verified_guide_and_routes_to_rom_studio() -> None:
    app = QApplication.instance() or QApplication([])
    center = KnowledgeCenter()
    routes: list[str] = []
    center.route_requested.connect(routes.append)

    center.search.setText("firmware source")
    app.processEvents()
    assert "guide" in center.search_status.text().casefold()
    assert "payload.bin" in center.detail.toPlainText().casefold()
    assert center.open_route.isVisibleTo(center)
    center.open_route.click()
    assert routes == ["rom_studio"]
    center.close()


def test_archives_never_leaves_stale_advice_when_search_has_no_match() -> None:
    app = QApplication.instance() or QApplication([])
    center = KnowledgeCenter()
    center.search.setText("definitely-not-a-real-romverse-topic")
    app.processEvents()

    assert "no verified guide matched" in center.search_status.text().casefold()
    assert "will not invent a fix" in center.detail.toPlainText().casefold()
    assert not center.open_route.isVisible()
    center.close()


def test_archives_accepts_a_bounded_contextual_query_from_guided_workflows() -> None:
    app = QApplication.instance() or QApplication([])
    center = KnowledgeCenter()
    center.show()

    center.open_query("  Incremental debloat safety  ")
    app.processEvents()

    assert center.search.text() == "Incremental debloat safety"
    assert "dependency failures" in center.detail.toPlainText()
    assert center.search.hasFocus()
    center.close()


def test_archives_resolves_each_ascension_stage_to_one_authoritative_guide() -> None:
    app = QApplication.instance() or QApplication([])
    center = KnowledgeCenter()
    center.show()

    center.open_query("Ascension stage 4")
    app.processEvents()

    assert "1 verified guide found" in center.search_status.text()
    assert "Guardian review" in center.detail.toPlainText()
    assert "relocking is always prohibited" in center.detail.toPlainText()
    assert center.open_route.property("route") == "rom_studio"
    center.close()


def test_focused_recipe_guide_uses_the_authoritative_archives_article() -> None:
    QApplication.instance() or QApplication([])
    guide = KnowledgeGuideDialog(
        "Recipe Forger stage 3",
        "Stage 3 of 6  •  Target",
    )

    assert guide.match_count == 1
    assert guide.article_title == "Recipe Forger beginner journey"
    assert "protected firmware and connected phone can never be targets" in guide.article_body
    labels = "\n".join(label.text() for label in guide.findChildren(QLabel))
    assert "Guardian authority stays locked" in labels
    guide.close()
