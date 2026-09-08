"""Canonical Desktop surface for ROMVERSE's privacy-safe local activity ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from romverse.core.activity import ActivityEvent, ActivityStore, ActivityStoreError
from romverse.ui.vocabulary import canonical_source_route, feature


@dataclass(frozen=True, slots=True)
class ActivitySummary:
    total: int
    success: int
    attention: int
    information: int


def summarize_activity(events: tuple[ActivityEvent, ...]) -> ActivitySummary:
    """Compile truthful counts without promoting informational events to completion."""

    return ActivitySummary(
        total=len(events),
        success=sum(event.outcome == "success" for event in events),
        attention=sum(event.outcome == "attention" for event in events),
        information=sum(event.outcome == "information" for event in events),
    )


def filter_activity_events(
    events: tuple[ActivityEvent, ...],
    *,
    query: str = "",
    category: str = "",
    outcome: str = "",
) -> tuple[ActivityEvent, ...]:
    """Filter a bounded in-memory ledger view while retaining newest-first order."""

    normalized_query = " ".join(query.casefold().split())[:160]
    tokens = normalized_query.split()
    normalized_category = category.casefold().strip()
    normalized_outcome = outcome.casefold().strip()
    matches: list[ActivityEvent] = []
    for event in events:
        if normalized_category and event.category.casefold() != normalized_category:
            continue
        if normalized_outcome and event.outcome.casefold() != normalized_outcome:
            continue
        searchable = " ".join(
            (
                event.title,
                event.detail,
                event.source,
                event.category,
                event.outcome,
                event.context_id,
            )
        ).casefold()
        if tokens and not all(token in searchable for token in tokens):
            continue
        matches.append(event)
    return tuple(matches)


def activity_source_route(event: ActivityEvent) -> str:
    """Resolve a ledger event back to its canonical Desktop source page when known."""

    return event.source_route or canonical_source_route(event.source, event.category)


class ActivityCenter(QWidget):
    """Searchable, evidence-aware viewer for completed and attention outcomes."""

    route_requested = Signal(str)
    source_requested = Signal(str, str, str)

    def __init__(self, store: ActivityStore) -> None:
        super().__init__()
        self.store = store
        self.events: tuple[ActivityEvent, ...] = ()
        self.visible_events: tuple[ActivityEvent, ...] = ()
        self._load_error = ""

        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 30)
        page.setSpacing(16)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        eyebrow = QLabel("ACTIVITY CENTER  •  LOCAL AND REDACTED")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("Activity Center")
        title.setObjectName("Title")
        self.subtitle = QLabel(
            "Follow genuine ROMVERSE outcomes across connected Desktop features, then return to the source page for its full evidence."
        )
        self.subtitle.setObjectName("Muted")
        self.subtitle.setWordWrap(True)
        heading.addWidget(eyebrow)
        heading.addWidget(title)
        heading.addWidget(self.subtitle)
        header.addLayout(heading, 1)
        self.refresh_button = QPushButton("Refresh activity")
        self.refresh_button.setAccessibleName("Refresh the local ROMVERSE activity ledger")
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button)
        self.export_button = QPushButton("Export redacted JSON")
        self.export_button.setAccessibleName("Export the privacy-safe activity ledger")
        self.export_button.setToolTip(
            "At least one local activity event is required. The export remains privacy-redacted "
            "and does not include raw device identifiers."
        )
        self.export_button.clicked.connect(self._export)
        header.addWidget(self.export_button)
        page.addLayout(header)

        boundary = QFrame()
        boundary.setObjectName("HeroCard")
        boundary_layout = QHBoxLayout(boundary)
        boundary_layout.setContentsMargins(20, 15, 20, 15)
        self.ledger_status = QLabel("READY  •  Loading local activity")
        self.ledger_status.setObjectName("Good")
        self.boundary_copy = QLabel(
            "This ledger contains bounded privacy-safe summaries. It is not an approval record, raw console log, or execution authority."
        )
        self.boundary_copy.setObjectName("Muted")
        self.boundary_copy.setWordWrap(True)
        boundary_layout.addWidget(self.ledger_status)
        boundary_layout.addSpacing(16)
        boundary_layout.addWidget(self.boundary_copy, 1)
        page.addWidget(boundary)

        self.metrics_host = QWidget()
        metrics = QHBoxLayout(self.metrics_host)
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setSpacing(10)
        self.metric_values: dict[str, QLabel] = {}
        for key, label, color in (
            ("total", "RECORDED", "#EDF4FF"),
            ("success", "COMPLETED SAFELY", "#44E39A"),
            ("attention", "ATTENTION", "#FFB454"),
            ("information", "INFORMATION", "#35E7F5"),
        ):
            card = QFrame()
            card.setObjectName("TelemetryTile")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            metric_label = QLabel(label)
            metric_label.setObjectName("TelemetryLabel")
            value = QLabel("0")
            value.setObjectName("TelemetryValue")
            value.setStyleSheet(f"color:{color}; font-size:20px; font-weight:800;")
            value.setAccessibleName(f"{label.title()} activity count")
            card_layout.addWidget(metric_label)
            card_layout.addWidget(value)
            metrics.addWidget(card, 1)
            self.metric_values[key] = value
        page.addWidget(self.metrics_host)
        self.compact_summary = QLabel()
        self.compact_summary.setObjectName("Muted")
        self.compact_summary.setAccessibleName("Compact Activity Center outcome summary")
        self.compact_summary.setWordWrap(True)
        page.addWidget(self.compact_summary)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search outcomes, details, or source …")
        self.search.setClearButtonEnabled(True)
        self.search.setMaxLength(160)
        self.search.setAccessibleName("Search Activity Center")
        self.search.textChanged.connect(lambda _text: self._apply_filters())
        filters.addWidget(self.search, 2)
        self.outcome_filter = QComboBox()
        self.outcome_filter.setAccessibleName("Filter activity by outcome")
        self.outcome_filter.addItem("All outcomes", "")
        self.outcome_filter.addItem("Completed safely", "success")
        self.outcome_filter.addItem("Attention", "attention")
        self.outcome_filter.addItem("Information", "information")
        self.outcome_filter.currentIndexChanged.connect(lambda _index: self._apply_filters())
        filters.addWidget(self.outcome_filter, 1)
        self.category_filter = QComboBox()
        self.category_filter.setAccessibleName("Filter activity by category")
        self.category_filter.addItem("All categories", "")
        self.category_filter.currentIndexChanged.connect(lambda _index: self._apply_filters())
        filters.addWidget(self.category_filter, 1)
        page.addLayout(filters)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.activity_list = QListWidget()
        self.activity_list.setObjectName("HistoryList")
        self.activity_list.setAccessibleName("Filtered ROMVERSE activity")
        self.activity_list.setMinimumWidth(350)
        self.activity_list.currentRowChanged.connect(self._select)
        self.splitter.addWidget(self.activity_list)

        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setMinimumWidth(430)
        self.detail_content = QWidget()
        self.detail_content.setObjectName("ScrollContent")
        self.detail_layout = QVBoxLayout(self.detail_content)
        self.detail_layout.setContentsMargins(8, 0, 6, 0)
        self.detail_layout.setSpacing(12)
        self.detail_scroll.setWidget(self.detail_content)
        self.splitter.addWidget(self.detail_scroll)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setSizes([440, 680])
        page.addWidget(self.splitter, 1)

        self.footer = QLabel()
        self.footer.setObjectName("Muted")
        self.footer.setWordWrap(True)
        page.addWidget(self.footer)
        self.refresh()
        self._apply_responsive_layout()

    def refresh(self) -> None:
        selected_id = ""
        row = self.activity_list.currentRow()
        if 0 <= row < len(self.visible_events):
            selected_id = self.visible_events[row].event_id
        try:
            self.events = self.store.list_recent(self.store.MAX_EVENTS)
        except ActivityStoreError as exc:
            self.events = ()
            self.visible_events = ()
            self._load_error = str(exc)
            for value in self.metric_values.values():
                value.setText("0")
            self.compact_summary.setText(
                "ATTENTION  •  Activity unavailable; original data preserved"
            )
            self.export_button.setEnabled(False)
            self._set_status(f"ATTENTION  •  {exc}", "Danger")
            self._refresh_categories()
            self._apply_filters()
            return

        self._load_error = ""
        summary = summarize_activity(self.events)
        self.metric_values["total"].setText(str(summary.total))
        self.metric_values["success"].setText(str(summary.success))
        self.metric_values["attention"].setText(str(summary.attention))
        self.metric_values["information"].setText(str(summary.information))
        self.compact_summary.setText(
            f"{summary.total} recorded  •  {summary.success} completed safely  •  "
            f"{summary.attention} attention  •  {summary.information} information"
        )
        self.export_button.setEnabled(bool(self.events))
        if self.events:
            status = "ATTENTION" if summary.attention else "READY"
            style = "Warning" if summary.attention else "Good"
            self._set_status(f"{status}  •  {summary.total} local event(s) loaded", style)
        else:
            self._set_status("READY  •  No completed activity recorded yet", "Good")
        self._refresh_categories()
        self._apply_filters(selected_id)

    def _refresh_categories(self) -> None:
        selected = self.category_filter.currentData()
        categories = sorted({event.category for event in self.events}, key=str.casefold)
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("All categories", "")
        for category in categories:
            self.category_filter.addItem(category.replace("-", " ").title(), category)
        restored = self.category_filter.findData(selected)
        self.category_filter.setCurrentIndex(max(0, restored))
        self.category_filter.blockSignals(False)

    def _apply_filters(self, selected_id: str = "") -> None:
        self.visible_events = filter_activity_events(
            self.events,
            query=self.search.text(),
            category=str(self.category_filter.currentData() or ""),
            outcome=str(self.outcome_filter.currentData() or ""),
        )
        self.activity_list.blockSignals(True)
        self.activity_list.clear()
        selected_row = 0
        for index, event in enumerate(self.visible_events):
            marker = {"success": "✓", "attention": "!", "information": "◇"}[event.outcome]
            item = QListWidgetItem(
                f"{marker}  {event.title}\n{_display_time(event.recorded_at)}  •  {event.source}"
            )
            item.setData(Qt.ItemDataRole.UserRole, event.event_id)
            item.setData(
                Qt.ItemDataRole.AccessibleTextRole,
                f"{event.title}. {event.outcome}. {event.source}. {_display_time(event.recorded_at)}",
            )
            item.setToolTip(event.detail)
            self.activity_list.addItem(item)
            if event.event_id == selected_id:
                selected_row = index
        self.activity_list.blockSignals(False)
        self.footer.setText(
            f"Showing {len(self.visible_events)} of {len(self.events)} privacy-safe local events"
        )
        if self.visible_events:
            self.activity_list.setCurrentRow(selected_row)
            self._select(selected_row)
        else:
            self._render_empty(
                "No activity matches these filters. Adjust the search or filters; the underlying ledger is unchanged."
                if self.events
                else f"Activity is unavailable. The original ledger was preserved for review: {self._load_error}"
                if self._load_error
                else "No completed ROMVERSE activity is available yet. Connected features append only after a genuine completion or safe-failure boundary."
            )

    def _select(self, row: int) -> None:
        if not 0 <= row < len(self.visible_events):
            return
        self._render_event(self.visible_events[row])

    def _render_event(self, event: ActivityEvent) -> None:
        self._clear_detail()
        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(22, 18, 22, 18)
        top = QHBoxLayout()
        title = QLabel(event.title)
        title.setObjectName("HeroTitle")
        title.setWordWrap(True)
        status = QLabel(
            {
                "success": "COMPLETED SAFELY",
                "attention": "ATTENTION",
                "information": "INFORMATION",
            }[event.outcome]
        )
        status.setObjectName(
            {"success": "Good", "attention": "Warning", "information": "Eyebrow"}[event.outcome]
        )
        top.addWidget(title, 1)
        top.addWidget(status)
        hero_layout.addLayout(top)
        detail = QLabel(event.detail)
        detail.setObjectName("Muted")
        detail.setWordWrap(True)
        detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        hero_layout.addWidget(detail)
        self.detail_layout.addWidget(hero)

        evidence = QFrame()
        evidence.setObjectName("Card")
        evidence_layout = QVBoxLayout(evidence)
        evidence_layout.setContentsMargins(20, 16, 20, 16)
        evidence_title = QLabel("Event evidence")
        evidence_title.setObjectName("SectionTitle")
        evidence_layout.addWidget(evidence_title)
        metadata = QLabel(
            f"Recorded: {_display_time(event.recorded_at)}\n"
            f"Source: {event.source}\n"
            f"Category: {event.category.replace('-', ' ').title()}\n"
            f"Event reference: {event.event_id[:16]}…"
        )
        metadata.setObjectName("Muted")
        metadata.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        evidence_layout.addWidget(metadata)
        truth = QLabel(
            "This is a redacted local outcome summary. Open its source page for the authoritative receipt, project evidence, or safety state."
        )
        truth.setObjectName("Warning" if event.outcome == "attention" else "Muted")
        truth.setWordWrap(True)
        evidence_layout.addWidget(truth)
        route = activity_source_route(event)
        destination_title = feature(route).title if route else ""
        exact_context = bool(event.source_route and event.context_type and event.context_id)
        if exact_context:
            context = QLabel(
                f"EXACT CONTEXT READY  •  {event.context_type.replace('-', ' ').upper()}  •  "
                f"{event.context_id}"
            )
            context.setObjectName("Good")
            context.setWordWrap(True)
            context.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            context.setAccessibleName(
                f"Exact {event.context_type.replace('-', ' ')} source context is available"
            )
            evidence_layout.addWidget(context)
        self.open_source_button = QPushButton(
            f"Open exact {destination_title} evidence"
            if exact_context
            else f"Open {destination_title}"
            if route
            else "Source page unavailable"
        )
        if route:
            self.open_source_button.setToolTip(
                f"Restore the exact verified {event.context_type.replace('-', ' ')} in "
                f"{destination_title}."
                if exact_context
                else f"Open the canonical {destination_title} page for this {event.source} outcome."
            )
        self.open_source_button.setAccessibleName(
            f"Open the exact source evidence for {event.title}"
            if exact_context
            else f"Open the canonical source page for {event.title}"
            if route
            else f"No canonical source page is registered for {event.title}"
        )
        self.open_source_button.setEnabled(bool(route))
        if exact_context:
            self.open_source_button.clicked.connect(
                lambda _checked=False: self.source_requested.emit(
                    event.source_route,
                    event.context_type,
                    event.context_id,
                )
            )
        elif route:
            self.open_source_button.clicked.connect(
                lambda _checked=False, destination=route: self.route_requested.emit(destination)
            )
        evidence_layout.addWidget(self.open_source_button)
        self.detail_layout.addWidget(evidence)
        self.detail_layout.addStretch()

    def source_handoff_stopped(self, reason: str) -> None:
        """Keep the user on Activity Center when referenced evidence is no longer valid."""

        safe = reason.replace("\x00", " ").strip()[:240] or "Source evidence is unavailable"
        self._set_status("ATTENTION  •  Exact source handoff stopped safely", "Warning")
        self.footer.setText(f"{safe}. No workspace or device state changed.")

    def _render_empty(self, message: str) -> None:
        self._clear_detail()
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        label = QLabel(message)
        label.setObjectName("Muted")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        self.detail_layout.addWidget(card)
        self.detail_layout.addStretch()

    def _export(self) -> None:
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Export ROMVERSE activity",
            "romverse-activity.json",
            "JSON (*.json)",
        )
        if not destination:
            return
        try:
            path = self.store.export(Path(destination))
            self.footer.setText(f"Exported privacy-safe activity ledger: {path.name}")
        except ActivityStoreError as exc:
            self.footer.setText(f"Activity export stopped safely: {exc}")

    def _set_status(self, text: str, object_name: str) -> None:
        self.ledger_status.setText(text)
        self.ledger_status.setObjectName(object_name)
        self.ledger_status.style().unpolish(self.ledger_status)
        self.ledger_status.style().polish(self.ledger_status)

    def _clear_detail(self) -> None:
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._apply_responsive_layout()
        super().resizeEvent(event)

    def _apply_responsive_layout(self) -> None:
        compact_height = self.height() < 760
        # Native font metrics make the same nominal width slightly wider on
        # Windows.  Collapse the secondary copy before it can crowd the ledger
        # controls on either supported desktop platform.
        compact_width = self.width() < 1100
        self.metrics_host.setVisible(not compact_height)
        self.compact_summary.setVisible(compact_height)
        self.subtitle.setVisible(not compact_width)
        self.boundary_copy.setVisible(not (compact_height and compact_width))
        self.ledger_status.setToolTip(
            "The ledger contains bounded privacy-safe summaries and has no approval or execution authority."
            if compact_height and compact_width
            else ""
        )


def _display_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%d %b %Y • %H:%M")
    except ValueError:
        return "Unknown time"
