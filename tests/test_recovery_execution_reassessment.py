from __future__ import annotations

import inspect
import json
from dataclasses import replace

import pytest

from romverse.device.models import DeviceState
from romverse.guardian.recovery_execution import RecoveryStepOutcome
from romverse.guardian.recovery_execution_result import (
    GuardianRecoveryExecutionResultService,
    RecoveryExecutionResultState,
)
from romverse.repair.autopilot import (
    RecoveryAutopilotContext,
    RecoveryAutopilotError,
    RecoveryAutopilotService,
    RecoveryIncidentState,
    RecoveryTrigger,
)
from tests.test_guardian_recovery_adapter_runner import _runner_context


def _results(executions):
    return GuardianRecoveryExecutionResultService(executions, clock=executions.clock)


def _complete(runner, grant, prepared, adapter) -> None:
    for _step in prepared.steps:
        run = runner.execute_next(grant, prepared, adapter)
        assert run.durable_outcome is RecoveryStepOutcome.SUCCEEDED


def test_completed_sequence_advances_same_incident_only_to_verification_boundary(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_transport, autopilot = _runner_context(
        tmp_path,
        monkeypatch,
    )
    _complete(runner, grant, prepared, adapter)
    results = _results(executions)
    aggregate = results.record(prepared)
    before = autopilot.load(prepared.incident_id)

    reassessed = autopilot.reassess_execution(prepared, results)

    assert reassessed.incident_id == before.incident_id == aggregate.incident_id
    assert reassessed.record_digest != before.record_digest
    assert reassessed.state is RecoveryIncidentState.VERIFYING
    assert reassessed.routes == ()
    assert not reassessed.repaired
    assert not reassessed.verified_reboot
    assert not reassessed.phone_changed
    assert "not declared" in reassessed.diagnosis
    event = reassessed.events[-1]
    assert event.event_type == autopilot.EXECUTION_COMPLETED_EVENT
    assert event.state is RecoveryIncidentState.VERIFYING
    assert event.evidence_digest == aggregate.result_digest
    assert results.load(prepared) == aggregate
    assert autopilot.reassess_execution(prepared, results) == reassessed
    with pytest.raises(RecoveryAutopilotError, match="no longer matches"):
        autopilot.record_route_result(
            reassessed.incident_id,
            prepared.route_id,
            "started",
            "A stale route must not run again.",
        )


@pytest.mark.parametrize(
    (
        "outcome",
        "aggregate_state",
        "event_name",
        "diagnosis_fragment",
        "safety_fragment",
    ),
    [
        (
            "failed",
            RecoveryExecutionResultState.FAILED_AWAITING_REASSESSMENT,
            RecoveryAutopilotService.EXECUTION_FAILED_EVENT,
            "known failure",
            "no action will be retried automatically",
        ),
        (
            "unknown",
            RecoveryExecutionResultState.UNKNOWN_AWAITING_RECONSTRUCTION,
            RecoveryAutopilotService.EXECUTION_UNKNOWN_EVENT,
            "unknown outcome",
            "will not blindly retry",
        ),
    ],
)
def test_failure_and_unknown_stop_without_retry_or_repair(
    tmp_path,
    monkeypatch,
    outcome,
    aggregate_state,
    event_name,
    diagnosis_fragment,
    safety_fragment,
) -> None:
    runner, executions, grant, prepared, adapter, *_transport, autopilot = _runner_context(
        tmp_path,
        monkeypatch,
    )
    if outcome == "failed":
        adapter.outcome = RecoveryStepOutcome.FAILED
    else:
        adapter.raise_error = True
    runner.execute_next(grant, prepared, adapter)
    results = _results(executions)
    aggregate = results.record(prepared)

    reassessed = autopilot.reassess_execution(prepared, results)

    assert aggregate.state is aggregate_state
    assert reassessed.incident_id == aggregate.incident_id
    assert reassessed.state is RecoveryIncidentState.EMERGENCY
    assert reassessed.routes == ()
    assert not reassessed.repaired
    assert not reassessed.verified_reboot
    assert diagnosis_fragment in reassessed.diagnosis
    assert safety_fragment in reassessed.diagnosis.casefold()
    assert reassessed.events[-1].event_type == event_name
    assert reassessed.events[-1].evidence_digest == aggregate.result_digest
    assert not aggregate.automatic_retry_allowed


@pytest.mark.parametrize(
    ("terminal", "expected_state"),
    [
        ("completed", RecoveryIncidentState.VERIFYING),
        ("failed", RecoveryIncidentState.EMERGENCY),
        ("unknown", RecoveryIncidentState.EMERGENCY),
    ],
)
def test_generic_refresh_cannot_reopen_or_reclassify_terminal_execution(
    tmp_path,
    monkeypatch,
    terminal,
    expected_state,
) -> None:
    runner, executions, grant, prepared, adapter, *_transport, autopilot = _runner_context(
        tmp_path,
        monkeypatch,
    )
    if terminal == "completed":
        _complete(runner, grant, prepared, adapter)
    else:
        if terminal == "failed":
            adapter.outcome = RecoveryStepOutcome.FAILED
        else:
            adapter.raise_error = True
        runner.execute_next(grant, prepared, adapter)
    results = _results(executions)
    aggregate = results.record(prepared)
    reassessed = autopilot.reassess_execution(prepared, results)
    visible_android = replace(
        grant.reviewed_device,
        state=DeviceState.DEVICE,
        boot_completed=True,
    )

    refreshed = autopilot.refresh(
        reassessed.incident_id,
        RecoveryAutopilotContext(
            RecoveryTrigger.BOOTLOOP,
            device=visible_android,
            project_id=prepared.project_id,
        ),
    )

    assert refreshed.state is expected_state
    assert refreshed.routes == ()
    assert not refreshed.repaired
    assert not refreshed.verified_reboot
    assert any(
        event.evidence_digest == aggregate.result_digest
        and event.event_type in autopilot.EXECUTION_REASSESSMENT_EVENTS
        for event in refreshed.events
    )
    assert autopilot.reassess_execution(prepared, results) == refreshed


def test_execution_reassessment_rejects_boot_evidence_until_independent_boundary(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_transport, autopilot = _runner_context(
        tmp_path,
        monkeypatch,
    )
    _complete(runner, grant, prepared, adapter)
    results = _results(executions)
    results.record(prepared)
    reassessed = autopilot.reassess_execution(prepared, results)

    with pytest.raises(RecoveryAutopilotError, match="independent verification"):
        autopilot.refresh(
            reassessed.incident_id,
            RecoveryAutopilotContext(
                RecoveryTrigger.BOOTLOOP,
                device=replace(
                    grant.reviewed_device,
                    state=DeviceState.DEVICE,
                    boot_completed=True,
                ),
                project_id=prepared.project_id,
                boot_observation=object(),  # rejected before any receipt can be attached
            ),
        )
    assert autopilot.load(reassessed.incident_id) == reassessed


def test_execution_gated_refresh_preserves_project_and_rejects_project_drift(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_transport, autopilot = _runner_context(
        tmp_path,
        monkeypatch,
    )
    adapter.raise_error = True
    runner.execute_next(grant, prepared, adapter)
    results = _results(executions)
    results.record(prepared)
    reassessed = autopilot.reassess_execution(prepared, results)
    visible_android = replace(
        grant.reviewed_device,
        state=DeviceState.DEVICE,
        boot_completed=True,
    )

    refreshed = autopilot.refresh(
        reassessed.incident_id,
        RecoveryAutopilotContext(
            RecoveryTrigger.BOOTLOOP,
            device=visible_android,
        ),
    )

    assert refreshed.project_id == reassessed.project_id
    assert refreshed.device_key == reassessed.device_key
    assert refreshed.pack_id == reassessed.pack_id
    assert refreshed.pack_sha256 == reassessed.pack_sha256
    with pytest.raises(RecoveryAutopilotError, match="different Recovery project"):
        autopilot.refresh(
            reassessed.incident_id,
            RecoveryAutopilotContext(
                RecoveryTrigger.BOOTLOOP,
                device=visible_android,
                project_id="different-project",
            ),
        )
    assert autopilot.load(reassessed.incident_id) == refreshed


def test_reassessment_rejects_changed_incident_or_tampered_aggregate(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_transport, autopilot = _runner_context(
        tmp_path,
        monkeypatch,
    )
    adapter.outcome = RecoveryStepOutcome.FAILED
    runner.execute_next(grant, prepared, adapter)
    results = _results(executions)
    results.record(prepared)
    changed = autopilot.record_route_result(
        prepared.incident_id,
        prepared.route_id,
        "reviewed",
        "Incident changed after execution result recording.",
    )

    with pytest.raises(RecoveryAutopilotError, match="exact active incident"):
        autopilot.reassess_execution(prepared, results)
    assert autopilot.load(prepared.incident_id) == changed

    path = executions.aggregate_result_path(prepared)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["automatic_retry_allowed"] = True
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(RecoveryAutopilotError, match="exact durable execution result"):
        autopilot.reassess_execution(prepared, results)
    assert autopilot.load(prepared.incident_id) == changed


def test_idempotent_reassessment_rejects_resealed_identity_or_outcome_drift(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_transport, autopilot = _runner_context(
        tmp_path,
        monkeypatch,
    )
    _complete(runner, grant, prepared, adapter)
    results = _results(executions)
    results.record(prepared)
    reassessed = autopilot.reassess_execution(prepared, results)
    forged = autopilot._seal(
        replace(
            reassessed,
            device_key="f" * 20,
            record_digest="",
        )
    )
    autopilot._save(forged)

    with pytest.raises(RecoveryAutopilotError, match="changed after"):
        autopilot.reassess_execution(prepared, results)
    assert autopilot.load(prepared.incident_id) == forged


def test_reassessment_requires_exact_local_service_and_has_no_outcome_override(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, _grant, prepared, adapter, *_transport, autopilot = _runner_context(
        tmp_path,
        monkeypatch,
    )
    adapter.outcome = RecoveryStepOutcome.FAILED
    runner.execute_next(_grant, prepared, adapter)
    results = _results(executions)
    results.record(prepared)
    other_workspace = tmp_path / "other-workspace"
    other_workspace.mkdir()
    original_workspace = results.store.workspace
    results.store.workspace = other_workspace
    try:
        with pytest.raises(RecoveryAutopilotError, match="different workspace"):
            autopilot.reassess_execution(prepared, results)
    finally:
        results.store.workspace = original_workspace

    assert list(inspect.signature(RecoveryAutopilotService.reassess_execution).parameters) == [
        "self",
        "preparation",
        "execution_results",
    ]
    assert autopilot.load(prepared.incident_id).routes
