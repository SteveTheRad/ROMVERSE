from __future__ import annotations

from time import monotonic

from romverse.device.adb import AdbClient
from romverse.device.fastboot import FastbootClient
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device.parsers import (
    coerce_device_state,
    parse_adb_devices,
    parse_battery,
    parse_fastboot_devices,
    parse_fastboot_getvar,
    parse_getprop,
    parse_memory,
    parse_storage,
    parse_uptime,
)
from romverse.guardian.models import GuardianDeniedError


class DeviceEngine:
    COMPANION_PACKAGE = "com.radforge.romverse.companion"
    MAGISK_PACKAGE = "com.topjohnwu.magisk"
    KERNELSU_PACKAGE = "me.weishu.kernelsu"
    DETAIL_CACHE_SECONDS = 30.0

    FASTBOOT_IDENTITY_VARIABLES = (
        "product",
        "current-slot",
        "unlocked",
        "secure",
        "is-userspace",
    )

    def __init__(
        self,
        adb: AdbClient | None,
        fastboot: FastbootClient | None = None,
    ) -> None:
        if adb is None and fastboot is None:
            raise ValueError("Device Engine requires a verified ADB or Fastboot client")
        self.adb = adb
        self.fastboot = fastboot
        self._transport_tokens: dict[str, str] = {}
        self._stable_sightings: dict[str, int] = {}
        self._detail_cache: dict[str, tuple[float, AndroidDevice]] = {}

    def scan(self) -> list[AndroidDevice]:
        errors: list[str] = []
        snapshots: list[AndroidDevice] = []
        if self.adb is not None:
            discovery = self.adb.devices()
            if discovery.ok:
                snapshots.extend(
                    self._inspect(item) for item in parse_adb_devices(discovery.stdout)
                )
            else:
                errors.append(f"ADB: {discovery.stderr.strip() or 'discovery failed'}")
        snapshots.extend(self._scan_fastboot({item.serial for item in snapshots}, errors))
        if not snapshots and errors:
            raise RuntimeError(" • ".join(errors))
        return snapshots

    def scan_reconnect_safe(self) -> list[AndroidDevice]:
        """Debounce a new USB transport before issuing the detailed probe sequence.

        A flaky cable or controller can repeatedly create a new ADB transport while xHCI is
        still enumerating it. One cheap ``adb devices`` result is therefore not enough to
        trigger eight follow-up commands. A transport must appear twice unchanged; healthy
        detail is then cached briefly so the periodic UI scan remains lightweight.
        """

        errors: list[str] = []
        snapshots: list[AndroidDevice] = []
        discovered: list[dict[str, str]] = []
        if self.adb is not None:
            discovery = self.adb.devices()
            if discovery.ok:
                discovered = parse_adb_devices(discovery.stdout)
            else:
                errors.append(f"ADB: {discovery.stderr.strip() or 'discovery failed'}")
        present = {item["serial"] for item in discovered}
        for serial in tuple(self._transport_tokens):
            if serial not in present:
                self._transport_tokens.pop(serial, None)
                self._stable_sightings.pop(serial, None)
                self._detail_cache.pop(serial, None)

        now = monotonic()
        for item in discovered:
            serial = item["serial"]
            state = coerce_device_state(item["state"])
            transport = "network" if ":" in serial else "usb"
            token = f"{state.value}:{item.get('transport_id', '')}:{item.get('usb', '')}"
            if state is not DeviceState.DEVICE or transport != "usb":
                snapshots.append(self._inspect(item))
                continue
            if self._transport_tokens.get(serial) != token:
                self._transport_tokens[serial] = token
                self._stable_sightings[serial] = 1
                self._detail_cache.pop(serial, None)
                snapshots.append(self._stabilizing_snapshot(item))
                continue
            self._stable_sightings[serial] = self._stable_sightings.get(serial, 1) + 1
            if self._stable_sightings[serial] < 2:
                snapshots.append(self._stabilizing_snapshot(item))
                continue
            cached = self._detail_cache.get(serial)
            if cached is not None and now - cached[0] < self.DETAIL_CACHE_SECONDS:
                snapshots.append(cached[1])
                continue
            snapshot = self._inspect(item)
            snapshots.append(snapshot)
            if not snapshot.errors:
                self._detail_cache[serial] = (now, snapshot)
        snapshots.extend(self._scan_fastboot({item.serial for item in snapshots}, errors))
        if not snapshots and errors:
            raise RuntimeError(" • ".join(errors))
        return snapshots

    def _scan_fastboot(
        self,
        observed_serials: set[str],
        errors: list[str],
    ) -> list[AndroidDevice]:
        if self.fastboot is None:
            return []
        discovery = self.fastboot.devices()
        if not discovery.ok:
            errors.append(f"Fastboot: {discovery.stderr.strip() or 'discovery failed'}")
            return []
        return [
            self._inspect_fastboot(item)
            for item in parse_fastboot_devices(discovery.stdout + "\n" + discovery.stderr)
            if item["serial"] not in observed_serials
        ]

    def _inspect_fastboot(self, discovered: dict[str, str]) -> AndroidDevice:
        if self.fastboot is None:  # defensive; discovery cannot reach this state
            raise RuntimeError("Verified Fastboot runtime is unavailable")
        serial = discovered["serial"]
        values: dict[str, str] = {}
        errors: list[str] = []
        transport_lost = False
        for variable in self.FASTBOOT_IDENTITY_VARIABLES:
            result = self.fastboot.getvar(serial, variable)
            value = parse_fastboot_getvar(
                result.stdout + "\n" + result.stderr,
                variable,
            )
            if value:
                values[variable] = value
            elif not result.ok:
                detail = " ".join(result.stderr.replace("\x00", " ").split())[:180]
                detail = detail.replace(serial, _masked_serial(serial))
                errors.append(f"fastboot.getvar.{variable}: {detail or 'not reported'}")
                normalized = detail.casefold()
                if result.timed_out or any(
                    phrase in normalized
                    for phrase in (
                        "device disconnected",
                        "device not found",
                        "no devices",
                        "transport error",
                        "usb read error",
                        "waiting for device",
                    )
                ):
                    transport_lost = True
                    break

        userspace = values.get("is-userspace", "").casefold()
        state = (
            DeviceState.FASTBOOTD
            if userspace in {"yes", "1", "true"}
            else DeviceState.BOOTLOADER
            if userspace in {"no", "0", "false"}
            else DeviceState.FASTBOOT
        )
        unlocked = _property_bool(values.get("unlocked", ""))
        product = values.get("product", "")
        slot = values.get("current-slot", "").casefold().removeprefix("_")
        mode = {
            DeviceState.FASTBOOTD: "userspace fastbootd",
            DeviceState.BOOTLOADER: "bootloader fastboot",
            DeviceState.FASTBOOT: "fastboot",
        }[state]
        return AndroidDevice(
            serial=serial,
            state=state,
            transport="usb-fastboot",
            model=product,
            product=product,
            codename=product,
            bootloader_locked=None if unlocked is None else not unlocked,
            slot_suffix=f"_{slot}" if slot in {"a", "b"} else "",
            fastboot_capability=f"Observed {mode} transport",
            connection_note=(
                "Fastboot transport became unstable during a bounded identity probe. ROMVERSE "
                "stopped the probe chain and will retry without changing the phone."
                if transport_lost
                else f"Connected in {mode} mode. ROMVERSE used only Guardian-approved read-only "
                "identity probes; Android health telemetry is unavailable until Android boots."
            ),
            errors=tuple(errors),
        )

    def _inspect(self, discovered: dict[str, str]) -> AndroidDevice:
        serial = discovered["serial"]
        state = coerce_device_state(discovered["state"])
        base = {
            "serial": serial,
            "state": state,
            "transport": "network" if ":" in serial else "usb",
        }
        if state is not DeviceState.DEVICE:
            note = {
                DeviceState.UNAUTHORIZED: "Unlock the phone and accept the USB debugging prompt.",
                DeviceState.OFFLINE: "Reconnect USB or restart the ADB server.",
            }.get(state, f"Device is in {state.value} state; detailed inspection is unavailable.")
            return AndroidDevice(
                **base,
                model=discovered.get("model", "").replace("_", " "),
                product=discovered.get("product", ""),
                codename=discovered.get("device", ""),
                connection_note=note,
            )

        errors: list[str] = []
        try:
            properties = self._probe(serial, "adb.getprop", ("shell", "getprop"), errors)
            props = parse_getprop(properties)
            battery_raw = self._probe(
                serial, "adb.battery", ("shell", "dumpsys", "battery"), errors
            )
            battery, battery_status, temperature = parse_battery(battery_raw)
            storage_raw = self._probe(serial, "adb.storage", ("shell", "df", "-k", "/data"), errors)
            memory_raw = self._probe(
                serial, "adb.memory", ("shell", "cat", "/proc/meminfo"), errors
            )
            uptime_raw = self._probe(serial, "adb.uptime", ("shell", "cat", "/proc/uptime"), errors)
            identity = self._probe(serial, "adb.identity", ("shell", "id"), errors)
            kernel_version = self._probe(
                serial, "adb.kernel", ("shell", "uname", "-r"), errors
            ).strip()
            companion_raw = self._probe_optional(
                serial,
                "adb.companion",
                ("shell", "pm", "path", self.COMPANION_PACKAGE),
            )
            magisk_raw = self._probe_optional(
                serial,
                "adb.root_manager.magisk",
                ("shell", "pm", "path", self.MAGISK_PACKAGE),
            )
            kernelsu_raw = self._probe_optional(
                serial,
                "adb.root_manager.kernelsu",
                ("shell", "pm", "path", self.KERNELSU_PACKAGE),
            )
        except _DeviceTransportLost as exc:
            return AndroidDevice(
                **base,
                model=discovered.get("model", "").replace("_", " "),
                product=discovered.get("product", ""),
                codename=discovered.get("device", ""),
                connection_note=(
                    "USB reconnect is unstable; ROMVERSE stopped detailed probes and will retry "
                    "with backoff. Check the cable or move the phone to a different USB controller."
                ),
                errors=(str(exc),),
            )

        locked_prop = props.get("ro.boot.flash.locked", "")
        bootloader_locked = True if locked_prop == "1" else False if locked_prop == "0" else None
        manufacturer = props.get("ro.product.manufacturer", "")
        model = props.get("ro.product.model", "") or discovered.get("model", "").replace("_", " ")
        marketing_name = next(
            (
                props.get(key, "").strip()
                for key in (
                    "ro.product.marketname",
                    "ro.vendor.product.marketname",
                    "ro.product.vendor.marketname",
                    "ro.config.marketing_name",
                )
                if props.get(key, "").strip()
            ),
            "",
        )
        boot_completed_value = props.get("sys.boot_completed", "")
        slot_suffix = props.get("ro.boot.slot_suffix", "")
        ab_update = _property_bool(props.get("ro.build.ab_update", ""))
        virtual_ab = _property_bool(props.get("ro.virtual_ab.enabled", ""))
        dynamic_partitions = _property_bool(
            props.get("ro.boot.dynamic_partitions", "")
            or props.get("ro.boot.dynamic_partitions_retrofit", "")
        )
        fastbootd = _property_bool(props.get("ro.fastbootd.available", ""))
        root_manager_candidate = (
            "conflict"
            if magisk_raw.strip() and kernelsu_raw.strip()
            else "magisk"
            if magisk_raw.strip()
            else "kernelsu_lkm"
            if kernelsu_raw.strip()
            else "none"
        )
        rom_display = next(
            (
                props.get(key, "").strip()
                for key in (
                    "ro.mi.os.version.incremental",
                    "ro.build.version.incremental",
                    "ro.build.display.id",
                )
                if props.get(key, "").strip()
            ),
            "",
        )
        return AndroidDevice(
            **base,
            manufacturer=manufacturer,
            brand=props.get("ro.product.brand", ""),
            model=model,
            marketing_name=marketing_name,
            product=props.get("ro.product.name", "") or discovered.get("product", ""),
            codename=props.get("ro.product.device", "") or discovered.get("device", ""),
            android_version=props.get("ro.build.version.release", ""),
            api_level=props.get("ro.build.version.sdk", ""),
            build_id=props.get("ro.build.id", ""),
            build_fingerprint=props.get("ro.build.fingerprint", ""),
            rom_display=rom_display,
            security_patch=props.get("ro.build.version.security_patch", ""),
            abi=props.get("ro.product.cpu.abi", ""),
            battery_percent=battery,
            battery_status=battery_status,
            battery_temperature_c=temperature,
            storage=parse_storage(storage_raw),
            memory=parse_memory(memory_raw),
            bootloader_locked=bootloader_locked,
            verified_boot=props.get("ro.boot.verifiedbootstate", ""),
            root_detected=("uid=0(" in identity) if identity else None,
            root_signal_source=(
                "adb-shell-uid-0" if "uid=0(" in identity else "adb-shell-id" if identity else ""
            ),
            root_manager_candidate=root_manager_candidate,
            root_manager_evidence="allowlisted-package-presence",
            companion_installed=bool(companion_raw.strip()) if companion_raw else False,
            companion_version="Detected" if companion_raw.strip() else "Not installed",
            connection_note="Connected over ADB (read-only inspection)",
            errors=tuple(errors),
            boot_completed=(boot_completed_value == "1") if boot_completed_value else None,
            uptime_seconds=parse_uptime(uptime_raw),
            slot_suffix=slot_suffix if slot_suffix in {"_a", "_b"} else "",
            kernel_version=kernel_version,
            soc_platform=(
                props.get("ro.soc.model", "")
                or props.get("ro.board.platform", "")
                or props.get("ro.hardware", "")
            ),
            encryption_state=props.get("ro.crypto.state", ""),
            encryption_type=props.get("ro.crypto.type", ""),
            ab_update=ab_update,
            virtual_ab=virtual_ab,
            dynamic_partitions=dynamic_partitions,
            fastboot_capability="fastbootd reported by Android" if fastbootd is True else "",
            recovery_capability=(
                f"Current transport: {state.value}"
                if state in {DeviceState.RECOVERY, DeviceState.SIDELOAD}
                else ""
            ),
        )

    def _probe(self, serial: str, probe_id: str, args: tuple[str, ...], errors: list[str]) -> str:
        result = self.adb.probe(serial, probe_id, args)
        if result.ok:
            return result.stdout
        detail = result.stderr.strip() or "probe failed"
        errors.append(f"{probe_id}: {detail}")
        normalized = detail.casefold()
        if result.timed_out or any(
            phrase in normalized
            for phrase in (
                "device offline",
                "device not found",
                "no devices/emulators found",
                "transport error",
                "connection reset",
                "closed",
            )
        ):
            raise _DeviceTransportLost(f"{probe_id}: {detail}")
        return ""

    def _probe_optional(self, serial: str, probe_id: str, args: tuple[str, ...]) -> str:
        """Run an informational probe where an empty result is an expected state."""
        try:
            result = self.adb.probe(serial, probe_id, args)
        except GuardianDeniedError:
            return ""
        return result.stdout if result.ok else ""

    @staticmethod
    def _stabilizing_snapshot(discovered: dict[str, str]) -> AndroidDevice:
        return AndroidDevice(
            discovered["serial"],
            coerce_device_state(discovered["state"]),
            transport="usb",
            model=discovered.get("model", "").replace("_", " "),
            product=discovered.get("product", ""),
            codename=discovered.get("device", ""),
            connection_note=(
                "USB link detected; ROMVERSE is waiting for one stable transport cycle before "
                "running detailed probes."
            ),
        )


class _DeviceTransportLost(RuntimeError):
    pass


def _property_bool(value: str) -> bool | None:
    normalized = value.casefold().strip()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    return None


def _masked_serial(serial: str) -> str:
    return "••••" if len(serial) <= 4 else f"••••{serial[-4:]}"
