"""Keep Qt alive until every test-owned window and deferred deletion is cleaned up."""

import gc
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def qt_application():
    application = QApplication.instance() or QApplication([])
    yield application
    gc.collect()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()
    application.quit()


@pytest.fixture(autouse=True)
def close_test_windows(qt_application):
    yield
    # These widgets belong to this pytest process, never another running desktop.
    for window in qt_application.topLevelWidgets():
        window.close()
        window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qt_application.processEvents()
    gc.collect()
