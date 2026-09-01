from __future__ import annotations

from dataclasses import dataclass

from romverse.ascension.models import AscensionAssessment, AscensionGate, GateState


@dataclass(frozen=True, slots=True)
class AscensionResolutionStep:
    gate_id: str
    action_id: str
    title: str
    kind: str
    button_label: str
    romverse_action: str
    user_action: str
    why: str
    safe_to_start_automatically: bool = False


@dataclass(frozen=True, slots=True)
class AscensionResolutionPlan:
    state: str
    steps: tuple[AscensionResolutionStep, ...]

    @property
    def primary(self) -> AscensionResolutionStep | None:
        return self.steps[0] if self.steps else None

    @property
    def automatic_step_count(self) -> int:
        return sum(step.kind in {"automatic-local", "verified-tool"} for step in self.steps)

    @property
    def user_step_count(self) -> int:
        return sum(step.kind in {"user-required", "safety-stop"} for step in self.steps)


_PRIORITY = {
    "root-state": 0,
    "patch-target": 10,
    "recovery": 11,
    "source": 20,
    "source-contract": 21,
    "device-dna": 22,
    "kernel": 30,
    "live-device": 40,
    "device-match": 41,
    "bootloader": 42,
}


def build_resolution_plan(report: AscensionAssessment) -> AscensionResolutionPlan:
    """Convert blocked evidence into one deterministic, plain-language recovery plan."""

    blocked = tuple(gate for gate in report.gates if gate.state is GateState.BLOCKED)
    ordered = sorted(blocked, key=lambda gate: (_PRIORITY.get(gate.gate_id, 90), gate.gate_id))
    steps_by_action: dict[str, AscensionResolutionStep] = {}
    for gate in ordered:
        step = _step(gate)
        steps_by_action.setdefault(step.action_id, step)
    steps = tuple(steps_by_action.values())
    if not steps:
        state = "ready"
    elif steps[0].kind == "safety-stop":
        state = "safety-stop"
    elif any(step.kind in {"automatic-local", "verified-tool"} for step in steps):
        state = "resolving"
    else:
        state = "user-required"
    return AscensionResolutionPlan(state, steps)


def _step(gate: AscensionGate) -> AscensionResolutionStep:
    resolution = gate.resolution or "Review the evidence shown by ROMVERSE before continuing."
    if gate.gate_id == "root-state":
        return AscensionResolutionStep(
            gate.gate_id,
            "review-existing-root",
            gate.title,
            "safety-stop",
            "Review existing root first",
            "ROMVERSE will preserve the current root identity and stop a conflicting setup.",
            resolution,
            gate.detail,
        )
    if gate.gate_id in {"patch-target", "recovery"}:
        return AscensionResolutionStep(
            gate.gate_id,
            "extract-root-images",
            gate.title,
            "automatic-local",
            "Auto-extract required boot images",
            "ROMVERSE will locate one contained payload or image set, extract only the required boot/recovery partitions, hash them, and reassess the rollback evidence.",
            "No technical choice is needed when one unambiguous contained source is available. Keep Ascension open while ROMVERSE completes the local step.",
            gate.detail,
            True,
        )
    if gate.gate_id in {"source", "source-contract", "device-dna"}:
        return AscensionResolutionStep(
            gate.gate_id,
            "run-genesis-prerequisites",
            gate.title,
            "automatic-local",
            "Auto-resolve project prerequisites",
            "ROMVERSE will run the safe local Genesis detection, Device DNA, tool-resolution, and isolated-workspace stages in dependency order.",
            "Approve opening Genesis Sequence; device-changing stages remain unavailable.",
            gate.detail,
        )
    if gate.gate_id == "kernel":
        return AscensionResolutionStep(
            gate.gate_id,
            "verify-kernelsu-support",
            gate.title,
            "verified-tool",
            "Install manager & check KernelSU support",
            "ROMVERSE will acquire and verify the official KernelSU Manager, then prepare a separately approved app-only installation handoff.",
            "After the verified Manager opens, report its exact Supported or Unsupported result. ROMVERSE will not infer compatibility.",
            gate.detail,
        )
    if gate.gate_id == "live-device":
        return AscensionResolutionStep(
            gate.gate_id,
            "connect-authorized-device",
            gate.title,
            "user-required",
            "Connect and authorize the phone",
            "ROMVERSE has completed the local checks and will rescan read-only identity evidence when the phone appears.",
            resolution,
            gate.detail,
        )
    if gate.gate_id == "device-match":
        return AscensionResolutionStep(
            gate.gate_id,
            "select-matching-firmware",
            gate.title,
            "user-required",
            "Select matching firmware",
            "ROMVERSE will keep the conflicting project and phone isolated and will not guess across models.",
            resolution,
            gate.detail,
        )
    if gate.gate_id == "bootloader":
        return AscensionResolutionStep(
            gate.gate_id,
            "official-bootloader-process",
            gate.title,
            "user-required",
            "Review the official unlock requirement",
            "ROMVERSE will keep every write handoff blocked while the bootloader state is unsuitable.",
            resolution,
            gate.detail,
        )
    return AscensionResolutionStep(
        gate.gate_id,
        "review-evidence",
        gate.title,
        "user-required",
        "Review unresolved evidence",
        "ROMVERSE stopped instead of guessing at an unclassified safety gate.",
        resolution,
        gate.detail,
    )
