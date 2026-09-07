from pathlib import Path

from romverse.device.adb import AdbClient
from romverse.device.engine import DeviceEngine
from romverse.device.fastboot import FastbootClient
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
                    "[ro.product.vendor.device]: [rad_vendor]",
                    "[ro.hardware]: [rad_board]",
                    "[ro.boot.hardware.sku]: [pro]",
                    "[ro.build.version.release]: [15]",
                    "[ro.build.version.sdk]: [35]",
                    "[ro.build.id]: [AP4A]",
                    "[ro.build.version.incremental]: [123456]",
                    "[ro.build.date.utc]: [1788220800]",
                    "[ro.system.build.fingerprint]: [RadForge/rad/system:15/AP4A/789:user/release-keys]",
                    "[ro.system.build.version.incremental]: [789]",
                    "[ro.system.build.date.utc]: [1788220700]",
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


class AdbTransportRunner(FakeAdbRunner):
    def __init__(self, serial: str, *, qemu: bool = False, usb: bool = False) -> None:
        self.serial = serial
        self.qemu = qemu
        self.usb = usb

    def run(self, args, timeout=10):
        call = tuple(args)
        if tuple(args[1:]) == ("devices", "-l"):
            usb = " usb:1-2.3" if self.usb else ""
            return CommandResult(
                call,
                0,
                "List of devices attached\n"
                f"{self.serial} device{usb} product:test model:Rad_Phone "
                "device:rad transport_id:1\n",
                "",
            )
        translated = list(args)
        if len(translated) >= 3 and translated[1:3] == ["-s", self.serial]:
            translated[2] = "SERIAL123"
        result = super().run(translated, timeout)
        stdout = result.stdout
        if tuple(args[1:]) == ("-s", self.serial, "shell", "getprop") and self.qemu:
            stdout += "\n[ro.kernel.qemu]: [1]\n"
        return CommandResult(call, result.returncode, stdout, result.stderr, result.timed_out)


def test_device_engine_builds_real_snapshot_and_preserves_unauthorized():
    gateway = ExecutionGateway(MilestoneOnePolicy(), FakeAdbRunner())
    devices = DeviceEngine(AdbClient(Path("adb"), gateway)).scan()
    assert len(devices) == 2
    phone = devices[0]
    assert phone.transport == "usb"
    assert phone.manufacturer == "RadForge"
    assert phone.brand == "ROMVERSE"
    assert phone.marketing_name == "ROMVERSE One"
    assert phone.display_name == "RadForge ROMVERSE One"
    assert phone.android_version == "15"
    assert phone.vendor_device == "rad_vendor"
    assert phone.hardware == "rad_board"
    assert phone.hardware_sku == "pro"
    assert phone.build_incremental == "123456"
    assert phone.build_timestamp_utc == 1788220800
    assert phone.system_build_fingerprint == "RadForge/rad/system:15/AP4A/789:user/release-keys"
    assert phone.system_build_incremental == "789"
    assert phone.system_build_timestamp_utc == 1788220700
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


def test_adb_connection_source_distinguishes_emulator_network_and_physical_usb():
    cases = (
        ("emulator-5554", False, False, "emulator"),
        ("LOCALQEMU", True, False, "emulator"),
        ("192.168.1.17:5555", False, False, "network"),
        ("SERIAL123", False, True, "usb"),
    )

    for serial, qemu, usb, expected in cases:
        runner = AdbTransportRunner(serial, qemu=qemu, usb=usb)
        gateway = ExecutionGateway(MilestoneOnePolicy(), runner)

        device = DeviceEngine(AdbClient(Path("adb"), gateway)).scan()[0]

        assert device.transport == expected
        if expected == "emulator":
            assert "emulator" in device.connection_note.lower()
        elif expected == "network":
            assert "network adb" in device.connection_note.lower()
        else:
            assert "physical usb" in device.connection_note.lower()


def test_reconnect_safe_scan_never_stabilizes_an_emulator_as_usb():
    runner = AdbTransportRunner("emulator-5554", qemu=True)
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner)
    engine = DeviceEngine(AdbClient(Path("adb"), gateway))

    device = engine.scan_reconnect_safe()[0]

    assert device.transport == "emulator"
    assert "stable transport cycle" not in device.connection_note


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


def test_device_engine_prefers_xiaomi_hyperos_incremental_over_android_build_label():
    class XiaomiRunner(FakeAdbRunner):
        def run(self, args, timeout=10):
            result = super().run(args, timeout)
            if tuple(args[1:]) == ("-s", "SERIAL123", "shell", "getprop"):
                return CommandResult(
                    result.args,
                    result.returncode,
                    result.stdout
                    + "\n[ro.mi.os.version.incremental]: [OS4.0.0.23.XPBCNXM]"
                    + "\n[ro.build.version.incremental]: [OS4.0.0.23.XPBCNXM]"
                    + "\n[ro.build.display.id]: [CP2A.260605.016]",
                    result.stderr,
                )
            return result

    gateway = ExecutionGateway(MilestoneOnePolicy(), XiaomiRunner())

    phone = DeviceEngine(AdbClient(Path("adb"), gateway)).scan()[0]

    assert phone.rom_display == "OS4.0.0.23.XPBCNXM"
    assert phone.build_id == "AP4A"


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


class FastbootRunner(FakeAdbRunner):
    def run(self, args, timeout=10):
        call = tuple(args)
        if Path(args[0]).name == "fastboot":
            key = tuple(args[1:])
            outputs = {
                ("devices", "-l"): ("BOOT123\tfastboot usb:3-2\n", ""),
                ("-s", "BOOT123", "getvar", "product"): (
                    "",
                    "(bootloader) product: popsicle\nFinished. Total time: 0.001s\n",
                ),
                ("-s", "BOOT123", "getvar", "current-slot"): (
                    "",
                    "current-slot: b\n",
                ),
                ("-s", "BOOT123", "getvar", "unlocked"): ("", "unlocked: yes\n"),
                ("-s", "BOOT123", "getvar", "secure"): ("", "secure: yes\n"),
                ("-s", "BOOT123", "getvar", "is-userspace"): (
                    "",
                    "is-userspace: no\n",
                ),
            }
            output = outputs.get(key)
            return CommandResult(
                call,
                0 if output is not None else 1,
                output[0] if output else "",
                output[1] if output else "unknown fake fastboot command",
            )
        return super().run(args, timeout)


def test_device_engine_combines_adb_and_guardian_read_only_fastboot_identity() -> None:
    runner = FastbootRunner()
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner)
    engine = DeviceEngine(
        AdbClient(Path("adb"), gateway),
        FastbootClient(Path("fastboot"), gateway),
    )

    devices = engine.scan()

    assert len(devices) == 3
    bootloader = devices[-1]
    assert bootloader.state is DeviceState.BOOTLOADER
    assert bootloader.transport == "usb-fastboot"
    assert bootloader.product == "popsicle"
    assert bootloader.codename == "popsicle"
    assert bootloader.slot_suffix == "_b"
    assert bootloader.bootloader_locked is False
    assert bootloader.is_fastboot
    assert "read-only identity probes" in bootloader.connection_note
    assert not bootloader.errors


def test_device_engine_can_identify_fastbootd_when_adb_is_unavailable() -> None:
    class FastbootdRunner(FastbootRunner):
        def run(self, args, timeout=10):
            if tuple(args[1:]) == ("-s", "BOOT123", "getvar", "is-userspace"):
                return CommandResult(tuple(args), 0, "", "is-userspace: yes\n")
            return super().run(args, timeout)

    runner = FastbootdRunner()
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner)
    engine = DeviceEngine(None, FastbootClient(Path("fastboot"), gateway))

    device = engine.scan_reconnect_safe()[0]

    assert device.state is DeviceState.FASTBOOTD
    assert device.is_fastboot
    assert "userspace fastbootd" in device.fastboot_capability


def test_device_engine_stops_fastboot_probe_chain_after_transport_timeout() -> None:
    class TimedOutFastbootRunner:
        def __init__(self) -> None:
            self.calls: list[tuple[str, ...]] = []

        def run(self, args, timeout=10):
            call = tuple(args)
            self.calls.append(call)
            if tuple(args[1:]) == ("devices", "-l"):
                return CommandResult(call, 0, "BOOT123 fastboot usb:3-2\n", "")
            return CommandResult(
                call,
                124,
                "",
                "USB read error: device disconnected",
                timed_out=True,
            )

    runner = TimedOutFastbootRunner()
    gateway = ExecutionGateway(MilestoneOnePolicy(), runner)
    engine = DeviceEngine(None, FastbootClient(Path("fastboot"), gateway))

    device = engine.scan()[0]

    assert len(runner.calls) == 2
    assert device.state is DeviceState.FASTBOOT
    assert "stopped the probe chain" in device.connection_note
    assert device.errors == ("fastboot.getvar.product: USB read error: device disconnected",)
