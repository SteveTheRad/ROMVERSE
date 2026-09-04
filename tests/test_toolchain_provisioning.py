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
    install_system_packages,
    required_tools_for_debloat,
    required_tools_for_source,
)
from romverse.infrastructure.tools import ToolStatus


class LinuxHost:
    name = "Linux"
    distribution_id = "ubuntu"

    def find_tool(self, name):
        return Path("/usr/bin/pkexec") if name == "pkexec" else None


class FedoraHost(LinuxHost):
    distribution_id = "fedora"


class RecordingRunner:
    def __init__(self, fail_at: int = 0):
        self.calls = []
        self.fail_at = fail_at

    def run(self, args, timeout=10, cwd=None):
        self.calls.append((tuple(args), timeout, cwd))
        code = 1 if self.fail_at == len(self.calls) else 0
        return CommandResult(tuple(args), code, "ok", "authorization denied" if code else "")


def _pretend_package_tools_exist(monkeypatch, *paths: str) -> None:
    original_is_file = Path.is_file
    existing = {Path("/usr/bin/pkexec"), *(Path(path) for path in paths)}
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda path: path in existing or original_is_file(path),
    )


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
        ToolStatus("OEM USB Driver", False),
        ToolStatus("Git", True),
    )

    plan = create_provision_plan(LinuxHost(), statuses)

    assert [item.name for item in plan.managed] == ["ADB", "LP Make"]
    assert [item.name for item in plan.system] == ["EROFS Builder"]
    assert [item.name for item in plan.manual] == ["OEM USB Driver"]


def test_fedora_plan_uses_only_available_distro_packages() -> None:
    statuses = (
        ToolStatus("7-Zip", False),
        ToolStatus("EROFS Builder", False),
        ToolStatus("Fakeroot", False),
        ToolStatus("Java", False),
        ToolStatus("AAPT2", False),
        ToolStatus("APK Signer", False),
    )

    plan = create_provision_plan(FedoraHost(), statuses)

    assert [(item.name, item.packages) for item in plan.system] == [
        ("7-Zip", ("7zip",)),
        ("EROFS Builder", ("erofs-utils",)),
        ("Fakeroot", ("fakeroot",)),
    ]
    assert [item.name for item in plan.managed] == ["AAPT2", "APK Signer"]
    assert [item.name for item in plan.manual] == ["Java"]
    assert all("Fedora" in item.explanation for item in plan.system)
    aapt = next(item for item in plan.managed if item.name == "AAPT2")
    signer = next(item for item in plan.managed if item.name == "APK Signer")
    assert "Google Maven" in aapt.explanation
    assert "verification-only" in signer.explanation
    assert "full SDK Build Tools" in signer.explanation


def test_non_x86_linux_keeps_android_apk_tools_in_user_controlled_sdk_flow(
    monkeypatch,
) -> None:
    monkeypatch.setattr("romverse.infrastructure.provisioning.platform.machine", lambda: "aarch64")
    statuses = (ToolStatus("AAPT2", False), ToolStatus("APK Signer", False))

    plan = create_provision_plan(FedoraHost(), statuses)

    assert [item.name for item in plan.manual] == ["AAPT2", "APK Signer"]
    assert plan.managed == ()
    assert all("ANDROID_SDK_ROOT" in item.explanation for item in plan.manual)


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


def test_ubuntu_installer_uses_only_allowlisted_argument_array(monkeypatch) -> None:
    _pretend_package_tools_exist(monkeypatch, "/usr/bin/apt-get")
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

    success, detail = install_system_packages(items, LinuxHost(), runner)

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

    success, detail = install_system_packages((item,), LinuxHost(), runner)

    assert not success
    assert "outside ROMVERSE's Ubuntu allowlist" in detail
    assert runner.calls == []


def test_ubuntu_installer_reports_authorization_failure_and_stops(monkeypatch) -> None:
    _pretend_package_tools_exist(monkeypatch, "/usr/bin/apt-get")
    runner = RecordingRunner(fail_at=1)
    item = ToolProvisionItem("LZ4", ProvisionStrategy.SYSTEM, "", ("lz4",))

    success, detail = install_system_packages((item,), LinuxHost(), runner)

    assert not success
    assert "index refresh failed" in detail
    assert len(runner.calls) == 1


def test_fedora_installer_uses_only_allowlisted_argument_array(monkeypatch) -> None:
    _pretend_package_tools_exist(monkeypatch, "/usr/bin/dnf")
    runner = RecordingRunner()
    items = (
        ToolProvisionItem(
            "EROFS Builder",
            ProvisionStrategy.SYSTEM,
            "official",
            ("erofs-utils",),
        ),
        ToolProvisionItem("7-Zip", ProvisionStrategy.SYSTEM, "official", ("7zip",)),
    )

    success, detail = install_system_packages(items, FedoraHost(), runner)

    assert success
    assert "7zip, erofs-utils" in detail
    assert runner.calls[0][0] == (
        "/usr/bin/pkexec",
        "/usr/bin/dnf",
        "--refresh",
        "makecache",
    )
    assert runner.calls[1][0] == (
        "/usr/bin/pkexec",
        "/usr/bin/dnf",
        "--assumeyes",
        "--setopt=install_weak_deps=False",
        "install",
        "7zip",
        "erofs-utils",
    )


def test_fedora_installer_rejects_ubuntu_package_without_running(monkeypatch) -> None:
    _pretend_package_tools_exist(monkeypatch, "/usr/bin/dnf")
    runner = RecordingRunner()
    item = ToolProvisionItem(
        "7-Zip",
        ProvisionStrategy.SYSTEM,
        "official",
        ("p7zip-full",),
    )

    success, detail = install_system_packages((item,), FedoraHost(), runner)

    assert not success
    assert "outside ROMVERSE's Fedora allowlist" in detail
    assert runner.calls == []


def test_fedora_installer_rejects_allowlisted_package_bound_to_wrong_tool(monkeypatch) -> None:
    _pretend_package_tools_exist(monkeypatch, "/usr/bin/dnf")
    runner = RecordingRunner()
    item = ToolProvisionItem(
        "Unexpected",
        ProvisionStrategy.SYSTEM,
        "official",
        ("git",),
    )

    success, detail = install_system_packages((item,), FedoraHost(), runner)

    assert not success
    assert "outside ROMVERSE's Fedora allowlist" in detail
    assert runner.calls == []


def test_fedora_installer_reports_metadata_failure_and_stops(monkeypatch) -> None:
    _pretend_package_tools_exist(monkeypatch, "/usr/bin/dnf")
    runner = RecordingRunner(fail_at=1)
    item = ToolProvisionItem("LZ4", ProvisionStrategy.SYSTEM, "official", ("lz4",))

    success, detail = install_system_packages((item,), FedoraHost(), runner)

    assert not success
    assert "metadata refresh failed" in detail
    assert len(runner.calls) == 1


def test_unknown_linux_distribution_keeps_system_tools_manual() -> None:
    class UnknownLinuxHost(LinuxHost):
        distribution_id = "unknown-linux"

    plan = create_provision_plan(UnknownLinuxHost(), (ToolStatus("EROFS Builder", False),))

    assert [item.name for item in plan.manual] == ["EROFS Builder"]
    assert plan.system == ()
