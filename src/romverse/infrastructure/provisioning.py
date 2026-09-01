from __future__ import annotations

import platform
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from romverse.infrastructure.process import CommandRunner
from romverse.infrastructure.tools import ToolStatus
from romverse.platform.host import HostPlatform


class ProvisionStrategy(StrEnum):
    MANAGED = "romverse-managed"
    SYSTEM = "system-authorized"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class ToolProvisionItem:
    name: str
    strategy: ProvisionStrategy
    source: str
    packages: tuple[str, ...] = ()
    explanation: str = ""


@dataclass(frozen=True, slots=True)
class ToolProvisionPlan:
    host: str
    missing: tuple[ToolProvisionItem, ...]

    @property
    def managed(self) -> tuple[ToolProvisionItem, ...]:
        return tuple(item for item in self.missing if item.strategy is ProvisionStrategy.MANAGED)

    @property
    def system(self) -> tuple[ToolProvisionItem, ...]:
        return tuple(item for item in self.missing if item.strategy is ProvisionStrategy.SYSTEM)

    @property
    def manual(self) -> tuple[ToolProvisionItem, ...]:
        return tuple(item for item in self.missing if item.strategy is ProvisionStrategy.MANUAL)


GENESIS_REQUIRED_TOOLS = (
    "Python",
    "ADB",
    "Fastboot",
    "Git",
    "7-Zip",
    "Unzip",
    "LZ4",
    "simg2img",
    "EXT4 Browser",
    "Payload Dumper",
    "EROFS Builder",
    "EROFS Verifier",
    "LP Make",
    "LP Unpack",
    "LP Dump",
    "Fakeroot",
    "AAPT2",
    "APK Signer",
    "AVBTool",
    "Make",
    "Java",
)

# The complete catalog stays available in Forge Arsenal, but an active ROM Studio
# mission must install only the subset declared by its exact Device Pack contract.
ROM_STUDIO_CONTRACT_MINIMUM_TOOLS = (
    "Python",
    "simg2img",
    "Payload Dumper",
    "EROFS Builder",
    "EROFS Verifier",
    "LP Make",
    "LP Unpack",
    "LP Dump",
    "Fakeroot",
    "AVBTool",
)
ROM_STUDIO_DEFAULT_REQUIRED_TOOLS = (
    "Python",
    "ADB",
    "Fastboot",
    "7-Zip",
    "Unzip",
    "EXT4 Browser",
    *ROM_STUDIO_CONTRACT_MINIMUM_TOOLS[1:],
)
OTA_SOURCE_REQUIRED_TOOLS = (
    "Python",
    "Payload Dumper",
    "AVBTool",
)
FASTBOOT_SUPER_REQUIRED_TOOLS = (
    "Python",
    "simg2img",
    "LP Unpack",
    "LP Dump",
    "AVBTool",
)
PARTITION_BUNDLE_REQUIRED_TOOLS = (
    "Python",
    "simg2img",
    "AVBTool",
)
DEBLOAT_OTA_REQUIRED_TOOLS = (
    "Python",
    "Payload Dumper",
    "simg2img",
    "EXT4 Browser",
    "EROFS Verifier",
    "Fakeroot",
)
DEBLOAT_SUPER_REQUIRED_TOOLS = (
    "Python",
    "LP Unpack",
    "simg2img",
    "EXT4 Browser",
    "EROFS Verifier",
    "Fakeroot",
)
DEBLOAT_IMAGE_REQUIRED_TOOLS = (
    "Python",
    "simg2img",
    "EXT4 Browser",
    "EROFS Verifier",
    "Fakeroot",
)
ROM_STUDIO_TOOL_CATALOG = frozenset(GENESIS_REQUIRED_TOOLS)


_SOURCES = {
    "ADB": "https://developer.android.com/tools/releases/platform-tools",
    "Fastboot": "https://developer.android.com/tools/releases/platform-tools",
    "Google USB Driver": "https://developer.android.com/studio/run/win-usb",
    "Git": "https://git-scm.com/downloads",
    "7-Zip": "https://www.7-zip.org/download.html",
    "Unzip": "https://infozip.sourceforge.net/UnZip.html",
    "LZ4": "https://github.com/lz4/lz4/releases",
    "simg2img": "https://android.googlesource.com/platform/system/core/+/main/libsparse/",
    "EXT4 Browser": "https://e2fsprogs.sourceforge.net/",
    "AVBTool": "https://android.googlesource.com/platform/external/avb/",
    "Payload Dumper": "https://github.com/ssut/payload-dumper-go/releases",
    "Make": "https://www.gnu.org/software/make/",
    "Java": "https://adoptium.net/temurin/releases/",
    "EROFS Builder": "https://git.kernel.org/pub/scm/linux/kernel/git/xiang/erofs-utils.git/",
    "EROFS Verifier": "https://git.kernel.org/pub/scm/linux/kernel/git/xiang/erofs-utils.git/",
    "LP Make": "https://android.googlesource.com/platform/system/extras/+/main/partition_tools/",
    "LP Unpack": "https://android.googlesource.com/platform/system/extras/+/main/partition_tools/",
    "LP Dump": "https://android.googlesource.com/platform/system/extras/+/main/partition_tools/",
    "Fakeroot": "https://packages.ubuntu.com/search?keywords=fakeroot",
    "AAPT2": "https://developer.android.com/tools/aapt2",
    "APK Signer": "https://developer.android.com/tools/apksigner",
}

_MANAGED = frozenset(
    {
        "ADB",
        "Fastboot",
        "AVBTool",
        "Payload Dumper",
        "simg2img",
        "LP Make",
        "LP Unpack",
        "LP Dump",
        "AAPT2",
        "APK Signer",
    }
)
_UBUNTU_PACKAGES = {
    "Git": ("git",),
    "7-Zip": ("p7zip-full",),
    "Unzip": ("unzip",),
    "LZ4": ("lz4",),
    "simg2img": ("android-sdk-libsparse-utils",),
    "EXT4 Browser": ("e2fsprogs",),
    "Make": ("make",),
    "Java": ("default-jdk-headless",),
    "EROFS Builder": ("erofs-utils",),
    "EROFS Verifier": ("erofs-utils",),
    "Fakeroot": ("fakeroot",),
    "AAPT2": ("aapt",),
    "APK Signer": ("apksigner",),
}
_FEDORA_PACKAGES = {
    "Git": ("git",),
    "7-Zip": ("7zip",),
    "Unzip": ("unzip",),
    "LZ4": ("lz4",),
    "EXT4 Browser": ("e2fsprogs",),
    "Make": ("make",),
    "EROFS Builder": ("erofs-utils",),
    "EROFS Verifier": ("erofs-utils",),
    "Fakeroot": ("fakeroot",),
}


def _system_package_profile(
    host: HostPlatform,
) -> tuple[str, dict[str, tuple[str, ...]]]:
    if host.name.casefold() != "linux":
        return "", {}
    distribution_id = str(getattr(host, "distribution_id", "")).casefold().strip()
    if distribution_id == "ubuntu":
        return "Ubuntu", _UBUNTU_PACKAGES
    if distribution_id == "fedora":
        return "Fedora", _FEDORA_PACKAGES
    return "", {}


def create_provision_plan(
    host: HostPlatform,
    statuses: tuple[ToolStatus, ...],
    required_names: tuple[str, ...] | None = None,
) -> ToolProvisionPlan:
    items: list[ToolProvisionItem] = []
    system_name, system_packages = _system_package_profile(host)
    status_by_name = {status.name: status for status in statuses}
    selected_statuses = (
        tuple(
            status_by_name.get(
                name,
                ToolStatus(name, False, detail="Tool verification result is unavailable"),
            )
            for name in required_names
        )
        if required_names is not None
        else statuses
    )
    for status in selected_statuses:
        if status.available:
            continue
        managed_apk_tool = status.name in {"AAPT2", "APK Signer"}
        managed_supported = not managed_apk_tool or (
            host.name.casefold() == "linux" and platform.machine().casefold() in {"amd64", "x86_64"}
        )
        if status.name in _MANAGED and managed_supported:
            strategy = ProvisionStrategy.MANAGED
            packages: tuple[str, ...] = ()
            explanation = (
                "Downloaded from the pinned, hash-verified Android 15 reference toolchain used by the proven popsicle build."
                if status.name in {"simg2img", "LP Make", "LP Unpack", "LP Dump"}
                else "Downloaded as an exact SHA-256-pinned, Apache-licensed stable AAPT2 artifact from official Google Maven."
                if status.name == "AAPT2"
                else "Downloaded as the exact SHA-256-pinned, Apache-licensed official apksig library with a ROMVERSE verification-only launcher; full SDK Build Tools remain required for APK signing."
                if status.name == "APK Signer"
                else "Downloaded from the official upstream source into ROMVERSE's managed tool directory."
            )
        elif status.name in system_packages:
            strategy = ProvisionStrategy.SYSTEM
            packages = system_packages[status.name]
            explanation = (
                f"Installed by {system_name} after its normal administrator authorization prompt."
            )
        else:
            strategy = ProvisionStrategy.MANUAL
            packages = ()
            explanation = (
                "Install one stable Android SDK Build Tools revision with Android Studio or "
                "sdkmanager. ROMVERSE automatically checks ANDROID_SDK_ROOT, ANDROID_HOME, and "
                "the standard Android Studio SDK folder; package licenses remain user-controlled."
                if status.name in {"AAPT2", "APK Signer"}
                else "No bounded automatic installer is approved for this host yet."
            )
        items.append(
            ToolProvisionItem(
                status.name,
                strategy,
                _SOURCES.get(status.name, ""),
                packages,
                explanation,
            )
        )
    return ToolProvisionPlan(host.name, tuple(items))


def required_tools_for_contract(contract: object | None) -> tuple[str, ...]:
    """Return the exact ordered tool profile declared by a Device Pack contract."""

    declared = tuple(getattr(contract, "required_tools", ()) or ())
    return declared or GENESIS_REQUIRED_TOOLS


def required_tools_for_source(
    contract: object | None,
    partition_signals: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Resolve the narrowest truthful tool profile from exact or structural evidence.

    An exact Device Pack contract always wins. Structure-only profiles authorize tool
    preparation for inspection/extraction, never a build or flash operation.
    """

    declared = tuple(getattr(contract, "required_tools", ()) or ())
    if declared:
        return declared
    signals = {str(value).casefold().strip() for value in partition_signals}
    if "ota_payload" in signals:
        return OTA_SOURCE_REQUIRED_TOOLS
    if "super" in signals:
        return FASTBOOT_SUPER_REQUIRED_TOOLS
    if signals:
        return PARTITION_BUNDLE_REQUIRED_TOOLS
    return ROM_STUDIO_DEFAULT_REQUIRED_TOOLS


def required_tools_for_debloat(partition_signals: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Select the read-only tools needed to expose app files from this source shape."""

    signals = {str(value).casefold().strip() for value in partition_signals}
    if "ota_payload" in signals:
        return DEBLOAT_OTA_REQUIRED_TOOLS
    if "super" in signals:
        return DEBLOAT_SUPER_REQUIRED_TOOLS
    if signals:
        return DEBLOAT_IMAGE_REQUIRED_TOOLS
    return ()


def install_system_packages(
    items: tuple[ToolProvisionItem, ...],
    host: HostPlatform,
    runner: CommandRunner,
) -> tuple[bool, str]:
    """Install only distro-allowlisted packages through a visible authorization boundary."""

    if host.name.casefold() != "linux":
        return (
            False,
            "Automatic system package installation is currently supported only on Linux.",
        )
    system_name, package_profile = _system_package_profile(host)
    if not package_profile:
        return (
            False,
            "Automatic system package installation is approved only for Ubuntu and Fedora.",
        )
    packages = tuple(sorted({package for item in items for package in item.packages}))
    allowed = {package for values in package_profile.values() for package in values}
    if (
        not packages
        or any(item.strategy is not ProvisionStrategy.SYSTEM for item in items)
        or any(
            item.name not in package_profile or item.packages != package_profile[item.name]
            for item in items
        )
        or any(package not in allowed for package in packages)
    ):
        return (
            False,
            f"The package plan is empty or contains a package outside ROMVERSE's {system_name} allowlist.",
        )
    pkexec = host.find_tool("pkexec")
    trusted_pkexec = Path("/usr/bin/pkexec")
    if pkexec != trusted_pkexec or not trusted_pkexec.is_file():
        return (
            False,
            f"{system_name} authorization tools are unavailable; install the listed packages manually.",
        )
    if system_name == "Ubuntu":
        return _install_ubuntu_packages(packages, trusted_pkexec, runner)
    if system_name == "Fedora":
        return _install_fedora_packages(packages, trusted_pkexec, runner)
    return False, "The detected Linux package manager is not approved."


def _install_ubuntu_packages(
    packages: tuple[str, ...],
    pkexec: Path,
    runner: CommandRunner,
) -> tuple[bool, str]:
    apt_get = Path("/usr/bin/apt-get")
    if not apt_get.is_file():
        return (
            False,
            "Ubuntu authorization tools are unavailable; install the listed packages manually.",
        )
    update = runner.run((str(pkexec), str(apt_get), "update"), timeout=20 * 60)
    if not update.ok:
        detail = _bounded_detail(update.stderr or update.stdout)
        return False, f"Ubuntu package index refresh failed: {detail}"
    install = runner.run(
        (
            str(pkexec),
            str(apt_get),
            "install",
            "--yes",
            "--no-install-recommends",
            *packages,
        ),
        timeout=30 * 60,
    )
    if not install.ok:
        detail = _bounded_detail(install.stderr or install.stdout)
        return False, f"Ubuntu package installation failed: {detail}"
    return True, "Ubuntu installed: " + ", ".join(packages)


def _install_fedora_packages(
    packages: tuple[str, ...],
    pkexec: Path,
    runner: CommandRunner,
) -> tuple[bool, str]:
    dnf = Path("/usr/bin/dnf")
    if not dnf.is_file():
        return (
            False,
            "Fedora authorization tools are unavailable; install the listed packages manually.",
        )
    refresh = runner.run((str(pkexec), str(dnf), "--refresh", "makecache"), timeout=20 * 60)
    if not refresh.ok:
        detail = _bounded_detail(refresh.stderr or refresh.stdout)
        return False, f"Fedora package metadata refresh failed: {detail}"
    install = runner.run(
        (
            str(pkexec),
            str(dnf),
            "--assumeyes",
            "--setopt=install_weak_deps=False",
            "install",
            *packages,
        ),
        timeout=30 * 60,
    )
    if not install.ok:
        detail = _bounded_detail(install.stderr or install.stdout)
        return False, f"Fedora package installation failed: {detail}"
    return True, "Fedora installed: " + ", ".join(packages)


def source_for(name: str) -> str:
    return _SOURCES.get(name, "")


def _bounded_detail(value: str) -> str:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    return (lines[-1] if lines else "no diagnostic output")[:300]
