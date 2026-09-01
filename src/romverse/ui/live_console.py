from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
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


class LiveConsoleCenter(QWidget):
    """Beginner-readable view of genuine ROMVERSE Nexus mission events."""

    FILTERS = ("All events", "Active", "Completed", "Needs attention")

    def __init__(self, store: LiveConsoleEventStore) -> None:
        super().__init__()
        self.store = store
        self._events: tuple[LiveConsoleEvent, ...] = ()
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
        self.table.setHorizontalHeaderLabels(
            ("Time", "Subsystem", "Stage", "State", "Progress", "Confidence")
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
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
            self.status.setText(f"Live Console evidence needs attention: {exc}")
            self.status.setObjectName("Danger")
            self._repolish(self.status)
            self._render()
            return
        changed = events != self._events
        self._events = events
        active = sum(item.state is MissionState.RUNNING for item in events)
        self.status.setText(
            f"{len(events)} genuine event{'s' if len(events) != 1 else ''}  •  "
            f"{active} active  •  privacy-redacted local ledger"
        )
        self.status.setObjectName("Good" if events else "Muted")
        self._repolish(self.status)
        if changed:
            self._render()

    def _filtered(self) -> tuple[LiveConsoleEvent, ...]:
        selected = self.filter.currentText()
        if selected == "Active":
            return tuple(item for item in self._events if item.state is MissionState.RUNNING)
        if selected == "Completed":
            return tuple(item for item in self._events if item.state is MissionState.SUCCEEDED)
        if selected == "Needs attention":
            return tuple(
                item
                for item in self._events
                if item.state in {MissionState.FAILED, MissionState.BLOCKED, MissionState.ATTENTION}
            )
        return self._events

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
                if column == 3:
                    item.setForeground(color)
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

    def showEvent(self, event) -> None:
        self.refresh()
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
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

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
