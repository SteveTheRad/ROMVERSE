from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from romverse.companion.usb_assist import UsbPairingAssistService
from romverse.companion.usb_contract import (
    USB_PAIRING_ACTION,
    USB_PAIRING_CODE_EXTRA,
    USB_PAIRING_COMPONENT,
    usb_launch_arguments,
    usb_reverse_arguments,
    usb_reverse_remove_arguments,
)
from romverse.guardian.approval import ApprovalStore
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.models import GuardianDeniedError, OperationClass, OperationRequest
from romverse.guardian.policy import GuardianPolicy
from romverse.infrastructure.process import CommandResult


class RecordingUsbRunner:
    def __init__(self, *, fail_launch: bool = False) -> None:
        self.fail_launch = fail_launch
        self.calls: list[tuple[str, ...]] = []

    def run(self, args, timeout=10, cwd=None):
        call = tuple(args)
        self.calls.append(call)
        failed = self.fail_launch and call[4:6] == ("am", "start")
        return CommandResult(
            call, 1 if failed else 0, "" if failed else "OK", "failed" if failed else ""
        )


def service_and_plan(tmp_path: Path, *, fail_launch: bool = False):
    runner = RecordingUsbRunner(fail_launch=fail_launch)
    approvals = ApprovalStore(tmp_path)
    service = UsbPairingAssistService(
        Path("/usr/bin/adb"),
        ExecutionGateway(GuardianPolicy(tmp_path), runner),
        approvals,
        tmp_path,
    )
    plan = service.prepare(
        serial="phone-123",
        port=8765,
        certificate_sha256="a" * 64,
        pairing_code="123 456",
        expires_at=(datetime.now(UTC) + timedelta(minutes=9)).isoformat(),
    )
    return service, plan, runner


def test_usb_pairing_contract_is_exact_and_loopback_only() -> None:
    args = usb_launch_arguments("phone-123", 8765, "A" * 64, "123 456")

    assert args[:12] == (
        "-s",
        "phone-123",
        "shell",
        "am",
        "start",
        "-W",
        "-f",
        "0x20000000",
        "-a",
        USB_PAIRING_ACTION,
        "-n",
        USB_PAIRING_COMPONENT,
    )
    assert args[-3:] == ("--es", USB_PAIRING_CODE_EXTRA, "123456")
    assert "127.0.0.1:8765" in args
    assert usb_reverse_arguments("phone-123", 8765) == (
        "-s",
        "phone-123",
        "reverse",
        "tcp:8765",
        "tcp:8765",
    )


@pytest.mark.parametrize(
    ("serial", "port", "fingerprint", "code"),
    [
        ("bad serial", 8765, "a" * 64, "123456"),
        ("phone", 0, "a" * 64, "123456"),
        ("phone", 8765, "a" * 63, "123456"),
        ("phone", 8765, "a" * 64, "12x456"),
    ],
)
def test_usb_pairing_contract_rejects_unbounded_inputs(
    serial: str,
    port: int,
    fingerprint: str,
    code: str,
) -> None:
    with pytest.raises(ValueError):
        usb_launch_arguments(serial, port, fingerprint, code)


def test_usb_pairing_requires_approval_then_opens_exact_phone_confirmation(tmp_path) -> None:
    service, plan, runner = service_and_plan(tmp_path)

    with pytest.raises(GuardianDeniedError, match="has not been approved"):
        service.launch(plan)
    assert runner.calls == []

    records = service.approve(plan)
    result = service.launch(plan)

    assert len(records) == 3
    assert result.ok
    assert runner.calls == [
        ("/usr/bin/adb", *usb_reverse_arguments("phone-123", 8765)),
        ("/usr/bin/adb", *usb_launch_arguments("phone-123", 8765, "a" * 64, "123456")),
    ]


def test_usb_pairing_removes_tunnel_if_companion_confirmation_cannot_open(tmp_path) -> None:
    service, plan, runner = service_and_plan(tmp_path, fail_launch=True)
    service.approve(plan)

    result = service.launch(plan)

    assert not result.ok
    assert result.cleanup is not None and result.cleanup.ok
    assert runner.calls[-1] == (
        "/usr/bin/adb",
        *usb_reverse_remove_arguments("phone-123", 8765),
    )


def test_guardian_rejects_mutated_usb_pairing_handoff_after_approval(tmp_path) -> None:
    service, plan, runner = service_and_plan(tmp_path)
    service.approve(plan)
    expected = plan.arguments_for("companion.usb_launch")
    mutated = (*expected[:-1], "654321")
    request = OperationRequest(
        "companion.usb_launch",
        OperationClass.STATE_CHANGING,
        "/usr/bin/adb",
        mutated,
        "mutated test",
        plan.serial,
        plan.digest_for("companion.usb_launch"),
        plan.target_key,
    )

    with pytest.raises(GuardianDeniedError, match="differs from the approved"):
        service.gateway.execute(request)

    assert runner.calls == []
