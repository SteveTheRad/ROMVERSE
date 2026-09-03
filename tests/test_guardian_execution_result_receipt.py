from __future__ import annotations

import base64
import hashlib
import json
import os
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from romverse.device_packs.models import DeviceMode, DeviceRecoveryOperation
from romverse.guardian.execution_gateway_contract import (
    GatewayEvidenceKind,
    GatewayStepPhase,
    GuardianGatewayRecoveryStep,
)
from romverse.guardian.execution_result_receipt import (
    ExecutionResultValidationError,
    ExecutionTerminalState,
    GatewayResultOutcome,
    GuardianExecutionPrerequisiteBindings,
    GuardianExecutionResultVerifier,
    GuardianGatewayRecoveryResult,
    GuardianRuntimeTrust,
    canonical_execution_result_bytes,
    execution_result_digest,
    load_signed_execution_result,
    parse_signed_execution_result_bytes,
)
from tests.test_guardian_execution_gateway_contract import _service
from tests.test_guardian_execution_plan import (
    _prepared_with_post_write_verification,
    _prepared_with_transition_recovery,
)

_START = datetime(2026, 9, 3, 20, 0, tzinfo=UTC)
_EMPTY_EVIDENCE = hashlib.sha256(b"").hexdigest()


def _trust(private_key: Ed25519PrivateKey, gateway) -> GuardianRuntimeTrust:
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return GuardianRuntimeTrust(
        key_id="guardian-runtime-test-2026",
        public_key_sha256=hashlib.sha256(raw).hexdigest(),
        adapter_id="fixture.fastboot.runtime",
        adapter_version=1,
        adapter_sha256="9" * 64,
        device_pack_id=gateway.device_pack_id,
        device_pack_sha256=gateway.device_pack_sha256,
        write_contract_id=gateway.write_contract_id,
        write_contract_version=gateway.write_contract_version,
        write_attestation_sha256=gateway.write_attestation_sha256,
        transition_recovery_contract_digest=gateway.transition_recovery_contract_digest,
    )


def _step_result(step, *, outcome: GatewayResultOutcome = GatewayResultOutcome.PASSED):
    observed_value = ""
    observed_size = 0
    observed_sha = ""
    if step.evidence_kind is GatewayEvidenceKind.FILE_SIZE_AND_SHA256:
        observed_size = step.expected_size_bytes
        observed_sha = step.expected_sha256
    elif step.evidence_kind is not GatewayEvidenceKind.COMMAND_EXIT_ZERO:
        observed_value = step.expected_value
    started = _START + timedelta(seconds=step.order * 2)
    payload = {
        "order": step.order,
        "operation_id": step.operation_id,
        "gateway_step_digest": execution_result_digest({"gateway_step": asdict(step)}),
        "started_at": started.isoformat(),
        "completed_at": (started + timedelta(seconds=1)).isoformat(),
        "outcome": outcome.value,
        "returncode": 0 if outcome is GatewayResultOutcome.PASSED else 1,
        "timed_out": False,
        "observed_value": observed_value,
        "observed_size_bytes": observed_size,
        "observed_sha256": observed_sha,
        "evidence_sha256": hashlib.sha256(step.operation_id.encode()).hexdigest(),
        "error_code": "" if outcome is GatewayResultOutcome.PASSED else "COMMAND_FAILED",
    }
    payload["result_digest"] = execution_result_digest(payload)
    return payload


def _recovery_result(step, *, outcome: GatewayResultOutcome = GatewayResultOutcome.PASSED):
    started = _START + timedelta(minutes=2, seconds=step.order * 2)
    payload = {
        "order": step.order,
        "operation": step.operation.value,
        "adapter_action_id": step.adapter_action_id,
        "recovery_step_digest": execution_result_digest({"recovery_step": asdict(step)}),
        "started_at": started.isoformat(),
        "completed_at": (started + timedelta(seconds=1)).isoformat(),
        "outcome": outcome.value,
        "resulting_mode": step.to_mode.value if outcome is GatewayResultOutcome.PASSED else "",
        "resulting_slot": "" if step.target_slot == "none" else step.target_slot,
        "wiped_user_data": False,
        "evidence_sha256": hashlib.sha256(step.adapter_action_id.encode()).hexdigest(),
        "error_code": "" if outcome is GatewayResultOutcome.PASSED else "RECOVERY_FAILED",
    }
    payload["result_digest"] = execution_result_digest(payload)
    return payload


def _reseal_item(item: dict[str, object]) -> None:
    unsigned = dict(item)
    unsigned.pop("result_digest", None)
    item["result_digest"] = execution_result_digest(unsigned)


def _signed_envelope(
    gateway,
    private_key: Ed25519PrivateKey,
    trust: GuardianRuntimeTrust,
    *,
    forward_results=None,
    recovery_results=None,
    terminal_state: ExecutionTerminalState = ExecutionTerminalState.SUCCEEDED,
    recovery_invoked: bool = False,
    recovery_consent: str = "",
    wipe_consent: str = "",
):
    forward = (
        [_step_result(step) for step in gateway.steps]
        if forward_results is None
        else list(forward_results)
    )
    recovery = [] if recovery_results is None else list(recovery_results)
    forward_steps = gateway.steps[: len(forward)]
    recovery_steps = gateway.recovery_steps[: len(recovery)]
    forward_passed = [item["outcome"] == GatewayResultOutcome.PASSED.value for item in forward]
    recovery_passed = [item["outcome"] == GatewayResultOutcome.PASSED.value for item in recovery]
    attempted = any(step.phone_changes for step in forward_steps) or any(
        step.phone_changes_if_executed for step in recovery_steps
    )
    verified = any(
        step.phone_changes and passed
        for step, passed in zip(forward_steps, forward_passed, strict=False)
    ) or any(
        step.phone_changes_if_executed and passed
        for step, passed in zip(recovery_steps, recovery_passed, strict=False)
    )
    uncertain = any(
        step.phone_changes and not passed
        for step, passed in zip(forward_steps, forward_passed, strict=False)
    ) or any(
        step.phone_changes_if_executed and not passed
        for step, passed in zip(recovery_steps, recovery_passed, strict=False)
    )
    last_time = _START + timedelta(minutes=3)
    payload = {
        "schema_version": 2,
        "receipt_id": "a" * 32,
        "created_at": (last_time + timedelta(seconds=1)).isoformat(),
        "started_at": _START.isoformat(),
        "completed_at": last_time.isoformat(),
        "gateway_contract_digest": gateway.contract_digest,
        "project_id": gateway.project_id,
        "plan_digest": gateway.plan_digest,
        "manifest_digest": gateway.manifest_digest,
        "artifact_binding_digest": gateway.artifact_binding_digest,
        "device_key": gateway.device_key,
        "device_pack_id": gateway.device_pack_id,
        "device_pack_version": gateway.device_pack_version,
        "device_pack_sha256": gateway.device_pack_sha256,
        "live_target_receipt_digest": "1" * 64,
        "final_consent_receipt_digest": "2" * 64,
        "runtime_signer_key_id": trust.key_id,
        "runtime_adapter_id": trust.adapter_id,
        "runtime_adapter_version": trust.adapter_version,
        "runtime_adapter_sha256": trust.adapter_sha256,
        "recorded_prewrite_slot": "a" if gateway.recovery_require_prewrite_slot_capture else "",
        "forward_result_count": len(forward),
        "forward_results_digest": execution_result_digest({"forward_results": forward}),
        "forward_results": forward,
        "recovery_invoked": recovery_invoked,
        "recovery_consent_receipt_digest": recovery_consent,
        "wipe_consent_receipt_digest": wipe_consent,
        "recovery_result_count": len(recovery),
        "recovery_results_digest": execution_result_digest({"recovery_results": recovery}),
        "recovery_results": recovery,
        "terminal_state": terminal_state.value,
        "phone_change_attempted": attempted,
        "phone_change_verified": verified,
        "phone_state_uncertain": uncertain,
        "postconditions_verified": terminal_state
        in {ExecutionTerminalState.SUCCEEDED, ExecutionTerminalState.RECOVERED},
    }
    payload["receipt_digest"] = execution_result_digest(payload)
    return _resign(payload, private_key, trust)


def _resign(
    receipt: dict[str, object],
    private_key: Ed25519PrivateKey,
    trust: GuardianRuntimeTrust,
):
    encoded = canonical_execution_result_bytes(receipt)
    return {
        "format": GuardianExecutionResultVerifier.FORMAT,
        "schema_version": GuardianExecutionResultVerifier.SCHEMA_VERSION,
        "algorithm": GuardianExecutionResultVerifier.ALGORITHM,
        "key_id": trust.key_id,
        "receipt_sha256": hashlib.sha256(encoded).hexdigest(),
        "receipt": receipt,
        "signature": base64.b64encode(
            private_key.sign(GuardianExecutionResultVerifier.DOMAIN + encoded)
        ).decode("ascii"),
    }


@pytest.fixture
def signed_result_context(tmp_path, monkeypatch):
    plans, project, report, device, *_rest = _prepared_with_transition_recovery(
        tmp_path, monkeypatch
    )
    plans.compile(project.project_id, report, device)
    gateway = _service(plans).compile(project.project_id, report, device)
    private_key = Ed25519PrivateKey.generate()
    trust = _trust(private_key, gateway)
    envelope = _signed_envelope(gateway, private_key, trust)
    return gateway, private_key, trust, envelope


def _verify(context, envelope=None, *, prerequisites=None):
    gateway, private_key, trust, original = context
    return GuardianExecutionResultVerifier.verify(
        original if envelope is None else envelope,
        gateway=gateway,
        trust=trust,
        prerequisites=prerequisites or _prerequisites(gateway),
        public_key=private_key.public_key(),
    )


def _prerequisites(gateway, *, recovery: str = "", wipe: str = ""):
    return GuardianExecutionPrerequisiteBindings(
        gateway_contract_digest=gateway.contract_digest,
        device_key=gateway.device_key,
        live_target_receipt_digest="1" * 64,
        final_consent_receipt_digest="2" * 64,
        recovery_consent_receipt_digest=recovery,
        wipe_consent_receipt_digest=wipe,
        recorded_prewrite_slot="a" if gateway.recovery_require_prewrite_slot_capture else "",
    )


def test_exact_runtime_signed_success_receipt_verifies_all_postconditions(
    signed_result_context,
) -> None:
    gateway, _private_key, trust, envelope = signed_result_context

    verified = _verify(signed_result_context)

    assert verified.signer_key_id == trust.key_id
    assert verified.signed_receipt_sha256 == envelope["receipt_sha256"]
    assert verified.receipt.gateway_contract_digest == gateway.contract_digest
    assert verified.receipt.terminal_state is ExecutionTerminalState.SUCCEEDED
    assert verified.receipt.forward_result_count == gateway.step_count
    assert verified.receipt.phone_change_attempted
    assert verified.receipt.phone_change_verified
    assert not verified.receipt.phone_state_uncertain
    assert verified.receipt.postconditions_verified


def test_byte_tampering_and_wrong_runtime_key_are_rejected(signed_result_context) -> None:
    gateway, _private_key, trust, envelope = signed_result_context
    tampered = deepcopy(envelope)
    tampered["receipt"]["device_key"] = "0" * 20

    with pytest.raises(ExecutionResultValidationError, match="digest does not match"):
        _verify(signed_result_context, tampered)
    with pytest.raises(ExecutionResultValidationError, match="verification failed"):
        wrong_key = Ed25519PrivateKey.generate()
        wrong_trust = _trust(wrong_key, gateway)
        GuardianExecutionResultVerifier.verify(
            envelope,
            gateway=gateway,
            trust=wrong_trust,
            prerequisites=_prerequisites(gateway),
            public_key=wrong_key.public_key(),
        )


def test_resigned_result_cannot_claim_success_with_wrong_postcondition(
    signed_result_context,
) -> None:
    _gateway, private_key, trust, envelope = signed_result_context
    receipt = deepcopy(envelope["receipt"])
    final = receipt["forward_results"][-1]
    final["observed_value"] = "wrong"
    _reseal_item(final)
    receipt["forward_results_digest"] = execution_result_digest(
        {"forward_results": receipt["forward_results"]}
    )
    receipt.pop("receipt_digest")
    receipt["receipt_digest"] = execution_result_digest(receipt)

    with pytest.raises(ExecutionResultValidationError, match="claims success"):
        _verify(signed_result_context, _resign(receipt, private_key, trust))


@pytest.mark.parametrize(
    "binding",
    (
        "gateway_contract_digest",
        "plan_digest",
        "manifest_digest",
        "artifact_binding_digest",
        "device_pack_sha256",
        "live_target_receipt_digest",
        "final_consent_receipt_digest",
        "runtime_adapter_sha256",
    ),
)
def test_resigned_receipt_cannot_change_any_exact_authority_binding(
    signed_result_context,
    binding,
) -> None:
    _gateway, private_key, trust, envelope = signed_result_context
    receipt = deepcopy(envelope["receipt"])
    receipt[binding] = "f" * 64
    receipt.pop("receipt_digest")
    receipt["receipt_digest"] = execution_result_digest(receipt)

    with pytest.raises(ExecutionResultValidationError, match="exact Guardian gateway"):
        _verify(signed_result_context, _resign(receipt, private_key, trust))


def test_failed_write_receipt_is_an_exact_prefix_and_marks_phone_uncertain(
    signed_result_context,
) -> None:
    gateway, private_key, trust, _envelope = signed_result_context
    write_index = next(
        index for index, step in enumerate(gateway.steps) if step.phase is GatewayStepPhase.WRITE
    )
    forward = [_step_result(step) for step in gateway.steps[:write_index]]
    forward.append(_step_result(gateway.steps[write_index], outcome=GatewayResultOutcome.FAILED))
    envelope = _signed_envelope(
        gateway,
        private_key,
        trust,
        forward_results=forward,
        terminal_state=ExecutionTerminalState.FAILED,
    )

    verified = _verify(signed_result_context, envelope).receipt

    assert verified.terminal_state is ExecutionTerminalState.FAILED
    assert verified.phone_change_attempted
    assert verified.phone_state_uncertain
    assert not verified.postconditions_verified


def test_operator_abort_before_a_write_records_the_prior_mode_change(
    signed_result_context,
) -> None:
    gateway, private_key, trust, _envelope = signed_result_context
    first_write = next(
        index for index, step in enumerate(gateway.steps) if step.phase is GatewayStepPhase.WRITE
    )
    forward = [_step_result(step) for step in gateway.steps[:first_write]]
    envelope = _signed_envelope(
        gateway,
        private_key,
        trust,
        forward_results=forward,
        terminal_state=ExecutionTerminalState.ABORTED,
    )

    receipt = _verify(signed_result_context, envelope).receipt

    assert receipt.terminal_state is ExecutionTerminalState.ABORTED
    # This fixture enters fastbootd before its first write, so aborting here has still
    # completed one signed state-changing transition even though no partition was written.
    assert receipt.phone_change_attempted
    assert receipt.phone_change_verified
    assert not receipt.phone_state_uncertain
    assert not receipt.postconditions_verified


def test_success_cannot_skip_reorder_or_duplicate_gateway_results(
    signed_result_context,
) -> None:
    gateway, private_key, trust, envelope = signed_result_context
    for changed in (
        envelope["receipt"]["forward_results"][:-1],
        list(reversed(envelope["receipt"]["forward_results"])),
        [
            envelope["receipt"]["forward_results"][0],
            *envelope["receipt"]["forward_results"],
        ],
    ):
        candidate = _signed_envelope(
            gateway,
            private_key,
            trust,
            forward_results=deepcopy(changed),
        )
        with pytest.raises(ExecutionResultValidationError):
            _verify(signed_result_context, candidate)


def test_separately_consented_recovery_can_prove_recovered_state(
    signed_result_context,
) -> None:
    gateway, private_key, trust, _envelope = signed_result_context
    write_index = next(
        index for index, step in enumerate(gateway.steps) if step.phase is GatewayStepPhase.WRITE
    )
    forward = [_step_result(step) for step in gateway.steps[:write_index]]
    forward.append(_step_result(gateway.steps[write_index], outcome=GatewayResultOutcome.FAILED))
    recovery = [_recovery_result(step) for step in gateway.recovery_steps]
    envelope = _signed_envelope(
        gateway,
        private_key,
        trust,
        forward_results=forward,
        recovery_results=recovery,
        terminal_state=ExecutionTerminalState.RECOVERED,
        recovery_invoked=True,
        recovery_consent="3" * 64,
    )

    receipt = _verify(
        signed_result_context,
        envelope,
        prerequisites=_prerequisites(gateway, recovery="3" * 64),
    ).receipt

    assert receipt.terminal_state is ExecutionTerminalState.RECOVERED
    assert receipt.recovery_result_count == gateway.recovery_action_count
    assert receipt.recovery_results[-1].operation is DeviceRecoveryOperation.VERIFY_POST_BOOT
    assert receipt.postconditions_verified


def test_separately_consented_recovery_failure_is_never_called_recovered(
    signed_result_context,
) -> None:
    gateway, private_key, trust, _envelope = signed_result_context
    write_index = next(
        index for index, step in enumerate(gateway.steps) if step.phase is GatewayStepPhase.WRITE
    )
    forward = [_step_result(step) for step in gateway.steps[:write_index]]
    forward.append(_step_result(gateway.steps[write_index], outcome=GatewayResultOutcome.FAILED))
    recovery = [_recovery_result(gateway.recovery_steps[0])]
    recovery.append(
        _recovery_result(gateway.recovery_steps[1], outcome=GatewayResultOutcome.FAILED)
    )
    envelope = _signed_envelope(
        gateway,
        private_key,
        trust,
        forward_results=forward,
        recovery_results=recovery,
        terminal_state=ExecutionTerminalState.RECOVERY_FAILED,
        recovery_invoked=True,
        recovery_consent="3" * 64,
    )

    receipt = _verify(
        signed_result_context,
        envelope,
        prerequisites=_prerequisites(gateway, recovery="3" * 64),
    ).receipt

    assert receipt.terminal_state is ExecutionTerminalState.RECOVERY_FAILED
    assert receipt.phone_state_uncertain
    assert not receipt.postconditions_verified


def test_recovery_wipe_requires_separate_wipe_consent(signed_result_context) -> None:
    gateway, private_key, trust, _envelope = signed_result_context
    write_index = next(
        index for index, step in enumerate(gateway.steps) if step.phase is GatewayStepPhase.WRITE
    )
    forward = [_step_result(step) for step in gateway.steps[:write_index]]
    forward.append(_step_result(gateway.steps[write_index], outcome=GatewayResultOutcome.FAILED))
    recovery = [_recovery_result(step) for step in gateway.recovery_steps]
    recovery[0]["wiped_user_data"] = True
    _reseal_item(recovery[0])
    missing = _signed_envelope(
        gateway,
        private_key,
        trust,
        forward_results=forward,
        recovery_results=recovery,
        terminal_state=ExecutionTerminalState.RECOVERED,
        recovery_invoked=True,
        recovery_consent="3" * 64,
    )

    with pytest.raises(ExecutionResultValidationError, match="consent"):
        _verify(
            signed_result_context,
            missing,
            prerequisites=_prerequisites(gateway, recovery="3" * 64),
        )

    present = _signed_envelope(
        gateway,
        private_key,
        trust,
        forward_results=forward,
        recovery_results=recovery,
        terminal_state=ExecutionTerminalState.RECOVERED,
        recovery_invoked=True,
        recovery_consent="3" * 64,
        wipe_consent="4" * 64,
    )
    assert (
        _verify(
            signed_result_context,
            present,
            prerequisites=_prerequisites(gateway, recovery="3" * 64, wipe="4" * 64),
        )
        .receipt.recovery_results[0]
        .wiped_user_data
    )


def test_schema_two_gateway_result_uses_same_fail_closed_verifier(tmp_path, monkeypatch) -> None:
    plans, project, report, device, *_rest = _prepared_with_post_write_verification(
        tmp_path, monkeypatch
    )
    plans.compile(project.project_id, report, device)
    gateway = _service(plans).compile(project.project_id, report, device)
    private_key = Ed25519PrivateKey.generate()
    trust = _trust(private_key, gateway)
    envelope = _signed_envelope(gateway, private_key, trust)

    receipt = GuardianExecutionResultVerifier.verify(
        envelope,
        gateway=gateway,
        trust=trust,
        prerequisites=_prerequisites(gateway),
        public_key=private_key.public_key(),
    ).receipt

    assert gateway.write_contract_version == 2
    assert not receipt.recovery_invoked
    assert receipt.terminal_state is ExecutionTerminalState.SUCCEEDED
    assert receipt.postconditions_verified


def test_recorded_slot_recovery_result_must_match_captured_prewrite_slot() -> None:
    step = GuardianGatewayRecoveryStep(
        order=1,
        operation=DeviceRecoveryOperation.ACTIVATE_RECORDED_SLOT,
        adapter_action_id="fixture.fastboot.runtime.activate-recorded",
        from_mode=DeviceMode.BOOTLOADER,
        to_mode=DeviceMode.BOOTLOADER,
        target_slot="recorded_prewrite",
        timeout_seconds=60,
        may_wipe_user_data=False,
        phone_changes_if_executed=True,
    )
    result = _recovery_result(step)
    result["resulting_slot"] = "a"
    _reseal_item(result)
    typed = GuardianGatewayRecoveryResult(
        **{
            **result,
            "operation": DeviceRecoveryOperation(result["operation"]),
            "outcome": GatewayResultOutcome(result["outcome"]),
        }
    )

    assert GuardianExecutionResultVerifier._validate_recovery_result(typed, step, "a")
    with pytest.raises(ExecutionResultValidationError, match="claims success"):
        GuardianExecutionResultVerifier._validate_recovery_result(typed, step, "b")


def test_runtime_trust_binds_public_key_and_exact_adapter(signed_result_context) -> None:
    gateway, private_key, trust, envelope = signed_result_context
    wrong_key_digest = replace(trust, public_key_sha256="0" * 64)
    wrong_adapter = replace(trust, adapter_id="other.runtime")
    wrong_pack_scope = replace(trust, device_pack_sha256="f" * 64)

    with pytest.raises(ExecutionResultValidationError, match="trust record"):
        GuardianExecutionResultVerifier.verify(
            envelope,
            gateway=gateway,
            trust=wrong_key_digest,
            prerequisites=_prerequisites(gateway),
            public_key=private_key.public_key(),
        )
    with pytest.raises(ExecutionResultValidationError, match="exact Guardian gateway"):
        GuardianExecutionResultVerifier.verify(
            envelope,
            gateway=gateway,
            trust=wrong_adapter,
            prerequisites=_prerequisites(gateway),
            public_key=private_key.public_key(),
        )
    with pytest.raises(ExecutionResultValidationError, match="trust record"):
        GuardianExecutionResultVerifier.verify(
            envelope,
            gateway=gateway,
            trust=wrong_pack_scope,
            prerequisites=_prerequisites(gateway),
            public_key=private_key.public_key(),
        )


def test_prerequisite_bindings_are_scoped_to_exact_gateway_and_device(
    signed_result_context,
) -> None:
    gateway, private_key, trust, envelope = signed_result_context
    wrong_gateway = replace(
        _prerequisites(gateway),
        gateway_contract_digest="f" * 64,
    )
    wrong_device = replace(_prerequisites(gateway), device_key="0" * 20)

    for prerequisites in (wrong_gateway, wrong_device):
        with pytest.raises(ExecutionResultValidationError, match="exact Guardian gateway"):
            GuardianExecutionResultVerifier.verify(
                envelope,
                gateway=gateway,
                trust=trust,
                prerequisites=prerequisites,
                public_key=private_key.public_key(),
            )


def test_result_timeline_cannot_overlap_or_exceed_signed_timeout(
    signed_result_context,
) -> None:
    _gateway, private_key, trust, envelope = signed_result_context
    receipt = deepcopy(envelope["receipt"])
    second = receipt["forward_results"][1]
    second["started_at"] = receipt["started_at"]
    _reseal_item(second)
    receipt["forward_results_digest"] = execution_result_digest(
        {"forward_results": receipt["forward_results"]}
    )
    receipt.pop("receipt_digest")
    receipt["receipt_digest"] = execution_result_digest(receipt)

    with pytest.raises(ExecutionResultValidationError, match="timeline"):
        _verify(signed_result_context, _resign(receipt, private_key, trust))


def test_bounded_json_parser_rejects_duplicate_fields_and_linked_files(
    signed_result_context,
    tmp_path: Path,
) -> None:
    _gateway, _private_key, _trust_value, envelope = signed_result_context
    with pytest.raises(ExecutionResultValidationError, match="Duplicate"):
        parse_signed_execution_result_bytes(b'{"format":"one","format":"two"}')

    document = tmp_path / "result.romverse"
    document.write_text(json.dumps(envelope), encoding="utf-8")
    assert load_signed_execution_result(document) == envelope
    if os.name != "nt":
        linked = tmp_path / "linked.romverse"
        linked.symlink_to(document)
        with pytest.raises(ExecutionResultValidationError, match="not a link"):
            load_signed_execution_result(linked)


def test_verifier_has_no_signer_runner_or_execution_method() -> None:
    source = Path("src/romverse/guardian/execution_result_receipt.py").read_text(encoding="utf-8")
    assert "Ed25519PrivateKey" not in source
    assert "CommandRunner" not in source
    assert "SubprocessRunner" not in source
    assert "def execute(" not in source
    assert "def sign" not in source
    assert _EMPTY_EVIDENCE == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
