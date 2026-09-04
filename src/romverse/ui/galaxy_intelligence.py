from __future__ import annotations

import html
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from romverse.device.models import AndroidDevice
from romverse.galaxy.intelligence import (
    GalaxyContribution,
    GalaxyContributionDraft,
    GalaxyContributionKind,
    GalaxyContributionPreview,
    GalaxyEvidenceClass,
    GalaxyIntelligenceDashboard,
    GalaxyIntelligenceError,
    GalaxyIntelligenceService,
    GalaxyModerationService,
    GalaxyOutcome,
)


class GalaxyConstellation(QWidget):
    """Data-backed visual language for Galaxy evidence and device families."""

    _POINTS = (
        (0.05, 0.56),
        (0.14, 0.27),
        (0.24, 0.68),
        (0.34, 0.34),
        (0.44, 0.63),
        (0.54, 0.25),
        (0.64, 0.57),
        (0.73, 0.32),
        (0.82, 0.67),
        (0.91, 0.39),
    )
    _EDGES = (
        (0, 1),
        (0, 2),
        (1, 3),
        (2, 3),
        (2, 4),
        (3, 5),
        (4, 5),
        (4, 6),
        (5, 7),
        (6, 7),
        (6, 8),
        (7, 9),
        (8, 9),
    )

    def __init__(self, *, reduced_motion: bool = False) -> None:
        super().__init__()
        self._reduced_motion = bool(reduced_motion)
        self._phase = 0.0
        self._dashboard = GalaxyIntelligenceDashboard(0, 0, 0, 0, 0, 0, 0, 0, (), "")
        self.setAccessibleName("Galaxy verified contribution constellation")
        self.setMinimumHeight(128)
        self.setMaximumHeight(154)
        self._timer = QTimer(self)
        self._timer.setInterval(52)
        self._timer.timeout.connect(self._advance)

    def set_dashboard(self, dashboard: GalaxyIntelligenceDashboard) -> None:
        self._dashboard = dashboard
        self.setAccessibleDescription(
            f"{dashboard.official_records} official records, "
            f"{dashboard.verified_community} verified community contributions, "
            f"{dashboard.experimental} experimental, {dashboard.disputed} disputed, and "
            f"{dashboard.device_families} contributed device families."
        )
        self.update()

    def set_reduced_motion(self, enabled: bool) -> None:
        self._reduced_motion = bool(enabled)
        if self._reduced_motion:
            self._phase = 0.0
            self._timer.stop()
        elif self.isVisible():
            self._timer.start()
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._reduced_motion:
            self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(event)

    def _advance(self) -> None:
        self._phase = (self._phase + 0.032) % (math.tau * 4)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(1, 1, max(1, self.width() - 2), max(1, self.height() - 2))
        background = QLinearGradient(bounds.topLeft(), bounds.bottomRight())
        background.setColorAt(0.0, QColor(4, 10, 26, 247))
        background.setColorAt(0.48, QColor(19, 9, 46, 244))
        background.setColorAt(1.0, QColor(3, 28, 39, 247))
        painter.setPen(QPen(QColor(82, 102, 255, 105), 1.0))
        painter.setBrush(background)
        painter.drawRoundedRect(bounds, 17, 17)

        graph = bounds.adjusted(24, 18, -24, -36)
        points = tuple(
            QPointF(
                graph.left() + graph.width() * x,
                graph.top()
                + graph.height() * y
                + (0 if self._reduced_motion else math.sin(self._phase + index) * 2.0),
            )
            for index, (x, y) in enumerate(self._POINTS)
        )
        for index, (start, end) in enumerate(self._EDGES):
            alpha = (
                64
                if self._reduced_motion
                else 48 + int(36 * (1 + math.sin(self._phase * 1.5 + index)) / 2)
            )
            painter.setPen(QPen(QColor(64, 171, 255, alpha), 1.2))
            painter.drawLine(points[start], points[end])

        counts = (
            (self._dashboard.official_records, QColor("#39E7F4")),
            (self._dashboard.verified_community, QColor("#59F2B1")),
            (self._dashboard.experimental, QColor("#B768FF")),
            (self._dashboard.disputed + self._dashboard.rejected, QColor("#FFB14A")),
        )
        colors: list[QColor] = []
        for count, color in counts:
            colors.extend([color] * min(4, count))
        while len(colors) < len(points):
            colors.append(QColor("#52627F"))
        for index, point in enumerate(points):
            color = colors[index]
            pulse = 1.0 if self._reduced_motion else 1 + math.sin(self._phase * 1.8 + index) * 0.17
            radius = 4.0 * pulse
            halo = QColor(color)
            halo.setAlpha(48)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(point, radius + 5.5, radius + 5.5)
            painter.setBrush(color)
            painter.drawEllipse(point, radius, radius)

        painter.setPen(QColor("#AFC4E6"))
        painter.drawText(
            bounds.adjusted(18, 0, -18, -9),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
            f"{self._dashboard.device_families} DEVICE FAMILIES   •   "
            f"{self._dashboard.verified_community} VERIFIED COMMUNITY STARS",
        )
        painter.setPen(QColor("#FFB14A") if self._dashboard.unresolved else QColor("#59F2B1"))
        painter.drawText(
            bounds.adjusted(18, 0, -18, -9),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
            f"{self._dashboard.unresolved} UNRESOLVED   •   {self._dashboard.queued} REVIEW QUEUED",
        )


class GalaxyContributionPreviewDialog(QDialog):
    settings_requested = Signal()

    def __init__(
        self,
        service: GalaxyIntelligenceService,
        preview: GalaxyContributionPreview,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.preview = preview
        self.queued_contribution: GalaxyContribution | None = None
        self.setWindowTitle("ROMVERSE Galaxy • Privacy preview")
        self.setMinimumSize(820, 650)
        self.resize(920, 720)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        eyebrow = QLabel("GALAXY INTELLIGENCE  •  REVIEW BEFORE SHARING")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("Your privacy-cleared contribution")
        title.setObjectName("Title")
        copy = QLabel(
            "This is the exact structured record ROMVERSE can queue for moderation. Nothing is "
            "uploaded here, it grants no execution authority, and it cannot change the phone."
        )
        copy.setObjectName("Muted")
        copy.setWordWrap(True)
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(copy)

        self.review = QTextBrowser()
        self.review.setOpenExternalLinks(False)
        self.review.setHtml(self._preview_html(preview))
        layout.addWidget(self.review, 1)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setObjectName(
            "Good"
            if preview.eligible_for_queue and preview.upload_authority == "reviewed-export-only"
            else "Warning"
        )
        self.status.setText(self._status_text(preview))
        layout.addWidget(self.status)

        self.confirm = QCheckBox(
            "I reviewed this exact privacy preview and confirm it contains no personal information."
        )
        self.confirm.setEnabled(preview.eligible_for_queue)
        self.confirm.toggled.connect(self._update_queue_button)
        layout.addWidget(self.confirm)

        actions = QHBoxLayout()
        self.settings_button = QPushButton("Open privacy settings")
        self.settings_button.setVisible(preview.upload_authority == "disabled")
        self.settings_button.clicked.connect(self.settings_requested.emit)
        actions.addWidget(self.settings_button)
        actions.addStretch()
        cancel = QPushButton("Keep private")
        cancel.clicked.connect(self.reject)
        self.queue_button = QPushButton("Queue for signed review")
        self.queue_button.setObjectName("Primary")
        self.queue_button.clicked.connect(self._queue)
        actions.addWidget(cancel)
        actions.addWidget(self.queue_button)
        layout.addLayout(actions)
        self._update_queue_button()

    def _update_queue_button(self) -> None:
        self.queue_button.setEnabled(
            self.confirm.isChecked()
            and self.preview.eligible_for_queue
            and self.preview.upload_authority == "reviewed-export-only"
        )

    def _queue(self) -> None:
        try:
            self.queued_contribution = self.service.queue(
                self.preview,
                self.preview.preview_digest,
            )
        except GalaxyIntelligenceError as exc:
            self.status.setObjectName("Danger")
            self.status.setText(f"Contribution stopped safely: {exc}")
            _restyle(self.status)
            return
        self.accept()

    @staticmethod
    def _status_text(preview: GalaxyContributionPreview) -> str:
        if preview.upload_authority == "disabled":
            return "SHARING OPTED OUT  •  Preview only; enable contributions in Privacy settings."
        if not preview.eligible_for_queue:
            return "NOT ELIGIBLE  •  Resolve the warnings before this record can enter review."
        return "READY FOR LOCAL REVIEW QUEUE  •  Export is manual  •  NOT UPLOADED"

    @staticmethod
    def _preview_html(preview: GalaxyContributionPreview) -> str:
        pattern = preview.device_pattern
        rows = (
            ("Evidence lane", preview.evidence_class.value),
            ("Contribution", f"{preview.kind.value} / {preview.outcome.value}"),
            ("Device family", f"{pattern.manufacturer} {pattern.model}".strip() or "Unconfirmed"),
            ("Codename / product", f"{pattern.codename or '—'} / {pattern.product or '—'}"),
            ("Build / Android", f"{pattern.build_id or '—'} / {pattern.android_version or '—'}"),
            ("Region", pattern.region or "Not encoded in build ID"),
            ("Partition model", f"{pattern.slot_scheme} / dynamic {pattern.dynamic_partitions}"),
            ("Device Pack", pattern.pack_id or "Not supplied"),
            ("Pattern SHA-256", pattern.pattern_digest),
        )
        facts = "".join(
            "<tr><td style='color:#8FA4C6; padding:5px 12px 5px 0;'>"
            f"{html.escape(label)}</td><td style='color:#EAF2FF;'>{html.escape(value)}</td></tr>"
            for label, value in rows
        )
        warnings = "".join(f"<li>{html.escape(value)}</li>" for value in preview.warnings)
        excluded = "".join(
            f"<li>{html.escape(value)}</li>" for value in preview.excluded_private_fields
        )
        evidence = "".join(f"<li>{html.escape(value)}</li>" for value in preview.evidence_refs)
        return (
            "<div style='color:#DCE8FA;'>"
            f"<h2 style='color:#FFFFFF;'>{html.escape(preview.title)}</h2>"
            f"<p>{html.escape(preview.summary)}</p><table>{facts}</table>"
            "<h3 style='color:#40DFF3;'>Reviewable evidence</h3>"
            f"<ul>{evidence or '<li>None supplied</li>'}</ul>"
            "<h3 style='color:#59F2B1;'>Always excluded</h3>"
            f"<ul>{excluded}</ul>"
            + (f"<h3 style='color:#FFB14A;'>Warnings</h3><ul>{warnings}</ul>" if warnings else "")
            + "<p style='color:#899AB7;'>Preview SHA-256: "
            f"{html.escape(preview.preview_digest)}</p></div>"
        )


class GalaxyIntelligenceDialog(QDialog):
    archives_requested = Signal()
    settings_requested = Signal()
    archive_updated = Signal(object)

    def __init__(
        self,
        service: GalaxyIntelligenceService,
        devices: tuple[AndroidDevice, ...] = (),
        *,
        moderation_service: GalaxyModerationService | None = None,
        signed_updates_available: bool = False,
        reduced_motion: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.moderation_service = moderation_service
        self.signed_updates_available = bool(signed_updates_available)
        self.devices = devices
        self.contributions: tuple[GalaxyContribution, ...] = ()
        self.current_contribution_id = ""
        self.setWindowTitle("ROMVERSE Galaxy Intelligence")
        self.setMinimumSize(1040, 720)
        self.resize(1220, 820)

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(12)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        eyebrow = QLabel("ROMVERSE GALAXY  •  PRIVACY-RESPECTING FIELD INTELLIGENCE")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("Turn confirmed discoveries into safer offline knowledge")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Capture anonymised Device DNA patterns, detect duplicates and conflicts, and keep "
            "community claims separated until signed evidence moderation verifies them."
        )
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        heading.addWidget(eyebrow)
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading, 1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        header.addWidget(close_button)
        root.addLayout(header)

        self.constellation = GalaxyConstellation(reduced_motion=reduced_motion)
        root.addWidget(self.constellation)

        self.metric_labels: dict[str, QLabel] = {}
        metrics = QHBoxLayout()
        for key, label in (
            ("official", "OFFICIAL"),
            ("verified", "VERIFIED COMMUNITY"),
            ("experimental", "EXPERIMENTAL"),
            ("disputed", "DISPUTED"),
            ("unresolved", "UNRESOLVED"),
        ):
            card = QFrame()
            card.setObjectName("MetricCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 8, 12, 8)
            value = QLabel("0")
            value.setObjectName("MetricValue")
            caption = QLabel(label)
            caption.setObjectName("Muted")
            card_layout.addWidget(value)
            card_layout.addWidget(caption)
            self.metric_labels[key] = value
            metrics.addWidget(card, 1)
        root.addLayout(metrics)

        self.privacy_bar = QFrame()
        self.privacy_bar.setObjectName("DiagnosticHandoffBar")
        privacy_layout = QHBoxLayout(self.privacy_bar)
        privacy_layout.setContentsMargins(16, 10, 14, 10)
        self.privacy_state = QLabel()
        self.privacy_state.setWordWrap(True)
        privacy_layout.addWidget(self.privacy_state, 1)
        self.settings_button = QPushButton("Privacy settings")
        self.settings_button.clicked.connect(self.settings_requested.emit)
        privacy_layout.addWidget(self.settings_button)
        root.addWidget(self.privacy_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._contribution_panel())
        splitter.addWidget(self._review_panel())
        splitter.setSizes([510, 690])
        root.addWidget(splitter, 1)

        footer = QHBoxLayout()
        self.update_button = QPushButton("Open signed Synapse updates")
        if not self.signed_updates_available:
            self.update_button.setText("Signed updates · publisher key required")
        self.update_button.setToolTip(
            "Open the offline Synapse update chamber. Updates require an enrolled Ed25519 publisher key."
        )
        self.update_button.clicked.connect(self.archives_requested.emit)
        footer.addWidget(self.update_button)
        self.moderation_button = QPushButton("Import signed moderation")
        self.moderation_button.setEnabled(
            moderation_service is not None and moderation_service.configured
        )
        self.moderation_button.setToolTip(
            "Requires a production ROMVERSE Galaxy moderator public key. Unverified reports "
            "cannot promote themselves."
        )
        self.moderation_button.clicked.connect(self._import_moderation)
        footer.addWidget(self.moderation_button)
        footer.addStretch()
        self.status = QLabel()
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        root.addLayout(footer)
        self.refresh()

    def _contribution_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        panel = QFrame()
        panel.setObjectName("Card")
        form = QVBoxLayout(panel)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(8)
        heading = QLabel("CONTRIBUTE A TECHNICAL DISCOVERY")
        heading.setObjectName("SectionTitle")
        form.addWidget(heading)
        self.device_status = QLabel()
        self.device_status.setWordWrap(True)
        form.addWidget(self.device_status)

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        self.kind = QComboBox()
        for item in GalaxyContributionKind:
            self.kind.addItem(item.value.replace("-", " ").title(), item)
        self.outcome = QComboBox()
        for item in GalaxyOutcome:
            self.outcome.addItem(item.value.title(), item)
        grid.addWidget(QLabel("Contribution type"), 0, 0)
        grid.addWidget(self.kind, 0, 1)
        grid.addWidget(QLabel("Observed outcome"), 1, 0)
        grid.addWidget(self.outcome, 1, 1)
        form.addLayout(grid)

        self.title_input = QLineEdit()
        self.title_input.setMaxLength(160)
        self.title_input.setPlaceholderText("One precise, searchable finding")
        form.addWidget(QLabel("Title"))
        form.addWidget(self.title_input)
        self.summary_input = QPlainTextEdit()
        self.summary_input.setMaximumHeight(82)
        self.summary_input.setPlaceholderText(
            "What happened, in which exact context, and what changed?"
        )
        form.addWidget(QLabel("Evidence summary"))
        form.addWidget(self.summary_input)
        self.symptoms_input = QPlainTextEdit()
        self.symptoms_input.setMaximumHeight(72)
        self.symptoms_input.setPlaceholderText("One observed symptom per line")
        form.addWidget(QLabel("Symptoms / observations"))
        form.addWidget(self.symptoms_input)
        self.steps_input = QPlainTextEdit()
        self.steps_input.setMaximumHeight(82)
        self.steps_input.setPlaceholderText("One reproducible step per line; never paste secrets")
        form.addWidget(QLabel("Reproduction, fix, or recovery steps"))
        form.addWidget(self.steps_input)
        self.evidence_input = QPlainTextEdit()
        self.evidence_input.setMaximumHeight(72)
        self.evidence_input.setPlaceholderText(
            "One public HTTPS evidence page or sha256:<digest> per line"
        )
        form.addWidget(QLabel("Reviewable evidence"))
        form.addWidget(self.evidence_input)
        self.alias_input = QLineEdit("Local contributor")
        self.alias_input.setMaxLength(100)
        self.pack_input = QLineEdit()
        self.pack_input.setMaxLength(180)
        self.pack_input.setPlaceholderText("Optional exact Device Pack ID")
        form.addWidget(QLabel("Contributor alias (stored only as a salted pseudonym)"))
        form.addWidget(self.alias_input)
        form.addWidget(QLabel("Device Pack"))
        form.addWidget(self.pack_input)
        self.preview_button = QPushButton("Preview privacy-cleared contribution")
        self.preview_button.setObjectName("Primary")
        self.preview_button.clicked.connect(self._preview_contribution)
        form.addWidget(self.preview_button)
        scroll.setWidget(panel)
        return scroll

    def _review_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        controls = QHBoxLayout()
        heading = QLabel("LOCAL EVIDENCE LEDGER")
        heading.setObjectName("SectionTitle")
        controls.addWidget(heading)
        controls.addStretch()
        self.unresolved_only = QCheckBox("Unresolved only")
        self.unresolved_only.toggled.connect(self.refresh)
        controls.addWidget(self.unresolved_only)
        layout.addLayout(controls)
        self.contribution_list = QListWidget()
        self.contribution_list.setMinimumHeight(150)
        self.contribution_list.currentItemChanged.connect(self._select_contribution)
        layout.addWidget(self.contribution_list, 1)
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(False)
        self.detail.setMinimumHeight(180)
        layout.addWidget(self.detail, 1)
        actions = QHBoxLayout()
        self.export_button = QPushButton("Export reviewed submission")
        self.export_button.clicked.connect(self._export_selected)
        actions.addWidget(self.export_button)
        actions.addStretch()
        layout.addLayout(actions)
        return panel

    def set_devices(self, devices: tuple[AndroidDevice, ...]) -> None:
        self.devices = devices
        self._render_device()

    def set_sharing_enabled(self, enabled: bool) -> None:
        self.service.set_sharing_enabled(enabled)
        self._render_privacy()
        self._update_actions()

    def set_reduced_motion(self, enabled: bool) -> None:
        self.constellation.set_reduced_motion(enabled)

    def build_preview(self) -> GalaxyContributionPreview:
        if len(self.devices) != 1:
            raise GalaxyIntelligenceError(
                "Select exactly one connected Android device before creating Device DNA evidence"
            )
        return self.service.preview(
            GalaxyContributionDraft(
                GalaxyContributionKind(self.kind.currentData()),
                GalaxyOutcome(self.outcome.currentData()),
                self.title_input.text(),
                self.summary_input.toPlainText(),
                _lines(self.symptoms_input.toPlainText()),
                _lines(self.steps_input.toPlainText()),
                _lines(self.evidence_input.toPlainText()),
                self.alias_input.text(),
                self.pack_input.text(),
            ),
            self.devices[0],
        )

    def _preview_contribution(self) -> None:
        try:
            preview = self.build_preview()
        except GalaxyIntelligenceError as exc:
            self._set_status(str(exc), "Danger")
            return
        dialog = GalaxyContributionPreviewDialog(self.service, preview, self)
        dialog.settings_requested.connect(self.settings_requested.emit)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.queued_contribution is None:
            self._set_status(
                "Privacy preview closed; no contribution was queued or uploaded.", "Muted"
            )
            return
        self.current_contribution_id = dialog.queued_contribution.contribution_id
        self._set_status(
            "Privacy-reviewed contribution queued locally. Export remains manual; nothing was uploaded.",
            "Good",
        )
        self.refresh()

    def refresh(self, _value: object = None) -> None:
        try:
            dashboard = self.service.dashboard()
            contributions = (
                self.service.unresolved()
                if self.unresolved_only.isChecked()
                else self.service.load()
            )
        except GalaxyIntelligenceError as exc:
            self.contributions = ()
            self.contribution_list.clear()
            self._set_status(str(exc), "Danger")
            return
        self.contributions = contributions
        self.constellation.set_dashboard(dashboard)
        values = {
            "official": dashboard.official_records,
            "verified": dashboard.verified_community,
            "experimental": dashboard.experimental,
            "disputed": dashboard.disputed,
            "unresolved": dashboard.unresolved,
        }
        for key, value in values.items():
            self.metric_labels[key].setText(str(value))
        requested = self.current_contribution_id
        self.contribution_list.blockSignals(True)
        self.contribution_list.clear()
        selected_row = -1
        for row, contribution in enumerate(contributions):
            icon = {
                GalaxyEvidenceClass.VERIFIED_COMMUNITY: "✦",
                GalaxyEvidenceClass.EXPERIMENTAL: "◇",
                GalaxyEvidenceClass.DISPUTED: "!",
                GalaxyEvidenceClass.REJECTED: "×",
                GalaxyEvidenceClass.OFFICIAL: "★",
            }[contribution.evidence_class]
            item = QListWidgetItem(
                f"{icon}  {contribution.title}\n"
                f"{contribution.evidence_class.value.replace('-', ' ').upper()}  •  "
                f"{contribution.device_pattern.model or contribution.device_pattern.codename or 'Unknown family'}"
            )
            item.setData(Qt.ItemDataRole.UserRole, contribution.contribution_id)
            self.contribution_list.addItem(item)
            if contribution.contribution_id == requested:
                selected_row = row
        self.contribution_list.blockSignals(False)
        if contributions:
            self.contribution_list.setCurrentRow(selected_row if selected_row >= 0 else 0)
            self._render_contribution(contributions[self.contribution_list.currentRow()])
        else:
            self.current_contribution_id = ""
            self.detail.setHtml(
                "<div style='color:#8FA4C6; text-align:center; margin:35px;'>"
                "No matching contribution records yet.<br>New reports remain experimental until "
                "signed evidence moderation verifies them.</div>"
            )
        self._render_device()
        self._render_privacy()
        self._update_actions()

    def _select_contribution(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        contribution_id = str(current.data(Qt.ItemDataRole.UserRole))
        contribution = next(
            (item for item in self.contributions if item.contribution_id == contribution_id),
            None,
        )
        if contribution is not None:
            self._render_contribution(contribution)

    def _render_contribution(self, contribution: GalaxyContribution) -> None:
        self.current_contribution_id = contribution.contribution_id
        pattern = contribution.device_pattern
        evidence = "".join(f"<li>{html.escape(item)}</li>" for item in contribution.evidence_refs)
        steps = "".join(f"<li>{html.escape(item)}</li>" for item in contribution.solution_steps)
        conflicts = ", ".join(value[:12] + "…" for value in contribution.conflict_ids) or "None"
        self.detail.setHtml(
            "<div style='color:#DCE8FA;'>"
            f"<h2 style='color:#FFFFFF;'>{html.escape(contribution.title)}</h2>"
            f"<p>{html.escape(contribution.summary)}</p>"
            f"<p><b style='color:#40DFF3;'>CLASS</b> {contribution.evidence_class.value.upper()} &nbsp; "
            f"<b style='color:#40DFF3;'>OUTCOME</b> {contribution.outcome.value.upper()}</p>"
            f"<p><b>Scope:</b> {html.escape(pattern.manufacturer)} {html.escape(pattern.model)} / "
            f"{html.escape(pattern.codename)} / {html.escape(pattern.build_id)}</p>"
            f"<p><b>Conflicts:</b> {html.escape(conflicts)}<br>"
            f"<b>Corroboration:</b> {contribution.corroboration_count}<br>"
            f"<b>Moderation:</b> {html.escape(contribution.moderation_reason)}</p>"
            f"<h3 style='color:#59F2B1;'>Evidence</h3><ul>{evidence}</ul>"
            f"<h3 style='color:#B768FF;'>Steps</h3><ol>{steps or '<li>None recorded</li>'}</ol>"
            "<p style='color:#899AB7;'>Execution authority: NONE  •  Phone changed: NO  •  "
            f"Record SHA-256: {contribution.record_digest}</p></div>"
        )
        self._update_actions()

    def _render_device(self) -> None:
        if len(self.devices) == 1:
            device = self.devices[0]
            self.device_status.setObjectName("Good")
            self.device_status.setText(
                f"LIVE DNA READY  •  {device.display_name}  •  "
                f"{device.codename or 'codename unconfirmed'}  •  "
                f"{device.build_id or 'build unconfirmed'}  •  serial excluded"
            )
        elif self.devices:
            self.device_status.setObjectName("Warning")
            self.device_status.setText(
                "SELECT ONE DEVICE  •  Galaxy will not mix evidence from multiple connected phones."
            )
        else:
            self.device_status.setObjectName("Warning")
            self.device_status.setText(
                "NO SELECTED DEVICE  •  Connect and select one phone to bind a contribution to Device DNA."
            )
        _restyle(self.device_status)
        self.preview_button.setEnabled(len(self.devices) == 1)

    def _render_privacy(self) -> None:
        if self.service.sharing_enabled:
            self.privacy_state.setObjectName("Good")
            self.privacy_state.setText(
                "CONTRIBUTIONS OPTED IN  •  Serial, IMEI, accounts and personal data are excluded  •  "
                "Preview + explicit acceptance required  •  reviewed export only  •  no automatic upload"
            )
        else:
            self.privacy_state.setObjectName("Warning")
            self.privacy_state.setText(
                "CONTRIBUTIONS OPTED OUT  •  You may preview locally, but queue and export are disabled."
            )
        _restyle(self.privacy_state)

    def _update_actions(self) -> None:
        selected = next(
            (
                item
                for item in self.contributions
                if item.contribution_id == self.current_contribution_id
            ),
            None,
        )
        self.export_button.setEnabled(
            selected is not None and selected.queued_for_review and self.service.sharing_enabled
        )

    def _export_selected(self) -> None:
        selected = next(
            (
                item
                for item in self.contributions
                if item.contribution_id == self.current_contribution_id
            ),
            None,
        )
        if selected is None:
            return
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export reviewed Galaxy submission",
            str(Path.home() / f"romverse-galaxy-{selected.contribution_id[:12]}.json"),
            "ROMVERSE Galaxy reviewed submission (*.json)",
        )
        if not filename:
            return
        try:
            output = self.service.export_submission(selected, Path(filename))
        except GalaxyIntelligenceError as exc:
            self._set_status(str(exc), "Danger")
            return
        self._set_status(
            f"Reviewed submission exported to {output}. Nothing was uploaded.",
            "Good",
        )

    def _import_moderation(self) -> None:
        service = self.moderation_service
        if service is None or not service.configured:
            return
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Select signed Galaxy moderation bundle",
            "",
            "ROMVERSE signed Galaxy moderation (*.json *.romverse);;All files (*)",
        )
        if not filename:
            return
        try:
            preview = service.inspect(Path(filename))
        except GalaxyIntelligenceError as exc:
            self._set_status(f"Signed moderation rejected: {exc}", "Danger")
            return
        if (
            QMessageBox.question(
                self,
                "ROMVERSE Galaxy • Verified moderation",
                f"Moderator signature verified: {preview.signer_id}\n"
                f"Bundle: {preview.update_id}\n"
                f"Decisions: {len(preview.decisions)}\n"
                f"Envelope SHA-256: {preview.envelope_sha256}\n\n"
                "Apply these reviewed classifications? Verified-community records will join "
                "the offline Synapse archive. No network, command, flash, repair, or phone action runs.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            is not QMessageBox.StandardButton.Yes
        ):
            self._set_status("Signed moderation verified but not applied.", "Warning")
            return
        try:
            changed = service.apply(preview)
        except GalaxyIntelligenceError as exc:
            self._set_status(f"Signed moderation stopped safely: {exc}", "Danger")
            return
        self.current_contribution_id = changed[0].contribution_id if changed else ""
        self.refresh()
        self.archive_updated.emit(changed)
        self._set_status(
            f"Applied {len(changed)} signed moderation decision(s); verified findings are now "
            "available to the offline ROMVERSE brain.",
            "Good",
        )

    def _set_status(self, text: str, state: str) -> None:
        self.status.setText(text)
        self.status.setObjectName(state)
        _restyle(self.status)


def _lines(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(line.strip() for line in value.splitlines() if line.strip()))


def _restyle(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
