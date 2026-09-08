from __future__ import annotations

import json
import os
import re
import shutil
from contextlib import suppress
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path, PurePosixPath

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from romverse.ascension.build_handoff import RootRomBuildHandoffService
from romverse.ascension.integration import RootRomIntegrationService
from romverse.ascension.models import AscensionMethod
from romverse.ascension.planning import AscensionRootPlanService
from romverse.core.settings import AppSettings, ExperienceMode
from romverse.device.adb import AdbClient
from romverse.device.dna import CapabilityState, DeviceDnaProfile, DeviceDnaService
from romverse.device.fastboot import FastbootClient
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.attestations import DevicePackAttestationStore
from romverse.device_packs.registry import DevicePackRegistry
from romverse.device_packs.validation import DevicePackValidationReport
from romverse.guardian.approval import ApprovalStore
from romverse.guardian.artifact_binding import GuardianArtifactBindingService
from romverse.guardian.execution_gateway_contract import (
    GuardianExecutionGatewayContract,
    GuardianExecutionGatewayContractService,
    execution_plan_matches_manifest,
    gateway_contract_matches_plan,
)
from romverse.guardian.execution_plan import (
    GuardianExecutionPlan,
    GuardianExecutionPlanService,
)
from romverse.guardian.execution_result_receipt import VerifiedGuardianExecutionResult
from romverse.guardian.flash_handoff import GuardianFlashHandoffService
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.live_target_receipt import GuardianLiveTargetReceiptService
from romverse.guardian.manifest_review import (
    GuardianManifestReview,
    GuardianManifestReviewService,
)
from romverse.infrastructure.process import SubprocessRunner
from romverse.infrastructure.provisioning import required_tools_for_source
from romverse.infrastructure.tools import ToolStatus, ToolVerifier
from romverse.intelligence.online_remediation import OnlineFixReceipt, SourceAuthority
from romverse.knowledge.models import KnowledgeFailure
from romverse.nexus.compatibility import CompatibilityMatrix, CompatibilityMatrixService
from romverse.nexus.planning import NexusPlanStore
from romverse.platform.host import current_host
from romverse.rom.avb_evidence import SourceAvbEvidenceService, SourceAvbTopologyReceipt
from romverse.rom.boot_observation import BootObservationService, BootObservationStatus
from romverse.rom.builds import BuildPlan, RomBuildPlanner
from romverse.rom.debloat import DebloatService
from romverse.rom.dna import DnaStore, derive_dna
from romverse.rom.external_intake import (
    ExternalFirmwareIntakeReceipt,
    ExternalFirmwareIntakeService,
)
from romverse.rom.filesystems import FilesystemManifest, PartitionFilesystemService
from romverse.rom.forge import ForgeBundleReceipt, ForgeBundleService
from romverse.rom.guided import (
    STAGES,
    GenesisFlightPlan,
    GuidedContext,
    GuidedMissionEngine,
    GuidedMissionState,
    GuidedMissionStore,
    GuidedStageStatus,
)
from romverse.rom.inspection import RomInspectionReport, RomInspectionService
from romverse.rom.models import (
    ArtifactVerification,
    ProjectError,
    RomProject,
    TimeMachineSnapshot,
    WorkingCopy,
)
from romverse.rom.payloads import PayloadManifest, PayloadService
from romverse.rom.project_flash import ProjectFlashOutcome, ProjectFlashPreparationService
from romverse.rom.projects import RomProjectStore
from romverse.rom.readiness import BuildReadinessService
from romverse.rom.recipes import (
    ExecutionReceipt,
    RecipeExecutor,
    RecipePreview,
    RecipeRollbackReceipt,
    RecipeRunReceipt,
    RecipeStep,
    RecipeStore,
    RomRecipe,
    load_run_receipt,
    preview_recipe,
    save_rollback_receipt,
    save_run_receipt,
)
from romverse.rom.source_identity import identify_firmware_source
from romverse.rom.source_installation_history import (
    SourceInstallationOutcome,
    load_latest_source_installation,
)
from romverse.rom.source_intelligence import FirmwareSourceIntelligenceService
from romverse.rom.upgrade import (
    USER_FIRMWARE_RESPONSIBILITY_NOTICE,
    FirmwareRelationship,
    ProjectFirmwareUpgradeReview,
    assess_project_firmware_upgrade,
)
from romverse.rom.workspace_recovery import WorkspaceRecoveryReport, WorkspaceRecoveryService
from romverse.ui.background import (
    CoalescedProgress,
    ManagedRunnable,
    measured_percent,
    start_background,
)
from romverse.ui.formatters import human_bytes
from romverse.ui.process_progress import ProcessProgressBar


class ProjectWorkerSignals(QObject):
    progress = Signal(int)
    recovery = Signal(object)
    complete = Signal(object)
    failed = Signal(str)


@dataclass(frozen=True, slots=True)
class FirmwareImportResult:
    project: RomProject
    inspection: RomInspectionReport


class ProjectWorker(ManagedRunnable):
    def __init__(
        self,
        store: RomProjectStore,
        operation: str,
        project_id: str,
        source: Path | None = None,
        inspection: RomInspectionService | None = None,
        payload_service: PayloadService | None = None,
        filesystem_service: PartitionFilesystemService | None = None,
        partitions: tuple[str, ...] = (),
        source_avb_service: SourceAvbEvidenceService | None = None,
        tool_statuses: tuple[ToolStatus, ...] = (),
        required_tools: tuple[str, ...] = (),
    ) -> None:
        super().__init__()
        self.store = store
        self.operation = operation
        self.project_id = project_id
        self.source = source
        self.inspection = inspection
        self.payload_service = payload_service
        self.filesystem_service = filesystem_service
        self.partitions = partitions
        self.source_avb_service = source_avb_service
        self.tool_statuses = tool_statuses
        self.required_tools = required_tools
        self.signals = ProjectWorkerSignals()

    @Slot()
    def execute(self) -> None:
        emit_progress = CoalescedProgress(self.signals.progress.emit)

        def progress(done: int, total: int) -> None:
            percent = measured_percent(done, total)
            if percent is not None:
                emit_progress(percent)

        try:
            recovery = WorkspaceRecoveryService(self.store.workspace).recover(
                self.project_id,
                stale_after_seconds=0,
            )
            if recovery.recovered_count or recovery.blocked_paths:
                self.signals.recovery.emit(recovery)
            if self.operation == "import" and self.source is not None:

                def publish_import_copy(done: int, total: int) -> None:
                    if total > 0 and done < total:
                        progress(done, total)

                imported = self.store.import_original(
                    self.project_id,
                    self.source,
                    progress=publish_import_copy,
                )
                if self.inspection is None:
                    raise ProjectError("Automatic firmware detection is unavailable")
                report = self.inspection.inspect_project(self.project_id)
                emit_progress(100)
                result = FirmwareImportResult(imported, report)
            elif self.operation == "external-intake" and self.source is not None:
                result = ExternalFirmwareIntakeService(self.store).inspect(
                    self.project_id,
                    self.source,
                    progress=progress,
                )
            elif self.operation == "verify":
                result = self.store.verify_original(self.project_id, progress=progress)
            elif self.operation == "inspect" and self.inspection is not None:
                result = self.inspection.inspect_project(self.project_id, progress=progress)
            elif self.operation == "working-copy":
                result = self.store.create_working_copy(self.project_id, progress=progress)
            elif self.operation == "snapshot":
                result = self.store.create_snapshot(self.project_id, progress=progress)
            elif self.operation == "extract" and self.inspection is not None:
                result = self.inspection.extract_project_tree(
                    self.project_id,
                    progress=progress,
                )
            elif self.operation == "plan" and self.inspection is not None:
                result = RomBuildPlanner(
                    self.store,
                    self.tool_statuses,
                    self.required_tools,
                ).plan(self.project_id)
            elif self.operation == "verify-plan":
                result = RomBuildPlanner(
                    self.store,
                    self.tool_statuses,
                    self.required_tools,
                ).verify_tree(self.project_id)
            elif self.operation == "forge-bundle":
                forge = ForgeBundleService(self.store, self.tool_statuses)
                result = forge.create(
                    self.project_id,
                    progress=lambda done, total: emit_progress(
                        85 if not total or done >= total else max(0, min(84, done * 85 // total))
                    ),
                )
                verification = forge.verify(
                    self.project_id,
                    progress=lambda done, total: emit_progress(
                        100
                        if not total or done >= total
                        else max(85, min(99, 85 + done * 15 // total))
                    ),
                )
                if not verification.valid:
                    raise ProjectError(verification.status)
            elif self.operation == "verify-forge":
                result = ForgeBundleService(self.store).verify(self.project_id)
            elif self.operation == "scan-payload" and self.payload_service is not None:
                result = self.payload_service.scan(self.project_id, progress=progress)
            elif self.operation == "extract-payload" and self.payload_service is not None:
                result = self.payload_service.extract(
                    self.project_id, self.partitions, progress=progress
                )
            elif self.operation == "expand-filesystem" and self.filesystem_service is not None:
                if len(self.partitions) != 1:
                    raise ProjectError("Choose one partition filesystem to expand")
                result = self.filesystem_service.expand(self.project_id, self.partitions[0])
            elif self.operation == "inspect-source-avb" and self.source_avb_service is not None:
                result = self.source_avb_service.inspect(self.project_id)
            elif self.operation == "preview-recipe":
                recipe = RecipeStore().load(self.store.projects_root / self.project_id)
                tree = self.store.working_root / self.project_id / "tree"
                if recipe is None or not tree.is_dir():
                    raise ProjectError("Save a recipe and extract a working tree before previewing")
                result = RecipeExecutor().execute(recipe, tree)
            elif self.operation == "replace-file":
                recipe = RecipeStore().load(self.store.projects_root / self.project_id)
                tree = self.store.working_root / self.project_id / "tree"
                if recipe is None or self.source is None:
                    raise ProjectError("A recipe and replacement source are required")
                ApprovalStore(self.store.workspace).issue(recipe.digest(), recipe.steps[0].target)
                result = RecipeExecutor().apply_replace_file(
                    recipe,
                    tree,
                    self.store.snapshots_root / self.project_id / "rollback",
                    True,
                    recipe.digest(),
                )
            elif self.operation == "set-property":
                recipe = RecipeStore().load(self.store.projects_root / self.project_id)
                tree = self.store.working_root / self.project_id / "tree"
                if recipe is None:
                    raise ProjectError("A property recipe is required")
                ApprovalStore(self.store.workspace).issue(recipe.digest(), recipe.steps[0].target)
                result = RecipeExecutor().apply_set_property(
                    recipe,
                    tree,
                    self.store.snapshots_root / self.project_id / "rollback",
                    True,
                    recipe.digest(),
                )
                (self.store.projects_root / self.project_id / "execution-receipt.json").write_text(
                    json.dumps({"format": "romverse.execution-receipt", **asdict(result)}, indent=2)
                    + "\n",
                    encoding="utf-8",
                )
            elif self.operation == "execute-recipe":
                recipe = RecipeStore().load(self.store.projects_root / self.project_id)
                tree = self.store.working_root / self.project_id / "tree"
                if recipe is None or not tree.is_dir():
                    raise ProjectError("A saved recipe and extracted working tree are required")
                executor = RecipeExecutor()
                approval = executor.issue_approval(recipe, tree)
                ApprovalStore(self.store.workspace).issue(recipe.digest(), self.project_id)

                def publish_recipe_steps(done: int, total: int) -> None:
                    if total > 0 and done < total:
                        progress(done, total)

                result = executor.execute_approved(
                    recipe,
                    tree,
                    self.store.snapshots_root / self.project_id / "recipes",
                    approval,
                    publish_recipe_steps,
                )
                save_run_receipt(
                    self.store.projects_root / self.project_id,
                    result,
                    recipe=recipe,
                    tree_root=tree,
                    snapshot_root=self.store.snapshots_root / self.project_id / "recipes",
                )
                emit_progress(100)
            elif self.operation == "rollback-recipe" and self.source is not None:
                tree = self.store.working_root / self.project_id / "tree"
                snapshot = RecipeExecutor.load_snapshot(self.source)
                if snapshot is None:
                    raise ProjectError("Selected recipe snapshot failed integrity verification")
                ApprovalStore(self.store.workspace).issue(snapshot.snapshot_digest, self.project_id)
                result = RecipeExecutor().rollback(tree, snapshot, snapshot.snapshot_digest)
                save_rollback_receipt(self.store.projects_root / self.project_id, result)
            elif self.operation == "rollback-plan":
                raise ProjectError("Select a snapshot before generating a rollback plan")
            else:
                raise ProjectError("Unknown project worker operation")
            self.signals.complete.emit(result)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class GuardianReviewWorker(ManagedRunnable):
    """Rehash review artifacts outside Qt's UI thread, then seal a command-free review."""

    def __init__(
        self,
        binding_service: GuardianArtifactBindingService,
        manifest_service: GuardianManifestReviewService,
        project_id: str,
        report,
        device: AndroidDevice,
    ) -> None:
        super().__init__()
        self.binding_service = binding_service
        self.manifest_service = manifest_service
        self.project_id = project_id
        self.report = report
        self.device = device
        self.signals = ProjectWorkerSignals()
        self.execution_plan: GuardianExecutionPlan | None = None
        self.gateway_contract: GuardianExecutionGatewayContract | None = None

    @Slot()
    def execute(self) -> None:
        emit_progress = CoalescedProgress(self.signals.progress.emit)
        binding = None
        binding_error = ""
        try:
            handoffs = GuardianFlashHandoffService(self.binding_service.store)
            handoff = handoffs.load(self.project_id)
            if handoff is None or not handoffs.matches_current(
                self.project_id,
                handoff,
                self.device,
                self.report,
            ):
                raise ProjectError(
                    "Prepare a fresh current Guardian keep-data or wipe-data handoff first"
                )
            project = self.binding_service.store.get(self.project_id)
            pack = next(
                (
                    item
                    for item in self.binding_service.registry.packs
                    if item.pack_id == project.device_pack_id
                ),
                None,
            )
            write_contract = (
                pack.build_contract.partition_write_contract
                if pack is not None and pack.build_contract is not None
                else None
            )
            rehash_passes = (
                1
                + int(write_contract is not None)
                + int(
                    write_contract is not None
                    and write_contract.post_write_verification_contract is not None
                )
            )

            def publish_rehash_progress(phase: int, value: int) -> None:
                measured = round((phase * 100 + max(0, min(100, int(value)))) / rehash_passes)
                if measured < 100:
                    emit_progress(measured)

            try:

                def publish_binding_progress(value: int) -> None:
                    publish_rehash_progress(0, value)

                binding = self.binding_service.prepare(
                    self.project_id,
                    publish_binding_progress,
                )
            except (OSError, ProjectError) as exc:
                binding_error = str(exc)
            manifest = self.manifest_service.compile(
                self.project_id,
                self.report,
                self.device,
                binding=binding,
                binding_error=binding_error,
            )
            if manifest.partition_writes:
                plan_service = GuardianExecutionPlanService(
                    self.binding_service.store,
                    self.binding_service.registry,
                    self.binding_service.tool_statuses,
                    self.binding_service.avbtool,
                    self.binding_service.runner,
                )
                self.execution_plan = plan_service.compile(
                    self.project_id,
                    self.report,
                    self.device,
                    lambda value: publish_rehash_progress(1, value),
                )
                if self.execution_plan.post_write_verification_contract_version:
                    self.gateway_contract = GuardianExecutionGatewayContractService(
                        self.binding_service.store,
                        self.binding_service.registry,
                        self.binding_service.tool_statuses,
                        self.binding_service.avbtool,
                        self.binding_service.runner,
                    ).compile(
                        self.project_id,
                        self.report,
                        self.device,
                        lambda value: publish_rehash_progress(2, value),
                    )
            emit_progress(100)
            self.signals.complete.emit(manifest)
        except (OSError, ProjectError) as exc:
            self.signals.failed.emit(str(exc))


def confirm_expert_mode(parent: QWidget | None = None) -> bool:
    """Require a deliberate acknowledgement before revealing unrestricted expert surfaces."""

    dialog = QMessageBox(parent)
    dialog.setWindowTitle("ROMVERSE • enter Expert Mode?")
    dialog.setIcon(QMessageBox.Icon.Warning)
    dialog.setText("Expert Mode removes Guided Setup's automatic safety sequencing")
    dialog.setInformativeText(
        "Advanced build, partition, signing, and device-operation surfaces will be exposed. "
        "You are responsible for the firmware, instructions, backups, and consequences of every "
        "operation you deliberately approve. Device damage, data loss, loss of warranty, or an "
        "unbootable phone may result.\n\nGuardian guidance and workflow lockouts are reduced in "
        "Expert Mode. ROMVERSE still refuses a proven device mismatch, corrupted or changed "
        "artifact, path escape, or missing/invalid command target; those checks prevent the app "
        "from executing a different operation than the one you selected."
    )
    accept = dialog.addButton(
        "I accept the risk • Enter Expert Mode",
        QMessageBox.ButtonRole.DestructiveRole,
    )
    decline = dialog.addButton(
        "Decline • Stay in Guided Mode",
        QMessageBox.ButtonRole.RejectRole,
    )
    dialog.setDefaultButton(decline)
    dialog.exec()
    return dialog.clickedButton() is accept


class RomModeChooser(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose ROM Studio mode")
        self.setMinimumSize(560, 300)
        layout = QVBoxLayout(self)
        title = QLabel("How do you want to work?")
        title.setObjectName("Title")
        layout.addWidget(title)
        detail = QLabel(
            "Genesis Sequence teaches each step and presents recommendations. "
            "Architect Mode exposes the complete advanced workspace after an explicit risk warning. "
            "Its guided lockouts are reduced, while exact target, artifact-integrity, and command-validity checks remain active."
        )
        detail.setObjectName("Muted")
        detail.setWordWrap(True)
        layout.addWidget(detail)
        layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        automatic = buttons.addButton("Genesis Sequence", QDialogButtonBox.ButtonRole.AcceptRole)
        expert = buttons.addButton("Architect Mode", QDialogButtonBox.ButtonRole.DestructiveRole)
        automatic.clicked.connect(lambda: self.done(1))
        expert.clicked.connect(self._choose_expert)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _choose_expert(self) -> None:
        if confirm_expert_mode(self):
            self.done(2)


class ProjectNameDialog(QDialog):
    """Stable, readable project-creation prompt with explicit validation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ProjectNameDialog")
        self.setWindowTitle("New ROMVERSE project")
        self.setModal(True)
        self.setMinimumSize(620, 340)
        self.resize(660, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        eyebrow = QLabel("ROM STUDIO  •  NEW WORKSPACE")
        eyebrow.setObjectName("Eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("Create a ROMVERSE project")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)
        description = QLabel(
            "Give this build workspace a clear name. The original firmware remains protected and unchanged."
        )
        description.setObjectName("Muted")
        description.setWordWrap(True)
        layout.addWidget(description)

        field_label = QLabel("PROJECT NAME")
        field_label.setObjectName("Eyebrow")
        layout.addWidget(field_label)
        self.name_input = QLineEdit()
        self.name_input.setObjectName("ProjectNameInput")
        self.name_input.setMaxLength(80)
        self.name_input.setFixedHeight(54)
        self.name_input.setPlaceholderText("Example: HyperOS 4 daily driver")
        self.name_input.textChanged.connect(self._validate)
        self.name_input.returnPressed.connect(self._accept_if_valid)
        layout.addWidget(self.name_input)

        self.hint = QLabel("1–80 characters")
        self.hint.setObjectName("Muted")
        layout.addWidget(self.hint)
        layout.addStretch(1)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addStretch(1)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setMinimumWidth(110)
        self.cancel_button.clicked.connect(self.reject)
        actions.addWidget(self.cancel_button)
        self.create_button = QPushButton("Create project")
        self.create_button.setObjectName("Primary")
        self.create_button.setMinimumWidth(150)
        self.create_button.setEnabled(False)
        self.create_button.clicked.connect(self._accept_if_valid)
        actions.addWidget(self.create_button)
        layout.addLayout(actions)

    @property
    def project_name(self) -> str:
        return self.name_input.text().strip()

    def _validate(self, text: str) -> None:
        valid = bool(text.strip())
        self.create_button.setEnabled(valid)
        self.hint.setText("Ready to create" if valid else "Enter 1–80 characters")
        self.hint.setObjectName("Good" if valid else "Muted")
        self.hint.style().unpolish(self.hint)
        self.hint.style().polish(self.hint)

    def _accept_if_valid(self) -> None:
        if self.project_name:
            self.accept()


class RecipeGuidedWizard(QDialog):
    STEPS = (
        (
            "Choose a target",
            "Select a relative path inside the extracted working tree. Protected originals are never targets.",
        ),
        (
            "Select an operation",
            "Choose a bounded operation such as replace-file or set-property. Every step is previewed first.",
        ),
        (
            "Review safeguards",
            "Confirm the recipe will require approval, create rollback material, and remain locked from device execution.",
        ),
    )

    def __init__(self, studio: RomStudio) -> None:
        super().__init__(studio)
        self.setWindowTitle("Guided Recipe Setup")
        self.setMinimumSize(520, 290)
        layout = QVBoxLayout(self)
        self.progress = QLabel()
        self.progress.setObjectName("Eyebrow")
        self.title = QLabel()
        self.title.setObjectName("Title")
        self.detail = QLabel()
        self.detail.setObjectName("Muted")
        self.detail.setWordWrap(True)
        layout.addWidget(self.progress)
        layout.addWidget(self.title)
        layout.addWidget(self.detail)
        layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.next_button = buttons.addButton("Next", QDialogButtonBox.ButtonRole.AcceptRole)
        self.next_button.clicked.connect(self._next)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._step = 0
        self._render()

    def _render(self) -> None:
        title, detail = self.STEPS[self._step]
        self.progress.setText(f"RECIPE GUIDE  •  STEP {self._step + 1} OF {len(self.STEPS)}")
        self.title.setText(title)
        self.detail.setText(detail)
        self.next_button.setText("Create recipe" if self._step == len(self.STEPS) - 1 else "Next")

    def _next(self) -> None:
        if self._step == len(self.STEPS) - 1:
            self.accept()
            return
        self._step += 1
        self._render()


class RomStudio(QWidget):
    operation_started = Signal(str)
    operation_completed = Signal(str, object)
    operation_failed = Signal(str, str)
    operation_progress = Signal(str, int)
    toolchain_requested = Signal(str, str)
    tool_statuses_resolved = Signal(object)
    time_machine_requested = Signal(str)
    device_packs_requested = Signal(str)
    guardian_review_requested = Signal(str, str)
    device_center_requested = Signal(str, str)
    knowledge_requested = Signal(str)
    ascension_status_changed = Signal()
    device_context_changed = Signal()
    device_scan_requested = Signal()
    device_scan_finished = Signal(bool, str)
    device_dna_updated = Signal(object)
    guardian_flash_verified = Signal(str, str, object)
    boot_observation_updated = Signal(object, object)
    first_light_updated = Signal(object, object)
    compatibility_matrix_updated = Signal(object)
    offline_knowledge_updated = Signal(object)
    experience_mode_requested = Signal(object)
    expert_flash_requested = Signal()
    project_flash_requested = Signal(str)
    source_installation_history_requested = Signal(str)
    source_installation_recovery_requested = Signal(str, str)

    def __init__(
        self,
        store: RomProjectStore,
        pack_registry: DevicePackRegistry,
        tool_statuses: tuple[ToolStatus, ...] = (),
        attestation_store: DevicePackAttestationStore | None = None,
        gateway: ExecutionGateway | None = None,
        adb_executable: Path | None = None,
        app_settings: AppSettings | None = None,
        fastboot_executable: Path | None = None,
    ) -> None:
        super().__init__()
        self.store = store
        self.inspection = RomInspectionService(store)
        self.external_intake = ExternalFirmwareIntakeService(store)
        self.device_dna = DeviceDnaService(store, pack_registry)
        self.compatibility = CompatibilityMatrixService(store)
        self.pack_registry = pack_registry
        self.attestation_store = attestation_store
        self.gateway = gateway
        self.adb_executable = adb_executable
        self.fastboot_executable = fastboot_executable
        self.app_settings = app_settings or AppSettings()
        self.projects: tuple[RomProject, ...] = ()
        self.current_project: RomProject | None = None
        self.suggested_pack_id = ""
        self.devices: list[AndroidDevice] = []
        self.observed_devices: list[AndroidDevice] = []
        self.device_scan_error = ""
        self.companion_snapshot = None
        self.device_scan_available = False
        self.tool_statuses: tuple[ToolStatus, ...] = ()
        self.payload_service: PayloadService | None = None
        self.filesystem_service: PartitionFilesystemService | None = None
        self.source_avb_service: SourceAvbEvidenceService | None = None
        self._configure_tools(tool_statuses)
        self.worker: ManagedRunnable | None = None
        self._active_operation = ""
        self._active_project_id = ""
        self._automatic_preparation_project_id = ""
        self._automatic_preparation_destination = ""
        self._automatic_simulation_project_id = ""
        self._automatic_simulation_verification_plan: BuildPlan | None = None
        self._automatic_simulation_verification_saved = False
        self._intentional_forge_plan: BuildPlan | None = None
        self._automatic_forge_verification: tuple[BuildPlan, ForgeBundleReceipt] | None = None
        self._last_validated_completion: tuple[str, str, int] | None = None
        self._last_recovery_report: WorkspaceRecoveryReport | None = None
        self._latest_guardian_execution_plan: GuardianExecutionPlan | None = None
        self._latest_guardian_gateway_contract: GuardianExecutionGatewayContract | None = None
        self._latest_guardian_reviewed_device: AndroidDevice | None = None
        self._latest_guardian_execution_result: VerifiedGuardianExecutionResult | None = None
        self._guided_mission_dialog: QDialog | None = None
        self._pending_repair_solution: (
            tuple[str, str, str, str, str, str, OnlineFixReceipt] | None
        ) = None

        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 30)
        page.setSpacing(18)
        header = QHBoxLayout()
        text = QVBoxLayout()
        eyebrow = QLabel("ROM STUDIO  •  PROVENANCE BEFORE MODIFICATION")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("ROM Projects")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Create versioned projects and preserve source firmware as hashed, immutable workspace originals."
        )
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        text.addWidget(eyebrow)
        text.addWidget(title)
        text.addWidget(subtitle)
        header.addLayout(text, 1)
        self.new_button = QPushButton("New project")
        self.new_button.setToolTip("Create a versioned ROMVERSE project manifest.")
        self.new_button.setObjectName("Primary")
        self.new_button.clicked.connect(self._new_project)
        header.addWidget(self.new_button)
        page.addLayout(header)

        workflow_bar = QFrame()
        workflow_bar.setObjectName("StudioWorkflowBar")
        workflow = QHBoxLayout(workflow_bar)
        workflow.setContentsMargins(12, 9, 12, 9)
        workflow.setSpacing(9)
        workflow_label = QLabel("PROJECT WORKFLOW")
        workflow_label.setObjectName("StudioWorkflowLabel")
        workflow.addWidget(workflow_label)
        self.delete_button = QPushButton("Delete project")
        self.delete_button.setToolTip(
            "Delete the selected project and derived working data after confirmation."
        )
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self._delete_project)
        workflow.addWidget(self.delete_button)
        workflow.addStretch()
        self.guided_button = QPushButton("Genesis Sequence")
        self.guided_button.setToolTip(
            "Enter ROMVERSE Genesis Sequence: prepare a verified local build, optionally review source-bound image installation, and check separate boot evidence."
        )
        self.guided_button.clicked.connect(self._open_guided_setup)
        workflow.addWidget(self.guided_button)
        self.ascension_button = QPushButton("Ascension Protocol")
        self.ascension_button.setToolTip(
            "Identify a device-specific Magisk or KernelSU path, verify official tools, and prepare a Guardian-controlled root handoff."
        )
        self.ascension_button.clicked.connect(self._open_ascension_protocol)
        workflow.addWidget(self.ascension_button)
        self.expert_button = QPushButton("Architect Mode")
        self.expert_button.setObjectName("ArchitectModeButton")
        self.expert_button.setCheckable(True)
        self.expert_button.setToolTip(
            "Switch the complete Desktop to Expert · Architect mode and reveal specialist "
            "routes. Projects, evidence, and Guardian protections remain unchanged."
        )
        self.expert_button.clicked.connect(self._toggle_architect_mode)
        workflow.addWidget(self.expert_button)
        page.addWidget(workflow_bar)

        boundary = QFrame()
        boundary.setObjectName("HeroCard")
        boundary_layout = QHBoxLayout(boundary)
        boundary_layout.setContentsMargins(20, 16, 20, 16)
        locked = QLabel("Original protection active")
        locked.setObjectName("Good")
        copy = QLabel(
            "Inspect external firmware in place for authority-free evidence, or deliberately import "
            "a separate hashed, read-only workspace original. Neither path extracts the source in place."
        )
        copy.setObjectName("Muted")
        copy.setWordWrap(True)
        boundary_layout.addWidget(locked)
        boundary_layout.addSpacing(14)
        boundary_layout.addWidget(copy, 1)
        page.addWidget(boundary)

        self.dashboard_handoff = QFrame()
        self.dashboard_handoff.setObjectName("DiagnosticHandoffBar")
        dashboard_handoff_layout = QHBoxLayout(self.dashboard_handoff)
        dashboard_handoff_layout.setContentsMargins(18, 13, 18, 13)
        dashboard_handoff_layout.setSpacing(14)
        dashboard_handoff_copy = QVBoxLayout()
        self.dashboard_handoff_eyebrow = QLabel(
            "COMMAND DECK HANDOFF  •  EXACT ROM STUDIO WORKFLOW"
        )
        self.dashboard_handoff_eyebrow.setObjectName("Eyebrow")
        self.dashboard_handoff_title = QLabel()
        self.dashboard_handoff_title.setObjectName("SectionTitle")
        self.dashboard_handoff_detail = QLabel()
        self.dashboard_handoff_detail.setObjectName("Muted")
        self.dashboard_handoff_detail.setWordWrap(True)
        self.dashboard_handoff_detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        dashboard_handoff_copy.addWidget(self.dashboard_handoff_eyebrow)
        dashboard_handoff_copy.addWidget(self.dashboard_handoff_title)
        dashboard_handoff_copy.addWidget(self.dashboard_handoff_detail)
        dashboard_handoff_layout.addLayout(dashboard_handoff_copy, 1)
        self.dashboard_handoff_badge = QLabel()
        dashboard_handoff_layout.addWidget(self.dashboard_handoff_badge)
        self.dashboard_handoff.setVisible(False)
        page.addWidget(self.dashboard_handoff)

        self.project_filter = QLineEdit()
        self.project_filter.setPlaceholderText("Search ROM projects…")
        self.project_filter.setToolTip("Filter projects by name, date, or protection status.")
        self.project_filter.textChanged.connect(self._filter_projects)
        page.addWidget(self.project_filter)

        content = QHBoxLayout()
        content.setSpacing(16)
        self.project_list = QListWidget()
        self.project_list.setObjectName("HistoryList")
        self.project_list.setMinimumWidth(280)
        self.project_list.setMaximumWidth(340)
        self.project_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.project_list.setWordWrap(True)
        self.project_list.currentRowChanged.connect(self._select)
        content.addWidget(self.project_list)

        detail = QFrame()
        detail.setObjectName("Card")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(24, 22, 24, 22)
        detail_layout.setSpacing(14)
        self.project_name = QLabel("No project selected")
        self.project_name.setObjectName("HeroTitle")
        self.project_meta = QLabel()
        self.project_meta.setObjectName("Muted")
        self.project_meta.setWordWrap(True)
        detail_layout.addWidget(self.project_name)
        detail_layout.addWidget(self.project_meta)

        self.upgrade_passport = QFrame()
        self.upgrade_passport.setObjectName("UpgradePassport")
        self.upgrade_passport.setProperty("upgradeState", "attention")
        upgrade_layout = QVBoxLayout(self.upgrade_passport)
        upgrade_layout.setContentsMargins(16, 13, 16, 13)
        upgrade_layout.setSpacing(5)
        upgrade_title = QLabel("FIRMWARE UPGRADE PASSPORT  •  SOURCE + LIVE DEVICE")
        upgrade_title.setObjectName("UpgradePassportTitle")
        self.upgrade_passport_status = QLabel("AWAITING PROTECTED FIRMWARE")
        self.upgrade_passport_status.setObjectName("UpgradePassportStatus")
        self.upgrade_passport_status.setProperty("upgradeState", "attention")
        self.upgrade_passport_detail = QLabel(
            "ROMVERSE will compare the exact protected package with one connected phone. "
            "Classification never grants installation or flash authority."
        )
        self.upgrade_passport_detail.setObjectName("Muted")
        self.upgrade_passport_detail.setWordWrap(True)
        self.upgrade_passport_detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        upgrade_layout.addWidget(upgrade_title)
        upgrade_layout.addWidget(self.upgrade_passport_status)
        upgrade_layout.addWidget(self.upgrade_passport_detail)
        detail_layout.addWidget(self.upgrade_passport)

        dna_title = QLabel("Device DNA • Capability Map")
        dna_title.setObjectName("SectionTitle")
        detail_layout.addWidget(dna_title)
        self.device_dna_detail = QLabel(
            "Import protected firmware to create an evidence-backed Device DNA profile."
        )
        self.device_dna_detail.setObjectName("Muted")
        self.device_dna_detail.setWordWrap(True)
        self.device_dna_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail_layout.addWidget(self.device_dna_detail)

        source_title = QLabel("Protected original")
        source_title.setObjectName("SectionTitle")
        detail_layout.addWidget(source_title)
        self.original_name = QLabel("Not imported")
        self.original_name.setObjectName("Value")
        self.original_detail = QLabel(
            "Choose an original ROM, OTA, image, archive, or firmware package when you are ready."
        )
        self.original_detail.setObjectName("Muted")
        self.original_detail.setWordWrap(True)
        self.original_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail_layout.addWidget(self.original_name)
        detail_layout.addWidget(self.original_detail)
        self.firmware_responsibility_notice = QLabel(
            "Firmware source responsibility  •  " + USER_FIRMWARE_RESPONSIBILITY_NOTICE
        )
        self.firmware_responsibility_notice.setObjectName("Warning")
        self.firmware_responsibility_notice.setWordWrap(True)
        self.firmware_responsibility_notice.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        detail_layout.addWidget(self.firmware_responsibility_notice)

        inspection_title = QLabel("Structure inspection")
        inspection_title.setObjectName("SectionTitle")
        detail_layout.addWidget(inspection_title)
        self.inspection_detail = QLabel(
            "Not inspected. ROMVERSE will verify SHA-256 before reading container metadata."
        )
        self.inspection_detail.setObjectName("Muted")
        self.inspection_detail.setTextFormat(Qt.TextFormat.PlainText)
        self.inspection_detail.setWordWrap(True)
        self.inspection_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail_layout.addWidget(self.inspection_detail)

        time_machine_title = QLabel("Time Machine")
        time_machine_title.setObjectName("SectionTitle")
        detail_layout.addWidget(time_machine_title)
        self.time_machine_detail = QLabel("No working copy or snapshots yet.")
        self.time_machine_detail.setObjectName("Muted")
        self.time_machine_detail.setWordWrap(True)
        self.time_machine_detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        detail_layout.addWidget(self.time_machine_detail)

        self.operation_status = QLabel("Ready")
        self.operation_status.setObjectName("Muted")
        self.operation_status.setWordWrap(True)
        detail_layout.addWidget(self.operation_status)
        self.progress = ProcessProgressBar()
        detail_layout.addWidget(self.progress)

        self.command_tabs = QTabWidget()
        self.command_tabs.setObjectName("StudioCommandTabs")
        self.command_tabs.setMinimumHeight(264)
        self.command_tabs.setDocumentMode(True)
        self.command_tabs.setMovable(False)
        self.command_tabs.setUsesScrollButtons(True)
        self.external_intake_button = QPushButton("Inspect firmware in place…")
        self.external_intake_button.setToolTip(
            "Hash and inspect an external firmware package without copying, extracting, "
            "changing it, or granting build, device, or execution authority."
        )
        self.external_intake_button.setEnabled(False)
        self.external_intake_button.clicked.connect(self._inspect_external)
        self.import_button = QPushButton("Import original…")
        self.import_button.setToolTip(
            "Copy, SHA-256 hash, protect, and automatically inspect firmware in the workspace."
        )
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self._import_original)
        self.verify_button = QPushButton("Verify integrity")
        self.verify_button.setToolTip("Recompute SHA-256 for the protected workspace copy.")
        self.verify_button.setEnabled(False)
        self.verify_button.clicked.connect(self._verify)
        self.inspect_button = QPushButton("Inspect structure")
        self.inspect_button.setToolTip(
            "Read container metadata safely; no archive content is extracted."
        )
        self.inspect_button.setEnabled(False)
        self.inspect_button.clicked.connect(self._inspect)
        self.working_button = QPushButton("Create working copy")
        self.working_button.setToolTip(
            "Create an isolated writable baseline while preserving the protected original."
        )
        self.working_button.setEnabled(False)
        self.working_button.clicked.connect(lambda: self._start_worker("working-copy"))
        self.snapshot_button = QPushButton("Time Machine snapshot")
        self.snapshot_button.setToolTip(
            "Save a verified local snapshot for future rollback planning."
        )
        self.snapshot_button.setEnabled(False)
        self.snapshot_button.clicked.connect(lambda: self._start_worker("snapshot"))
        self.extract_button = QPushButton("Prepare safe tree")
        self.extract_button.setToolTip(
            "Extract a verified ZIP/TAR or stage a recognized single image into a contained working tree with safety limits."
        )
        self.extract_button.setEnabled(False)
        self.extract_button.clicked.connect(lambda: self._start_worker("extract"))
        self.plan_button = QPushButton("Plan build (dry-run)")
        self.plan_button.setToolTip(
            "Generate a deterministic, Guardian-assessed build plan; execution is locked."
        )
        self.plan_button.setEnabled(False)
        self.plan_button.clicked.connect(lambda: self._start_worker("plan"))
        self.verify_plan_button = QPushButton("Verify plan")
        self.verify_plan_button.setToolTip(
            "Check that extracted files still match the saved build-plan hash."
        )
        self.verify_plan_button.setEnabled(False)
        self.verify_plan_button.clicked.connect(lambda: self._start_worker("verify-plan"))
        self.forge_button = QPushButton("Forge Bundle")
        self.forge_button.setToolTip(
            "Create a deterministic, content-addressed ZIP from the verified working tree. If Genesis selected and completed Ascension, its sealed rooted partition and provenance are included; otherwise the bundle remains unrooted. This intermediate is unsigned, non-bootable, and never flashable."
        )
        self.forge_button.setEnabled(False)
        self.forge_button.clicked.connect(self._begin_intentional_forge_bundle)
        self.verify_forge_button = QPushButton("Verify Forge Bundle")
        self.verify_forge_button.setToolTip(
            "Re-hash the Forge archive, embedded manifest, and every bundled file without changing the phone or project tree."
        )
        self.verify_forge_button.setEnabled(False)
        self.verify_forge_button.clicked.connect(lambda: self._start_worker("verify-forge"))
        self.recipe_button = QPushButton("Preview recipe")
        self.recipe_button.setToolTip("Resolve recipe targets without changing files or devices.")
        self.recipe_button.setEnabled(False)
        self.recipe_button.clicked.connect(lambda: self._start_worker("preview-recipe"))
        self.new_recipe_button = QPushButton("New recipe")
        self.new_recipe_button.setToolTip(
            "Create a Guardian-controlled recipe for a target in the extracted tree."
        )
        self.new_recipe_button.setEnabled(False)
        self.new_recipe_button.clicked.connect(self._new_recipe)
        self.guided_recipe_button = QPushButton("Recipe Forge")
        self.guided_recipe_button.setToolTip(
            "Open ROMVERSE Recipe Forge to design, target, configure, and Guardian-review a safe working-tree change."
        )
        self.guided_recipe_button.setEnabled(False)
        self.guided_recipe_button.clicked.connect(self._guided_recipe)
        self.add_step_button = QPushButton("Add recipe step")
        self.add_step_button.setToolTip(
            "Append another bounded operation to the current Guardian-controlled recipe."
        )
        self.add_step_button.setEnabled(False)
        self.add_step_button.clicked.connect(self._add_recipe_step)
        self.rollback_button = QPushButton("Open Time Machine")
        self.rollback_button.setToolTip(
            "Open the Time Machine console to verify or restore a local working-baseline snapshot."
        )
        self.rollback_button.setEnabled(False)
        self.rollback_button.clicked.connect(self.request_time_machine)
        self.replace_button = QPushButton("Run approved recipe")
        self.replace_button.setToolTip(
            "Execute all validated local recipe steps after confirmation and create automatic rollback data."
        )
        self.replace_button.setEnabled(False)
        self.replace_button.clicked.connect(self._execute_recipe)
        self.property_button = QPushButton("Restore recipe snapshot")
        self.property_button.setToolTip(
            "Restore every target from a verified automatic pre-recipe snapshot."
        )
        self.property_button.setEnabled(False)
        self.property_button.clicked.connect(self._restore_recipe)
        self.partition_button = QPushButton("Partition Atlas")
        self.partition_button.setToolTip(
            "Scan payload.bin, visualize its partition map, and extract selected ROM partitions with Guardian storage and provenance checks."
        )
        self.partition_button.setEnabled(False)
        self.partition_button.clicked.connect(self._open_partition_workspace)
        guide = QFrame()
        guide.setObjectName("HeroCard")
        guide_layout = QVBoxLayout(guide)
        guide_layout.setContentsMargins(14, 10, 14, 10)
        guide_title = QLabel("GUIDED MODE  •  SAFE ROM WORKFLOW")
        guide_title.setObjectName("Eyebrow")
        guide_layout.addWidget(guide_title)
        self.guide_status = QLabel("Select or create a project to begin.")
        self.guide_status.setObjectName("Muted")
        self.guide_status.setWordWrap(True)
        guide_layout.addWidget(self.guide_status)
        detail_layout.addWidget(guide)
        self.build_control_button = QPushButton("Forge Control")
        self.build_control_button.setToolTip(
            "Inspect build, signing, recovery, and flash-readiness gates and run a phone-safe pipeline simulation."
        )
        self.build_control_button.setEnabled(False)
        self.build_control_button.clicked.connect(self._open_build_control)
        self.expert_flash_button = QPushButton("Flash / restore images…")
        self.expert_flash_button.setToolTip(
            "Review explicit image-to-partition writes on the connected Fastboot device, "
            "then confirm execution in Expert Mode."
        )
        self.expert_flash_button.clicked.connect(self._request_expert_flash)
        action_buttons = (
            self.external_intake_button,
            self.import_button,
            self.verify_button,
            self.inspect_button,
            self.working_button,
            self.snapshot_button,
            self.extract_button,
            self.plan_button,
            self.verify_plan_button,
            self.forge_button,
            self.verify_forge_button,
            self.recipe_button,
            self.new_recipe_button,
            self.guided_recipe_button,
            self.add_step_button,
            self.rollback_button,
            self.replace_button,
            self.property_button,
            self.partition_button,
            self.build_control_button,
            self.expert_flash_button,
        )
        hover_help = {
            "Inspect firmware in place…": "Create project-bound, read-only package evidence without copying or extracting the selected firmware. All build and device actions remain locked.",
            "Import original…": "Load firmware into protected Original ROMs. ROMVERSE copies, hashes, protects, and automatically inspects the source without modifying it.",
            "Verify integrity": "Recalculate the protected original SHA-256 and confirm it is unchanged.",
            "Inspect structure": "Read safe container metadata without extracting or changing files.",
            "Create working copy": "Create an isolated writable copy while preserving the protected original.",
            "Time Machine snapshot": "Save a local rollback snapshot before edits.",
            "Prepare safe tree": "Extract supported archives or stage a recognized single image into a contained, safety-checked working tree.",
            "Plan build (dry-run)": "Generate a deterministic plan and Guardian preflight; nothing is built or flashed.",
            "Verify plan": "Confirm the working tree still matches the saved build-plan hash.",
            "Forge Bundle": "Create a reproducible content-addressed workspace ZIP. ROMVERSE verifies every input while writing; the result is explicitly unsigned, non-bootable, and non-flashable.",
            "Verify Forge Bundle": "Verify the archive hash, embedded safety manifest, exact member set, and every file SHA-256 without rebuilding or touching a phone.",
            "Preview recipe": "Resolve recipe targets without changing files or devices.",
            "New recipe": "Create a Guardian-controlled recipe for a contained working-tree target.",
            "Add recipe step": "Append another reviewed operation to the current recipe.",
            "Open Time Machine": "Verify or restore a local working-baseline snapshot with typed approval, automatic safety snapshot, and receipt.",
            "Run approved recipe": "Run all bounded local recipe steps transactionally; affected targets are snapshotted and verified first.",
            "Restore recipe snapshot": "Restore affected targets from a verified automatic recipe snapshot after confirmation.",
            "Partition Atlas": "Map payload.bin, inspect filesystems, and prepare verified partition images without touching the connected phone.",
            "Forge Control": "Inspect every build, signing, recovery, and flash gate; prepare exact inputs; and execute a verified versioned local candidate when the Device Pack contract is complete.",
        }
        for button in action_buttons:
            button.setToolTip(hover_help.get(button.text(), button.toolTip()))
            button.setObjectName("StudioAction")
            button.setMinimumHeight(46)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        for button in (
            self.guided_recipe_button,
            self.partition_button,
            self.rollback_button,
            self.build_control_button,
        ):
            button.setProperty("featured", True)

        command_groups = (
            (
                "SOURCE LAB",
                "Protect, identify, and isolate the exact firmware source.",
                (
                    self.external_intake_button,
                    self.import_button,
                    self.verify_button,
                    self.inspect_button,
                    self.working_button,
                    self.extract_button,
                ),
            ),
            (
                "BUILD & PROOF",
                "Freeze inputs, create reproducible artifacts, and verify every byte.",
                (
                    self.plan_button,
                    self.verify_plan_button,
                    self.forge_button,
                    self.verify_forge_button,
                    self.partition_button,
                    self.build_control_button,
                    self.expert_flash_button,
                ),
            ),
            (
                "RECIPE FORGE",
                "Design, preview, apply, and reverse contained ROM changes.",
                (
                    self.guided_recipe_button,
                    self.new_recipe_button,
                    self.add_step_button,
                    self.recipe_button,
                    self.replace_button,
                    self.property_button,
                ),
            ),
            (
                "RECOVERY BAY",
                "Create and verify rollback checkpoints before higher-risk work.",
                (self.snapshot_button, self.rollback_button),
            ),
        )
        for position, (heading, summary, buttons) in enumerate(command_groups):
            group = QFrame()
            group.setObjectName("StudioCommandGroup")
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(14, 12, 14, 14)
            group_layout.setSpacing(8)
            group.setMinimumHeight(206)
            title = QLabel(heading)
            title.setObjectName("StudioCommandTitle")
            description = QLabel(summary)
            description.setObjectName("StudioCommandSummary")
            description.setWordWrap(True)
            group_layout.addWidget(title)
            group_layout.addWidget(description)
            button_grid = QGridLayout()
            button_grid.setHorizontalSpacing(8)
            button_grid.setVerticalSpacing(8)
            for index, button in enumerate(buttons):
                button_grid.addWidget(button, index // 3, index % 3)
            button_grid.setColumnStretch(0, 1)
            button_grid.setColumnStretch(1, 1)
            button_grid.setColumnStretch(2, 1)
            group_layout.addLayout(button_grid)
            group_layout.addStretch()
            glow = QGraphicsDropShadowEffect(group)
            glow.setBlurRadius(24)
            glow.setOffset(0, 3)
            glow.setColor(QColor(61, 220, 244, 32) if position < 2 else QColor(177, 78, 255, 34))
            group.setGraphicsEffect(glow)
            self.command_tabs.addTab(group, heading.title())
        self.command_tabs.setCurrentIndex(0)
        detail_layout.addWidget(self.command_tabs)
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setObjectName("StudioDetailScroll")
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.detail_scroll.setWidget(detail)
        content.addWidget(self.detail_scroll, 1)
        page.addLayout(content, 1)

        footer = QLabel(
            "ROM Studio preserves firmware originals and builds local candidates. Forge Bundles "
            "are intermediate archives. In Architect Mode, Flash / restore images provides "
            "direct, reviewed Fastboot partition writes with separate confirmation and recorded results."
        )
        footer.setObjectName("Muted")
        footer.setWordWrap(True)
        page.addWidget(footer)
        self.refresh()
        self.set_experience_mode(self.app_settings.experience_mode)

    def _configure_tools(self, tool_statuses: tuple[ToolStatus, ...]) -> None:
        self.tool_statuses = tuple(tool_statuses)
        payload_path = next(
            (
                Path(item.path)
                for item in self.tool_statuses
                if item.name == "Payload Dumper" and item.available and item.path
            ),
            None,
        )
        payload_path = payload_path or (
            Path(found) if (found := shutil.which("payload-dumper-go")) else None
        )
        self.payload_service = (
            PayloadService(self.store, payload_path, SubprocessRunner())
            if payload_path is not None
            else None
        )

        def resolved_tool(status_name: str, executable: str) -> Path | None:
            configured = next(
                (
                    Path(item.path)
                    for item in self.tool_statuses
                    if item.name == status_name and item.available and item.path
                ),
                None,
            )
            found_path = shutil.which(executable)
            return configured or (Path(found_path) if found_path else None)

        self.filesystem_service = PartitionFilesystemService(
            self.store,
            self.payload_service,
            SubprocessRunner(),
            simg2img=resolved_tool("simg2img", "simg2img"),
            debugfs=resolved_tool("EXT4 Browser", "debugfs"),
            erofs=resolved_tool("EROFS Verifier", "fsck.erofs"),
            fakeroot=resolved_tool("Fakeroot", "fakeroot"),
            lpunpack=resolved_tool("LP Unpack", "lpunpack"),
        )
        avbtool = resolved_tool("AVBTool", "avbtool")
        self.source_avb_service = (
            SourceAvbEvidenceService(
                self.store,
                self.payload_service,
                avbtool,
                SubprocessRunner(),
            )
            if self.payload_service is not None and avbtool is not None
            else None
        )

    def _open_guided_setup(self, *, start_new_project: bool = False) -> None:
        from romverse.ui.guided_mission import GuidedBuildMission

        if self._guided_mission_dialog is not None:
            self._guided_mission_dialog.raise_()
            self._guided_mission_dialog.activateWindow()
            return
        dialog = GuidedBuildMission(self, start_new_project=start_new_project)
        self._guided_mission_dialog = dialog
        dialog.finished.connect(lambda _result, opened=dialog: self._guided_setup_closed(opened))
        dialog.open()

    def _guided_setup_closed(self, dialog: QDialog) -> None:
        if self._guided_mission_dialog is not dialog:
            return
        self._guided_mission_dialog = None
        preferred_id = self.current_project.project_id if self.current_project is not None else ""
        self.refresh(preferred_id)
        self._refresh_visible_genesis_handoff()
        dialog.deleteLater()

    def _genesis_handoff_scope(self) -> str:
        project = self.current_project
        if project is not None:
            try:
                build_evidence_recorded = (
                    RomBuildPlanner(self.store).load(project.project_id) is not None
                )
            except (OSError, ProjectError):
                build_evidence_recorded = False
            if build_evidence_recorded:
                return "LOCAL BUILD EVIDENCE RECORDED; NO INSTALLATION OR PHONE ACTION STARTED."
        return "NO BUILD OR PHONE ACTION STARTED."

    def _refresh_visible_genesis_handoff(self) -> None:
        """Repaint a Genesis entry card from the mission's newly durable state."""

        title = self.dashboard_handoff_title.text()
        if self.dashboard_handoff.isHidden() or "Genesis Sequence" not in title:
            return
        flight = self.genesis_flight_plan()
        needs_attention = flight.has_saved_error or flight.status is GuidedStageStatus.ATTENTION
        self._show_dashboard_handoff(
            title,
            f"{flight.project_name}  •  Stage {flight.stage_number}/{flight.stage_total}: "
            f"{flight.stage_title}  •  {flight.progress_percent}% verified. Genesis returned "
            f"to this exact saved project state; {self._genesis_handoff_scope()}",
            "ATTENTION" if needs_attention else "CURRENT STAGE",
            ready=not needs_attention,
            eyebrow=self.dashboard_handoff_eyebrow.text(),
        )

    def open_dashboard_intent(self, action: str) -> bool:
        """Preserve one Command Deck intent after navigation into ROM Studio.

        Build ROM opens Genesis. Simulation and Recipes may run an already-inspected exact
        project's reversible local preparation, but never gain phone authority or start a build;
        Recipes also cannot create a recipe merely through navigation.
        """

        action = str(action).strip()
        if action == "Build ROM":
            flight = self.genesis_flight_plan()
            project_context = (
                f"{flight.project_name}  •  Stage {flight.stage_number}/{flight.stage_total}: "
                f"{flight.stage_title}  •  {flight.progress_percent}% verified."
                if self.current_project is not None
                else "No project exists yet; Genesis will begin at protected project creation."
            )
            self._show_dashboard_handoff(
                "Build ROM → Genesis Sequence",
                f"{project_context} The guide is opening at the exact next safe stage. "
                f"{self._genesis_handoff_scope()}",
                "GUIDED ENTRY",
                ready=True,
            )
            self.guided_button.setFocus(Qt.FocusReason.OtherFocusReason)
            self._open_guided_setup()
            return True

        if action == "Pre-Build Simulation":
            ready, detail = self._prebuild_simulation_handoff()
            if not ready:
                started, automatic_detail = self._begin_automatic_local_preparation(action)
                if started:
                    return True
                if automatic_detail:
                    detail = automatic_detail
            if ready:
                self._open_prebuild_simulation_destination(True)
                self._begin_automatic_prebuild_simulation()
                self.detail_scroll.ensureWidgetVisible(self.command_tabs, 0, 24)
                return True
            destination = self._open_prebuild_simulation_destination(ready)
            self._show_dashboard_handoff(
                f"Pre-Build Simulation → {destination}",
                detail,
                "READY" if ready else "PREREQUISITE",
                ready=ready,
            )
            self.detail_scroll.ensureWidgetVisible(self.command_tabs, 0, 24)
            return True

        if action == "Recipes":
            ready, detail = self._recipe_forge_handoff()
            if not ready:
                started, automatic_detail = self._begin_automatic_local_preparation(action)
                if started:
                    return True
                if automatic_detail:
                    detail = automatic_detail
            destination = self._open_recipe_forge_destination(ready)
            self._show_dashboard_handoff(
                f"Recipes → {destination}",
                detail,
                "READY" if ready else "PREREQUISITE",
                ready=ready,
            )
            self.detail_scroll.ensureWidgetVisible(self.command_tabs, 0, 24)
            return True

        return False

    def _begin_automatic_prebuild_simulation(self) -> None:
        """Run or present one exact existing bounded dry-run result for the requested project."""

        project = self.current_project
        if project is None or self.worker is not None:
            return
        planner = RomBuildPlanner(self.store)
        plan_path = self.store.projects_root / project.project_id / planner.PLAN_NAME
        plan_temporary = plan_path.with_suffix(".tmp")
        if os.path.lexists(plan_temporary):
            self._show_dashboard_handoff(
                "Pre-Build Simulation → Interrupted dry run needs attention",
                f"{project.name} has an unfinished dry-run transaction, so its completion is "
                "unknown. ROMVERSE preserved the evidence and did not retry or infer a result. "
                "Review Build & Proof before intentionally starting another dry run; no build or "
                "phone action started.",
                "ATTENTION",
                ready=False,
            )
            self.plan_button.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        existing = planner.load(project.project_id)
        if existing is not None:
            expected_tree = (
                (self.store.working_root / project.project_id / "tree")
                .relative_to(self.store.workspace)
                .as_posix()
            )
            recipe = RecipeStore().load(self.store.projects_root / project.project_id)
            recipe_digest = recipe.digest() if recipe is not None else ""
            if (
                existing.schema_version not in {2, 3}
                or existing.project_id != project.project_id
                or existing.device_pack_id != project.device_pack_id
                or existing.source_tree != expected_tree
                or existing.recipe_digest != recipe_digest
                or not existing.execution_locked
            ):
                self._show_dashboard_handoff(
                    "Pre-Build Simulation → Saved result needs attention",
                    f"{project.name}'s saved dry-run identity no longer matches the exact current "
                    "project inputs. ROMVERSE preserved it for review and did not overwrite or "
                    "retry it. Review Build & Proof verification before requesting a new plan. "
                    "No build or phone action started.",
                    "ATTENTION",
                    ready=False,
                )
                self.verify_plan_button.setFocus(Qt.FocusReason.OtherFocusReason)
                return
            self._begin_automatic_simulation_verification(existing, saved=True)
            return
        if os.path.lexists(plan_path):
            self._show_dashboard_handoff(
                "Pre-Build Simulation → Saved result needs attention",
                f"{project.name} has unreadable or malformed saved dry-run evidence. ROMVERSE "
                "preserved it and did not overwrite, guess, or retry. Review Build & Proof before "
                "requesting a new plan. No build or phone action started.",
                "ATTENTION",
                ready=False,
            )
            self.plan_button.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        self._automatic_simulation_project_id = project.project_id
        self._show_dashboard_handoff(
            "Pre-Build Simulation → Dry run in progress",
            f"ROMVERSE is freezing {project.name}'s exact current inputs and running the existing "
            "Guardian preflight. This creates a locked inert plan only; no build, signing, phone, "
            "flash, or execution action starts.",
            "SIMULATING",
            ready=True,
        )
        self._start_worker("plan")

    def _begin_automatic_simulation_verification(
        self,
        plan: BuildPlan,
        *,
        saved: bool,
    ) -> None:
        """Run the existing exact current-tree verifier once for this Simulation request."""

        project = self.current_project
        if project is None or project.project_id != plan.project_id or self.worker is not None:
            return
        self._automatic_simulation_verification_plan = plan
        self._automatic_simulation_verification_saved = saved
        source = "safely reloaded" if saved else "newly completed"
        self._show_dashboard_handoff(
            "Pre-Build Simulation → Verifying current tree",
            f"ROMVERSE is independently checking {project.name}'s current contained tree against "
            f"the {source} exact dry-run result. This read-only verification runs once for this "
            "request; no build, signing, execution, or phone action starts.",
            "VERIFYING",
            ready=True,
        )
        self._start_worker("verify-plan")

    def _show_prebuild_simulation_result(
        self,
        plan: BuildPlan,
        verification: ArtifactVerification,
        *,
        saved: bool,
    ) -> None:
        """Present one independently verified typed dry-run result without build authority."""

        project = self.store.get(plan.project_id)
        self.command_tabs.setCurrentIndex(1)
        self.forge_button.setFocus(Qt.FocusReason.OtherFocusReason)
        source = "Saved" if saved else "Completed"
        self._show_dashboard_handoff(
            "Pre-Build Simulation → Dry run complete",
            f"{source} typed result for {project.name}: {len(plan.input_files):,} inputs, "
            f"{len(plan.partitions):,} detected image partitions, tree SHA-256 "
            f"{plan.tree_sha256[:16]}…, Guardian {plan.guardian_status} / {plan.guardian_risk}. "
            f"Current-tree verification: {verification.status}. The plan is execution-locked; "
            "Forge Bundle is the next intentional local action: an unsigned, non-bootable, "
            "non-flashable intermediate. Nothing begins until you choose it; no build or phone "
            "action occurred.",
            "VERIFIED",
            ready=True,
        )

    def _begin_intentional_forge_bundle(self) -> None:
        """Bind one explicit Forge choice to the exact current persisted plan."""

        project = self.current_project
        if project is None or self.worker is not None:
            return
        plan = RomBuildPlanner(self.store).load(project.project_id)
        if plan is None or not self.forge_button.isEnabled():
            return
        forge = ForgeBundleService(self.store)
        existing = forge.load_receipt(project.project_id)
        if existing is not None and not forge.receipt_matches_plan(existing, plan):
            self._show_dashboard_handoff(
                "Forge Bundle → Preserving earlier plan evidence",
                "The saved Forge Bundle belongs to a different exact Build Readiness plan. "
                "ROMVERSE will preserve its receipt and immutable archive in private history, "
                "then create and verify the current generation from this one explicit Forge "
                "choice. The previous latest receipt remains recoverable unless current Forge "
                "completion succeeds.",
                "PRESERVING HISTORY",
                ready=True,
            )
        self._intentional_forge_plan = plan
        self._start_worker("forge-bundle")

    def _begin_automatic_local_preparation(self, destination: str) -> tuple[bool, str]:
        """Start one admitted exact-project preparation for an existing destination."""

        operation, detail = self._automatic_local_preparation_admission(destination)
        if not operation:
            return False, detail
        project = self.current_project
        if project is None:
            return False, ""
        self._automatic_preparation_project_id = project.project_id
        self._automatic_preparation_destination = destination
        if destination == "Recipes":
            self._open_recipe_forge_destination(False)
        else:
            self._open_prebuild_simulation_destination(False)
        self._show_dashboard_handoff(
            f"{destination} → Automatic safe preparation",
            detail,
            "PREPARING",
            ready=True,
        )
        self.detail_scroll.ensureWidgetVisible(self.command_tabs, 0, 24)
        self._start_worker(operation)
        return True, detail

    def _automatic_local_preparation_admission(self, destination: str) -> tuple[str, str]:
        """Admit exact reversible local prerequisites for one known existing workflow."""

        project = self.current_project
        if (
            destination not in {"Pre-Build Simulation", "Recipes"}
            or project is None
            or project.original is None
            or self.worker is not None
        ):
            return "", ""
        report = self.inspection.load_report(project.project_id)
        if report is None:
            return "", ""
        if any(finding.severity.value == "critical" for finding in report.findings):
            return (
                "",
                f"{project.name} has a critical structure finding. ROMVERSE did not prepare or "
                "guess around unsafe evidence. Review Source Lab inspection evidence; the "
                "protected source and phone remain unchanged.",
            )
        if self.inspection.working_tree_exists(project.project_id):
            return "", ""
        try:
            budget = self.inspection.extraction_budget(project.project_id, report)
            working = self.store.working_copy(project.project_id)
            baseline_bytes = 0 if working is not None else project.original.size_bytes
            required_free = baseline_bytes + budget.expected_bytes + budget.reserve_bytes
            if not budget.safe or budget.free_bytes < required_free:
                reason = (
                    budget.reason
                    if not budget.safe
                    else "Safe preparation needs "
                    f"{human_bytes(required_free)} free for the verified baseline, extracted "
                    f"tree, and retained reserve; {human_bytes(budget.free_bytes)} is available"
                )
                return (
                    "",
                    f"{project.name} remains exactly selected, but automatic preparation stopped "
                    f"before writing: {reason}. Free workspace storage, then choose {destination} "
                    "again. Prior evidence, the protected source, and the phone remain unchanged.",
                )
        except (OSError, ProjectError, TypeError, ValueError) as exc:
            return (
                "",
                f"{project.name} remains exactly selected, but ROMVERSE could not prove safe "
                f"preparation admission: {exc}. Review Source Lab evidence, then choose "
                f"{destination} again. No preparation or phone action started.",
            )
        operation = "working-copy" if working is None else "extract"
        next_step = (
            "verify an isolated baseline, then prepare the contained tree"
            if operation == "working-copy"
            else "prepare the contained tree from the already verified baseline"
        )
        resume = "Recipe Forge" if destination == "Recipes" else "Build & Proof dry-run readiness"
        return (
            operation,
            f"ROMVERSE is using {project.name}'s protected original and valid inspection to "
            f"{next_step}. Progress and producer evidence remain visible; on verified completion "
            f"{resume} will resume automatically. This is reversible local preparation only; "
            "no build starts, and the protected source and phone remain unchanged.",
        )

    def _prebuild_simulation_handoff(self) -> tuple[bool, str]:
        project = self.current_project
        if project is None:
            return (
                False,
                "Create or select a ROM project, then import its protected firmware source. "
                "ROMVERSE cannot simulate an unknown input. NO BUILD OR PHONE ACTION STARTED.",
            )
        if project.original is None:
            return (
                False,
                f"{project.name} needs a protected original before planning. Use Source Lab → "
                "Import original. NO BUILD OR PHONE ACTION STARTED.",
            )
        report = self.inspection.load_report(project.project_id)
        if report is None:
            return (
                False,
                f"{project.name} needs a saved structure inspection before its build inputs can "
                "be prepared. Use Source Lab → Inspect structure. NO BUILD OR PHONE ACTION STARTED.",
            )
        if not self.inspection.working_tree_exists(project.project_id):
            return (
                False,
                f"{project.name} needs a contained working tree. Use Source Lab to create the "
                "working copy and prepare the safe tree. NO BUILD OR PHONE ACTION STARTED.",
            )
        if self.worker is not None:
            return (
                False,
                f"{project.name} already has a bounded Studio operation in progress. Wait for its "
                "verified result before planning. NO BUILD OR PHONE ACTION STARTED.",
            )
        return (
            True,
            f"{project.name} has a contained working tree. Choose Plan build (dry-run) below to "
            "freeze the exact inputs and run Guardian preflight. Execution remains locked; "
            "NO BUILD OR PHONE ACTION STARTED.",
        )

    def prebuild_simulation_ready(self) -> bool:
        """Report the same current-project readiness used by the Simulation handoff."""

        ready, _detail = self._prebuild_simulation_handoff()
        return ready

    def _open_prebuild_simulation_destination(self, ready: bool) -> str:
        """Open the existing action that owns the current Simulation prerequisite."""

        project = self.current_project
        inputs_ready = bool(
            project is not None
            and project.original is not None
            and self.inspection.load_report(project.project_id) is not None
            and self.inspection.working_tree_exists(project.project_id)
        )
        if ready or inputs_ready:
            self.command_tabs.setCurrentIndex(1)
            self.plan_button.setFocus(Qt.FocusReason.OtherFocusReason)
            return "Build & Proof"

        self.command_tabs.setCurrentIndex(0)
        target = (
            self.new_button
            if project is None
            else self.import_button
            if project.original is None
            else self.inspect_button
            if self.inspection.load_report(project.project_id) is None
            else self.working_button
            if self.store.working_copy(project.project_id) is None
            else self.extract_button
        )
        target.setFocus(Qt.FocusReason.OtherFocusReason)
        return "Source Lab prerequisite"

    def _recipe_forge_handoff(self) -> tuple[bool, str]:
        project = self.current_project
        if project is None:
            return (
                False,
                "Create or select a ROM project and prepare a contained working tree before "
                "designing a recipe. NO RECIPE OR PHONE ACTION STARTED.",
            )
        if project.original is None:
            return (
                False,
                f"{project.name} needs a protected original before Recipe Forge can target its "
                "contents. NO RECIPE OR PHONE ACTION STARTED.",
            )
        if not self.inspection.working_tree_exists(project.project_id):
            return (
                False,
                f"{project.name} needs a contained working tree. Complete Source Lab preparation, "
                "then return to Recipe Forge. NO RECIPE OR PHONE ACTION STARTED.",
            )
        if self.worker is not None:
            return (
                False,
                f"{project.name} already has a bounded Studio operation in progress. Wait for its "
                "verified result before opening Recipe Forge. NO RECIPE OR PHONE ACTION STARTED.",
            )
        return (
            True,
            f"{project.name} is ready for Recipe Forge. Open the guided designer below to choose "
            "contained targets, preview changes, and preserve rollback evidence. Nothing changes "
            "until explicit approval; NO PHONE ACTION STARTED.",
        )

    def _open_recipe_forge_destination(self, ready: bool) -> str:
        """Open Recipe Forge or the existing action that owns its current prerequisite."""

        project = self.current_project
        inputs_ready = bool(
            project is not None
            and project.original is not None
            and self.inspection.working_tree_exists(project.project_id)
        )
        if ready or inputs_ready:
            self.command_tabs.setCurrentIndex(2)
            self.guided_recipe_button.setFocus(Qt.FocusReason.OtherFocusReason)
            return "Recipe Forge"

        self.command_tabs.setCurrentIndex(0)
        target = (
            self.new_button
            if project is None
            else self.import_button
            if project.original is None
            else self.working_button
            if self.store.working_copy(project.project_id) is None
            else self.extract_button
        )
        target.setFocus(Qt.FocusReason.OtherFocusReason)
        return "Source Lab prerequisite"

    def _show_dashboard_handoff(
        self,
        title: str,
        detail: str,
        badge: str,
        *,
        ready: bool,
        eyebrow: str = "COMMAND DECK HANDOFF  •  EXACT ROM STUDIO WORKFLOW",
    ) -> None:
        self.dashboard_handoff_eyebrow.setText(eyebrow)
        self.dashboard_handoff_title.setText(title)
        self.dashboard_handoff_detail.setText(detail)
        self.dashboard_handoff_badge.setText(badge)
        self.dashboard_handoff_badge.setObjectName("Good" if ready else "Warning")
        self._repolish(self.dashboard_handoff_badge)
        self.dashboard_handoff.setVisible(True)

    def request_time_machine(self) -> bool:
        """Open Time Machine only with the exact selected Studio project identity."""

        project = self.current_project
        if project is None:
            self.outbound_handoff_stopped(
                "Time Machine",
                "No exact ROM project is selected",
            )
            return False
        self.time_machine_requested.emit(project.project_id)
        return True

    def open_time_machine_setup_handoff(self, project_id: str) -> bool:
        """Open the exact missing prerequisite requested by Time Machine."""

        normalized = str(project_id).strip()
        self.command_tabs.setCurrentIndex(0)
        if not normalized:
            if self.store.list_projects():
                return False
            self.refresh()
            self._show_dashboard_handoff(
                "Time Machine → protected recovery project",
                "No ROM project exists. Create one, import its exact protected firmware, then "
                "prepare a working baseline before taking a Time Machine snapshot. The New "
                "project control is focused; no dialog or worker was started automatically. "
                "NO PROJECT, SNAPSHOT, RESTORE, BUILD, OR PHONE ACTION STARTED.",
                "PROJECT REQUIRED",
                ready=False,
                eyebrow="TIME MACHINE HANDOFF  •  EXACT MISSING RECOVERY PREREQUISITE",
            )
            self.new_button.setFocus(Qt.FocusReason.OtherFocusReason)
            return True

        try:
            project = self.store.get(normalized)
        except (OSError, ProjectError, TypeError, ValueError):
            return False
        if self.store.list_snapshots(project.project_id):
            return False
        self.refresh(project.project_id)
        if self.current_project is None or self.current_project.project_id != project.project_id:
            return False
        working = self.store.working_copy(project.project_id)
        if project.original is None:
            next_step = "Import original"
            detail = (
                "needs its exact protected firmware source before a recovery baseline can exist"
            )
            focus = self.import_button
        elif working is None:
            next_step = "Create working copy"
            detail = "has protected source evidence but no isolated working baseline"
            focus = self.working_button
        else:
            next_step = "Time Machine snapshot"
            detail = "has an isolated working baseline ready for a verified local snapshot"
            focus = self.snapshot_button
        self._show_dashboard_handoff(
            f"Time Machine → {project.name}",
            f"Exact project {project.project_id} {detail}. Continue with {next_step}; ROM Studio "
            "will preserve its normal verification and approval boundaries. NO PROJECT WORKER, "
            "SNAPSHOT, RESTORE, BUILD, FLASH, OR PHONE ACTION STARTED.",
            next_step.upper(),
            ready=focus.isEnabled(),
            eyebrow="TIME MACHINE HANDOFF  •  EXACT MISSING RECOVERY PREREQUISITE",
        )
        self.detail_scroll.ensureWidgetVisible(self.command_tabs, 0, 24)
        focus.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def request_device_atlas(self) -> bool:
        """Open Device Atlas only with the exact selected Studio project identity."""

        project = self.current_project
        if project is None:
            self.outbound_handoff_stopped(
                "Device Atlas",
                "No exact ROM project is selected",
            )
            return False
        self.device_packs_requested.emit(project.project_id)
        return True

    def request_device_center(self, intent: str) -> bool:
        """Open Command Deck only with one exact selected project and bounded purpose."""

        project = self.current_project
        if project is None or intent not in {"build-readiness", "ascension-refresh"}:
            self.outbound_handoff_stopped(
                "Command Deck",
                "No exact ROM project or approved device-evidence purpose is selected",
            )
            return False
        self.device_center_requested.emit(project.project_id, intent)
        return True

    def request_toolchain(self, intent: str = "build-readiness") -> bool:
        """Open Forge Arsenal with the exact selected project and bounded purpose."""

        project = self.current_project
        if project is None or project.original is None or intent != "build-readiness":
            self.outbound_handoff_stopped(
                "Forge Arsenal",
                "No exact protected ROM source or approved tool-evidence purpose is selected",
            )
            return False
        self.toolchain_requested.emit(project.project_id, intent)
        return True

    def outbound_handoff_stopped(self, destination: str, reason: str) -> None:
        """Keep a refused outbound route visible without changing project or phone state."""

        self.operation_status.setText(
            f"{destination.upper()} HANDOFF STOPPED  •  {reason}  •  "
            "NO WORKER, BUILD, APPROVAL, FLASH, RESTORE, OR PHONE ACTION STARTED"
        )
        self.operation_status.setObjectName("Danger")
        self._repolish(self.operation_status)

    def open_guardian_handoff(self, manifest: GuardianManifestReview) -> bool:
        """Return from Guardian Core to the exact command-free Studio review context."""

        if not isinstance(manifest, GuardianManifestReview):
            return False
        persisted = GuardianManifestReviewService(self.store, self.pack_registry).load(
            manifest.project_id
        )
        if persisted != manifest:
            return False
        try:
            project = self.store.get(manifest.project_id)
            self.refresh(project.project_id)
        except (OSError, ProjectError, TypeError, ValueError):
            return False
        self.command_tabs.setCurrentIndex(1)
        bound = len(manifest.partition_writes)
        self._show_dashboard_handoff(
            f"Guardian Core → {project.name}",
            f"Exact manifest {manifest.manifest_digest[:16]}… is selected for project "
            f"{project.project_id}  •  {manifest.device_name} / {manifest.codename}  •  "
            f"{bound} image(s) hash-bound for review  •  status "
            f"{manifest.review_status.replace('-', ' ')}. Execution authority: NONE  •  "
            "final consent: LOCKED  •  bootloader relock: NEVER  •  PHONE CHANGED: NO.",
            "REVIEW ONLY",
            ready=False,
            eyebrow="GUARDIAN CORE HANDOFF  •  EXACT COMMAND-FREE MANIFEST",
        )
        self.detail_scroll.ensureWidgetVisible(self.command_tabs, 0, 24)
        self.build_control_button.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def open_command_deck_handoff(
        self,
        project_id: str,
        source_sha256: str,
        intent: str,
    ) -> bool:
        """Return from Command Deck to the exact source-bound Studio project."""

        if intent not in {"build-readiness", "ascension-refresh"}:
            return False
        try:
            project = self.store.get(project_id)
        except (OSError, ProjectError, TypeError, ValueError):
            return False
        if project.original is None or project.original.sha256 != source_sha256:
            return False
        self.refresh(project.project_id)
        profile = self.device_dna.profiles.load(project.project_id)
        expected_model = (
            profile.fact("identity.model").value
            if profile and profile.fact("identity.model")
            else ""
        )
        expected_codename = (
            profile.fact("identity.codename").value
            if profile and profile.fact("identity.codename")
            else ""
        )
        matching = next(
            (
                device
                for device in self.devices
                if device.state is DeviceState.DEVICE
                and (not expected_model or device.model.casefold() == expected_model.casefold())
                and (
                    not expected_codename
                    or device.codename.casefold() == expected_codename.casefold()
                    or device.product.casefold() == expected_codename.casefold()
                )
            ),
            None,
        )
        target = matching.display_name if matching is not None else "no exact authorized target"
        if intent == "build-readiness":
            self.command_tabs.setCurrentIndex(1)
            focus = self.build_control_button
            purpose = "Forge Control device prerequisite"
        else:
            focus = self.ascension_button
            purpose = "Ascension target refresh"
        self._show_dashboard_handoff(
            f"Command Deck → {project.name}",
            f"Exact project {project.project_id}  •  protected source {source_sha256[:16]}…  •  "
            f"{purpose}  •  target evidence: {target}. The scan granted no build, root, approval, "
            "flash, wipe, or relock authority; NO PROJECT WORKER OR PHONE-CHANGING ACTION STARTED.",
            "TARGET EVIDENCE REVIEWED" if matching is not None else "TARGET EVIDENCE NEEDED",
            ready=matching is not None,
            eyebrow="COMMAND DECK HANDOFF  •  EXACT PROJECT / READ-ONLY DEVICE EVIDENCE",
        )
        focus.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def open_forge_toolchain_handoff(
        self,
        project_id: str,
        source_sha256: str,
        context_digest: str,
        required_tools: tuple[str, ...],
        build_contract_bound: bool,
    ) -> bool:
        """Return freshly verified host-tool evidence to the exact Studio project."""

        try:
            project = self.store.get(project_id)
        except (OSError, ProjectError, TypeError, ValueError):
            return False
        if (
            project.original is None
            or project.original.sha256 != source_sha256
            or not re.fullmatch(r"[0-9a-f]{64}", context_digest)
            or not required_tools
        ):
            return False
        self.refresh(project.project_id)
        statuses = {status.name: status for status in self.tool_statuses}
        missing = tuple(
            name for name in required_tools if name not in statuses or not statuses[name].available
        )
        ready = len(required_tools) - len(missing)
        self.command_tabs.setCurrentIndex(1)
        self._show_dashboard_handoff(
            f"Forge Arsenal → {project.name}",
            f"Exact project {project.project_id}  •  protected source {source_sha256[:16]}…  •  "
            f"tool context {context_digest[:16]}…  •  {ready}/{len(required_tools)} required host "
            f"tools verified  •  missing: {' • '.join(missing) if missing else 'none'}  •  "
            f"source-matched Device Pack contract: {'YES' if build_contract_bound else 'NO'}. "
            "Forge returned host evidence only; NO PROJECT WORKER, BUILD, ROOT, APPROVAL, FLASH, "
            "WIPE, RELOCK, OR PHONE ACTION STARTED.",
            "HOST TOOLS VERIFIED" if not missing else "HOST TOOLS NEED ATTENTION",
            ready=not missing,
            eyebrow="FORGE ARSENAL HANDOFF  •  EXACT PROJECT / SOURCE-BOUND HOST EVIDENCE",
        )
        self.detail_scroll.ensureWidgetVisible(self.command_tabs, 0, 24)
        self.build_control_button.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def open_device_atlas_handoff(
        self,
        report: DevicePackValidationReport,
        intent: str,
        *,
        source: str = "Device Atlas",
        device: AndroidDevice | None = None,
        device_dna: DeviceDnaProfile | None = None,
        compatibility: CompatibilityMatrix | None = None,
        launch_genesis: bool = False,
    ) -> bool:
        """Accept one current exact Pack contract without inheriting execution authority."""

        if source not in {"Device Atlas", "Forge Arsenal", "Time Machine"}:
            return False
        if intent not in {"genesis", "build", "artifact"}:
            return False
        if not isinstance(report, DevicePackValidationReport):
            return False
        pack = next(
            (
                candidate
                for candidate in self.pack_registry.packs
                if candidate.pack_id == report.pack_id
            ),
            None,
        )
        if (
            pack is None
            or report.pack_version != pack.version
            or report.pack_sha256 != pack.sha256
            or (intent != "genesis" and not report.build_contract_ready)
        ):
            return False
        if device is not None and (
            len(self.devices) != 1
            or self.devices[0].serial != device.serial
            or report.manufacturer.casefold() != (device.manufacturer or "Unknown OEM").casefold()
            or report.model.casefold() != (device.model or "Unknown model").casefold()
            or report.product.casefold() != (device.product or "Unknown product").casefold()
            or report.codename.casefold()
            != (device.codename or device.product or "Unknown codename").casefold()
        ):
            return False
        if device_dna is not None:
            project = self.current_project
            current_dna = (
                self.device_dna.profiles.load(project.project_id)
                if project is not None and project.original is not None
                else None
            )
            live_identity = next(
                (
                    evidence
                    for evidence in device_dna.evidence
                    if evidence.evidence_id == "device.live"
                ),
                None,
            )
            if (
                device is None
                or current_dna is None
                or current_dna.profile_digest != device_dna.profile_digest
                or live_identity is None
                or live_identity.source_ref != device.masked_serial()
            ):
                return False
        if compatibility is not None and (
            device_dna is None
            or compatibility.project_id != device_dna.project_id
            or compatibility.device_dna_digest != device_dna.profile_digest
            or compatibility.bootloader_relock_permitted
            or not compatibility.guardian_advisory_only
        ):
            return False
        if source == "Forge Arsenal":
            contract = pack.build_contract
            statuses = {status.name: status for status in self.tool_statuses}
            if contract is None or any(
                name not in statuses or not statuses[name].available
                for name in contract.required_tools
            ):
                return False

        project = self.current_project
        if project is None:
            project_context = (
                "No ROM project is selected. Create one and import the exact protected firmware; "
                "the Device Pack cannot substitute for source bytes."
            )
        elif project.device_pack_id == pack.pack_id:
            project_context = f"Current project {project.name} is associated with this Pack."
        else:
            project_context = (
                f"Current project {project.name} is not associated with Pack {pack.pack_id}; "
                "select or create the correct protected-source project before planning."
            )
        build = "READY" if report.build_contract_ready else "EVIDENCE NEEDED"
        flash = "READY" if report.flash_contract_ready else "LOCKED"
        intelligence = ""
        if device is not None:
            intelligence += f"selected target {device.masked_serial()}  •  "
        if device_dna is not None:
            intelligence += f"Device DNA {device_dna.profile_digest[:16]}…  •  "
        if compatibility is not None:
            guardian_flash = compatibility.decision("guardian_flash")
            compatibility_state = (
                guardian_flash.status.value if guardian_flash is not None else "Unknown"
            )
            intelligence += (
                f"Compatibility {compatibility_state} ({compatibility.matrix_digest[:16]}…)  •  "
            )
        if intent == "genesis":
            title = f"{source} → Genesis Sequence"
            next_step = (
                "Genesis will re-check project source binding and resume at the exact safe stage."
            )
            tab_index = 0
            focus = self.guided_button
        elif intent == "artifact":
            title = f"{source} → verified artifact build"
            next_step = (
                "Build & Proof is selected; Forge Control will independently revalidate every "
                "artifact, signing, recovery, and flash gate."
            )
            tab_index = 1
            focus = self.build_control_button
        else:
            title = f"{source} → Build & Proof"
            next_step = (
                "Build & Proof is selected for a deterministic plan; execution remains locked."
            )
            tab_index = 1
            focus = self.plan_button
        self.command_tabs.setCurrentIndex(tab_index)
        self._show_dashboard_handoff(
            title,
            f"{report.model} / {report.codename}  •  {intelligence}"
            f"Pack {pack.pack_id} v{pack.version}  •  "
            f"report {report.report_digest[:16]}…  •  build {build}  •  flash {flash}. "
            f"{project_context} {next_step} NO BUILD, APPROVAL, FLASH, OR PHONE ACTION STARTED.",
            f"BUILD {build} • FLASH {flash}",
            ready=report.build_contract_ready,
            eyebrow=f"{source.upper()} HANDOFF  •  EXACT CURRENT DEVICE EVIDENCE",
        )
        self.detail_scroll.ensureWidgetVisible(self.command_tabs, 0, 24)
        focus.setFocus(Qt.FocusReason.OtherFocusReason)
        if intent == "genesis" and launch_genesis:
            self._open_guided_setup()
        return True

    def open_device_atlas_source_handoff(
        self,
        project_id: str,
        source_sha256: str,
        blueprint_digest: str,
        plan_digest: str,
        source_kind: str,
        intent: str,
    ) -> bool:
        """Reopen one exact project-local source blueprint without inheriting authority."""

        if (
            self.worker is not None
            or self.current_project is None
            or self.current_project.project_id != project_id
            or intent not in {"build", "artifact"}
            or source_kind not in {"ota-payload", "fastboot-super", "partition-bundle"}
            or re.fullmatch(r"[0-9a-f]{64}", source_sha256) is None
            or re.fullmatch(r"[0-9a-f]{64}", blueprint_digest) is None
            or re.fullmatch(r"[0-9a-f]{64}", plan_digest) is None
        ):
            return False
        try:
            project = self.store.get(project_id)
            blueprint = FirmwareSourceIntelligenceService(
                self.store,
                self.tool_statuses,
                SubprocessRunner(),
            ).load(project_id)
        except (OSError, ProjectError, TypeError, ValueError):
            return False
        expected_authority = {
            "ota-payload": "project-local-build-evidence-only",
            "fastboot-super": "project-local-build-evidence-only",
            "partition-bundle": "project-local-inventory-evidence-only",
        }[source_kind]
        if (
            project.original is None
            or project.original.sha256 != source_sha256
            or blueprint is None
            or blueprint.project_id != project.project_id
            or blueprint.source_archive_sha256 != source_sha256
            or blueprint.source_kind != source_kind
            or blueprint.blueprint_digest != blueprint_digest
            or blueprint.plan_digest != plan_digest
            or blueprint.authority != expected_authority
            or blueprint.phone_changed
            or not blueprint.baseline_candidate_ready
        ):
            return False
        self.refresh(project_id)
        if self.current_project is None or self.current_project.project_id != project_id:
            return False
        self.command_tabs.setCurrentIndex(1)
        title = (
            "Device Atlas → exact artifact review"
            if intent == "artifact"
            else "Device Atlas → project Build & Proof"
        )
        next_step = (
            "Build & Proof will independently revalidate the artifact, Device Pack, recovery, "
            "AVB, partition-write, and Guardian gates."
            if intent == "artifact"
            else "Build & Proof can continue from the verified local source baseline; it will "
            "independently revalidate every later build and Guardian gate."
        )
        self._show_dashboard_handoff(
            title,
            f"Exact project {project.project_id}  •  {blueprint.manufacturer} / "
            f"{blueprint.codename} / {blueprint.build_id}  •  protected source "
            f"{source_sha256[:16]}…  •  strict {source_kind} blueprint "
            f"{blueprint_digest[:16]}…  •  source plan {plan_digest[:16]}…  •  "
            f"{len(blueprint.partitions)} partition records. Local baseline READY; flash "
            f"authority NONE. {next_step} NO PROJECT WORKER, PLAN, BUILD, APPROVAL, FLASH, "
            "WIPE, RELOCK, OR PHONE ACTION STARTED.",
            "PROJECT SOURCE VERIFIED • FLASH LOCKED",
            ready=True,
            eyebrow="DEVICE ATLAS HANDOFF  •  EXACT PROJECT / SOURCE BLUEPRINT",
        )
        self.detail_scroll.ensureWidgetVisible(self.command_tabs, 0, 24)
        (self.build_control_button if intent == "artifact" else self.plan_button).setFocus(
            Qt.FocusReason.OtherFocusReason
        )
        return True

    def open_nexus_handoff(self, project_id: str, plan_digest: str = "") -> bool:
        """Open the exact Nexus project or its honest project-creation prerequisite."""

        normalized = str(project_id).strip()
        normalized_digest = str(plan_digest).strip().casefold()
        if not normalized:
            if normalized_digest:
                return False
            self.command_tabs.setCurrentIndex(0)
            self._show_dashboard_handoff(
                "ROMVERSE Nexus → protected project creation",
                "Nexus has no project to bind. Create a ROM project and import protected "
                "firmware before Device DNA, Compatibility Matrix, or route planning can exist. "
                "NO PROJECT WORKER, PLAN, BUILD, OR PHONE ACTION STARTED.",
                "PROJECT REQUIRED",
                ready=False,
                eyebrow="ROMVERSE NEXUS HANDOFF  •  EXACT PROJECT EVIDENCE",
            )
            self.new_button.setFocus(Qt.FocusReason.OtherFocusReason)
            return True
        try:
            project = self.store.get(normalized)
            self.refresh(project.project_id)
        except (OSError, ProjectError, TypeError, ValueError):
            return False
        profile = self.device_dna.profiles.load(project.project_id)
        matrix = self.compatibility.matrices.load(project.project_id)
        nexus_plan = NexusPlanStore(self.store).load(project.project_id)
        if normalized_digest and (
            nexus_plan is None or nexus_plan.plan_digest != normalized_digest
        ):
            return False
        if not normalized_digest and nexus_plan is not None:
            return False
        missing = tuple(
            label
            for label, available in (
                ("Device DNA", profile is not None),
                ("Compatibility Matrix", matrix is not None),
            )
            if not available
        )
        if missing:
            self.command_tabs.setCurrentIndex(0)
            self._show_dashboard_handoff(
                f"ROMVERSE Nexus → {project.name}",
                f"Exact project {project.project_id} is selected. Missing: {', '.join(missing)}. "
                "Genesis will derive them only from this project's protected evidence. "
                "NO PROJECT WORKER, PLAN, BUILD, OR PHONE ACTION STARTED.",
                "EVIDENCE REQUIRED",
                ready=False,
                eyebrow="ROMVERSE NEXUS HANDOFF  •  EXACT PROJECT EVIDENCE",
            )
            self.guided_button.setFocus(Qt.FocusReason.OtherFocusReason)
            return True
        build_plan = RomBuildPlanner(self.store).load(project.project_id)
        nexus_context = (
            f"Nexus plan {nexus_plan.plan_digest[:16]}…  •  objective "
            f"{nexus_plan.objective.value.replace('-', ' ').replace('_', ' ')}  •  status "
            f"{nexus_plan.status.value.replace('-', ' ').replace('_', ' ')}. "
            if nexus_plan is not None
            else "No Nexus plan has been generated for this current evidence. "
        )
        self.command_tabs.setCurrentIndex(1)
        self._show_dashboard_handoff(
            f"ROMVERSE Nexus → {project.name}",
            f"Exact project {project.project_id} is selected with current Device DNA and "
            f"Compatibility Matrix evidence. {nexus_context}Build plan: "
            f"{'available' if build_plan is not None else 'not yet created'}. "
            "Build & Proof is selected; NO PROJECT WORKER, PLAN, BUILD, OR PHONE ACTION STARTED.",
            "EVIDENCE READY",
            ready=True,
            eyebrow="ROMVERSE NEXUS HANDOFF  •  EXACT PROJECT EVIDENCE",
        )
        self.detail_scroll.ensureWidgetVisible(self.command_tabs, 0, 24)
        (self.verify_plan_button if build_plan is not None else self.plan_button).setFocus(
            Qt.FocusReason.OtherFocusReason
        )
        return True

    def guided_context(self, state: GuidedMissionState | None = None) -> GuidedContext:
        """Compile the single evidence context consumed by every Genesis surface."""

        project = self.current_project
        if project is None:
            return GuidedContext(
                device=self.devices[0] if self.devices else None,
                observed_devices=tuple(self.observed_devices),
                device_scan_error=self.device_scan_error,
                tool_statuses=self.tool_statuses,
            )
        project_id = project.project_id
        state = state or GuidedMissionStore(self.store.projects_root / project_id).load()
        report = self.inspection.load_report(project_id)
        dna = self.device_dna.profiles.load(project_id)
        working = self.store.working_copy(project_id)
        tree_ready = self.inspection.working_tree_exists(project_id)
        budget_safe = tree_ready
        budget_detail = ""
        if report is not None and not tree_ready:
            try:
                budget = self.inspection.extraction_budget(project_id, report)
                budget_safe = budget.safe
                budget_detail = budget.reason
            except ProjectError as exc:
                budget_detail = str(exc)
        recipe = RecipeStore().load(self.store.projects_root / project_id)
        try:
            debloat_receipt = DebloatService(self.store).load_receipt(project_id)
        except ProjectError:
            debloat_receipt = None
        plan = RomBuildPlanner(self.store).load(project_id)
        device = self.devices[0] if self.devices else None
        authority_device = None if device is not None and device.is_simulated else device
        pack_id = ""
        selected_pack = next(
            (pack for pack in self.pack_registry.packs if pack.pack_id == project.device_pack_id),
            None,
        )
        if device is not None:
            resolution = self.pack_registry.resolve(device)
            if resolution.pack is not None:
                pack_id = resolution.pack.pack_id
        dna_evidence: list[str] = []
        if dna is not None:
            if any(item.evidence_id == "device.simulation" for item in dna.evidence):
                dna_evidence.append(
                    "SIMULATION ONLY • NOT HARDWARE VERIFIED • live-target, consent, Guardian, "
                    "and execution authority: NONE"
                )
            identity = next(
                (
                    fact.value
                    for fact_id in (
                        "identity.marketing_name",
                        "identity.model",
                        "identity.codename",
                    )
                    if (fact := dna.fact(fact_id)) is not None
                    and fact.value.casefold() != "unconfirmed"
                ),
                "Identity remains unconfirmed",
            )
            state_counts: dict[str, int] = {}
            for capability in dna.capabilities:
                capability_state = capability.state.value.upper()
                state_counts[capability_state] = state_counts.get(capability_state, 0) + 1
            summary = ", ".join(
                f"{capability_state} {state_counts.get(capability_state, 0)}"
                for capability_state in (
                    "SUPPORTED",
                    "CAUTION",
                    "UNSUPPORTED",
                    "UNCONFIRMED",
                )
            )
            dna_evidence.extend(
                (
                    f"Device DNA identity: {identity}",
                    f"Device DNA evidence: {dna.profile_digest[:16]}… current source-bound profile",
                    f"Capability Map: {summary}",
                )
            )
            for capability_id in (
                "device_identity",
                "firmware_detection",
                "source_adapter",
                "tool_resolution",
            ):
                capability = dna.capability(capability_id)
                if capability is not None:
                    dna_evidence.append(
                        f"{capability.label}: {capability.state.value.upper()} — {capability.detail}"
                    )
            dna_evidence.append("Bootloader relocking: UNSUPPORTED • permanent Guardian rule")
            matrix = self.compatibility.matrices.load(project_id)
            if matrix is not None and matrix.device_dna_digest == dna.profile_digest:
                guardian_flash = matrix.decision("guardian_flash")
                if guardian_flash is not None:
                    dna_evidence.append(
                        f"Guardian Flash: {guardian_flash.status.value} • Compatibility Matrix "
                        f"{matrix.matrix_digest[:16]}… • advisory only; zero execution authority"
                    )

        boot_observation_stable = False
        first_boot_verified = False
        flash_complete = False
        boot_service = BootObservationService(self.store, self.pack_registry)
        try:
            boot_receipt = boot_service.load(
                project_id,
                verified_flash=self._latest_guardian_execution_result,
                device=authority_device,
            )
        except ProjectError:
            boot_receipt = None
        if boot_receipt is not None:
            flash_complete = boot_receipt.flash_linked
            if boot_receipt.status is BootObservationStatus.STABLE:
                boot_observation_stable = True
                first_boot_verified = boot_receipt.verified_first_boot
        if (
            not flash_complete
            and authority_device is not None
            and self._latest_guardian_execution_result
        ):
            try:
                boot_service.verified_flash_digest(
                    project_id,
                    authority_device,
                    self._latest_guardian_execution_result,
                )
                flash_complete = True
            except ProjectError:
                pass

        # This bounded historical read validates private parent/child receipts and
        # current recorded source identity. It never grants fresh-byte or phone authority.
        try:
            local_outcome = ProjectFlashPreparationService(
                self.store, self.pack_registry
            ).load_latest(project_id)
        except (OSError, ProjectError):
            local_outcome = None
        if not isinstance(local_outcome, ProjectFlashOutcome) or (
            local_outcome.project_id != project_id
            or project.original is None
            or local_outcome.source_sha256 != project.original.sha256
        ):
            local_outcome = None
        try:
            source_outcome = load_latest_source_installation(self.store, project_id)
        except (OSError, ProjectError):
            source_outcome = None
        if not isinstance(source_outcome, SourceInstallationOutcome) or (
            source_outcome.project_id != project_id
            or project.original is None
            or source_outcome.source_sha256 != project.original.sha256
        ):
            source_outcome = None

        readiness = BuildReadinessService(
            self.store,
            self.pack_registry,
            self.tool_statuses,
            self.attestation_store,
        ).assess(
            project_id,
            tuple(item for item in self.devices if not item.is_simulated),
            persist=False,
        )
        handoff_service = GuardianFlashHandoffService(self.store)
        flash_handoff = handoff_service.load(project_id)
        flash_handoff_ready = bool(
            readiness.flash_ready
            and flash_handoff is not None
            and handoff_service.matches_current(
                project_id, flash_handoff, authority_device, readiness
            )
        )
        ascension_complete = False
        ascension_integrated = False
        if state.root_choice in {"skip", "ascension"}:
            for method in AscensionMethod:
                integration = RootRomIntegrationService(self.store).load(project_id, method)
                ascension_integrated = ascension_integrated or integration is not None
                build_seal = RootRomBuildHandoffService(self.store).load(project_id, method)
                root_plan = AscensionRootPlanService(self.store).load(project_id, method)
                if build_seal is not None and root_plan is not None:
                    ascension_complete = True
                    break
        return GuidedContext(
            project_exists=True,
            original_imported=project.original is not None,
            inspection_saved=report is not None,
            working_copy_ready=working is not None,
            working_tree_ready=tree_ready,
            extraction_budget_safe=budget_safe,
            extraction_budget_detail=budget_detail,
            device=device,
            observed_devices=tuple(self.observed_devices),
            device_scan_error=self.device_scan_error,
            device_pack_id=pack_id or project.device_pack_id,
            device_dna_ready=dna is not None,
            capability_map_ready=bool(dna and dna.capabilities),
            device_dna_evidence=tuple(dna_evidence),
            recipe_saved=recipe is not None,
            recipe_validated=state.recipe_validated,
            recipe_skipped=state.recipe_skipped,
            customization_skipped=state.customization_skipped,
            debloat_complete=debloat_receipt is not None,
            root_choice=state.root_choice,
            ascension_integrated=ascension_integrated,
            ascension_complete=ascension_complete,
            build_plan_saved=plan is not None,
            build_plan_verified=state.build_plan_verified and plan is not None,
            recovery_snapshot_ready=any(
                snapshot.schema_version == 2 for snapshot in self.store.list_snapshots(project_id)
            ),
            tool_statuses=self.tool_statuses,
            build_artifact_ready=readiness.local_candidate_ready,
            signed_artifact_ready=readiness.signing_ready,
            install_requested=state.install_requested,
            # Genesis opens Guardian as soon as every safe automatic
            # prerequisite is complete. Guardian owns the remaining backup
            # choice, flash mode, manifest review, and final consent.
            guardian_handoff_ready=readiness.guardian_handoff_ready,
            guardian_flash_handoff_ready=flash_handoff_ready,
            guardian_flash_mode=(
                flash_handoff.mode.display_name
                if flash_handoff_ready and flash_handoff is not None
                else ""
            ),
            flash_complete=flash_complete,
            boot_observation_stable=boot_observation_stable,
            first_boot_verified=first_boot_verified,
            local_image_state=local_outcome.state if local_outcome is not None else "",
            local_image_summary=local_outcome.summary if local_outcome is not None else "",
            local_image_count=local_outcome.selected_image_count
            if local_outcome is not None
            else 0,
            local_image_boot_status=local_outcome.boot_status if local_outcome is not None else "",
            source_installation_state=source_outcome.state if source_outcome else "",
            source_installation_summary=source_outcome.summary if source_outcome else "",
            source_installation_completed_count=source_outcome.completed_count
            if source_outcome
            else 0,
            source_installation_expected_count=source_outcome.expected_count
            if source_outcome
            else 0,
            source_installation_boot_status=source_outcome.boot_status if source_outcome else "",
            required_tools=required_tools_for_source(
                selected_pack.build_contract
                if selected_pack is not None
                and selected_pack.build_contract is not None
                and project.original is not None
                and selected_pack.build_contract.source.archive_sha256 == project.original.sha256
                else None,
                report.partition_signals if report is not None else (),
            ),
        )

    def register_guardian_execution_result(
        self,
        result: VerifiedGuardianExecutionResult,
    ) -> bool:
        """Bind one already verified successful Guardian result to the active mission."""

        project = self.current_project
        device = self.devices[0] if len(self.devices) == 1 else None
        if project is None or device is None or device.is_simulated:
            return False
        try:
            BootObservationService(self.store, self.pack_registry).verified_flash_digest(
                project.project_id,
                device,
                result,
            )
        except ProjectError:
            return False
        self._latest_guardian_execution_result = result
        self.guardian_flash_verified.emit(device.serial, project.name, result)
        return True

    def genesis_flight_plan(self) -> GenesisFlightPlan:
        """Summarize the exact stage Genesis Sequence would resume from."""

        project = self.current_project
        state = (
            GuidedMissionStore(self.store.projects_root / project.project_id).load()
            if project is not None
            else GuidedMissionState()
        )
        context = self.guided_context(state)
        assessments = GuidedMissionEngine().assess(context)
        index = GuidedMissionEngine.current_index(assessments)
        current = assessments[index]
        verified = sum(
            assessment.status is GuidedStageStatus.COMPLETE for assessment in assessments
        )
        root_route = (
            "Unrooted build"
            if state.root_choice == "skip"
            else "Ascension Protocol"
            if state.root_choice == "ascension"
            else "Decision pending"
        )
        return GenesisFlightPlan(
            project_name=project.name if project is not None else "No active project",
            stage_number=current.stage.number,
            stage_total=len(assessments),
            stage_title=current.stage.title,
            status=current.status,
            progress_percent=GuidedMissionEngine.progress(assessments),
            verified_stages=verified,
            blockers=current.blockers,
            recommendation=current.stage.recommendation,
            action_label=current.stage.action_label,
            root_route=root_route,
            recovery_ready=context.recovery_snapshot_ready,
            guardian_ready=context.guardian_flash_handoff_ready,
            has_saved_error=bool(state.last_error),
        )

    def _open_ascension_protocol(self, parent: QWidget | None = None) -> None:
        if self.current_project is None:
            QMessageBox.information(
                self,
                "Ascension Protocol",
                "Create or select a ROM project before starting root preparation.",
            )
            return
        from romverse.ui.ascension_protocol import AscensionProtocolDialog

        AscensionProtocolDialog(self, parent or self).exec()
        self.ascension_status_changed.emit()

    def set_experience_mode(self, mode: ExperienceMode) -> None:
        """Mirror the authoritative Desktop experience without changing project state."""

        try:
            selected = ExperienceMode(mode)
        except ValueError:
            selected = ExperienceMode.GUIDED
        self.app_settings = replace(self.app_settings, experience_mode=selected)
        expert = selected is ExperienceMode.EXPERT
        self.expert_button.blockSignals(True)
        self.expert_button.setChecked(expert)
        self.expert_button.blockSignals(False)
        self.expert_button.setProperty("active", expert)
        self.expert_button.setText("Return to Guided Mode" if expert else "Enter Architect Mode")
        self.expert_button.setAccessibleName(
            "Return ROMVERSE Desktop to Guided Arcana mode"
            if expert
            else "Enter ROMVERSE Desktop Expert Architect mode"
        )
        self.expert_button.style().unpolish(self.expert_button)
        self.expert_button.style().polish(self.expert_button)
        self.expert_flash_button.setVisible(expert)

    def _request_expert_flash(self) -> None:
        if self.app_settings.experience_mode is ExperienceMode.EXPERT:
            self.expert_flash_requested.emit()

    def _request_project_flash(self, project_id: str = "", *, source_sha256: str = "") -> bool:
        """Open project-bound image preparation, never approve or execute a phone write."""

        project = self.current_project
        if project is None or (project_id and project.project_id != project_id):
            self.operation_status.setText(
                "The selected project changed. Reopen image preparation from the intended project."
            )
            return False
        if self.worker is not None:
            self.operation_status.setText(
                "Wait for the current project operation before preparing image installation."
            )
            return False
        try:
            current = self.store.get(project.project_id)
        except ProjectError as exc:
            self.operation_status.setText(str(exc))
            return False
        if current.original is None or (source_sha256 and current.original.sha256 != source_sha256):
            self.operation_status.setText(
                "The protected firmware source is missing or changed. Review the current source first."
            )
            return False
        self.project_flash_requested.emit(current.project_id)
        return True

    def _request_source_installation_history(self, project_id: str, source_sha256: str) -> bool:
        """Dispatch historical review only; never turn a boot check into installation."""
        project = self.current_project
        if project is None or project.project_id != project_id or self.worker is not None:
            return False
        try:
            current = self.store.get(project_id)
        except ProjectError:
            return False
        if current.original is None or current.original.sha256 != source_sha256:
            self.operation_status.setText(
                "The project source changed. Reopen its installation history."
            )
            return False
        self.source_installation_history_requested.emit(project_id)
        return True

    def _request_source_installation_recovery(self, project_id: str, source_sha256: str) -> bool:
        """Dispatch sealed interrupted-operation evidence to diagnosis, never execution."""

        project = self.current_project
        if project is None or project.project_id != project_id or self.worker is not None:
            return False
        try:
            current = self.store.get(project_id)
        except ProjectError:
            return False
        if current.original is None or current.original.sha256 != source_sha256:
            self.operation_status.setText(
                "The project source changed. Reopen Genesis before diagnosing this installation."
            )
            return False
        self.source_installation_recovery_requested.emit(project_id, source_sha256)
        return True

    def _toggle_architect_mode(self, enabled: bool) -> None:
        """Make the Studio mode control a genuine persisted Desktop transition."""

        selected = ExperienceMode.EXPERT if enabled else ExperienceMode.GUIDED
        if (
            selected is ExperienceMode.EXPERT
            and self.app_settings.experience_mode is not ExperienceMode.EXPERT
            and not confirm_expert_mode(self)
        ):
            self.set_experience_mode(ExperienceMode.GUIDED)
            return
        self.set_experience_mode(selected)
        self.reveal_experience_mode(selected)
        self.experience_mode_requested.emit(selected)

    def reveal_experience_mode(self, mode: ExperienceMode) -> None:
        """Reveal the selected workspace while retaining every evidence boundary."""

        selected = ExperienceMode(mode)
        if selected is ExperienceMode.EXPERT:
            self.command_tabs.setCurrentIndex(1)
            ready, detail = self._prebuild_simulation_handoff()
            self._show_dashboard_handoff(
                "Architect Mode → complete advanced workspace",
                f"{detail} Specialist Desktop routes are now visible. Projects, evidence, "
                "and receipts are unchanged. Guided Guardian sequencing is off; exact target, "
                "artifact-integrity, and command-validity guards remain active. NO WORKER, BUILD, "
                "FLASH, OR PHONE ACTION STARTED.",
                "EXPERT • ARCHITECT" if ready else "EXPERT • PREREQUISITE",
                ready=ready,
                eyebrow="ARCHITECT MODE  •  PERSISTED DESKTOP EXPERIENCE",
            )
            self.detail_scroll.ensureWidgetVisible(self.command_tabs, 0, 24)
            (self.plan_button if self.plan_button.isEnabled() else self.expert_button).setFocus(
                Qt.FocusReason.OtherFocusReason
            )
            return

        self.command_tabs.setCurrentIndex(0)
        project = self.current_project
        if project is None:
            detail = (
                "No project is selected. Guided Arcana begins with New project and a protected "
                "firmware source."
            )
            focus = self.new_button
        elif project.original is None:
            external = self.external_intake.load(project.project_id)
            detail = (
                f"{project.name} has read-only external evidence; the protected-source, build, "
                "device, and execution boundaries remain locked."
                if external is not None
                else f"{project.name} is selected and needs firmware evidence before guided "
                "preparation can continue."
            )
            focus = self.external_intake_button
        else:
            detail = (
                f"{project.name} is selected with protected source evidence. Source Lab is "
                "restored to the current safe next step."
            )
            focus = next(
                (
                    button
                    for button in (
                        self.verify_button,
                        self.inspect_button,
                        self.working_button,
                        self.extract_button,
                    )
                    if button.isEnabled()
                ),
                self.guided_button,
            )
        self._show_dashboard_handoff(
            "Guided Mode → Arcana workspace",
            f"{detail} Specialist sidebar routes are folded, but no capability, evidence, "
            "project, or Guardian boundary was removed. NO WORKER, BUILD, FLASH, OR PHONE "
            "ACTION STARTED.",
            "GUIDED • ARCANA",
            ready=True,
            eyebrow="GUIDED MODE  •  PERSISTED DESKTOP EXPERIENCE",
        )
        self.detail_scroll.ensureWidgetVisible(self.command_tabs, 0, 24)
        focus.setFocus(Qt.FocusReason.OtherFocusReason)

    def open_feature_destination(self, route: str) -> bool:
        """Open one named Studio feature without launching its operation or dialog."""

        destination = str(route).strip()
        if destination == "source_lab":
            self.command_tabs.setCurrentIndex(0)
            project = self.current_project
            if project is None:
                detail = "Create or select an exact ROM project to begin protected source work."
                focus = self.new_button
            elif project.original is None:
                external = self.external_intake.load(project.project_id)
                detail = (
                    f"{project.name} has authority-free external firmware evidence ready for a "
                    "fresh read-only reinspection."
                    if external is not None
                    else f"{project.name} is ready for read-only in-place firmware inspection or "
                    "a later deliberate protected import."
                )
                focus = self.external_intake_button
            else:
                report = self.inspection.load_report(project.project_id)
                tree_ready = self.inspection.working_tree_exists(project.project_id)
                detail = (
                    f"{project.name} has protected source {project.original.sha256[:16]}…; "
                    f"structure {'inspected' if report is not None else 'needs inspection'}; "
                    f"contained tree {'ready' if tree_ready else 'not yet prepared'}."
                )
                focus = self.verify_button
            self._show_dashboard_handoff(
                "Find Anything → Source Lab",
                f"{detail} The Source Lab tab is selected. NO FILE DIALOG, IMPORT, HASH, "
                "INSPECTION, EXTRACTION, WORKER, BUILD, FLASH, OR PHONE ACTION STARTED.",
                "SOURCE WORKSPACE" if project is not None else "PROJECT REQUIRED",
                ready=project is not None,
                eyebrow="FIND ANYTHING  •  EXACT ROM STUDIO COMMAND GROUP",
            )
            focus.setFocus(Qt.FocusReason.OtherFocusReason)
        elif destination == "build_proof":
            self.command_tabs.setCurrentIndex(1)
            ready, detail = self._prebuild_simulation_handoff()
            self._show_dashboard_handoff(
                "Find Anything → Build & Proof",
                f"{detail} The deterministic planning and verification tab is selected. "
                "NO PLAN, WORKER, BUNDLE, BUILD, SIGNING, FLASH, OR PHONE ACTION STARTED.",
                "INPUTS READY" if ready else "PREREQUISITE",
                ready=ready,
                eyebrow="FIND ANYTHING  •  EXACT ROM STUDIO COMMAND GROUP",
            )
            (self.plan_button if ready else self.command_tabs).setFocus(
                Qt.FocusReason.OtherFocusReason
            )
        elif destination == "guided_arcana":
            guided = self.app_settings.experience_mode is ExperienceMode.GUIDED
            if guided:
                self.command_tabs.setCurrentIndex(0)
            self._show_dashboard_handoff(
                "Find Anything → Guided Arcana",
                (
                    "Guided Arcana is already the persisted Desktop experience. Source Lab is "
                    "selected and the current next-safe-action guidance remains unchanged."
                    if guided
                    else "The Desktop is currently in Expert Architect mode. Choose Return to "
                    "Guided Mode to switch the persisted experience deliberately."
                )
                + " Navigation did not switch mode, change a project or evidence, start a worker, "
                "build, flash, or change a phone.",
                "ACTIVE" if guided else "MODE CHOICE REQUIRED",
                ready=guided,
                eyebrow="FIND ANYTHING  •  PERSISTED DESKTOP EXPERIENCE",
            )
            (self.command_tabs if guided else self.expert_button).setFocus(
                Qt.FocusReason.OtherFocusReason
            )
        elif destination == "forge_bundle":
            self.command_tabs.setCurrentIndex(1)
            project = self.current_project
            forge = ForgeBundleService(self.store)
            plan = (
                RomBuildPlanner(self.store).load(project.project_id)
                if project is not None
                else None
            )
            receipt = forge.load_receipt(project.project_id) if project is not None else None
            receipt_current = bool(
                receipt is not None
                and plan is not None
                and forge.receipt_matches_plan(receipt, plan)
            )
            creatable = self.forge_button.isEnabled()
            if receipt_current:
                detail = (
                    f"{project.name} has verified Forge Bundle {receipt.archive_sha256[:16]}… "
                    f"containing {receipt.file_count} file(s) and {receipt.content_bytes} bytes."
                )
                badge = "VERIFIED INTERMEDIATE"
                ready = True
                focus = self.verify_forge_button
            elif receipt is not None:
                detail = (
                    f"{project.name} has preserved Forge evidence from a different exact Build "
                    "Readiness plan. Choose Forge Bundle once to preserve it in private history "
                    "and create and verify the current generation; nothing starts automatically."
                )
                badge = "READY TO PRESERVE + CREATE"
                ready = True
                focus = self.forge_button
            elif creatable:
                detail = (
                    f"{project.name} has a verified deterministic plan ready for deliberate "
                    "Forge Bundle creation."
                )
                badge = "READY TO CREATE"
                ready = True
                focus = self.forge_button
            else:
                _planning_ready, detail = self._prebuild_simulation_handoff()
                detail += " Create and verify the exact build plan before forging the bundle."
                badge = "PREREQUISITE"
                ready = False
                focus = self.command_tabs
            self._show_dashboard_handoff(
                "Find Anything → Forge Bundle",
                f"{detail} This artifact remains unsigned, non-bootable, and non-flashable. "
                "NO WORKER, BUNDLE CREATION, BUILD, SIGNING, FLASH, OR PHONE ACTION STARTED.",
                badge,
                ready=ready,
                eyebrow="FIND ANYTHING  •  EXACT ROM STUDIO ARTIFACT",
            )
            focus.setFocus(Qt.FocusReason.OtherFocusReason)
        elif destination == "nebula_debloat":
            self.command_tabs.setCurrentIndex(2)
            project = self.current_project
            receipt = None
            if project is not None:
                with suppress(ProjectError):
                    receipt = DebloatService(self.store).load_receipt(project.project_id)
            if receipt is not None:
                detail = (
                    f"{project.name} has a current Nebula Debloat receipt for "
                    f"{receipt.removed_app_count} reviewed app group(s)."
                )
                badge = "CURRENT RECEIPT"
                ready = True
            elif project is None:
                detail = "Create or select a ROM project before entering the Genesis customization stage."
                badge = "PROJECT REQUIRED"
                ready = False
            elif self.inspection.load_report(project.project_id) is None:
                detail = f"{project.name} needs a saved structure inspection before app discovery."
                badge = "INSPECTION REQUIRED"
                ready = False
            elif not self.inspection.working_tree_exists(project.project_id):
                detail = f"{project.name} needs a contained working tree before app review."
                badge = "WORKING TREE REQUIRED"
                ready = False
            else:
                detail = (
                    f"{project.name} can enter the Nebula Debloat stage through Genesis Sequence; "
                    "the stage will verify its exact source-shape tools first."
                )
                badge = "READY FOR GENESIS REVIEW"
                ready = True
            self._show_dashboard_handoff(
                "Find Anything → Nebula Debloat",
                f"{detail} Protected apps remain locked and changes target only the isolated "
                "working tree after review. NO DIALOG, SCAN, REMOVAL, WORKER, BUILD, FLASH, OR "
                "PHONE ACTION STARTED.",
                badge,
                ready=ready,
                eyebrow="FIND ANYTHING  •  EXACT GENESIS SUBSYSTEM",
            )
            self.guided_button.setFocus(Qt.FocusReason.OtherFocusReason)
        elif destination == "genesis_sequence":
            flight = self.genesis_flight_plan()
            self.command_tabs.setCurrentIndex(0)
            self._show_dashboard_handoff(
                "Find Anything → Genesis Sequence",
                f"{flight.project_name}  •  stage {flight.stage_number}/{flight.stage_total}: "
                f"{flight.stage_title}  •  {flight.progress_percent}% verified. Choose Genesis "
                "Sequence to open the guided journey; NO DIALOG, WORKER, BUILD, FLASH, OR PHONE "
                "ACTION STARTED.",
                "GUIDED ENTRY",
                ready=True,
                eyebrow="FIND ANYTHING  •  EXACT NESTED FEATURE",
            )
            self.guided_button.setFocus(Qt.FocusReason.OtherFocusReason)
        elif destination == "ascension_protocol":
            self.command_tabs.setCurrentIndex(0)
            project = self.current_project
            ready = project is not None
            detail = (
                f"Exact project {project.name} is selected. Choose Ascension Protocol to review "
                "the evidence-bound optional root-preparation journey."
                if project is not None
                else "Create or select an exact ROM project before optional root preparation can begin."
            )
            self._show_dashboard_handoff(
                "Find Anything → Ascension Protocol",
                f"{detail} Navigation did not open the dialog or acquire, install, copy, patch, "
                "build, root, flash, or change a phone.",
                "READY TO REVIEW" if ready else "PROJECT REQUIRED",
                ready=ready,
                eyebrow="FIND ANYTHING  •  EXACT NESTED FEATURE",
            )
            self.ascension_button.setFocus(Qt.FocusReason.OtherFocusReason)
        elif destination == "device_dna":
            self.command_tabs.setCurrentIndex(0)
            project = self.current_project
            profile = (
                self.device_dna.profiles.load(project.project_id) if project is not None else None
            )
            if project is None:
                detail = (
                    "Create or select a ROM project, then import its protected firmware before "
                    "Device DNA can bind device and source evidence."
                )
            elif profile is None:
                detail = (
                    f"{project.name} has no current Device DNA. Genesis must derive it from the "
                    "exact protected source and a fresh read-only device context without guessing."
                )
            else:
                detail = (
                    f"{project.name} has current Device DNA {profile.profile_digest[:16]}… with "
                    f"{len(profile.facts)} facts, {len(profile.capabilities)} Capability Map "
                    f"decisions, and {len(profile.warnings)} warning(s)."
                )
            ready = profile is not None
            self._show_dashboard_handoff(
                "Find Anything → Device DNA",
                f"{detail} The source-bound profile is displayed above the Source Lab controls. "
                "NO SCAN, PROFILE REFRESH, WORKER, BUILD, FLASH, OR PHONE ACTION STARTED.",
                "CURRENT EVIDENCE" if ready else "PREREQUISITE",
                ready=ready,
                eyebrow="FIND ANYTHING  •  EXACT NESTED FEATURE",
            )
            (self.project_list if ready else self.guided_button).setFocus(
                Qt.FocusReason.OtherFocusReason
            )
        elif destination == "compatibility_matrix":
            self.command_tabs.setCurrentIndex(0)
            project = self.current_project
            profile = (
                self.device_dna.profiles.load(project.project_id) if project is not None else None
            )
            matrix = (
                self.compatibility.matrices.load(project.project_id)
                if project is not None and profile is not None
                else None
            )
            if project is None:
                detail = "Select a protected-source project before compatibility can be assessed."
            elif profile is None:
                detail = (
                    f"{project.name} needs current Device DNA before the Compatibility Matrix can "
                    "separate proven, limited, unknown, and incompatible capability evidence."
                )
            elif matrix is None:
                detail = (
                    f"{project.name} has Device DNA {profile.profile_digest[:16]}… but no current "
                    "source-bound Compatibility Matrix. Resume Genesis to derive it."
                )
            else:
                states: dict[str, int] = {}
                for decision in matrix.decisions:
                    states[decision.status.value] = states.get(decision.status.value, 0) + 1
                summary = ", ".join(
                    f"{count} {state.replace('-', ' ')}" for state, count in sorted(states.items())
                )
                detail = (
                    f"{project.name} has current Compatibility Matrix "
                    f"{matrix.matrix_digest[:16]}… with {summary or 'no decisions'}."
                )
            ready = matrix is not None
            self._show_dashboard_handoff(
                "Find Anything → Compatibility Matrix",
                f"{detail} Its decisions remain Guardian-advisory only. NO PROFILE REFRESH, "
                "RESEARCH, WORKER, BUILD, APPROVAL, FLASH, OR PHONE ACTION STARTED.",
                "CURRENT EVIDENCE" if ready else "PREREQUISITE",
                ready=ready,
                eyebrow="FIND ANYTHING  •  EXACT NESTED FEATURE",
            )
            (self.project_list if ready else self.guided_button).setFocus(
                Qt.FocusReason.OtherFocusReason
            )
        elif destination == "prebuild_simulation":
            opened = self.open_dashboard_intent("Pre-Build Simulation")
            if opened:
                self.dashboard_handoff_eyebrow.setText("FIND ANYTHING  •  EXACT NESTED FEATURE")
                self.dashboard_handoff_title.setText("Find Anything → Pre-Build Simulation")
            return opened
        elif destination == "rom_dna":
            self.command_tabs.setCurrentIndex(1)
            project = self.current_project
            dna = DnaStore().load(self.store, project.project_id) if project is not None else None
            if project is None:
                detail = "Select an exact ROM project before project provenance can be derived."
            elif dna is None:
                detail = (
                    f"{project.name} needs a current protected source and deterministic build plan "
                    "before ROM DNA can bind its Pack, source, tree, and Recipe provenance."
                )
            else:
                detail = (
                    f"{project.name} has current ROM DNA {dna.fingerprint} with record "
                    f"{dna.record_digest[:16]}… bound to Pack {dna.device_pack_id or 'none'}."
                )
            ready = dna is not None
            self._show_dashboard_handoff(
                "Find Anything → ROM DNA",
                f"{detail} Navigation did not derive, save, modify, plan, build, sign, flash, or "
                "change a phone.",
                "PROVENANCE CURRENT" if ready else "PREREQUISITE",
                ready=ready,
                eyebrow="FIND ANYTHING  •  EXACT NESTED FEATURE",
            )
            (self.verify_plan_button if ready else self.plan_button).setFocus(
                Qt.FocusReason.OtherFocusReason
            )
        elif destination == "boot_observatory":
            self.command_tabs.setCurrentIndex(1)
            project = self.current_project
            receipt = (
                BootObservationService(self.store, self.pack_registry).load(
                    project.project_id,
                    verified_flash=self._latest_guardian_execution_result,
                    device=self.devices[0] if len(self.devices) == 1 else None,
                )
                if project is not None
                else None
            )
            if receipt is None:
                detail = (
                    "Boot Observatory needs an exact protected-source project, a reviewed Device "
                    "Pack build contract, and the matching authorized phone inside Forge Control."
                )
            else:
                detail = (
                    f"{project.name} has {len(receipt.samples)} current read-only boot sample(s); "
                    f"status {receipt.status.value}, stable {'yes' if receipt.stable else 'no'}, "
                    f"receipt {receipt.receipt_digest[:16]}…."
                )
            ready = receipt is not None
            self._show_dashboard_handoff(
                "Find Anything → Boot Observatory",
                f"{detail} Stability never proves a flash or verified first boot by itself. "
                "NO DIALOG, SAMPLE, ADB COMMAND, BUILD, FLASH, OR PHONE ACTION STARTED.",
                "CURRENT OBSERVATION" if ready else "FORGE CONTROL PREREQUISITE",
                ready=ready,
                eyebrow="FIND ANYTHING  •  EXACT NESTED FEATURE",
            )
            (self.build_control_button if project is not None else self.command_tabs).setFocus(
                Qt.FocusReason.OtherFocusReason
            )
        elif destination == "architect_mode":
            self.reveal_experience_mode(ExperienceMode.EXPERT)
        elif destination == "partition_atlas":
            self.command_tabs.setCurrentIndex(1)
            ready = self.partition_button.isEnabled()
            self._show_dashboard_handoff(
                "Find Anything → Partition Atlas",
                (
                    "The current project has a contained payload source ready for Partition "
                    "Atlas review. Choose the highlighted control when ready."
                    if ready
                    else "Partition Atlas needs an exact project, protected firmware, a contained "
                    "tree with payload.bin, and verified Payload Dumper evidence. Complete the "
                    "Source Lab prerequisites first."
                )
                + " NO DIALOG, TOOL INSTALL, EXTRACTION WORKER, BUILD, FLASH, OR PHONE ACTION STARTED.",
                "READY TO REVIEW" if ready else "PREREQUISITE",
                ready=ready,
                eyebrow="FIND ANYTHING  •  EXACT NESTED FEATURE",
            )
            (self.partition_button if ready else self.command_tabs).setFocus(
                Qt.FocusReason.OtherFocusReason
            )
        elif destination == "recipe_forge":
            self.command_tabs.setCurrentIndex(2)
            ready, detail = self._recipe_forge_handoff()
            self._show_dashboard_handoff(
                "Find Anything → Recipe Forge",
                detail,
                "READY TO REVIEW" if ready else "PREREQUISITE",
                ready=ready,
                eyebrow="FIND ANYTHING  •  EXACT NESTED FEATURE",
            )
            (self.guided_recipe_button if ready else self.command_tabs).setFocus(
                Qt.FocusReason.OtherFocusReason
            )
        elif destination == "forge_control":
            self.command_tabs.setCurrentIndex(1)
            ready = self.build_control_button.isEnabled()
            if ready:
                detail = (
                    "Current project evidence can open Forge Control for build, signing, "
                    "recovery, and flash-readiness review."
                )
            else:
                _planning_ready, detail = self._prebuild_simulation_handoff()
                detail += " Prepare and verify a build plan before Forge Control can open."
            self._show_dashboard_handoff(
                "Find Anything → Forge Control",
                f"{detail} NO DIALOG, WORKER, BUILD, SIGNING, FLASH, OR PHONE ACTION STARTED.",
                "READY TO REVIEW" if ready else "PREREQUISITE",
                ready=ready,
                eyebrow="FIND ANYTHING  •  EXACT NESTED FEATURE",
            )
            (self.build_control_button if ready else self.command_tabs).setFocus(
                Qt.FocusReason.OtherFocusReason
            )
        else:
            return False
        self.detail_scroll.ensureWidgetVisible(self.command_tabs, 0, 24)
        return True

    def open_repair_solution_handoff(
        self,
        action_id: str,
        fingerprint_id: str,
        receipt_digest: str,
        source_id: str,
        receipt: OnlineFixReceipt,
    ) -> bool:
        """Stage a research-bound firmware inspection for explicit local review."""

        lead = receipt.candidates[0] if receipt.candidates else None
        if (
            action_id
            not in {
                "inspect-payload-source",
                "inspect-avb-topology",
                "classify-ota-source",
            }
            or re.fullmatch(r"[0-9a-f]{64}", fingerprint_id) is None
            or re.fullmatch(r"[0-9a-f]{64}", receipt_digest) is None
            or re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", source_id) is None
            or receipt.fingerprint.fingerprint_id != fingerprint_id
            or receipt.receipt_digest != receipt_digest
            or lead is None
            or lead.local_action_id != action_id
            or lead.source_id != source_id
            or lead.authority not in {SourceAuthority.OFFICIAL, SourceAuthority.MAINTAINER}
        ):
            return False
        self._pending_repair_solution = None
        self.command_tabs.setCurrentIndex(1)
        project = self.current_project
        action_copy = {
            "inspect-payload-source": "inspect the firmware payload source",
            "inspect-avb-topology": "inspect the Android Verified Boot topology",
            "classify-ota-source": "classify the OTA source",
        }[action_id]
        if project is None:
            self._show_dashboard_handoff(
                "Recovery Bay → firmware evidence workspace",
                f"The saved lead evidence recommends ROMVERSE {action_copy}, but no exact ROM "
                "project is selected. Create or select a project first, then return to the Smart "
                "Solution so its receipt can be rebound. NO PROJECT, WORKER, BUILD, FLASH, OR "
                "PHONE ACTION STARTED.",
                "PROJECT REQUIRED",
                ready=False,
                eyebrow="RECOVERY BAY SMART SOLUTION  •  EXACT LOCAL HANDOFF",
            )
            self.new_button.setFocus(Qt.FocusReason.OtherFocusReason)
            return True
        if project.original is None:
            self._show_dashboard_handoff(
                f"Recovery Bay → {project.name}",
                f"The saved lead evidence recommends ROMVERSE {action_copy}. Exact project "
                f"{project.project_id} has no protected firmware source, so import and hash the "
                "user-selected package first, then return to refresh the Smart Solution. "
                "Compatibility is not inferred from the recommendation. NO IMPORT, WORKER, "
                "BUILD, FLASH, OR PHONE ACTION STARTED.",
                "PROTECTED SOURCE REQUIRED",
                ready=False,
                eyebrow="RECOVERY BAY SMART SOLUTION  •  EXACT LOCAL HANDOFF",
            )
            self.import_button.setFocus(Qt.FocusReason.OtherFocusReason)
            self.detail_scroll.ensureWidgetVisible(self.command_tabs, 0, 24)
            return True
        self._pending_repair_solution = (
            action_id,
            fingerprint_id,
            receipt_digest,
            source_id,
            project.project_id,
            project.original.sha256,
            receipt,
        )
        ready = self.worker is None and self.build_control_button.isEnabled()
        self._show_dashboard_handoff(
            f"Recovery Bay → {project.name} Forge Control",
            f"Saved source {source_id} recommends ROMVERSE {action_copy}. The handoff is bound "
            f"to research receipt {receipt_digest[:16]}…, project {project.project_id}, and "
            f"protected source {project.original.sha256[:16]}…. Open Forge Control to review "
            "only that host-side action; ROMVERSE does not assert firmware compatibility from "
            "the recommendation. NO DIALOG, WORKER, BUILD, FLASH, OR PHONE ACTION STARTED.",
            "READY TO REVIEW" if ready else "WAIT FOR CURRENT OPERATION",
            ready=ready,
            eyebrow="RECOVERY BAY SMART SOLUTION  •  EXACT LOCAL HANDOFF",
        )
        self.build_control_button.setFocus(Qt.FocusReason.OtherFocusReason)
        self.detail_scroll.ensureWidgetVisible(self.command_tabs, 0, 24)
        return True

    def choose_mode(self) -> int:
        return RomModeChooser(self).exec()

    def set_tool_statuses(self, statuses: tuple[ToolStatus, ...]) -> None:
        """Apply a fresh complete tool inventory to Studio and guided workflows."""

        self._configure_tools(statuses)
        if hasattr(self, "project_list"):
            preferred = self.current_project.project_id if self.current_project else ""
            self.refresh(preferred)

    def set_android_runtime(
        self,
        gateway: ExecutionGateway | None,
        adb_executable: Path | None,
        fastboot_executable: Path | None = None,
    ) -> None:
        changed = (
            self.gateway is not gateway
            or self.adb_executable != adb_executable
            or self.fastboot_executable != fastboot_executable
        )
        self.gateway = gateway
        self.adb_executable = adb_executable
        self.fastboot_executable = fastboot_executable
        if changed:
            self.device_context_changed.emit()

    def set_devices(
        self,
        devices: list[AndroidDevice],
        *,
        observed_devices: list[AndroidDevice] | None = None,
        scan_error: str = "",
    ) -> None:
        """Bind actions to one target while retaining truthful detection-only context."""

        active = list(devices)
        observed = list(active if observed_devices is None else observed_devices)
        normalized_error = scan_error.strip()
        changed = (
            self.devices != active
            or self.observed_devices != observed
            or self.device_scan_error != normalized_error
        )
        self.devices = active
        self.observed_devices = observed
        self.device_scan_error = normalized_error
        self.suggested_pack_id = ""
        if active:
            resolution = self.pack_registry.resolve(active[0])
            if resolution.pack is not None:
                self.suggested_pack_id = resolution.pack.pack_id
        if self.current_project is not None and active and not active[0].is_simulated:
            # Boot evidence is optional and must never interfere with device discovery.
            with suppress(OSError, ProjectError):
                receipt = BootObservationService(self.store, self.pack_registry).observe(
                    self.current_project.project_id,
                    active[0],
                    verified_flash=self._latest_guardian_execution_result,
                )
                knowledge_report = self.scan_boot_observation_knowledge(receipt)
                self.boot_observation_updated.emit(receipt, knowledge_report)
        if changed:
            self.device_context_changed.emit()
            if self.current_project is not None and self.worker is None:
                self.refresh(self.current_project.project_id)

    def scan_boot_observation_knowledge(self, receipt):
        """Automatically rank the offline archive when boot evidence needs attention."""

        failure = BootObservationService.knowledge_failure(receipt)
        if failure is None:
            return None
        return self.scan_failure_knowledge(receipt.project_id, failure)

    def scan_failure_knowledge(self, project_id: str, failure: KnowledgeFailure):
        """Run one project-scoped local diagnosis and announce the inert result."""

        report = self.device_dna.scan_knowledge_after_failure(project_id, failure)
        if report is not None:
            self.offline_knowledge_updated.emit(report)
        return report

    def scan_operation_failure_knowledge(
        self,
        project_id: str,
        operation: str,
        message: str,
    ):
        """Translate a bounded ROM worker failure into offline diagnostic evidence."""

        normalized_operation = operation.replace("\x00", " ").strip()[:160] or "unknown"
        normalized_message = message.replace("\x00", " ").strip()[:4_000]
        phase = (
            "flash"
            if any(
                token in normalized_operation.casefold()
                for token in ("flash", "guardian", "install", "fastboot")
            )
            else "build"
        )
        return self.scan_failure_knowledge(
            project_id,
            KnowledgeFailure(
                phase=phase,
                message=normalized_message or "ROM Studio operation failed without detail",
                finding_ids=(f"{phase}.operation_failed",),
                operation=normalized_operation,
            ),
        )

    def set_companion_snapshot(self, snapshot: object) -> None:
        """Receive authenticated, read-only Companion device-safety evidence."""

        changed = self.companion_snapshot != snapshot
        self.companion_snapshot = snapshot
        if changed:
            self.device_context_changed.emit()

    def refresh(self, preferred_id: str = "") -> None:
        current_id = preferred_id or (
            self.current_project.project_id if self.current_project is not None else ""
        )
        self.projects = self.store.list_projects()
        self.project_list.blockSignals(True)
        self.project_list.clear()
        selected = 0
        for index, project in enumerate(self.projects):
            source = "Original protected" if project.original else "Awaiting original"
            state = self._project_progress(project)
            item = QListWidgetItem(
                f"{project.name}\n{_display_time(project.updated_at)}   •   {source}   •   {state}"
            )
            self.project_list.addItem(item)
            if project.project_id == current_id:
                selected = index
        self.project_list.blockSignals(False)
        if self.projects:
            self.project_list.setCurrentRow(selected)
            self._select(selected)
        else:
            self.current_project = None
            self.delete_button.setEnabled(False)
            self.project_name.setText("No ROM projects yet")
            self.project_meta.setText("Create a project to establish its versioned manifest.")
            self.device_dna_detail.setText(
                "Import protected firmware to create an evidence-backed Device DNA profile."
            )
            self.original_name.setText("Not imported")
            self.original_detail.setText(
                "Original firmware remains outside ROMVERSE until you explicitly choose a file."
            )
            self.external_intake_button.setEnabled(False)
            self.import_button.setEnabled(False)
            self.verify_button.setEnabled(False)
            self.inspect_button.setEnabled(False)
            self.working_button.setEnabled(False)
            self.snapshot_button.setEnabled(False)
            self.extract_button.setEnabled(False)
            self.plan_button.setEnabled(False)
            self.verify_plan_button.setEnabled(False)
            self.forge_button.setEnabled(False)
            self.verify_forge_button.setEnabled(False)
            self.recipe_button.setEnabled(False)
            self.new_recipe_button.setEnabled(False)
            self.guided_recipe_button.setEnabled(False)
            self.add_step_button.setEnabled(False)
            self.rollback_button.setEnabled(False)
            self.replace_button.setEnabled(False)
            self.property_button.setEnabled(False)
            self.partition_button.setEnabled(False)
            self.partition_button.setText("Partition Atlas")
            self.partition_button.setToolTip(
                "Import and prepare an OTA payload before opening Partition Atlas."
            )
            self.build_control_button.setEnabled(False)
            self.inspection_detail.setText(
                "Create a project and import a protected original before inspection."
            )
            self.time_machine_detail.setText(
                "Import a protected original to enable an isolated working copy."
            )

    def _project_progress(self, project: RomProject) -> str:
        state = GuidedMissionStore(self.store.projects_root / project.project_id).load()
        if state.updated_at:
            saved_stage = next(
                (item for item in STAGES if item.stage_id == state.selected_stage), STAGES[0]
            )
            report = self.inspection.load_report(project.project_id)
            working = self.store.working_copy(project.project_id)
            tree_ready = self.inspection.working_tree_exists(project.project_id)
            dna = self.device_dna.profiles.load(project.project_id)
            required_stage = (
                STAGES[1]
                if project.original is None
                else STAGES[2]
                if report is None
                else STAGES[3]
                if working is None or not tree_ready
                else STAGES[4]
                if dna is None or not dna.capabilities
                else None
            )
            if state.last_error:
                return "GENESIS • ATTENTION"
            if required_stage is not None and required_stage.number < saved_stage.number:
                return (
                    f"GENESIS • {required_stage.number}/{len(STAGES)} • "
                    f"{required_stage.short_title.upper()}"
                )
            return (
                f"GENESIS • {saved_stage.number}/{len(STAGES)} • {saved_stage.short_title.upper()}"
            )
        return "READY TO START" if project.original is None else "IN PROGRESS"

    def _validation_summary(self, project: RomProject) -> str:
        report = self.inspection.load_report(project.project_id)
        dna = self.device_dna.profiles.load(project.project_id)
        matrix = self.compatibility.matrices.load(project.project_id)
        checks = (
            ("Protected original", project.original is not None),
            ("Device DNA profile", dna is not None),
            ("Capability Map", bool(dna and dna.capabilities)),
            ("Compatibility Matrix", matrix is not None),
            ("Structure inspected", report is not None),
            ("Working copy", self.store.working_copy(project.project_id) is not None),
            (
                "Working tree",
                self.inspection.working_tree_exists(project.project_id),
            ),
            ("Build plan", RomBuildPlanner(self.store).load(project.project_id) is not None),
        )
        return "\n".join(("✓ " if passed else "• ") + label for label, passed in checks)

    def _filter_projects(self, query: str) -> None:
        query = query.casefold().strip()
        for index in range(self.project_list.count()):
            item = self.project_list.item(index)
            item.setHidden(bool(query) and query not in item.text().casefold())

    def _select(self, row: int) -> None:
        if not 0 <= row < len(self.projects):
            return
        project = self._associate_exact_source_pack(self.projects[row], row)
        dna = self._refresh_device_dna(project)
        self.current_project = project
        self.delete_button.setEnabled(True)
        self.build_control_button.setEnabled(self.worker is None)
        self._update_guidance(project)
        self.project_name.setText(project.name)
        external = self.external_intake.load(project.project_id)
        source_identity = (
            identify_firmware_source(project.original.original_name).summary
            if project.original is not None
            else external.package_type
            if external is not None
            else "Awaiting protected source"
        )
        self.project_meta.setText(
            f"Project ID  •  {project.project_id}\n"
            f"Device Pack  •  {project.device_pack_id or 'Not associated'}\n"
            f"Detected base  •  {source_identity}\n"
            f"Manifest  •  projects/{project.project_id}/{self.store.MANIFEST_NAME}\n\n"
            f"Guided validation\n{self._validation_summary(project)}"
        )
        self._render_upgrade_passport(project, external)
        self._render_device_dna(dna, external)
        if project.original is None:
            self.external_intake_button.setEnabled(self.worker is None)
            self.external_intake_button.setText(
                "Reinspect external firmware in place"
                if external is not None
                else "Inspect firmware in place…"
            )
            if external is None:
                self.original_name.setText("No original imported")
                self.original_detail.setText(
                    "Choose read-only inspection to hash and classify a file in place, or import "
                    "a separate protected workspace copy."
                )
                self.inspection_detail.setText(
                    "Not inspected. Read-only intake does not copy or extract the selected source."
                )
            else:
                self.original_name.setText("External firmware inspected • not imported")
                self.original_detail.setText(
                    f"Name  •  {external.source_name}\n"
                    f"Size  •  {human_bytes(external.source_size_bytes)}\n"
                    f"SHA-256  •  {external.source_sha256}\n"
                    "Storage  •  Original external path; no workspace copy\n"
                    "Authority  •  Evidence only; build, device, Guardian, and execution: LOCKED"
                )
                self._render_external_intake(external)
            self.import_button.setEnabled(self.worker is None)
            self.verify_button.setEnabled(False)
            self.inspect_button.setEnabled(False)
            self.working_button.setEnabled(False)
            self.snapshot_button.setEnabled(False)
            self.extract_button.setEnabled(False)
            self.plan_button.setEnabled(False)
            self.verify_plan_button.setEnabled(False)
            self.forge_button.setEnabled(False)
            self.verify_forge_button.setEnabled(False)
            self.recipe_button.setEnabled(False)
            self.new_recipe_button.setEnabled(False)
            self.guided_recipe_button.setEnabled(False)
            self.add_step_button.setEnabled(False)
            self.rollback_button.setEnabled(False)
            self.replace_button.setEnabled(False)
            self.property_button.setEnabled(False)
            self.partition_button.setEnabled(False)
            self.partition_button.setText("Partition Atlas")
            self.partition_button.setToolTip(
                "Import and prepare an OTA payload before opening Partition Atlas."
            )
        else:
            self.external_intake_button.setEnabled(False)
            self.external_intake_button.setText("Inspect firmware in place…")
            self.original_name.setText(project.original.original_name)
            self.original_detail.setText(
                f"Size  •  {human_bytes(project.original.size_bytes)}\n"
                f"SHA-256  •  {project.original.sha256}\n"
                f"Workspace  •  {project.original.workspace_path}"
            )
            self.import_button.setEnabled(False)
            self.verify_button.setEnabled(self.worker is None)
            self.inspect_button.setEnabled(self.worker is None)
            self.working_button.setEnabled(self.worker is None)
            self.snapshot_button.setEnabled(
                self.worker is None and self.store.working_copy(project.project_id) is not None
            )
            report = self.inspection.load_report(project.project_id)
            self.extract_button.setEnabled(
                self.worker is None
                and report is not None
                and report.container.value in {"zip", "tar"}
                and not any(f.severity.value == "critical" for f in report.findings)
            )
            self.plan_button.setEnabled(
                self.worker is None and self.inspection.working_tree_exists(project.project_id)
            )
            self.verify_plan_button.setEnabled(
                self.worker is None
                and RomBuildPlanner(self.store).load(project.project_id) is not None
            )
            plan = RomBuildPlanner(self.store).load(project.project_id)
            forge = ForgeBundleService(self.store)
            forge_receipt = forge.load_receipt(project.project_id)
            current_forge_receipt = bool(
                forge_receipt is not None
                and plan is not None
                and forge.receipt_matches_plan(forge_receipt, plan)
            )
            self.forge_button.setEnabled(self.worker is None and plan is not None)
            self.verify_forge_button.setEnabled(self.worker is None and current_forge_receipt)
            self.recipe_button.setEnabled(
                self.worker is None
                and RecipeStore().load(self.store.projects_root / project.project_id) is not None
                and self.inspection.working_tree_exists(project.project_id)
            )
            self.new_recipe_button.setEnabled(self.worker is None and project.original is not None)
            self.guided_recipe_button.setEnabled(
                self.worker is None and self.inspection.working_tree_exists(project.project_id)
            )
            self.rollback_button.setEnabled(
                self.worker is None and bool(self.store.list_snapshots(project.project_id))
            )
            self.add_step_button.setEnabled(
                self.worker is None
                and RecipeStore().load(self.store.projects_root / project.project_id) is not None
            )
            recipe = RecipeStore().load(self.store.projects_root / project.project_id)
            tree = self.store.working_root / project.project_id / "tree"
            preview = preview_recipe(recipe, tree) if recipe is not None and tree.is_dir() else None
            self.replace_button.setEnabled(
                self.worker is None
                and recipe is not None
                and preview is not None
                and not preview.unresolved_targets
                and any(step.operation != "inspect" for step in recipe.steps)
            )
            self.property_button.setEnabled(
                self.worker is None
                and bool(
                    RecipeExecutor.list_snapshots(
                        self.store.snapshots_root / project.project_id / "recipes"
                    )
                )
            )
            payload_ready = self._working_payload_available(project.project_id)
            self.partition_button.setEnabled(self.worker is None and payload_ready)
            if payload_ready and self.payload_service is None:
                self.partition_button.setText("Resolve Partition tools")
                self.partition_button.setToolTip(
                    "payload.bin is ready, but Payload Dumper is not verified. Open the scoped "
                    "Forge Arsenal setup, verify the missing tool, and continue into Partition Atlas."
                )
            else:
                self.partition_button.setText("Partition Atlas")
                self.partition_button.setToolTip(
                    "Scan payload.bin, visualize its partition map, and extract selected ROM "
                    "partitions with Guardian storage and provenance checks."
                )
            self.build_control_button.setEnabled(self.worker is None)
            self._render_inspection(report)
            self._render_time_machine(project.project_id)

    def _associate_exact_source_pack(self, project: RomProject, row: int) -> RomProject:
        """Bind exact sources and demote mismatched model-only contracts safely."""

        if project.original is None:
            return project
        current_pack = next(
            (pack for pack in self.pack_registry.packs if pack.pack_id == project.device_pack_id),
            None,
        )
        resolution = self.pack_registry.resolve_source(project.original.sha256)
        if resolution.matched and resolution.pack is not None:
            if current_pack is not None and current_pack.pack_id == resolution.pack.pack_id:
                return project
            return self._associate_detected_pack(
                project,
                row,
                resolution.pack.pack_id,
                resolution.reason,
                f"Exact source verified — associated {resolution.pack.display_name}.",
                "Good",
            )
        if current_pack is None:
            identity = identify_firmware_source(project.original.original_name)
            connected = tuple(
                device for device in self.devices if device.state is DeviceState.DEVICE
            )
            knowledge_device: AndroidDevice | None = None
            if identity.manufacturer:
                knowledge_device = AndroidDevice(
                    "offline-source",
                    DeviceState.UNKNOWN,
                    manufacturer=identity.manufacturer,
                    codename=identity.codename,
                )
            elif len(connected) == 1:
                knowledge_device = connected[0]
            if knowledge_device is None:
                return project
            fallback = self.pack_registry.resolve_knowledge(knowledge_device)
            if not fallback.matched or fallback.pack is None:
                return project
            return self._associate_detected_pack(
                project,
                row,
                fallback.pack.pack_id,
                "No exact source contract matched; " + fallback.reason,
                f"No exact build contract exists for this SHA-256; associated "
                f"{fallback.pack.display_name} for read-only knowledge only.",
                "Warning",
            )
        if current_pack.build_contract is None:
            return project
        contract = current_pack.build_contract
        if contract.source.archive_sha256 == project.original.sha256:
            return project
        identity = identify_firmware_source(project.original.original_name)
        device = next(iter(self.devices), None) or AndroidDevice(
            "offline-source",
            DeviceState.UNKNOWN,
            manufacturer=identity.manufacturer
            or next((value for value in current_pack.manufacturers if value != "*"), ""),
            codename=identity.codename,
        )
        fallback = self.pack_registry.resolve_knowledge(device)
        if fallback is None or not fallback.matched or fallback.pack is None:
            self.operation_status.setText(
                f"Detected {identity.summary}, but its SHA-256 does not match "
                f"{contract.source.build_id}. No read-only fallback Pack is available."
            )
            self.operation_status.setObjectName("Warning")
            self._repolish(self.operation_status)
            return project
        return self._associate_detected_pack(
            project,
            row,
            fallback.pack.pack_id,
            "Protected source did not match the previous source-bound contract; " + fallback.reason,
            f"Detected {identity.summary}. No exact build contract exists for this SHA-256; "
            f"switched safely to {fallback.pack.display_name} knowledge mode.",
            "Warning",
        )

    def _associate_detected_pack(
        self,
        project: RomProject,
        row: int,
        pack_id: str,
        reason: str,
        message: str,
        state: str,
    ) -> RomProject:
        try:
            updated = self.store.associate_device_pack(
                project.project_id,
                pack_id,
                evidence_sha256=project.original.sha256 if project.original else "",
                reason=reason,
            )
        except ProjectError as exc:
            self.operation_status.setText(f"Automatic Device Pack association blocked: {exc}")
            self.operation_status.setObjectName("Warning")
            self._repolish(self.operation_status)
            return project
        self.projects = tuple(
            updated if index == row else existing for index, existing in enumerate(self.projects)
        )
        self.operation_status.setText(message)
        self.operation_status.setObjectName(state)
        self._repolish(self.operation_status)
        return updated

    def _update_guidance(self, project: RomProject) -> None:
        report = self.inspection.load_report(project.project_id)
        dna = self.device_dna.profiles.load(project.project_id)
        matrix = self.compatibility.matrices.load(project.project_id)
        tree_ready = self.inspection.working_tree_exists(project.project_id)
        plan_ready = RomBuildPlanner(self.store).load(project.project_id) is not None
        steps = (
            (project.original is not None, "Import protected original"),
            (dna is not None, "Create Device DNA"),
            (bool(dna and dna.capabilities), "Generate Capability Map"),
            (matrix is not None, "Create Compatibility Matrix"),
            (project.original is not None and report is not None, "Inspect structure"),
            (self.store.working_copy(project.project_id) is not None, "Create working copy"),
            (tree_ready, "Extract and verify working tree"),
            (plan_ready, "Create and verify build plan"),
        )
        completed = sum(done for done, _label in steps)
        next_step = next((label for done, label in steps if not done), "Workflow complete")
        self.guide_status.setText(f"{completed}/{len(steps)} steps complete  •  Next: {next_step}")

    def _refresh_device_dna(self, project: RomProject) -> DeviceDnaProfile | None:
        if project.original is None:
            self.device_dna_updated.emit(None)
            return None
        candidates = tuple(device for device in self.devices if device.state is DeviceState.DEVICE)
        device = candidates[0] if len(candidates) == 1 else None
        refreshed = False
        try:
            profile = self.device_dna.refresh(
                project.project_id,
                device,
                self.inspection.load_report(project.project_id),
            )
            refreshed = True
        except (OSError, ProjectError, TypeError, ValueError):
            profile = self.device_dna.profiles.load(project.project_id)
        if profile is not None:
            self.device_dna_updated.emit(profile)
            if refreshed and self.device_dna.last_knowledge_lookup is not None:
                self.offline_knowledge_updated.emit(self.device_dna.last_knowledge_lookup)
            matrix: CompatibilityMatrix | None
            try:
                matrix = self.compatibility.assess(profile)
            except (OSError, ProjectError, TypeError, ValueError):
                matrix = self.compatibility.matrices.load(project.project_id)
            if matrix is not None:
                self.compatibility_matrix_updated.emit(matrix)
        return profile

    def _render_device_dna(
        self,
        profile: DeviceDnaProfile | None,
        external: ExternalFirmwareIntakeReceipt | None = None,
    ) -> None:
        if profile is None:
            if external is None:
                self.device_dna_detail.setText(
                    "Device DNA is unavailable. Import protected firmware; ROMVERSE will preserve "
                    "unknown findings as unconfirmed rather than guess."
                )
            else:
                self.device_dna_detail.setText(
                    "Read-only package evidence is available, but no protected source or exact "
                    "device identity exists.\n"
                    "guardian_flash  •  UNCONFIRMED\n"
                    "Compatibility Matrix  •  Unknown\n"
                    "Device model, build, channel, upgrade relationship, and Device Pack match "
                    "remain unconfirmed. No build or phone authority was created."
                )
            return
        facts = []
        for fact_id in (
            "device.evidence_class",
            "identity.marketing_name",
            "identity.model",
            "identity.codename",
            "soc.platform",
            "software.build",
            "firmware.upgrade_relationship",
            "firmware.package_format",
            "partition.ab_scheme",
            "security.verified_boot",
        ):
            fact = profile.fact(fact_id)
            if fact is not None:
                facts.append(f"{fact.label}: {fact.value} [{fact.confidence.value}]")
        state_marks = {
            CapabilityState.SUPPORTED: "●",
            CapabilityState.CAUTION: "◆",
            CapabilityState.UNSUPPORTED: "■",
            CapabilityState.UNCONFIRMED: "○",
        }
        capabilities = [
            f"{state_marks[item.state]} {item.state.value}  •  {item.label}\n   {item.detail}"
            for item in profile.capabilities
        ]
        warning = (
            "\n\nAttention\n" + "\n".join(f"• {item}" for item in profile.warnings)
            if profile.warnings
            else ""
        )
        blueprint = next(
            (item for item in profile.evidence if item.evidence_id == "source.blueprint"),
            None,
        )
        source_intelligence = ""
        if blueprint is not None:
            source_kind = (
                blueprint.source_type.removesuffix("-source-blueprint").replace("-", " ").title()
            )
            source_intelligence = (
                "\n\nSource Intelligence\n"
                f"● VERIFIED  •  Project-local {source_kind} blueprint\n"
                f"   Digest {blueprint.source_ref[:16]}…  •  Build preparation evidence only\n"
                "   The blueprint grants no device-write or flash authority."
            )
        matrix = self.compatibility.matrices.load(profile.project_id)
        compatibility = (
            "\n\nCompatibility Matrix\n"
            + "\n".join(
                f"• {item.status.value}  •  {item.label}  •  "
                f"Proven: {'yes' if item.proven_compatible else 'no'}  •  "
                f"Freshness: {item.freshness.value}"
                for item in matrix.decisions
            )
            if matrix is not None
            else "\n\nCompatibility Matrix\n• Not available; ROMVERSE will not infer compatibility."
        )
        archive = ""
        knowledge_report = self.device_dna.last_knowledge_lookup
        if knowledge_report is not None and knowledge_report.trigger == "device-dna":
            best = (
                f"\n• Best match: {knowledge_report.matches[0].record.title}"
                if knowledge_report.matches
                else "\n• No compatible local record matched; unknowns remain explicit."
            )
            archive = (
                "\n\nOffline Archives\n"
                f"• AUTOMATIC SCAN COMPLETE  •  {len(knowledge_report.matches)} compatible "
                f"match(es)  •  EXECUTION AUTHORITY: NONE{best}"
            )
        elif self.device_dna.knowledge_lookup_error:
            archive = (
                "\n\nOffline Archives\n"
                "• Archive integrity or availability check failed; ROMVERSE did not guess."
            )
        self.device_dna_detail.setText(
            (
                "SIMULATION ONLY • NOT HARDWARE VERIFIED\n"
                if any(item.evidence_id == "device.simulation" for item in profile.evidence)
                else ""
            )
            + "Evidence-backed profile\n"
            + "\n".join(facts)
            + source_intelligence
            + "\n\nCapability Map\n"
            + "\n".join(capabilities)
            + compatibility
            + archive
            + warning
            + f"\n\nEvidence sources: {len(profile.evidence)}  •  "
            f"Profile digest: {profile.profile_digest[:16]}…  •  Bootloader relock: NEVER"
        )

    def _render_upgrade_passport(
        self,
        project: RomProject,
        external: ExternalFirmwareIntakeReceipt | None = None,
    ) -> None:
        if project.original is None:
            if external is not None:
                known_identity = ", ".join(
                    value
                    for value in (
                        external.manufacturer,
                        external.codename,
                        external.build_id,
                        f"Android {external.android_version}" if external.android_version else "",
                        external.region,
                    )
                    if value
                )
                known = (
                    f"{external.container.replace('_', ' ')} container, "
                    f"{human_bytes(external.source_size_bytes)}, exact SHA-256 "
                    f"{external.source_sha256[:16]}…"
                )
                if known_identity:
                    known += f", filename identity: {known_identity}"
                self._set_upgrade_passport(
                    "attention",
                    "READ-ONLY SOURCE EVIDENCE • RELATIONSHIP UNCONFIRMED",
                    f"Known  •  {known}\n"
                    "Unconfirmed  •  Exact device, firmware channel, Device Pack compatibility, "
                    "upgrade/downgrade relationship, and installation route\n"
                    "Next  •  Reinspect this external source in place, or deliberately import a "
                    "protected copy in a later workflow.\n"
                    "Authority  •  Evidence only  •  Protected source: NO  •  Build/install/flash: "
                    "LOCKED  •  Phone changed: NO  •  Bootloader relock: NEVER",
                )
                return
            self._set_upgrade_passport(
                "attention",
                "AWAITING PROTECTED FIRMWARE",
                "Import a firmware package to create a source-bound comparison. No phone action is available.",
            )
            return
        candidates = tuple(device for device in self.devices if device.state is DeviceState.DEVICE)
        device = candidates[0] if len(candidates) == 1 else None
        try:
            blueprint = FirmwareSourceIntelligenceService(
                self.store,
                self.tool_statuses,
                SubprocessRunner(),
            ).load(project.project_id)
            review = assess_project_firmware_upgrade(
                self.store,
                project.project_id,
                device,
                blueprint=blueprint,
            )
        except (OSError, ProjectError, TypeError, ValueError) as exc:
            self._set_upgrade_passport(
                "attention",
                "UPGRADE REVIEW UNAVAILABLE",
                f"ROMVERSE could not create the current relationship review: {exc}. Nothing was inferred or changed.",
            )
            return
        self._show_upgrade_review(review)

    def _show_upgrade_review(self, review: ProjectFirmwareUpgradeReview) -> None:
        assessment = review.assessment
        if review.metadata_error:
            state, title = "blocked", "PACKAGE METADATA REJECTED"
            next_step = (
                "Import a package with readable, internally consistent Android OTA metadata."
            )
        elif assessment.relationship is FirmwareRelationship.UPGRADE:
            if assessment.cross_channel:
                state, title = "attention", "CROSS-CHANNEL UPGRADE CANDIDATE"
                next_step = (
                    "Continue only through an exact Device Pack review of product, partitions, "
                    "unlock, wipe, rollback, and recovery. Physical country is not a compatibility gate."
                )
            else:
                state, title = "verified", "NEWER EXACT-DEVICE CANDIDATE"
                next_step = (
                    "Open Forge Control for package, recovery, Device Pack, and Guardian readiness."
                )
        elif assessment.relationship is FirmwareRelationship.SAME:
            state, title = "attention", "NOT AN UPGRADE  •  REINSTALL/RECOVERY REVIEW"
            next_step = (
                "Import a newer package for an upgrade, or continue only with an exact Device Pack "
                "that explicitly supports the intended reinstall/recovery route."
            )
        elif assessment.relationship is FirmwareRelationship.DOWNGRADE:
            state, title = "attention", "NOT AN UPGRADE  •  DOWNGRADE RISK REVIEW"
            next_step = (
                "Choose a newer package for an upgrade. Any intentional downgrade needs an exact "
                "Device Pack rollback/recovery contract and separate Guardian review."
            )
        elif assessment.relationship is FirmwareRelationship.INCOMPATIBLE:
            state, title = "blocked", "FIRMWARE TARGET DOES NOT MATCH"
            next_step = (
                "Import firmware that names the connected device or a verified device alias."
            )
        else:
            state, title = "attention", "UPGRADE RELATIONSHIP UNCONFIRMED"
            next_step = (
                "Connect and authorize exactly one phone, then provide a package with usable build "
                "identity or Android OTA metadata."
            )
        reasons = "\n".join(f"• {reason}" for reason in assessment.reasons)
        detail = (
            f"{assessment.summary}\n"
            f"Evidence  •  {review.evidence_kind} {review.evidence_digest[:16]}…  •  "
            f"protected source {review.source_sha256[:16]}…\n"
            f"{reasons}\n"
            f"Next  •  {next_step}\n"
            "Authority  •  Relationship classification only  •  Install/flash: NO  •  "
            "Phone changed: NO  •  Bootloader relock: NEVER"
        )
        self._set_upgrade_passport(state, title, detail)

    def _set_upgrade_passport(self, state: str, title: str, detail: str) -> None:
        self.upgrade_passport.setProperty("upgradeState", state)
        self.upgrade_passport_status.setText(title)
        self.upgrade_passport_status.setProperty("upgradeState", state)
        self.upgrade_passport_detail.setText(detail)
        self._repolish(self.upgrade_passport)
        self._repolish(self.upgrade_passport_status)

    def _new_project(self) -> None:
        dialog = ProjectNameDialog(self)
        dialog.name_input.setFocus(Qt.FocusReason.OtherFocusReason)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            project = self.store.create(dialog.project_name, self.suggested_pack_id)
        except ProjectError as exc:
            QMessageBox.warning(self, "Project not created", str(exc))
            return
        self.operation_status.setText("Created versioned project manifest.")
        self.operation_status.setObjectName("Good")
        self._repolish(self.operation_status)
        self.refresh(project.project_id)

    def _delete_project(self) -> None:
        if self.current_project is None:
            return
        project = self.current_project
        answer = QMessageBox.question(
            self,
            "Delete ROM project?",
            f"Delete '{project.name}' and its derived working data? Protected originals are retained.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.delete_project(project.project_id)
        except ProjectError as exc:
            QMessageBox.warning(self, "Project not deleted", str(exc))
            return
        self.current_project = None
        self.delete_button.setEnabled(False)
        self.refresh()

    def _guided_recipe(self, dialog_parent: QWidget | None = None) -> None:
        if self.current_project is None:
            return
        from romverse.ui.guided_recipe import RecipeForgeSequence

        try:
            parent = dialog_parent if isinstance(dialog_parent, QWidget) else self
            RecipeForgeSequence(self, parent).exec()
        except ProjectError as exc:
            QMessageBox.warning(self, "Recipe Forge unavailable", str(exc))

    def _open_partition_workspace(self) -> None:
        if self.current_project is None:
            return
        if self.payload_service is None and not self._resolve_partition_tools():
            return
        from romverse.ui.partition_workspace import PartitionWorkspace

        PartitionWorkspace(self).exec()

    def _working_payload_available(self, project_id: str) -> bool:
        """Use the sealed display index; never walk a large tree on the UI thread."""

        summary = self.inspection.cached_working_tree_summary(project_id)
        if summary is not None and any(
            PurePosixPath(path).name.casefold() == "payload.bin" for path in summary.notable_files
        ):
            return True
        # A root payload is a constant-time compatibility check for legacy projects whose
        # background extraction predates the display index. Nested legacy trees are indexed
        # by the next managed inspection/extraction refresh rather than scanned here.
        payload = self.store.working_root / project_id / "tree" / "payload.bin"
        return payload.is_file() and not payload.is_symlink()

    def _resolve_partition_tools(self) -> bool:
        """Resolve only Payload Atlas' missing tool, then re-verify before continuing."""

        resolved = self._resolve_required_tools(
            ("Payload Dumper",),
            purpose=(
                "ROMVERSE selected only Payload Dumper for this OTA. Its official managed package "
                "must verify before Partition Atlas can inspect payload.bin."
            ),
            title="ROMVERSE • Resolve Partition Atlas tools",
            success_message=(
                "Payload Dumper verified. Opening Partition Atlas with the current protected source."
            ),
        )
        return resolved and self.payload_service is not None

    def _resolve_required_tools(
        self,
        required_names: tuple[str, ...],
        *,
        purpose: str,
        title: str,
        success_message: str,
        parent: QWidget | None = None,
        auto_start: bool | None = None,
    ) -> bool:
        """Run one contract-scoped setup and accept only a fresh complete verification."""

        from romverse.ui.toolchain_center import (
            ToolchainSetupDialog,
            activate_verified_managed_tools,
        )

        required_names = tuple(dict.fromkeys(required_names))
        host = current_host()
        should_auto_start = (
            self.app_settings.auto_download_verified_tools
            if auto_start is None
            else auto_start
        )
        dialog = ToolchainSetupDialog(
            host,
            self.tool_statuses,
            self.store.workspace,
            parent or self,
            required_names=required_names,
            auto_start=should_auto_start,
            auto_close=should_auto_start,
        )
        dialog.setWindowTitle(title)
        dialog.status.setText(purpose)
        dialog.exec()
        activate_verified_managed_tools(self.store.workspace)
        self.set_tool_statuses(ToolVerifier(host, SubprocessRunner()).verify_extended())
        # MainWindow consumes the same complete inventory to atomically activate or revoke
        # ADB-dependent Desktop services. Standalone Studio remains fully updated above.
        self.tool_statuses_resolved.emit(self.tool_statuses)
        refreshed = {item.name: item for item in self.tool_statuses}
        remaining = tuple(
            name
            for name in required_names
            if name not in refreshed or not refreshed[name].available
        )
        if not remaining:
            self.operation_status.setText(success_message)
            self.operation_status.setObjectName("Good")
            self._repolish(self.operation_status)
            return True
        detail = dialog.last_message.strip()
        self.operation_status.setText(
            detail or f"Required tools remain unverified: {', '.join(remaining)}."
        )
        self.operation_status.setObjectName("Warning")
        self._repolish(self.operation_status)
        return False

    def _open_build_control(self, parent: QWidget | None = None) -> None:
        if self.current_project is None:
            return
        from romverse.ui.build_control import BuildControlCenter

        pending = self._pending_repair_solution
        if pending is not None:
            (
                action_id,
                fingerprint_id,
                receipt_digest,
                source_id,
                project_id,
                source_sha256,
                receipt,
            ) = pending
            if (
                self.current_project.project_id != project_id
                or self.current_project.original is None
                or self.current_project.original.sha256 != source_sha256
            ):
                self._pending_repair_solution = None
                self.outbound_handoff_stopped(
                    "Forge Control",
                    "The selected project or protected firmware changed after the Smart Solution handoff",
                )
                return
            dialog = BuildControlCenter(self, parent or self, auto_start=False)
            if not dialog.open_solution_review(
                action_id,
                fingerprint_id,
                receipt_digest,
                source_id,
                receipt,
            ):
                self._pending_repair_solution = None
                dialog.close()
                self.outbound_handoff_stopped(
                    "Forge Control",
                    "The typed Smart Solution action is no longer registered",
                )
                return
            self._pending_repair_solution = None
        else:
            dialog = BuildControlCenter(self, parent or self, auto_start=False)
        dialog.exec()
        if dialog.guardian_manifest_requested:
            self._open_guardian_manifest_review(parent)

    def _open_guardian_manifest_review(self, parent: QWidget | None = None) -> None:
        if self.current_project is None or self.worker is not None:
            return
        from romverse.rom.readiness import BuildReadinessService

        device = next(
            (
                item
                for item in self.devices
                if item.state is DeviceState.DEVICE and not item.is_simulated
            ),
            None,
        )
        if device is None:
            QMessageBox.warning(
                parent or self,
                "Reconnect the exact target phone",
                "Guardian must re-check the exact authorized phone before opening its manifest review.",
            )
            return
        report = BuildReadinessService(
            self.store,
            self.pack_registry,
            self.tool_statuses,
            self.attestation_store,
        ).assess(
            self.current_project.project_id,
            tuple(self.devices),
            persist=False,
        )
        avbtool = next(
            (
                Path(item.path)
                for item in self.tool_statuses
                if item.name == "AVBTool" and item.available and item.path
            ),
            None,
        )
        runner = (
            self.filesystem_service.runner
            if self.filesystem_service is not None
            else SubprocessRunner()
        )
        binding_service = GuardianArtifactBindingService(
            self.store,
            self.pack_registry,
            self.tool_statuses,
            avbtool,
            runner,
        )
        self._latest_guardian_execution_plan = None
        self._latest_guardian_gateway_contract = None
        self._latest_guardian_reviewed_device = device
        worker = GuardianReviewWorker(
            binding_service,
            GuardianManifestReviewService(self.store, self.pack_registry),
            self.current_project.project_id,
            report,
            device,
        )
        self._launch_worker(worker, "guardian-review")

    def _new_recipe(self) -> None:
        if self.current_project is None:
            return
        name, accepted = QInputDialog.getText(self, "New ROMVERSE recipe", "Recipe name")
        if not accepted or not name.strip():
            return
        step = self._prompt_recipe_step("step-1")
        if step is None:
            return
        recipe = RomRecipe(
            1,
            name.strip().casefold().replace(" ", "-"),
            name.strip(),
            "User-authored Guardian-controlled local recipe",
            (step,),
        )
        try:
            RecipeStore().save(self.store.projects_root / self.current_project.project_id, recipe)
        except ProjectError as exc:
            QMessageBox.warning(self, "Recipe not created", str(exc))
            return
        self.operation_status.setText(
            "Recipe saved. Preview its targets, then run it with Guardian approval and automatic rollback."
        )
        self.operation_status.setObjectName("Good")
        self._repolish(self.operation_status)
        self.refresh(self.current_project.project_id)

    def _execute_recipe(self) -> None:
        if self.current_project is None:
            return
        project_id = self.current_project.project_id
        recipe = RecipeStore().load(self.store.projects_root / project_id)
        tree = self.store.working_root / project_id / "tree"
        if recipe is None or not tree.is_dir():
            return
        preview = preview_recipe(recipe, tree)
        if preview.unresolved_targets:
            QMessageBox.warning(
                self,
                "Recipe targets unresolved",
                "Fix these targets before execution:\n\n" + "\n".join(preview.unresolved_targets),
            )
            return
        mutations = tuple(step for step in recipe.steps if step.operation != "inspect")
        if not mutations:
            QMessageBox.information(
                self,
                "Inspection-only recipe",
                "This recipe contains no changes. Use Preview recipe to inspect its targets.",
            )
            return
        summary = "\n".join(
            f"• {step.operation.replace('_', ' ')}  →  {step.target}" for step in recipe.steps
        )
        answer = QMessageBox.question(
            self,
            "Run approved local recipe?",
            f"Recipe: {recipe.name}\n"
            f"Digest: {recipe.digest()[:20]}…\n\n"
            f"{summary}\n\n"
            "ROMVERSE will bind approval to the current tree and replacement inputs, snapshot "
            "every affected target, run each step, and verify the result. If any step fails, "
            "the working tree is restored automatically. Protected originals and phones are never touched.",
        )
        if answer is QMessageBox.StandardButton.Yes:
            self._start_worker("execute-recipe")

    def _restore_recipe(self) -> None:
        if self.current_project is None:
            return
        project_id = self.current_project.project_id
        snapshots = RecipeExecutor.list_snapshots(
            self.store.snapshots_root / project_id / "recipes"
        )
        if not snapshots:
            return
        labels = [
            f"{snapshot.snapshot_id}  •  {len(snapshot.targets)} target(s)  •  {snapshot.snapshot_digest[:12]}…"
            for snapshot in snapshots
        ]
        selected, accepted = QInputDialog.getItem(
            self, "Restore recipe snapshot", "Verified snapshot", labels, 0, False
        )
        if not accepted:
            return
        snapshot = snapshots[labels.index(selected)]
        answer = QMessageBox.question(
            self,
            "Confirm working-tree rollback",
            f"Restore {len(snapshot.targets)} affected target(s) from {snapshot.snapshot_id}?\n\n"
            "The protected original and connected phone will not be changed.",
        )
        if answer is QMessageBox.StandardButton.Yes:
            self._start_worker("rollback-recipe", Path(snapshot.workspace_path))

    def _apply_replace(self) -> None:
        if self.current_project is None:
            return
        recipe = RecipeStore().load(self.store.projects_root / self.current_project.project_id)
        if recipe is None or len(recipe.steps) != 1:
            return
        source, _ = QFileDialog.getOpenFileName(
            self, "Choose replacement file", str(Path.home()), "All files (*)"
        )
        if not source:
            return
        target = recipe.steps[0].target
        if (
            QMessageBox.question(
                self,
                "Approve replacement",
                f"Replace {target} in the isolated working tree? A safety snapshot will be created first.",
            )
            == QMessageBox.StandardButton.Yes
        ):
            self._start_worker("replace-file", Path(source))

    def _apply_property(self) -> None:
        if self.current_project is None:
            return
        recipe = RecipeStore().load(self.store.projects_root / self.current_project.project_id)
        if recipe is None or len(recipe.steps) != 1 or recipe.steps[0].operation != "set_property":
            return
        step = recipe.steps[0]
        values = dict(step.parameters)
        if "key" not in values or "value" not in values:
            QMessageBox.warning(
                self, "Property unavailable", "The recipe requires key and value parameters."
            )
            return
        if (
            QMessageBox.question(
                self,
                "Approve property change",
                f"Set {values['key']} in {step.target} to {values['value']}?",
            )
            == QMessageBox.StandardButton.Yes
        ):
            self._start_worker("set-property")

    def _plan_rollback(self) -> None:
        if self.current_project is None:
            return
        snapshots = self.store.list_snapshots(self.current_project.project_id)
        if not snapshots:
            return
        selected, accepted = QInputDialog.getItem(
            self, "Plan rollback", "Snapshot", [item.snapshot_id for item in snapshots], 0, False
        )
        if not accepted:
            return
        try:
            plan = self.store.plan_rollback(self.current_project.project_id, selected)
        except ProjectError as exc:
            QMessageBox.warning(self, "Rollback unavailable", str(exc))
            return
        if plan.verified:
            self.operation_status.setText(
                f"Rollback evidence is current for {plan.snapshot_id}. Time Machine will fully rehash the bytes before any approval-bound local restore; the phone is never a target."
            )
        else:
            self.operation_status.setText(
                f"Snapshot {plan.snapshot_id} is preserved legacy evidence. Open Time Machine and choose Verify snapshot before planning a restore."
            )

    def _add_recipe_step(self) -> None:
        if self.current_project is None:
            return
        store = RecipeStore()
        project_dir = self.store.projects_root / self.current_project.project_id
        recipe = store.load(project_dir)
        if recipe is None:
            return
        step = self._prompt_recipe_step(f"step-{len(recipe.steps) + 1}")
        if step is None:
            return
        updated = RomRecipe(
            1, recipe.recipe_id, recipe.name, recipe.description, (*recipe.steps, step)
        )
        try:
            store.save(project_dir, updated)
        except ProjectError as exc:
            QMessageBox.warning(self, "Recipe step not added", str(exc))
            return
        self.operation_status.setText(
            f"Added {step.operation.replace('_', ' ')} step {step.step_id}. Preview the complete recipe before running it."
        )
        self.operation_status.setObjectName("Good")
        self._repolish(self.operation_status)
        self.refresh(self.current_project.project_id)

    def _prompt_recipe_step(self, step_id: str) -> RecipeStep | None:
        if self.current_project is None:
            return None
        target, accepted = QInputDialog.getText(
            self,
            "Recipe target",
            "Relative path inside the extracted working tree",
        )
        if not accepted or not target.strip():
            return None
        target = target.strip().replace("\\", "/")
        tree = self.store.working_root / self.current_project.project_id / "tree"
        resolved = (tree / target).resolve(strict=False)
        if (
            Path(target).is_absolute()
            or ".." in Path(target).parts
            or not resolved.is_relative_to(tree.resolve())
            or not resolved.exists()
        ):
            QMessageBox.warning(
                self,
                "Target unavailable",
                "Choose an existing contained path from the extracted working tree.",
            )
            return None
        labels = (
            "Inspect only",
            "Replace file",
            "Set property",
            "Remove package or path",
        )
        selected, accepted = QInputDialog.getItem(
            self, "Recipe operation", "Bounded operation", labels, 0, False
        )
        if not accepted:
            return None
        operation = {
            "Inspect only": "inspect",
            "Replace file": "replace_file",
            "Set property": "set_property",
            "Remove package or path": "remove_package",
        }[selected]
        parameters: tuple[tuple[str, str], ...] = ()
        if operation == "replace_file":
            if not resolved.is_file():
                QMessageBox.warning(
                    self, "File required", "Replace file requires a regular file target."
                )
                return None
            source, _ = QFileDialog.getOpenFileName(
                self, "Choose replacement file", str(Path.home()), "All files (*)"
            )
            if not source:
                return None
            parameters = (("source", source),)
        elif operation == "set_property":
            if not resolved.is_file():
                QMessageBox.warning(
                    self, "Text file required", "Set property requires a regular text file target."
                )
                return None
            key, accepted = QInputDialog.getText(self, "Property key", "Property name")
            if not accepted or not key:
                return None
            value, accepted = QInputDialog.getText(self, "Property value", "New value")
            if not accepted:
                return None
            parameters = (("key", key), ("value", value))
        return RecipeStep(step_id, operation, target, parameters)

    def _inspect_external(self) -> None:
        if self.current_project is None or self.current_project.original is not None:
            return
        existing = self.external_intake.load(self.current_project.project_id)
        if existing is not None:
            self._start_worker("external-intake", Path(existing.source_path))
            return
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose firmware for read-only inspection",
            str(Path.home()),
            "Android firmware (*.zip *.img *.bin *.tar *.md5 *.tgz *.xz);;All files (*)",
        )
        if selected:
            self._start_worker("external-intake", Path(selected))

    def _import_original(self) -> None:
        if self.current_project is None:
            return
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose original firmware",
            str(Path.home()),
            "Android firmware (*.zip *.img *.bin *.tar *.md5 *.tgz *.xz);;All files (*)",
        )
        if not selected:
            return
        source = Path(selected)
        try:
            size = source.stat().st_size
        except OSError as exc:
            QMessageBox.warning(self, "Original unavailable", str(exc))
            return
        answer = QMessageBox.question(
            self,
            "Import protected original?",
            f"ROMVERSE will copy {source.name} ({human_bytes(size)}) into Original ROMs, compute SHA-256, "
            "protect the copy, and automatically inspect its bounded structure for Device DNA. "
            "The source file will not be changed or extracted in place.\n\n"
            + USER_FIRMWARE_RESPONSIBILITY_NOTICE
            + "\n\nBy selecting Yes, you confirm that you understand and accept this responsibility.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._start_worker("import", source)

    def _verify(self) -> None:
        if self.current_project is not None:
            self._start_worker("verify")

    def _inspect(self) -> None:
        if self.current_project is not None:
            self._start_worker("inspect")

    def _start_worker(
        self,
        operation: str,
        source: Path | None = None,
        partitions: tuple[str, ...] = (),
        *,
        guided_evidence: bool = False,
    ) -> None:
        if self.current_project is None or self.worker is not None:
            return
        if operation == "verify-plan" and not guided_evidence:
            existing_plan = RomBuildPlanner(self.store).load(self.current_project.project_id)
            guided_evidence = existing_plan is not None and existing_plan.schema_version >= 3
        required_tools = (
            self.guided_context().required_tools
            if guided_evidence and operation in {"plan", "verify-plan"}
            else ()
        )
        worker = ProjectWorker(
            self.store,
            operation,
            self.current_project.project_id,
            source=source,
            inspection=self.inspection,
            payload_service=self.payload_service,
            filesystem_service=self.filesystem_service,
            partitions=partitions,
            source_avb_service=self.source_avb_service,
            tool_statuses=self.tool_statuses,
            required_tools=required_tools,
        )
        self._launch_worker(worker, operation)

    def _launch_worker(self, worker: ManagedRunnable, operation: str) -> None:
        self.worker = worker
        self._active_operation = operation
        self._active_project_id = str(getattr(worker, "project_id", ""))
        self._last_validated_completion = None
        self._last_recovery_report = None
        self.operation_started.emit(operation)
        self.new_button.setEnabled(False)
        self.project_list.setEnabled(False)
        self.external_intake_button.setEnabled(False)
        self.import_button.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.inspect_button.setEnabled(False)
        self.working_button.setEnabled(False)
        self.snapshot_button.setEnabled(False)
        self.extract_button.setEnabled(False)
        self.plan_button.setEnabled(False)
        self.verify_plan_button.setEnabled(False)
        self.forge_button.setEnabled(False)
        self.verify_forge_button.setEnabled(False)
        self.recipe_button.setEnabled(False)
        self.new_recipe_button.setEnabled(False)
        self.guided_recipe_button.setEnabled(False)
        self.add_step_button.setEnabled(False)
        self.rollback_button.setEnabled(False)
        self.replace_button.setEnabled(False)
        self.property_button.setEnabled(False)
        self.partition_button.setEnabled(False)
        self.build_control_button.setEnabled(False)
        self.progress.begin(
            determinate=operation
            in {
                "external-intake",
                "verify",
                "working-copy",
                "forge-bundle",
            }
        )
        self.operation_status.setText(
            "Copying the protected source with measured byte progress, then automatically detecting its structure without inventing an inspection percentage…"
            if operation == "import"
            else "Hashing the external firmware in place with measured byte progress, then reading bounded container metadata without copying, extracting, or granting authority…"
            if operation == "external-intake"
            else "Recomputing SHA-256 with measured bytes, then inspecting bounded structure metadata without inventing a percentage…"
            if operation == "inspect"
            else "Creating isolated working copy…"
            if operation == "working-copy"
            else "Creating Time Machine snapshot…"
            if operation == "snapshot"
            else "Verifying the source and structure with an animated preflight, then reporting measured extracted bytes while the isolated working tree is created…"
            if operation == "extract"
            else "Generating deterministic build plan…"
            if operation == "plan"
            else "Verifying extracted tree against the saved build plan…"
            if operation == "verify-plan"
            else "Forging a deterministic bundle and verifying every input byte…"
            if operation == "forge-bundle"
            else "Verifying the Forge archive, safety manifest, and bundled file hashes…"
            if operation == "verify-forge"
            else "Verifying payload.bin and reading its partition map without inventing an external-tool percentage…"
            if operation == "scan-payload"
            else "Extracting with an animated external-tool phase; measured output-byte verification appears when images exist…"
            if operation == "extract-payload"
            else "Expanding the selected read-only partition filesystem into the contained ROM tree…"
            if operation == "expand-filesystem"
            else "Verifying the firmware's own vbmeta chain and signing identity locally. This creates source evidence only and grants no signing, Pack, or phone authority…"
            if operation == "inspect-source-avb"
            else "Previewing recipe targets without mutation…"
            if operation == "preview-recipe"
            else "Verifying approval and creating rollback protection with an animated preflight, then reporting completed recipe steps; final tree and receipt verification remain below completion…"
            if operation == "execute-recipe"
            else "Verifying and restoring the selected recipe snapshot…"
            if operation == "rollback-recipe"
            else "Guardian is rehashing every declared image across the manifest, inert plan, and applicable result template with one measured byte progress scale, without inventing completion… phone changed: NO"
            if operation == "guardian-review"
            else "Recomputing SHA-256…"
        )
        if (
            self._automatic_preparation_project_id
            and self._automatic_preparation_project_id == self._active_project_id
            and operation in {"working-copy", "extract"}
        ):
            self.operation_status.setText(
                f"{self._automatic_preparation_destination} automatic preparation  •  "
                + self.operation_status.text()
                + "  •  protected source unchanged  •  phone unchanged"
            )
        self.operation_status.setObjectName("Muted")
        self._repolish(self.operation_status)
        signals = worker.signals
        signals.progress.connect(self.progress.report)
        signals.progress.connect(
            lambda value, active=operation: self.operation_progress.emit(active, value)
        )
        signals.recovery.connect(self._workspace_recovered)
        signals.complete.connect(self._worker_complete)
        signals.failed.connect(self._worker_failed)
        start_background(worker)

    @Slot(object)
    def _workspace_recovered(self, report: object) -> None:
        if (
            not isinstance(report, WorkspaceRecoveryReport)
            or report.project_id != self._active_project_id
            or report.phone_changed
            or report.protected_original_changed
            or report.execution_authority != "none"
            or report.bootloader_relock != "never"
        ):
            return
        self._last_recovery_report = report
        self.operation_status.setText(self._recovery_notice(report))
        self.operation_status.setObjectName("Warning" if report.blocked_paths else "Good")
        self._repolish(self.operation_status)

    @staticmethod
    def _recovery_notice(report: WorkspaceRecoveryReport) -> str:
        removed = report.recovered_count
        copy = (
            f"Automatic recovery cleared {removed} interrupted ROMVERSE transaction "
            f"artifact{'s' if removed != 1 else ''} before retrying."
            if removed
            else "Automatic recovery found no removable interrupted transaction artifacts."
        )
        if report.blocked_paths:
            blocked = len(report.blocked_paths)
            copy += (
                f" {blocked} unsafe or unreadable candidate{'s were' if blocked != 1 else ' was'} "
                "contained and left untouched."
            )
        return copy + " Protected original: unchanged • phone: unchanged • relock: never."

    def _completion_evidence_error(
        self,
        operation: str,
        project_id: str,
        result: object,
    ) -> str:
        """Return a fixed safe error unless the producer result matches current evidence."""

        expected_types: dict[str, type | tuple[type, ...]] = {
            "import": FirmwareImportResult,
            "external-intake": ExternalFirmwareIntakeReceipt,
            "verify": ArtifactVerification,
            "inspect": RomInspectionReport,
            "working-copy": WorkingCopy,
            "snapshot": TimeMachineSnapshot,
            "extract": Path,
            "plan": BuildPlan,
            "verify-plan": ArtifactVerification,
            "forge-bundle": ForgeBundleReceipt,
            "verify-forge": ArtifactVerification,
            "scan-payload": PayloadManifest,
            "extract-payload": PayloadManifest,
            "expand-filesystem": FilesystemManifest,
            "inspect-source-avb": SourceAvbTopologyReceipt,
            "preview-recipe": RecipePreview,
            "replace-file": ExecutionReceipt,
            "set-property": ExecutionReceipt,
            "execute-recipe": RecipeRunReceipt,
            "rollback-recipe": RecipeRollbackReceipt,
            "guardian-review": GuardianManifestReview,
        }
        expected = expected_types.get(operation)
        if not project_id or expected is None or not isinstance(result, expected):
            return "ROM Studio rejected unexpected or stale terminal evidence"
        bound_project = getattr(result, "project_id", project_id)
        if isinstance(bound_project, str) and bound_project != project_id:
            return "ROM Studio rejected terminal evidence bound to another project"
        try:
            if isinstance(result, FirmwareImportResult):
                if (
                    result.project.project_id != project_id
                    or self.store.get(project_id) != result.project
                    or self.inspection.load_report(project_id) != result.inspection
                ):
                    return "ROM Studio rejected changed firmware-import evidence"
            elif isinstance(result, ExternalFirmwareIntakeReceipt):
                if self.external_intake.load(project_id) != result:
                    return "ROM Studio rejected changed external firmware-intake evidence"
            elif isinstance(result, RomInspectionReport):
                if self.inspection.load_report(project_id) != result:
                    return "ROM Studio rejected changed structure-inspection evidence"
            elif isinstance(result, WorkingCopy):
                if self.store.working_copy(project_id) != result:
                    return "ROM Studio rejected changed working-copy evidence"
            elif isinstance(result, TimeMachineSnapshot):
                saved = next(
                    (
                        item
                        for item in self.store.list_snapshots(project_id)
                        if item.snapshot_id == result.snapshot_id
                    ),
                    None,
                )
                if saved != result:
                    return "ROM Studio rejected changed Time Machine evidence"
            elif operation == "extract" and isinstance(result, Path):
                expected_tree = (self.store.working_root / project_id / "tree").resolve()
                if (
                    result.resolve(strict=False) != expected_tree
                    or not expected_tree.is_dir()
                    or expected_tree.is_symlink()
                ):
                    return "ROM Studio rejected an unexpected extraction destination"
            elif isinstance(result, BuildPlan):
                if RomBuildPlanner(self.store).load(project_id) != result:
                    return "ROM Studio rejected changed build-plan evidence"
            elif operation == "verify-plan" and isinstance(result, ArtifactVerification):
                plan = RomBuildPlanner(self.store).load(project_id)
                if (
                    plan is None
                    or (
                        self._automatic_simulation_verification_plan
                        and plan != self._automatic_simulation_verification_plan
                    )
                    or result.expected_sha256 != plan.tree_sha256
                    or (
                        result.valid
                        and (
                            result.status != "Working tree matches build plan"
                            or result.actual_sha256 != plan.tree_sha256
                        )
                    )
                    or (not result.valid and result.status == "Working tree matches build plan")
                ):
                    return "ROM Studio rejected mismatched build-plan verification evidence"
            elif operation == "verify-forge" and isinstance(result, ArtifactVerification):
                current = self._automatic_forge_verification
                receipt = ForgeBundleService(self.store).load_receipt(project_id)
                plan = RomBuildPlanner(self.store).load(project_id)
                if (
                    receipt is None
                    or plan is None
                    or not ForgeBundleService.receipt_matches_plan(receipt, plan)
                    or (current is not None and current != (plan, receipt))
                    or receipt.plan_tree_sha256 != plan.tree_sha256
                    or result.expected_sha256 != receipt.archive_sha256
                    or (
                        result.valid
                        and (
                            not result.status.startswith("Forge Bundle verified;")
                            or result.actual_sha256 != receipt.archive_sha256
                        )
                    )
                    or (not result.valid and result.status.startswith("Forge Bundle verified;"))
                ):
                    return "ROM Studio rejected mismatched Forge Bundle verification evidence"
            elif isinstance(result, ForgeBundleReceipt):
                plan = RomBuildPlanner(self.store).load(project_id)
                if (
                    ForgeBundleService(self.store).load_receipt(project_id) != result
                    or plan is None
                    or not ForgeBundleService.receipt_matches_plan(result, plan)
                    or (
                        self._intentional_forge_plan is not None
                        and plan != self._intentional_forge_plan
                    )
                    or result.plan_tree_sha256 != plan.tree_sha256
                    or result.signed
                    or result.bootable
                    or result.flashable
                ):
                    return "ROM Studio rejected changed Forge Bundle evidence"
            elif isinstance(result, PayloadManifest):
                if self.payload_service is None or self.payload_service.load(project_id) != result:
                    return "ROM Studio rejected changed payload evidence"
            elif isinstance(result, FilesystemManifest):
                if (
                    self.filesystem_service is None
                    or self.filesystem_service.load(project_id, result.partition) != result
                ):
                    return "ROM Studio rejected changed filesystem evidence"
            elif isinstance(result, SourceAvbTopologyReceipt):
                if (
                    self.source_avb_service is None
                    or self.source_avb_service.load(project_id) != result
                ):
                    return "ROM Studio rejected changed source AVB evidence"
            elif isinstance(result, RecipeRunReceipt):
                project_dir = self.store.projects_root / project_id
                recipe = RecipeStore().load(project_dir)
                tree = self.store.working_root / project_id / "tree"
                snapshot_root = self.store.snapshots_root / project_id / "recipes"
                if (
                    recipe is None
                    or load_run_receipt(
                        project_dir,
                        recipe=recipe,
                        tree_root=tree,
                        snapshot_root=snapshot_root,
                    )
                    != result
                ):
                    return "ROM Studio rejected changed Recipe execution evidence"
            elif isinstance(result, GuardianManifestReview):
                persisted = GuardianManifestReviewService(self.store, self.pack_registry).load(
                    project_id
                )
                if persisted != result:
                    return "ROM Studio rejected changed Guardian review evidence"
            elif isinstance(result, ExecutionReceipt):
                if not result.success or not result.rollback_available:
                    return "ROM Studio rejected incomplete Recipe mutation evidence"
            elif isinstance(result, RecipeRollbackReceipt) and not result.success:
                return "ROM Studio rejected incomplete Recipe rollback evidence"
        except (OSError, ProjectError, ValueError, TypeError):
            return "ROM Studio could not independently reload terminal evidence"
        return ""

    def is_validated_completion(self, operation: str, result: object) -> bool:
        """Tell Genesis whether this exact object crossed Studio's verified boundary."""

        project_id = self.current_project.project_id if self.current_project is not None else ""
        return self._last_validated_completion == (operation, project_id, id(result))

    def guardian_execution_context(
        self,
        manifest: GuardianManifestReview,
    ) -> tuple[
        GuardianExecutionPlan | None,
        GuardianExecutionGatewayContract | None,
    ]:
        """Return only the locally validated inert evidence attached to this exact manifest."""

        plan = self._latest_guardian_execution_plan
        if plan is None:
            return None, None
        try:
            GuardianExecutionPlanService(self.store, self.pack_registry).validate(plan)
        except ProjectError:
            return None, None
        if not execution_plan_matches_manifest(plan, manifest):
            return None, None

        contract = self._latest_guardian_gateway_contract
        if contract is None:
            return plan, None
        try:
            GuardianExecutionGatewayContractService(
                self.store,
                self.pack_registry,
            ).validate(contract)
        except ProjectError:
            return plan, None
        if not gateway_contract_matches_plan(contract, plan):
            return plan, None
        return plan, contract

    def _live_target_service(self) -> GuardianLiveTargetReceiptService | None:
        """Create the read-only final identity checker only with both verified tools."""

        if self.gateway is None or self.adb_executable is None or self.fastboot_executable is None:
            return None
        return GuardianLiveTargetReceiptService(
            self.store,
            AdbClient(self.adb_executable, self.gateway),
            FastbootClient(self.fastboot_executable, self.gateway),
        )

    @Slot(object)
    def _worker_complete(self, result: object) -> None:
        completed_worker = self.worker
        operation = self._active_operation
        project_id = self._active_project_id
        evidence_error = self._completion_evidence_error(operation, project_id, result)
        if evidence_error:
            self._worker_failed(evidence_error)
            return
        if (
            operation == "verify-plan"
            and self._automatic_simulation_verification_plan is not None
            and isinstance(result, ArtifactVerification)
            and not result.valid
        ):
            self._worker_failed(result.status)
            return
        if (
            operation == "verify-forge"
            and self._automatic_forge_verification is not None
            and isinstance(result, ArtifactVerification)
            and not result.valid
        ):
            self._worker_failed(result.status)
            return
        self._active_operation = ""
        self._active_project_id = ""
        self.worker = None
        self.new_button.setEnabled(True)
        self.project_list.setEnabled(True)
        self.progress.finish()
        if isinstance(result, FirmwareImportResult):
            self.operation_status.setText(
                "Original copied, hashed, protected, and structurally detected successfully. "
                "Device DNA and the Capability Map were refreshed from the saved evidence."
            )
            project_id = result.project.project_id
        elif isinstance(result, ExternalFirmwareIntakeReceipt):
            self.operation_status.setText(
                "External firmware hashed and bounded-inspected in place. No copy, extraction, "
                "build, device action, or execution authority was created."
            )
            project_id = result.project_id
        elif isinstance(result, RomProject):
            self.operation_status.setText("Original copied, hashed, and protected successfully.")
            project_id = result.project_id
        elif isinstance(result, ArtifactVerification):
            self.operation_status.setText(result.status)
        elif isinstance(result, RomInspectionReport):
            self.operation_status.setText(
                "Structure inspection complete. No content was extracted."
            )
        elif isinstance(result, WorkingCopy):
            self.operation_status.setText("Isolated working copy created and integrity verified.")
        elif isinstance(result, TimeMachineSnapshot):
            self.operation_status.setText(
                "Time Machine snapshot saved and verified. Local baseline recovery is available in Time Machine."
            )
        elif isinstance(result, Path):
            self.operation_status.setText("Safe extraction complete in the isolated working tree.")
        elif isinstance(result, BuildPlan):
            self.operation_status.setText(
                f"Build dry-run plan saved ({len(result.input_files):,} inputs). "
                f"Guardian preflight: {result.guardian_status} / {result.guardian_risk}. Execution remains locked."
            )
        elif isinstance(result, ForgeBundleReceipt):
            root_state = (
                f"Ascension {result.rooted_partition} sealed and included"
                if result.ascension_handoff_digest
                else "unrooted route"
            )
            self.operation_status.setText(
                f"Forge Bundle created and verified  •  {result.file_count:,} files  •  "
                f"{human_bytes(result.content_bytes)}  •  SHA-256 {result.archive_sha256[:16]}…  •  "
                f"{root_state}  •  unsigned / non-bootable / non-flashable."
            )
        elif isinstance(result, PayloadManifest):
            extracted = sum(bool(item.extracted_path) for item in result.partitions)
            self.operation_status.setText(
                f"Payload evidence verified  •  {len(result.partitions)} partitions mapped"
                + (f"  •  {extracted} extracted and hashed." if extracted else ".")
            )
        elif isinstance(result, FilesystemManifest):
            self.operation_status.setText(
                f"{result.partition} filesystem expanded safely  •  "
                f"{result.file_count:,} files  •  {human_bytes(result.content_bytes)} browsable content."
            )
        elif isinstance(result, SourceAvbTopologyReceipt):
            top = result.images[0]
            chains = ", ".join(result.top_level_chain_partitions) or "none"
            state = "consistent" if result.signing_identity_consistent else "requires review"
            self.operation_status.setText(
                f"OEM source AVB verified  •  {state}  •  {top.algorithm}  •  "
                f"key {top.public_key_sha1[:16]}…  •  chains: {chains}  •  "
                "source evidence only  •  Pack/signing/flash authority: NONE  •  phone changed: NO"
            )
        elif isinstance(result, RecipePreview):
            self.operation_status.setText(
                f"Recipe preview: {len(result.matched_targets)} matched, "
                f"{len(result.unresolved_targets)} unresolved. Changes still require explicit approval."
            )
        elif isinstance(result, ExecutionReceipt):
            self.operation_status.setText(
                f"Replacement verified. Before {result.before_sha256[:12]}… → after {result.after_sha256[:12]}…. Rollback available."
            )
        elif isinstance(result, RecipeRunReceipt):
            changed = sum(step.changed for step in result.steps)
            self.operation_status.setText(
                f"Recipe complete and verified  •  {len(result.steps)} step(s), "
                f"{changed} change(s)  •  automatic snapshot {result.snapshot_id}."
            )
        elif isinstance(result, RecipeRollbackReceipt):
            self.operation_status.setText(
                f"Recipe rollback complete and verified  •  "
                f"{len(result.restored_targets)} target(s) restored from {result.snapshot_id}."
            )
        elif isinstance(result, GuardianManifestReview):
            if isinstance(completed_worker, GuardianReviewWorker):
                self._latest_guardian_execution_plan = completed_worker.execution_plan
                self._latest_guardian_gateway_contract = completed_worker.gateway_contract
            else:
                self._latest_guardian_execution_plan = None
                self._latest_guardian_gateway_contract = None
            bound = len(result.partition_writes)
            plan, contract = self.guardian_execution_context(result)
            self.operation_status.setText(
                f"Guardian review sealed  •  {bound} image(s) hash-bound for review  •  "
                + (
                    f"inert plan: {len(plan.commands)} step(s)  •  "
                    if plan is not None
                    else "inert plan: unavailable  •  "
                )
                + (
                    f"result template: {contract.step_count} checks  •  "
                    if contract is not None
                    else "result template: locked  •  "
                )
                + "executable commands: NONE  •  execution: NONE  •  "
                "final consent: LOCKED  •  phone changed: NO"
            )
        if self._last_recovery_report is not None:
            self.operation_status.setText(
                self.operation_status.text()
                + "\n"
                + self._recovery_notice(self._last_recovery_report)
            )
        successful = isinstance(
            result,
            (
                RomProject,
                FirmwareImportResult,
                ExternalFirmwareIntakeReceipt,
                RomInspectionReport,
                Path,
                WorkingCopy,
                TimeMachineSnapshot,
                ExecutionReceipt,
                RecipePreview,
                RecipeRunReceipt,
                RecipeRollbackReceipt,
                PayloadManifest,
                FilesystemManifest,
                SourceAvbTopologyReceipt,
                BuildPlan,
                ForgeBundleReceipt,
                GuardianManifestReview,
            ),
        ) or (isinstance(result, ArtifactVerification) and result.valid)
        self.operation_status.setObjectName("Good" if successful else "Danger")
        self._repolish(self.operation_status)
        self.refresh(project_id)
        self._last_validated_completion = (operation, project_id, id(result))
        self.operation_completed.emit(operation, result)
        if self._complete_automatic_forge_verification(operation, project_id, result):
            return
        if self._complete_intentional_forge_bundle(operation, project_id, result):
            return
        if self._complete_automatic_simulation_verification(operation, project_id, result):
            return
        if self._complete_automatic_prebuild_simulation(operation, project_id, result):
            return
        if self._continue_automatic_local_preparation(operation, project_id):
            return
        if isinstance(result, GuardianManifestReview):
            from romverse.ui.build_control import GuardianManifestReviewDialog

            plan, contract = self.guardian_execution_context(result)
            live_target_service = self._live_target_service() if contract is not None else None
            if plan is None and contract is None:
                review = GuardianManifestReviewDialog(result, self)
            else:
                review = GuardianManifestReviewDialog(
                    result,
                    self,
                    execution_plan=plan,
                    gateway_contract=contract,
                    live_target_service=live_target_service,
                    reviewed_device=self._latest_guardian_reviewed_device,
                )
            review.exec()
            if review.open_guardian_core_requested:
                self.guardian_review_requested.emit(
                    result.project_id,
                    result.manifest_digest,
                )

    def _complete_intentional_forge_bundle(
        self,
        operation: str,
        project_id: str,
        result: object,
    ) -> bool:
        """Continue one explicit Forge choice only after exact persisted receipt acceptance."""

        requested_plan = self._intentional_forge_plan
        if requested_plan is None:
            return False
        self._intentional_forge_plan = None
        plan = RomBuildPlanner(self.store).load(project_id)
        receipt = ForgeBundleService(self.store).load_receipt(project_id)
        if (
            operation != "forge-bundle"
            or project_id != requested_plan.project_id
            or self.current_project is None
            or self.current_project.project_id != project_id
            or plan != requested_plan
            or not isinstance(result, ForgeBundleReceipt)
            or receipt != result
            or not ForgeBundleService.receipt_matches_plan(result, requested_plan)
            or result.plan_tree_sha256 != requested_plan.tree_sha256
            or result.signed
            or result.bootable
            or result.flashable
        ):
            self._show_dashboard_handoff(
                "Forge Bundle → Creation stopped safely",
                "The producer result no longer matches the exact requested project, plan, tree, "
                "or persisted receipt. ROMVERSE preserved current evidence and did not retry, "
                "verify, build, sign, or change a phone. Review Build & Proof before choosing "
                "Forge Bundle again.",
                "ATTENTION",
                ready=False,
            )
            self.forge_button.setFocus(Qt.FocusReason.OtherFocusReason)
            return True
        self._automatic_forge_verification = (requested_plan, result)
        self._show_dashboard_handoff(
            "Forge Bundle → Verifying artifact",
            f"ROMVERSE accepted {result.archive_sha256[:16]}… as the exact persisted typed "
            "receipt for this project and plan. The existing read-only verifier is checking the "
            "archive, manifest, members, hashes, and non-flashable safety contract once; no "
            "build, signing, execution, or phone action starts.",
            "VERIFYING",
            ready=True,
        )
        self._start_worker("verify-forge")
        return True

    def _complete_automatic_forge_verification(
        self,
        operation: str,
        project_id: str,
        result: object,
    ) -> bool:
        """Present one exact Forge verification without granting later authority."""

        requested = self._automatic_forge_verification
        if requested is None:
            return False
        self._automatic_forge_verification = None
        requested_plan, requested_receipt = requested
        plan = RomBuildPlanner(self.store).load(project_id)
        receipt = ForgeBundleService(self.store).load_receipt(project_id)
        if (
            operation != "verify-forge"
            or project_id != requested_plan.project_id
            or self.current_project is None
            or self.current_project.project_id != project_id
            or plan != requested_plan
            or receipt != requested_receipt
            or not ForgeBundleService.receipt_matches_plan(requested_receipt, requested_plan)
            or not isinstance(result, ArtifactVerification)
            or not result.valid
        ):
            self._show_dashboard_handoff(
                "Forge Bundle → Verification stopped safely",
                "The verification result no longer matches the exact project, plan, tree, or "
                "persisted Forge receipt. ROMVERSE preserved the available artifact evidence and "
                "did not retry, infer success, build, sign, or change a phone. Review Build & "
                "Proof before choosing another action.",
                "ATTENTION",
                ready=False,
            )
            self.verify_forge_button.setFocus(Qt.FocusReason.OtherFocusReason)
            return True
        self.command_tabs.setCurrentIndex(1)
        self.build_control_button.setFocus(Qt.FocusReason.OtherFocusReason)
        self._show_dashboard_handoff(
            "Forge Bundle → Verified intermediate",
            f"Exact artifact {receipt.archive_sha256[:16]}…  •  {receipt.file_count:,} file(s)  •  "
            f"{human_bytes(receipt.content_bytes)}  •  {result.status}. Forge Control is the next "
            "intentional inspection of later gated stages; nothing starts until you choose it. "
            "This result grants no build, signing, Guardian, device, flash, or execution authority.",
            "VERIFIED INTERMEDIATE",
            ready=True,
        )
        return True

    def _complete_automatic_simulation_verification(
        self,
        operation: str,
        project_id: str,
        result: object,
    ) -> bool:
        """Accept one verifier result only while its exact source plan is still current."""

        requested_plan = self._automatic_simulation_verification_plan
        if requested_plan is None:
            return False
        saved = self._automatic_simulation_verification_saved
        self._automatic_simulation_verification_plan = None
        self._automatic_simulation_verification_saved = False
        plan = RomBuildPlanner(self.store).load(project_id)
        if (
            operation != "verify-plan"
            or project_id != requested_plan.project_id
            or self.current_project is None
            or self.current_project.project_id != project_id
            or plan is None
            or plan != requested_plan
            or not isinstance(result, ArtifactVerification)
        ):
            self._show_dashboard_handoff(
                "Pre-Build Simulation → Verification stopped safely",
                "The verifier result or dry-run identity changed before it could be accepted. "
                "ROMVERSE preserved the plan and tree and did not retry, build, or change a "
                "phone. Review Build & Proof before requesting another Simulation.",
                "ATTENTION",
                ready=False,
            )
            return False
        if not result.valid:
            self._show_dashboard_handoff(
                "Pre-Build Simulation → Current tree needs attention",
                f"The existing verifier reported: {result.status}. ROMVERSE preserved the exact "
                "plan and current tree and did not retry or infer success. Review Build & Proof "
                "before requesting another Simulation; no build or phone action occurred.",
                "ATTENTION",
                ready=False,
            )
            self.verify_plan_button.setFocus(Qt.FocusReason.OtherFocusReason)
            return True
        self._show_prebuild_simulation_result(plan, result, saved=saved)
        return True

    def _complete_automatic_prebuild_simulation(
        self,
        operation: str,
        project_id: str,
        result: object,
    ) -> bool:
        """Present only the exact producer result accepted by Studio's durable boundary."""

        if not self._automatic_simulation_project_id:
            return False
        expected_project_id = self._automatic_simulation_project_id
        self._automatic_simulation_project_id = ""
        if (
            operation != "plan"
            or project_id != expected_project_id
            or self.current_project is None
            or self.current_project.project_id != project_id
            or not isinstance(result, BuildPlan)
        ):
            self._show_dashboard_handoff(
                "Pre-Build Simulation → Dry run stopped safely",
                "The dry-run result no longer matches the exact requested project. ROMVERSE "
                "preserved current evidence and did not guess, retry, build, or change a phone. "
                "Review Build & Proof before requesting another Simulation.",
                "ATTENTION",
                ready=False,
            )
            return False
        self._begin_automatic_simulation_verification(result, saved=False)
        return True

    def _continue_automatic_local_preparation(self, operation: str, project_id: str) -> bool:
        """Advance or resume one exact destination after producer-validated evidence."""

        if not self._automatic_preparation_project_id:
            return False
        destination = self._automatic_preparation_destination
        if (
            destination not in {"Pre-Build Simulation", "Recipes"}
            or project_id != self._automatic_preparation_project_id
            or self.current_project is None
            or self.current_project.project_id != project_id
            or operation not in {"working-copy", "extract"}
        ):
            self._automatic_preparation_project_id = ""
            self._automatic_preparation_destination = ""
            self._show_dashboard_handoff(
                f"{destination or 'Requested workflow'} → Preparation stopped safely",
                "The selected project or preparation evidence changed. ROMVERSE preserved prior "
                "progress and did not guess, retry, or continue into another project. Select the "
                "exact project and choose the requested workflow to reassess current evidence.",
                "ATTENTION",
                ready=False,
            )
            return False
        if operation == "working-copy":
            next_operation, detail = self._automatic_local_preparation_admission(destination)
            if next_operation != "extract":
                self._automatic_preparation_project_id = ""
                self._automatic_preparation_destination = ""
                self._show_dashboard_handoff(
                    f"{destination} → Preparation stopped safely",
                    detail
                    or "The isolated baseline is preserved, but current evidence no longer admits "
                    "contained-tree preparation. Review Source Lab, then choose the requested "
                    "workflow again; ROMVERSE did not retry or change the phone.",
                    "ATTENTION",
                    ready=False,
                )
                return False
            self._show_dashboard_handoff(
                f"{destination} → Automatic safe preparation",
                detail,
                "PREPARING",
                ready=True,
            )
            self._start_worker("extract")
            return True

        self._automatic_preparation_project_id = ""
        self._automatic_preparation_destination = ""
        ready, _detail = (
            self._recipe_forge_handoff()
            if destination == "Recipes"
            else self._prebuild_simulation_handoff()
        )
        if not ready:
            self._show_dashboard_handoff(
                f"{destination} → Preparation stopped safely",
                "The contained tree result was recorded, but current destination readiness did "
                "not validate. Prior progress is preserved; review Source Lab and choose the "
                "requested workflow again. ROMVERSE did not guess, retry, or change the phone.",
                "ATTENTION",
                ready=False,
            )
            return False
        self.open_dashboard_intent(destination)
        return True

    @Slot(str)
    def _worker_failed(self, message: str) -> None:
        operation = self._active_operation
        project_id = self._active_project_id
        automatic_preparation_failure = bool(
            self._automatic_preparation_project_id
            and project_id == self._automatic_preparation_project_id
            and operation in {"working-copy", "extract"}
        )
        automatic_destination = self._automatic_preparation_destination
        automatic_simulation_failure = bool(
            self._automatic_simulation_project_id
            and project_id == self._automatic_simulation_project_id
            and operation == "plan"
        )
        automatic_simulation_verification_failure = bool(
            self._automatic_simulation_verification_plan is not None
            and project_id == self._automatic_simulation_verification_plan.project_id
            and operation == "verify-plan"
        )
        intentional_forge_failure = bool(
            self._intentional_forge_plan is not None
            and project_id == self._intentional_forge_plan.project_id
            and operation == "forge-bundle"
        )
        automatic_forge_verification_failure = bool(
            self._automatic_forge_verification is not None
            and project_id == self._automatic_forge_verification[0].project_id
            and operation == "verify-forge"
        )
        if operation == "guardian-review":
            self._latest_guardian_execution_plan = None
            self._latest_guardian_gateway_contract = None
            self._latest_guardian_reviewed_device = None
        recovery = self._last_recovery_report
        self._active_operation = ""
        self._active_project_id = ""
        self._last_validated_completion = None
        self.worker = None
        self.new_button.setEnabled(True)
        self.project_list.setEnabled(True)
        self.progress.stop()
        status = message + ("\n" + self._recovery_notice(recovery) if recovery is not None else "")
        if self.current_project is not None:
            self._select(self.project_list.currentRow())
            report = self.scan_operation_failure_knowledge(
                self.current_project.project_id,
                operation,
                message,
            )
            if report is not None:
                best = (
                    f" Best match: {report.matches[0].record.title}."
                    if report.matches
                    else " No compatible local record matched; ROMVERSE did not guess."
                )
                status += (
                    f"\nOffline Archives scanned {len(report.matches)} compatible match(es)."
                    f"{best} Guidance only; no action started."
                )
        self.operation_status.setText(status)
        self.operation_status.setObjectName("Danger")
        self._repolish(self.operation_status)
        if automatic_preparation_failure:
            self._automatic_preparation_project_id = ""
            self._automatic_preparation_destination = ""
            self.command_tabs.setCurrentIndex(0)
            target = (
                self.extract_button
                if self.current_project is not None
                and self.store.working_copy(self.current_project.project_id) is not None
                else self.working_button
            )
            target.setFocus(Qt.FocusReason.OtherFocusReason)
            self._show_dashboard_handoff(
                f"{automatic_destination} → Preparation stopped safely",
                f"ROMVERSE recorded a bounded {operation.replace('-', ' ')} failure: {message}. "
                "Verified prior progress remains preserved. Review the focused Source Lab action, "
                f"then choose {automatic_destination} to reassess; no automatic retry or phone "
                "action occurred.",
                "ATTENTION",
                ready=False,
            )
        if automatic_simulation_failure:
            self._automatic_simulation_project_id = ""
            self.command_tabs.setCurrentIndex(1)
            self.plan_button.setFocus(Qt.FocusReason.OtherFocusReason)
            self._show_dashboard_handoff(
                "Pre-Build Simulation → Dry run stopped safely",
                f"ROMVERSE recorded a bounded dry-run failure: {message}. Prepared inputs and "
                "prior evidence remain preserved. Review Build & Proof, then intentionally "
                "request Simulation again if appropriate; no automatic retry, build, or phone "
                "action occurred.",
                "ATTENTION",
                ready=False,
            )
        if automatic_simulation_verification_failure:
            self._automatic_simulation_verification_plan = None
            self._automatic_simulation_verification_saved = False
            self.command_tabs.setCurrentIndex(1)
            self.verify_plan_button.setFocus(Qt.FocusReason.OtherFocusReason)
            self._show_dashboard_handoff(
                "Pre-Build Simulation → Current tree needs attention",
                f"The existing verifier stopped: {message}. ROMVERSE preserved the exact plan "
                "and current tree and did not retry or infer success. Review Build & Proof before "
                "requesting another Simulation; no build or phone action occurred.",
                "ATTENTION",
                ready=False,
            )
        if intentional_forge_failure:
            self._intentional_forge_plan = None
            self.command_tabs.setCurrentIndex(1)
            self.forge_button.setFocus(Qt.FocusReason.OtherFocusReason)
            self._show_dashboard_handoff(
                "Forge Bundle → Creation stopped safely",
                f"The existing Forge producer stopped: {message}. ROMVERSE preserved current "
                "plan/tree evidence and did not retry, infer an artifact, build, sign, or change "
                "a phone. Review Build & Proof before intentionally choosing Forge Bundle again.",
                "ATTENTION",
                ready=False,
            )
        if automatic_forge_verification_failure:
            self._automatic_forge_verification = None
            self.command_tabs.setCurrentIndex(1)
            self.verify_forge_button.setFocus(Qt.FocusReason.OtherFocusReason)
            self._show_dashboard_handoff(
                "Forge Bundle → Verification needs attention",
                f"The existing read-only verifier stopped: {message}. ROMVERSE preserved the "
                "available receipt and artifact evidence and did not retry, infer success, build, "
                "sign, or change a phone. Review Build & Proof before choosing another action.",
                "ATTENTION",
                ready=False,
            )
        self.operation_failed.emit(operation, message)

    def _render_inspection(self, report: RomInspectionReport | None) -> None:
        if report is None:
            self.inspection_detail.setText(
                "Not inspected. ROMVERSE will verify SHA-256 before reading container metadata."
            )
            return
        severity_counts: dict[str, int] = {}
        for finding in report.findings:
            severity_counts[finding.severity.value] = (
                severity_counts.get(finding.severity.value, 0) + 1
            )
        warnings = severity_counts.get("warning", 0)
        critical = severity_counts.get("critical", 0)
        partitions = ", ".join(report.partition_signals) or "None detected"
        metadata = ", ".join(report.metadata_signals) or "None detected"
        self.inspection_detail.setText(
            f"Container  •  {report.container.value.replace('_', ' ')}  |  "
            f"Entries  •  {report.entry_count:,}  |  "
            f"Expanded metadata size  •  {human_bytes(report.uncompressed_bytes)}\n"
            f"Partition signals  •  {partitions}\n"
            f"Metadata signals  •  {metadata}\n"
            f"Structural findings  •  {critical} critical, {warnings} warning"
        )

    def _render_external_intake(self, receipt: ExternalFirmwareIntakeReceipt) -> None:
        partitions = ", ".join(receipt.partition_signals) or "None detected"
        metadata = ", ".join(receipt.metadata_signals) or "None detected"
        completeness = "complete" if receipt.inspection_complete else "bounded/incomplete"
        inventory = self.external_intake.load_inventory(receipt.project_id)
        declared = (
            ", ".join(f"{item.field}={item.value}" for item in inventory.identity_facts)
            if inventory is not None and inventory.identity_facts
            else "None confirmed"
        )
        inventory_members = (
            ", ".join(item.path for item in inventory.metadata_members)
            if inventory is not None and inventory.metadata_members
            else "None present"
        )
        procedures = (
            ", ".join(item.path for item in inventory.procedure_members)
            if inventory is not None and inventory.procedure_members
            else "None present"
        )
        self.inspection_detail.setText(
            "External read-only evidence  •  no copy or extraction\n"
            f"Container  •  {receipt.container.replace('_', ' ')}  |  "
            f"Entries  •  {receipt.entry_count:,}  |  "
            f"Expanded metadata size  •  {human_bytes(receipt.uncompressed_bytes)}\n"
            f"Partition signals  •  {partitions}\n"
            f"Metadata signals  •  {metadata}\n"
            f"Structural findings  •  {receipt.critical_count} critical, "
            f"{receipt.warning_count} warning, {receipt.information_count} information  •  "
            f"inspection {completeness}\n"
            f"Bounded metadata members  •  {inventory_members}\n"
            f"Package-declared identity (UNVERIFIED)  •  {declared}\n"
            f"Untrusted procedure presence (NEVER EXECUTED)  •  {procedures}\n"
            "Known  •  File identity, size, SHA-256, container, and bounded structure above\n"
            "Unconfirmed  •  Package claims, device match, compatibility, and upgrade route\n"
            "Build/install/Guardian/flash authority  •  LOCKED"
        )

    def _render_time_machine(self, project_id: str) -> None:
        working = self.store.working_copy(project_id)
        snapshots = self.store.list_snapshots(project_id)
        if working is None:
            lines = [
                "No isolated baseline copy. Extracted trees and Forge outputs remain contained, "
                "but create a Time Machine baseline before applying changes."
            ]
        else:
            lines = [
                f"Working copy ready  •  {human_bytes(working.size_bytes)}  •  {working.current_sha256}"
            ]
            if not snapshots:
                lines.append("No snapshots yet. Create one before changing the local baseline.")
            else:
                lines.append(f"Snapshots  •  {len(snapshots)} (newest first)")
                for snapshot in snapshots[:5]:
                    state = (
                        "current evidence"
                        if snapshot.schema_version == 2
                        else "legacy • verify in Time Machine"
                    )
                    lines.append(
                        f"{snapshot.snapshot_id}  •  {human_bytes(snapshot.size_bytes)}  •  "
                        f"{state} (full verification runs before restore)"
                    )
                if len(snapshots) > 5:
                    lines.append(f"…and {len(snapshots) - 5} older snapshot(s)")
                lines.append(
                    "Verified local baseline restore is available in Time Machine; connected phones are never restore targets."
                )
        plan = RomBuildPlanner(self.store).load(project_id)
        if plan is not None:
            partitions = ", ".join(plan.partitions) or "none detected"
            mission_state = GuidedMissionStore(self.store.projects_root / project_id).load()
            tree_state = (
                "last background verification passed"
                if mission_state.build_plan_verified
                else "verification required"
            )
            lines.append(
                f"Build plan  •  Guardian {plan.guardian_status}/{plan.guardian_risk}  •  "
                f"Partitions: {partitions}\nTree SHA-256  •  {plan.tree_sha256}\n"
                f"Plan inputs  •  {tree_state}"
            )
        recipe = RecipeStore().load(self.store.projects_root / project_id)
        if recipe is not None:
            tree = self.store.working_root / project_id / "tree"
            preview = preview_recipe(recipe, tree) if tree.is_dir() else None
            preview_text = (
                f"  •  {len(preview.matched_targets)} matched, {len(preview.unresolved_targets)} unresolved"
                if preview is not None
                else ""
            )
            lines.append(
                f"Recipe  •  {recipe.name}  •  {len(recipe.steps)} step(s){preview_text}  •  Guardian approval required\n"
                f"Recipe SHA-256  •  {recipe.digest()}"
            )
        recipe_snapshots = RecipeExecutor.list_snapshots(
            self.store.snapshots_root / project_id / "recipes"
        )
        if recipe_snapshots:
            latest = recipe_snapshots[0]
            lines.append(
                f"Recipe rollback snapshots  •  {len(recipe_snapshots)}  •  latest {latest.snapshot_id} "
                f"({len(latest.targets)} target(s), verified)"
            )
        report = self.inspection.load_report(project_id)
        tree_ready = self.inspection.working_tree_exists(project_id)
        missing = tuple(
            label
            for passed, label in (
                (self.store.get(project_id).original is not None, "Protected original imported"),
                (report is not None, "Structure inspection saved"),
                (tree_ready, "Contained working tree extracted"),
                (plan is not None, "Guardian-assessed build plan saved"),
            )
            if not passed
        )
        ready = not missing
        lines.append(
            "Project readiness  •  LOCAL INPUTS READY (run Verify plan before execution)"
            if ready
            else "Project readiness  •  INCOMPLETE  •  " + "; ".join(missing)
        )
        try:
            dna = derive_dna(self.store, project_id)
        except ProjectError:
            dna = None
        if dna is not None:
            dna_store = DnaStore()
            dna_store.save(self.store, dna)
            state = "verified" if dna_store.verify(self.store, project_id) else "stale"
            lines.append(f"ROM DNA  •  {dna.fingerprint}  •  {state}")
        recipe = RecipeStore().load(self.store.projects_root / project_id)
        receipt = (
            load_run_receipt(
                self.store.projects_root / project_id,
                recipe=recipe,
                tree_root=self.store.working_root / project_id / "tree",
                snapshot_root=self.store.snapshots_root / project_id / "recipes",
            )
            if recipe is not None
            else None
        )
        if receipt is not None:
            lines.append(
                f"Last recipe run  •  {len(receipt.steps)} step(s)  •  "
                f"snapshot {receipt.snapshot_id or 'none'}  •  verified"
            )
        forge_receipt = ForgeBundleService(self.store).load_receipt(project_id)
        if forge_receipt is not None:
            root_state = (
                f"Ascension rooted {forge_receipt.rooted_partition}  •  provenance {forge_receipt.ascension_handoff_digest[:16]}…"
                if forge_receipt.ascension_handoff_digest
                else "Root route  •  unrooted"
            )
            lines.append(
                f"Forge Bundle  •  {forge_receipt.file_count:,} files  •  "
                f"{human_bytes(forge_receipt.content_bytes)}  •  {forge_receipt.archive_sha256}\n"
                f"Output  •  {forge_receipt.output_path}\n"
                f"{root_state}\n"
                "Safety  •  unsigned, non-bootable, non-flashable"
            )
        self._append_tree_summary(lines, project_id)
        self.time_machine_detail.setText("\n".join(lines))

    def _append_tree_summary(self, lines: list[str], project_id: str) -> None:
        summary = self.inspection.cached_working_tree_summary(project_id)
        if summary is None:
            if self.inspection.working_tree_exists(project_id):
                lines.append(
                    "Extracted tree  •  Ready  •  detailed inventory refreshes during the next background build plan"
                )
            return
        notable = ", ".join(summary.notable_files) or "none"
        lines.append(
            f"Tree inventory snapshot  •  {summary.file_count:,} files  •  "
            f"{human_bytes(summary.total_bytes)}  •  refreshed during extraction/build planning"
        )
        lines.append(f"Key images  •  {notable}")

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)


def _display_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%d %b %Y • %H:%M")
    except ValueError:
        return "Unknown time"
