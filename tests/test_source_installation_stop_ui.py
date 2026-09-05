"""Stop at the final source action does not silently start another operation."""

from __future__ import annotations

import json

import pytest

from romverse.guardian.local_flash import LocalFlashState
from romverse.ui.local_flash import LocalBootWorker
from tests.test_source_installation_integration import (
    _answer,
    _click,
    _finish_worker,
    _review,
)
from tests.test_source_installation_integration import installation as installation
from tests.test_source_installation_integration import installation_dialog as installation_dialog


@pytest.mark.parametrize("stop_at_final_reboot", [True, False])
def test_final_reboot_completion_keeps_truthful_result_and_honours_stop(
    installation_dialog, monkeypatch, stop_at_final_reboot
):
    app, dialog, workers, context = installation_dialog
    _review(dialog, app, workers)
    _answer(monkeypatch, accept=True)
    _click(dialog.flash_button)
    stop_clicks = []

    def during_command(command):
        if command[3:] == ("reboot",) and stop_at_final_reboot:
            assert dialog.cancel_button.isVisible() and dialog.cancel_button.isEnabled()
            _click(dialog.cancel_button)
            stop_clicks.append(command)

    # Restore this inert callback at teardown: otherwise it retains a cycle from
    # phone -> callback -> dialog -> executor -> phone across later Qt tests.
    monkeypatch.setattr(context.phone, "on_change", during_command)
    _finish_worker(app, workers)
    assert dialog.result.state is LocalFlashState.COMPLETED
    assert dialog.result.completed_count == 53
    assert dialog.result.reboot_requested
    assert not dialog.result.boot_verified
    assert len(context.phone.changes) == 53
    record = json.loads(dialog.result.receipt_path.read_text())
    assert record["state"] == "completed"
    assert record["boot_verified"] is False
    if stop_at_final_reboot:
        assert len(stop_clicks) == 1
        assert workers == []
        assert dialog.worker is None and not dialog.monitoring
        assert not dialog.boot_timer.isActive()
        assert "not started because you requested Stop" in dialog.status.text()
        # The user can still explicitly ask for that separate read-only check.
        _click(dialog.boot_button)
        assert len(workers) == 1 and isinstance(workers[0], LocalBootWorker)
        assert workers[0].flash_result is dialog.result
        assert len(context.phone.changes) == 53
    else:
        assert stop_clicks == []
        assert dialog.monitoring
        assert len(workers) == 1 and isinstance(workers[0], LocalBootWorker)
