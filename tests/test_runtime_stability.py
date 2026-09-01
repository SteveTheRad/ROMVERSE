from __future__ import annotations

import gc
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from romverse.core.runtime_stability import GuiThreadGarbageCollector, RuntimeCrashGuard


def test_runtime_guard_records_unhandled_python_evidence(tmp_path: Path) -> None:
    previous_hook = sys.excepthook
    observed: list[str] = []
    guard = RuntimeCrashGuard(tmp_path)
    guard._previous_hook = lambda kind, error, trace: observed.append(str(error))  # type: ignore[method-assign]

    guard.install()
    guard._record_unhandled_exception(RuntimeError, RuntimeError("probe failure"), None)
    guard.close()

    content = guard.path.read_text(encoding="utf-8")
    assert "ROMVERSE runtime started" in content
    assert "RuntimeError: probe failure" in content
    assert "ROMVERSE runtime closed cleanly" in content
    assert observed == ["probe failure"]
    assert sys.excepthook is guard._previous_hook
    sys.excepthook = previous_hook


def test_cyclic_collection_is_confined_to_gui_thread() -> None:
    application = QApplication.instance() or QApplication([])
    was_enabled = gc.isenabled()
    collector = GuiThreadGarbageCollector(application, interval_ms=60_000)

    with patch("romverse.core.runtime_stability.gc.collect", return_value=7) as collect:
        collector.install()
        assert not gc.isenabled()
        assert collector.timer.isActive()
        assert collector.collect_now() == 7
        assert QThread.currentThread() is application.thread()
        collector.close()

    assert collect.call_count == 2
    collect.assert_called_with()
    assert collector.timer.isActive() is False
    assert gc.isenabled() is was_enabled


def test_gui_collector_rejects_collection_from_worker_thread() -> None:
    application = QApplication.instance() or QApplication([])
    collector = GuiThreadGarbageCollector(application, interval_ms=60_000)
    collector.install()
    try:
        with (
            patch.object(QThread, "currentThread", return_value=QThread()),
            pytest.raises(RuntimeError, match="outside the GUI thread"),
        ):
            collector.collect_now()
    finally:
        collector.close()
