from __future__ import annotations

import inspect
import json
from dataclasses import replace
from datetime import timedelta

import pytest

from romverse.guardian.recovery_execution import (
    GuardianRecoveryExecutionGrant,
    GuardianRecoveryExecutionService,
    RecoveryExecutionValidationError,
    RecoveryStepOutcome,
)
from romverse.guardian.recovery_preparation import GuardianRecoveryPreparationService
from romverse.guardian.recovery_step_target import (
    GuardianRecoveryStepTargetService,
    RecoveryStepTargetPhase,
)
from tests._recovery_adapter_trust import make_test_recovery_adapter_package
from tests.test_guardian_recovery_consent import _consent_context
from tests.test_guardian_recovery_live_target import _OBSERVED_AT


def _execution_context(tmp_path, monkeypatch):
    consents, target, prepared, phone, autopilot, adb, fastboot = _consent_context(
        tmp_path,
        monkeypatch,
    )
    grant = consents.issue(prepared, target, phone, confirmed=True)
    execution_time = _OBSERVED_AT + timedelta(seconds=60)
    consents.live_targets.clock = lambda: execution_time
    service = GuardianRecoveryExecutionService(
        consents,
        clock=lambda: execution_time,
    )
    return service, grant, target, prepared, phone, autopilot, adb, fastboot


def _adapter_package(tmp_path, prepared):
    package, *_details = make_test_recovery_adapter_package(
        tmp_path / "recovery-adapter",
        adapter_id=prepared.recovery_adapter_id,
        action_ids=tuple(step.adapter_action_id for step in prepared.steps),
    )
    return package


def test_executor_admission_freshly_revalidates_and_exclusively_consumes_exact_chain(
    tmp_path,
    monkeypatch,
) -> None:
    service, consent, target, prepared, phone, _autopilot, adb, fastboot = _execution_context(
        tmp_path, monkeypatch
    )
    original_calls = (adb.calls, fastboot.discovery_calls, len(fastboot.getvar_calls))

    grant = service.admit(prepared, target, consent, phone)
    claim = grant.claim

    assert (adb.calls, fastboot.discovery_calls, len(fastboot.getvar_calls)) == tuple(
        value + increment for value, increment in zip(original_calls, (3, 3, 6), strict=True)
    )
    assert claim.preparation_digest == prepared.preparation_digest
    assert claim.live_target_receipt_digest == target.receipt_digest
    assert claim.consent_receipt_digest == consent.receipt.receipt_digest
    assert claim.incident_id == prepared.incident_id
    assert claim.device_key == prepared.device_key
    assert claim.source_original_sha256 == prepared.source_original_sha256
    assert claim.device_pack_sha256 == prepared.device_pack_sha256
    assert claim.steps_digest == prepared.steps_digest
    assert claim.exact_sequence_authority == service.EXACT_SEQUENCE_AUTHORITY
    assert claim.exclusive_claim_recorded
    assert claim.consent_consumed_once
    assert not claim.execution_token_persisted
    assert not claim.automatic_retry_allowed
    assert not claim.bootloader_relock_allowed
    assert not claim.first_step_started
    assert not claim.phone_changed
    assert service.load_claim(prepared) == claim

    serialized = service._claim_path(prepared).read_text(encoding="utf-8")
    assert phone.serial not in serialized
    assert grant.ephemeral_token not in serialized

    with pytest.raises(RecoveryExecutionValidationError, match="already has"):
        service.admit(prepared, target, consent, phone)


def test_executor_rejects_unexpired_receipt_when_fresh_phone_evidence_drifted(
    tmp_path,
    monkeypatch,
) -> None:
    service, consent, target, prepared, phone, _autopilot, _adb, fastboot = _execution_context(
        tmp_path, monkeypatch
    )
    fastboot.values["product"] = "same-model-but-wrong-product"

    with pytest.raises(RecoveryExecutionValidationError, match="failed closed"):
        service.admit(prepared, target, consent, phone)

    assert not service._claim_path(prepared).exists()
    assert target.execution_authority == "none"


def test_executor_rejects_same_model_different_phone_and_incident_drift(
    tmp_path,
    monkeypatch,
) -> None:
    service, consent, target, prepared, phone, autopilot, *_rest = _execution_context(
        tmp_path,
        monkeypatch,
    )

    with pytest.raises(RecoveryExecutionValidationError, match="failed closed"):
        service.admit(
            prepared,
            target,
            consent,
            replace(phone, serial="same-model-different-physical-phone"),
        )

    autopilot.record_route_result(
        prepared.incident_id,
        prepared.route_id,
        "reviewed",
        "Mutable incident evidence changed before executor admission.",
    )
    with pytest.raises(RecoveryExecutionValidationError, match="failed closed"):
        service.admit(prepared, target, consent, phone)
    assert not service._claim_path(prepared).exists()


def test_executor_journal_preserves_unknown_and_forbids_blind_retry_or_advance(
    tmp_path,
    monkeypatch,
) -> None:
    service, consent, target, prepared, phone, *_rest = _execution_context(
        tmp_path,
        monkeypatch,
    )
    grant = service.admit(prepared, target, consent, phone)
    package = _adapter_package(tmp_path, prepared)

    targets = GuardianRecoveryStepTargetService(service, clock=service.clock)
    pre_first = targets.observe(
        grant,
        prepared,
        1,
        RecoveryStepTargetPhase.PRE_DISPATCH,
    )
    intent = service.record_step_intent(grant, prepared, 1, pre_first, package)
    assert intent.adapter_action_id == prepared.steps[0].adapter_action_id
    assert intent.adapter_version == package.manifest.adapter_version
    assert intent.adapter_package_id == package.manifest.package_id
    assert intent.adapter_package_version == package.manifest.package_version
    assert intent.adapter_package_sha256 == package.package_sha256
    assert intent.adapter_artifact_sha256 == package.manifest.artifact.sha256
    assert intent.adapter_release_key_id == package.release_key_id
    assert intent.adapter_release_public_key_sha256 == package.release_public_key_sha256
    assert intent.adapter_release_trust_scope == "test-only"
    assert intent.adapter_protocol_version == package.manifest.protocol_version
    assert intent.outcome_at_record_time == RecoveryStepOutcome.UNKNOWN.value
    assert service.step_outcome(prepared, grant.claim, 1) is RecoveryStepOutcome.UNKNOWN
    serialized_intent = service._intent_path(prepared, 1).read_text(encoding="utf-8")
    assert phone.serial not in serialized_intent
    assert package.release_public_key_sha256 in serialized_intent

    with pytest.raises(RecoveryExecutionValidationError, match="must not be retried"):
        service.record_step_intent(grant, prepared, 1, pre_first, package)
    pre_second = targets.observe(
        grant,
        prepared,
        2,
        RecoveryStepTargetPhase.PRE_DISPATCH,
    )
    substitute_grant = GuardianRecoveryExecutionGrant(
        grant.claim,
        "same-model-different-physical-phone",
        replace(phone, serial="same-model-different-physical-phone"),
        grant.ephemeral_token,
    )
    with pytest.raises(RecoveryExecutionValidationError, match="exact target"):
        service.record_step_intent(substitute_grant, prepared, 2, pre_second, package)
    with pytest.raises(RecoveryExecutionValidationError, match="previous step"):
        service.record_step_intent(grant, prepared, 2, pre_second, package)

    reloaded = GuardianRecoveryExecutionService(service.consents, clock=service.clock)
    assert reloaded.step_outcome(prepared, grant.claim, 1) is RecoveryStepOutcome.UNKNOWN

    unknown = service.record_step_result(
        grant,
        prepared,
        intent,
        outcome=RecoveryStepOutcome.UNKNOWN,
        operation_dispatched=True,
        observed_result_sha256="a" * 64,
        observed_next_mode="unknown",
    )
    assert unknown.recovery_reassessment_required
    assert not unknown.next_step_allowed
    with pytest.raises(RecoveryExecutionValidationError, match="previous step"):
        service.record_step_intent(grant, prepared, 2, pre_second, package)
    post_first = targets.observe(
        grant,
        prepared,
        1,
        RecoveryStepTargetPhase.POST_DISPATCH,
    )
    with pytest.raises(RecoveryExecutionValidationError, match="cannot be replaced"):
        service.record_step_result(
            grant,
            prepared,
            intent,
            outcome=RecoveryStepOutcome.SUCCEEDED,
            operation_dispatched=True,
            observed_result_sha256="b" * 64,
            observed_next_mode=prepared.steps[0].to_mode,
            post_target_witness=post_first,
        )


def test_executor_advances_only_after_durable_exact_step_success(
    tmp_path,
    monkeypatch,
) -> None:
    service, consent, target, prepared, phone, *_rest = _execution_context(
        tmp_path,
        monkeypatch,
    )
    grant = service.admit(prepared, target, consent, phone)
    package = _adapter_package(tmp_path, prepared)
    targets = GuardianRecoveryStepTargetService(service, clock=service.clock)
    pre_first = targets.observe(
        grant,
        prepared,
        1,
        RecoveryStepTargetPhase.PRE_DISPATCH,
    )
    post_first = targets.observe(
        grant,
        prepared,
        1,
        RecoveryStepTargetPhase.POST_DISPATCH,
    )
    first = service.record_step_intent(grant, prepared, 1, pre_first, package)
    with pytest.raises(RecoveryExecutionValidationError, match="conflicts"):
        service.record_step_result(
            grant,
            prepared,
            first,
            outcome=RecoveryStepOutcome.SUCCEEDED,
            operation_dispatched=False,
            observed_result_sha256="c" * 64,
            observed_next_mode=prepared.steps[0].to_mode,
            post_target_witness=post_first,
        )
    result = service.record_step_result(
        grant,
        prepared,
        first,
        outcome=RecoveryStepOutcome.SUCCEEDED,
        operation_dispatched=True,
        observed_result_sha256="c" * 64,
        observed_next_mode=prepared.steps[0].to_mode,
        post_target_witness=post_first,
    )

    assert result.next_step_allowed
    assert not result.recovery_reassessment_required
    pre_second = targets.observe(
        grant,
        prepared,
        2,
        RecoveryStepTargetPhase.PRE_DISPATCH,
    )
    changed_package, *_details = make_test_recovery_adapter_package(
        tmp_path / "changed-recovery-adapter",
        adapter_id=prepared.recovery_adapter_id,
        action_ids=tuple(step.adapter_action_id for step in prepared.steps),
        artifact_bytes=b"#!/bin/sh\nprintf 'different signed adapter\\n'\n",
    )
    with pytest.raises(RecoveryExecutionValidationError, match="package changed"):
        service.record_step_intent(
            grant,
            prepared,
            2,
            pre_second,
            changed_package,
        )
    second = service.record_step_intent(grant, prepared, 2, pre_second, package)
    assert second.step_order == 2
    assert second.adapter_action_id == prepared.steps[1].adapter_action_id
    assert service.step_outcome(prepared, grant.claim, 2) is RecoveryStepOutcome.UNKNOWN

    with pytest.raises(RecoveryExecutionValidationError, match="not part"):
        service.record_step_intent(
            grant,
            prepared,
            prepared.step_count + 1,
            pre_second,
            package,
        )


def test_executor_rejects_tamper_and_has_no_dispatch_or_relock_surface(
    tmp_path,
    monkeypatch,
) -> None:
    service, consent, target, prepared, phone, *_rest = _execution_context(
        tmp_path,
        monkeypatch,
    )
    grant = service.admit(prepared, target, consent, phone)
    path = service._claim_path(prepared)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["automatic_retry_allowed"] = True
    path.write_text(json.dumps(document), encoding="utf-8")
    assert service.load_claim(prepared) is None

    forbidden = {
        "erase",
        "execute",
        "flash",
        "reboot",
        "relock",
        "restore",
        "retry",
        "unlock",
        "wipe",
    }
    assert set(dir(GuardianRecoveryExecutionService)).isdisjoint(forbidden)
    source = inspect.getsource(GuardianRecoveryExecutionService)
    assert "subprocess" not in source
    assert "fastboot." not in source
    assert "adb." not in source

    for suffix in (
        "bootloader_lock",
        "bootloaderlock",
        "flashing.lock",
        "oem-lock",
        "relock",
        "relockbootloader",
    ):
        relock_step = replace(
            prepared.steps[0],
            adapter_action_id=f"{prepared.recovery_adapter_id}.{suffix}",
        )
        relock_preparation = replace(prepared, steps=(relock_step, *prepared.steps[1:]))
        with pytest.raises(RecoveryExecutionValidationError, match="bootloader-locking"):
            service._validate_actions(relock_preparation)
    assert grant.claim.bootloader_relock_allowed is False


def test_executor_rejects_stale_step_target_witness(tmp_path, monkeypatch) -> None:
    service, consent, target, prepared, phone, *_rest = _execution_context(
        tmp_path,
        monkeypatch,
    )
    grant = service.admit(prepared, target, consent, phone)
    package = _adapter_package(tmp_path, prepared)
    targets = GuardianRecoveryStepTargetService(service, clock=service.clock)
    witness = targets.observe(
        grant,
        prepared,
        1,
        RecoveryStepTargetPhase.PRE_DISPATCH,
    )
    service.clock = lambda: _OBSERVED_AT + timedelta(seconds=71)

    with pytest.raises(RecoveryExecutionValidationError, match="not fresh"):
        service.record_step_intent(grant, prepared, 1, witness, package)
    assert service.load_step_intent(prepared, grant.claim, 1) is None


def test_executor_claim_load_rejects_duplicate_json_key(tmp_path, monkeypatch) -> None:
    service, consent, target, prepared, phone, *_rest = _execution_context(
        tmp_path,
        monkeypatch,
    )
    service.admit(prepared, target, consent, phone)
    path = service._claim_path(prepared)
    original = path.read_text(encoding="utf-8")
    duplicate = original.replace(
        '"schema_version": 1,',
        '"schema_version": 1, "schema_version": 1,',
        1,
    )
    assert duplicate != original
    path.write_text(duplicate, encoding="utf-8")

    assert service.load_claim(prepared) is None
    GuardianRecoveryPreparationService.validate(prepared)
