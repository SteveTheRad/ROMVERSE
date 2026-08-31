from __future__ import annotations

import json
import shutil
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

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

from romverse.core.settings import AppSettings
from romverse.device.dna import CapabilityState, DeviceDnaProfile, DeviceDnaService
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.attestations import DevicePackAttestationStore
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.approval import ApprovalStore
from romverse.guardian.artifact_binding import GuardianArtifactBindingService
from romverse.guardian.flash_handoff import GuardianFlashHandoffService
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.manifest_review import (
    GuardianManifestReview,
    GuardianManifestReviewService,
)
from romverse.infrastructure.process import SubprocessRunner
from romverse.infrastructure.tools import ToolStatus
from romverse.nexus.compatibility import CompatibilityMatrix, CompatibilityMatrixService
from romverse.rom.boot_observation import BootObservationService
from romverse.rom.builds import BuildPlan, RomBuildPlanner
from romverse.rom.dna import DnaStore, derive_dna
from romverse.rom.filesystems import FilesystemManifest, PartitionFilesystemService
from romverse.rom.forge import ForgeBundleReceipt, ForgeBundleService
from romverse.rom.guided import STAGES, GuidedMissionStore
from romverse.rom.inspection import RomInspectionReport, RomInspectionService
from romverse.rom.models import (
    ArtifactVerification,
    ProjectError,
    RomProject,
    TimeMachineSnapshot,
    WorkingCopy,
)
from romverse.rom.payloads import PayloadManifest, PayloadService
from romverse.rom.projects import RomProjectStore
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
        self.signals = ProjectWorkerSignals()

    @Slot()
    def execute(self) -> None:
        emit_progress = CoalescedProgress(self.signals.progress.emit)

        def progress(done: int, total: int) -> None:
            percent = measured_percent(done, total)
            if percent is not None:
                emit_progress(percent)

        try:
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
            elif self.operation == "verify":
                result = self.store.verify_original(self.project_id, progress=progress)
            elif self.operation == "inspect" and self.inspection is not None:
                result = self.inspection.inspect_project(self.project_id, progress=progress)
            elif self.operation == "working-copy":
                result = self.store.create_working_copy(self.project_id, progress=progress)
            elif self.operation == "snapshot":
                result = self.store.create_snapshot(self.project_id)
            elif self.operation == "extract" and self.inspection is not None:
                result = self.inspection.extract_project_tree(
                    self.project_id,
                    progress=progress,
                )
            elif self.operation == "plan" and self.inspection is not None:
                result = RomBuildPlanner(self.store).plan(self.project_id)
            elif self.operation == "verify-plan":
                result = RomBuildPlanner(self.store).verify_tree(self.project_id)
            elif self.operation == "forge-bundle":
                forge = ForgeBundleService(self.store)
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
            try:

                def publish_binding_progress(value: int) -> None:
                    if int(value) < 100:
                        emit_progress(value)

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
            emit_progress(100)
            self.signals.complete.emit(manifest)
        except (OSError, ProjectError) as exc:
            self.signals.failed.emit(str(exc))


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
            "Architect Mode exposes the complete advanced workspace. Guardian Core protection remains active in both modes."
        )
        detail.setObjectName("Muted")
        detail.setWordWrap(True)
        layout.addWidget(detail)
        layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        automatic = buttons.addButton("Genesis Sequence", QDialogButtonBox.ButtonRole.AcceptRole)
        expert = buttons.addButton("Architect Mode", QDialogButtonBox.ButtonRole.DestructiveRole)
        automatic.clicked.connect(lambda: self.done(1))
        expert.clicked.connect(lambda: self.done(2))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


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
    toolchain_requested = Signal()
    time_machine_requested = Signal()
    device_packs_requested = Signal()
    device_center_requested = Signal()
    knowledge_requested = Signal(str)
    ascension_status_changed = Signal()
    device_context_changed = Signal()
    device_scan_requested = Signal()
    device_scan_finished = Signal(bool, str)
    device_dna_updated = Signal(object)
    compatibility_matrix_updated = Signal(object)

    def __init__(
        self,
        store: RomProjectStore,
        pack_registry: DevicePackRegistry,
        tool_statuses: tuple[ToolStatus, ...] = (),
        attestation_store: DevicePackAttestationStore | None = None,
        gateway: ExecutionGateway | None = None,
        adb_executable: Path | None = None,
        app_settings: AppSettings | None = None,
    ) -> None:
        super().__init__()
        self.store = store
        self.inspection = RomInspectionService(store)
        self.device_dna = DeviceDnaService(store, pack_registry)
        self.compatibility = CompatibilityMatrixService(store)
        self.pack_registry = pack_registry
        self.attestation_store = attestation_store
        self.gateway = gateway
        self.adb_executable = adb_executable
        self.app_settings = app_settings or AppSettings()
        self.projects: tuple[RomProject, ...] = ()
        self.current_project: RomProject | None = None
        self.suggested_pack_id = ""
        self.devices: list[AndroidDevice] = []
        self.companion_snapshot = None
        self.device_scan_available = False
        self.tool_statuses: tuple[ToolStatus, ...] = ()
        self.payload_service: PayloadService | None = None
        self.filesystem_service: PartitionFilesystemService | None = None
        self._configure_tools(tool_statuses)
        self.worker: ManagedRunnable | None = None
        self._active_operation = ""

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
        self.delete_button = QPushButton("Delete project")
        self.delete_button.setToolTip(
            "Delete the selected project and derived working data after confirmation."
        )
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self._delete_project)
        header.addWidget(self.delete_button)
        self.guided_button = QPushButton("Genesis Sequence")
        self.guided_button.setToolTip(
            "Enter ROMVERSE Genesis Sequence: a guided journey from trusted firmware through build, Guardian flash, and verified first boot."
        )
        self.guided_button.clicked.connect(self._open_guided_setup)
        header.addWidget(self.guided_button)
        self.ascension_button = QPushButton("Ascension Protocol")
        self.ascension_button.setToolTip(
            "Identify a device-specific Magisk or KernelSU path, verify official tools, and prepare a Guardian-controlled root handoff."
        )
        self.ascension_button.clicked.connect(self._open_ascension_protocol)
        header.addWidget(self.ascension_button)
        self.expert_button = QPushButton("Architect Mode")
        self.expert_button.setToolTip(
            "Show the complete advanced ROM workspace; Guardian Core protections remain active."
        )
        self.expert_button.clicked.connect(self._enable_expert_mode)
        header.addWidget(self.expert_button)
        page.addLayout(header)

        boundary = QFrame()
        boundary.setObjectName("HeroCard")
        boundary_layout = QHBoxLayout(boundary)
        boundary_layout.setContentsMargins(20, 16, 20, 16)
        locked = QLabel("Original protection active")
        locked.setObjectName("Good")
        copy = QLabel(
            "Imports are copied into Original ROMs, hashed while streaming, marked read-only, and never extracted in place."
        )
        copy.setObjectName("Muted")
        copy.setWordWrap(True)
        boundary_layout.addWidget(locked)
        boundary_layout.addSpacing(14)
        boundary_layout.addWidget(copy, 1)
        page.addWidget(boundary)

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

        inspection_title = QLabel("Structure inspection")
        inspection_title.setObjectName("SectionTitle")
        detail_layout.addWidget(inspection_title)
        self.inspection_detail = QLabel(
            "Not inspected. ROMVERSE will verify SHA-256 before reading container metadata."
        )
        self.inspection_detail.setObjectName("Muted")
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
        self.forge_button.clicked.connect(lambda: self._start_worker("forge-bundle"))
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
        self.rollback_button.clicked.connect(self.time_machine_requested)
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
        action_buttons = (
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
        )
        hover_help = {
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
        detail_scroll = QScrollArea()
        detail_scroll.setObjectName("StudioDetailScroll")
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        detail_scroll.setWidget(detail)
        content.addWidget(detail_scroll, 1)
        page.addLayout(content, 1)

        footer = QLabel(
            "ROM Studio performs protected project work, inspection, exact partition extraction, metadata-preserving filesystem preparation, Recipes, deterministic Device Pack planning, and versioned local candidate builds with byte-for-byte super verification. Forge Bundles remain non-bootable intermediates; signing and every phone-changing action remain Guardian-locked."
        )
        footer.setObjectName("Muted")
        footer.setWordWrap(True)
        page.addWidget(footer)
        self.refresh()

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

    def _open_guided_setup(self) -> None:
        from romverse.ui.guided_mission import GuidedBuildMission

        GuidedBuildMission(self).exec()

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

    def _enable_expert_mode(self) -> None:
        self.operation_status.setText(
            "Architect Mode enabled. Guardian Core protections remain active."
        )
        self.operation_status.setObjectName("Good")
        self._repolish(self.operation_status)

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
    ) -> None:
        changed = self.gateway is not gateway or self.adb_executable != adb_executable
        self.gateway = gateway
        self.adb_executable = adb_executable
        if changed:
            self.device_context_changed.emit()

    def set_devices(self, devices: list[AndroidDevice]) -> None:
        changed = self.devices != devices
        self.devices = list(devices)
        self.suggested_pack_id = ""
        if devices:
            resolution = self.pack_registry.resolve(devices[0])
            if resolution.pack is not None:
                self.suggested_pack_id = resolution.pack.pack_id
        if self.current_project is not None and devices:
            # Boot evidence is optional and must never interfere with device discovery.
            with suppress(OSError, ProjectError):
                BootObservationService(self.store, self.pack_registry).observe(
                    self.current_project.project_id,
                    devices[0],
                )
        if changed:
            self.device_context_changed.emit()
            if self.current_project is not None and self.worker is None:
                self.refresh(self.current_project.project_id)

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
            self.partition_button.setEnabled(False)
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
            tree = self.inspection.summarize_working_tree(project.project_id)
            dna = self.device_dna.profiles.load(project.project_id)
            required_stage = (
                STAGES[1]
                if project.original is None
                else STAGES[2]
                if report is None
                else STAGES[3]
                if working is None or tree is None
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
                self.inspection.summarize_working_tree(project.project_id) is not None,
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
        source_identity = (
            identify_firmware_source(project.original.original_name).summary
            if project.original is not None
            else "Awaiting protected source"
        )
        self.project_meta.setText(
            f"Project ID  •  {project.project_id}\n"
            f"Device Pack  •  {project.device_pack_id or 'Not associated'}\n"
            f"Detected base  •  {source_identity}\n"
            f"Manifest  •  projects/{project.project_id}/{self.store.MANIFEST_NAME}\n\n"
            f"Guided validation\n{self._validation_summary(project)}"
        )
        self._render_device_dna(dna)
        if project.original is None:
            self.original_name.setText("No original imported")
            self.original_detail.setText(
                "Importing creates a separate protected workspace copy; the selected source file is not modified."
            )
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
            self.inspection_detail.setText(
                "Not inspected. Import an original to enable bounded metadata inspection."
            )
        else:
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
                self.worker is None
                and self.inspection.summarize_working_tree(project.project_id) is not None
            )
            self.verify_plan_button.setEnabled(
                self.worker is None
                and RomBuildPlanner(self.store).load(project.project_id) is not None
            )
            plan = RomBuildPlanner(self.store).load(project.project_id)
            forge_receipt = ForgeBundleService(self.store).load_receipt(project.project_id)
            self.forge_button.setEnabled(self.worker is None and plan is not None)
            self.verify_forge_button.setEnabled(self.worker is None and forge_receipt is not None)
            self.recipe_button.setEnabled(
                self.worker is None
                and RecipeStore().load(self.store.projects_root / project.project_id) is not None
                and self.inspection.summarize_working_tree(project.project_id) is not None
            )
            self.new_recipe_button.setEnabled(self.worker is None and project.original is not None)
            self.guided_recipe_button.setEnabled(
                self.worker is None
                and self.inspection.summarize_working_tree(project.project_id) is not None
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
            payload = self.store.working_root / project.project_id / "tree" / "payload.bin"
            self.partition_button.setEnabled(
                self.worker is None and payload.is_file() and self.payload_service is not None
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
        tree_ready = self.inspection.summarize_working_tree(project.project_id) is not None
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
        try:
            profile = self.device_dna.refresh(
                project.project_id,
                device,
                self.inspection.load_report(project.project_id),
            )
        except (OSError, ProjectError, TypeError, ValueError):
            profile = self.device_dna.profiles.load(project.project_id)
        if profile is not None:
            self.device_dna_updated.emit(profile)
            matrix: CompatibilityMatrix | None
            try:
                matrix = self.compatibility.assess(profile)
            except (OSError, ProjectError, TypeError, ValueError):
                matrix = self.compatibility.matrices.load(project.project_id)
            if matrix is not None:
                self.compatibility_matrix_updated.emit(matrix)
        return profile

    def _render_device_dna(self, profile: DeviceDnaProfile | None) -> None:
        if profile is None:
            self.device_dna_detail.setText(
                "Device DNA is unavailable. Import protected firmware; ROMVERSE will preserve "
                "unknown findings as unconfirmed rather than guess."
            )
            return
        facts = []
        for fact_id in (
            "identity.marketing_name",
            "identity.model",
            "identity.codename",
            "soc.platform",
            "software.build",
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
        self.device_dna_detail.setText(
            "Evidence-backed profile\n"
            + "\n".join(facts)
            + "\n\nCapability Map\n"
            + "\n".join(capabilities)
            + compatibility
            + warning
            + f"\n\nEvidence sources: {len(profile.evidence)}  •  "
            f"Profile digest: {profile.profile_digest[:16]}…  •  Bootloader relock: NEVER"
        )

    def _new_project(self) -> None:
        name, accepted = QInputDialog.getText(self, "New ROMVERSE project", "Project name")
        if not accepted:
            return
        try:
            project = self.store.create(name, self.suggested_pack_id)
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
        from romverse.ui.partition_workspace import PartitionWorkspace

        PartitionWorkspace(self).exec()

    def _open_build_control(self, parent: QWidget | None = None) -> None:
        if self.current_project is None:
            return
        from romverse.ui.build_control import BuildControlCenter

        dialog = BuildControlCenter(self, parent or self)
        dialog.exec()
        if dialog.guardian_manifest_requested:
            self._open_guardian_manifest_review(parent)

    def _open_guardian_manifest_review(self, parent: QWidget | None = None) -> None:
        if self.current_project is None or self.worker is not None:
            return
        from romverse.rom.readiness import BuildReadinessService

        device = next(
            (item for item in self.devices if item.state is DeviceState.DEVICE),
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
            "The source file will not be changed or extracted in place.",
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
    ) -> None:
        if self.current_project is None or self.worker is not None:
            return
        worker = ProjectWorker(
            self.store,
            operation,
            self.current_project.project_id,
            source,
            self.inspection,
            self.payload_service,
            self.filesystem_service,
            partitions,
        )
        self._launch_worker(worker, operation)

    def _launch_worker(self, worker: ManagedRunnable, operation: str) -> None:
        self.worker = worker
        self._active_operation = operation
        self.operation_started.emit(operation)
        self.new_button.setEnabled(False)
        self.project_list.setEnabled(False)
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
                "verify",
                "working-copy",
                "forge-bundle",
            }
        )
        self.operation_status.setText(
            "Copying the protected source with measured byte progress, then automatically detecting its structure without inventing an inspection percentage…"
            if operation == "import"
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
            else "Previewing recipe targets without mutation…"
            if operation == "preview-recipe"
            else "Verifying approval and creating rollback protection with an animated preflight, then reporting completed recipe steps; final tree and receipt verification remain below completion…"
            if operation == "execute-recipe"
            else "Verifying and restoring the selected recipe snapshot…"
            if operation == "rollback-recipe"
            else "Guardian is binding every declared image with measured byte progress, then compiling the full review without inventing a final-verification percentage… phone changed: NO"
            if operation == "guardian-review"
            else "Recomputing SHA-256…"
        )
        self.operation_status.setObjectName("Muted")
        self._repolish(self.operation_status)
        signals = worker.signals
        signals.progress.connect(self.progress.report)
        signals.progress.connect(
            lambda value, active=operation: self.operation_progress.emit(active, value)
        )
        signals.complete.connect(self._worker_complete)
        signals.failed.connect(self._worker_failed)
        start_background(worker)

    @Slot(object)
    def _worker_complete(self, result: object) -> None:
        operation = self._active_operation
        self._active_operation = ""
        project_id = self.current_project.project_id if self.current_project else ""
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
            bound = len(result.partition_writes)
            self.operation_status.setText(
                f"Guardian review sealed  •  {bound} image(s) hash-bound for review  •  "
                "commands: NONE  •  final consent: LOCKED  •  phone changed: NO"
            )
        successful = isinstance(
            result,
            (
                RomProject,
                FirmwareImportResult,
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
                BuildPlan,
                ForgeBundleReceipt,
                GuardianManifestReview,
            ),
        ) or (isinstance(result, ArtifactVerification) and result.valid)
        self.operation_status.setObjectName("Good" if successful else "Danger")
        self._repolish(self.operation_status)
        self.refresh(project_id)
        self.operation_completed.emit(operation, result)
        if isinstance(result, GuardianManifestReview):
            from romverse.ui.build_control import GuardianManifestReviewDialog

            GuardianManifestReviewDialog(result, self).exec()

    @Slot(str)
    def _worker_failed(self, message: str) -> None:
        operation = self._active_operation
        self._active_operation = ""
        self.worker = None
        self.new_button.setEnabled(True)
        self.project_list.setEnabled(True)
        self.progress.stop()
        self.operation_status.setText(message)
        self.operation_status.setObjectName("Danger")
        self._repolish(self.operation_status)
        if self.current_project is not None:
            self._select(self.project_list.currentRow())
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
        tree = self.inspection.summarize_working_tree(project_id)
        missing = tuple(
            label
            for passed, label in (
                (self.store.get(project_id).original is not None, "Protected original imported"),
                (report is not None, "Structure inspection saved"),
                (tree is not None, "Contained working tree extracted"),
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
        summary = self.inspection.summarize_working_tree(project_id)
        if summary is None:
            return
        notable = ", ".join(summary.notable_files) or "none"
        lines.append(
            f"Extracted tree  •  {summary.file_count:,} files  •  {human_bytes(summary.total_bytes)}"
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
