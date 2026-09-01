from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from romverse.ui.connectivity import OnlineStatusBadge


def test_online_badge_distinguishes_checking_online_and_offline() -> None:
    QApplication.instance() or QApplication([])
    badge = OnlineStatusBadge(auto_start=False)
    states: list[tuple[bool, str]] = []
    badge.status_changed.connect(lambda online, detail: states.append((online, detail)))

    assert badge.online is None
    assert badge.label.text() == "CHECKING"
    assert "no online service is assumed" in badge.toolTip()

    badge._set_state(True, "Internet route verified")
    assert badge.online is True
    assert badge.label.text() == "ONLINE"
    assert badge.accessibleName() == "ROMVERSE online"

    badge._set_state(True, "A refreshed detail")
    assert states == [(True, "Internet route verified")]

    badge._set_state(False, "Internet check failed")
    assert badge.online is False
    assert badge.label.text() == "OFFLINE"
    assert badge.accessibleName() == "ROMVERSE offline"
    assert states[-1] == (False, "Internet check failed")

    badge.close()


def test_online_badge_local_mode_starts_no_monitor_and_can_be_toggled() -> None:
    QApplication.instance() or QApplication([])
    badge = OnlineStatusBadge(auto_start=True, monitoring_enabled=False)

    assert not badge.monitoring_enabled
    assert badge.online is None
    assert badge.label.text() == "LOCAL"
    assert "no internet reachability request is running" in badge.toolTip()
    assert badge.reply is None
    assert not badge.timer.isActive()

    badge.refresh()
    assert badge.reply is None

    badge.set_monitoring_enabled(True)
    assert badge.monitoring_enabled
    assert badge.label.text() == "CHECKING"
    assert badge.timer.isActive()

    class FakeFinished:
        def __init__(self) -> None:
            self.disconnected = False

        def disconnect(self, _callback) -> None:
            self.disconnected = True

    class FakeReply:
        def __init__(self) -> None:
            self.finished = FakeFinished()
            self.aborted = False
            self.deleted = False

        def abort(self) -> None:
            self.aborted = True

        def deleteLater(self) -> None:
            self.deleted = True

    reply = FakeReply()
    badge.reply = reply  # type: ignore[assignment]

    badge.set_monitoring_enabled(False)
    assert not badge.monitoring_enabled
    assert badge.label.text() == "LOCAL"
    assert badge.reply is None
    assert not badge.timer.isActive()
    assert reply.finished.disconnected
    assert reply.aborted
    assert reply.deleted
    badge.close()
