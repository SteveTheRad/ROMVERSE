from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from romverse.core.activity import ActivityStore
from romverse.galaxy.store import GalaxySort
from romverse.ui.galaxy_center import GalaxyCenter, NewTopicDialog
from romverse.ui.theme import STYLESHEET, apply_dark_palette


def test_galaxy_center_renders_and_updates_real_local_conversations(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = GalaxyCenter(tmp_path)
    post = center.store.create_post("ROM DNA findings", "Compare fingerprints before edits.")
    center.refresh(select_id=post.post_id)
    app.processEvents()

    assert center.topic_list.count() == 1
    assert "Integrity verified" in center.status.text()
    assert center.status.objectName() == "Good"
    assert center.current_post_id == post.post_id
    assert center.topic_title.text() == "ROM DNA findings"
    assert center.comment_button.isEnabled()

    center.comment_input.setPlainText("The protected baseline must remain immutable.")
    center._add_comment()
    center._vote(1)
    app.processEvents()
    stored = center.store.get(post.post_id)
    assert stored.score == 1
    assert stored.comments[0].body.startswith("The protected baseline")
    assert "1 replies" in center.topic_meta.text()

    center.search.setText("immutable")
    app.processEvents()
    assert center.topic_list.count() == 1
    center.search.setText("not present")
    app.processEvents()
    assert center.topic_list.count() == 0
    center.close()


def test_galaxy_opens_its_exact_local_privacy_guide_without_publishing(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = GalaxyCenter(tmp_path)
    requested: list[str] = []
    center.knowledge_article_requested.connect(requested.append)

    center.guide_button.click()

    assert requested == ["galaxy-local-publishing-boundary"]
    assert not center.store.path.exists()
    center.close()
    app.processEvents()


def test_galaxy_activity_records_and_reopens_the_exact_local_topic(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    activity = ActivityStore(tmp_path)
    center = GalaxyCenter(tmp_path, activity)
    post = center.store.create_post("Exact activity topic", "Keep this local evidence bound.")
    center.refresh(select_id=post.post_id)
    center.comment_input.setPlainText("Verified reply context.")
    center._add_comment()
    app.processEvents()

    event = activity.list_recent()[0]
    assert (event.source_route, event.context_type, event.context_id) == (
        "galaxy",
        "galaxy-topic",
        post.post_id,
    )

    other = center.store.create_post("Other topic", "Do not restore this one.")
    center.refresh(select_id=other.post_id)
    assert center.open_topic(event.context_id)
    assert center.current_post_id == post.post_id
    assert center.topic_title.text() == "Exact activity topic"
    assert "Nothing was published" in center.status.text()

    center.store.delete_post(post.post_id)
    assert not center.open_topic(post.post_id)
    center.close()


def test_galaxy_center_labels_legacy_data_without_overwriting_it(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = GalaxyCenter(tmp_path)
    center.store.create_post("Legacy evidence", "Keep old local topics readable.")
    payload = json.loads(center.store.path.read_text(encoding="utf-8"))
    payload.pop("integrity_version")
    payload.pop("community_digest")
    center.store.path.write_text(json.dumps(payload), encoding="utf-8")

    center.refresh()
    app.processEvents()

    assert center.topic_list.count() == 1
    assert "Legacy / unverified" in center.status.text()
    assert center.status.objectName() == "Warning"
    center.close()


def test_galaxy_center_exposes_clear_topic_ordering_without_mutating_posts(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = GalaxyCenter(tmp_path)
    first = center.store.create_post("First topic", "Active again later")
    second = center.store.create_post("Second topic", "Newest topic")
    center.store.add_comment(first.post_id, "Recent reply")
    center.store.set_vote(second.post_id, 1)

    center.ordering.setCurrentIndex(center.ordering.findData(GalaxySort.NEWEST))
    app.processEvents()
    assert [post.post_id for post in center.posts] == [second.post_id, first.post_id]

    center.ordering.setCurrentIndex(center.ordering.findData(GalaxySort.MOST_HELPFUL))
    app.processEvents()
    assert [post.post_id for post in center.posts] == [second.post_id, first.post_id]
    assert center.store.status().post_count == 2
    center.close()


def test_new_topic_dialog_recovers_private_local_draft(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = GalaxyCenter(tmp_path)
    dialog = NewTopicDialog(center.store)
    dialog.title_input.setText("Recovered ROM idea")
    dialog.body_input.setPlainText("Keep this evidence if the dialog closes.")
    dialog._persist_draft()
    dialog.reject()

    restored = NewTopicDialog(center.store)
    app.processEvents()

    assert restored.title_input.text() == "Recovered ROM idea"
    assert restored.body_input.toPlainText() == "Keep this evidence if the dialog closes."
    assert "restored" in restored.draft_status.text().casefold()
    restored.close()
    center.close()


def test_galaxy_editors_render_with_explicit_dark_theme_surfaces(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    previous_palette = QPalette(app.palette())
    previous_stylesheet = app.styleSheet()
    apply_dark_palette(app)
    app.setStyleSheet(STYLESHEET)
    center = GalaxyCenter(tmp_path)
    dialog = NewTopicDialog(center.store)
    center.resize(1000, 700)
    dialog.resize(620, 440)
    center.show()
    dialog.show()
    app.processEvents()

    center_image = center.comment_input.viewport().grab().toImage()
    dialog_image = dialog.body_input.viewport().grab().toImage()
    assert center_image.pixelColor(4, 4).lightness() < 40
    assert dialog_image.pixelColor(4, 4).lightness() < 40
    assert center.topic_body.palette().color(QPalette.ColorRole.Text).lightness() > 160
    dialog.close()
    center.close()
    app.setStyleSheet(previous_stylesheet)
    app.setPalette(previous_palette)
