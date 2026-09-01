from __future__ import annotations

import faulthandler
import gc
import sys
import traceback
from pathlib import Path
from types import TracebackType
from typing import TextIO

from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication


class GuiThreadGarbageCollector:
    """Run Python cyclic collection only from Qt's GUI thread.

    PySide wrappers are ordinary Python objects, but deleting a wrapper can also
    destroy its underlying QObject.  If Python's allocation-triggered collector
    happens to run inside a ``QThreadPool`` worker, a previously unreachable GUI
    wrapper can therefore be finalized on the wrong thread.  Qt does not permit
    that and the result can be a native crash rather than a Python exception.

    ROMVERSE disables only *automatic cyclic* collection while the event loop is
    active and performs bounded collections from a GUI-owned timer instead.
    Reference counting is unaffected, and a final GUI-thread collection runs only
    after the event loop (and the background-task shutdown hook) has completed.
    """

    DEFAULT_INTERVAL_MS = 15_000

    def __init__(
        self,
        application: QApplication,
        *,
        interval_ms: int = DEFAULT_INTERVAL_MS,
    ) -> None:
        if QThread.currentThread() is not application.thread():
            raise RuntimeError("GUI garbage collection must be configured on the GUI thread")
        self.application = application
        self._was_enabled = gc.isenabled()
        self._closed = False
        self.timer = QTimer(application)
        self.timer.setInterval(max(1_000, interval_ms))
        self.timer.setSingleShot(False)
        self.timer.timeout.connect(self.collect_now)
        application.aboutToQuit.connect(self.pause)

    def install(self) -> None:
        if self._closed:
            raise RuntimeError("GUI garbage collector has already been closed")
        gc.disable()
        self.timer.start()

    def collect_now(self) -> int:
        if QThread.currentThread() is not self.application.thread():
            raise RuntimeError("Cyclic garbage collection was requested outside the GUI thread")
        return gc.collect()

    def pause(self) -> None:
        """Stop scheduling collections while Qt drains shutdown callbacks."""

        self.timer.stop()

    def close(self) -> None:
        if self._closed:
            return
        self.pause()
        # QApplication.aboutToQuit invokes the background supervisor after ``pause``.
        # By the time app.exec() returns, its bounded workers have finished and a final
        # main-thread collection is safe.
        self.collect_now()
        if self._was_enabled:
            gc.enable()
        self._closed = True

    def __enter__(self) -> GuiThreadGarbageCollector:
        self.install()
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _exception_traceback: TracebackType | None,
    ) -> None:
        self.close()


class RuntimeCrashGuard:
    """Persist Python and native fault evidence for the current ROMVERSE run."""

    def __init__(self, workspace: Path) -> None:
        self.path = workspace / "logs" / "crash" / "runtime-fault.log"
        self._stream: TextIO | None = None
        self._previous_hook = sys.excepthook
        self._owns_faulthandler = False

    def install(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = self.path.open("a", encoding="utf-8", buffering=1)
        self._stream.write("\n=== ROMVERSE runtime started ===\n")
        self._stream.flush()
        if not faulthandler.is_enabled():
            faulthandler.enable(self._stream, all_threads=True)
            self._owns_faulthandler = True
        sys.excepthook = self._record_unhandled_exception

    def _record_unhandled_exception(
        self,
        exception_type: type[BaseException],
        exception: BaseException,
        exception_traceback: TracebackType | None,
    ) -> None:
        if self._stream is not None:
            self._stream.write("\n--- Unhandled Python exception ---\n")
            traceback.print_exception(
                exception_type,
                exception,
                exception_traceback,
                file=self._stream,
            )
            self._stream.flush()
        self._previous_hook(exception_type, exception, exception_traceback)

    def close(self) -> None:
        sys.excepthook = self._previous_hook
        if self._owns_faulthandler and faulthandler.is_enabled():
            faulthandler.disable()
        self._owns_faulthandler = False
        if self._stream is not None:
            self._stream.write("=== ROMVERSE runtime closed cleanly ===\n")
            self._stream.close()
            self._stream = None

    def __enter__(self) -> RuntimeCrashGuard:
        self.install()
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _exception_traceback: TracebackType | None,
    ) -> None:
        self.close()
