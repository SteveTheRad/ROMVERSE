from pathlib import Path

from romverse.device.adb import AdbClient
from romverse.device.engine import DeviceEngine
from romverse.device.models import DeviceState
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.policy import MilestoneOnePolicy
from romverse.infrastructure.process import CommandResult


class FakeAdbRunner:
    def run(self, args, timeout=10):
        key = tuple(args[1:])
        outputs = {
            (
                "devices",
                "-l",
            ): "List of devices attached\nSERIAL123 device product:test model:Rad_Phone device:rad transport_id:1\nWAIT unauthorized usb:1-2\n",
            ("-s", "SERIAL123", "shell", "getprop"): "\n".join(
                [
                    "[ro.product.manufacturer]: [RadForge]",
                    "[ro.product.brand]: [ROMVERSE]",
                    "[ro.product.model]: [Rad Phone]",
                    "[ro.product.marketname]: [ROMVERSE One]",
                    "[ro.product.name]: [rad_global]",
                    "[ro.product.device]: [rad]",
                    "[ro.build.version.release]: [15]",
                    "[ro.build.version.sdk]: [35]",
                    "[ro.build.id]: [AP4A]",
                    "[ro.build.version.security_patch]: [2026-08-01]",
                    "[ro.product.cpu.abi]: [arm64-v8a]",
                    "[ro.boot.flash.locked]: [1]",
                    "[ro.boot.verifiedbootstate]: [green]",
                    "[ro.boot.slot_suffix]: [_a]",
                    "[ro.soc.model]: [Snapdragon Test Platform]",
                    "[ro.crypto.state]: [encrypted]",
                    "[ro.crypto.type]: [file]",
                    "[ro.build.ab_update]: [true]",
                    "[ro.virtual_ab.enabled]: [true]",
                    "[ro.boot.dynamic_partitions]: [true]",
                    "[ro.fastbootd.available]: [true]",
                    "[sys.boot_completed]: [1]",
                ]
            ),
            (
                "-s",
                "SERIAL123",
                "shell",
                "dumpsys",
                "battery",
            ): "level: 77\nstatus: 3\ntemperature: 301\n",
            (
                "-s",
                "SERIAL123",
                "shell",
                "df",
                "-k",
                "/data",
            ): "/dev/dm 200000 50000 150000 25% /data\n",
            (
                "-s",
                "SERIAL123",
                "shell",
                "cat",
                "/proc/meminfo",
            ): "MemTotal: 8000000 kB\nMemAvailable: 6000000 kB\n",
            ("-s", "SERIAL123", "shell", "cat", "/proc/uptime"): "1234.50 900.00\n",
            ("-s", "SERIAL123", "shell", "uname", "-r"): "6.12.23-popsicle\n",
            ("-s", "SERIAL123", "shell", "id"): "uid=2000(shell) gid=2000(shell)\n",
        }
        output = outputs.get(key)
        return CommandResult(
            tuple(args),
            0 if output is not None else 1,
            output or "",
            "unknown fake command" if output is None else "",
        )


def test_device_engine_builds_real_snapshot_and_preserves_unauthorized():
    gateway = ExecutionGateway(MilestoneOnePolicy(), FakeAdbRunner())
    devices = DeviceEngine(AdbClient(Path("adb"), gateway)).scan()
    assert len(devices) == 2
    phone = devices[0]
    assert phone.manufacturer == "RadForge"
    assert phone.brand == "ROMVERSE"
    assert phone.marketing_name == "ROMVERSE One"
    assert phone.display_name == "RadForge ROMVERSE One"
    assert phone.android_version == "15"
    assert phone.battery_percent == 77
    assert phone.memory.percent_used == 25
    assert phone.bootloader_locked is True
    assert phone.root_detected is False
    assert phone.root_signal_source == "adb-shell-id"
    assert phone.root_manager_candidate == "none"
    assert phone.root_manager_evidence == "allowlisted-package-presence"
    assert phone.boot_completed is True
    assert phone.uptime_seconds == 1234
    assert phone.slot_suffix == "_a"
    assert phone.kernel_version == "6.12.23-popsicle"
    assert phone.soc_platform == "Snapdragon Test Platform"
    assert phone.encryption_state == "encrypted"
    assert phone.encryption_type == "file"
    assert phone.ab_update is True
    assert phone.virtual_ab is True
    assert phone.dynamic_partitions is True
    assert phone.fastboot_capability == "fastbootd reported by Android"
    assert phone.masked_serial() == "••••L123"
    assert devices[1].state is DeviceState.UNAUTHORIZED
    assert "accept" in devices[1].connection_note.lower()


class RootManagerRunner(FakeAdbRunner):
    def run(self, args, timeout=10):
        if tuple(args[1:]) == (
            "-s",
            "SERIAL123",
            "shell",
            "pm",
            "path",
            "com.topjohnwu.magisk",
        ):
            return CommandResult(tuple(args), 0, "package:/data/app/magisk/base.apk\n", "")
        return super().run(args, timeout)


def test_device_engine_reports_manager_presence_as_a_candidate_not_root_proof():
    gateway = ExecutionGateway(MilestoneOnePolicy(), RootManagerRunner())

    phone = DeviceEngine(AdbClient(Path("adb"), gateway)).scan()[0]

    assert phone.root_detected is False
    assert phone.root_manager_candidate == "magisk"
    assert phone.root_manager_evidence == "allowlisted-package-presence"


class ReconnectRunner(FakeAdbRunner):
    def __init__(self) -> None:
        self.transport_id = "1"
        self.calls: list[tuple[str, ...]] = []

    def run(self, args, timeout=10):
        call = tuple(args)
        self.calls.append(call)
        if tuple(args[1:]) == ("devices", "-l"):
            return CommandResult(
                call,
                0,
                "List of devices attached\n"
                f"SERIAL123 device usb:1-2.3 product:test model:Rad_Phone "
                f"device:rad transport_id:{self.transport_id}\n",
                "",
            )
        return super().run(args, timeout)


def test_reconnect_safe_scan_waits_for_stable_transport_and_caches_details():
    runner = ReconnectRunner()
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner)
    engine = DeviceEngine(AdbClient(Path("adb"), gateway))

    first = engine.scan_reconnect_safe()[0]
    assert "waiting for one stable transport cycle" in first.connection_note
    assert len(runner.calls) == 1

    second = engine.scan_reconnect_safe()[0]
    assert second.marketing_name == "ROMVERSE One"
    detailed_call_count = len(runner.calls)
    assert detailed_call_count > 2

    cached = engine.scan_reconnect_safe()[0]
    assert cached == second
    assert len(runner.calls) == detailed_call_count + 1

    runner.transport_id = "2"
    reconnected = engine.scan_reconnect_safe()[0]
    assert "waiting for one stable transport cycle" in reconnected.connection_note
    assert len(runner.calls) == detailed_call_count + 2


class TimedOutProbeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, args, timeout=10):
        call = tuple(args)
        self.calls.append(call)
        if tuple(args[1:]) == ("devices", "-l"):
            return CommandResult(
                call,
                0,
                "List of devices attached\n"
                "SERIAL123 device usb:1-2.3 product:test model:Rad_Phone "
                "device:rad transport_id:1\n",
                "",
            )
        return CommandResult(call, 124, "", "USB transport timed out", timed_out=True)


def test_device_engine_stops_probe_chain_after_usb_transport_timeout():
    runner = TimedOutProbeRunner()
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner)
    engine = DeviceEngine(AdbClient(Path("adb"), gateway))

    device = engine.scan()[0]

    assert len(runner.calls) == 2
    assert "USB reconnect is unstable" in device.connection_note
    assert device.errors == ("adb.getprop: USB transport timed out",)
