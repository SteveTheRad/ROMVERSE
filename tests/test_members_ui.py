from PySide6.QtWidgets import QApplication

from romverse.ui.members_center import MembersCenter


def test_members_network_busy_state_has_honest_indeterminate_progress() -> None:
    app = QApplication.instance() or QApplication([])
    center = MembersCenter()

    assert center.progress.isHidden()
    center._set_busy(True, "Contacting the trusted Members service …")

    assert center._busy
    assert not center.progress.isHidden()
    assert center.progress.minimum() == 0
    assert center.progress.maximum() == 0
    assert not center.primary.isEnabled()
    assert not center.settings_button.isEnabled()

    center._set_busy(False)
    assert center.progress.isHidden()
    assert center.primary.isEnabled()
    assert center.settings_button.isEnabled()

    center.close()
    app.processEvents()
