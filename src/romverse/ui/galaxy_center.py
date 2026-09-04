from __future__ import annotations

import html
import re
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from romverse.core.activity import ActivityStore, ActivityStoreError
from romverse.device.models import AndroidDevice
from romverse.galaxy.intelligence import (
    GalaxyIntelligenceService,
    GalaxyModerationService,
)
from romverse.galaxy.network import GalaxyNetworkService, GalaxyServiceTrust
from romverse.galaxy.store import (
    CommunityPost,
    GalaxyCommunityStore,
    GalaxySort,
    GalaxyStoreError,
)
from romverse.knowledge.updates import KnowledgeUpdateService
from romverse.ui.galaxy_intelligence import GalaxyIntelligenceDialog


class NewTopicDialog(QDialog):
    def __init__(
        self,
        store: GalaxyCommunityStore,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("ROMVERSE Galaxy • New local topic")
        self.setMinimumSize(620, 440)
        layout = QVBoxLayout(self)
        eyebrow = QLabel("COMMUNITY LAB  /  NEW LOCAL TOPIC")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("Start a conversation")
        title.setObjectName("Title")
        copy = QLabel(
            "This topic is saved only in your ROMVERSE workspace. It will not be published "
            "or synchronized until a future Galaxy account explicitly enables that action."
        )
        copy.setObjectName("Muted")
        copy.setWordWrap(True)
        self.title_input = QLineEdit()
        self.title_input.setMaxLength(GalaxyCommunityStore.MAX_TITLE)
        self.title_input.setPlaceholderText("A clear title for your ROM, device, or idea")
        self.body_input = QPlainTextEdit()
        self.body_input.setPlaceholderText(
            "Share the context, device, build, evidence, steps tried, and what you want to discuss…"
        )
        self.draft_status = QLabel("Drafts stay private in this ROMVERSE workspace.")
        self.draft_status.setObjectName("Muted")
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(copy)
        layout.addWidget(QLabel("Topic title"))
        layout.addWidget(self.title_input)
        layout.addWidget(QLabel("Message"))
        layout.addWidget(self.body_input, 1)
        layout.addWidget(self.draft_status)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Save local topic")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("Primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._draft_timer = QTimer(self)
        self._draft_timer.setSingleShot(True)
        self._draft_timer.setInterval(450)
        self._draft_timer.timeout.connect(self._persist_draft)
        try:
            draft = self.store.load_draft()
        except GalaxyStoreError as exc:
            self.draft_status.setText(str(exc) + "  •  existing draft was preserved")
            self.draft_status.setObjectName("Warning")
        else:
            if draft is not None:
                self.title_input.setText(draft.title)
                self.body_input.setPlainText(draft.body)
                self.draft_status.setText("Private local draft restored.")
                self.draft_status.setObjectName("Good")
        self.title_input.textChanged.connect(self._schedule_draft)
        self.body_input.textChanged.connect(self._schedule_draft)

    def _schedule_draft(self) -> None:
        self._draft_timer.start()

    def _persist_draft(self) -> None:
        try:
            draft = self.store.save_draft(
                self.title_input.text(),
                self.body_input.toPlainText(),
            )
        except GalaxyStoreError as exc:
            self.draft_status.setText(str(exc))
            self.draft_status.setObjectName("Warning")
        else:
            self.draft_status.setText(
                "Private local draft saved." if draft is not None else "Draft is empty."
            )
            self.draft_status.setObjectName("Good" if draft is not None else "Muted")
        self.draft_status.style().unpolish(self.draft_status)
        self.draft_status.style().polish(self.draft_status)

    def accept(self) -> None:
        self._draft_timer.stop()
        self._persist_draft()
        super().accept()

    def reject(self) -> None:
        self._draft_timer.stop()
        self._persist_draft()
        super().reject()


class GalaxyCenter(QWidget):
    """Real offline community workspace with no implied network synchronization."""

    knowledge_article_requested = Signal(str)
    route_requested = Signal(str)
    settings_requested = Signal()
    offline_archive_updated = Signal(object)

    def __init__(
        self,
        workspace: Path,
        activity_store: ActivityStore | None = None,
        *,
        knowledge_update_service: KnowledgeUpdateService | None = None,
        galaxy_trust: GalaxyServiceTrust | None = None,
        member_issuer: str = "",
        member_session_provider=None,
        contribution_opt_in: bool = False,
        reduced_motion: bool = False,
    ) -> None:
        super().__init__()
        self.store = GalaxyCommunityStore(workspace)
        self.intelligence = GalaxyIntelligenceService(
            workspace,
            sharing_enabled=contribution_opt_in,
        )
        resolved_trust = galaxy_trust or GalaxyServiceTrust(
            False,
            "The production Galaxy endpoint and public trust keys have not been enrolled yet.",
            "",
            "",
            (),
            (),
            (),
        )
        self.moderation = GalaxyModerationService(
            self.intelligence,
            resolved_trust.moderation_keys,
            unavailable_reason=resolved_trust.reason,
        )
        self.knowledge_update_service = knowledge_update_service
        self.network = GalaxyNetworkService(
            workspace,
            self.intelligence,
            resolved_trust,
            member_issuer=member_issuer,
            update_service=knowledge_update_service,
        )
        self.member_session_provider = member_session_provider or (lambda: None)
        self._devices: tuple[AndroidDevice, ...] = ()
        self._reduced_motion = bool(reduced_motion)
        self.intelligence_dialog: GalaxyIntelligenceDialog | None = None
        self.activity_store = activity_store
        self.posts: tuple[CommunityPost, ...] = ()
        self.current_post_id = ""

        page = QVBoxLayout(self)
        page.setContentsMargins(26, 22, 26, 24)
        page.setSpacing(14)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        eyebrow = QLabel("ROMVERSE GALAXY  •  COMMUNITY LAB")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("Your community starts here")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Create topics, record build discoveries, discuss troubleshooting, and shape ideas "
            "locally while the secure public Galaxy service is developed."
        )
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        heading.addWidget(eyebrow)
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading, 1)
        self.intelligence_button = QPushButton("✦  Galaxy Intelligence")
        self.intelligence_button.setObjectName("Primary")
        self.intelligence_button.setToolTip(
            "Open the opt-in Device DNA contribution, evidence review, and constellation chamber."
        )
        self.intelligence_button.clicked.connect(self._open_intelligence)
        header.addWidget(self.intelligence_button)
        self.new_button = QPushButton("＋  New topic")
        self.new_button.setToolTip("Create a private local Community Lab topic.")
        self.new_button.clicked.connect(self._new_topic)
        header.addWidget(self.new_button)
        page.addLayout(header)

        boundary = QFrame()
        boundary.setObjectName("HeroCard")
        boundary_layout = QHBoxLayout(boundary)
        boundary_layout.setContentsMargins(18, 13, 18, 13)
        self.network_badge = QLabel()
        self.network_explanation = QLabel(
            "Nothing here is public or synchronized. Future Galaxy accounts, moderation, "
            "privacy controls, and server security must pass review before online publishing unlocks."
        )
        self.network_explanation.setObjectName("Muted")
        self.network_explanation.setWordWrap(True)
        boundary_layout.addWidget(self.network_badge)
        boundary_layout.addSpacing(16)
        boundary_layout.addWidget(self.network_explanation, 1)
        self.guide_button = QPushButton("Privacy & publishing guide")
        self.guide_button.setToolTip(
            "Open the exact local Archives guide for Galaxy privacy, integrity, and publishing "
            "boundaries. This starts no upload or network action."
        )
        self.guide_button.clicked.connect(
            lambda: self.knowledge_article_requested.emit("galaxy-local-publishing-boundary")
        )
        boundary_layout.addWidget(self.guide_button)
        page.addWidget(boundary)

        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search local topics and comments…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        self.ordering = QComboBox()
        self.ordering.setToolTip(
            "Choose how local topics are ordered. This changes only the view, never the saved data."
        )
        self.ordering.addItem("Recently active", GalaxySort.RECENTLY_ACTIVE)
        self.ordering.addItem("Newest topics", GalaxySort.NEWEST)
        self.ordering.addItem("Most helpful", GalaxySort.MOST_HELPFUL)
        self.ordering.currentIndexChanged.connect(self.refresh)
        refresh_button = QPushButton("Refresh")
        refresh_button.setToolTip("Reload Community Lab data from the local workspace.")
        refresh_button.clicked.connect(self.refresh)
        tools.addWidget(self.search, 1)
        tools.addWidget(self.ordering)
        tools.addWidget(refresh_button)
        page.addLayout(tools)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.topic_list = QListWidget()
        self.topic_list.setMinimumWidth(310)
        self.topic_list.currentItemChanged.connect(self._select_topic)
        splitter.addWidget(self.topic_list)

        detail = QFrame()
        detail.setObjectName("Card")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(20, 18, 20, 18)
        detail_layout.setSpacing(10)
        self.topic_title = QLabel("No local topics yet")
        self.topic_title.setObjectName("HeroTitle")
        self.topic_title.setWordWrap(True)
        self.topic_meta = QLabel("Create the first real conversation in your Community Lab.")
        self.topic_meta.setObjectName("Muted")
        self.topic_body = QTextBrowser()
        self.topic_body.setOpenExternalLinks(False)
        self.topic_body.setMinimumHeight(150)
        self.topic_body.setStyleSheet(
            "background:#030711; color:#D8E3FA; border:1px solid #202E49; "
            "border-radius:10px; padding:10px;"
        )
        self.topic_body.setHtml(self._empty_html())
        detail_layout.addWidget(self.topic_title)
        detail_layout.addWidget(self.topic_meta)
        detail_layout.addWidget(self.topic_body, 2)

        actions = QHBoxLayout()
        self.upvote = QPushButton("△  Helpful")
        self.upvote.setToolTip("Add or remove your local helpful vote.")
        self.upvote.clicked.connect(lambda: self._vote(1))
        self.downvote = QPushButton("▽  Needs work")
        self.downvote.setToolTip("Add or remove your local needs-work vote.")
        self.downvote.clicked.connect(lambda: self._vote(-1))
        self.export_button = QPushButton("Export topic")
        self.export_button.setToolTip("Export this local topic as a portable JSON record.")
        self.export_button.clicked.connect(self._export_topic)
        self.delete_button = QPushButton("Delete local topic")
        self.delete_button.setToolTip("Permanently delete this topic from this workspace.")
        self.delete_button.clicked.connect(self._delete_topic)
        actions.addWidget(self.upvote)
        actions.addWidget(self.downvote)
        actions.addStretch()
        actions.addWidget(self.export_button)
        actions.addWidget(self.delete_button)
        detail_layout.addLayout(actions)

        comment_heading = QLabel("JOIN THE CONVERSATION")
        comment_heading.setObjectName("SectionTitle")
        self.comment_input = QPlainTextEdit()
        self.comment_input.setMaximumHeight(100)
        self.comment_input.setPlaceholderText("Add a local reply…")
        self.comment_button = QPushButton("Post local reply")
        self.comment_button.setObjectName("Primary")
        self.comment_button.setToolTip("Save a reply locally under this topic.")
        self.comment_button.clicked.connect(self._add_comment)
        detail_layout.addWidget(comment_heading)
        detail_layout.addWidget(self.comment_input)
        detail_layout.addWidget(self.comment_button, 0, Qt.AlignmentFlag.AlignRight)
        splitter.addWidget(detail)
        splitter.setSizes([360, 800])
        page.addWidget(splitter, 1)

        self.status = QLabel()
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        page.addWidget(self.status)
        self._set_detail_enabled(False)
        self._render_network_state()
        self.refresh()

    def set_devices(self, devices: list[AndroidDevice] | tuple[AndroidDevice, ...]) -> None:
        self._devices = tuple(devices)
        if self.intelligence_dialog is not None:
            self.intelligence_dialog.set_devices(self._devices)

    def set_contribution_opt_in(self, enabled: bool) -> None:
        self.intelligence.set_sharing_enabled(enabled)
        if self.intelligence_dialog is not None:
            self.intelligence_dialog.set_sharing_enabled(enabled)

    def set_reduced_motion(self, enabled: bool) -> None:
        self._reduced_motion = bool(enabled)
        if self.intelligence_dialog is not None:
            self.intelligence_dialog.set_reduced_motion(enabled)

    def set_member_issuer(self, issuer: str) -> None:
        self.network.set_member_issuer(issuer)
        self._render_network_state()

    def _render_network_state(self) -> None:
        if self.network.configured:
            self.network_badge.setObjectName("Good")
            self.network_badge.setText("✦  SIGNED GALAXY AVAILABLE")
            self.network_explanation.setText(
                "Public submission is opt-in and requires ROMVERSE Members sign-in, an exact "
                "payload review, and a signed server receipt. Local topics remain private."
            )
        else:
            self.network_badge.setObjectName("Warning")
            self.network_badge.setText("◆  OFFLINE LOCAL MODE")
            self.network_explanation.setText(
                f"Nothing here is public or synchronized. {self.network.status_reason} "
                "Local topics and manual reviewed exports remain available."
            )
        for widget in (self.network_badge, self.network_explanation):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _open_intelligence(self) -> None:
        dialog = GalaxyIntelligenceDialog(
            self.intelligence,
            self._devices,
            moderation_service=self.moderation,
            network_service=self.network,
            member_session_provider=self.member_session_provider,
            signed_updates_available=(
                self.knowledge_update_service is not None
                and self.knowledge_update_service.configured
            ),
            reduced_motion=self._reduced_motion,
            parent=self,
        )
        self.intelligence_dialog = dialog
        dialog.archives_requested.connect(self._leave_for_archives)
        dialog.settings_requested.connect(self._leave_for_settings)
        dialog.members_requested.connect(self._leave_for_members)
        dialog.archive_updated.connect(self.offline_archive_updated.emit)
        dialog.exec()
        if self.intelligence_dialog is dialog:
            self.intelligence_dialog = None
        self.refresh()

    def _leave_for_archives(self) -> None:
        if self.intelligence_dialog is not None:
            self.intelligence_dialog.accept()
        self.route_requested.emit("archives")

    def _leave_for_settings(self) -> None:
        if self.intelligence_dialog is not None:
            self.intelligence_dialog.accept()
        self.settings_requested.emit()

    def _leave_for_members(self) -> None:
        if self.intelligence_dialog is not None:
            self.intelligence_dialog.accept()
        self.route_requested.emit("members")

    def refresh(self, _value: str | None = None, select_id: str = "") -> None:
        requested = select_id or self.current_post_id
        try:
            order = self.ordering.currentData() or GalaxySort.RECENTLY_ACTIVE
            self.posts = self.store.list_posts(self.search.text(), GalaxySort(order))
            store_status = self.store.status()
        except GalaxyStoreError as exc:
            self.posts = ()
            self.topic_list.clear()
            self._show_error(str(exc))
            return
        self.topic_list.blockSignals(True)
        self.topic_list.clear()
        selected_row = -1
        for row, post in enumerate(self.posts):
            item = QListWidgetItem(
                f"{post.title}\n{post.author}  •  {len(post.comments)} replies  •  score {post.score:+d}"
            )
            item.setData(Qt.ItemDataRole.UserRole, post.post_id)
            item.setToolTip(post.body[:240])
            self.topic_list.addItem(item)
            if post.post_id == requested:
                selected_row = row
        self.topic_list.blockSignals(False)
        if self.posts:
            self.topic_list.setCurrentRow(selected_row if selected_row >= 0 else 0)
            self._render_post(self.posts[self.topic_list.currentRow()])
        else:
            self.current_post_id = ""
            self._render_empty(
                "No matching local topics" if self.search.text() else "No local topics yet"
            )
        count = len(self.posts)
        if store_status.exists and store_status.integrity_verified:
            integrity = f"Integrity verified  •  SHA-256 {store_status.digest[:12]}…"
            state = "Good"
        elif store_status.exists:
            integrity = "Legacy / unverified  •  next successful save upgrades integrity"
            state = "Warning"
        else:
            integrity = "No local community file saved yet"
            state = "Muted"
        self._set_status(
            f"{count} local topic{'s' if count != 1 else ''} visible  •  {integrity}  •  "
            f"Stored at {self.store.path}  •  Online publishing locked",
            state,
        )

    def _select_topic(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        post_id = str(current.data(Qt.ItemDataRole.UserRole))
        post = next((item for item in self.posts if item.post_id == post_id), None)
        if post is not None:
            self._render_post(post)

    def _render_post(self, post: CommunityPost) -> None:
        self.current_post_id = post.post_id
        self.topic_title.setText(post.title)
        self.topic_meta.setText(
            f"{post.author}  •  {_display_time(post.created_at)}  •  "
            f"{len(post.comments)} replies  •  local score {post.score:+d}"
        )
        sections = [
            f"<p style='font-size:14px; color:#E8EEFF;'>{_paragraphs(post.body)}</p>",
            "<hr style='border:0; border-top:1px solid #263452;'>",
            "<p style='color:#37DFF2; font-weight:700; letter-spacing:1px;'>LOCAL REPLIES</p>",
        ]
        if post.comments:
            for comment in post.comments:
                sections.append(
                    "<div style='margin:8px 0; padding:10px; background:#07101C; "
                    "border-left:3px solid #8D55FF;'>"
                    f"<b style='color:#D7B6FF;'>{html.escape(comment.author)}</b> "
                    f"<span style='color:#8391AE;'>• {_display_time(comment.created_at)}</span>"
                    f"<p style='color:#D8E3FA;'>{_paragraphs(comment.body)}</p></div>"
                )
        else:
            sections.append("<p style='color:#8391AE;'>No replies yet. Start the conversation.</p>")
        self.topic_body.setHtml("".join(sections))
        self.upvote.setText("▲  Helpful" if post.vote == 1 else "△  Helpful")
        self.downvote.setText("▼  Needs work" if post.vote == -1 else "▽  Needs work")
        self._set_detail_enabled(True)

    def _render_empty(self, title: str) -> None:
        self.topic_title.setText(title)
        self.topic_meta.setText(
            "Create a topic for build notes, troubleshooting evidence, Recipes, or ideas."
        )
        self.topic_body.setHtml(self._empty_html())
        self._set_detail_enabled(False)

    def _new_topic(self) -> None:
        dialog = NewTopicDialog(self.store, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            post = self.store.create_post(
                dialog.title_input.text(), dialog.body_input.toPlainText()
            )
        except GalaxyStoreError as exc:
            self._show_error(str(exc), modal=True)
            return
        draft_clear_error = ""
        try:
            self.store.clear_draft()
        except GalaxyStoreError as exc:
            draft_clear_error = str(exc)
        self.search.clear()
        self.refresh(select_id=post.post_id)
        verified = self.store.status()
        if draft_clear_error:
            self._set_status(
                "Topic saved and integrity verified, but the private draft could not be "
                f"cleared: {draft_clear_error}",
                "Warning",
            )
        else:
            self._set_status(
                "Local topic saved and integrity verified. Nothing was published or synchronized. "
                f"SHA-256 {verified.digest[:12]}…",
                "Good",
            )
        self._record_activity(
            "Local Galaxy topic created",
            "A private offline topic was saved; nothing was published or synchronized.",
            post.post_id,
        )

    def _add_comment(self) -> None:
        if not self.current_post_id:
            return
        try:
            post = self.store.add_comment(self.current_post_id, self.comment_input.toPlainText())
        except GalaxyStoreError as exc:
            self._show_error(str(exc), modal=True)
            return
        self.comment_input.clear()
        self.refresh(select_id=post.post_id)
        self._record_activity(
            "Local Galaxy reply added",
            "A private offline reply was saved; nothing was published or synchronized.",
            post.post_id,
        )

    def _vote(self, value: int) -> None:
        if not self.current_post_id:
            return
        current = next((post for post in self.posts if post.post_id == self.current_post_id), None)
        if current is None:
            return
        try:
            post = self.store.set_vote(current.post_id, 0 if current.vote == value else value)
        except GalaxyStoreError as exc:
            self._show_error(str(exc), modal=True)
            return
        self.refresh(select_id=post.post_id)

    def _delete_topic(self) -> None:
        if not self.current_post_id:
            return
        current = next((post for post in self.posts if post.post_id == self.current_post_id), None)
        if current is None:
            return
        if (
            QMessageBox.question(
                self,
                "Delete local Galaxy topic",
                f"Delete “{current.title}” and its {len(current.comments)} local replies?\n\n"
                "This cannot be undone unless you exported the topic.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.store.delete_post(current.post_id)
        except GalaxyStoreError as exc:
            self._show_error(str(exc), modal=True)
            return
        self.current_post_id = ""
        self.refresh()
        self._record_activity(
            "Local Galaxy topic deleted",
            "The selected offline topic and its replies were removed locally.",
        )

    def _export_topic(self) -> None:
        if not self.current_post_id:
            return
        current = next((post for post in self.posts if post.post_id == self.current_post_id), None)
        if current is None:
            return
        safe_name = "-".join(current.title.casefold().split())[:50] or "galaxy-topic"
        filename, _selected = QFileDialog.getSaveFileName(
            self,
            "Export local Galaxy topic",
            str(Path.home() / f"{safe_name}.romverse-galaxy.json"),
            "ROMVERSE Galaxy JSON (*.json)",
        )
        if not filename:
            return
        try:
            path = self.store.export_post(current.post_id, Path(filename))
        except GalaxyStoreError as exc:
            self._show_error(str(exc), modal=True)
            return
        self._set_status(f"Exported an integrity-bound local topic to {path}", "Good")

    def _set_detail_enabled(self, enabled: bool) -> None:
        for widget in (
            self.upvote,
            self.downvote,
            self.export_button,
            self.delete_button,
            self.comment_input,
            self.comment_button,
        ):
            widget.setEnabled(enabled)

    def open_topic(self, post_id: str) -> bool:
        """Reload and select one exact integrity-checked local Galaxy topic."""

        normalized = str(post_id).strip()[:80]
        try:
            post = self.store.get(normalized)
        except GalaxyStoreError:
            return False
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.refresh(select_id=post.post_id)
        if self.current_post_id != post.post_id:
            return False
        self._set_status(
            "Exact Activity Center topic restored from the integrity-checked local Galaxy store. "
            "Nothing was published or synchronized.",
            "Good",
        )
        return True

    def _show_error(self, message: str, modal: bool = False) -> None:
        self._set_status(message, "Danger")
        if modal:
            QMessageBox.warning(self, "ROMVERSE Galaxy", message)

    def _set_status(self, message: str, state: str) -> None:
        self.status.setObjectName(state)
        self.status.setText(message)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def _record_activity(self, title: str, detail: str, post_id: str = "") -> None:
        if self.activity_store is None:
            return
        exact_id = post_id if re.fullmatch(r"[0-9a-f]{32}", post_id) else ""
        with suppress(ActivityStoreError):
            self.activity_store.record(
                "community",
                title,
                detail,
                outcome="success",
                source="ROMVERSE Galaxy",
                source_route="galaxy" if exact_id else "",
                context_type="galaxy-topic" if exact_id else "",
                context_id=exact_id,
            )

    @staticmethod
    def _empty_html() -> str:
        return (
            "<div style='text-align:center; margin:35px; color:#8391AE;'>"
            "<p style='font-size:28px; color:#A85CFF;'>◎</p>"
            "<p>Your private Community Lab is ready.</p>"
            "<p>Begin locally. Publish deliberately when Galaxy goes online.</p></div>"
        )


def _paragraphs(value: str) -> str:
    return html.escape(value).replace("\n", "<br>")


def _display_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
        return parsed.strftime("%d %b %Y, %I:%M %p")
    except ValueError:
        return "Unknown time"
