from dataclasses import replace
from importlib.resources import files

import pytest

from romverse.device.catalog import DeviceCatalogMatch
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.registry import DevicePackRegistry
from romverse.device_packs.requirements import DeviceRequirementsService, RequirementState
from romverse.device_packs.validation import DevicePackValidationService


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
