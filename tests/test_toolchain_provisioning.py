from pathlib import Path

from romverse.infrastructure.process import CommandResult
from romverse.infrastructure.provisioning import (
    DEBLOAT_IMAGE_REQUIRED_TOOLS,
    DEBLOAT_OTA_REQUIRED_TOOLS,
    DEBLOAT_SUPER_REQUIRED_TOOLS,
    FASTBOOT_SUPER_REQUIRED_TOOLS,
    GENESIS_REQUIRED_TOOLS,
    OTA_SOURCE_REQUIRED_TOOLS,
    PARTITION_BUNDLE_REQUIRED_TOOLS,
    ROM_STUDIO_DEFAULT_REQUIRED_TOOLS,
    ProvisionStrategy,
    ToolProvisionItem,
    create_provision_plan,
    install_ubuntu_packages,
    required_tools_for_debloat,
    required_tools_for_source,
)
from romverse.infrastructure.tools import ToolStatus


class LinuxHost:
    name = "Linux"

    def find_tool(self, name):
        return Path("/usr/bin/pkexec") if name == "pkexec" else None


class RecordingRunner:
    def __init__(self, fail_at: int = 0):
        self.calls = []
        self.fail_at = fail_at

    def run(self, args, timeout=10, cwd=None):
        self.calls.append((tuple(args), timeout, cwd))
        code = 1 if self.fail_at == len(self.calls) else 0
        return CommandResult(tuple(args), code, "ok", "authorization denied" if code else "")


def test_genesis_profile_includes_proven_hyperos_build_tools() -> None:
    assert {
        "Payload Dumper",
        "EXT4 Browser",
        "EROFS Builder",
        "EROFS Verifier",
        "LP Make",
        "LP Unpack",
        "LP Dump",
        "Fakeroot",
        "AAPT2",
        "APK Signer",
        "AVBTool",
    }.issubset(GENESIS_REQUIRED_TOOLS)


def test_plan_separates_managed_system_and_manual_requirements() -> None:
    statuses = (
        ToolStatus("ADB", False),
        ToolStatus("EROFS Builder", False),
        ToolStatus("LP Make", False),
        ToolStatus("Google USB Driver", False),
        ToolStatus("Git", True),
    )

    plan = create_provision_plan(LinuxHost(), statuses)

    assert [item.name for item in plan.managed] == ["ADB", "LP Make"]
    assert [item.name for item in plan.system] == ["EROFS Builder"]
    assert [item.name for item in plan.manual] == ["Google USB Driver"]


def test_contract_scoped_plan_excludes_unrelated_missing_tools() -> None:
    statuses = (
        ToolStatus("ADB", False),
        ToolStatus("Fastboot", False),
        ToolStatus("Git", False),
        ToolStatus("Java", False),
    )

    plan = create_provision_plan(
        LinuxHost(),
        statuses,
        ("ADB", "Fastboot"),
    )

    assert [item.name for item in plan.missing] == ["ADB", "Fastboot"]
    assert "Git" not in ROM_STUDIO_DEFAULT_REQUIRED_TOOLS
    assert "Java" not in ROM_STUDIO_DEFAULT_REQUIRED_TOOLS


def test_contract_scoped_plan_keeps_required_tool_when_scan_result_is_absent() -> None:
    plan = create_provision_plan(
        LinuxHost(),
        (ToolStatus("ADB", False),),
        ("ADB", "Fastboot"),
    )

    assert [item.name for item in plan.managed] == ["ADB", "Fastboot"]


def test_source_structure_resolves_only_relevant_tool_profiles() -> None:
    assert required_tools_for_source(None, ("ota_payload",)) == OTA_SOURCE_REQUIRED_TOOLS
    assert required_tools_for_source(None, ("super",)) == FASTBOOT_SUPER_REQUIRED_TOOLS
    assert required_tools_for_source(None, ("boot", "vendor_boot")) == (
        PARTITION_BUNDLE_REQUIRED_TOOLS
    )
    assert required_tools_for_source(None) == ROM_STUDIO_DEFAULT_REQUIRED_TOOLS


def test_debloat_materialization_profile_resolves_every_read_only_image_tool() -> None:
    assert required_tools_for_debloat(("ota_payload",)) == DEBLOAT_OTA_REQUIRED_TOOLS
    assert required_tools_for_debloat(("super",)) == DEBLOAT_SUPER_REQUIRED_TOOLS
    assert required_tools_for_debloat(("system", "product")) == DEBLOAT_IMAGE_REQUIRED_TOOLS
    assert required_tools_for_debloat(()) == ()
    for profile in (
        DEBLOAT_OTA_REQUIRED_TOOLS,
        DEBLOAT_SUPER_REQUIRED_TOOLS,
        DEBLOAT_IMAGE_REQUIRED_TOOLS,
    ):
        assert {"simg2img", "EXT4 Browser", "EROFS Verifier", "Fakeroot"}.issubset(profile)


def test_exact_contract_tool_profile_overrides_structure_profile() -> None:
    class Contract:
        required_tools = ("Python", "LP Make")

    assert required_tools_for_source(Contract(), ("ota_payload",)) == (
        "Python",
        "LP Make",
    )


def test_ubuntu_installer_uses_only_allowlisted_argument_array() -> None:
    runner = RecordingRunner()
    items = (
        ToolProvisionItem(
            "EROFS Builder",
            ProvisionStrategy.SYSTEM,
            "official",
            ("erofs-utils",),
        ),
        ToolProvisionItem(
            "EROFS Verifier",
            ProvisionStrategy.SYSTEM,
            "official",
            ("erofs-utils",),
        ),
        ToolProvisionItem("APK Signer", ProvisionStrategy.SYSTEM, "official", ("apksigner",)),
    )

    success, detail = install_ubuntu_packages(items, LinuxHost(), runner)

    assert success
    assert "apksigner" in detail
    assert runner.calls[0][0] == ("/usr/bin/pkexec", "/usr/bin/apt-get", "update")
    assert runner.calls[1][0] == (
        "/usr/bin/pkexec",
        "/usr/bin/apt-get",
        "install",
        "--yes",
        "--no-install-recommends",
        "apksigner",
        "erofs-utils",
    )


def test_ubuntu_installer_rejects_non_allowlisted_package_without_running() -> None:
    runner = RecordingRunner()
    item = ToolProvisionItem("Unexpected", ProvisionStrategy.SYSTEM, "", ("evil-package",))

    success, detail = install_ubuntu_packages((item,), LinuxHost(), runner)

    assert not success
    assert "outside ROMVERSE's allowlist" in detail
    assert runner.calls == []


def test_ubuntu_installer_reports_authorization_failure_and_stops() -> None:
    runner = RecordingRunner(fail_at=1)
    item = ToolProvisionItem("LZ4", ProvisionStrategy.SYSTEM, "", ("lz4",))

    success, detail = install_ubuntu_packages((item,), LinuxHost(), runner)

    assert not success
    assert "index refresh failed" in detail
    assert len(runner.calls) == 1
