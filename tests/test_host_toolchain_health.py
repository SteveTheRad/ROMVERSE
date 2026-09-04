from __future__ import annotations

from pathlib import Path

from romverse.infrastructure.host_toolchain_health import (
    PLATFORM_TOOLS_MINIMUM_TEXT,
    ToolHealthState,
    assess_host_toolchain,
    extract_platform_tools_version,
)
from romverse.infrastructure.tools import ToolStatus
from romverse.platform.host import LinuxHost, WindowsHost


def _statuses(
    adb_version: str = "37.0.0 (ADB protocol 1.0.41)",
    fastboot_version: str = "fastboot version 37.0.0-android-tools",
    *,
    first_root: Path,
    second_root: Path | None = None,
) -> tuple[ToolStatus, ...]:
    second = first_root if second_root is None else second_root
    return (
        ToolStatus("ADB", True, str(first_root / "adb"), adb_version, "Ready"),
        ToolStatus("Fastboot", True, str(second / "fastboot"), fastboot_version, "Ready"),
        ToolStatus("Python", True, "/runtime/python", "3.14.7", "Ready"),
        ToolStatus("Java", True, "/runtime/java", "openjdk 21.0.8", "Ready"),
    )


def _executables(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "adb").write_bytes(b"adb")
    (root / "fastboot").write_bytes(b"fastboot")
    return root


def test_platform_version_parser_rejects_adb_protocol_and_reads_release() -> None:
    assert extract_platform_tools_version("ADB", "1.0.41") is None
    assert extract_platform_tools_version("ADB", "37.0.0 (ADB protocol 1.0.41)") == (37, 0, 0)
    assert extract_platform_tools_version("Fastboot", "fastboot version 36.0.2-123456") == (
        36,
        0,
        2,
    )


def test_verified_pair_and_fedora_uaccess_rule_are_reported_without_phone_claim(
    tmp_path: Path,
) -> None:
    tools = _executables(tmp_path / "platform-tools")
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "70-uaccess.rules").write_text(
        '# Android devices (ADB, Fastboot)\nENV{ID_DEBUG_APPLIANCE}="?*", TAG+="uaccess"\n',
        encoding="utf-8",
    )

    health = assess_host_toolchain(
        LinuxHost(distribution_id="fedora"),
        _statuses(first_root=tools),
        group_names=frozenset({"wheel"}),
        rule_roots=(rules,),
    )

    assert health.platform_tools_state is ToolHealthState.VERIFIED
    assert health.usb.state is ToolHealthState.VERIFIED
    assert "Connect a phone to prove" in health.usb.detail
    assert all(check.state is ToolHealthState.VERIFIED for check in health.version_checks)


def test_outdated_and_mixed_platform_tools_are_detected(tmp_path: Path) -> None:
    first = _executables(tmp_path / "first")
    second = _executables(tmp_path / "second")

    outdated = assess_host_toolchain(
        LinuxHost(distribution_id="fedora"),
        _statuses("35.0.2", "fastboot version 35.0.2", first_root=first),
        group_names=frozenset(),
        rule_roots=(),
    )
    assert outdated.platform_tools_state is ToolHealthState.OUTDATED
    assert PLATFORM_TOOLS_MINIMUM_TEXT in outdated.platform_tools_detail

    mixed = assess_host_toolchain(
        LinuxHost(distribution_id="fedora"),
        _statuses(first_root=first, second_root=second),
        group_names=frozenset(),
        rule_roots=(),
    )
    assert mixed.platform_tools_state is ToolHealthState.CONFLICT
    assert mixed.needs_platform_tools_repair


def test_ubuntu_requires_both_android_rules_and_plugdev(tmp_path: Path) -> None:
    tools = _executables(tmp_path / "platform-tools")
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "51-android.rules").write_text(
        'SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", MODE="0660", GROUP="plugdev"\n'
        "# Android Debug Bridge\n",
        encoding="utf-8",
    )

    missing_group = assess_host_toolchain(
        LinuxHost(distribution_id="ubuntu"),
        _statuses(first_root=tools),
        group_names=frozenset({"sudo"}),
        rule_roots=(rules,),
    )
    assert missing_group.usb.state is ToolHealthState.ATTENTION
    assert "not in plugdev" in missing_group.usb.detail

    ready = assess_host_toolchain(
        LinuxHost(distribution_id="ubuntu"),
        _statuses(first_root=tools),
        group_names=frozenset({"plugdev"}),
        rule_roots=(rules,),
    )
    assert ready.usb.state is ToolHealthState.VERIFIED


def test_real_communication_supersedes_static_permission_guess(tmp_path: Path) -> None:
    tools = _executables(tmp_path / "platform-tools")
    health = assess_host_toolchain(
        LinuxHost(distribution_id="fedora"),
        _statuses(first_root=tools),
        communication_verified=True,
        group_names=frozenset(),
        rule_roots=(),
    )

    assert health.usb.state is ToolHealthState.VERIFIED
    assert health.usb.title == "Genuine Android communication verified"


def test_windows_never_substitutes_generic_driver_for_exact_oem(tmp_path: Path) -> None:
    tools = _executables(tmp_path / "platform-tools")
    health = assess_host_toolchain(
        WindowsHost(),
        _statuses(first_root=tools),
    )

    assert health.usb.state is ToolHealthState.ATTENTION
    assert health.overall_state is ToolHealthState.ATTENTION
    assert health.usb.guide_article_id == "android-oem-usb-driver-source"
    assert "Google devices" in health.usb.detail
    assert "generic bundle" in health.usb.detail
