from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from romverse.device.models import AndroidDevice, DeviceState
from romverse.infrastructure.local_store import LocalStoreError, atomic_write_json, read_json_object
from romverse.infrastructure.provisioning import GENESIS_REQUIRED_TOOLS
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.workspace_recovery import WorkspaceRecoveryService

VERIFIED_ROM_INSTALLATION_ACTION = "Prepare verified ROM installation…"


class GuidedStageStatus(StrEnum):
    COMPLETE = "complete"
    READY = "ready"
    LOCKED = "locked"
    ATTENTION = "attention"
    FUTURE = "future"


@dataclass(frozen=True, slots=True)
class GuidedStage:
    stage_id: str
    number: int
    short_title: str
    title: str
    explanation: str
    recommendation: str
    action: str
    action_label: str
    optional: bool = False
    future_gate: bool = False


@dataclass(frozen=True, slots=True)
class GuidedContext:
    project_exists: bool = False
    original_imported: bool = False
    inspection_saved: bool = False
    working_copy_ready: bool = False
    working_tree_ready: bool = False
    extraction_budget_safe: bool = False
    extraction_budget_detail: str = ""
    device: AndroidDevice | None = None
    observed_devices: tuple[AndroidDevice, ...] = ()
    device_scan_error: str = ""
    device_pack_id: str = ""
    device_dna_ready: bool = False
    capability_map_ready: bool = False
    device_dna_evidence: tuple[str, ...] = ()
    recipe_saved: bool = False
    recipe_validated: bool = False
    recipe_skipped: bool = False
    customization_skipped: bool = False
    debloat_complete: bool = False
    root_choice: str = "undecided"
    ascension_integrated: bool = False
    ascension_complete: bool = False
    build_plan_saved: bool = False
    build_plan_verified: bool = False
    recovery_snapshot_ready: bool = False
    tool_statuses: tuple[ToolStatus, ...] = ()
    build_artifact_ready: bool = False
    signed_artifact_ready: bool = False
    install_requested: bool = False
    guardian_handoff_ready: bool = False
    guardian_flash_handoff_ready: bool = False
    guardian_flash_mode: str = ""
    flash_complete: bool = False
    boot_observation_stable: bool = False
    first_boot_verified: bool = False
    required_tools: tuple[str, ...] = ()
    local_image_state: str = ""
    local_image_summary: str = ""
    local_image_count: int = 0
    local_image_boot_status: str = ""
    source_installation_state: str = ""
    source_installation_summary: str = ""
    source_installation_completed_count: int = 0
    source_installation_expected_count: int = 0
    source_installation_boot_status: str = ""


@dataclass(frozen=True, slots=True)
class GuidedAssessment:
    stage: GuidedStage
    status: GuidedStageStatus
    evidence: tuple[str, ...]
    blockers: tuple[str, ...]
    next_outcome: str

    @property
    def can_run(self) -> bool:
        return self.status in {GuidedStageStatus.READY, GuidedStageStatus.ATTENTION}


@dataclass(frozen=True, slots=True)
class GuidedFailure:
    title: str
    explanation: str
    recommendations: tuple[str, ...]
    safe_cleanup: bool = False


@dataclass(frozen=True, slots=True)
class GuidedMissionState:
    schema_version: int = 6
    updated_at: str = ""
    selected_stage: str = "project"
    customization_skipped: bool = False
    recipe_skipped: bool = False
    recipe_validated: bool = False
    build_plan_verified: bool = False
    last_error: str = ""
    root_choice: str = "undecided"
    install_requested: bool = False


@dataclass(frozen=True, slots=True)
class GenesisFlightPlan:
    """Compact, evidence-derived Genesis status for non-mission surfaces."""

    project_name: str
    stage_number: int
    stage_total: int
    stage_title: str
    status: GuidedStageStatus
    progress_percent: int
    verified_stages: int
    blockers: tuple[str, ...]
    recommendation: str
    action_label: str
    root_route: str
    recovery_ready: bool
    guardian_ready: bool
    has_saved_error: bool = False


STAGES = (
    GuidedStage(
        "project",
        1,
        "Project",
        "Create the mission workspace",
        "A ROMVERSE project keeps the protected source, working tree, evidence, recipes, and recovery material together.",
        "Use a clear device and ROM name. If a phone is connected, ROMVERSE will suggest its Device Pack automatically.",
        "new-project",
        "Create ROM project",
    ),
    GuidedStage(
        "firmware",
        2,
        "Firmware",
        "Load the untouched firmware",
        "Choose the complete stock ROM, OTA, factory archive, image, or firmware package that will be the trusted starting point.",
        "Prefer firmware published for the exact model, region, and bootloader generation. ROMVERSE copies and hashes it; the selected source is never edited.",
        "import",
        "Choose firmware…",
    ),
    GuidedStage(
        "provenance",
        3,
        "Provenance",
        "Verify and understand the source",
        "ROMVERSE recomputes SHA-256, checks the protected copy, and performs bounded structure inspection without extracting content.",
        "Stop if the hash changes or the container reports critical findings. A trustworthy build begins with trustworthy evidence.",
        "verify-inspect",
        "Run integrity checks",
    ),
    GuidedStage(
        "workspace",
        4,
        "Working lab",
        "Prepare an isolated working tree",
        "A verified working copy and contained tree keep every modification away from the protected original. ROMVERSE extracts supported archives or stages a recognized single firmware image automatically.",
        "Keep the protected original immutable. All recipes and future build work must target only this isolated tree.",
        "prepare-workspace",
        "Prepare working lab",
    ),
    GuidedStage(
        "device",
        5,
        "Device DNA",
        "Confirm device identity and capabilities",
        "ROMVERSE performs a fresh read-only Android scan, compares the authorized device with the protected firmware and Device Pack, then recompiles Device DNA and its Capability Map.",
        "Connect by USB, unlock the phone, enable USB debugging, and accept the computer fingerprint. Unknown evidence remains unconfirmed, and ROMVERSE never permits bootloader relocking.",
        "check-device",
        "Scan device & refresh DNA",
    ),
    GuidedStage(
        "customize",
        6,
        "Customize",
        "Choose the changes to make",
        "Build a bounded Recipe with explained operations and previewed targets, or explicitly continue with an unchanged base.",
        "Make one purposeful change at a time. Smaller recipes are easier to diagnose, review, and roll back.",
        "create-recipe",
        "Open Recipe Forge",
        optional=True,
    ),
    GuidedStage(
        "validate_recipe",
        7,
        "Validate changes",
        "Apply safely and verify the result",
        "ROMVERSE binds approval to the current inputs, snapshots affected targets, applies the Recipe transactionally, and verifies the result.",
        "If any recipe step fails, ROMVERSE restores the working tree automatically. The phone and protected original remain untouched.",
        "validate-recipe",
        "Apply and validate recipe",
        optional=True,
    ),
    GuidedStage(
        "debloat",
        8,
        "Nebula Debloat",
        "Review removable system apps",
        "ROMVERSE scans the isolated firmware tree, classifies every system app with a clear green, orange, or red safety signal, and lets you review the exact proposed removals.",
        "Green apps are recommended optional components. Orange apps need your explicit review. Red Android and device-critical components are Guardian-locked and can never be selected.",
        "guided-debloat",
        "Scan system apps",
        optional=True,
    ),
    GuidedStage(
        "root_choice",
        9,
        "Root choice",
        "Choose whether this ROM should include root",
        "Root is optional. ROMVERSE can continue with a clean unrooted ROM, or guide the verified source through Ascension Protocol before the build is frozen.",
        "Choose No for the standard unrooted route. Choose Yes only when you want ROMVERSE to prepare a source-bound Magisk or KernelSU image and complete its Guardian review.",
        "choose-root",
        "Choose rooted or unrooted…",
        optional=True,
    ),
    GuidedStage(
        "toolchain",
        10,
        "Toolchain",
        "Verify every required tool",
        "ROMVERSE checks the local build and Android command-line tools before a real build can begin.",
        "Install tools through ROMVERSE Forge Arsenal, then return here and refresh. Versions must be pinned into the final build record.",
        "refresh-tools",
        "Install and verify requirements",
    ),
    GuidedStage(
        "build_plan",
        11,
        "Build readiness",
        "Freeze a deterministic build plan",
        "ROMVERSE inventories the working tree, records its digest, and verifies that nothing changes between planning and execution.",
        "Regenerate the plan after every intentional Recipe change. Unexpected tree changes must be investigated before building.",
        "plan-verify",
        "Create and verify plan",
    ),
    GuidedStage(
        "build_sign",
        12,
        "Build & sign",
        "Build, sign, and verify the ROM artifact",
        "Forge Control runs the source-bound build pipeline, validates every output byte, verifies AVB topology, and records a reproducible artifact receipt.",
        "ROMVERSE resolves every safe local prerequisite automatically and pauses only when an authorized signing identity or authoritative device evidence must come from you.",
        "build-sign",
        "Resolve build automatically",
    ),
    GuidedStage(
        "recovery",
        13,
        "Recovery",
        "Establish the final recovery checkpoint",
        "A verified Time Machine checkpoint protects the local build baseline. A future device flash additionally requires a real device backup and an exact recovery path.",
        "Preserve the verified build first. Before flashing, keep important phone data outside the device and prove the supported stock recovery route.",
        "snapshot",
        "Create recovery checkpoint",
    ),
    GuidedStage(
        "flash",
        14,
        "ROM installation",
        "Review the phone installation route",
        "Phone installation is optional and separate from the local build. ROMVERSE prefers a complete, understood package procedure and keeps manual verified-image subsets as an explicitly limited alternative. Every route still requires exact-phone review, warnings and final consent; no prepared route is a production certificate.",
        "Finish after the local build, or prepare a verified ROM installation route. Review backups and recovery options before any write; do not repeat a completed operation just to turn certification rows green. Bootloader relocking is never offered.",
        "flash",
        VERIFIED_ROM_INSTALLATION_ACTION,
    ),
    GuidedStage(
        "first_boot",
        15,
        "First boot",
        "Guide first boot and verify health",
        "ROMVERSE will watch reconnect and boot progress, explain expected pauses, collect diagnostics, and confirm core Android health after installation.",
        "Do not disconnect during a declared critical phase. If boot verification fails, Guardian will select the safest supported recovery route.",
        "first-boot",
        "Start first-boot checks",
    ),
)


class GuidedMissionEngine:
    """Derive mission progress from evidence instead of trusting UI checkboxes."""

    def assess(self, context: GuidedContext) -> tuple[GuidedAssessment, ...]:
        facts = self._facts(context)
        assessments: list[GuidedAssessment] = []
        previous_complete = True
        for stage in STAGES:
            complete, evidence, blockers = facts[stage.stage_id]
            if complete:
                status = GuidedStageStatus.COMPLETE
            elif stage.stage_id in {"flash", "first_boot"} and context.source_installation_state:
                status = GuidedStageStatus.ATTENTION
            elif stage.stage_id in {"flash", "first_boot"} and not context.install_requested:
                status = GuidedStageStatus.FUTURE
            elif stage.stage_id in {"flash", "first_boot"} and context.local_image_state:
                # A measured local subset outcome is actionable context, never proof
                # that the production flash or full first-boot stage is complete.
                status = GuidedStageStatus.ATTENTION
            elif stage.stage_id == "flash" and context.guardian_handoff_ready:
                status = GuidedStageStatus.READY
            elif stage.future_gate:
                status = GuidedStageStatus.FUTURE
            elif not previous_complete:
                status = GuidedStageStatus.LOCKED
            elif blockers:
                status = GuidedStageStatus.ATTENTION
            else:
                status = GuidedStageStatus.READY
            assessments.append(
                GuidedAssessment(
                    stage,
                    status,
                    evidence,
                    blockers,
                    self._next_outcome(stage.stage_id, context),
                )
            )
            previous_complete = previous_complete and complete
        return tuple(assessments)

    @staticmethod
    def current_index(assessments: tuple[GuidedAssessment, ...]) -> int:
        for index, assessment in enumerate(assessments):
            if assessment.status is not GuidedStageStatus.COMPLETE:
                return index
        return max(0, len(assessments) - 1)

    @staticmethod
    def progress(assessments: tuple[GuidedAssessment, ...]) -> int:
        completed = sum(item.status is GuidedStageStatus.COMPLETE for item in assessments)
        return round(completed * 100 / len(assessments)) if assessments else 0

    @staticmethod
    def diagnose(message: str) -> GuidedFailure:
        normalized = message.casefold()
        if (
            "insufficient free space" in normalized
            or "no space" in normalized
            or "extraction requires" in normalized
        ):
            return GuidedFailure(
                "Workspace needs more free space",
                "ROMVERSE stopped before producing a partial or unreliable artifact.",
                (
                    "Free space on the workspace drive, then retry.",
                    "Keep at least the firmware size plus a safety reserve available.",
                ),
                True,
            )
        if (
            "expanded size" in normalized
            or "expansion ratio" in normalized
            or "hard limit" in normalized
        ):
            return GuidedFailure(
                "Archive expansion safety check stopped extraction",
                "ROMVERSE compared the archive's declared output with disk capacity and anti-zip-bomb limits before writing the working tree.",
                (
                    "Confirm the firmware came from a trusted source and rerun structure inspection.",
                    "If the declared size is legitimate, use a workspace drive with sufficient free space.",
                ),
            )
        if "sha-256" in normalized or "integrity" in normalized or "hash" in normalized:
            return GuidedFailure(
                "Integrity evidence does not match",
                "The source or working artifact differs from its recorded digest, so continuing would be unsafe.",
                (
                    "Do not bypass this check.",
                    "Re-download the correct firmware or recreate the derived working copy from the protected original.",
                ),
            )
        if "unsupported" in normalized or "container" in normalized:
            return GuidedFailure(
                "Firmware format needs a compatible extractor",
                "The current safe extractor cannot prove that it can contain this firmware format.",
                (
                    "Confirm the package is complete and intended for this model.",
                    "Install the required payload or OEM extractor through Forge Arsenal.",
                ),
            )
        if "unauthorized" in normalized or "accept" in normalized or "fingerprint" in normalized:
            return GuidedFailure(
                "Android has not authorized this computer",
                "ADB can see the phone, but Android has not granted debugging access.",
                (
                    "Unlock the phone and accept the USB debugging fingerprint.",
                    "If no prompt appears, revoke USB debugging authorizations, reconnect, and retry.",
                ),
            )
        if "symbolic link" in normalized or "outside" in normalized or "traversal" in normalized:
            return GuidedFailure(
                "Guardian contained an unsafe path",
                "A path could escape or redirect outside the isolated working tree.",
                (
                    "Inspect the archive or Recipe target before retrying.",
                    "Never disable containment checks for an unknown package.",
                ),
            )
        if "missing" in normalized or "not found" in normalized:
            return GuidedFailure(
                "A required input is missing",
                "The mission state references an artifact or tool that is no longer available.",
                (
                    "Return to the highlighted prerequisite stage.",
                    "Recreate derived files from the protected original instead of substituting unknown data.",
                ),
                True,
            )
        return GuidedFailure(
            "This stage needs attention",
            message or "ROMVERSE stopped because the operation did not produce verified evidence.",
            (
                "Review the evidence below and retry the same stage.",
                "If it repeats, preserve the project logs before changing the inputs.",
            ),
        )

    @staticmethod
    def clean_partial_files(workspace: Path, project_id: str = "") -> tuple[Path, ...]:
        """Remove recognized transaction artifacts without scanning an extracted tree."""

        return (
            WorkspaceRecoveryService(workspace)
            .recover(
                project_id,
                stale_after_seconds=0,
            )
            .removed_paths
        )

    @staticmethod
    def _facts(
        context: GuidedContext,
    ) -> dict[str, tuple[bool, tuple[str, ...], tuple[str, ...]]]:
        device = context.device
        source_complete = (
            context.source_installation_state == "completed"
            and context.source_installation_expected_count > 0
            and context.source_installation_completed_count
            == context.source_installation_expected_count
        )
        source_evidence = (
            (
                f"Historical source-declared installation: {context.source_installation_state}",
                f"{context.source_installation_completed_count} / "
                f"{context.source_installation_expected_count} declared actions completed",
                context.source_installation_summary,
                "Independent image readback and full subsystem certification remain unverified.",
            )
            if context.source_installation_state
            else ()
        )
        local_image_evidence = (
            (
                f"Local image subset operation: {context.local_image_state} • "
                f"{context.local_image_count} selected image(s)",
                context.local_image_summary,
                f"Separate Android boot observation: {context.local_image_boot_status or 'unverified'}",
                "Not a full-ROM installation, independent image readback, or production certificate.",
            )
            if context.local_image_state
            else ()
        )
        authorized = device is not None and device.state is DeviceState.DEVICE
        observed = context.observed_devices
        device_evidence = (
            (
                f"Authorized {device.display_name} ({device.codename or 'codename unknown'})"
                if authorized and device is not None
                else f"Detected {device.display_name} in {device.state.value} mode"
                if device is not None
                else f"Detected {len(observed)} Android devices; target selection required"
                if len(observed) > 1
                else f"Detected {observed[0].display_name}; target selection required"
                if observed
                else "Latest Android device scan failed"
                if context.device_scan_error
                else "No authorized Android device detected"
            ),
            (
                f"Matched Device Pack: {context.device_pack_id}"
                if context.device_pack_id
                else "No matching Device Pack confirmed"
            ),
        ) + context.device_dna_evidence
        device_blockers: list[str] = []
        if device is None:
            if len(observed) > 1:
                device_blockers.append(
                    f"Choose one of the {len(observed)} detected Android devices in Device Center "
                    "before continuing."
                )
            elif observed:
                device_blockers.append(
                    "Select the detected Android device in Device Center before continuing."
                )
            elif context.device_scan_error:
                detail = " ".join(context.device_scan_error.split())
                if len(detail) > 180:
                    detail = f"{detail[:179].rstrip()}…"
                device_blockers.append(
                    "The latest USB device scan failed"
                    + (f": {detail}" if detail else "")
                    + ". ROMVERSE is not treating this as proof that the phone is disconnected; "
                    "retry the read-only scan."
                )
            else:
                device_blockers.append(
                    "No Android device is currently visible. Connect the target phone by USB, "
                    "enable USB debugging, then refresh the scan."
                )
        elif device.state is DeviceState.UNAUTHORIZED:
            device_blockers.append(
                "USB phone detected. Unlock it and approve this computer's USB debugging "
                "fingerprint, then refresh the scan."
            )
        elif device.state is DeviceState.OFFLINE:
            device_blockers.append(
                "ADB detected the phone, but it is offline. Reconnect USB or restart ADB, then "
                "refresh the scan."
            )
        elif device.is_fastboot:
            device_blockers.append(
                f"Phone detected in {device.state.value} mode. Boot normal Android with USB "
                "debugging enabled, then refresh to compile complete Device DNA."
            )
        elif device.state in {DeviceState.RECOVERY, DeviceState.SIDELOAD}:
            device_blockers.append(
                f"Phone detected in {device.state.value} mode. Return to normal Android with USB "
                "debugging enabled, then refresh to compile complete Device DNA."
            )
        elif device.state is not DeviceState.DEVICE:
            device_blockers.append(
                "ROMVERSE detected the phone, but its connection mode is unknown. Reconnect in "
                "normal Android with USB debugging enabled, then refresh the scan."
            )
        if not context.device_pack_id:
            device_blockers.append("A compatible Device Pack must identify the exact target.")
        if not context.device_dna_ready:
            device_blockers.append(
                "Device DNA must be compiled from the current protected firmware and fresh device scan."
            )
        elif not context.capability_map_ready:
            device_blockers.append(
                "The Device DNA Capability Map is incomplete and must be refreshed."
            )

        tool_map = {item.name.casefold(): item for item in context.tool_statuses}
        required_tools = tuple(
            name.casefold() for name in (context.required_tools or GENESIS_REQUIRED_TOOLS)
        )
        missing_tools = tuple(
            name for name in required_tools if name not in tool_map or not tool_map[name].available
        )
        tool_evidence = tuple(
            f"{item.name}: {'ready' if item.available else 'missing'}"
            + (f" ({item.version})" if item.version else "")
            for item in context.tool_statuses
        ) or ("Toolchain has not been verified in this session",)

        recipe_done = (
            context.customization_skipped or context.recipe_saved or context.recipe_skipped
        )
        validation_done = (
            context.customization_skipped or context.recipe_validated or context.recipe_skipped
        )
        debloat_done = context.customization_skipped or context.debloat_complete
        root_choice = (
            context.root_choice
            if context.root_choice in {"undecided", "skip", "ascension"}
            else "undecided"
        )
        root_choice_complete = (root_choice == "skip" and not context.ascension_integrated) or (
            root_choice == "ascension" and context.ascension_complete
        )
        if root_choice == "skip" and not context.ascension_integrated:
            root_evidence = ("Unrooted ROM route selected; no root image will be packaged",)
            root_blockers: tuple[str, ...] = ()
        elif root_choice == "skip":
            root_evidence = ("Unrooted ROM route selected, but a rooted input still exists",)
            root_blockers = (
                "A rooted local input is still integrated. Choose the unrooted route again so ROMVERSE can restore the pristine image.",
            )
        elif root_choice == "ascension" and context.ascension_complete:
            root_evidence = (
                "Ascension Protocol completed with a sealed, review-ready rooted ROM input",
            )
            root_blockers = ()
        elif root_choice == "ascension":
            root_evidence = ("Rooted ROM route selected; Ascension Protocol is not complete yet",)
            root_blockers = (
                "Finish Ascension Protocol, or review the choice and continue unrooted.",
            )
        else:
            root_evidence = ()
            root_blockers = ()
        return {
            "project": (
                context.project_exists,
                ("Versioned project manifest selected",) if context.project_exists else (),
                (),
            ),
            "firmware": (
                context.original_imported,
                ("Protected original imported and SHA-256 recorded",)
                if context.original_imported
                else (),
                (),
            ),
            "provenance": (
                context.inspection_saved,
                ("Integrity-checked structure report saved",) if context.inspection_saved else (),
                (),
            ),
            "workspace": (
                context.working_copy_ready and context.working_tree_ready,
                tuple(
                    text
                    for passed, text in (
                        (context.working_copy_ready, "Verified working copy ready"),
                        (context.working_tree_ready, "Contained extraction tree ready"),
                    )
                    if passed
                )
                + ((context.extraction_budget_detail,) if context.extraction_budget_detail else ()),
                ((context.extraction_budget_detail or "Extraction budget is not safe"),)
                if context.inspection_saved
                and not context.working_tree_ready
                and not context.extraction_budget_safe
                else (),
            ),
            "device": (
                bool(
                    authorized
                    and context.device_pack_id
                    and context.device_dna_ready
                    and context.capability_map_ready
                ),
                device_evidence,
                tuple(device_blockers),
            ),
            "customize": (
                recipe_done,
                (
                    ("Unchanged base selected" if context.customization_skipped else "Recipe saved")
                    if recipe_done
                    else "No customization decision recorded",
                ),
                (),
            ),
            "validate_recipe": (
                validation_done,
                ("Recipe result validated" if context.recipe_validated else "No changes to apply",)
                if validation_done
                else (),
                (),
            ),
            "debloat": (
                debloat_done,
                (
                    "Verified base kept unchanged; optional app removal was not requested"
                    if context.customization_skipped
                    else "System-app review completed with a verified Debloat receipt",
                )
                if debloat_done
                else (),
                (),
            ),
            "root_choice": (
                root_choice_complete,
                root_evidence,
                root_blockers,
            ),
            "build_plan": (
                context.build_plan_saved and context.build_plan_verified,
                tuple(
                    text
                    for passed, text in (
                        (context.build_plan_saved, "Deterministic build plan saved"),
                        (context.build_plan_verified, "Working tree matches saved plan"),
                    )
                    if passed
                ),
                (),
            ),
            "recovery": (
                context.recovery_snapshot_ready,
                ("Verified local recovery checkpoint available",)
                if context.recovery_snapshot_ready
                else (),
                (),
            ),
            "toolchain": (
                not missing_tools and bool(context.tool_statuses),
                tool_evidence,
                tuple(f"Required tool missing: {name}" for name in missing_tools),
            ),
            "build_sign": (
                context.build_artifact_ready and context.signed_artifact_ready,
                (
                    ("Signed build artifact verified",)
                    if context.build_artifact_ready and context.signed_artifact_ready
                    else ("Verified local build candidate available; signing remains locked",)
                    if context.build_artifact_ready
                    else ()
                ),
                (
                    (
                        "A verified local candidate is required before signing.",
                        "Use Forge Control to execute and byte-verify the exact Device Pack plan.",
                    )
                    if not context.build_artifact_ready
                    else (
                        "The local candidate is verified but no approved signing identity is configured.",
                        "Guardian will not simulate or falsely mark an unsigned candidate as signed.",
                    )
                ),
            ),
            "flash": (
                context.flash_complete or source_complete,
                ("Guardian flash receipt verified",)
                if context.flash_complete
                else source_evidence
                if source_evidence
                else local_image_evidence
                if local_image_evidence
                else (
                    "Local ROM build complete; optional phone installation was not requested",
                    "Flash-only evidence remains separate and does not invalidate the local artifact",
                    "No device write has started and bootloader relocking is permanently prohibited",
                )
                if not context.install_requested
                else (
                    f"Exact Guardian handoff prepared: {context.guardian_flash_mode}",
                    "No device write has started; final manifest review and consent remain required",
                    "Bootloader relocking is permanently prohibited",
                )
                if context.guardian_flash_handoff_ready
                else (
                    "Every safe automatic prerequisite is verified; Guardian handoff is ready",
                    "Backup choice, flash mode, exact manifest, final Guardian review, and consent remain",
                    "No device write has started and bootloader relocking is permanently prohibited",
                )
                if context.guardian_handoff_ready
                else (),
                ()
                if source_complete or context.flash_complete
                else (
                    "Review the recorded procedure outcome and diagnose the exact phone before "
                    "deciding on any new operation. Do not automatically repeat installation.",
                )
                if source_evidence
                else (
                    "Review the recorded local outcome. Continue the local image workflow only "
                    "if another deliberate operation is needed; do not repeat a completed write.",
                    "Full-firmware, readback and subsystem verification remain separate evidence.",
                )
                if local_image_evidence
                else (
                    "Prepare the project's source-bound image inventory and explicitly review "
                    "the phone, partition mappings, order and risks before final consent.",
                    "Production Device Pack certification is a separate optional review, not "
                    "a prerequisite for opening local image preparation.",
                ),
            ),
            "first_boot": (
                context.flash_complete and context.first_boot_verified,
                ("First boot and health verification appears stable",)
                if context.flash_complete and context.first_boot_verified
                else (
                    f"Historical Android boot observation: "
                    f"{context.source_installation_boot_status or 'unverified'}",
                    "Installation completion and measured boot are separate. "
                    "A stable boot record does not prove calls, camera, Android Auto or other subsystems.",
                )
                if source_evidence
                else (
                    "Local image subset outcome recorded; it does not prove a full-ROM first boot.",
                    f"Separate Android boot observation: {context.local_image_boot_status or 'unverified'}",
                )
                if local_image_evidence
                else ("Optional post-install verification is deferred with phone installation",)
                if not context.install_requested
                else (
                    "Stable read-only boot baseline recorded; not linked to a Guardian flash receipt",
                )
                if context.boot_observation_stable
                else ("No stable first-boot session has been recorded yet.",),
                (
                    "Review the saved outcome or run a separate read-only boot check. "
                    "There is no need to reinstall to observe Android.",
                    "Full subsystem validation is still required before this stage is certified.",
                )
                if source_evidence
                else (
                    (
                        "A verified Guardian flash receipt is required before ROMVERSE can classify any later stable sample as first boot."
                        if not context.flash_complete
                        else "Complete boot-observatory sample collection until the stability window passes."
                    ),
                ),
            ),
        }

    @staticmethod
    def _next_outcome(stage_id: str, context: GuidedContext) -> str:
        outcomes = {
            "project": "A versioned mission workspace becomes the source of truth.",
            "firmware": "The source is copied, hashed, and protected from modification.",
            "provenance": "ROMVERSE records trustworthy source evidence and container findings.",
            "workspace": "All future changes occur only inside a contained working tree.",
            "device": "Device-specific recommendations can be checked against the real target.",
            "customize": "Your intended changes become an auditable, reusable Recipe.",
            "validate_recipe": "Every affected target has rollback evidence and a verified result.",
            "debloat": "Your reviewed choices are applied transactionally with a verified rollback snapshot.",
            "root_choice": "Genesis continues with either a verified rooted input or an explicitly unrooted build.",
            "build_plan": "The exact inputs are frozen for repeatable build execution.",
            "recovery": "A local recovery point is verified before later high-risk work.",
            "toolchain": "The build environment is ready to be pinned into provenance records.",
            "build_sign": "A signed, validated ROM artifact will be ready for Guardian review.",
            "flash": "Review a supported package procedure or explicit image mappings, then separately confirm the exact installation. Saved outcomes remain available without repeating it.",
            "first_boot": "Observe Android boot without reinstalling, then validate individual phone features. Command completion alone never proves health.",
        }
        return outcomes[stage_id]


class GuidedMissionStore:
    NAME = "guided-mission.json"
    FORMAT = "romverse.guided-mission"
    SCHEMA_VERSION = 6
    MAX_BYTES = 64 * 1024
    MAX_ERROR_CHARS = 4096
    LEGACY_FIELDS = {
        "schema_version",
        "updated_at",
        "selected_stage",
        "customization_skipped",
        "recipe_skipped",
        "recipe_validated",
        "build_plan_verified",
        "last_error",
        "root_choice",
    }
    SIGNED_LEGACY_FIELDS = LEGACY_FIELDS | {"format", "record_digest"}
    CURRENT_FIELDS = SIGNED_LEGACY_FIELDS | {"install_requested"}

    def __init__(self, project_directory: Path) -> None:
        self.project_directory = project_directory
        self.path = project_directory / self.NAME

    def load(self) -> GuidedMissionState:
        try:
            data = read_json_object(
                self.path,
                boundary=self.project_directory,
                maximum_bytes=self.MAX_BYTES,
            )
            schema = data.get("schema_version")
            if type(schema) is not int or schema not in {2, 3, 4, 5, self.SCHEMA_VERSION}:
                return GuidedMissionState()
            if schema in {5, self.SCHEMA_VERSION}:
                expected_fields = (
                    self.CURRENT_FIELDS
                    if schema == self.SCHEMA_VERSION
                    else self.SIGNED_LEGACY_FIELDS
                )
                if set(data) != expected_fields or data.get("format") != self.FORMAT:
                    return GuidedMissionState()
                record_digest = data.get("record_digest")
                unsigned = dict(data)
                unsigned.pop("record_digest", None)
                if not _guided_digest(record_digest) or record_digest != _guided_payload_digest(
                    unsigned
                ):
                    return GuidedMissionState()
            elif not {"schema_version"} <= set(data) <= self.LEGACY_FIELDS:
                return GuidedMissionState()
            state = self._parse(data, legacy=schema != self.SCHEMA_VERSION)
            return state if state is not None else GuidedMissionState()
        except (LocalStoreError, OSError, ValueError, TypeError):
            return GuidedMissionState()

    def save(self, state: GuidedMissionState) -> GuidedMissionState:
        updated = GuidedMissionState(
            self.SCHEMA_VERSION,
            datetime.now(UTC).isoformat(),
            state.selected_stage,
            state.customization_skipped,
            state.recipe_skipped,
            state.recipe_validated,
            state.build_plan_verified,
            state.last_error,
            state.root_choice,
            state.install_requested,
        )
        if not self._valid(updated, allow_blank_time=False):
            raise ValueError("Genesis mission state contains invalid or unbounded fields")
        payload = self._payload(updated)
        payload["record_digest"] = _guided_payload_digest(payload)
        self.project_directory.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            self.path,
            payload,
            boundary=self.project_directory,
            maximum_bytes=self.MAX_BYTES,
        )
        return updated

    @classmethod
    def _payload(cls, state: GuidedMissionState) -> dict[str, object]:
        return {
            "format": cls.FORMAT,
            "schema_version": cls.SCHEMA_VERSION,
            "updated_at": state.updated_at,
            "selected_stage": state.selected_stage,
            "customization_skipped": state.customization_skipped,
            "recipe_skipped": state.recipe_skipped,
            "recipe_validated": state.recipe_validated,
            "build_plan_verified": state.build_plan_verified,
            "last_error": state.last_error,
            "root_choice": state.root_choice,
            "install_requested": state.install_requested,
        }

    @classmethod
    def _parse(cls, data: dict[str, object], *, legacy: bool) -> GuidedMissionState | None:
        boolean_fields = (
            "customization_skipped",
            "recipe_skipped",
            "recipe_validated",
            "build_plan_verified",
            "install_requested",
        )
        if any(field in data and type(data[field]) is not bool for field in boolean_fields):
            return None
        selected_stage = data.get("selected_stage", "project")
        root_choice = data.get("root_choice", "undecided")
        last_error = data.get("last_error", "")
        updated_at = data.get("updated_at", "")
        state = GuidedMissionState(
            cls.SCHEMA_VERSION,
            updated_at,
            selected_stage,
            data.get("customization_skipped", False),
            data.get("recipe_skipped", False),
            data.get("recipe_validated", False),
            data.get("build_plan_verified", False),
            last_error,
            root_choice,
            data.get("install_requested", False),
        )
        return state if cls._valid(state, allow_blank_time=legacy) else None

    @classmethod
    def _valid(cls, state: GuidedMissionState, *, allow_blank_time: bool) -> bool:
        stage_ids = {stage.stage_id for stage in STAGES}
        try:
            parsed_time = (
                datetime.fromisoformat(state.updated_at.replace("Z", "+00:00"))
                if state.updated_at
                else None
            )
        except (AttributeError, TypeError, ValueError):
            return False
        return (
            type(state.schema_version) is int
            and state.schema_version == cls.SCHEMA_VERSION
            and isinstance(state.updated_at, str)
            and (
                (allow_blank_time and not state.updated_at)
                or bool(parsed_time and parsed_time.tzinfo)
            )
            and isinstance(state.selected_stage, str)
            and state.selected_stage in stage_ids
            and type(state.customization_skipped) is bool
            and type(state.recipe_skipped) is bool
            and type(state.recipe_validated) is bool
            and type(state.build_plan_verified) is bool
            and isinstance(state.last_error, str)
            and len(state.last_error) <= cls.MAX_ERROR_CHARS
            and "\0" not in state.last_error
            and isinstance(state.root_choice, str)
            and state.root_choice in {"undecided", "skip", "ascension"}
            and type(state.install_requested) is bool
        )


def _guided_payload_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _guided_digest(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None
