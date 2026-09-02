"""Keyboard-first navigation for the ROMVERSE Desktop shell.

The palette deliberately owns no operation callbacks.  It emits only stable route keys so
MainWindow remains the sole authority for opening canonical pages.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True, slots=True)
class NavigationCommand:
    """One canonical Desktop page or owner-routed feature destination."""

    route: str
    title: str
    subtitle: str
    aliases: tuple[str, ...] = ()


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def match_navigation_commands(
    commands: tuple[NavigationCommand, ...], query: str
) -> tuple[NavigationCommand, ...]:
    """Return stable, relevance-ranked navigation matches for one bounded query."""

    normalized_query = _normalized(query)[:120]
    if not normalized_query:
        return commands

    query_tokens = normalized_query.split()
    matches: list[tuple[int, int, NavigationCommand]] = []
    for position, command in enumerate(commands):
        title = _normalized(command.title)
        subtitle = _normalized(command.subtitle)
        aliases = tuple(_normalized(alias) for alias in command.aliases)
        searchable = " ".join((title, subtitle, *aliases))
        if not all(token in searchable for token in query_tokens):
            continue

        if title == normalized_query:
            rank = 0
        elif title.startswith(normalized_query):
            rank = 1
        elif any(word.startswith(normalized_query) for word in title.split()):
            rank = 2
        elif normalized_query in title:
            rank = 3
        elif any(
            alias == normalized_query or alias.startswith(normalized_query) for alias in aliases
        ):
            rank = 4
        elif normalized_query in subtitle:
            rank = 5
        else:
            rank = 6
        matches.append((rank, position, command))

    return tuple(command for _rank, _position, command in sorted(matches))


class CommandPaletteDialog(QDialog):
    """Accessible navigation-only command palette."""

    navigation_requested = Signal(str)

    def __init__(
        self,
        commands: tuple[NavigationCommand, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._commands = commands
        self.setWindowTitle("Navigate ROMVERSE")
        self.setModal(True)
        self.setMinimumSize(600, 430)
        self.resize(680, 500)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)

        title = QLabel("Navigate ROMVERSE")
        title.setObjectName("Title")
        layout.addWidget(title)

        self.boundary = QLabel(
            "Search existing pages and tools. Navigation only — no device or build operation will run."
        )
        self.boundary.setObjectName("Muted")
        self.boundary.setWordWrap(True)
        layout.addWidget(self.boundary)

        self.search = QLineEdit()
        self.search.setObjectName("CommandPaletteSearch")
        self.search.setAccessibleName("Search ROMVERSE features")
        self.search.setPlaceholderText("Type a page, goal, or familiar feature name …")
        self.search.setClearButtonEnabled(True)
        self.search.setMaxLength(120)
        self.search.textChanged.connect(self._refresh)
        self.search.returnPressed.connect(self._activate_current)
        self.search.installEventFilter(self)
        layout.addWidget(self.search)

        self.result_count = QLabel()
        self.result_count.setObjectName("Muted")
        self.result_count.setAccessibleName("Command palette result count")
        layout.addWidget(self.result_count)

        self.results = QListWidget()
        self.results.setObjectName("CommandPaletteResults")
        self.results.setAccessibleName("Matching ROMVERSE features")
        self.results.setUniformItemSizes(True)
        self.results.itemActivated.connect(self._activate_item)
        layout.addWidget(self.results, 1)

        keyboard_help = QLabel("Enter opens the selected feature  •  Esc closes  •  Ctrl+K opens")
        keyboard_help.setObjectName("Muted")
        keyboard_help.setAccessibleName(
            "Keyboard help: Enter opens the selected feature, Escape closes the palette"
        )
        layout.addWidget(keyboard_help)

        self._refresh("")
        QTimer.singleShot(0, self.search.setFocus)

    def _refresh(self, query: str) -> None:
        matches = match_navigation_commands(self._commands, query)
        self.results.clear()
        for command in matches:
            item = QListWidgetItem(f"{command.title}   ·   {command.subtitle}")
            item.setData(Qt.ItemDataRole.UserRole, command.route)
            item.setToolTip(f"Open {command.title} — {command.subtitle}")
            item.setData(
                Qt.ItemDataRole.AccessibleTextRole,
                f"{command.title}. {command.subtitle}",
            )
            item.setSizeHint(QSize(0, 48))
            self.results.addItem(item)
        if matches:
            self.results.setCurrentRow(0)
            noun = "destination" if len(matches) == 1 else "destinations"
            self.result_count.setText(f"{len(matches)} {noun}")
        else:
            empty = QListWidgetItem("No matching ROMVERSE feature")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            empty.setData(Qt.ItemDataRole.AccessibleTextRole, "No matching ROMVERSE feature")
            empty.setSizeHint(QSize(0, 52))
            self.results.addItem(empty)
            self.result_count.setText("0 destinations")

    def _activate_current(self) -> None:
        self._activate_item(self.results.currentItem())

    def _activate_item(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        route = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(route, str) or not route:
            return
        self.navigation_requested.emit(route)
        self.accept()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if (
            watched is self.search
            and event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up)
        ):
            direction = 1 if event.key() == Qt.Key.Key_Down else -1
            next_row = max(0, min(self.results.count() - 1, self.results.currentRow() + direction))
            self.results.setCurrentRow(next_row)
            self.results.setFocus()
            return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)
