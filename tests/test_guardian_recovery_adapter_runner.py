from __future__ import annotations

import json
from dataclasses import fields
from datetime import timedelta

import pytest

from romverse.guardian.recovery_adapter_runner import (
    GuardianRecoveryAdapterObservation,
    GuardianRecoveryAdapterRunner,
    RecoveryAdapterRunnerError,
    RecoveryAdapterRunState,
)
from romverse.guardian.recovery_consent import GuardianRecoveryConsentReceiptService
from romverse.guardian.recovery_execution import (
    GuardianRecoveryExecutionService,
    RecoveryStepOutcome,
)
from romverse.guardian.recovery_runtime_adapter import (
    GuardianTrustedRecoveryProcessAdapter,
    RecoveryAdapterProcessResult,
)
from romverse.guardian.recovery_step_target import GuardianRecoveryStepTargetService
from romverse.infrastructure.process import CommandResult
from tests._recovery_adapter_trust import make_test_recovery_adapter_package
from tests.test_guardian_recovery_live_target import _OBSERVED_AT, _live_context


class _ModeAdb:
    def __init__(self) -> None:
        self.mode = "bootloader"
        self.multiple = False
        self.lost = False
        self.transient_unavailable_cycles = 0
        self.calls = 0
        self.probe_calls: list[str] = []

    def devices(self) -> CommandResult:
        self.calls += 1
        rows = ""
        if not self.lost and not self.transient_unavailable_cycles and self.mode == "android":
            rows = "private-serial\tdevice usb:1-2\n"
            if self.multiple:
                rows += "other-serial\tdevice usb:1-3\n"
        return CommandResult(("adb", "devices", "-l"), 0, f"List of devices attached\n{rows}", "")

    def probe(
        self,
        serial: str,
        probe_id: str,
        args: tuple[str, ...],
        timeout: float = 4,
    ) -> CommandResult:
        assert serial == "private-serial"
        assert timeout == 4
        self.probe_calls.append(probe_id)
        values = {
            "ro.product.device": "product",
            "sys.boot_completed": "1",
            "ro.boot.slot_suffix": "_a",
        }
        return CommandResult(("adb", *args), 0, values[args[-1]] + "\n", "")


class _ModeFastboot:
    def __init__(self, adb: _ModeAdb) -> None:
        self.adb = adb
        self.discovery_calls = 0
        self.getvar_calls: list[str] = []

    def devices(self) -> CommandResult:
        self.discovery_calls += 1
        rows = ""
        if (
            not self.adb.lost
            and not self.adb.transient_unavailable_cycles
            and self.adb.mode != "android"
        ):
            rows = "private-serial\tfastboot usb:1-2\n"
            if self.adb.multiple:
                rows += "other-serial\tfastboot usb:1-3\n"
        if self.adb.transient_unavailable_cycles:
            self.adb.transient_unavailable_cycles -= 1
        return CommandResult(("fastboot", "devices", "-l"), 0, rows, "")

    def getvar(self, serial: str, variable: str, timeout: float = 4) -> CommandResult:
        assert serial == "private-serial"
        assert timeout == 4
        self.getvar_calls.append(variable)
        values = {
            "product": "product",
            "unlocked": "yes",
            "is-userspace": "yes" if self.adb.mode == "fastbootd" else "no",
            "current-slot": "a",
        }
        value = values[variable]
        return CommandResult(
            ("fastboot", "getvar", variable),
            0,
            "",
            f"(bootloader) {variable}: {value}\nOKAY",
        )


class _AdapterProcess:
    def __init__(self, prepared, transport: _ModeAdb) -> None:
        self.prepared = prepared
        self.transport = transport
        self.calls = []
        self.outcome = RecoveryStepOutcome.SUCCEEDED
        self.timed_out = False
        self.raise_error = False
        self.lose_after_dispatch = False
        self.transient_after_dispatch = 0
        self.post_mode_override = ""

    def run(self, package, request_bytes, timeout_seconds):
        request = json.loads(request_bytes)
        self.calls.append(request)
        if self.raise_error:
            raise RuntimeError("simulated adapter interruption")
        if self.lose_after_dispatch:
            self.transport.lost = True
        elif self.outcome is RecoveryStepOutcome.SUCCEEDED:
            self.transport.mode = self.post_mode_override or request["expected_to_mode"]
            self.transport.transient_unavailable_cycles = self.transient_after_dispatch
        response = {
            "schema_version": 1,
            "protocol_version": 1,
            "request_digest": request["request_digest"],
            "package_sha256": package.package_sha256,
            "adapter_id": request["adapter_id"],
            "adapter_version": package.manifest.adapter_version,
            "adapter_action_id": request["adapter_action_id"],
            "step_order": request["step_order"],
            "outcome": self.outcome.value,
            "dispatch_started": True,
            "timed_out": False,
            "evidence_sha256": f"{request['step_order']}" * 64,
        }
        encoded = json.dumps(
            response,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
        return RecoveryAdapterProcessResult(
            True,
            0,
            encoded,
            b"",
            self.timed_out,
            False,
        )


class _Adapter(GuardianTrustedRecoveryProcessAdapter):
    def __init__(self, package, prepared, transport) -> None:
        self.fixture = _AdapterProcess(prepared, transport)
        self._action_ids_override = None
        self._relock_override = False
        super().__init__(package, self.fixture)

    @property
    def action_ids(self):
        return self._action_ids_override or super().action_ids

    @action_ids.setter
    def action_ids(self, value):
        self._action_ids_override = value

    @property
    def bootloader_relock_allowed(self):
        return self._relock_override

    @bootloader_relock_allowed.setter
    def bootloader_relock_allowed(self, value):
        self._relock_override = value

    @property
    def calls(self):
        return self.fixture.calls

    @property
    def outcome(self):
        return self.fixture.outcome

    @outcome.setter
    def outcome(self, value):
        self.fixture.outcome = value

    @property
    def timed_out(self):
        return self.fixture.timed_out

    @timed_out.setter
    def timed_out(self, value):
        self.fixture.timed_out = value

    @property
    def raise_error(self):
        return self.fixture.raise_error

    @raise_error.setter
    def raise_error(self, value):
        self.fixture.raise_error = value

    @property
    def lose_after_dispatch(self):
        return self.fixture.lose_after_dispatch

    @lose_after_dispatch.setter
    def lose_after_dispatch(self, value):
        self.fixture.lose_after_dispatch = value

    @property
    def transient_after_dispatch(self):
        return self.fixture.transient_after_dispatch

    @transient_after_dispatch.setter
    def transient_after_dispatch(self, value):
        self.fixture.transient_after_dispatch = value

    @property
    def post_mode_override(self):
        return self.fixture.post_mode_override

    @post_mode_override.setter
    def post_mode_override(self, value):
        self.fixture.post_mode_override = value


def _runner_context(tmp_path, monkeypatch):
    adb = _ModeAdb()
    fastboot = _ModeFastboot(adb)
    live, prepared, phone, autopilot, _adb, _fastboot = _live_context(
        tmp_path,
        monkeypatch,
        adb=adb,
        fastboot=fastboot,
    )
    target = live.observe(prepared, phone)
    consents = GuardianRecoveryConsentReceiptService(
        live,
        clock=lambda: _OBSERVED_AT + timedelta(seconds=30),
    )
    consent = consents.issue(prepared, target, phone, confirmed=True)
    execution_time = _OBSERVED_AT + timedelta(seconds=60)
    live.clock = lambda: execution_time
    executions = GuardianRecoveryExecutionService(
        consents,
        clock=lambda: execution_time,
    )
    grant = executions.admit(prepared, target, consent, phone)
    targets = GuardianRecoveryStepTargetService(executions, clock=lambda: execution_time)
    elapsed = [0.0]
    runner = GuardianRecoveryAdapterRunner(
        executions,
        targets,
        monotonic=lambda: elapsed[0],
        sleeper=lambda _seconds: elapsed.__setitem__(0, elapsed[0] + 3600),
        allow_test_adapter_trust=True,
    )
    package, *_package_details = make_test_recovery_adapter_package(
        tmp_path / "recovery-adapter",
        adapter_id=prepared.recovery_adapter_id,
        action_ids=tuple(step.adapter_action_id for step in prepared.steps),
    )
    adapter = _Adapter(package, prepared, adb)
    return runner, executions, grant, prepared, adapter, adb, fastboot, autopilot


def test_runner_executes_exactly_one_step_with_pre_and_post_target_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )

    run = runner.execute_next(grant, prepared, adapter)

    assert run.state is RecoveryAdapterRunState.STEP_SUCCEEDED
    assert run.step_order == 1
    assert run.next_step_order == 2
    assert run.same_incident_preserved
    assert not run.recovery_verified
    assert not run.automatic_retry_allowed
    assert not run.bootloader_relock_allowed
    assert len(adapter.calls) == 1
    request = adapter.calls[0]
    assert request["adapter_action_id"] == prepared.steps[0].adapter_action_id
    assert request["operation"] == prepared.steps[0].operation.value
    assert request["target_serial"] == grant.target_serial
    assert request["stock_package_sha256"] == prepared.stock_package_sha256
    assert run.intent is not None and run.result is not None
    assert run.intent.pre_dispatch_witness_digest
    assert run.result.result_target_witness_digest
    assert executions.step_outcome(prepared, grant.claim, 1) is RecoveryStepOutcome.SUCCEEDED


def test_runner_completes_sequence_without_claiming_recovery_verification(
    tmp_path,
    monkeypatch,
) -> None:
    runner, _executions, grant, prepared, adapter, adb, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )

    first = runner.execute_next(grant, prepared, adapter)
    second = runner.execute_next(grant, prepared, adapter)
    assert adb.mode == "android"
    third = runner.execute_next(grant, prepared, adapter)
    completed = runner.execute_next(grant, prepared, adapter)

    assert [first.step_order, second.step_order, third.step_order] == [1, 2, 3]
    assert all(
        item.state is RecoveryAdapterRunState.STEP_SUCCEEDED for item in (first, second, third)
    )
    assert completed.state is RecoveryAdapterRunState.SEQUENCE_COMPLETE_AWAITING_DURABLE_RESULT
    assert completed.durable_outcome is RecoveryStepOutcome.SUCCEEDED
    assert not completed.recovery_verified
    assert len(adapter.calls) == prepared.step_count


def test_runner_waits_within_step_timeout_for_exact_post_transition_target(
    tmp_path,
    monkeypatch,
) -> None:
    runner, _executions, grant, prepared, adapter, adb, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )
    assert (
        runner.execute_next(grant, prepared, adapter).state
        is RecoveryAdapterRunState.STEP_SUCCEEDED
    )
    elapsed = [0.0]
    runner.monotonic = lambda: elapsed[0]
    runner.sleeper = lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds)
    adapter.transient_after_dispatch = 2

    second = runner.execute_next(grant, prepared, adapter)

    assert second.state is RecoveryAdapterRunState.STEP_SUCCEEDED
    assert adb.mode == "android"
    assert elapsed[0] > 0


@pytest.mark.parametrize("failure_kind", ["timeout", "exception", "ambiguous"])
def test_runner_records_uncertain_dispatch_as_unknown_and_never_retries(
    tmp_path,
    monkeypatch,
    failure_kind,
) -> None:
    runner, executions, grant, prepared, adapter, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )
    if failure_kind == "timeout":
        adapter.outcome = RecoveryStepOutcome.UNKNOWN
        adapter.timed_out = True
    elif failure_kind == "exception":
        adapter.raise_error = True
    else:
        adapter.lose_after_dispatch = True

    first = runner.execute_next(grant, prepared, adapter)
    second = runner.execute_next(grant, prepared, adapter)

    assert first.state is RecoveryAdapterRunState.STEP_UNKNOWN
    assert first.durable_outcome is RecoveryStepOutcome.UNKNOWN
    assert first.result is not None and first.result.recovery_reassessment_required
    assert not first.result.next_step_allowed
    assert second.state is RecoveryAdapterRunState.STEP_UNKNOWN
    assert len(adapter.calls) == 1
    assert executions.load_step_intent(prepared, grant.claim, 2) is None
    assert executions.step_outcome(prepared, grant.claim, 1) is RecoveryStepOutcome.UNKNOWN


def test_runner_preserves_prior_success_when_next_step_loses_target(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )
    first = runner.execute_next(grant, prepared, adapter)
    adapter.lose_after_dispatch = True

    second = runner.execute_next(grant, prepared, adapter)

    assert first.state is RecoveryAdapterRunState.STEP_SUCCEEDED
    assert second.state is RecoveryAdapterRunState.STEP_UNKNOWN
    assert executions.step_outcome(prepared, grant.claim, 1) is RecoveryStepOutcome.SUCCEEDED
    assert executions.step_outcome(prepared, grant.claim, 2) is RecoveryStepOutcome.UNKNOWN
    assert executions.load_step_intent(prepared, grant.claim, 3) is None


def test_runner_records_known_failure_only_when_exact_target_remains_observable(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )
    adapter.outcome = RecoveryStepOutcome.FAILED

    first = runner.execute_next(grant, prepared, adapter)
    second = runner.execute_next(grant, prepared, adapter)

    assert first.state is RecoveryAdapterRunState.STEP_FAILED
    assert first.result is not None and first.result.recovery_reassessment_required
    assert first.result.result_target_witness_digest
    assert first.result.target_observation_phase == "pre_dispatch"
    assert second.state is RecoveryAdapterRunState.STEP_FAILED
    assert len(adapter.calls) == 1
    assert executions.load_step_intent(prepared, grant.claim, 2) is None


def test_runner_records_success_with_wrong_post_state_as_unknown(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )
    adapter.post_mode_override = "android"

    result = runner.execute_next(grant, prepared, adapter)

    assert result.state is RecoveryAdapterRunState.STEP_UNKNOWN
    assert result.result is not None
    assert result.result.recovery_reassessment_required
    assert executions.step_outcome(prepared, grant.claim, 1) is RecoveryStepOutcome.UNKNOWN


def test_runner_fails_before_intent_on_ambiguous_target_or_adapter_action_set(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, adb, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )
    adb.multiple = True

    with pytest.raises(RecoveryAdapterRunnerError, match="without dispatching"):
        runner.execute_next(grant, prepared, adapter)
    assert not adapter.calls
    assert executions.load_step_intent(prepared, grant.claim, 1) is None

    adb.multiple = False
    adapter.action_ids = (*adapter.action_ids, f"{adapter.adapter_id}.hidden")
    with pytest.raises(RecoveryAdapterRunnerError, match="allowlisted"):
        runner.execute_next(grant, prepared, adapter)
    assert not adapter.calls
    assert executions.load_step_intent(prepared, grant.claim, 1) is None


def test_runner_rejects_arbitrary_adapter_implementation_before_intent(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )

    class ArbitraryAdapter:
        verified_package = adapter.verified_package
        adapter_id = adapter.adapter_id
        adapter_version = adapter.adapter_version
        package_sha256 = adapter.package_sha256
        protocol_version = adapter.protocol_version
        action_ids = adapter.action_ids
        bootloader_relock_allowed = False
        automatic_retry_allowed = False

        @staticmethod
        def invoke(_request):
            raise AssertionError("an arbitrary implementation must never be called")

    with pytest.raises(RecoveryAdapterRunnerError, match="allowlisted"):
        runner.execute_next(grant, prepared, ArbitraryAdapter())
    assert executions.load_step_intent(prepared, grant.claim, 1) is None


def test_runner_rejects_test_release_trust_unless_explicitly_in_test_mode(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )
    runner.allow_test_adapter_trust = False

    with pytest.raises(RecoveryAdapterRunnerError, match="allowlisted"):
        runner.execute_next(grant, prepared, adapter)
    assert executions.load_step_intent(prepared, grant.claim, 1) is None


def test_runner_rejects_relock_surface_and_mutable_source_drift_before_intent(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )
    adapter.bootloader_relock_allowed = True
    with pytest.raises(RecoveryAdapterRunnerError, match="allowlisted"):
        runner.execute_next(grant, prepared, adapter)
    assert not adapter.calls

    adapter.bootloader_relock_allowed = False
    project = executions.store.get(prepared.project_id)
    assert project.original is not None
    source = executions.store.workspace / project.original.workspace_path
    source.chmod(0o600)
    with source.open("ab") as stream:
        stream.write(b"drift")
    with pytest.raises(RecoveryAdapterRunnerError, match="changed after preparation"):
        runner.execute_next(grant, prepared, adapter)
    assert not adapter.calls
    assert executions.load_step_intent(prepared, grant.claim, 1) is None


def test_runner_rejects_unexpected_adapter_observation_and_leaves_unknown_intent(
    tmp_path,
    monkeypatch,
) -> None:
    runner, executions, grant, prepared, adapter, *_rest = _runner_context(
        tmp_path,
        monkeypatch,
    )

    def unexpected(request):
        adapter.calls.append(request)
        return GuardianRecoveryAdapterObservation(
            adapter.adapter_id,
            f"{adapter.adapter_id}.hidden",
            request.step_order,
            RecoveryStepOutcome.SUCCEEDED,
            True,
            False,
            "d" * 64,
        )

    adapter.invoke = unexpected
    first = runner.execute_next(grant, prepared, adapter)

    assert first.state is RecoveryAdapterRunState.STEP_UNKNOWN
    assert first.result is not None
    assert executions.step_outcome(prepared, grant.claim, 1) is RecoveryStepOutcome.UNKNOWN
    again = runner.execute_next(grant, prepared, adapter)
    assert again.state is RecoveryAdapterRunState.STEP_UNKNOWN
    assert len(adapter.calls) == 1
    assert {field.name for field in fields(GuardianRecoveryAdapterObservation)} == {
        "adapter_id",
        "adapter_action_id",
        "step_order",
        "outcome",
        "dispatch_started",
        "timed_out",
        "evidence_sha256",
    }
