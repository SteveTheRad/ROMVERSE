from pathlib import Path

from romverse.ascension.companion import AscensionCompanionStatusService
from romverse.ascension.models import (
    AscensionAssessment,
    AscensionGate,
    AscensionMethod,
    GateState,
)
from romverse.ascension.resolution import build_resolution_plan
from romverse.device_packs.registry import DevicePackRegistry
from romverse.rom.projects import RomProjectStore


def _report(*gates: AscensionGate) -> AscensionAssessment:
    return AscensionAssessment(
        "project",
        AscensionMethod.MAGISK,
        "protected source",
        "",
        gates,
        True,
    )


def _gate(gate_id: str, title: str = "Gate") -> AscensionGate:
    return AscensionGate(
        gate_id,
        title,
        GateState.BLOCKED,
        f"{title} evidence is unresolved",
        f"Resolve {title.casefold()}",
    )


def test_resolution_plan_prioritizes_existing_root_as_a_safety_stop() -> None:
    plan = build_resolution_plan(
        _report(_gate("patch-target", "Boot image"), _gate("root-state", "Existing root"))
    )

    assert plan.state == "safety-stop"
    assert plan.primary is not None
    assert plan.primary.action_id == "review-existing-root"
    assert plan.primary.kind == "safety-stop"
    assert not plan.primary.safe_to_start_automatically
    assert plan.automatic_step_count == 1
    assert plan.user_step_count == 1


def test_resolution_plan_marks_unambiguous_image_extraction_automatic() -> None:
    plan = build_resolution_plan(
        _report(
            _gate("live-device", "Authorized phone"),
            _gate("recovery", "Rollback"),
            _gate("patch-target", "Boot image"),
        )
    )

    assert plan.state == "resolving"
    assert plan.primary is not None
    assert plan.primary.action_id == "extract-root-images"
    assert plan.primary.button_label == "Auto-extract required boot images"
    assert plan.primary.safe_to_start_automatically
    assert plan.automatic_step_count == 1
    assert plan.steps[-1].action_id == "connect-authorized-device"


def test_resolution_plan_exposes_verified_tool_and_user_boundaries() -> None:
    plan = build_resolution_plan(
        _report(_gate("kernel", "Kernel support"), _gate("device-match", "Identity match"))
    )

    assert plan.primary is not None
    assert plan.primary.action_id == "verify-kernelsu-support"
    assert plan.primary.kind == "verified-tool"
    assert "official KernelSU Manager" in plan.primary.romverse_action
    assert plan.steps[1].kind == "user-required"
    assert "will not guess" in plan.steps[1].romverse_action


def test_resolution_plan_is_ready_when_no_gate_is_blocked() -> None:
    plan = build_resolution_plan(
        _report(AscensionGate("source", "Source", GateState.PASS, "Protected"))
    )

    assert plan.state == "ready"
    assert plan.primary is None
    assert plan.steps == ()


def test_companion_uses_the_same_plain_language_resolution_plan(tmp_path: Path) -> None:
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Companion resolution")
    source = tmp_path / "popsicle_images_OS3.0.318.0.WPBCNXM_test.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)

    status = AscensionCompanionStatusService(store, DevicePackRegistry(())).snapshot(
        project.project_id
    )

    assert status.state == "blocked"
    assert status.method == "none"
    assert "No technical choice is needed" in status.next_action
    assert "unambiguous contained source" in status.next_action
    assert "extract only the required" in status.romverse_action
    assert "No contained init_boot.img" in status.why
