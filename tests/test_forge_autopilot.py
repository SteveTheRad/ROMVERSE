from romverse.rom.forge_autopilot import ResolutionKind, resolution_plan
from romverse.rom.readiness import BuildGate, BuildReadinessReport, GateStatus


def _report(*gates: BuildGate) -> BuildReadinessReport:
    return BuildReadinessReport(
        1, "id", "project", "now", gates, False, False, False, False, False, (), (), "d"
    )


def test_resolution_plan_orders_safe_actions_before_irreducible_evidence() -> None:
    report = _report(
        BuildGate("inspection", "Inspect", "Workspace", GateStatus.BLOCKED, "missing", "build"),
        BuildGate("tools", "Tools", "Build", GateStatus.ATTENTION, "missing", "build"),
        BuildGate("device-pack-build", "Pack", "Build", GateStatus.BLOCKED, "missing", "build"),
    )
    steps = resolution_plan(report)
    assert [step.action_id for step in steps] == ["inspect", "tools", "source-blueprint"]
    assert steps[-1].kind is ResolutionKind.AUTOMATIC
    assert steps[0].kind is ResolutionKind.AUTOMATIC


def test_flash_contract_is_external_evidence_after_local_automation() -> None:
    report = _report(
        BuildGate(
            "device-pack-flash",
            "Exact flash contract",
            "Recovery",
            GateStatus.ATTENTION,
            "local preparation complete",
            "flash",
        ),
        BuildGate(
            "physical-validation",
            "Physical recovery certification",
            "Guardian",
            GateStatus.ATTENTION,
            "signed evidence missing",
            "release",
        ),
    )

    steps = resolution_plan(report)

    assert [step.action_id for step in steps] == [
        "flash-validation",
        "review-release-certification",
    ]
    assert all(step.kind is ResolutionKind.EXTERNAL_EVIDENCE for step in steps)
    assert "partition-write" in steps[0].explanation
