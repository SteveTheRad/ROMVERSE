from dataclasses import replace
from importlib.resources import files

import pytest

from romverse.device.catalog import DeviceCatalogMatch
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.registry import DevicePackRegistry
from romverse.device_packs.requirements import (
    DeviceRequirementsService,
    ProjectSourceRequirements,
    RequirementState,
)
from romverse.device_packs.validation import DevicePackValidationService
from romverse.infrastructure.tools import ToolStatus


def _xiaomi() -> AndroidDevice:
    return AndroidDevice(
        "private-requirements",
        DeviceState.DEVICE,
        brand="Xiaomi",
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        product="popsicle_global",
        codename="popsicle",
    )


def test_exact_pack_blueprint_separates_build_compile_and_flash_requirements() -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    pack = registry.resolve(_xiaomi()).pack
    assert pack is not None and pack.build_contract is not None
    report = DevicePackValidationService().assess(pack, _xiaomi())

    blueprint = DeviceRequirementsService().assess(pack, report)

    identity = blueprint.lane("identity")
    build = blueprint.lane("build")
    compile_lane = blueprint.lane("compile")
    flash = blueprint.lane("flash")
    assert identity is not None and identity.state is RequirementState.DECLARED
    assert build is not None and build.state is RequirementState.VERIFIED
    assert build.route == "rom_studio"
    assert compile_lane is not None and compile_lane.state is RequirementState.DECLARED
    assert compile_lane.route == "forge_arsenal"
    assert compile_lane.requirements == pack.build_contract.required_tools
    assert flash is not None and flash.state is RequirementState.NEEDS_EVIDENCE
    assert flash.route == "time_machine"
    assert blueprint.report_digest == report.report_digest


def test_official_generic_identity_blueprint_never_invents_build_or_tool_contract() -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    device = AndroidDevice(
        "private-generic",
        DeviceState.DEVICE,
        brand="Example",
        manufacturer="Example Industries",
        model="EX-100",
        product="nebula_global",
        codename="nebula",
    )
    pack = registry.resolve(device).pack
    assert pack is not None and pack.pack_id == "android.generic"
    report = DevicePackValidationService().assess(pack, device)
    official = DeviceCatalogMatch(True, False, "Example Nebula", "EX-100", 1, "Exact")

    blueprint = DeviceRequirementsService().assess(pack, report, official)

    identity = blueprint.lane("identity")
    build = blueprint.lane("build")
    compile_lane = blueprint.lane("compile")
    flash = blueprint.lane("flash")
    assert identity is not None and identity.state is RequirementState.VERIFIED
    assert "Example Nebula" in identity.summary
    assert build is not None and build.state is RequirementState.LOCKED
    assert compile_lane is not None and compile_lane.state is RequirementState.LOCKED
    assert compile_lane.route == "archives"
    assert "generic tool bundle" in compile_lane.summary
    assert flash is not None and flash.state is RequirementState.LOCKED
    assert all(lane.route != "guardian_core" for lane in blueprint.lanes)


def test_requirements_blueprint_rejects_a_report_from_another_pack_digest() -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    pack = registry.resolve(_xiaomi()).pack
    assert pack is not None
    report = DevicePackValidationService().assess(pack, _xiaomi())

    with pytest.raises(ValueError, match="exact current Device Pack report"):
        DeviceRequirementsService().assess(
            pack,
            replace(report, pack_sha256="0" * 64),
        )


def test_exact_compile_lane_consumes_current_host_tool_evidence() -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    pack = registry.resolve(_xiaomi()).pack
    assert pack is not None and pack.build_contract is not None
    report = DevicePackValidationService().assess(pack, _xiaomi())
    statuses = tuple(
        ToolStatus(name, True, f"/verified/{index}", f"test-{index}", "Ready")
        for index, name in enumerate(pack.build_contract.required_tools)
    )

    ready = (
        DeviceRequirementsService()
        .assess(
            pack,
            report,
            tool_statuses=statuses,
        )
        .lane("compile")
    )
    assert ready is not None and ready.state is RequirementState.VERIFIED
    assert ready.badge == "14/14 TOOLS VERIFIED • HOST READY"
    assert ready.requirements == pack.build_contract.required_tools
    assert ready.button_label == "Review verified toolchain"

    unavailable = replace(statuses[-1], available=False, detail="Not installed")
    missing = (
        DeviceRequirementsService()
        .assess(
            pack,
            report,
            tool_statuses=(*statuses[:-1], unavailable),
        )
        .lane("compile")
    )
    assert missing is not None and missing.state is RequirementState.NEEDS_EVIDENCE
    assert missing.badge == "13/14 TOOLS VERIFIED • 1 MISSING"
    assert missing.requirements == (pack.build_contract.required_tools[-1],)
    assert missing.route == "forge_arsenal"
    assert missing.button_label == "Resolve missing build tools"

    contradictory = (
        DeviceRequirementsService()
        .assess(
            pack,
            report,
            tool_statuses=(*statuses, replace(statuses[-1], available=False)),
        )
        .lane("compile")
    )
    assert contradictory is not None
    assert contradictory.state is RequirementState.NEEDS_EVIDENCE
    assert contradictory.requirements == (pack.build_contract.required_tools[-1],)


def test_project_source_blueprint_replaces_stale_pack_build_and_tool_requirements() -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    pack = registry.resolve(_xiaomi()).pack
    assert pack is not None and pack.build_contract is not None
    report = DevicePackValidationService().assess(pack, _xiaomi())
    source = ProjectSourceRequirements(
        project_id="hyperos-current-1234",
        project_name="HyperOS current",
        source_sha256="a" * 64,
        device_pack_id="xiaomi.hyperos",
        source_kind="ota-payload",
        blueprint_digest="b" * 64,
        plan_digest="c" * 64,
        authority="project-local-build-evidence-only",
        manufacturer="Xiaomi",
        codename="popsicle",
        build_id="OS4.0.0.25.XPBCNXM",
        partition_count=58,
        required_tools=("Python", "Payload Dumper", "AVBTool"),
    )
    statuses = tuple(
        ToolStatus(name, True, f"/verified/{index}", "test", "Ready")
        for index, name in enumerate(source.required_tools)
    )

    blueprint = DeviceRequirementsService().assess(
        pack,
        report,
        tool_statuses=statuses,
        project_source=source,
    )

    assert blueprint.project_scoped
    assert blueprint.project_id == source.project_id
    assert blueprint.project_source_sha256 == source.source_sha256
    assert blueprint.source_required_tools == source.required_tools
    build = blueprint.lane("build")
    compile_lane = blueprint.lane("compile")
    flash = blueprint.lane("flash")
    assert build is not None and build.state is RequirementState.VERIFIED
    assert build.badge == "PROJECT SOURCE • LOCAL BASELINE READY"
    assert build.route == "rom_studio_project"
    assert "OS4.0.0.25" in build.summary
    assert compile_lane is not None and compile_lane.state is RequirementState.VERIFIED
    assert compile_lane.requirements == source.required_tools
    assert compile_lane.route == "forge_arsenal_project"
    assert flash is not None and flash.state is RequirementState.LOCKED
    assert flash.route == "archives"
    assert "cannot authorize writes" in flash.summary


def test_project_source_blueprint_keeps_exact_source_pack_tool_contract() -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    pack = registry.resolve(_xiaomi()).pack
    assert pack is not None and pack.build_contract is not None
    report = DevicePackValidationService().assess(pack, _xiaomi())
    source = ProjectSourceRequirements(
        "exact-project-1234",
        "Exact project",
        pack.build_contract.source.archive_sha256,
        pack.pack_id,
        "ota-payload",
        "b" * 64,
        "c" * 64,
        "project-local-build-evidence-only",
        "Xiaomi",
        "popsicle",
        "OS4.0.0.23.XPBCNXM",
        58,
        ("Python", "Payload Dumper", "AVBTool"),
    )

    blueprint = DeviceRequirementsService().assess(pack, report, project_source=source)

    build = blueprint.lane("build")
    compile_lane = blueprint.lane("compile")
    assert build is not None and build.badge == "PROJECT + EXACT PACK • BUILD READY"
    assert compile_lane is not None
    assert compile_lane.requirements == pack.build_contract.required_tools
    assert blueprint.source_required_tools == pack.build_contract.required_tools


@pytest.mark.parametrize(
    ("change", "value"),
    [
        ("codename", "different-device"),
        ("authority", "flash-authority"),
        ("blueprint_digest", "not-a-digest"),
    ],
)
def test_project_source_blueprint_rejects_changed_or_foreign_evidence(change, value) -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    pack = registry.resolve(_xiaomi()).pack
    assert pack is not None
    report = DevicePackValidationService().assess(pack, _xiaomi())
    source = ProjectSourceRequirements(
        "project-1234",
        "Project",
        "a" * 64,
        "xiaomi.hyperos",
        "ota-payload",
        "b" * 64,
        "c" * 64,
        "project-local-build-evidence-only",
        "Xiaomi",
        "popsicle",
        "OS4.0.0.25.XPBCNXM",
        58,
        ("Python", "Payload Dumper", "AVBTool"),
    )

    with pytest.raises(ValueError, match="exact current source blueprint"):
        DeviceRequirementsService().assess(
            pack,
            report,
            project_source=replace(source, **{change: value}),
        )
