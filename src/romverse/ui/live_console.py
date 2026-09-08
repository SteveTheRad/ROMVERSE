from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from romverse.nexus.events import (
    LiveConsoleEvent,
    LiveConsoleEventStore,
    LiveConsoleStoreError,
    MissionState,
)
from romverse.ui.vocabulary import NESTED_FEATURE_OWNERS, canonical_source_route, feature


class _LiveConsoleItemDelegate(QStyledItemDelegate):
    """Paint evidence cells without trusting the host desktop's item-view theme."""

    BASE = QColor("#060B16")
    ALTERNATE = QColor("#0B1322")
    HOVER = QColor("#142440")
    TEXT = QColor("#DCE8F8")
    GRID = QColor("#223653")

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        painter.save()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            background = QLinearGradient(option.rect.topLeft(), option.rect.topRight())
            background.setColorAt(0.0, QColor("#523B9B"))
            background.setColorAt(1.0, QColor("#236996"))
            painter.fillRect(option.rect, QBrush(background))
        else:
            background = (
                self.HOVER if hovered else (self.BASE if index.row() % 2 == 0 else self.ALTERNATE)
            )
            painter.fillRect(option.rect, background)

        painter.setPen(self.GRID)
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
        painter.drawLine(option.rect.topRight(), option.rect.bottomRight())

        foreground = index.data(Qt.ItemDataRole.ForegroundRole)
        text_color = foreground.color() if isinstance(foreground, QBrush) else self.TEXT
        painter.setPen(QColor("#FFFFFF") if selected or hovered else text_color)
        painter.setFont(option.font)
        text_rect = option.rect.adjusted(7, 0, -6, 0)
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        text = option.fontMetrics.elidedText(
            text,
            Qt.TextElideMode.ElideRight,
            max(0, text_rect.width()),
        )
        alignment = index.data(Qt.ItemDataRole.TextAlignmentRole)
        if alignment is None:
            alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        painter.drawText(text_rect, int(alignment), text)
        painter.restore()


class _LiveConsoleHeader(QHeaderView):
    """Paint a stable dark header even when Wayland injects a light native base."""

    def paintSection(self, painter: QPainter, rect, logical_index: int) -> None:
        if not rect.isValid():
            return
        painter.save()
        painter.fillRect(rect, QColor("#0D1729"))
        painter.setPen(QColor("#29466F"))
        painter.drawLine(rect.topRight(), rect.bottomRight())
        painter.setPen(QColor("#3B5E8E"))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        font = self.font()
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#CFE1F7"))
        text_rect = rect.adjusted(7, 0, -6, 0)
        text = str(
            self.model().headerData(
                logical_index,
                self.orientation(),
                Qt.ItemDataRole.DisplayRole,
            )
            or ""
        )
        text = painter.fontMetrics().elidedText(
            text,
            Qt.TextElideMode.ElideRight,
            max(0, text_rect.width()),
        )
        alignment = self.model().headerData(
            logical_index,
            self.orientation(),
            Qt.ItemDataRole.TextAlignmentRole,
        )
        if alignment is None:
            alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        painter.drawText(text_rect, int(alignment), text)
        painter.restore()


class LiveConsoleCenter(QWidget):
    """Beginner-readable view of genuine ROMVERSE Nexus mission events."""

    source_requested = Signal(str, str)
    FILTERS = ("All events", "Active", "Completed", "Needs attention")
    TABLE_BASE = QColor("#060B16")
    TABLE_ALTERNATE = QColor("#0B1322")
    TABLE_TEXT = QColor("#DCE8F8")

    def __init__(self, store: LiveConsoleEventStore) -> None:
        super().__init__()
        self.store = store
        self._events: tuple[LiveConsoleEvent, ...] = ()
        self._mission_context_id = ""
        self._mission_context_project_id = ""
        self._selected_source_route = ""
        self._selected_project_id = ""
        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 30)
        page.setSpacing(16)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        eyebrow = QLabel("ROMVERSE LIVE CONSOLE  •  NEXUS EVENTS  •  GUARDIAN TRUTH")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("Live Console")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Watch what ROMVERSE is doing, why it is doing it, the evidence it trusts, "
            "and what happens next. Success appears only after the producing subsystem reports it."
        )
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        heading.addWidget(eyebrow)
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading, 1)
        self.refresh_button = QPushButton("Refresh events")
        self.refresh_button.setObjectName("Primary")
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button)
        page.addLayout(header)

        controls = QFrame()
        controls.setObjectName("Card")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(16, 12, 16, 12)
        self.status = QLabel("Waiting for genuine Nexus events")
        self.status.setObjectName("Muted")
        controls_layout.addWidget(self.status, 1)
        controls_layout.addWidget(QLabel("Show"))
        self.filter = QComboBox()
        self.filter.addItems(self.FILTERS)
        self.filter.currentTextChanged.connect(self._render)
        controls_layout.addWidget(self.filter)
        page.addWidget(controls)

        self.table = QTableWidget(0, 6)
        self.table.setObjectName("LiveConsoleTable")
        self.table.setAccessibleName("Genuine ROMVERSE mission events")
        table_header = _LiveConsoleHeader(Qt.Orientation.Horizontal, self.table)
        table_header.setObjectName("LiveConsoleHeader")
        self.table.setHorizontalHeader(table_header)
        self.table.setItemDelegate(_LiveConsoleItemDelegate(self.table))
        self.table.setHorizontalHeaderLabels(
            ("Time", "Subsystem", "Stage", "State", "Progress", "Confidence")
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)
        self.table.setCornerButtonEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        table_header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        table_header.setMinimumHeight(36)
        table_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._apply_dark_table_surface(table_header)
        self.table.itemSelectionChanged.connect(self._show_selected)
        page.addWidget(self.table, 1)

        detail_card = QFrame()
        detail_card.setObjectName("Card")
        detail_layout = QVBoxLayout(detail_card)
        detail_layout.setContentsMargins(18, 16, 18, 16)
        self.detail_title = QLabel("No mission selected")
        self.detail_title.setObjectName("SectionTitle")
        self.detail = QLabel(
            "ROMVERSE has not recorded a Live Console event yet. The console will stay empty "
            "instead of simulating activity."
        )
        self.detail.setObjectName("Muted")
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("No active progress")
        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail)
        detail_layout.addWidget(self.progress)
        source_actions = QHBoxLayout()
        self.source_feedback = QLabel(
            "Select a genuine event to inspect its canonical source feature."
        )
        self.source_feedback.setObjectName("Muted")
        self.source_feedback.setWordWrap(True)
        source_actions.addWidget(self.source_feedback, 1)
        self.open_source_button = QPushButton("Source page unavailable")
        self.open_source_button.setEnabled(False)
        self.open_source_button.clicked.connect(self._open_selected_source)
        source_actions.addWidget(self.open_source_button)
        detail_layout.addLayout(source_actions)
        page.addWidget(detail_card)

        self._timer = QTimer(self)
        self._timer.setInterval(1_000)
        self._timer.timeout.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        try:
            events = self.store.list_recent()
        except LiveConsoleStoreError as exc:
            self._events = ()
            self._clear_source_action("Source routing is unavailable until the ledger verifies.")
            self.status.setText(f"Live Console evidence needs attention: {exc}")
            self.status.setObjectName("Danger")
            self._repolish(self.status)
            self._render()
            return
        changed = events != self._events
        self._events = events
        visible_events = (
            tuple(
                item
                for item in events
                if item.mission_id == self._mission_context_id
                and item.project_id == self._mission_context_project_id
            )
            if self._mission_context_id
            else events
        )
        active = sum(item.state is MissionState.RUNNING for item in visible_events)
        if self._mission_context_id:
            self.status.setText(
                f"EXACT MISSION LEDGER  •  {len(visible_events)} genuine event"
                f"{'s' if len(visible_events) != 1 else ''}  •  {active} active  •  "
                "no action started"
            )
        else:
            self.status.setText(
                f"{len(events)} genuine event{'s' if len(events) != 1 else ''}  •  "
                f"{active} active  •  privacy-redacted local ledger"
            )
        self.status.setObjectName("Good" if visible_events else "Muted")
        self._repolish(self.status)
        if changed:
            self._render()

    def _filtered(self) -> tuple[LiveConsoleEvent, ...]:
        events = self._events
        if self._mission_context_id:
            events = tuple(
                item
                for item in events
                if item.mission_id == self._mission_context_id
                and item.project_id == self._mission_context_project_id
            )
        selected = self.filter.currentText()
        if selected == "Active":
            return tuple(item for item in events if item.state is MissionState.RUNNING)
        if selected == "Completed":
            return tuple(item for item in events if item.state is MissionState.SUCCEEDED)
        if selected == "Needs attention":
            return tuple(
                item
                for item in events
                if item.state in {MissionState.FAILED, MissionState.BLOCKED, MissionState.ATTENTION}
            )
        return events

    def open_mission_context(self, mission_id: str, project_id: str) -> bool:
        """Show one current project-owned mission without inferring or starting work."""

        normalized_mission = mission_id.strip()
        normalized_project = project_id.strip()
        if not normalized_mission or not normalized_project:
            return False
        try:
            events = self.store.list_recent()
        except LiveConsoleStoreError:
            return False
        latest = next(
            (
                item
                for item in events
                if item.mission_id == normalized_mission and item.project_id == normalized_project
            ),
            None,
        )
        if latest is None or latest.state is not MissionState.RUNNING:
            return False
        self._events = events
        self._mission_context_id = normalized_mission
        self._mission_context_project_id = normalized_project
        self.filter.setCurrentText("All events")
        matching = tuple(
            item
            for item in events
            if item.mission_id == normalized_mission and item.project_id == normalized_project
        )
        active = sum(item.state is MissionState.RUNNING for item in matching)
        self.status.setText(
            f"EXACT MISSION LEDGER  •  {len(matching)} genuine event"
            f"{'s' if len(matching) != 1 else ''}  •  {active} active  •  no action started"
        )
        self.status.setObjectName("Good")
        self._repolish(self.status)
        self._render()
        return True

    def clear_mission_context(self) -> None:
        """Return future direct navigation to the complete genuine event ledger."""

        if not self._mission_context_id:
            return
        self._mission_context_id = ""
        self._mission_context_project_id = ""
        self._render()

    def _render(self) -> None:
        events = self._filtered()
        self.table.setRowCount(0)
        for row, event in enumerate(events):
            self.table.insertRow(row)
            values = (
                self._display_time(event.updated_at),
                event.source,
                event.stage.replace("-", " ").title(),
                event.state.value.replace("-", " ").upper(),
                f"{event.progress_percent}%",
                event.confidence.value.replace("-", " ").upper(),
            )
            color = self._state_color(event.state)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, event.event_id)
                item.setBackground(
                    QBrush(self.TABLE_BASE if row % 2 == 0 else self.TABLE_ALTERNATE)
                )
                item.setForeground(QBrush(self.TABLE_TEXT))
                if column == 3:
                    item.setForeground(QBrush(color))
                self.table.setItem(row, column, item)
        if events:
            self.table.selectRow(0)
        else:
            self.detail_title.setText("No matching genuine events")
            self.detail.setText(
                "Nothing matches this filter. ROMVERSE does not generate placeholder mission activity."
            )
            self.progress.setValue(0)
            self.progress.setFormat("No active progress")
            self._clear_source_action(
                "No matching event has a canonical source to open from this view."
            )

    def _show_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0 or self.table.item(row, 0) is None:
            return
        event_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        event = next((item for item in self._events if item.event_id == event_id), None)
        if event is None:
            return
        guardian = "Guardian protected" if event.guardian_protected else "Read-only evidence"
        evidence = (
            "\nEvidence: " + ", ".join(event.evidence_refs)
            if event.evidence_refs
            else "\nEvidence: no artifact reference reported"
        )
        project = f"\nProject: {event.project_id}" if event.project_id else ""
        self.detail_title.setText(event.title)
        self.detail.setText(
            f"WHAT HAPPENED\n{event.summary}\n\nWHY\n{event.explanation}\n\n"
            f"NEXT\n{event.next_action}\n\n{guardian}  •  "
            f"Confidence: {event.confidence.value.replace('-', ' ')}"
            f"{project}{evidence}"
        )
        self.progress.setValue(event.progress_percent)
        self.progress.setFormat(f"{event.state.value.replace('-', ' ').title()}  •  %p%")
        route = canonical_source_route(event.source)
        self._selected_source_route = route
        self._selected_project_id = event.project_id
        if route:
            destination = feature(route).title
            self.open_source_button.setText(f"Open {destination}")
            self.open_source_button.setEnabled(True)
            self.open_source_button.setToolTip(
                f"Open the exact canonical {destination} destination for this genuine "
                f"{event.source} event without repeating it."
            )
            owner_route = NESTED_FEATURE_OWNERS.get(route, route)
            project = (
                f"  •  exact project {event.project_id}"
                if event.project_id and owner_route in {"nexus", "rom_studio"}
                else ""
            )
            self.source_feedback.setText(
                f"SOURCE READY  •  {event.source} → {destination}{project}"
            )
            self.source_feedback.setObjectName("Good")
            self._repolish(self.source_feedback)
        else:
            self._clear_source_action(
                f"{event.source} did not report a registered canonical Desktop source page."
            )

    def _open_selected_source(self) -> None:
        if not self._selected_source_route:
            return
        self.source_requested.emit(self._selected_source_route, self._selected_project_id)

    def source_handoff_stopped(self, reason: str) -> None:
        """Keep a failed source return readable even without Desktop notifications."""

        self.source_feedback.setText(f"SOURCE HANDOFF STOPPED  •  {reason}  •  NO ACTION STARTED")
        self.source_feedback.setObjectName("Danger")
        self._repolish(self.source_feedback)

    def _clear_source_action(self, message: str) -> None:
        self._selected_source_route = ""
        self._selected_project_id = ""
        self.open_source_button.setText("Source page unavailable")
        self.open_source_button.setEnabled(False)
        self.open_source_button.setToolTip("")
        self.source_feedback.setText(message)
        self.source_feedback.setObjectName("Muted")
        self._repolish(self.source_feedback)

    def showEvent(self, event) -> None:
        self.refresh()
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        self.clear_mission_context()
        super().hideEvent(event)

    @staticmethod
    def _display_time(value: str) -> str:
        return datetime.fromisoformat(value).astimezone().strftime("%H:%M:%S")

    @staticmethod
    def _state_color(state: MissionState) -> QColor:
        return {
            MissionState.SUCCEEDED: QColor("#72FFB2"),
            MissionState.RUNNING: QColor("#57E7FF"),
            MissionState.INFORMATION: QColor("#A7C8FF"),
            MissionState.ATTENTION: QColor("#FFB454"),
            MissionState.BLOCKED: QColor("#FF8D74"),
            MissionState.FAILED: QColor("#FF6685"),
        }[state]

    def _apply_dark_table_surface(self, header: QHeaderView) -> None:
        """Keep Fedora's native palette from repainting this dark evidence grid white."""

        palette = self.table.palette()
        for group in (
            QPalette.ColorGroup.Active,
            QPalette.ColorGroup.Inactive,
            QPalette.ColorGroup.Disabled,
        ):
            palette.setColor(group, QPalette.ColorRole.Base, self.TABLE_BASE)
            palette.setColor(group, QPalette.ColorRole.AlternateBase, self.TABLE_ALTERNATE)
            palette.setColor(group, QPalette.ColorRole.Text, self.TABLE_TEXT)
            palette.setColor(group, QPalette.ColorRole.Window, self.TABLE_BASE)
            palette.setColor(group, QPalette.ColorRole.WindowText, self.TABLE_TEXT)
            palette.setColor(group, QPalette.ColorRole.Button, QColor("#0D1729"))
            palette.setColor(group, QPalette.ColorRole.ButtonText, QColor("#CFE1F7"))
            palette.setColor(group, QPalette.ColorRole.Highlight, QColor("#28589C"))
            palette.setColor(group, QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        self.table.setPalette(palette)
        self.table.viewport().setPalette(palette)
        self.table.viewport().setAutoFillBackground(True)
        header.setPalette(palette)
        header.setAutoFillBackground(True)

        # This local header rule is intentional. Some Fedora desktop themes polish
        # the internal header before its object name is assigned, leaving the global
        # named selector unable to dislodge a light native base.
        header.setStyleSheet(
            """
            QHeaderView { background-color: #0D1729; color: #CFE1F7; }
            QHeaderView::section {
                color: #CFE1F7;
                background-color: #0D1729;
                border: 0;
                border-right: 1px solid #29466F;
                border-bottom: 1px solid #3B5E8E;
                padding: 8px 7px;
                font-weight: 750;
            }
            """
        )

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
