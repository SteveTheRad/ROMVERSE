from __future__ import annotations

import pytest

from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.models import GuardianDeniedError, OperationClass, OperationRequest
from romverse.guardian.policy import MilestoneOnePolicy
from romverse.infrastructure.process import CommandResult


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, args, timeout=10):
        self.calls.append(tuple(args))
        return CommandResult(tuple(args), 0, "", "")


def request(
    category=OperationClass.READ_ONLY,
    arguments=("devices", "-l"),
    *,
    operation_id="test",
    executable="adb",
    target="host",
):
    return OperationRequest(operation_id, category, executable, arguments, "test", target)


def test_allows_known_read_only_probe():
    runner = RecordingRunner()
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner)
    gateway.execute(request())
    assert runner.calls == [("adb", "devices", "-l")]


@pytest.mark.parametrize(
    "category",
    [OperationClass.STATE_CHANGING, OperationClass.PRIVILEGED, OperationClass.DESTRUCTIVE],
)
def test_denies_non_read_only_before_execution(category):
    runner = RecordingRunner()
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner)
    with pytest.raises(GuardianDeniedError):
        gateway.execute(request(category, ("reboot", "bootloader")))
    assert runner.calls == []


def test_denies_unknown_command_even_when_mislabeled_read_only():
    runner = RecordingRunner()
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner)
    with pytest.raises(GuardianDeniedError):
        gateway.execute(request(arguments=("install", "payload.apk")))
    assert runner.calls == []


@pytest.mark.parametrize(
    "arguments",
    (("flashing", "lock"), ("flashing", "lock_critical"), ("oem", "lock")),
)
def test_bootloader_relock_is_permanently_denied_before_execution(arguments):
    runner = RecordingRunner()
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner)
    operation = OperationRequest(
        "guardian.flash",
        OperationClass.STATE_CHANGING,
        "fastboot",
        arguments,
        "forbidden relock",
    )

    with pytest.raises(GuardianDeniedError, match="permanently prohibits"):
        gateway.execute(operation)
    assert runner.calls == []


@pytest.mark.parametrize(
    "arguments",
    [
        ("-s", "serial", "shell", "getprop", "ro.product.model"),
        ("-s", "serial", "shell", "getprop", "ro.build.version.release"),
        ("-s", "serial", "shell", "getprop", "ro.boot.verifiedbootstate"),
        ("-s", "serial", "shell", "df", "-k", "/data"),
        ("-s", "serial", "shell", "cat", "/proc/uptime"),
        ("-s", "serial", "shell", "pm", "path", "com.topjohnwu.magisk"),
        ("-s", "serial", "shell", "pm", "path", "me.weishu.kernelsu"),
    ],
)
def test_allows_bounded_console_device_probes(arguments):
    runner = RecordingRunner()
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner)

    gateway.execute(request(arguments=arguments))

    assert runner.calls == [("adb", *arguments)]


def test_allows_only_exact_guardian_named_fastboot_identity_probes() -> None:
    runner = RecordingRunner()
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner)

    gateway.execute(
        request(
            executable="fastboot",
            operation_id="fastboot.devices",
            arguments=("devices", "-l"),
        )
    )
    gateway.execute(
        request(
            executable="fastboot",
            operation_id="fastboot.getvar.is-userspace",
            arguments=("-s", "serial", "getvar", "is-userspace"),
            target="serial",
        )
    )

    assert runner.calls == [
        ("fastboot", "devices", "-l"),
        ("fastboot", "-s", "serial", "getvar", "is-userspace"),
    ]


@pytest.mark.parametrize(
    ("operation_id", "arguments"),
    [
        ("fastboot.getvar.all", ("-s", "serial", "getvar", "all")),
        ("fastboot.flash", ("-s", "serial", "flash", "boot", "boot.img")),
        ("fastboot.reboot", ("-s", "serial", "reboot")),
    ],
)
def test_denies_fastboot_commands_outside_exact_read_only_identity_allowlist(
    operation_id,
    arguments,
) -> None:
    runner = RecordingRunner()
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner)

    with pytest.raises(GuardianDeniedError):
        gateway.execute(
            request(
                executable="fastboot",
                operation_id=operation_id,
                arguments=arguments,
                target="serial",
            )
        )

    assert runner.calls == []
