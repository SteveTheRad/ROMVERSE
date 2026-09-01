from __future__ import annotations

from dataclasses import dataclass

from romverse.ascension.models import AscensionMethod


@dataclass(frozen=True, slots=True)
class AscensionJourneyBrief:
    stage_number: int
    title: str
    romverse_action: str
    user_action: str
    why: str
    verified_checkpoints: int

    @property
    def progress_percent(self) -> int:
        return round(max(0, min(9, self.verified_checkpoints)) * 100 / 9)


@dataclass(frozen=True, slots=True)
class AscensionJourneyCheckpoint:
    stage_number: int
    title: str
    complete: bool


def build_journey_checkpoints(
    *,
    blocked: bool,
    manager_verified: bool,
    capsule_ready: bool,
    handoff_ready: bool,
    patched_ready: bool,
    integration_ready: bool,
    build_handoff_ready: bool,
    plan_ready: bool,
    manifest_ready: bool,
    final_handoff_ready: bool,
) -> tuple[AscensionJourneyCheckpoint, ...]:
    """Return the authoritative nine-stage evidence tracker used by every UI surface.

    A locally imported patched image may legitimately bypass the phone-handoff receipt, so the
    verified patched output also completes stage four. No other later receipt is allowed to make an
    earlier checkpoint look complete indirectly.
    """

    return (
        AscensionJourneyCheckpoint(1, "Prerequisites", not blocked),
        AscensionJourneyCheckpoint(2, "Official manager", manager_verified),
        AscensionJourneyCheckpoint(3, "Patch capsule", capsule_ready),
        AscensionJourneyCheckpoint(4, "Phone handoff", handoff_ready or patched_ready),
        AscensionJourneyCheckpoint(5, "Patched image", patched_ready),
        AscensionJourneyCheckpoint(6, "ROM integration", integration_ready),
        AscensionJourneyCheckpoint(7, "Build seal", build_handoff_ready),
        AscensionJourneyCheckpoint(8, "Device binding", plan_ready and manifest_ready),
        AscensionJourneyCheckpoint(9, "Guardian review", final_handoff_ready),
    )


def build_journey_brief(
    method: AscensionMethod,
    *,
    blocked: bool,
    manager_verified: bool,
    capsule_ready: bool,
    handoff_ready: bool,
    patched_ready: bool,
    integration_ready: bool,
    build_handoff_ready: bool,
    plan_ready: bool,
    manifest_ready: bool,
    review_ready: bool = False,
    manager_opened: bool = False,
) -> AscensionJourneyBrief:
    """Return the one next beginner action backed by current local evidence."""

    checkpoints = build_journey_checkpoints(
        blocked=blocked,
        manager_verified=manager_verified,
        capsule_ready=capsule_ready,
        handoff_ready=handoff_ready,
        patched_ready=patched_ready,
        integration_ready=integration_ready,
        build_handoff_ready=build_handoff_ready,
        plan_ready=plan_ready,
        manifest_ready=manifest_ready,
        final_handoff_ready=False,
    )
    next_stage = next(
        checkpoint.stage_number for checkpoint in checkpoints if not checkpoint.complete
    )
    verified_checkpoints = sum(checkpoint.complete for checkpoint in checkpoints)

    if next_stage == 1:
        return AscensionJourneyBrief(
            1,
            "Let ROMVERSE prepare the prerequisites",
            "ROMVERSE will verify and extract only the required source images, check the exact phone, and resolve every safe local gate in dependency order.",
            "Select the highlighted action. If ROMVERSE pauses, follow the one connection or authorization prompt it explains.",
            "A root image must be tied to the exact firmware and exact phone. Guessing here can make a device unbootable.",
            verified_checkpoints,
        )
    if next_stage == 2:
        return AscensionJourneyBrief(
            2,
            f"Verify the official {method.display_name} manager",
            "ROMVERSE will obtain the current stable manager from its official repository and require its published SHA-256 before vaulting it.",
            "Keep the PC online. Nothing is installed on the phone during this verification.",
            "A verified official manager prevents an unknown or modified APK from entering the preparation chain.",
            verified_checkpoints,
        )
    if next_stage == 3:
        return AscensionJourneyBrief(
            3,
            "Build the source-bound patch capsule",
            "ROMVERSE will copy and hash the pristine patch target, rollback image, and verified manager into an isolated capsule.",
            "No action is normally needed. Leave ROMVERSE open while the progress bar completes.",
            "The capsule proves which untouched image is being patched and preserves a byte-exact rollback source.",
            verified_checkpoints,
        )
    if next_stage == 4:
        return AscensionJourneyBrief(
            4,
            "Prepare the guided phone handoff",
            "ROMVERSE will show an exact review before installing the verified manager and copying only the pristine patch input to the authorized phone.",
            "Read the review and approve only if the displayed phone and two preparation actions are correct.",
            "Installing an app and copying a file change phone storage, so Guardian requires your approval even though no partition is written.",
            verified_checkpoints,
        )
    if next_stage == 5:
        manager = "Magisk" if method is AscensionMethod.MAGISK else "KernelSU Manager"
        return AscensionJourneyBrief(
            5,
            f"Create the patched image in {manager}",
            "ROMVERSE has prepared and transferred the exact source image. It will retrieve and verify the resulting image after the on-phone patch finishes.",
            (
                f"The verified {manager} is open. Choose its Select and Patch a File option, select the ROMVERSE image, then return here and choose Find patched image on phone."
                if manager_opened
                else f"Choose Open verified {manager} on phone. ROMVERSE will recheck the installed package and signing certificate before opening it; then select the ROMVERSE image for patching."
            ),
            "The official manager performs the method-specific patch; ROMVERSE then proves the output still belongs to this project before it can progress.",
            verified_checkpoints,
        )
    if next_stage == 6:
        return AscensionJourneyBrief(
            6,
            "Integrate root into the isolated ROM",
            "ROMVERSE will snapshot the pristine boot input, replace only that exact local build input with the verified patched image, and verify every byte.",
            "Choose Integrate verified root image. The protected firmware and connected phone remain untouched.",
            "This turns the verified manager output into a real rooted ROM build input while preserving a one-click rollback path.",
            verified_checkpoints,
        )
    if next_stage == 7:
        return AscensionJourneyBrief(
            7,
            "Seal the Ascension build input",
            "ROMVERSE will create a content-addressed copy of the integrated root partition, verify it byte for byte, and record the exact packaging route.",
            "Choose Seal rooted ROM build input. This is local preparation only and does not write to the phone.",
            "The build seal prevents a stale or substituted patched image from reaching Guardian review or a future ROM package.",
            verified_checkpoints,
        )
    if next_stage == 8:
        return AscensionJourneyBrief(
            8,
            "Bind the verified output to the exact phone",
            "ROMVERSE will rescan the connected phone, prove the slot and partition target, and compile a command-free Guardian manifest.",
            "Connect and authorize the same phone used for this project. ROMVERSE will not flash it during this stage.",
            "A valid patched image is not enough by itself; the target device, partition, slot, backup, and rollback route must also match.",
            verified_checkpoints,
        )
    return AscensionJourneyBrief(
        9,
        "Ready for final Guardian review" if review_ready else "Resolve the final Guardian gates",
        "ROMVERSE has compiled the exact intent, source, patched output, target, and rollback evidence into a tamper-evident review.",
        (
            "Review the manifest. A separate final consent is still required before any future device write."
            if review_ready
            else "Open the manifest and use its highlighted actions for any remaining backup, Device Pack, or exact-device evidence."
        ),
        "The final review is the last place to catch a wrong phone, wrong slot, missing backup, or changed artifact before any device write is considered.",
        verified_checkpoints,
    )
