from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from romverse.core.settings import AppSettings, ExperienceMode
from romverse.device.models import DeviceState
from romverse.guardian.recovery_execution import RecoveryStepOutcome
from romverse.repair.autopilot import RecoveryIncidentState
from romverse.rom.boot_observation import BootObservationService
from romverse.ui.main_window import MainWindow
from romverse.ui.recovery_operation_session import (
    RecoveryOperationPhase,
    RecoveryOperationSession,
    RecoveryOperationSessionError,
)
from tests.test_guardian_recovery_adapter_runner import _runner_context
from tests.test_recovery_execution_reassessment import _results
from tests.test_recovery_execution_verification import _completed_context


def _boot_devices(grant):
    first = replace(
        grant.reviewed_device,
        state=DeviceState.DEVICE,
        boot_completed=True,
        uptime_seconds=600,
    )
    return first, replace(first, uptime_seconds=910)


def test_session_automatically_carries_completed_result_to_verified_same_incident(
    tmp_path,
    monkeypatch,
) -> None:
    executions, grant, prepared, results, aggregate, reassessed, autopilot = _completed_context(
        tmp_path,
        monkeypatch,
    )
    now = datetime.now(UTC)
    started = now - timedelta(seconds=300)
    observed_at = [started]
    session = RecoveryOperationSession(
        prepared,
        results,
        autopilot,
        BootObservationService(executions.store, autopilot.registry),
        clock=lambda: observed_at[0],
    )
    initial = session.snapshot()
    assert initial.phase is RecoveryOperationPhase.WAITING_FOR_ANDROID
    assert initial.incident_id == reassessed.incident_id == aggregate.incident_id
    assert initial.result_digest == aggregate.result_digest
    assert initial.incident_state is RecoveryIncidentState.VERIFYING
    assert initial.execution_authority == "none"
    assert not initial.automatic_retry_allowed
    assert not initial.bootloader_relock_allowed

    first, _stable = _boot_devices(grant)
    unrelated = replace(first, serial="another-phone")
    observing = session.accept_scan((unrelated, first))
    assert observing.phase is RecoveryOperationPhase.OBSERVING_BOOT
    assert observing.boot_observation_digest
    assert not observing.recovered

    for elapsed in (60, 120, 180, 240):
        observed_at[0] = started + timedelta(seconds=elapsed)
        intermediate = session.accept_scan(
            (replace(first, uptime_seconds=600 + elapsed), unrelated)
        )
        assert intermediate.phase is RecoveryOperationPhase.OBSERVING_BOOT
        assert not intermediate.recovered

    observed_at[0] = now
    verified = session.accept_scan((replace(first, uptime_seconds=900), unrelated))
    assert verified.phase is RecoveryOperationPhase.VERIFIED
    assert verified.recovered
    assert verified.terminal
    assert not verified.can_observe
    assert verified.incident_id == reassessed.incident_id
    assert session.incident.state is RecoveryIncidentState.RECOVERED
    assert session.incident.repaired
    assert session.incident.verified_reboot
    assert session.incident.boot_observation_digest == verified.boot_observation_digest
    assert grant.target_serial not in repr(verified)


def test_session_waits_for_exact_phone_and_android_without_polluting_boot_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    executions, grant, prepared, results, _aggregate, reassessed, autopilot = _completed_context(
        tmp_path,
        monkeypatch,
    )
    service = BootObservationService(executions.store, autopilot.registry)
    session = RecoveryOperationSession(prepared, results, autopilot, service)
    path = executions.store.projects_root / prepared.project_id / service.NAME
    exact, _stable = _boot_devices(grant)
    wrong = replace(exact, serial="same-model-different-phone")

    missing = session.accept_scan(())
    substituted = session.accept_scan((wrong,))
    wrong_mode = session.accept_scan((grant.reviewed_device,))
    ambiguous = session.accept_scan((exact, replace(exact, boot_completed=False)))

    assert all(
        snapshot.phase is RecoveryOperationPhase.WAITING_FOR_ANDROID
        for snapshot in (missing, substituted, wrong_mode, ambiguous)
    )
    assert all(snapshot.waiting_for_exact_device for snapshot in (missing, substituted))
    assert not path.exists()
    assert autopilot.load(reassessed.incident_id) == reassessed
    assert not session.incident.repaired


@pytest.mark.parametrize(
    ("terminal", "phase"),
    [
        ("failed", RecoveryOperationPhase.STOPPED_FAILED),
        ("unknown", RecoveryOperationPhase.STOPPED_UNKNOWN),
    ],
)
def test_session_stops_failed_or_unknown_result_without_observation_or_retry(
    tmp_path,
    monkeypatch,
    terminal,
    phase,
) -> None:
    runner, executions, grant, prepared, adapter, *_transport, autopilot = _runner_context(
        tmp_path,
        monkeypatch,
    )
    if terminal == "failed":
        adapter.outcome = RecoveryStepOutcome.FAILED
    else:
        adapter.raise_error = True
    runner.execute_next(grant, prepared, adapter)
    calls = len(adapter.calls)
    results = _results(executions)
    results.record(prepared)
    service = BootObservationService(executions.store, autopilot.registry)
    session = RecoveryOperationSession(prepared, results, autopilot, service)
    before = session.snapshot()
    device, _stable = _boot_devices(grant)

    after = session.accept_scan((device,))

    assert before.phase is phase
    assert after == before
    assert after.terminal
    assert not after.can_observe
    assert not after.recovered
    assert not after.automatic_retry_allowed
    assert len(adapter.calls) == calls
    assert not (executions.store.projects_root / prepared.project_id / service.NAME).exists()
    assert session.incident.state is RecoveryIncidentState.EMERGENCY
    assert not session.incident.repaired


def test_session_stops_on_boot_attention_without_looping_or_inferring_repair(
    tmp_path,
    monkeypatch,
) -> None:
    executions, grant, prepared, results, _aggregate, reassessed, autopilot = _completed_context(
        tmp_path,
        monkeypatch,
    )
    now = datetime.now(UTC)
    session = RecoveryOperationSession(
        prepared,
        results,
        autopilot,
        BootObservationService(executions.store, autopilot.registry),
        clock=lambda: now,
    )
    timed_out = replace(
        grant.reviewed_device,
        state=DeviceState.DEVICE,
        boot_completed=False,
        uptime_seconds=1_300,
    )

    attention = session.accept_scan((timed_out,))
    retained_receipt = session.boot_receipt
    ignored = session.accept_scan((replace(timed_out, boot_completed=True),))

    assert attention.phase is RecoveryOperationPhase.ATTENTION
    assert attention.terminal
    assert not attention.recovered
    assert ignored == attention
    assert session.boot_receipt == retained_receipt
    assert autopilot.load(reassessed.incident_id) == reassessed
    assert not session.incident.repaired


def test_session_rejects_split_context_and_malformed_scan_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    executions, _grant, prepared, results, _aggregate, _reassessed, autopilot = _completed_context(
        tmp_path, monkeypatch
    )
    other_service = BootObservationService(executions.store, type(autopilot.registry)(()))
    with pytest.raises(RecoveryOperationSessionError, match="one exact local evidence context"):
        RecoveryOperationSession(prepared, results, autopilot, other_service)

    session = RecoveryOperationSession(
        prepared,
        results,
        autopilot,
        BootObservationService(executions.store, autopilot.registry),
    )
    with pytest.raises(RecoveryOperationSessionError, match="invalid shape"):
        session.accept_scan((object(),))


def test_main_window_owns_one_session_across_mode_changes_and_scan_continuation(
    tmp_path,
    monkeypatch,
) -> None:
    executions, grant, prepared, results, _aggregate, _reassessed, autopilot = _completed_context(
        tmp_path,
        monkeypatch,
    )
    app = QApplication.instance() or QApplication([])
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        executions.store.workspace,
        pack_registry=autopilot.registry,
        app_icon_path=logo,
        app_settings=AppSettings(
            experience_mode=ExperienceMode.GUIDED,
            online_intelligence_enabled=False,
            desktop_notifications_enabled=False,
            reduced_motion=True,
        ),
    )
    try:
        session = window._begin_recovery_result_handoff(prepared, results)
        assert session is not None
        assert session.parent() is window
        assert window._begin_recovery_result_handoff(prepared, results) is session
        assert window._recovery_operation_session is session
        assert window.repair_center.autopilot_incident == session.incident

        window._apply_experience_mode(ExperienceMode.EXPERT)
        assert window._recovery_operation_session is session
        assert session.phase is RecoveryOperationPhase.WAITING_FOR_ANDROID

        now = datetime.now(UTC)
        session.clock = lambda: now - timedelta(seconds=310)
        first, stable = _boot_devices(grant)
        window._advance_recovery_operation_session([first])
        assert session.phase is RecoveryOperationPhase.OBSERVING_BOOT
        session.clock = lambda: now
        window._advance_recovery_operation_session([stable])

        assert window._recovery_operation_session is session
        assert session.phase is RecoveryOperationPhase.VERIFIED
        assert window.repair_center.autopilot_incident == session.incident
        assert window.repair_center.autopilot_incident.repaired
    finally:
        window.companion_center.transport.close()
        window.close()
        app.processEvents()
