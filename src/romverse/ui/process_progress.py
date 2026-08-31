from __future__ import annotations

from PySide6.QtWidgets import QProgressBar, QWidget


class ProcessProgressBar(QProgressBar):
    """One honest progress language for ROMVERSE background operations.

    A determinate bar is used only after a worker reports real units. Operations that
    cannot expose bounded units remain indeterminate instead of displaying a made-up
    percentage.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ProcessProgress")
        self.setTextVisible(True)
        self.setFormat("%p%")
        self.setVisible(False)

    def begin(self, *, determinate: bool = False) -> None:
        if determinate:
            self.setRange(0, 100)
            self.setValue(0)
            self.setTextVisible(True)
        else:
            self.setRange(0, 0)
            self.setTextVisible(False)
        self.setVisible(True)

    def report(self, value: int) -> None:
        self.setRange(0, 100)
        self.setTextVisible(True)
        self.setValue(max(0, min(100, int(value))))

    def finish(self) -> None:
        self.setRange(0, 100)
        self.setTextVisible(True)
        self.setValue(100)
        self.setVisible(False)

    def stop(self) -> None:
        self.setVisible(False)
