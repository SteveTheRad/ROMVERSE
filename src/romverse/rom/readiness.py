from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from romverse.ascension.build_handoff import RootRomBuildHandoffService
from romverse.ascension.evidence import AscensionEvidenceService
from romverse.ascension.integration import RootRomIntegrationService
from romverse.ascension.manifest import AscensionGuardianManifestService
from romverse.ascension.models import AscensionMethod
from romverse.ascension.planning import AscensionRootPlanService
from romverse.backup.handoff import BackupHandoffService
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.attestations import DevicePackAttestationStore
from romverse.device_packs.models import CapabilityStatus
from romverse.device_packs.registry import DevicePackRegistry
from romverse.device_packs.validation import DevicePackValidationService, ValidationState
from romverse.infrastructure.process import SubprocessRunner
from romverse.infrastructure.provisioning import required_tools_for_source
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.avb_evidence import AvbEvidenceService
from romverse.rom.build_contracts import DeviceBuildContractService, DeviceBuildExecutionPlan
from romverse.rom.build_execution import LocalDeviceBuildExecutor
from romverse.rom.builds import RomBuildPlanner
from romverse.rom.debloat import DebloatService
from romverse.rom.forge import ForgeBundleService
from romverse.rom.inspection import RomInspectionService
from romverse.rom.payloads import PayloadService
from romverse.rom.projects import RomProjectStore
from romverse.rom.recipes import RecipeStore, load_run_receipt
from romverse.rom.recovery_evidence import RecoveryEvidenceService
from romverse.rom.signing_ceremony import OfflineSigningCeremonyService
from romverse.rom.source_blueprint import FastbootSourceBlueprintService
from romverse.rom.source_intelligence import FirmwareSourceIntelligenceService, SourceBlueprint


class GateStatus(StrEnum):
    PASS = "pass"
    ATTENTION = "attention"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class BuildGate:
    gate_id: str
    label: str
    phase: str
    status: GateStatus
    evidence: str
    required_for: str


@dataclass(frozen=True, slots=True)
class GateRemediation:
    """Human-readable, non-bypassing guidance for a readiness gate."""

    summary: str
    fixes: tuple[str, ...]
    action_label: str = ""
    action_id: str = ""

    @property
    def tooltip(self) -> str:
        steps = "\n".join(f"• {fix}" for fix in self.fixes)
        return f"{self.summary}\n\nPossible fixes:\n{steps}"


_GATE_REMEDIATIONS: dict[str, GateRemediation] = {
    "original": GateRemediation(
        "ROMVERSE needs a hashed, immutable firmware source before it can trust later work.",
        (
            "Return to ROM Studio and import the correct stock or custom firmware archive.",
            "Confirm its device, region, and version before accepting the protected copy.",
            "Never edit or extract directly inside the protected original.",
        ),
        "Return to ROM Studio",
        "rom-studio",
    ),
    "inspection": GateRemediation(
        "The bounded structure report is missing, so ROMVERSE has not verified the container layout.",
        (
            "Run Structure inspection from ROM Studio.",
            "If an archive limit is reported, verify the source and review the exact size/entry finding.",
            "Use a supported OTA or firmware container rather than bypassing inspection.",
        ),
        "Return to ROM Studio",
        "rom-studio",
    ),
    "tree": GateRemediation(
        "All modifications require an isolated working tree that is separate from the protected source.",
        (
            "Create the isolated working copy in ROM Studio.",
            "Extract only the verified source into that contained tree.",
            "Keep the protected original immutable for rollback and provenance.",
        ),
        "Return to ROM Studio",
        "rom-studio",
    ),
    "recipe": GateRemediation(
        "A saved mutating Recipe has not produced the matching verified execution receipt.",
        (
            "Open Recipe Forge and review every intended file change.",
            "Run the approved local Recipe so ROMVERSE creates rollback evidence.",
            "Refresh Forge Control after the receipt has been verified.",
        ),
        "Open Recipe Forge",
        "recipe-forge",
    ),
    "plan": GateRemediation(
        "The deterministic build plan is absent or no longer represents the final working tree.",
        (
            "Finish all Recipe changes first.",
            "Generate Plan build (dry-run), then run Verify plan.",
            "Regenerate the plan whenever an input file changes.",
        ),
        "Return to ROM Studio",
        "rom-studio",
    ),
    "tools": GateRemediation(
        "One or more required local build tools are missing or have not been verified.",
        (
            "Open Forge Arsenal and install or locate each named tool.",
            "Allow ROMVERSE to verify the executable version and managed receipt.",
            "Return here and refresh the evidence after installation.",
        ),
        "Open Forge Arsenal",
        "toolchain",
    ),
    "device-pack-build": GateRemediation(
        "ROMVERSE has not yet derived a source-bound local build blueprint from this protected firmware. The blueprint can be created automatically without touching a phone.",
        (
            "Choose Auto-resolve & continue so ROMVERSE inspects payload.bin, sparse super.img, or a partition-image bundle directly.",
            "ROMVERSE will bind available model/build evidence, partition inventory or geometry, hashes, and the local baseline plan to this exact protected source.",
            "Published Device Pack and independent recovery evidence remain separate requirements for physical flashing.",
        ),
        "Run automatic resolution",
        "autopilot",
    ),
    "device-pack-flash": GateRemediation(
        "ROMVERSE has completed the safe local preparation it can prove, but Guardian still needs an exact flash-certified Device Pack before it can create a partition-write manifest.",
        (
            "Open Device Atlas and review the exact model, source, AVB, recovery, and physical-test checks.",
            "Import a valid signed physical-test envelope if an approved ROMVERSE Pack publisher supplied one.",
            "A local rollback capsule or prior successful flash is useful recovery evidence, but cannot replace the signed exact partition-write contract.",
        ),
        "Open Device Atlas",
        "device-packs",
    ),
    "device-build-plan": GateRemediation(
        "The exact Device Pack contract has not yet produced a verified, deterministic local execution plan.",
        (
            "Open Partition Atlas and extract every partition named by the exact contract.",
            "Capture the rebuild partition's ownership/mode and SELinux file-context evidence.",
            "Freeze the final working tree, then select Prepare local build plan in Forge Control.",
        ),
        "Return to ROM Studio",
        "rom-studio",
    ),
    "signer": GateRemediation(
        "ROMVERSE first proves which artifact-trust route applies: preserved OEM bytes, an authorized AVB signing identity, or a source-bound Ascension image for the exact unlocked target.",
        (
            "Let Forge Control compare the candidate with the immutable protected source and inspect AVB topology when a local rebuild exists.",
            "Use Forge Control's Offline signing ceremony only when the exact Device Pack authorizes a flash-validated custom re-chain.",
            "Keep private keys outside ROMVERSE; import only the resulting artifacts so their identity, descriptors, rollback fields, and hashes can be verified.",
        ),
        "Resolve artifact trust automatically",
        "autopilot",
    ),
    "ascension-guardian": GateRemediation(
        "The rooted ROM input is locally sealed, but its exact phone, AVB/slot, recovery, and backup policy still needs Guardian review.",
        (
            "Open Ascension Protocol; ROMVERSE will re-check the exact phone and regenerate its source-bound root plan.",
            "Resolve every visible Guardian check without substituting a generic image, slot, key, or Device Pack.",
            "No root or flash command is produced here, and bootloader relocking remains permanently prohibited.",
        ),
        "Open Ascension Protocol",
        "ascension-protocol",
    ),
    "local-candidate": GateRemediation(
        "Signing can begin only after the exact local candidate has completed byte-for-byte partition verification.",
        (
            "Prepare exact build inputs and save a fresh Device Pack execution plan.",
            "Choose Build verified local candidate in Forge Control.",
            "If a prior attempt failed, review its step log and create a new plan before retrying.",
        ),
        "Open Forge Control",
        "rom-studio",
    ),
    "device": GateRemediation(
        "No authorized live device exactly matches the project Device Pack.",
        (
            "Connect the intended phone with a data-capable USB cable and approve ADB.",
            "Confirm its model and codename match the selected Device Pack.",
            "Refresh Device Center and then refresh this evidence; do not substitute a similar model.",
        ),
        "Open Device Center",
        "device-center",
    ),
    "battery": GateRemediation(
        "ROMVERSE requires current evidence of at least 50% battery before device-changing work.",
        (
            "Charge the connected phone above 50%.",
            "Let the phone cool if it is warm or under heavy load.",
            "Keep it connected and refresh the live evidence.",
        ),
        "Open Device Center",
        "device-center",
    ),
    "boot": GateRemediation(
        "Bootloader and Verified Boot evidence is incomplete; ROMVERSE will not infer a safe state.",
        (
            "Keep the phone unlocked on screen and authorize the current ADB connection.",
            "Refresh Device Center so ROMVERSE can reread the boot evidence.",
            "Do not unlock the bootloader merely to clear this gate; unlocking remains Guardian-locked.",
        ),
        "Open Device Center",
        "device-center",
    ),
    "recovery": GateRemediation(
        "ROMVERSE automatically verifies a local checkpoint plus pristine source-bound partition rollback images.",
        (
            "Create or verify the Time Machine checkpoint automatically.",
            "Verify the protected stock recovery and patch-target images from the exact source.",
            "Keep user-data backup confirmation in the final Guardian handoff; it is not a build failure.",
        ),
        "Open Time Machine",
        "time-machine",
    ),
    "user-backup": GateRemediation(
        "The ROM project and stock partitions are recoverable, but Android backup locations differ by device and provider.",
        (
            "Choose an existing local backup for hash verification, or confirm the completed Google/Xiaomi/OEM cloud backup shown on the phone.",
            "Confirm you can still access the restore account and review photos, contacts, messages, authenticator recovery, and important app data.",
            "ROMVERSE records whether evidence is file-verified or user-confirmed; it never claims to inspect cloud contents.",
        ),
        "Choose backup route",
        "backup-guide",
    ),
    "physical-validation": GateRemediation(
        "The exact Device Pack has not been independently certified for the final write and recovery sequence.",
        (
            "Open Device Atlas and export the exact physical-test challenge when certification is missing.",
            "Import only a signed, unexpired response from a trusted, non-revoked Pack publisher.",
            "ROMVERSE will re-check the Pack, firmware, hardware, AVB policy, recovery scenarios, and signature before this gate can pass.",
        ),
        "Open Device Atlas",
        "device-packs",
    ),
}


def remediation_for(gate: BuildGate) -> GateRemediation:
    """Return stable resolution guidance without weakening the gate itself."""

    return _GATE_REMEDIATIONS.get(
        gate.gate_id,
        GateRemediation(
            "ROMVERSE needs additional verified evidence for this gate.",
            ("Review the evidence shown on the card and refresh after correcting the source.",),
        ),
    )


@dataclass(frozen=True, slots=True)
class BuildReadinessReport:
    schema_version: int
    report_id: str
    project_id: str
    created_at: str
    gates: tuple[BuildGate, ...]
    workspace_ready: bool
    build_ready: bool
    local_candidate_ready: bool
    signing_ready: bool
    flash_ready: bool
    blockers: tuple[str, ...]
    next_actions: tuple[str, ...]
    report_digest: str

    @property
    def guardian_handoff_ready(self) -> bool:
        """True when all automatic work is complete and only human-bound proof remains."""

        if not self.signing_ready:
            return False
        required = {
            "device-pack-flash",
            "device",
            "battery",
            "boot",
            "recovery",
            "ascension-guardian",
        }
        return all(
            gate.status is GateStatus.PASS for gate in self.gates if gate.gate_id in required
        )


@dataclass(frozen=True, slots=True)
class PipelineSimulationReceipt:
    schema_version: int
    simulation_id: str
    project_id: str
    created_at: str
    readiness_digest: str
    stages: tuple[tuple[str, str], ...]
    stopped_at: str
    phone_changed: bool
    success: bool


@dataclass(frozen=True, slots=True)
class BuildEvidenceBundle:
    schema_version: int
    project_id: str
    created_at: str
    artifacts: tuple[tuple[str, str, str], ...]
    toolchain: tuple[tuple[str, str, str], ...]
    evidence_digest: str
    output_path: str


class BuildReadinessService:
    """Evidence-only build/sign/flash gates; it never invokes a build or device tool."""

    REPORT_NAME = "build-readiness.romverse"
    SIMULATION_NAME = "latest-pipeline-simulation.romverse"

    def __init__(
        self,
        store: RomProjectStore,
        registry: DevicePackRegistry,
        tool_statuses: tuple[ToolStatus, ...] = (),
        attestation_store: DevicePackAttestationStore | None = None,
    ) -> None:
        self.store = store
        self.registry = registry
        self.tool_statuses = tool_statuses
        self.attestation_store = attestation_store

    def assess(
        self,
        project_id: str,
        devices: tuple[AndroidDevice, ...] = (),
        *,
        persist: bool = True,
    ) -> BuildReadinessReport:
        project = self.store.get(project_id)
        project_dir = self.store.projects_root / project_id
        inspection = RomInspectionService(self.store)
        report = inspection.load_report(project_id)
        tree = self.store.working_root / project_id / "tree"
        plan = RomBuildPlanner(self.store).load(project_id)
        recipe = RecipeStore().load(project_dir)
        recipe_receipt = (
            load_run_receipt(
                project_dir,
                recipe=recipe,
                tree_root=tree,
                snapshot_root=self.store.snapshots_root / project_id / "recipes",
            )
            if recipe is not None
            else None
        )
        mutating_recipe = recipe is not None and any(
            step.operation != "inspect" for step in recipe.steps
        )
        recipe_applied = not mutating_recipe or bool(
            recipe_receipt
            and recipe_receipt.success
            and recipe_receipt.recipe_digest == recipe.digest()
        )
        pack = next(
            (item for item in self.registry.packs if item.pack_id == project.device_pack_id), None
        )
        firmware_capability = next(
            (
                capability
                for capability in (pack.capabilities if pack else ())
                if "firmware" in capability.capability_id
            ),
            None,
        )
        declared_pack_build_supported = bool(
            firmware_capability
            and firmware_capability.status is CapabilityStatus.SUPPORTED
            and firmware_capability.scope != "locked"
        )
        source_bound_pack = bool(
            pack is not None
            and pack.build_contract is not None
            and project.original is not None
            and project.original.sha256 == pack.build_contract.source.archive_sha256
        )
        source_blueprint = FirmwareSourceIntelligenceService(
            self.store,
            self.tool_statuses,
            SubprocessRunner(),
        ).load(project_id)
        observed_source_contract = source_blueprint is not None
        available_tools = {item.name for item in self.tool_statuses if item.available}
        core_tools = required_tools_for_source(
            pack.build_contract if source_bound_pack and pack is not None else None,
            report.partition_signals if report is not None else (),
        )
        missing_core = tuple(name for name in core_tools if name not in available_tools)
        signer_available = "AVBTool" in available_tools
        status_by_name = {item.name: item for item in self.tool_statuses if item.available}
        avb_evidence = None
        signing_receipt = None
        avb_status = status_by_name.get("AVBTool")
        payload_status = status_by_name.get("Payload Dumper")
        if (
            avb_status is not None
            and avb_status.path
            and payload_status is not None
            and payload_status.path
        ):
            payloads = PayloadService(
                self.store,
                Path(payload_status.path),
                SubprocessRunner(),
            )
            avb_evidence = AvbEvidenceService(
                self.store,
                self.registry,
                self.tool_statuses,
                payloads,
                Path(avb_status.path),
                SubprocessRunner(),
            ).load(project_id)
            signing_receipt = OfflineSigningCeremonyService(
                self.store,
                self.registry,
                self.tool_statuses,
                Path(avb_status.path),
                SubprocessRunner(),
            ).load_receipt(project_id)
        device = next((item for item in devices if item.state is DeviceState.DEVICE), None)
        resolution = self.registry.resolve(device) if device is not None else None
        attestation = (
            self.attestation_store.load_exact(pack, device)
            if self.attestation_store is not None and pack is not None and device is not None
            else None
        )
        validation_report = (
            DevicePackValidationService().assess(pack, device, attestation)
            if pack is not None and device is not None
            else None
        )
        # A live model match proves device identity, not firmware compatibility. Every
        # executable build contract remains bound to its immutable source archive.
        pack_build_supported = bool(
            (declared_pack_build_supported and source_bound_pack) or observed_source_contract
        )
        validation_blockers = (
            tuple(
                check.label
                for check in validation_report.checks
                if check.required_for == "build" and check.state is not ValidationState.PASS
            )
            if validation_report is not None
            else ()
        )
        flash_validation_blockers = (
            tuple(
                check.label
                for check in validation_report.checks
                if check.required_for == "flash" and check.state is not ValidationState.PASS
            )
            if validation_report is not None
            else ()
        )
        pack_flash_supported = bool(
            validation_report is not None and validation_report.flash_contract_ready
        )
        contract_service = DeviceBuildContractService(self.store, self.registry, self.tool_statuses)
        contract_assessment = contract_service.assess(project_id)
        contract_plan = contract_service.load(project_id)
        contract_plan_ready = bool(
            (contract_assessment.ready and contract_plan is not None)
            or (source_blueprint is not None and source_blueprint.baseline_candidate_ready)
        )
        local_candidate = LocalDeviceBuildExecutor(
            self.store,
            self.registry,
            self.tool_statuses,
            SubprocessRunner(),
        ).load_receipt(project_id)
        debloat_receipt = DebloatService(self.store).load_receipt(project_id)
        debloat_mutated = bool(
            debloat_receipt is not None
            and (debloat_receipt.removed_app_count > 0 or not debloat_receipt.keep_all)
        )
        ascension_integration = None
        ascension_build_seal = None
        ascension_root_plan = None
        ascension_manifest = None
        ascension_method = None
        integration_service = RootRomIntegrationService(self.store)
        build_seal_service = RootRomBuildHandoffService(self.store)
        root_plan_service = AscensionRootPlanService(self.store)
        manifest_service = AscensionGuardianManifestService(
            self.store,
            self.registry,
            self.attestation_store,
        )
        for method in AscensionMethod:
            integration = integration_service.load(project_id, method)
            if integration is None:
                continue
            ascension_method = method
            ascension_integration = integration
            ascension_build_seal = build_seal_service.load(project_id, method)
            ascension_root_plan = root_plan_service.load(project_id, method)
            ascension_manifest = manifest_service.load(project_id, method)
            break
        ascension_integrated = ascension_integration is not None
        rooted_candidate_ready = bool(
            ascension_integration is not None
            and ascension_build_seal is not None
            and ascension_build_seal.integration_digest == ascension_integration.integration_digest
        )
        source_baseline_candidate = bool(
            source_blueprint is not None
            and source_blueprint.baseline_candidate_ready
            and not mutating_recipe
            and not debloat_mutated
            and not ascension_integrated
        )
        # A source-baseline candidate is the immutable OEM artifact itself, not a
        # rebuilt or re-signed output. An older local-build receipt may still be on
        # disk after the user returns to the unmodified route; it is not the selected
        # candidate in that state. Prefer the protected source and its preserved OEM
        # signature whenever Recipe, Debloat, and Ascension all report no mutation.
        # Do not route that state into the custom-candidate AVB signer, which requires
        # a pre-authored Device Pack.
        oem_signature_preserved = source_baseline_candidate
        exact_pack = bool(
            device
            and resolution
            and resolution.pack
            and resolution.pack.pack_id == project.device_pack_id
            and project.device_pack_id
        )
        blueprint_codename = str(getattr(source_blueprint, "codename", "")).casefold().strip()
        blueprint_manufacturer = (
            str(getattr(source_blueprint, "manufacturer", "")).casefold().strip()
        )
        blueprint_exact_target = bool(
            device
            and source_blueprint is not None
            and blueprint_codename
            and device.codename.casefold().strip() == blueprint_codename
            and (
                not blueprint_manufacturer
                or not device.manufacturer
                or device.manufacturer.casefold().strip() == blueprint_manufacturer
            )
        )
        exact_target = exact_pack or blueprint_exact_target
        rooted_artifact_policy_ready = bool(
            rooted_candidate_ready
            and ascension_root_plan is not None
            and ascension_build_seal is not None
            and device is not None
            and device.bootloader_locked is False
            and root_plan_service.matches_device(ascension_root_plan, device)
            and ascension_root_plan.target_partition == ascension_build_seal.target_partition
            and ascension_root_plan.root_image_artifact_sha256
            == ascension_build_seal.artifact_sha256
        )
        ascension_guardian_ready = bool(
            rooted_candidate_ready
            and ascension_method is not None
            and ascension_manifest is not None
            and ascension_manifest.review_ready
            and device is not None
            and manifest_service.matches_device(ascension_manifest, device)
        )
        battery_ready = bool(
            device and device.battery_percent is not None and device.battery_percent >= 50
        )
        boot_evidence = bool(
            device and device.bootloader_locked is not None and device.verified_boot
        )
        local_snapshot = any(
            snapshot.schema_version == 2 for snapshot in self.store.list_snapshots(project_id)
        )
        recovery_evidence = RecoveryEvidenceService(self.store).assess(project_id, device)
        backup_handoff = BackupHandoffService(self.store).load(project_id, device)
        ascension_rollback = AscensionEvidenceService(self.store).load(project_id)
        local_flash_preflight = bool(
            source_blueprint is not None and exact_target and ascension_rollback is not None
        )
        user_recovery_ready = local_snapshot and recovery_evidence.ready
        automatic_recovery_ready = bool(
            local_snapshot
            and ascension_rollback is not None
            and ascension_rollback.stock_recovery is not None
        )

        gates = (
            _gate(
                "original",
                "Protected original",
                "Workspace",
                project.original is not None,
                "Source hash and immutable workspace copy recorded"
                if project.original
                else "No protected original",
                "build",
            ),
            _gate(
                "inspection",
                "Structure inspection",
                "Workspace",
                report is not None,
                "Bounded container report saved" if report else "Inspection report missing",
                "build",
            ),
            _gate(
                "tree",
                "Contained working tree",
                "Workspace",
                tree.is_dir(),
                str(tree) if tree.is_dir() else "Working tree missing",
                "build",
            ),
            _gate(
                "recipe",
                "Recipe result",
                "Workspace",
                recipe_applied,
                "No unapplied changes"
                if recipe_applied
                else "Saved mutating Recipe has no matching verified receipt",
                "build",
            ),
            _gate(
                "plan",
                "Deterministic build plan",
                "Build",
                plan is not None,
                "Plan artifact recorded"
                if plan
                else "Create a build plan after final Recipe changes",
                "build",
            ),
            BuildGate(
                "tools",
                "Resolved source toolchain",
                "Build",
                GateStatus.PASS
                if self.tool_statuses and not missing_core
                else GateStatus.ATTENTION,
                f"{len(core_tools)} source-scoped tool checks passed: " + ", ".join(core_tools)
                if self.tool_statuses and not missing_core
                else (
                    "Refresh Forge Arsenal to verify: " + ", ".join(core_tools)
                    if not self.tool_statuses
                    else "Missing: " + ", ".join(missing_core)
                ),
                "build",
            ),
            BuildGate(
                "device-pack-build",
                "Device Pack build contract",
                "Build",
                GateStatus.PASS if pack_build_supported else GateStatus.BLOCKED,
                (
                    f"Source-bound {source_blueprint.source_kind} blueprint derived and verified locally"
                    if observed_source_contract
                    else "Exact source-bound contract verified offline by Device Atlas"
                    if source_bound_pack
                    else "Exact model contract verified by Device Atlas"
                    if pack_build_supported
                    else "Exact source contract required: "
                    + (
                        ", ".join(validation_blockers)
                        if validation_blockers
                        else "the protected archive SHA-256 does not match this Device Pack"
                    )
                ),
                "build",
            ),
            BuildGate(
                "device-build-plan",
                "Deterministic source/build plan",
                "Build",
                GateStatus.PASS if contract_plan_ready else GateStatus.BLOCKED,
                (
                    _source_blueprint_plan_evidence(source_blueprint)
                    if source_blueprint is not None and source_blueprint.baseline_candidate_ready
                    else f"Plan {contract_plan.plan_digest[:16]}… binds exact source, partitions, metadata, and outputs"
                    if contract_plan_ready and contract_plan is not None
                    else "Contract preparation required: "
                    + ", ".join(contract_assessment.blockers or ("save the execution plan",))
                ),
                "build",
            ),
            BuildGate(
                "local-candidate",
                "Verified local candidate",
                "Signing",
                GateStatus.PASS
                if local_candidate is not None
                or source_baseline_candidate
                or rooted_candidate_ready
                else GateStatus.BLOCKED,
                (
                    f"Ascension Build Seal {ascension_build_seal.handoff_digest[:16]}… binds rooted {ascension_build_seal.target_partition} {ascension_build_seal.artifact_sha256[:16]}… to the protected source"
                    if rooted_candidate_ready and ascension_build_seal is not None
                    else f"Protected baseline {source_blueprint.candidate_sha256[:16]}… selected; no Recipe, Debloat, or Ascension mutations require a rebuild"
                    if source_baseline_candidate and source_blueprint is not None
                    else f"Build receipt {local_candidate.receipt_digest[:16]}… binds verified product, vbmeta_system, and super outputs"
                    if local_candidate is not None
                    else "No current successful local build receipt"
                ),
                "signing",
            ),
            BuildGate(
                "signer",
                "Artifact trust and AVB policy",
                "Signing",
                GateStatus.PASS
                if (
                    (avb_evidence is not None and avb_evidence.signing_ready)
                    or signing_receipt is not None
                    or oem_signature_preserved
                    or rooted_artifact_policy_ready
                    or (
                        source_baseline_candidate
                        and source_blueprint is not None
                        and source_blueprint.avb_topology_verified
                    )
                )
                else GateStatus.ATTENTION
                if signer_available
                else GateStatus.BLOCKED,
                (
                    f"Ascension Build Seal verified for rooted {ascension_build_seal.target_partition}; exact unlocked target is bound and OEM re-signing is not claimed"
                    if rooted_artifact_policy_ready and ascension_build_seal is not None
                    else "Protected OEM-signed source is byte-identical; no local mutation or re-signing action is required"
                    if oem_signature_preserved
                    else (
                        f"Offline signing receipt {signing_receipt.receipt_digest[:16]}… verifies exact Device Pack identity and AVB policy"
                        if signing_receipt is not None
                        else avb_evidence.diagnosis
                    )
                    if avb_evidence is not None or signing_receipt is not None
                    else "Protected baseline AVB topology verified; no Recipe mutation requires re-signing"
                    if (
                        source_baseline_candidate
                        and source_blueprint is not None
                        and source_blueprint.avb_topology_verified
                    )
                    else "AVBTool found; inspect source/candidate topology and provide an authorized identity"
                    if signer_available
                    else "AVBTool, signing identity, and device-specific descriptors are unavailable"
                ),
                "signing",
            ),
            *(
                (
                    BuildGate(
                        "ascension-guardian",
                        "Ascension Guardian policy",
                        "Recovery",
                        GateStatus.PASS if ascension_guardian_ready else GateStatus.ATTENTION,
                        (
                            f"Ascension manifest {ascension_manifest.manifest_digest[:16]}… is ready for exact-device review; commands: NONE; bootloader relock: PROHIBITED"
                            if ascension_guardian_ready and ascension_manifest is not None
                            else "Rooted build input is sealed; complete the exact phone, AVB/slot, recovery, and backup review in Ascension Protocol"
                        ),
                        "flash",
                    ),
                )
                if ascension_integrated
                else ()
            ),
            BuildGate(
                "device-pack-flash",
                "Device Pack flash and recovery contract",
                "Recovery",
                GateStatus.PASS
                if pack_flash_supported
                else GateStatus.ATTENTION
                if local_flash_preflight
                else GateStatus.BLOCKED,
                (
                    "Independent model-specific recovery and failure-path evidence is signed into the Device Pack"
                    if pack_flash_supported
                    else f"Safe local preparation is complete: {source_blueprint.source_kind}, live {device.codename}, AVB/build evidence, and pristine rollback capsule {ascension_rollback.record_digest[:16]}…. The exact signed partition-write contract is still missing; Guardian handoff remains locked"
                    if local_flash_preflight
                    and source_blueprint is not None
                    and device is not None
                    and ascension_rollback is not None
                    else "Device Atlas flash validation required: "
                    + (
                        ", ".join(flash_validation_blockers)
                        if flash_validation_blockers
                        else "connect the exact target and validate a flash-certified Pack"
                    )
                ),
                "flash",
            ),
            _gate(
                "device",
                "Exact authorized target",
                "Flash",
                exact_target,
                (
                    f"{device.display_name} ({device.codename}) matches the source-bound local blueprint"
                    if blueprint_exact_target and device
                    else device.display_name
                )
                if exact_target and device
                else "No authorized device matching the project Device Pack",
                "flash",
            ),
            _gate(
                "battery",
                "Battery safety margin",
                "Flash",
                battery_ready,
                f"{device.battery_percent}%"
                if device and device.battery_percent is not None
                else "Require at least 50% with live evidence",
                "flash",
            ),
            _gate(
                "boot",
                "Boot-state evidence",
                "Flash",
                boot_evidence,
                "Bootloader and Verified Boot evidence available"
                if boot_evidence
                else "Bootloader / Verified Boot evidence incomplete",
                "flash",
            ),
            BuildGate(
                "recovery",
                "Recovery evidence",
                "Recovery",
                GateStatus.PASS
                if user_recovery_ready or automatic_recovery_ready
                else GateStatus.ATTENTION
                if local_snapshot
                or recovery_evidence.external_backup_ready
                or recovery_evidence.stock_recovery_ready
                else GateStatus.BLOCKED,
                (
                    "Local checkpoint, external backup, and stock-recovery package are present and unchanged"
                    if user_recovery_ready
                    else f"Automatic recovery contract complete: Time Machine checkpoint plus exact pristine patch target and stock recovery from Ascension capsule {ascension_rollback.record_digest[:16]}…"
                    if automatic_recovery_ready and ascension_rollback is not None
                    else (
                        "Local checkpoint: present; "
                        if local_snapshot
                        else "Local checkpoint: missing; "
                    )
                    + (
                        f"automatic pristine partition rollback: {ascension_rollback.record_digest[:16]}…; "
                        if ascension_rollback is not None
                        else "automatic pristine partition rollback: missing; "
                    )
                    + "; ".join(recovery_evidence.evidence)
                ),
                "flash",
            ),
            BuildGate(
                "user-backup",
                "Final user-data backup confirmation",
                "Guardian",
                GateStatus.PASS
                if recovery_evidence.external_backup_ready or backup_handoff is not None
                else GateStatus.ATTENTION,
                "Independently readable external phone backup is registered"
                if recovery_evidence.external_backup_ready
                else f"User-confirmed {backup_handoff.provider} backup • {backup_handoff.last_backup_label} • cloud contents not inspected by ROMVERSE"
                if backup_handoff is not None
                else "Project and stock-partition rollback are ready; choose a local backup or confirm the phone's completed cloud backup at final handoff",
                "flash",
            ),
            BuildGate(
                "physical-validation",
                "Operation and release scope",
                "Guardian",
                GateStatus.PASS
                if pack_flash_supported
                else GateStatus.ATTENTION
                if local_flash_preflight
                else GateStatus.BLOCKED,
                "Independent signed physical recovery-test evidence is active"
                if pack_flash_supported
                else "Local source, target, and rollback evidence is prepared, but it cannot certify the exact partition-write sequence or physical recovery outcomes"
                if local_flash_preflight
                else "No exact local operation scope or public release certification is available",
                "release",
            ),
        )
        workspace_ready = all(
            gate.status is GateStatus.PASS for gate in gates if gate.phase == "Workspace"
        )
        build_ready = workspace_ready and all(
            gate.status is GateStatus.PASS for gate in gates if gate.phase == "Build"
        )
        local_candidate_ready = bool(
            local_candidate is not None or source_baseline_candidate or rooted_candidate_ready
        )
        signing_ready = build_ready and all(
            gate.status is GateStatus.PASS for gate in gates if gate.phase == "Signing"
        )
        flash_ready = signing_ready and all(
            gate.status is GateStatus.PASS for gate in gates if gate.required_for == "flash"
        )
        blockers = tuple(gate.label for gate in gates if gate.status is GateStatus.BLOCKED)
        next_actions = tuple(
            remediation_for(gate).fixes[0] for gate in gates if gate.status is not GateStatus.PASS
        )
        payload = {
            "schema_version": 1,
            "report_id": uuid4().hex,
            "project_id": project_id,
            "created_at": datetime.now(UTC).isoformat(),
            "gates": [asdict(gate) for gate in gates],
            "workspace_ready": workspace_ready,
            "build_ready": build_ready,
            "local_candidate_ready": local_candidate_ready,
            "signing_ready": signing_ready,
            "flash_ready": flash_ready,
            "blockers": blockers,
            "next_actions": next_actions,
        }
        digest = _digest(payload)
        result = BuildReadinessReport(
            1,
            str(payload["report_id"]),
            project_id,
            str(payload["created_at"]),
            gates,
            workspace_ready,
            build_ready,
            local_candidate_ready,
            signing_ready,
            flash_ready,
            blockers,
            next_actions,
            digest,
        )
        if persist:
            _write_json(
                project_dir / self.REPORT_NAME,
                {"format": "romverse.build-readiness", **asdict(result)},
            )
        return result

    def prepare_device_build_plan(self, project_id: str) -> DeviceBuildExecutionPlan:
        """Create a validated local execution plan; no build tool or device command is run."""

        return DeviceBuildContractService(
            self.store, self.registry, self.tool_statuses
        ).create_plan(project_id)

    def simulate(self, report: BuildReadinessReport) -> PipelineSimulationReceipt:
        stages: list[tuple[str, str]] = []
        stopped_at = "complete"
        for phase in ("Workspace", "Build", "Signing", "Recovery", "Flash"):
            phase_gates = tuple(gate for gate in report.gates if gate.phase == phase)
            if not phase_gates:
                continue
            status = (
                "blocked"
                if any(gate.status is GateStatus.BLOCKED for gate in phase_gates)
                else "attention"
                if any(gate.status is GateStatus.ATTENTION for gate in phase_gates)
                else "pass"
            )
            stages.append((phase, status))
            if status == "blocked":
                stopped_at = phase
                break
        receipt = PipelineSimulationReceipt(
            1,
            uuid4().hex,
            report.project_id,
            datetime.now(UTC).isoformat(),
            report.report_digest,
            tuple(stages),
            stopped_at,
            False,
            stopped_at == "complete",
        )
        _write_json(
            self.store.projects_root / report.project_id / self.SIMULATION_NAME,
            {"format": "romverse.pipeline-simulation", **asdict(receipt)},
        )
        return receipt

    def export_evidence_bundle(self, report: BuildReadinessReport) -> BuildEvidenceBundle:
        """Package small provenance manifests without copying or rebuilding firmware."""

        project_dir = self.store.projects_root / report.project_id
        recipe = RecipeStore().load(project_dir)
        recipe_receipt = (
            load_run_receipt(
                project_dir,
                recipe=recipe,
                tree_root=self.store.working_root / report.project_id / "tree",
                snapshot_root=self.store.snapshots_root / report.project_id / "recipes",
            )
            if recipe is not None
            else None
        )
        candidates = (
            ("project", project_dir / self.store.MANIFEST_NAME),
            ("inspection", project_dir / "inspection.romverse"),
            ("build-plan", project_dir / RomBuildPlanner.PLAN_NAME),
            ("recipe", project_dir / RecipeStore.NAME),
            ("recipe-receipt", project_dir / "latest-recipe-receipt.romverse"),
            ("payload", project_dir / "payload-manifest.romverse"),
            ("readiness", project_dir / self.REPORT_NAME),
            ("forge-bundle", project_dir / ForgeBundleService.RECEIPT_NAME),
            ("device-build-plan", project_dir / DeviceBuildContractService.PLAN_NAME),
            (
                "source-blueprint",
                project_dir / FastbootSourceBlueprintService.NAME,
            ),
            (
                "ota-source-blueprint",
                project_dir / FirmwareSourceIntelligenceService.OTA_NAME,
            ),
            (
                "partition-bundle-blueprint",
                project_dir / FirmwareSourceIntelligenceService.BUNDLE_NAME,
            ),
            ("local-build-attempt", project_dir / LocalDeviceBuildExecutor.ATTEMPT_NAME),
            ("recovery-evidence", project_dir / RecoveryEvidenceService.RECEIPT_NAME),
            ("avb-topology", project_dir / AvbEvidenceService.RECEIPT_NAME),
        )
        artifacts: list[tuple[str, str, str]] = []
        for label, path in candidates:
            if label == "recipe-receipt" and recipe_receipt is None:
                continue
            if path.is_file() and path.is_relative_to(project_dir):
                artifacts.append(
                    (label, path.relative_to(self.store.workspace).as_posix(), _sha256(path))
                )
        filesystem_root = project_dir / "filesystems"
        for path in sorted(filesystem_root.glob("*.romverse")) if filesystem_root.is_dir() else ():
            artifacts.append(
                (
                    f"filesystem:{path.stem}",
                    path.relative_to(self.store.workspace).as_posix(),
                    _sha256(path),
                )
            )
        toolchain = tuple(
            sorted(
                (
                    item.name,
                    item.version or "unknown",
                    item.path if item.available else "unavailable",
                )
                for item in self.tool_statuses
            )
        )
        evidence_payload = {
            "project_id": report.project_id,
            "artifacts": artifacts,
            "toolchain": toolchain,
        }
        evidence_digest = _digest(evidence_payload)
        output_root = self.store.workspace / "builds" / report.project_id
        output_root.mkdir(parents=True, exist_ok=True)
        output = output_root / f"evidence-{evidence_digest[:16]}.romverse"
        bundle = BuildEvidenceBundle(
            1,
            report.project_id,
            datetime.now(UTC).isoformat(),
            tuple(artifacts),
            toolchain,
            evidence_digest,
            output.relative_to(self.store.workspace).as_posix(),
        )
        _write_json(output, {"format": "romverse.build-evidence", **asdict(bundle)})
        return bundle


def _gate(
    gate_id: str,
    label: str,
    phase: str,
    passed: bool,
    evidence: str,
    required_for: str,
) -> BuildGate:
    return BuildGate(
        gate_id,
        label,
        phase,
        GateStatus.PASS if passed else GateStatus.BLOCKED,
        evidence,
        required_for,
    )


def _source_blueprint_plan_evidence(blueprint: SourceBlueprint) -> str:
    digest = blueprint.plan_digest[:16]
    partition_count = len(blueprint.partitions)
    if blueprint.source_kind == "ota-payload":
        return (
            f"Plan {digest}… binds the protected source, payload hash, and "
            f"{partition_count}-partition OTA baseline"
        )
    if blueprint.source_kind == "fastboot-super":
        return f"Plan {digest}… binds the exact fastboot super geometry and baseline"
    if blueprint.source_kind == "partition-bundle":
        return (
            f"Plan {digest}… binds the protected source and hash-backed "
            f"{partition_count}-image baseline inventory"
        )
    return f"Plan {digest}… binds the current {blueprint.source_kind} baseline evidence"


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)
