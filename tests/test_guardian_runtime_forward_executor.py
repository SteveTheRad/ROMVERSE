from __future__ import annotations

import json
from dataclasses import replace
from itertools import count
from pathlib import Path

import pytest

from romverse.guardian.execution_gateway_contract import GatewayStepPhase
from romverse.guardian.execution_result_receipt import (
    ExecutionTerminalState,
    GatewayResultOutcome,
)
from romverse.guardian.runtime_forward_executor import (
    GuardianRuntimeForwardExecutor,
    RuntimeForwardExecutionError,
)
from romverse.infrastructure.process import CommandResult
from tests.test_guardian_runtime_execution_claim import _CLAIM_AT, _claim, _ready

pytest_plugins = ("tests.test_guardian_runtime_session",)


class _RuntimeFixture:
    def __init__(self, context, *, discovered_serial: str | None = None, fail_write=False):
        self.context = context
        self.gateway = context["gateway"]
        self.serial = context["reviewed"].serial
        self.discovered_serial = discovered_serial or self.serial
        self.fail_write = fail_write
        self.mode = self.gateway.transition_entry_mode or "bootloader"
        self.slot = context["live"].recorded_prewrite_slot or "a"
        self.calls: list[tuple[str, ...]] = []

    def run(self, args, timeout=10, cwd=None):
        del timeout, cwd
        command = tuple(str(item) for item in args)
        self.calls.append(command)
        tool = Path(command[0]).name.casefold()
        tail = command[1:]
        if tool == "fastboot":
            return self._fastboot(command, tail)
        if tool == "adb":
            return self._adb(command, tail)
        return CommandResult(command, 127, "", "unknown fixture tool")

    def _fastboot(self, command, tail):
        if tail == ("devices", "-l"):
            if self.mode == "system":
                return CommandResult(command, 0, "", "")
            return CommandResult(
                command,
                0,
                f"{self.discovered_serial} fastboot usb:1-1\n",
                "",
            )
        if len(tail) < 3 or tail[:2] != ("-s", self.serial):
            return CommandResult(command, 1, "", "wrong exact target")
        action = tail[2:]
        if action[:1] == ("getvar",):
            variable = action[1]
            value = self._getvar(variable)
            return CommandResult(command, 0, "", f"(bootloader) {variable}: {value}\n")
        if action == ("reboot", "fastboot"):
            self.mode = "fastbootd"
            return CommandResult(command, 0, "", "")
        if action == ("reboot", "bootloader"):
            self.mode = "bootloader"
            return CommandResult(command, 0, "", "")
        if action == ("reboot",):
            self.mode = "system"
            return CommandResult(command, 0, "", "")
        if action[:1] == ("set_active",):
            self.slot = action[1]
            return CommandResult(command, 0, "", "")
        if "flash" in action:
            return CommandResult(
                command,
                1 if self.fail_write else 0,
                "",
                "fixture write failure" if self.fail_write else "",
            )
        if "fetch" in action:
            output = Path(action[-1])
            partition = action[-2]
            target_slot = action[action.index("--slot") + 1] if "--slot" in action else "none"
            write = next(
                step
                for step in self.gateway.steps
                if step.phase is GatewayStepPhase.WRITE
                and step.partition == partition
                and step.target_slot == target_slot
            )
            source = self.context["plans"].store.workspace / write.artifact_relative_path
            output.write_bytes(source.read_bytes())
            return CommandResult(command, 0, "", "")
        return CommandResult(command, 1, "", "unsupported fixture command")

    def _adb(self, command, tail):
        if tail == ("devices", "-l"):
            body = (
                f"List of devices attached\n{self.serial}\tdevice product:fixture\n"
                if self.mode == "system"
                else "List of devices attached\n"
            )
            return CommandResult(command, 0, body, "")
        if (
            len(tail) == 5
            and tail[:2] == ("-s", self.serial)
            and tail[2:4]
            == (
                "shell",
                "getprop",
            )
        ):
            property_name = tail[4]
            expected = next(
                step.expected_value
                for step in self.gateway.steps
                if step.property_name == property_name
            )
            return CommandResult(command, 0, f"{expected}\n", "")
        return CommandResult(command, 1, "", "unsupported fixture command")

    def _getvar(self, variable):
        if variable == "product":
            return next(
                step.expected_value
                for step in self.gateway.steps
                if step.arguments[-2:] == ("getvar", "product")
            )
        if variable == "unlocked":
            return "yes"
        if variable == "is-userspace":
            return "yes" if self.mode == "fastbootd" else "no"
        if variable == "current-slot":
            return self.slot
        if variable.startswith("has-slot:"):
            return "yes"
        return ""


class _FixtureExecutor(GuardianRuntimeForwardExecutor):
    """Bridge historical arbitrary fixture digests while preserving real file creation."""

    def __init__(self, *args, gateway, **kwargs):
        super().__init__(*args, **kwargs)
        self.fixture_gateway = gateway

    def _measure_output(self, path, output_root):
        super()._measure_output(path, output_root)
        step = next(
            item
            for item in self.fixture_gateway.steps
            if item.output_relative_path and path.as_posix().endswith(item.output_relative_path)
        )
        return step.expected_size_bytes, step.expected_sha256


def _tools(tmp_path: Path) -> tuple[Path, Path]:
    paths = []
    for name in ("fastboot", "adb"):
        path = tmp_path / name
        path.write_text("fixture executable\n", encoding="utf-8")
        path.chmod(0o700)
        paths.append(path)
    return paths[0], paths[1]


def _prepared_executor(runtime_context, tmp_path, *, runner=None):
    claims, runtime_grant, grant, reservation, session = _ready(runtime_context)
    permit = _claim(claims, runtime_context, runtime_grant, grant, reservation, session)
    fixture = runner or _RuntimeFixture(runtime_context)
    fastboot, adb = _tools(tmp_path)
    ticks = count()
    executor = _FixtureExecutor(
        claims,
        fixture,
        gateway=runtime_context["gateway"],
        fastboot_path=fastboot,
        adb_path=adb,
        clock=lambda: _CLAIM_AT,
        monotonic=lambda: float(next(ticks) * 1_000),
        sleeper=lambda _seconds: None,
    )
    chain = (permit, runtime_grant, grant, reservation, session)
    return executor, fixture, chain


def _execute(executor, context, chain, **kwargs):
    permit, runtime_grant, grant, reservation, session = chain
    return executor.execute(
        permit,
        runtime_grant,
        grant,
        reservation,
        session,
        context["gateway"],
        context["plan"],
        context["live"],
        context["reviewed"],
        context["trust"],
        context["private_key"].public_key(),
        context["private_key"],
        **kwargs,
    )


def test_forward_runtime_executes_exact_gateway_and_signs_verified_result(
    runtime_context,
    tmp_path,
) -> None:
    executor, fixture, chain = _prepared_executor(runtime_context, tmp_path)

    verified = _execute(executor, runtime_context, chain)
    receipt = verified.receipt

    assert receipt.terminal_state is ExecutionTerminalState.SUCCEEDED
    assert receipt.forward_result_count == runtime_context["gateway"].step_count
    assert all(result.outcome is GatewayResultOutcome.PASSED for result in receipt.forward_results)
    assert receipt.phone_change_attempted
    assert receipt.phone_change_verified
    assert not receipt.phone_state_uncertain
    assert receipt.postconditions_verified
    assert fixture.calls[0][1:] == ("devices", "-l")
    assert fixture.calls[1][1:4] == ("-s", runtime_context["reviewed"].serial, "getvar")
    forbidden = {"erase", "format", "wipe", "unlock", "lock", "relock"}
    assert not any(token.casefold() in forbidden for call in fixture.calls for token in call)

    guardian = (
        runtime_context["plans"].store.projects_root
        / runtime_context["gateway"].project_id
        / "guardian"
    )
    result_paths = tuple(guardian.glob("execution-result-*.romverse"))
    open_paths = tuple(guardian.glob("runtime-device-open-*.romverse"))
    assert len(result_paths) == 1
    assert len(open_paths) == 1
    saved = open_paths[0].read_text(encoding="utf-8")
    assert chain[0].target_serial not in saved
    assert chain[0].ephemeral_open_token not in saved
    assert json.loads(saved)["record"]["forward_scope_only"] is True
    assert chain[0].target_serial not in result_paths[0].read_text(encoding="utf-8")


def test_runtime_permit_is_consumed_once_and_cannot_be_replayed(
    runtime_context,
    tmp_path,
) -> None:
    executor, _fixture, chain = _prepared_executor(runtime_context, tmp_path)
    _execute(executor, runtime_context, chain, should_cancel=lambda: True)

    with pytest.raises(RuntimeForwardExecutionError, match="already been consumed"):
        _execute(executor, runtime_context, chain, should_cancel=lambda: True)


def test_wrong_fresh_target_aborts_before_any_gateway_step(runtime_context, tmp_path) -> None:
    fixture = _RuntimeFixture(runtime_context, discovered_serial="OTHER-SERIAL")
    executor, fixture, chain = _prepared_executor(runtime_context, tmp_path, runner=fixture)

    receipt = _execute(executor, runtime_context, chain).receipt

    assert receipt.terminal_state is ExecutionTerminalState.ABORTED
    assert receipt.forward_result_count == 0
    assert not receipt.phone_change_attempted
    assert fixture.calls == [(str(executor.fastboot_path.resolve()), "devices", "-l")]


def test_artifact_change_fails_before_permit_consumption_or_device_access(
    runtime_context,
    tmp_path,
) -> None:
    executor, fixture, chain = _prepared_executor(runtime_context, tmp_path)
    write = next(
        step for step in runtime_context["gateway"].steps if step.phase is GatewayStepPhase.WRITE
    )
    artifact = runtime_context["plans"].store.workspace / write.artifact_relative_path
    artifact.write_bytes(artifact.read_bytes() + b"tampered")

    with pytest.raises(RuntimeForwardExecutionError, match="Artifact size changed"):
        _execute(executor, runtime_context, chain)

    assert fixture.calls == []
    guardian = (
        runtime_context["plans"].store.projects_root
        / runtime_context["gateway"].project_id
        / "guardian"
    )
    assert not tuple(guardian.glob("runtime-device-open-*.romverse"))


def test_same_size_artifact_change_is_rejected_by_digest_before_device_access(
    runtime_context,
    tmp_path,
) -> None:
    executor, fixture, chain = _prepared_executor(runtime_context, tmp_path)
    write = next(
        step for step in runtime_context["gateway"].steps if step.phase is GatewayStepPhase.WRITE
    )
    artifact = runtime_context["plans"].store.workspace / write.artifact_relative_path
    original = artifact.read_bytes()
    artifact.write_bytes(bytes([original[0] ^ 1]) + original[1:])

    with pytest.raises(RuntimeForwardExecutionError, match="Artifact digest changed"):
        _execute(executor, runtime_context, chain)

    assert fixture.calls == []


def test_real_readback_measurement_rejects_wrong_size_and_digest(
    runtime_context,
    tmp_path,
) -> None:
    fixture = _RuntimeFixture(runtime_context)
    fixture_executor, fixture, chain = _prepared_executor(
        runtime_context,
        tmp_path,
        runner=fixture,
    )
    ticks = count()
    executor = GuardianRuntimeForwardExecutor(
        fixture_executor.claims,
        fixture,
        fastboot_path=fixture_executor.fastboot_path,
        adb_path=fixture_executor.adb_path,
        clock=lambda: _CLAIM_AT,
        monotonic=lambda: float(next(ticks) * 1_000),
        sleeper=lambda _seconds: None,
    )

    receipt = _execute(executor, runtime_context, chain).receipt

    assert receipt.terminal_state is ExecutionTerminalState.FAILED
    assert receipt.forward_results[-1].operation_id.startswith("guardian.verify.readback")
    assert receipt.forward_results[-1].error_code == "EVIDENCE_MISMATCH"
    assert not receipt.postconditions_verified


def test_write_failure_stops_exact_prefix_and_never_runs_recovery(
    runtime_context,
    tmp_path,
) -> None:
    fixture = _RuntimeFixture(runtime_context, fail_write=True)
    executor, fixture, chain = _prepared_executor(runtime_context, tmp_path, runner=fixture)

    receipt = _execute(executor, runtime_context, chain).receipt

    assert receipt.terminal_state is ExecutionTerminalState.FAILED
    assert receipt.forward_results[-1].outcome is GatewayResultOutcome.FAILED
    assert receipt.forward_results[-1].error_code == "COMMAND_FAILED"
    assert receipt.phone_change_attempted
    assert receipt.phone_state_uncertain
    assert not receipt.postconditions_verified
    failed_operation = receipt.forward_results[-1].operation_id
    failed_index = next(
        index
        for index, step in enumerate(runtime_context["gateway"].steps)
        if step.operation_id == failed_operation
    )
    assert receipt.forward_result_count == failed_index + 1
    recovery_ids = {step.adapter_action_id for step in runtime_context["gateway"].recovery_steps}
    assert not any(
        any(action in token for action in recovery_ids) for call in fixture.calls for token in call
    )


def test_wrong_private_key_and_unsafe_tool_link_fail_before_device_access(
    runtime_context,
    tmp_path,
) -> None:
    executor, fixture, chain = _prepared_executor(runtime_context, tmp_path)
    wrong = replace(chain[0], ephemeral_open_token="0" * 64)
    wrong_chain = (wrong, *chain[1:])
    with pytest.raises(RuntimeForwardExecutionError, match="before device access"):
        _execute(executor, runtime_context, wrong_chain)
    assert fixture.calls == []

    if executor.fastboot_path.is_symlink():
        pytest.skip("fixture host does not support an ordinary tool path")
    link = tmp_path / "tools" / "fastboot"
    link.parent.mkdir()
    link.symlink_to(executor.fastboot_path)
    executor.fastboot_path = link
    with pytest.raises(RuntimeForwardExecutionError, match="regular executable"):
        _execute(executor, runtime_context, chain)
    assert fixture.calls == []
