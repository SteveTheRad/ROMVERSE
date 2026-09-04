from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from romverse.infrastructure.tools import ToolStatus
from romverse.platform.host import HostPlatform


class ToolHealthState(StrEnum):
    VERIFIED = "verified"
    ATTENTION = "attention"
    MISSING = "missing"
    OUTDATED = "outdated"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class ToolVersionHealth:
    name: str
    state: ToolHealthState
    detected: str
    minimum: str
    detail: str


@dataclass(frozen=True, slots=True)
class HostUsbHealth:
    state: ToolHealthState
    title: str
    detail: str
    guide_article_id: str


@dataclass(frozen=True, slots=True)
class HostToolchainHealth:
    platform_tools_state: ToolHealthState
    platform_tools_title: str
    platform_tools_detail: str
    version_checks: tuple[ToolVersionHealth, ...]
    usb: HostUsbHealth

    @property
    def overall_state(self) -> ToolHealthState:
        states = (
            self.platform_tools_state,
            *(check.state for check in self.version_checks),
            self.usb.state,
        )
        for state in (
            ToolHealthState.CONFLICT,
            ToolHealthState.MISSING,
            ToolHealthState.OUTDATED,
            ToolHealthState.ATTENTION,
        ):
            if state in states:
                return state
        return ToolHealthState.VERIFIED

    @property
    def needs_platform_tools_repair(self) -> bool:
        return self.platform_tools_state in {
            ToolHealthState.ATTENTION,
            ToolHealthState.MISSING,
            ToolHealthState.OUTDATED,
            ToolHealthState.CONFLICT,
        }


# This is a deliberately stable ROMVERSE compatibility floor, not a claim that
# it is the newest release. Android's 36.0.2 notes document fixes for Linux USB
# instability, Samsung discovery, and older Miscellaneous-class devices.
PLATFORM_TOOLS_MINIMUM = (36, 0, 2)
PLATFORM_TOOLS_MINIMUM_TEXT = ".".join(str(value) for value in PLATFORM_TOOLS_MINIMUM)
PLATFORM_TOOLS_SOURCE = "https://developer.android.com/tools/releases/platform-tools"
ANDROID_DEVICE_SOURCE = "https://developer.android.com/studio/run/device"
ANDROID_OEM_DRIVER_SOURCE = "https://developer.android.com/studio/run/oem-usb"

_VERSION_POLICIES = {
    "Python": ((3, 12, 0), "3.12"),
    "Java": ((17, 0, 0), "17"),
}
_RULE_ROOTS = (
    Path("/etc/udev/rules.d"),
    Path("/usr/lib/udev/rules.d"),
    Path("/lib/udev/rules.d"),
)
_MAX_RULE_FILES = 256
_MAX_RULE_BYTES = 512 * 1024


def assess_host_toolchain(
    host: HostPlatform,
    statuses: tuple[ToolStatus, ...],
    *,
    communication_verified: bool = False,
    transport_visible: bool = False,
    scan_failed: bool = False,
    group_names: frozenset[str] | None = None,
    rule_roots: tuple[Path, ...] | None = None,
) -> HostToolchainHealth:
    """Assess host readiness without running a phone command or changing the host."""

    status_by_name = {status.name: status for status in statuses}
    adb = status_by_name.get("ADB", ToolStatus("ADB", False, detail="Not installed"))
    fastboot = status_by_name.get("Fastboot", ToolStatus("Fastboot", False, detail="Not installed"))
    adb_check = _platform_tool_check(adb)
    fastboot_check = _platform_tool_check(fastboot)
    platform_state, platform_title, platform_detail = _platform_tools_pair(
        adb, fastboot, adb_check, fastboot_check
    )
    version_checks = [adb_check, fastboot_check]
    for name, (minimum, minimum_text) in _VERSION_POLICIES.items():
        status = status_by_name.get(name)
        if status is not None:
            version_checks.append(_generic_version_check(status, minimum, minimum_text))
    usb = _host_usb_health(
        host,
        communication_verified=communication_verified,
        transport_visible=transport_visible,
        scan_failed=scan_failed,
        group_names=group_names,
        rule_roots=rule_roots,
    )
    return HostToolchainHealth(
        platform_state,
        platform_title,
        platform_detail,
        tuple(version_checks),
        usb,
    )


def extract_platform_tools_version(name: str, value: str) -> tuple[int, int, int] | None:
    """Extract a Platform Tools release while rejecting ADB's 1.0.41 protocol version."""

    text = " ".join(str(value).split())[:240]
    if not text:
        return None
    if name == "ADB":
        release = re.search(
            r"(?:platform[ -]?tools(?:\s+release)?|release|version)\s+"
            r"(\d{2,4}\.\d+\.\d+)",
            text,
            re.IGNORECASE,
        )
        if release is None:
            bare = re.match(r"(\d{2,4})\.(\d+)\.(\d+)(?:\b|-)", text)
            return tuple(int(value) for value in bare.groups()) if bare else None
        return _version_tuple(release.group(1))
    match = re.search(r"(?<!\d)(\d{2,4}\.\d+\.\d+)(?!\d)", text)
    return _version_tuple(match.group(1)) if match else None


def _platform_tool_check(status: ToolStatus) -> ToolVersionHealth:
    if not status.available:
        return ToolVersionHealth(
            status.name,
            ToolHealthState.MISSING,
            "not available",
            PLATFORM_TOOLS_MINIMUM_TEXT,
            status.detail or "Install the official Android SDK Platform Tools package.",
        )
    version = extract_platform_tools_version(status.name, status.version)
    if version is None:
        return ToolVersionHealth(
            status.name,
            ToolHealthState.ATTENTION,
            status.version or "not reported",
            PLATFORM_TOOLS_MINIMUM_TEXT,
            "The executable starts, but its Platform Tools release could not be proven.",
        )
    detected = ".".join(str(value) for value in version)
    if version < PLATFORM_TOOLS_MINIMUM:
        return ToolVersionHealth(
            status.name,
            ToolHealthState.OUTDATED,
            detected,
            PLATFORM_TOOLS_MINIMUM_TEXT,
            "Below ROMVERSE's compatibility floor for reliable Android USB discovery.",
        )
    return ToolVersionHealth(
        status.name,
        ToolHealthState.VERIFIED,
        detected,
        PLATFORM_TOOLS_MINIMUM_TEXT,
        "Meets the ROMVERSE Platform Tools compatibility floor.",
    )


def _generic_version_check(
    status: ToolStatus,
    minimum: tuple[int, int, int],
    minimum_text: str,
) -> ToolVersionHealth:
    if not status.available:
        return ToolVersionHealth(
            status.name,
            ToolHealthState.MISSING,
            "not available",
            minimum_text,
            status.detail or "Required build runtime is not available.",
        )
    match = re.search(r"(?<!\d)(\d+)(?:\.(\d+))?(?:\.(\d+))?", status.version)
    if match is None:
        return ToolVersionHealth(
            status.name,
            ToolHealthState.ATTENTION,
            status.version or "not reported",
            minimum_text,
            "The executable starts, but its release could not be compared with the project floor.",
        )
    version = tuple(int(value or 0) for value in match.groups())
    detected = ".".join(str(value) for value in version)
    return ToolVersionHealth(
        status.name,
        ToolHealthState.VERIFIED if version >= minimum else ToolHealthState.OUTDATED,
        detected,
        minimum_text,
        (
            "Meets the ROMVERSE project runtime floor."
            if version >= minimum
            else "Below the ROMVERSE project runtime floor."
        ),
    )


def _platform_tools_pair(
    adb: ToolStatus,
    fastboot: ToolStatus,
    adb_check: ToolVersionHealth,
    fastboot_check: ToolVersionHealth,
) -> tuple[ToolHealthState, str, str]:
    checks = (adb_check, fastboot_check)
    if any(check.state is ToolHealthState.MISSING for check in checks):
        missing = ", ".join(
            check.name for check in checks if check.state is ToolHealthState.MISSING
        )
        return (
            ToolHealthState.MISSING,
            "Android Platform Tools are incomplete",
            f"Missing: {missing}. Install ADB and Fastboot together from one official package.",
        )
    origins_match = _same_parent(adb.path, fastboot.path)
    releases = (
        extract_platform_tools_version("ADB", adb.version),
        extract_platform_tools_version("Fastboot", fastboot.version),
    )
    releases_match = None not in releases and releases[0] == releases[1]
    if not origins_match or (None not in releases and not releases_match):
        return (
            ToolHealthState.CONFLICT,
            "Conflicting Platform Tools installations found",
            "ADB and Fastboot do not resolve to one matching installation. Replace the pair "
            "together so ROMVERSE cannot mix host-tool releases.",
        )
    if any(check.state is ToolHealthState.OUTDATED for check in checks):
        detected = ", ".join(f"{check.name} {check.detected}" for check in checks)
        return (
            ToolHealthState.OUTDATED,
            "Platform Tools update required",
            f"{detected}. ROMVERSE requires {PLATFORM_TOOLS_MINIMUM_TEXT} or newer.",
        )
    if any(check.state is ToolHealthState.ATTENTION for check in checks):
        return (
            ToolHealthState.ATTENTION,
            "Platform Tools release is not fully proven",
            "ADB and Fastboot start from one location, but one release string is incomplete. "
            "Installing the current official package will produce a comparable pair.",
        )
    return (
        ToolHealthState.VERIFIED,
        "Platform Tools pair verified",
        f"ADB and Fastboot resolve together and meet the {PLATFORM_TOOLS_MINIMUM_TEXT} "
        "compatibility floor.",
    )


def _same_parent(first: str, second: str) -> bool:
    try:
        return Path(first).resolve(strict=True).parent == Path(second).resolve(strict=True).parent
    except (OSError, RuntimeError, ValueError):
        return False


def _host_usb_health(
    host: HostPlatform,
    *,
    communication_verified: bool,
    transport_visible: bool,
    scan_failed: bool,
    group_names: frozenset[str] | None,
    rule_roots: tuple[Path, ...] | None,
) -> HostUsbHealth:
    name = host.name.casefold()
    if communication_verified:
        return HostUsbHealth(
            ToolHealthState.VERIFIED,
            "Genuine Android communication verified",
            "The latest bounded Device Engine evidence proves this host can reach the phone. "
            "No driver or permission change is recommended.",
            "android-usb-host-checklist",
        )
    if name == "windows":
        if transport_visible:
            detail = (
                "Windows reached an Android transport. Complete the phone's RSA confirmation "
                "before changing a working driver."
            )
        else:
            detail = (
                "Windows must use the signed driver for the exact phone maker. Google's USB "
                "driver is for Google devices; ROMVERSE will not substitute a generic bundle."
            )
        return HostUsbHealth(
            ToolHealthState.ATTENTION,
            "Exact OEM driver route",
            detail,
            "android-oem-usb-driver-source",
        )
    if name != "linux":
        return HostUsbHealth(
            ToolHealthState.ATTENTION,
            "USB host setup not yet proven",
            "Use the official Android hardware-device checklist, then verify a real connection.",
            "android-usb-host-checklist",
        )
    groups = _current_group_names() if group_names is None else group_names
    roots = _RULE_ROOTS if rule_roots is None else rule_roots
    rules_found = _android_udev_rules_found(roots)
    distribution = str(getattr(host, "distribution_id", "")).casefold()
    plugdev_required = distribution in {"ubuntu", "debian"}
    plugdev_ready = not plugdev_required or "plugdev" in groups
    if rules_found and plugdev_ready:
        detail = (
            "Android-capable udev access rules are present"
            + (" and plugdev membership is active" if plugdev_required else "")
            + ". Connect a phone to prove the complete cable, port and authorization path."
        )
        return HostUsbHealth(
            ToolHealthState.VERIFIED,
            "Linux Android USB access prepared",
            detail,
            "linux-udev-permission",
        )
    gaps: list[str] = []
    if not rules_found:
        gaps.append("Android-capable udev access rules were not found")
    if not plugdev_ready:
        gaps.append("the current login is not in plugdev")
    suffix = (
        " The last Device Engine scan also failed, so correct the evidenced host gap before "
        "reconnecting."
        if scan_failed
        else " This is a host-readiness warning, not proof that a disconnected phone is faulty."
    )
    return HostUsbHealth(
        ToolHealthState.ATTENTION,
        "Linux USB permission needs attention",
        "; ".join(gaps) + "." + suffix,
        "linux-udev-permission",
    )


def _current_group_names() -> frozenset[str]:
    try:
        import grp

        identifiers = set(os.getgroups())
        identifiers.add(os.getgid())
        return frozenset(grp.getgrgid(identifier).gr_name for identifier in identifiers)
    except (AttributeError, ImportError, KeyError, OSError):
        return frozenset()


def _android_udev_rules_found(roots: tuple[Path, ...]) -> bool:
    inspected: set[Path] = set()
    remaining = _MAX_RULE_FILES
    markers = (
        "id_debug_appliance",
        "ff4201",
        "ff4203",
        "android debug bridge",
        "android devices",
    )
    for root in roots[:8]:
        try:
            root_path = Path(root)
            details = root_path.lstat()
            if root_path.is_symlink() or not stat.S_ISDIR(details.st_mode):
                continue
            entries = sorted(root_path.iterdir(), key=lambda path: path.name)[:remaining]
        except (OSError, RuntimeError):
            continue
        for path in entries:
            if remaining <= 0:
                return False
            remaining -= 1
            try:
                resolved = path.resolve(strict=True)
                if resolved in inspected or path.is_symlink():
                    continue
                inspected.add(resolved)
                details = resolved.stat()
                if (
                    not stat.S_ISREG(details.st_mode)
                    or details.st_size > _MAX_RULE_BYTES
                    or resolved.suffix.casefold() != ".rules"
                ):
                    continue
                text = resolved.read_text(encoding="utf-8", errors="replace").casefold()
            except (OSError, RuntimeError):
                continue
            if any(marker in text for marker in markers):
                return True
    return False


def _version_tuple(value: str) -> tuple[int, int, int]:
    values = tuple(int(part) for part in value.split(".")[:3])
    return (values + (0, 0, 0))[:3]
