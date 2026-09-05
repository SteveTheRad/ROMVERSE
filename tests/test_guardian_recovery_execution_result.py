from __future__ import annotations

import hashlib
import inspect
import json
from datetime import datetime

import pytest

from romverse.guardian.recovery_adapter_runner import RecoveryAdapterRunState
from romverse.guardian.recovery_execution import (
    RecoveryExecutionValidationError,
    RecoveryStepOutcome,
)
from romverse.guardian.recovery_execution_result import (
    GuardianRecoveryExecutionResultService,
    RecoveryExecutionResultState,
    RecoveryExecutionResultValidationError,
)
from romverse.guardian.recovery_step_target import RecoveryStepTargetPhase
from tests.test_guardian_recovery_adapter_runner import _runner_context


def _service(executions, *, clock=None):
    return GuardianRecoveryExecutionResultService(
        executions,
        clock=clock or executions.clock,
    )


def _complete(runner, grant, prepared, adapter):
    runs = [runner.execute_next(grant, prepared, adapter) for _step in prepared.steps]
    assert all(item.state is RecoveryAdapterRunState.STEP_SUCCEEDED for item in runs)
    return runs


def _reseal(document: dict[str, object], digest_field: str) -> None:
    unsigned = {
        key: value for key, value in document.items() if key not in {"format", digest_field}
    }
    document[digest_field] = hashlib.sha256(
        json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def test_aggregate_derives_completed_sequence_without_claiming_repair(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, _adb, _fastboot, autopilot = _runner_context(
        tmp_path, monkeypatch
    )
    _complete(runner, grant, prepared, adapter)
    incident_before = autopilot.load(prepared.incident_id)

    result = _service(executions).record(prepared)

    assert result.state is RecoveryExecutionResultState.SEQUENCE_COMPLETED_AWAITING_REASSESSMENT
    assert result.incident_id == prepared.incident_id
    assert result.incident_record_digest == prepared.incident_record_digest
    assert result.claim_digest == grant.claim.claim_digest
    assert result.preparation_digest == prepared.preparation_digest
    assert result.adapter_package_sha256 == adapter.package_sha256
    assert result.journal_entry_count == result.step_count == prepared.step_count
    assert result.completed_step_count == prepared.step_count
    assert result.terminal_step_order == prepared.step_count
    assert all(item.outcome is RecoveryStepOutcome.SUCCEEDED for item in result.journal_entries)
    assert result.sequence_actions_completed
    assert not result.known_failure_recorded
    assert not result.unknown_outcome_recorded
    assert result.same_incident_preserved
    assert result.recovery_reassessment_required
    assert result.post_repair_verification_required
    assert not result.recovery_verified
    assert not result.device_repaired
    assert result.execution_authority == "none"
    assert not result.automatic_retry_allowed
    assert not result.bootloader_relock_allowed
    assert autopilot.load(prepared.incident_id) == incident_before
    assert _service(executions).load(prepared) == result
    serialized = executions.aggregate_result_path(prepared).read_text(encoding="utf-8")
    assert grant.target_serial not in serialized
    assert grant.ephemeral_token not in serialized
    with pytest.raises(RecoveryExecutionResultValidationError, match="already has"):
        _service(executions).record(prepared)


def test_aggregate_derives_known_failure_and_preserves_same_incident(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )
    adapter.outcome = RecoveryStepOutcome.FAILED
    run = runner.execute_next(grant, prepared, adapter)
    assert run.state is RecoveryAdapterRunState.STEP_FAILED

    result = _service(executions).record(prepared)

    assert result.state is RecoveryExecutionResultState.FAILED_AWAITING_REASSESSMENT
    assert result.incident_id == prepared.incident_id
    assert result.terminal_step_order == 1
    assert result.completed_step_count == 0
    assert result.known_failure_recorded
    assert not result.sequence_actions_completed
    assert not result.device_repaired


@pytest.mark.parametrize("runner_outcome", ["explicit", "missing"])
def test_aggregate_preserves_unknown_and_closes_blind_retry_path(
    tmp_path,
    monkeypatch,
    runner_outcome,
) -> None:
    runner, executions, grant, prepared, adapter, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )
    if runner_outcome == "explicit":
        adapter.raise_error = True
        run = runner.execute_next(grant, prepared, adapter)
        assert run.state is RecoveryAdapterRunState.STEP_UNKNOWN
        intent = run.intent
    else:
        witness = runner.targets.observe(
            grant,
            prepared,
            1,
            RecoveryStepTargetPhase.PRE_DISPATCH,
        )
        intent = executions.record_step_intent(
            grant,
            prepared,
            1,
            witness,
            adapter.verified_package,
        )
    assert intent is not None

    result = _service(executions).record(prepared)

    assert result.state is RecoveryExecutionResultState.UNKNOWN_AWAITING_RECONSTRUCTION
    assert result.journal_entries[0].outcome is RecoveryStepOutcome.UNKNOWN
    assert result.unknown_outcome_recorded
    assert not result.automatic_retry_allowed
    with pytest.raises(RecoveryExecutionValidationError, match="aggregate result"):
        executions.record_step_result(
            grant,
            prepared,
            intent,
            outcome=RecoveryStepOutcome.FAILED,
            operation_dispatched=True,
            observed_result_sha256="a" * 64,
            observed_next_mode=intent.from_mode,
        )
    with pytest.raises(RecoveryExecutionValidationError, match="aggregate result"):
        executions.record_step_intent(
            grant,
            prepared,
            1,
            runner.targets.observe(
                grant,
                prepared,
                1,
                RecoveryStepTargetPhase.PRE_DISPATCH,
            ),
            adapter.verified_package,
        )


def test_aggregate_preserves_completed_prefix_before_unknown_step(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )
    first = runner.execute_next(grant, prepared, adapter)
    assert first.state is RecoveryAdapterRunState.STEP_SUCCEEDED
    witness = runner.targets.observe(
        grant,
        prepared,
        2,
        RecoveryStepTargetPhase.PRE_DISPATCH,
    )
    executions.record_step_intent(
        grant,
        prepared,
        2,
        witness,
        adapter.verified_package,
    )

    result = _service(executions).record(prepared)

    assert result.state is RecoveryExecutionResultState.UNKNOWN_AWAITING_RECONSTRUCTION
    assert result.completed_step_count == 1
    assert result.terminal_step_order == 2
    assert [item.outcome for item in result.journal_entries] == [
        RecoveryStepOutcome.SUCCEEDED,
        RecoveryStepOutcome.UNKNOWN,
    ]
    assert not result.automatic_retry_allowed


def test_aggregate_refuses_empty_or_in_progress_nonterminal_journal(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )
    with pytest.raises(RecoveryExecutionResultValidationError, match="no started"):
        _service(executions).record(prepared)

    first = runner.execute_next(grant, prepared, adapter)
    assert first.state is RecoveryAdapterRunState.STEP_SUCCEEDED
    with pytest.raises(RecoveryExecutionResultValidationError, match="waiting to start"):
        _service(executions).record(prepared)
    assert not executions.aggregate_result_path(prepared).exists()


def test_malformed_result_after_intent_is_conservatively_unknown(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )
    witness = runner.targets.observe(
        grant,
        prepared,
        1,
        RecoveryStepTargetPhase.PRE_DISPATCH,
    )
    executions.record_step_intent(
        grant,
        prepared,
        1,
        witness,
        adapter.verified_package,
    )
    executions._result_path(prepared, 1).write_text("not-json", encoding="utf-8")

    result = _service(executions).record(prepared)

    assert result.state is RecoveryExecutionResultState.UNKNOWN_AWAITING_RECONSTRUCTION
    assert result.journal_entries[0].result_digest == ""


@pytest.mark.parametrize("unexpected", ["step-99-intent.romverse", ".hidden-evidence"])
def test_aggregate_rejects_later_or_hidden_journal_evidence(
    tmp_path,
    monkeypatch,
    unexpected,
) -> None:
    runner, executions, grant, prepared, adapter, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )
    adapter.outcome = RecoveryStepOutcome.FAILED
    runner.execute_next(grant, prepared, adapter)
    (executions._root(prepared) / unexpected).write_text("{}", encoding="utf-8")

    with pytest.raises(RecoveryExecutionResultValidationError, match="evidence"):
        _service(executions).record(prepared)


def test_aggregate_rejects_adapter_package_identity_drift_inside_journal(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )
    _complete(runner, grant, prepared, adapter)
    path = executions._intent_path(prepared, 2)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["adapter_package_id"] = "test.drifted.package"
    _reseal(document, "intent_digest")
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(RecoveryExecutionResultValidationError, match="adapter package"):
        _service(executions).record(prepared)


def test_aggregate_record_is_derived_not_editable_even_when_redigested(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )
    adapter.outcome = RecoveryStepOutcome.FAILED
    runner.execute_next(grant, prepared, adapter)
    service = _service(executions)
    service.record(prepared)
    path = executions.aggregate_result_path(prepared)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["state"] = RecoveryExecutionResultState.SEQUENCE_COMPLETED_AWAITING_REASSESSMENT.value
    document["sequence_actions_completed"] = True
    document["known_failure_recorded"] = False
    _reseal(document, "result_digest")
    path.write_text(json.dumps(document), encoding="utf-8")

    assert service.load(prepared) is None
    with pytest.raises(RecoveryExecutionResultValidationError, match="already has"):
        service.record(prepared)


def test_underlying_journal_tamper_invalidates_loaded_aggregate(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )
    _complete(runner, grant, prepared, adapter)
    service = _service(executions)
    service.record(prepared)
    executions._result_path(prepared, prepared.step_count).write_text("{}", encoding="utf-8")

    assert service.load(prepared) is None


@pytest.mark.parametrize("hostile", ["duplicate", "extra", "symlink"])
def test_aggregate_loader_rejects_hostile_or_linked_records(
    tmp_path,
    monkeypatch,
    hostile,
) -> None:
    runner, executions, grant, prepared, adapter, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )
    adapter.outcome = RecoveryStepOutcome.FAILED
    runner.execute_next(grant, prepared, adapter)
    service = _service(executions)
    service.record(prepared)
    path = executions.aggregate_result_path(prepared)
    original = path.read_text(encoding="utf-8")
    if hostile == "duplicate":
        document = json.loads(original)
        marker = f'"format": "{document["format"]}",'
        path.write_text(original.replace(marker, f"{marker}\n  {marker}", 1), encoding="utf-8")
    elif hostile == "extra":
        document = json.loads(original)
        document["repaired"] = True
        path.write_text(json.dumps(document), encoding="utf-8")
    else:
        outside = tmp_path / "outside-aggregate.romverse"
        outside.write_text(original, encoding="utf-8")
        path.unlink()
        path.symlink_to(outside)

    assert service.load(prepared) is None


def test_aggregate_rejects_naive_clock_and_exposes_no_state_setter(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )
    adapter.outcome = RecoveryStepOutcome.FAILED
    runner.execute_next(grant, prepared, adapter)

    with pytest.raises(RecoveryExecutionResultValidationError, match="timezone-aware"):
        _service(executions, clock=lambda: datetime(2026, 9, 5)).record(prepared)
    assert list(inspect.signature(GuardianRecoveryExecutionResultService.record).parameters) == [
        "self",
        "preparation",
    ]
    assert not executions.aggregate_result_path(prepared).exists()
