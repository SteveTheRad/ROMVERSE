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
