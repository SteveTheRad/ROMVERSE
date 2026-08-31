from __future__ import annotations

import time

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QApplication

from romverse.ui.background import (
    ManagedRunnable,
    background_supervisor,
    shutdown_background_tasks,
    start_background,
)


class ProbeSignals(QObject):
    complete = Signal(bool)


class ProbeWorker(ManagedRunnable):
    def __init__(self) -> None:
        super().__init__()
        self.signals = ProbeSignals()

    def execute(self) -> None:
        application = QApplication.instance()
        self.signals.complete.emit(QThread.currentThread() is not application.thread())


def test_managed_worker_disables_qt_auto_delete_and_is_supervised_until_exit() -> None:
    application = QApplication.instance() or QApplication([])
    worker = ProbeWorker()
    completed: list[bool] = []
    worker.signals.complete.connect(completed.append)

    assert worker.autoDelete() is False
    start_background(worker)
    deadline = time.monotonic() + 2
    while (not completed or background_supervisor().active_count) and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.005)

    assert completed == [True]
    assert background_supervisor().active_count == 0
    assert background_supervisor().retired_count >= 1


def test_managed_worker_lifecycle_survives_repeated_pooled_callbacks() -> None:
    application = QApplication.instance() or QApplication([])
    completed: list[bool] = []
    workers = [ProbeWorker() for _ in range(300)]
    for worker in workers:
        worker.signals.complete.connect(completed.append)
        start_background(worker)

    deadline = time.monotonic() + 5
    while (
        len(completed) < len(workers) or background_supervisor().active_count
    ) and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.001)

    assert len(completed) == len(workers)
    assert all(completed)
    assert background_supervisor().active_count == 0


def test_shutdown_drains_workers_and_allows_a_fresh_supervisor() -> None:
    application = QApplication.instance() or QApplication([])
    completed: list[bool] = []
    workers = [ProbeWorker() for _ in range(100)]
    for worker in workers:
        worker.signals.complete.connect(completed.append)
        start_background(worker)

    shutdown_background_tasks()
    application.processEvents()

    assert background_supervisor().active_count == 0
    replacement = ProbeWorker()
    replacement.signals.complete.connect(completed.append)
    start_background(replacement)
    deadline = time.monotonic() + 2
    while background_supervisor().active_count and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.005)
    assert background_supervisor().active_count == 0
