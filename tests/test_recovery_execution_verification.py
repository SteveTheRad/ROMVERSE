from __future__ import annotations

import inspect
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from romverse.device.models import DeviceState
from romverse.guardian.recovery_execution import RecoveryStepOutcome
from romverse.repair.autopilot import (
    RecoveryAutopilotError,
    RecoveryAutopilotService,
    RecoveryIncidentState,
)
from romverse.rom.boot_observation import BootObservationService, BootObservationStatus
from romverse.rom.models import ProjectError
from tests.test_boot_observation import _verified_flash
from tests.test_guardian_recovery_adapter_runner import _runner_context
from tests.test_recovery_execution_reassessment import _complete, _results


def _completed_context(tmp_path, monkeypatch):
    runner, executions, grant, prepared, adapter, *_transport, autopilot = _runner_context(
        tmp_path,
        monkeypatch,
    )
    _complete(runner, grant, prepared, adapter)
    results = _results(executions)
    aggregate = results.record(prepared)
    reassessed = autopilot.reassess_execution(prepared, results)
    return executions, grant, prepared, results, aggregate, reassessed, autopilot


def _stable_recovery_boot(
    executions,
    autopilot,
    grant,
    prepared,
    results,
    *,
    started: datetime | None = None,
):
    observations = BootObservationService(executions.store, autopilot.registry)
    started = started or (datetime.now(UTC) - timedelta(seconds=310))
    first_device = replace(
        grant.reviewed_device,
        state=DeviceState.DEVICE,
        boot_completed=True,
        uptime_seconds=600,
    )
    observations.observe_recovery(
        prepared.project_id,
        first_device,
        prepared,
        results,
        started,
    )
    current_device = replace(first_device, uptime_seconds=910)
    receipt = observations.observe_recovery(
        prepared.project_id,
        current_device,
        prepared,
        results,
        started + timedelta(seconds=310),
    )
    return (
        BootObservationService(executions.store, autopilot.registry),
        current_device,
        receipt,
    )


def test_completed_recovery_requires_fresh_stable_exact_device_boot_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    executions, grant, prepared, results, aggregate, reassessed, autopilot = _completed_context(
        tmp_path,
        monkeypatch,
    )
    observations, device, receipt = _stable_recovery_boot(
        executions,
        autopilot,
        grant,
        prepared,
        results,
    )
    assert receipt.status is BootObservationStatus.STABLE
    assert receipt.stable
    assert receipt.flash_linked
    assert receipt.guardian_execution_receipt_digest == aggregate.result_digest
    assert receipt.verified_first_boot

    verified = autopilot.verify_execution_recovery(
        prepared,
        results,
        observations,
        device,
    )

    assert verified.incident_id == reassessed.incident_id == aggregate.incident_id
    assert verified.state is RecoveryIncidentState.RECOVERED
    assert verified.repaired
    assert verified.verified_reboot
    assert not verified.phone_changed
    assert verified.routes == ()
    assert verified.mode == "adb"
    assert verified.boot_observation_digest == receipt.receipt_digest
    assert "fresh exact-device evidence" in verified.diagnosis.casefold()
    event = verified.events[-1]
    assert event.event_type == autopilot.EXECUTION_VERIFIED_EVENT
    assert event.state is RecoveryIncidentState.RECOVERED
    assert event.evidence_digest not in {aggregate.result_digest, receipt.receipt_digest}
    assert (
        autopilot.verify_execution_recovery(
            prepared,
            results,
            observations,
            device,
        )
        == verified
    )
    serialized = (autopilot.root / f"{verified.incident_id}{autopilot.SUFFIX}").read_text(
        encoding="utf-8"
    )
    assert grant.target_serial not in serialized


def test_recovery_boot_observation_starts_fresh_after_an_older_unlinked_session(
    tmp_path,
    monkeypatch,
) -> None:
    executions, grant, prepared, results, aggregate, _reassessed, autopilot = _completed_context(
        tmp_path,
        monkeypatch,
    )
    observations = BootObservationService(executions.store, autopilot.registry)
    device = replace(
        grant.reviewed_device,
        state=DeviceState.DEVICE,
        boot_completed=True,
        uptime_seconds=600,
    )
    result_time = datetime.fromisoformat(aggregate.recorded_at)
    older = observations.observe(
        prepared.project_id,
        device,
        result_time - timedelta(minutes=10),
    )
    assert not older.flash_linked
    recovery_start = datetime.now(UTC) - timedelta(seconds=310)

    fresh = observations.observe_recovery(
        prepared.project_id,
        device,
        prepared,
        results,
        recovery_start,
    )
    stable = observations.observe_recovery(
        prepared.project_id,
        replace(device, uptime_seconds=910),
        prepared,
        results,
        recovery_start + timedelta(seconds=310),
    )

    assert len(fresh.samples) == 1
    assert fresh.samples[0].observed_at == recovery_start.isoformat()
    assert fresh.flash_linked
    assert fresh.guardian_execution_receipt_digest == aggregate.result_digest
    assert stable.status is BootObservationStatus.STABLE
    assert stable.verified_first_boot


def test_recovery_boot_observation_replaces_valid_older_link_after_restart(
    tmp_path,
    monkeypatch,
) -> None:
    executions, grant, prepared, results, aggregate, _reassessed, autopilot = _completed_context(
        tmp_path,
        monkeypatch,
    )
    project = executions.store.get(prepared.project_id)
    device = replace(
        grant.reviewed_device,
        state=DeviceState.DEVICE,
        boot_completed=True,
        uptime_seconds=600,
    )
    result_time = datetime.fromisoformat(aggregate.recorded_at)
    older_completion = result_time - timedelta(minutes=30)
    older_result = _verified_flash(
        executions.store,
        project,
        device,
        older_completion,
    )
    older_service = BootObservationService(executions.store, autopilot.registry)
    older = older_service.observe(
        prepared.project_id,
        device,
        older_completion + timedelta(seconds=5),
        verified_flash=older_result,
    )
    assert older.flash_linked
    assert older.guardian_execution_receipt_digest == older_result.signed_receipt_sha256

    restarted = BootObservationService(executions.store, autopilot.registry)
    recovery_start = result_time + timedelta(seconds=1)
    evidence_path = executions.store.projects_root / prepared.project_id / restarted.NAME
    original = evidence_path.read_text(encoding="utf-8")
    tampered = json.loads(original)
    tampered["status"] = BootObservationStatus.ATTENTION.value
    evidence_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ProjectError, match="will not be overwritten"):
        restarted.observe_recovery(
            prepared.project_id,
            device,
            prepared,
            results,
            recovery_start,
        )
    assert evidence_path.read_text(encoding="utf-8") == json.dumps(tampered)
    evidence_path.write_text(original, encoding="utf-8")

    fresh = restarted.observe_recovery(
        prepared.project_id,
        device,
        prepared,
        results,
        recovery_start,
    )

    assert len(fresh.samples) == 1
    assert fresh.samples[0].observed_at == recovery_start.isoformat()
    assert fresh.flash_linked
    assert fresh.guardian_execution_receipt_digest == aggregate.result_digest
    assert fresh.guardian_execution_receipt_digest != older_result.signed_receipt_sha256


@pytest.mark.parametrize("terminal", ["failed", "unknown"])
def test_failed_or_unknown_execution_is_ineligible_for_verification(
    tmp_path,
    monkeypatch,
    terminal,
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
    results = _results(executions)
    results.record(prepared)
    stopped = autopilot.reassess_execution(prepared, results)
    observations = BootObservationService(executions.store, autopilot.registry)
    visible = replace(
        grant.reviewed_device,
        state=DeviceState.DEVICE,
        boot_completed=True,
        uptime_seconds=600,
    )

    with pytest.raises(ProjectError, match="completed Recovery result"):
        observations.observe_recovery(
            prepared.project_id,
            visible,
            prepared,
            results,
            datetime.now(UTC),
        )

    with pytest.raises(RecoveryAutopilotError, match="Only a completed exact sequence"):
        autopilot.verify_execution_recovery(
            prepared,
            results,
            observations,
            replace(
                grant.reviewed_device,
                state=DeviceState.DEVICE,
                boot_completed=True,
            ),
        )
    assert autopilot.load(stopped.incident_id) == stopped
    assert not stopped.repaired


def test_verification_rejects_same_model_different_phone_and_live_identity_drift(
    tmp_path,
    monkeypatch,
) -> None:
    executions, grant, prepared, results, _aggregate, reassessed, autopilot = _completed_context(
        tmp_path,
        monkeypatch,
    )
    observations, device, _receipt = _stable_recovery_boot(
        executions,
        autopilot,
        grant,
        prepared,
        results,
    )

    with pytest.raises(RecoveryAutopilotError, match="exact Recovery phone"):
        autopilot.verify_execution_recovery(
            prepared,
            results,
            observations,
            replace(device, serial="same-model-different-physical-phone"),
        )
    assert autopilot.load(reassessed.incident_id) == reassessed

    for changed in (
        replace(device, build_fingerprint="changed/after/boot-observation"),
        replace(device, slot_suffix="_b"),
        replace(device, state=DeviceState.OFFLINE, boot_completed=None),
    ):
        with pytest.raises(RecoveryAutopilotError, match="fresh stable boot evidence"):
            autopilot.verify_execution_recovery(
                prepared,
                results,
                observations,
                changed,
            )
        assert autopilot.load(reassessed.incident_id) == reassessed


def test_verification_rejects_stale_pre_execution_or_incomplete_boot_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    executions, grant, prepared, results, aggregate, reassessed, autopilot = _completed_context(
        tmp_path,
        monkeypatch,
    )
    too_early = BootObservationService(executions.store, autopilot.registry)
    with pytest.raises(ProjectError, match="completed Recovery result"):
        too_early.observe_recovery(
            prepared.project_id,
            replace(
                grant.reviewed_device,
                state=DeviceState.DEVICE,
                boot_completed=True,
                uptime_seconds=600,
            ),
            prepared,
            results,
            datetime.fromisoformat(aggregate.recorded_at) - timedelta(seconds=1),
        )

    stale, stale_device, stale_receipt = _stable_recovery_boot(
        executions,
        autopilot,
        grant,
        prepared,
        results,
        started=datetime.fromisoformat(aggregate.recorded_at) + timedelta(seconds=1),
    )
    assert stale_receipt.status is BootObservationStatus.STABLE
    with pytest.raises(RecoveryAutopilotError, match="fresh stable boot evidence"):
        autopilot.verify_execution_recovery(prepared, results, stale, stale_device)
    assert autopilot.load(reassessed.incident_id) == reassessed

    evidence_path = executions.store.projects_root / prepared.project_id / stale.NAME
    evidence_path.unlink()
    incomplete = BootObservationService(executions.store, autopilot.registry)
    current = replace(
        grant.reviewed_device,
        state=DeviceState.DEVICE,
        boot_completed=True,
        uptime_seconds=600,
    )
    waiting = incomplete.observe_recovery(
        prepared.project_id,
        current,
        prepared,
        results,
        datetime.now(UTC),
    )
    assert waiting.status is BootObservationStatus.WAITING
    with pytest.raises(RecoveryAutopilotError, match="fresh stable boot evidence"):
        autopilot.verify_execution_recovery(prepared, results, incomplete, current)
    assert autopilot.load(reassessed.incident_id) == reassessed


def test_verification_rejects_tampered_boot_receipt_or_reassessment_history(
    tmp_path,
    monkeypatch,
) -> None:
    executions, grant, prepared, results, _aggregate, reassessed, autopilot = _completed_context(
        tmp_path,
        monkeypatch,
    )
    observations, device, _receipt = _stable_recovery_boot(
        executions,
        autopilot,
        grant,
        prepared,
        results,
    )
    path = executions.store.projects_root / prepared.project_id / observations.NAME
    original = path.read_text(encoding="utf-8")
    document = json.loads(original)
    document["status"] = BootObservationStatus.ATTENTION.value
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(RecoveryAutopilotError, match="incomplete or unreadable"):
        autopilot.verify_execution_recovery(prepared, results, observations, device)
    assert autopilot.load(reassessed.incident_id) == reassessed
    path.write_text(original, encoding="utf-8")

    forged_event = replace(reassessed.events[-1], evidence_digest="f" * 64)
    forged = autopilot._seal(
        replace(
            reassessed,
            events=(*reassessed.events[:-1], forged_event),
            record_digest="",
        )
    )
    autopilot._save(forged)
    with pytest.raises(RecoveryAutopilotError, match="exact reassessed incident"):
        autopilot.verify_execution_recovery(prepared, results, observations, device)
    assert autopilot.load(reassessed.incident_id) == forged


def test_verification_api_has_no_repair_outcome_or_authority_override() -> None:
    assert list(
        inspect.signature(RecoveryAutopilotService.verify_execution_recovery).parameters
    ) == [
        "self",
        "preparation",
        "execution_results",
        "boot_observations",
        "device",
    ]
    observe_parameters = list(inspect.signature(BootObservationService.observe_recovery).parameters)
    assert observe_parameters == [
        "self",
        "project_id",
        "device",
        "preparation",
        "execution_results",
        "observed_at",
    ]


def test_recovery_boot_observation_rejects_naive_time(
    tmp_path,
    monkeypatch,
) -> None:
    executions, grant, prepared, results, _aggregate, _reassessed, autopilot = _completed_context(
        tmp_path,
        monkeypatch,
    )
    observations = BootObservationService(executions.store, autopilot.registry)

    with pytest.raises(ProjectError, match="timezone"):
        observations.observe_recovery(
            prepared.project_id,
            replace(
                grant.reviewed_device,
                state=DeviceState.DEVICE,
                boot_completed=True,
                uptime_seconds=600,
            ),
            prepared,
            results,
            datetime(2026, 9, 5, 12, 0),
        )
