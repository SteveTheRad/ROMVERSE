from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from romverse.rom.readiness import BuildReadinessReport, GateStatus


class ResolutionKind(StrEnum):
    AUTOMATIC = "automatic"
    GUIDED_INPUT = "guided_input"
    EXTERNAL_EVIDENCE = "external_evidence"


@dataclass(frozen=True, slots=True)
class ForgeResolutionStep:
    gate_id: str
    title: str
    action_id: str
    kind: ResolutionKind
    explanation: str


_ACTIONS: dict[str, tuple[str, ResolutionKind, str]] = {
    "inspection": (
        "inspect",
        ResolutionKind.AUTOMATIC,
        "Inspect the protected container with bounded limits.",
    ),
    "tree": (
        "prepare-tree",
        ResolutionKind.AUTOMATIC,
        "Create a verified working copy and contained extraction tree.",
    ),
    "plan": (
        "plan",
        ResolutionKind.AUTOMATIC,
        "Regenerate the deterministic plan from the current tree.",
    ),
    "tools": (
        "tools",
        ResolutionKind.AUTOMATIC,
        "Install and verify only the missing contract-scoped tools.",
    ),
    "device-build-plan": (
        "contract-plan",
        ResolutionKind.AUTOMATIC,
        "Prepare exact partition inputs and save the source-bound execution plan.",
    ),
    "local-candidate": (
        "local-build",
        ResolutionKind.AUTOMATIC,
        "Build and byte-verify the versioned local candidate.",
    ),
    "signer": (
        "avb-inspect",
        ResolutionKind.AUTOMATIC,
        "Inspect AVB topology before asking for any external signing identity.",
    ),
    "original": (
        "choose-source",
        ResolutionKind.GUIDED_INPUT,
        "Select the exact firmware source; ROMVERSE cannot choose a personal file without consent.",
    ),
    "recipe": (
        "review-recipe",
        ResolutionKind.GUIDED_INPUT,
        "Review intended modifications before ROMVERSE applies them transactionally.",
    ),
    "device": (
        "connect-device",
        ResolutionKind.GUIDED_INPUT,
        "Connect and authorize the exact target phone.",
    ),
    "battery": (
        "charge-device",
        ResolutionKind.GUIDED_INPUT,
        "Charge and cool the phone; software cannot manufacture battery safety evidence.",
    ),
    "boot": (
        "refresh-device",
        ResolutionKind.GUIDED_INPUT,
        "Authorize a fresh read-only scan so boot evidence can be observed.",
    ),
    "recovery": (
        "recovery-evidence",
        ResolutionKind.AUTOMATIC,
        "Create or verify the safe local checkpoint first, then request only personal recovery evidence ROMVERSE cannot choose.",
    ),
    "device-pack-build": (
        "source-blueprint",
        ResolutionKind.AUTOMATIC,
        "Derive the model, build, partition geometry, AVB inputs, hashes, and local plan from the exact protected firmware.",
    ),
    "device-pack-flash": (
        "flash-validation",
        ResolutionKind.EXTERNAL_EVIDENCE,
        "Automatic local preparation is complete; Guardian now requires a signed exact-device partition-write and physical-recovery contract.",
    ),
    "user-backup": (
        "confirm-user-backup",
        ResolutionKind.GUIDED_INPUT,
        "Confirm an independently readable user-data backup at final Guardian handoff.",
    ),
    "physical-validation": (
        "review-release-certification",
        ResolutionKind.EXTERNAL_EVIDENCE,
        "Independent signed physical certification is required for the final write manifest and cannot be fabricated locally.",
    ),
}


def resolution_plan(report: BuildReadinessReport) -> tuple[ForgeResolutionStep, ...]:
    """Return dependency-ordered truthful actions for every unresolved gate."""

    steps = []
    for gate in report.gates:
        if gate.status is GateStatus.PASS:
            continue
        action, kind, explanation = _ACTIONS.get(
            gate.gate_id,
            (
                "review-evidence",
                ResolutionKind.GUIDED_INPUT,
                "Review the evidence and provide the missing authoritative input.",
            ),
        )
        steps.append(ForgeResolutionStep(gate.gate_id, gate.label, action, kind, explanation))
    # Final signed flash/recovery certification can appear before later safe local
    # gates in the readiness report. Preserve every dependency order except for
    # deferring those irreducible external attestations, so local recovery work is
    # never stranded behind evidence ROMVERSE cannot manufacture.
    return tuple(
        step for step in steps if step.kind is not ResolutionKind.EXTERNAL_EVIDENCE
    ) + tuple(step for step in steps if step.kind is ResolutionKind.EXTERNAL_EVIDENCE)
