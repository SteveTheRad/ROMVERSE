from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class DeviceState(StrEnum):
    DEVICE = "device"
    UNAUTHORIZED = "unauthorized"
    OFFLINE = "offline"
    RECOVERY = "recovery"
    SIDELOAD = "sideload"
    FASTBOOT = "fastboot"
    BOOTLOADER = "bootloader"
    FASTBOOTD = "fastbootd"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class StorageInfo:
    total_bytes: int | None = None
    used_bytes: int | None = None
    available_bytes: int | None = None
    percent_used: int | None = None


@dataclass(frozen=True, slots=True)
class MemoryInfo:
    total_bytes: int | None = None
    available_bytes: int | None = None
    percent_used: int | None = None


@dataclass(frozen=True, slots=True)
class AndroidDevice:
    serial: str
    state: DeviceState
    transport: str = "usb"
    manufacturer: str = ""
    model: str = ""
    marketing_name: str = ""
    product: str = ""
    codename: str = ""
    android_version: str = ""
    api_level: str = ""
    build_id: str = ""
    build_fingerprint: str = ""
    rom_display: str = ""
    security_patch: str = ""
    abi: str = ""
    battery_percent: int | None = None
    battery_status: str = ""
    battery_temperature_c: float | None = None
    storage: StorageInfo = field(default_factory=StorageInfo)
    memory: MemoryInfo = field(default_factory=MemoryInfo)
    bootloader_locked: bool | None = None
    verified_boot: str = ""
    root_detected: bool | None = None
    root_signal_source: str = ""
    root_manager_candidate: str = "unknown"
    root_manager_evidence: str = ""
    companion_installed: bool | None = None
    companion_version: str = ""
    connection_note: str = ""
    errors: tuple[str, ...] = ()
    boot_completed: bool | None = None
    uptime_seconds: int | None = None
    slot_suffix: str = ""
    kernel_version: str = ""
    soc_platform: str = ""
    encryption_state: str = ""
    encryption_type: str = ""
    ab_update: bool | None = None
    virtual_ab: bool | None = None
    dynamic_partitions: bool | None = None
    fastboot_capability: str = ""
    recovery_capability: str = ""
    brand: str = ""
    vendor_device: str = ""
    hardware: str = ""
    hardware_sku: str = ""
    build_incremental: str = ""
    build_timestamp_utc: int | None = None
    system_build_fingerprint: str = ""
    system_build_incremental: str = ""
    system_build_timestamp_utc: int | None = None

    @property
    def display_name(self) -> str:
        if self.marketing_name:
            if self.manufacturer and not self.marketing_name.casefold().startswith(
                self.manufacturer.casefold()
            ):
                return f"{self.manufacturer} {self.marketing_name}".strip()
            return self.marketing_name
        return (
            " ".join(part for part in (self.manufacturer, self.model) if part).strip()
            or self.model
            or "Android device"
        )

    def masked_serial(self) -> str:
        if len(self.serial) <= 4:
            return "••••"
        return f"••••{self.serial[-4:]}"

    @property
    def is_fastboot(self) -> bool:
        return self.state in {
            DeviceState.FASTBOOT,
            DeviceState.BOOTLOADER,
            DeviceState.FASTBOOTD,
        }

    @property
    def is_simulated(self) -> bool:
        """Identify explicit inert test-device evidence without treating it as hardware."""

        return self.transport.casefold().strip() == "simulation"
