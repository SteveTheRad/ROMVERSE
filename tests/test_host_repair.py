from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from romverse.guardian.approval import ApprovalStore
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.models import GuardianDeniedError, OperationClass, OperationRequest
from romverse.guardian.policy import GuardianPolicy
from romverse.infrastructure.process import CommandResult
from romverse.repair.host import (
    ADB_HOST_REPAIR_TARGET,
    AdbHostRepairError,
    AdbHostRepairMode,
    AdbHostRepairReceiptStore,
    AdbHostRepairService,
    AdbHostRepairStatus,
)


class HostRepairRunner:
    def __init__(self, failures: dict[tuple[str, ...], int] | None = None) -> None:
        self.failures = failures or {}
        self.calls: list[tuple[str, ...]] = []

    def run(self, args, timeout=10, cwd=None):
        call = tuple(str(part) for part in args)
        self.calls.append(call)
        returncode = self.failures.get(call[1:], 0)
        output = "List of devices attached\nPRIVATE-SERIAL device\n" if "devices" in call else ""
        return CommandResult(call, returncode, output, "failed" if returncode else "")


def service(tmp_path: Path, runner: HostRepairRunner) -> AdbHostRepairService:
    adb = tmp_path / "adb"
    adb.write_bytes(b"verified adb test executable")
    adb.chmod(0o755)
    approvals = ApprovalStore(tmp_path)
    gateway = ExecutionGateway(GuardianPolicy(tmp_path), runner)
    return AdbHostRepairService(
        adb,
        gateway,
        approvals,
        AdbHostRepairReceiptStore(tmp_path),
    )


def test_adb_host_repair_requires_exact_approval_and_runs_no_device_command(tmp_path) -> None:
    runner = HostRepairRunner()
    recovery = service(tmp_path, runner)
    plan = recovery.plan(AdbHostRepairMode.RESTART, "ADB discovery failed")

    with pytest.raises(AdbHostRepairError, match="not been approved"):
        recovery.execute(plan)
    assert runner.calls == []

    recovery.approve(plan)
    result = recovery.execute(plan)

    assert result.status is AdbHostRepairStatus.SUCCEEDED
    assert result.receipt_saved
    assert result.receipt_ref.startswith("diagnostics/host-repair-receipts/")
    assert (tmp_path / result.receipt_ref).is_file()
    assert runner.calls == [
        (str(tmp_path / "adb"), "kill-server"),
        (str(tmp_path / "adb"), "start-server"),
        (str(tmp_path / "adb"), "devices", "-l"),
    ]
    assert all("-s" not in call for call in runner.calls)


def test_adb_host_repair_attempts_daemon_restore_after_unclean_stop(tmp_path) -> None:
    runner = HostRepairRunner({("kill-server",): 1})
    recovery = service(tmp_path, runner)
    plan = recovery.plan(AdbHostRepairMode.RESTART, "ADB transport is offline")
    recovery.approve(plan)

    result = recovery.execute(plan)

    assert result.status is AdbHostRepairStatus.ATTENTION
    assert [call[1:] for call in runner.calls] == [
        ("kill-server",),
        ("start-server",),
        ("devices", "-l"),
    ]


def test_adb_host_repair_does_not_claim_success_when_daemon_start_fails(tmp_path) -> None:
    runner = HostRepairRunner({("start-server",): 1})
    recovery = service(tmp_path, runner)
    plan = recovery.plan(AdbHostRepairMode.START, "ADB daemon is unavailable")
    recovery.approve(plan)

    result = recovery.execute(plan)

    assert result.status is AdbHostRepairStatus.FAILED
    assert [call[1:] for call in runner.calls] == [("start-server",)]
    assert recovery.receipts.load_latest().valid


def test_adb_host_repair_revalidates_binary_after_approval(tmp_path) -> None:
    runner = HostRepairRunner()
    recovery = service(tmp_path, runner)
    plan = recovery.plan(AdbHostRepairMode.START, "ADB daemon is unavailable")
    recovery.approve(plan)
    Path(plan.executable_path).write_bytes(b"changed after approval")

    with pytest.raises(AdbHostRepairError, match="changed"):
        recovery.execute(plan)
    assert runner.calls == []


def test_adb_host_repair_receipt_is_private_integrity_bound_and_tamper_detected(tmp_path) -> None:
    runner = HostRepairRunner()
    recovery = service(tmp_path, runner)
    plan = recovery.plan(AdbHostRepairMode.START, "ADB daemon is unavailable")
    recovery.approve(plan)
    recovery.execute(plan)

    store = recovery.receipts
    verified = store.load_latest()
    assert verified.valid
    assert verified.integrity_verified
    assert verified.data is not None
    encoded = json.dumps(verified.data)
    assert "PRIVATE-SERIAL" not in encoded
    assert '"device_commands_executed": false' in encoded
    assert '"phone_changed": false' in encoded
    assert '"bootloader_relock": "never"' in encoded

    payload = json.loads(store.latest_path.read_text(encoding="utf-8"))
    payload["phone_changed"] = True
    store.latest_path.write_text(json.dumps(payload), encoding="utf-8")
    rejected = store.load_latest()
    assert not rejected.valid
    assert "rejected" in rejected.reason.casefold()


def test_adb_host_repair_receipt_rejects_oversized_and_symlink_files(tmp_path) -> None:
    runner = HostRepairRunner()
    recovery = service(tmp_path, runner)
    plan = recovery.plan(AdbHostRepairMode.START, "ADB daemon is unavailable")
    recovery.approve(plan)
    recovery.execute(plan)
    store = recovery.receipts

    store.latest_path.write_bytes(b"{" + b" " * store.MAX_RECEIPT_BYTES + b"}")
    oversized = store.load_latest()
    assert not oversized.valid
    assert "size boundary" in oversized.reason

    outside = tmp_path / "outside.json"
    outside.write_text('{"private":"untouched"}', encoding="utf-8")
    store.latest_path.unlink()
    store.latest_path.symlink_to(outside)
    linked = store.load_latest()
    assert not linked.valid
    assert outside.read_text(encoding="utf-8") == '{"private":"untouched"}'


def test_adb_host_repair_receipt_write_rejects_symlinked_store_directory(tmp_path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "diagnostics").symlink_to(outside, target_is_directory=True)
    runner = HostRepairRunner()
    recovery = service(tmp_path, runner)
    plan = recovery.plan(AdbHostRepairMode.START, "ADB daemon is unavailable")
    recovery.approve(plan)

    result = recovery.execute(plan)

    assert result.status is AdbHostRepairStatus.SUCCEEDED
    assert not result.receipt_saved
    assert list(outside.iterdir()) == []


def test_adb_host_repair_receipts_are_private_files(tmp_path) -> None:
    runner = HostRepairRunner()
    recovery = service(tmp_path, runner)
    plan = recovery.plan(AdbHostRepairMode.START, "ADB daemon is unavailable")
    recovery.approve(plan)
    recovery.execute(plan)

    mode = stat.S_IMODE(recovery.receipts.latest_path.stat().st_mode)
    assert mode == 0o600


def test_guardian_rejects_unapproved_or_device_addressed_host_repair(tmp_path) -> None:
    runner = HostRepairRunner()
    policy = GuardianPolicy(tmp_path)
    gateway = ExecutionGateway(policy, runner)
    unapproved = OperationRequest(
        "repair.adb_start_server",
        OperationClass.STATE_CHANGING,
        str(tmp_path / "adb"),
        ("start-server",),
        "recover host ADB",
        ADB_HOST_REPAIR_TARGET,
        "a" * 64,
        ADB_HOST_REPAIR_TARGET,
    )
    with pytest.raises(GuardianDeniedError):
        gateway.execute(unapproved)

    approvals = ApprovalStore(tmp_path)
    approvals.issue("a" * 64, ADB_HOST_REPAIR_TARGET)
    addressed = OperationRequest(
        "repair.adb_start_server",
        OperationClass.STATE_CHANGING,
        str(tmp_path / "adb"),
        ("-s", "PRIVATE-SERIAL", "start-server"),
        "invalid device-addressed repair",
        ADB_HOST_REPAIR_TARGET,
        "a" * 64,
        ADB_HOST_REPAIR_TARGET,
    )
    with pytest.raises(GuardianDeniedError):
        gateway.execute(addressed)
    assert runner.calls == []
