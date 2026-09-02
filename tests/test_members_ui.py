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


def test_members_opens_its_exact_local_service_guide_without_network_work() -> None:
    app = QApplication.instance() or QApplication([])
    center = MembersCenter()
    requested: list[str] = []
    center.knowledge_article_requested.connect(requested.append)

    center.guide_button.click()

    assert requested == ["members-service-unavailable-or-unconfigured"]
    assert not center._busy
    assert center._authorization is None
    assert center.session is None
    assert not center._poll_timer.isActive()
    center.close()
    app.processEvents()
