from __future__ import annotations

from collections import deque
from collections.abc import Callable
from contextlib import suppress

from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QObject,
    QRunnable,
    QThread,
    QThreadPool,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtWidgets import QApplication


class WorkerLifecycle(QObject):
    """Main-thread signal bridge kept alive independently of a page or dialog."""

    exited = Signal(object)


class CoalescedProgress:
    """Bound and de-duplicate worker progress before it enters Qt's event queue.

    Multi-gigabyte copies, hashes, downloads, and filesystem scans can report many
    thousands of byte-level callbacks for the same visible percentage. Queuing each
    callback makes the GUI appear frozen even though the worker remains healthy.
    This relay publishes at most one event for each new integer percentage and never
    lets a late phase move the visible bar backwards.
    """

    def __init__(self, publish: Callable[[int], None]) -> None:
        self._publish = publish
        self._last = -1

    def __call__(self, value: int | float) -> None:
        percent = max(0, min(100, int(value)))
        if percent <= self._last:
            return
        self._last = percent
        self._publish(percent)


def measured_percent(done: int, total: int) -> int | None:
    """Convert real units without rounding unfinished work up to completion."""

    if total <= 0:
        return None
    if done >= total:
        return 100
    return max(0, min(99, int(done * 100 / total)))


class ManagedRunnable(QRunnable):
    """QRunnable whose C++ and Python lifetimes are supervised explicitly.

    PySide callbacks may still be unwinding after a result signal reaches the UI. Qt's
    default auto-delete can therefore race Python/Shiboken object destruction. Managed
    workers disable auto-delete and notify the application-level supervisor only after
    their operation body has exited.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.lifecycle = WorkerLifecycle()

    @Slot()
    def run(self) -> None:
        try:
            self.execute()
        finally:
            # The application can finish while a bounded network or hashing worker is
            # unwinding. Qt may already have deleted its signal bridge at that point;
            # shutdown has intentionally disconnected every UI receiver, so there is
            # nothing left to notify.
            with suppress(RuntimeError):
                self.lifecycle.exited.emit(self)

    def execute(self) -> None:
        raise NotImplementedError


class BackgroundTaskSupervisor(QObject):
    """Own managed workers beyond page lifetime and retire them on the UI thread."""

    RETENTION_MILLISECONDS = 1_000
    MAX_RETIRED = 64

    def __init__(self, application: QApplication) -> None:
        super().__init__(application)
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(max(2, min(6, QThread.idealThreadCount())))
        self._active: dict[int, ManagedRunnable] = {}
        self._retired: deque[ManagedRunnable] = deque(maxlen=self.MAX_RETIRED)
        self._shutting_down = False
        application.aboutToQuit.connect(self.shutdown)

    def start(self, worker: ManagedRunnable) -> None:
        if self._shutting_down:
            raise RuntimeError("ROMVERSE is shutting down; new background work is disabled")
        identity = id(worker)
        if identity in self._active:
            raise RuntimeError("Background worker is already running")
        self._active[identity] = worker
        worker.lifecycle.exited.connect(self._worker_exited)
        self.pool.start(worker)

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def retired_count(self) -> int:
        return len(self._retired)

    @Slot(object)
    def _worker_exited(self, worker: ManagedRunnable) -> None:
        if self._shutting_down:
            return
        retained = self._active.pop(id(worker), None)
        if retained is None:
            return
        self._retired.append(retained)
        # The queued lifecycle signal can be delivered just before QRunnable.run()
        # returns. A short UI-thread grace period guarantees callback unwinding before
        # the last application-owned reference is released.
        QTimer.singleShot(self.RETENTION_MILLISECONDS, lambda: self._release(retained))

    def _release(self, worker: ManagedRunnable) -> None:
        if self._shutting_down:
            return
        with suppress(ValueError):
            self._retired.remove(worker)
        self._dispose_worker(worker)

    @staticmethod
    def _dispose_worker(worker: ManagedRunnable) -> None:
        """Retire every QObject bridge on the GUI thread."""

        signal_bridge = getattr(worker, "signals", None)
        if isinstance(signal_bridge, QObject):
            with suppress(RuntimeError):
                signal_bridge.deleteLater()
        with suppress(RuntimeError):
            worker.lifecycle.deleteLater()

    @Slot()
    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self.pool.clear()
        workers = tuple(self._active.values()) + tuple(self._retired)
        # No result callback should target a page while its widget tree is closing.
        # Disconnecting the GUI bridges is thread-safe; the operation bodies remain
        # bounded and are allowed to unwind normally below.
        for worker in workers:
            signal_bridge = getattr(worker, "signals", None)
            if isinstance(signal_bridge, QObject):
                with suppress(RuntimeError, TypeError):
                    signal_bridge.disconnect()
            with suppress(RuntimeError, TypeError):
                worker.lifecycle.exited.disconnect(self._worker_exited)

        # ROMVERSE workers use bounded subprocess/network timeouts. Waiting here avoids
        # interpreter teardown while a PySide callback still owns Python state.
        # Worker operations are bounded or finite. A clean wait is safer than allowing
        # Python/Qt teardown to race a still-running callback. This happens only while
        # the user is closing ROMVERSE.
        self.pool.waitForDone(-1)
        for worker in workers:
            self._dispose_worker(worker)
        self._active.clear()
        self._retired.clear()
        # aboutToQuit may be the final event-loop turn. Flush only deferred deletion
        # events so Qt objects are destroyed deterministically before Python teardown.
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


_supervisor: BackgroundTaskSupervisor | None = None


def background_supervisor() -> BackgroundTaskSupervisor:
    global _supervisor
    application = QApplication.instance()
    if application is None:
        raise RuntimeError("Background tasks require an active QApplication")
    if _supervisor is None:
        _supervisor = BackgroundTaskSupervisor(application)
    return _supervisor


def start_background(worker: ManagedRunnable) -> None:
    background_supervisor().start(worker)


def shutdown_background_tasks() -> None:
    """Shut down an existing supervisor without creating one during app exit."""

    global _supervisor
    if _supervisor is not None:
        supervisor = _supervisor
        _supervisor = None
        supervisor.shutdown()
