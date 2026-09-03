from __future__ import annotations

import hashlib
import json
from contextlib import suppress
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from romverse.ascension import (
    AscensionGuardianManifestService,
    AscensionMethod,
    AscensionRootPlanService,
    RootPatchPreparationService,
    RootRomBuildHandoffService,
    RootRomIntegrationService,
)
from romverse.backup.handoff import BackupHandoffService, CloudBackupProvider
from romverse.backup.media import (
    PhoneMediaBackupPlan,
    PhoneMediaBackupReceipt,
    PhoneMediaBackupService,
)
from romverse.device.models import AndroidDevice, DeviceState
from romverse.guardian.approval import ApprovalStore
from romverse.guardian.execution_gateway_contract import (
    GatewayStepPhase,
    GuardianExecutionGatewayContract,
    execution_plan_matches_manifest,
    gateway_contract_matches_plan,
)
from romverse.guardian.execution_plan import GuardianExecutionPlan
from romverse.guardian.flash_handoff import (
    FlashMode,
    GuardianFlashHandoffService,
)
from romverse.guardian.live_target_receipt import (
    GuardianLiveTargetReceipt,
    GuardianLiveTargetReceiptService,
)
from romverse.guardian.manifest_review import (
    GuardianManifestReview,
    GuardianManifestReviewService,
    ManifestReviewState,
)
from romverse.guardian.models import GuardianDeniedError
from romverse.infrastructure.process import SubprocessRunner
from romverse.intelligence.action_evidence import (
    ToolchainVerificationStore,
    TypedLocalActionEvidence,
)
from romverse.intelligence.online_remediation import (
    ErrorFingerprint,
    OnlineFixReceipt,
    OnlineRemediationService,
)
from romverse.intelligence.synapse import (
    SynapseContribution,
    SynapseScope,
    SynapseStore,
    SynapseStoreError,
)
from romverse.nexus.events import (
    LiveConsoleEventStore,
    LiveConsoleStoreError,
    MissionConfidence,
    MissionState,
)
from romverse.rom.avb_evidence import AvbEvidenceService, AvbTopologyReceipt
from romverse.rom.boot_observation import BootObservationService
from romverse.rom.build_execution import LocalBuildReceipt, LocalDeviceBuildExecutor
from romverse.rom.build_inputs import BuildInputPreparation, BuildInputPreparationService
from romverse.rom.forge_autopilot import ResolutionKind, resolution_plan
from romverse.rom.guided import GuidedMissionStore
from romverse.rom.models import ProjectError
from romverse.rom.readiness import (
    BuildGate,
    BuildReadinessReport,
    BuildReadinessService,
    GateStatus,
    remediation_for,
)
from romverse.rom.rebuild_metadata import RebuildMetadataService
from romverse.rom.recovery_evidence import RecoveryEvidenceService
from romverse.rom.signing_ceremony import (
    OfflineSigningCeremonyService,
    OfflineSigningReceipt,
    OfflineSigningRequest,
)
from romverse.rom.source_blueprint import FastbootSourceBlueprint
from romverse.rom.source_intelligence import (
    FirmwareSourceIntelligenceService,
    OtaPayloadBlueprint,
    PartitionBundleBlueprint,
)
from romverse.ui.background import CoalescedProgress, ManagedRunnable, start_background
from romverse.ui.backup_center import RecoveryEvidenceWorker
from romverse.ui.guided_mission import GuidedBuildMission
from romverse.ui.phone_backup import PhoneMediaBackupDialog, PhoneMediaBackupWorker
from romverse.ui.process_progress import ProcessProgressBar


class LiveTargetCheckSignals(QObject):
    complete = Signal(object)
    failed = Signal(str)


class LiveTargetCheckWorker(ManagedRunnable):
    """Run the bounded read-only re-identification sequence off the UI thread."""

    def __init__(
        self,
        service: GuardianLiveTargetReceiptService,
        gateway: GuardianExecutionGatewayContract,
        reviewed_device: AndroidDevice,
    ) -> None:
        super().__init__()
        self.service = service
        self.gateway = gateway
        self.reviewed_device = reviewed_device
        self.signals = LiveTargetCheckSignals()

    @Slot()
    def execute(self) -> None:
        try:
            receipt = self.service.observe(self.gateway, self.reviewed_device)
            with suppress(RuntimeError):
                self.signals.complete.emit(receipt)
        except (OSError, ProjectError, TypeError, ValueError) as exc:
            with suppress(RuntimeError):
                self.signals.failed.emit(str(exc))


class RebuildMetadataSignals(QObject):
    complete = Signal(object)
    failed = Signal(str)


class SourceBlueprintSignals(QObject):
    complete = Signal(object)
    failed = Signal(str)
    progress = Signal(int)


class OnlineRemediationSignals(QObject):
    complete = Signal(object)
    failed = Signal(str)


class OnlineRemediationWorker(ManagedRunnable):
    def __init__(
        self,
        service: OnlineRemediationService,
        fingerprint: ErrorFingerprint,
    ) -> None:
        super().__init__()
        self.service = service
        self.fingerprint = fingerprint
        self.signals = OnlineRemediationSignals()

    @Slot()
    def execute(self) -> None:
        try:
            self.signals.complete.emit(self.service.lookup(self.fingerprint))
        except (OSError, ValueError, TypeError) as exc:
            self.signals.failed.emit(str(exc))


class PhoneBackupGuideDialog(QDialog):
    """Guide the user to a real phone/provider backup before evidence capture."""

    _GUIDANCE = {
        CloudBackupProvider.GOOGLE: (
            "On the phone, open Settings → Google → Backup (or Google One → Device backup). "
            "Review the account and included data, choose Back up now, and wait until the phone "
            "shows a successful completion time."
        ),
        CloudBackupProvider.XIAOMI: (
            "On the phone, open Settings → Xiaomi Account → Xiaomi Cloud. Review Photos, "
            "Contacts, Messages, Notes, and device backup, then choose Sync/Back up now and wait "
            "for the latest-backup status to update."
        ),
        CloudBackupProvider.OEM: (
            "Open the manufacturer's backup or cloud section in phone Settings. Confirm the "
            "restore account, review every included data category, start the backup, and wait for "
            "a successful completion time."
        ),
        CloudBackupProvider.OTHER: (
            "Open the trusted backup provider on the phone. Confirm the restore account and "
            "recovery method, review its included data, start the backup, and wait for a clear "
            "successful completion status."
        ),
    }

    def __init__(self, device_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Guardian handoff • create phone backup")
        self.setMinimumWidth(690)
        layout = QVBoxLayout(self)
        title = QLabel(f"Back up {device_name} before Guardian review")
        title.setObjectName("GateTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        intro = QLabel(
            "Choose the provider available on your phone. ROMVERSE guides this step but never "
            "asks for cloud credentials and cannot inspect private cloud contents."
        )
        intro.setObjectName("GateCopy")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.provider = QComboBox()
        for provider in CloudBackupProvider:
            self.provider.addItem(provider.value, provider)
        layout.addWidget(self.provider)
        self.steps = QLabel()
        self.steps.setObjectName("Card")
        self.steps.setWordWrap(True)
        self.steps.setMinimumHeight(125)
        layout.addWidget(self.steps)
        limits = QLabel(
            "Before continuing, separately review authenticator recovery, eSIMs, local-only app "
            "data, secure folders, downloads, and anything the provider excludes. A cloud backup "
            "is not claimed as an independently readable PC archive."
        )
        limits.setObjectName("Warning")
        limits.setWordWrap(True)
        layout.addWidget(limits)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.finished_button = buttons.addButton(
            "Continue after backup completes",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        self.finished_button.setObjectName("MissionNext")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.provider.currentIndexChanged.connect(self._update_steps)
        self._update_steps()

    def _update_steps(self, _index: int = -1) -> None:
        provider = self.provider.currentData()
        guidance = self._GUIDANCE.get(provider, self._GUIDANCE[CloudBackupProvider.OTHER])
        self.steps.setText(
            "1  Keep the phone powered and connected to a trusted network.\n\n"
            f"2  {guidance}\n\n"
            "3  Return here only after the provider shows that the backup completed."
        )

    def selected_provider(self) -> CloudBackupProvider | None:
        if self.exec() != QDialog.DialogCode.Accepted:
            return None
        try:
            return CloudBackupProvider(str(self.provider.currentData()))
        except ValueError:
            return None


class CloudBackupConfirmationDialog(QDialog):
    """Explicit cloud evidence prompt; it never implies ROMVERSE read cloud data."""

    def __init__(
        self,
        device_name: str,
        parent: QWidget | None = None,
        selected_provider: CloudBackupProvider | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Guardian handoff • confirm cloud backup")
        self.setMinimumWidth(650)
        layout = QVBoxLayout(self)
        intro = QLabel(
            f"Confirm the backup status shown for {device_name}. ROMVERSE records your confirmation locally and never requests cloud credentials or uploads data."
        )
        intro.setWordWrap(True)
        intro.setObjectName("GateCopy")
        layout.addWidget(intro)
        form = QFormLayout()
        self.provider = QComboBox()
        for provider in CloudBackupProvider:
            self.provider.addItem(provider.value, provider)
        if selected_provider is not None:
            selected_index = self.provider.findData(selected_provider)
            if selected_index >= 0:
                self.provider.setCurrentIndex(selected_index)
        self.last_backup = QLineEdit()
        self.last_backup.setPlaceholderText("Example: Completed today at 3:42 PM")
        form.addRow("Backup provider", self.provider)
        form.addRow("Status/date shown", self.last_backup)
        layout.addLayout(form)
        self.checks = (
            QCheckBox("The phone/provider reports that the backup completed successfully."),
            QCheckBox("I can access the restore account and its recovery method."),
            QCheckBox(
                "I reviewed photos, contacts, messages, authenticator recovery, and important app data."
            ),
            QCheckBox(
                "I understand ROMVERSE cannot inspect cloud contents and this is user-confirmed evidence."
            ),
        )
        for check in self.checks:
            check.toggled.connect(self._update_ready)
            layout.addWidget(check)
        warning = QLabel(
            "This receipt enables private Guardian review only. It is not an independent cloud-restore test or public release certification."
        )
        warning.setWordWrap(True)
        warning.setObjectName("MissionMuted")
        layout.addWidget(warning)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self.confirm_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.confirm_button.setText("Record verified confirmation")
        self.confirm_button.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.last_backup.textChanged.connect(self._update_ready)
        layout.addWidget(buttons)

    def _update_ready(self, _value: object = None) -> None:
        self.confirm_button.setEnabled(
            bool(self.last_backup.text().strip())
            and all(check.isChecked() for check in self.checks)
        )

    def values(self) -> tuple[CloudBackupProvider, str] | None:
        if self.exec() != QDialog.DialogCode.Accepted:
            return None
        try:
            provider = CloudBackupProvider(str(self.provider.currentData()))
        except ValueError:
            return None
        return provider, self.last_backup.text().strip()


class GuardianFlashModeDialog(QDialog):
    """Present the only two supported data-handling choices for final review."""

    def __init__(self, device_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ROMVERSE Guardian • choose flash mode")
        self.setMinimumWidth(760)
        layout = QVBoxLayout(self)
        title = QLabel("ROMVERSE FORGE COMPLETE • YOUR PROJECT IS READY")
        title.setObjectName("ReadyHeading")
        layout.addWidget(title)
        copy = QLabel(
            f"Every automatic prerequisite for {device_name} is green. Choose how Guardian "
            "should prepare the final, exact-device manifest. This choice does not start a "
            "device write; ROMVERSE will still show the complete manifest and require final consent."
        )
        copy.setObjectName("GateCopy")
        copy.setWordWrap(True)
        layout.addWidget(copy)

        required = QLabel(
            "ONE CHOICE IS REQUIRED  •  ROMVERSE WILL NOT GUESS HOW YOUR USER DATA SHOULD BE HANDLED"
        )
        required.setObjectName("CardHeading")
        required.setWordWrap(True)
        layout.addWidget(required)

        self.dirty = QRadioButton("Dirty flash • keep user data")
        dirty_card = self._choice_card(
            self.dirty,
            "Choose only when you know the source, current firmware base, encryption, and data "
            "layout are compatible. ROMVERSE preserves userdata but cannot promise every app will remain compatible.",
            "FlashChoiceKeep",
        )
        layout.addWidget(dirty_card)

        self.clean = QRadioButton("Clean flash • wipe user data")
        clean_card = self._choice_card(
            self.clean,
            "Erases user data after a separate final approval. Use when changing an incompatible "
            "firmware base or when Guardian recommends a clean installation.",
            "FlashChoiceWipe",
        )
        layout.addWidget(clean_card)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.dirty)
        self.mode_group.addButton(self.clean)

        invariant = QLabel(
            "PERMANENT GUARDIAN RULE  •  ROMVERSE NEVER RELOCKS THE BOOTLOADER. "
            "No relock option or relock command can be generated."
        )
        invariant.setObjectName("BootloaderInvariant")
        invariant.setWordWrap(True)
        layout.addWidget(invariant)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self.review_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.review_button.setText("Prepare exact Guardian review")
        self.review_button.setObjectName("MissionNext")
        self.review_button.setEnabled(False)
        self.mode_group.buttonToggled.connect(self._update_ready)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_ready(self, _button: object = None, _checked: bool = False) -> None:
        self.review_button.setEnabled(self.mode_group.checkedButton() is not None)

    @staticmethod
    def _choice_card(radio: QRadioButton, detail: str, object_name: str) -> QFrame:
        card = QFrame()
        card.setObjectName(object_name)
        row = QVBoxLayout(card)
        row.setContentsMargins(18, 15, 18, 15)
        radio.setObjectName("FlashMode")
        row.addWidget(radio)
        explanation = QLabel(detail)
        explanation.setObjectName("GateCopy")
        explanation.setWordWrap(True)
        row.addWidget(explanation)
        return card

    def value(self) -> FlashMode | None:
        if self.exec() != QDialog.DialogCode.Accepted or self.mode_group.checkedButton() is None:
            return None
        return FlashMode.CLEAN_WIPE_DATA if self.clean.isChecked() else FlashMode.DIRTY_KEEP_DATA


class GuardianManifestReviewDialog(QDialog):
    """Show the genuine post-handoff state without inventing a write contract."""

    def __init__(
        self,
        manifest: GuardianManifestReview,
        parent: QWidget | None = None,
        *,
        execution_plan: GuardianExecutionPlan | None = None,
        gateway_contract: GuardianExecutionGatewayContract | None = None,
        live_target_service: GuardianLiveTargetReceiptService | None = None,
        reviewed_device: AndroidDevice | None = None,
    ) -> None:
        super().__init__(parent)
        self.execution_plan = (
            execution_plan if execution_plan_matches_manifest(execution_plan, manifest) else None
        )
        self.gateway_contract = (
            gateway_contract
            if gateway_contract_matches_plan(gateway_contract, self.execution_plan)
            else None
        )
        self.live_target_service = live_target_service
        self.reviewed_device = reviewed_device
        self.live_target_receipt: GuardianLiveTargetReceipt | None = None
        self.live_target_worker: LiveTargetCheckWorker | None = None
        self.open_guardian_core_requested = False
        self.setWindowTitle("ROMVERSE Guardian • exact manifest review")
        self.setMinimumSize(820, 640)
        self.resize(920, 760)
        # This dialog is opened directly from ROM Studio rather than from Forge
        # Control, so it must carry the same dark evidence-card styling itself.
        # Otherwise some desktop themes give the scroll viewport a light base
        # while the inherited label text remains light and unreadable.
        self.setStyleSheet(GuidedBuildMission._stylesheet() + BuildControlCenter._stylesheet())
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        title = QLabel("GUARDIAN MANIFEST REVIEW • EXECUTION LOCKED")
        title.setObjectName("ReadyHeading")
        root.addWidget(title)
        if self.gateway_contract is not None:
            review_detail = (
                f"ROMVERSE rehashed {len(manifest.partition_writes)} exact current image(s), "
                "compiled the inert command plan, and sealed every required readback and first-boot "
                "result check. The runtime and final consent remain unavailable, so nothing can be "
                "written to the phone."
            )
        elif self.execution_plan is not None:
            review_detail = (
                f"ROMVERSE rehashed {len(manifest.partition_writes)} exact current image(s) and "
                "compiled a private inert command preview. The remaining plan blockers below keep "
                "the runtime and final consent unavailable, so nothing can be written to the phone."
            )
        elif manifest.partition_writes:
            review_detail = (
                f"ROMVERSE rehashed {len(manifest.partition_writes)} exact current image(s) and "
                "bound them to this handoff for review. The inert execution plan is not available "
                "in this view, so nothing can be written to the phone."
            )
        elif manifest.review_status == "blocked-missing-current-artifact-binding":
            review_detail = (
                "ROMVERSE found the signed exact-build write contract, but could not bind every "
                "declared image to the current verified build/signing receipts. The evidence card "
                "below explains exactly what must be regenerated or verified."
            )
        else:
            review_detail = (
                "ROMVERSE has not found a signed exact-build partition-write contract, so no "
                "final consent or device command is available."
            )
        intro = QLabel(
            f"{manifest.device_name} • {manifest.mode.display_name}\n"
            "ROMVERSE verified the current project, phone, backup/recovery gates, and your "
            f"data choice. {review_detail}"
        )
        intro.setObjectName("GateCopy")
        intro.setWordWrap(True)
        root.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 8, 0)
        body_layout.setSpacing(10)

        identity = QFrame()
        identity.setObjectName("BuildPhase")
        identity_layout = QVBoxLayout(identity)
        identity_layout.setContentsMargins(18, 15, 18, 15)
        identity_title = QLabel("EXACT REVIEW BINDING")
        identity_title.setObjectName("CardHeading")
        identity_copy = QLabel(
            f"Device • {manifest.device_name} • {manifest.model} • {manifest.codename}\n"
            f"Device Pack • {manifest.device_pack_id} • {manifest.device_pack_version}\n"
            f"Protected source • {manifest.source_sha256[:20]}…\n"
            f"Readiness evidence • {manifest.readiness_evidence_digest[:20]}…"
        )
        identity_copy.setObjectName("GateCopy")
        identity_copy.setWordWrap(True)
        identity_layout.addWidget(identity_title)
        identity_layout.addWidget(identity_copy)
        body_layout.addWidget(identity)

        for check in manifest.checks:
            row = QFrame()
            row.setProperty("gateStatus", check.state.value)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(14, 11, 14, 11)
            symbol = QLabel("✓" if check.state is ManifestReviewState.PASS else "×")
            symbol.setObjectName("GateSymbol")
            symbol.setFixedWidth(28)
            copy = QLabel(f"{check.label}\n{check.evidence}\nNext: {check.recommendation}")
            copy.setObjectName("GateCopy")
            copy.setWordWrap(True)
            badge = QLabel(check.state.value.upper())
            badge.setObjectName("GateBadge")
            row_layout.addWidget(symbol)
            row_layout.addWidget(copy, 1)
            row_layout.addWidget(badge)
            body_layout.addWidget(row)

        writes = QFrame()
        writes.setProperty("gateStatus", "attention" if manifest.partition_writes else "blocked")
        writes_layout = QVBoxLayout(writes)
        writes_layout.setContentsMargins(18, 15, 18, 15)
        writes_title = QLabel(
            f"PARTITION WRITES • {len(manifest.partition_writes)} HASH-BOUND FOR REVIEW • NONE AUTHORIZED"
            if manifest.partition_writes
            else "PARTITION WRITES • NONE AUTHORIZED"
        )
        writes_title.setObjectName("CardHeading")
        writes_copy = QLabel(
            "These hashes are evidence, not commands. ROMVERSE still requires an independently "
            "verified command manifest, live preconditions, recovery actions, post-write checks, "
            "and separate final consent before any device write can exist."
            if manifest.partition_writes
            else "ROMVERSE will not infer a super, vbmeta, boot, slot, wipe, or reboot sequence from "
            "filenames, previous devices, or a successful local build. The missing exact contract "
            "must name every artifact, digest, partition, slot rule, order, precondition, rollback, "
            "and verification step before final consent can exist."
        )
        writes_copy.setObjectName("GateCopy")
        writes_copy.setWordWrap(True)
        writes_layout.addWidget(writes_title)
        writes_layout.addWidget(writes_copy)
        for item in manifest.partition_writes:
            slot = item.target_slot.upper() if item.target_slot != "none" else "NO SLOT SUFFIX"
            row = QLabel(
                f"{item.order:02d}  •  {item.partition}  ←  {item.artifact_name}\n"
                f"SHA-256 {item.artifact_sha256[:24]}…  •  {item.transport.value.upper()}  •  "
                f"{slot}  •  VERIFY AFTER WRITE: REQUIRED"
            )
            row.setObjectName("GateCopy")
            row.setWordWrap(True)
            row.setToolTip(
                f"Review-only artifact binding\n\nContained evidence: {item.artifact_relative_path}\n"
                f"Full SHA-256: {item.artifact_sha256}\nEvidence: {item.evidence_kind}\n\n"
                "No command or device authority is attached to this row."
            )
            writes_layout.addWidget(row)
        body_layout.addWidget(writes)

        plan = self.execution_plan
        plan_card = QFrame()
        plan_card.setObjectName("BuildPhase")
        plan_card.setProperty("gateStatus", "attention" if plan is not None else "blocked")
        plan_layout = QVBoxLayout(plan_card)
        plan_layout.setContentsMargins(18, 15, 18, 15)
        plan_layout.setSpacing(7)
        if plan is None:
            plan_title = QLabel("INERT EXECUTION PLAN • NOT AVAILABLE")
            plan_copy = QLabel(
                "The command-free manifest remains useful evidence, but this view has no current "
                "independently sealed command preview. Return to Forge Control to regenerate the "
                "exact Guardian review. Execution and final consent remain locked."
            )
        else:
            preconditions = sum(command.phase.value == "precondition" for command in plan.commands)
            writes_count = sum(command.phase.value == "write" for command in plan.commands)
            plan_title = QLabel(
                f"INERT EXECUTION PLAN • {preconditions} PREFLIGHT • {writes_count} WRITE PREVIEW"
            )
            plan_copy = QLabel(
                f"Plan {plan.plan_digest[:20]}… • {plan.plan_status.replace('-', ' ')}\n"
                "Every target and workspace path is redacted. These are review templates, not "
                "runnable commands; execution authority is NONE and final consent is LOCKED."
            )
            for command in plan.commands:
                if command.phase.value != "precondition":
                    continue
                row = QLabel(f"{command.order:02d}  •  CHECK  •  {command.expected_result}")
                row.setObjectName("GateCopy")
                row.setWordWrap(True)
                plan_layout.addWidget(row)
            blockers = QLabel(
                "REMAINING PLAN BLOCKERS\n" + "\n".join(f"• {item}" for item in plan.blockers)
            )
            blockers.setObjectName("GateCopy")
            blockers.setWordWrap(True)
            plan_layout.addWidget(blockers)
        plan_title.setObjectName("CardHeading")
        plan_copy.setObjectName("GateCopy")
        plan_copy.setWordWrap(True)
        plan_layout.insertWidget(0, plan_title)
        plan_layout.insertWidget(1, plan_copy)
        body_layout.addWidget(plan_card)

        contract = self.gateway_contract
        result_card = QFrame()
        result_card.setObjectName("BuildPhase")
        result_card.setProperty("gateStatus", "attention" if contract is not None else "blocked")
        result_layout = QVBoxLayout(result_card)
        result_layout.setContentsMargins(18, 15, 18, 15)
        result_layout.setSpacing(7)
        if contract is None:
            result_title = QLabel("VERIFICATION RESULT TEMPLATE • LOCKED")
            result_copy = QLabel(
                "Guardian has not sealed a current signed result template. Exact partition "
                "readbacks, post-boot Device DNA, and—where required—signed mode and recovery "
                "orchestration must be current. No command or phone action is available."
            )
        else:
            transition_summary = (
                f" • {contract.mode_transition_count} SIGNED TRANSITION"
                f"{'S' if contract.mode_transition_count != 1 else ''}"
                if contract.mode_transition_count
                else ""
            )
            result_title = QLabel(
                f"VERIFICATION RESULT TEMPLATE • {contract.readback_count} IMMEDIATE READBACK"
                f"{'S' if contract.readback_count != 1 else ''} • "
                f"{contract.post_boot_property_count} FIRST-BOOT CHECKS{transition_summary}"
            )
            result_copy = QLabel(
                f"Contract {contract.contract_digest[:20]}… • "
                f"{contract.contract_status.replace('-', ' ')}\n"
                "Each write must be read back immediately and match the signed full-partition "
                "size and SHA-256. Signed transitions below are exact review templates only; after "
                "a separately governed runtime, the same phone must match every Device DNA value. "
                f"Signed result verifier v{contract.result_receipt_schema_version} requires a "
                "separately trusted runtime signature plus independently verified live-target and "
                "consent receipts. Live-target check v1 is read-only, samples one exact Fastboot "
                "device three times around two matching identity rounds, and expires after two "
                "minutes; no receipt is captured by opening this review. No runtime trust is "
                "enrolled. This template did not run anything."
            )
            for step in contract.steps:
                if step.phase is GatewayStepPhase.TRANSITION:
                    slot = (
                        f" • SLOT {step.target_slot.upper()}" if step.target_slot != "none" else ""
                    )
                    row = QLabel(
                        f"{step.order:02d}  •  SIGNED TRANSITION  •  "
                        f"{step.transition_operation.value.replace('_', ' ').upper()}  •  "
                        f"{step.from_mode.value.upper()} → {step.to_mode.value.upper()}"
                        f"{slot}  •  WAIT UP TO {step.timeout_seconds}s"
                    )
                elif step.phase is GatewayStepPhase.READBACK:
                    slot = step.target_slot.upper() if step.target_slot != "none" else "NO SLOT"
                    row = QLabel(
                        f"{step.order:02d}  •  READ BACK {step.partition}  •  {slot}  •  "
                        f"{_human_bytes(step.expected_size_bytes)}  •  SHA-256 "
                        f"{step.expected_sha256[:20]}…"
                    )
                    row.setToolTip(
                        f"Full expected SHA-256: {step.expected_sha256}\n"
                        "Private output path remains redacted until a governed runtime exists."
                    )
                elif step.phase is GatewayStepPhase.POST_BOOT:
                    row = QLabel(
                        f"{step.order:02d}  •  FIRST BOOT  •  {step.property_name} = "
                        f"{step.expected_value}"
                    )
                else:
                    continue
                row.setObjectName("GateCopy")
                row.setWordWrap(True)
                result_layout.addWidget(row)
            if contract.recovery_steps:
                recovery_heading = QLabel(
                    f"SIGNED RECOVERY CONTINGENCY • {contract.recovery_strategy.replace('_', ' ').upper()}"
                )
                recovery_heading.setObjectName("CardHeading")
                recovery_heading.setWordWrap(True)
                result_layout.addWidget(recovery_heading)
                recovery_copy = QLabel(
                    f"Adapter • {contract.recovery_adapter_id}  •  Stock package SHA-256 "
                    f"{contract.recovery_stock_package_sha256[:20]}…\n"
                    "This is a review-only, adapter-scoped recovery sequence. It contains no raw "
                    "command and cannot run from this screen."
                )
                recovery_copy.setObjectName("GateCopy")
                recovery_copy.setWordWrap(True)
                result_layout.addWidget(recovery_copy)
                for step in contract.recovery_steps:
                    wipe = " • MAY WIPE USER DATA" if step.may_wipe_user_data else ""
                    slot = (
                        " • RECORDED PRE-WRITE SLOT"
                        if step.target_slot == "recorded_prewrite"
                        else ""
                    )
                    row = QLabel(
                        f"R{step.order:02d}  •  {step.operation.value.replace('_', ' ').upper()}  •  "
                        f"{step.from_mode.value.upper()} → {step.to_mode.value.upper()}"
                        f"{slot}{wipe}  •  WAIT UP TO {step.timeout_seconds}s"
                    )
                    row.setObjectName("GateCopy")
                    row.setWordWrap(True)
                    result_layout.addWidget(row)
                if contract.recovery_may_wipe_user_data:
                    wipe_warning = QLabel(
                        "RECOVERY WARNING • The signed stock-recovery contingency may erase user "
                        "data. Automatic wipe is forbidden; a future runtime must stop for a "
                        "separate explicit decision."
                    )
                    wipe_warning.setObjectName("Warning")
                    wipe_warning.setWordWrap(True)
                    result_layout.addWidget(wipe_warning)
            blockers = QLabel(
                "STILL REQUIRED\n" + "\n".join(f"• {item}" for item in contract.blockers)
            )
            blockers.setObjectName("GateCopy")
            blockers.setWordWrap(True)
            result_layout.addWidget(blockers)
        result_title.setObjectName("CardHeading")
        result_title.setWordWrap(True)
        result_copy.setObjectName("GateCopy")
        result_copy.setWordWrap(True)
        result_layout.insertWidget(0, result_title)
        result_layout.insertWidget(1, result_copy)
        body_layout.addWidget(result_card)

        self.live_target_card = QFrame()
        self.live_target_card.setObjectName("BuildPhase")
        live_target_available = bool(
            contract is not None
            and self.live_target_service is not None
            and isinstance(self.reviewed_device, AndroidDevice)
            and self.reviewed_device.build_id
            and self.reviewed_device.build_fingerprint
        )
        self.live_target_card.setProperty(
            "gateStatus", "attention" if live_target_available else "blocked"
        )
        live_target_layout = QVBoxLayout(self.live_target_card)
        live_target_layout.setContentsMargins(18, 15, 18, 15)
        live_target_layout.setSpacing(7)
        live_target_title = QLabel("LIVE TARGET CHECK v1 • READ-ONLY • TWO-MINUTE RECEIPT")
        live_target_title.setObjectName("CardHeading")
        live_target_title.setWordWrap(True)
        live_target_layout.addWidget(live_target_title)
        self.live_target_status = QLabel(
            "Not captured. Put the exact reviewed phone into the entry mode shown by this "
            "gateway, connect only that one phone by USB, then run the check. Guardian samples "
            "discovery three times around two matching product, unlock and mode checks. It "
            "does not flash, reboot, unlock, relock or grant consent."
            if live_target_available
            else "Unavailable in this review. A current exact gateway, complete earlier Android "
            "build identity, and verified ADB plus Fastboot tools are required. Opening this "
            "screen did not contact or change the phone."
        )
        self.live_target_status.setObjectName("GateCopy")
        self.live_target_status.setWordWrap(True)
        self.live_target_status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        live_target_layout.addWidget(self.live_target_status)
        self.live_target_button: QPushButton | None = None
        if live_target_available:
            self.live_target_button = QPushButton("Run read-only target check")
            self.live_target_button.setObjectName("MissionNext")
            self.live_target_button.setAccessibleName(
                "Run the read-only Guardian live target identity check"
            )
            self.live_target_button.setToolTip(
                "Uses only ADB/Fastboot discovery and allowlisted Fastboot identity reads. "
                "No device-changing command or final consent is available."
            )
            self.live_target_button.clicked.connect(self._start_live_target_check)
            live_target_layout.addWidget(self.live_target_button, 0, Qt.AlignmentFlag.AlignLeft)
        body_layout.addWidget(self.live_target_card)

        invariant = QLabel(
            "PERMANENT GUARDIAN RULE • BOOTLOADER RELOCK: NEVER • EXECUTION AUTHORITY: NONE • PHONE CHANGED: NO"
        )
        invariant.setObjectName("BootloaderInvariant")
        invariant.setWordWrap(True)
        body_layout.addWidget(invariant)
        body_layout.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        footer = QHBoxLayout()
        receipt = QLabel(f"Review receipt • {manifest.manifest_digest[:20]}…")
        receipt.setObjectName("MissionMuted")
        footer.addWidget(receipt, 1)
        return_button = QPushButton("Return to Genesis")
        return_button.clicked.connect(self.accept)
        footer.addWidget(return_button)
        self.guardian_core_button = QPushButton("Open Guardian Core")
        self.guardian_core_button.setObjectName("MissionNext")
        self.guardian_core_button.setToolTip(
            "Open this exact command-free manifest as persistent Guardian Core evidence. "
            "No approval, command, or phone action is created."
        )
        self.guardian_core_button.clicked.connect(self._open_guardian_core)
        footer.addWidget(self.guardian_core_button)
        root.addLayout(footer)

    def _open_guardian_core(self) -> None:
        self.open_guardian_core_requested = True
        self.accept()

    def _start_live_target_check(self) -> None:
        if (
            self.live_target_worker is not None
            or self.live_target_button is None
            or self.live_target_service is None
            or self.gateway_contract is None
            or not isinstance(self.reviewed_device, AndroidDevice)
        ):
            return
        self.live_target_receipt = None
        self.live_target_button.setEnabled(False)
        self.live_target_status.setObjectName("MissionMuted")
        self.live_target_status.setText(
            "Checking one exact Fastboot target with read-only discovery and identity probes… "
            "No flash, reboot, wipe, unlock, relock or consent action can run."
        )
        self._repolish_live_target_status()
        worker = LiveTargetCheckWorker(
            self.live_target_service,
            self.gateway_contract,
            self.reviewed_device,
        )
        self.live_target_worker = worker
        worker.signals.complete.connect(self._live_target_check_complete)
        worker.signals.failed.connect(self._live_target_check_failed)
        start_background(worker)

    @Slot(object)
    def _live_target_check_complete(self, result: object) -> None:
        self.live_target_worker = None
        if (
            not isinstance(result, GuardianLiveTargetReceipt)
            or self.gateway_contract is None
            or result.gateway_contract_digest != self.gateway_contract.contract_digest
            or not result.identity_verified
            or result.execution_authority != "none"
            or result.runtime_invoked
            or result.phone_changed
        ):
            self._live_target_check_failed(
                "The returned receipt did not match this exact Guardian gateway"
            )
            return
        self.live_target_receipt = result
        self.live_target_card.setProperty("gateStatus", "pass")
        self.live_target_status.setObjectName("Good")
        slot = (
            f" • recorded pre-write slot {result.recorded_prewrite_slot.upper()}"
            if result.recorded_prewrite_slot
            else ""
        )
        self.live_target_status.setText(
            f"PASSED • {result.observed_product} • {result.observed_entry_mode.upper()} • "
            f"bootloader unlocked{slot}\nReceipt {result.receipt_digest[:20]}… • valid until "
            f"{_display_time(result.expires_at)} • local observation only • cryptographic device "
            "attestation: no • final consent: locked • execution authority: none • phone changed: no"
        )
        self._repolish_live_target_status()
        if self.live_target_button is not None:
            self.live_target_button.setText("Run check again")
            self.live_target_button.setEnabled(True)

    @Slot(str)
    def _live_target_check_failed(self, message: str) -> None:
        self.live_target_worker = None
        self.live_target_receipt = None
        self.live_target_card.setProperty("gateStatus", "blocked")
        clean = " ".join(str(message).replace("\x00", " ").split())[:500]
        self.live_target_status.setObjectName("Danger")
        self.live_target_status.setText(
            f"CHECK STOPPED SAFELY • {clean or 'The exact target could not be verified.'}\n"
            "No receipt remains current. No flash, reboot, wipe, unlock, relock, consent or phone "
            "change was attempted. Confirm one exact phone is in the gateway entry mode, then retry."
        )
        self._repolish_live_target_status()
        if self.live_target_button is not None:
            self.live_target_button.setText("Retry read-only target check")
            self.live_target_button.setEnabled(True)

    def _repolish_live_target_status(self) -> None:
        style = self.live_target_status.style()
        style.unpolish(self.live_target_status)
        style.polish(self.live_target_status)
        card_style = self.live_target_card.style()
        card_style.unpolish(self.live_target_card)
        card_style.polish(self.live_target_card)


class SourceBlueprintWorker(ManagedRunnable):
    def __init__(self, service: FirmwareSourceIntelligenceService, project_id: str) -> None:
        super().__init__()
        self.service = service
        self.project_id = project_id
        self.signals = SourceBlueprintSignals()

    @Slot()
    def execute(self) -> None:
        emit_progress = CoalescedProgress(self.signals.progress.emit)

        try:
            self.signals.complete.emit(self.service.prepare(self.project_id, emit_progress))
        except (OSError, ProjectError) as exc:
            self.signals.failed.emit(str(exc))


class RebuildMetadataWorker(ManagedRunnable):
    def __init__(self, service: BuildInputPreparationService, project_id: str, contract) -> None:
        super().__init__()
        self.service = service
        self.project_id = project_id
        self.contract = contract
        self.signals = RebuildMetadataSignals()

    @Slot()
    def execute(self) -> None:
        try:
            self.signals.complete.emit(self.service.prepare(self.project_id, self.contract))
        except (OSError, ProjectError) as exc:
            self.signals.failed.emit(str(exc))


class LocalBuildWorker(ManagedRunnable):
    def __init__(self, executor: LocalDeviceBuildExecutor, project_id: str) -> None:
        super().__init__()
        self.executor = executor
        self.project_id = project_id
        self.signals = RebuildMetadataSignals()

    @Slot()
    def execute(self) -> None:
        try:
            self.signals.complete.emit(self.executor.execute(self.project_id))
        except (OSError, ProjectError) as exc:
            self.signals.failed.emit(str(exc))


class AvbEvidenceWorker(ManagedRunnable):
    def __init__(self, service: AvbEvidenceService, project_id: str) -> None:
        super().__init__()
        self.service = service
        self.project_id = project_id
        self.signals = RebuildMetadataSignals()

    @Slot()
    def execute(self) -> None:
        try:
            self.signals.complete.emit(self.service.inspect(self.project_id))
        except (OSError, ProjectError) as exc:
            self.signals.failed.emit(str(exc))


class OfflineSigningWorker(ManagedRunnable):
    def __init__(
        self,
        service: OfflineSigningCeremonyService,
        operation: str,
        project_id: str,
        folder: Path,
    ) -> None:
        super().__init__()
        self.service = service
        self.operation = operation
        self.project_id = project_id
        self.folder = folder
        self.signals = RebuildMetadataSignals()

    @Slot()
    def execute(self) -> None:
        try:
            if self.operation == "export":
                result = self.service.export_request(self.project_id, self.folder)
            else:
                result = self.service.import_signed_bundle(self.project_id, self.folder)
            self.signals.complete.emit(result)
        except (OSError, ProjectError) as exc:
            self.signals.failed.emit(str(exc))


class BuildControlCenter(QDialog):
    """A truthful control surface for local build, signing, recovery, and flash gates."""

    def __init__(
        self,
        studio,
        parent: QWidget | None = None,
        *,
        auto_start: bool = True,
    ) -> None:
        super().__init__(parent or studio)
        self.studio = studio
        self.project = studio.current_project
        if self.project is None:
            raise RuntimeError("Select a ROM project before opening Build Control")
        self.service = BuildReadinessService(
            studio.store,
            studio.pack_registry,
            studio.tool_statuses,
            studio.attestation_store,
        )
        self.report: BuildReadinessReport | None = None
        self.gate_rows: dict[str, QFrame] = {}
        self.resolve_buttons: dict[str, QPushButton] = {}
        self.metadata_worker: RebuildMetadataWorker | None = None
        self.blueprint_worker: SourceBlueprintWorker | None = None
        self.build_worker: LocalBuildWorker | None = None
        self.avb_worker: AvbEvidenceWorker | None = None
        self.signing_worker: OfflineSigningWorker | None = None
        self.recovery_worker: RecoveryEvidenceWorker | None = None
        self.media_backup_worker: PhoneMediaBackupWorker | None = None
        self.online_worker: OnlineRemediationWorker | None = None
        self.online_receipt: OnlineFixReceipt | None = None
        self.online_mission_id = ""
        self.preparation_missions: dict[str, str] = {}
        self.autopilot_active = False
        self.autopilot_completed: list[str] = []
        self.autopilot_waiting_for = ""
        self.guardian_manifest_requested = False
        self.evidence_watch = QTimer(self)
        self.evidence_watch.setInterval(1500)
        self.evidence_watch.timeout.connect(self._refresh_if_evidence_changed)
        self.setWindowTitle("ROMVERSE • Forge Control")
        self.setMinimumSize(1040, 700)
        self.resize(1240, 820)
        self.setStyleSheet(GuidedBuildMission._stylesheet() + self._stylesheet())
        self.studio.operation_completed.connect(self._autopilot_studio_complete)
        self.studio.operation_failed.connect(self._autopilot_studio_failed)
        self.studio.operation_progress.connect(self._autopilot_studio_progress)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._header())
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.host = QWidget()
        self.content = QVBoxLayout(self.host)
        self.content.setContentsMargins(28, 24, 28, 24)
        self.content.setSpacing(14)
        self.content.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        scroll.setWidget(self.host)
        root.addWidget(scroll, 1)
        root.addWidget(self._footer())
        self.refresh()
        if auto_start:
            QTimer.singleShot(0, self._start_autopilot)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        parent = self.parentWidget()
        if parent is not None:
            available = parent.window().geometry()
            self.resize(
                max(self.minimumWidth(), int(available.width() * 0.9)),
                max(self.minimumHeight(), int(available.height() * 0.9)),
            )
            frame = self.frameGeometry()
            frame.moveCenter(parent.window().frameGeometry().center())
            self.move(frame.topLeft())
        # Evidence may be completed by a nested Guardian/Ascension dialog while this
        # control surface is still alive. Reassess when it becomes visible so an old
        # amber card can never strand the user after its receipt has turned green.
        QTimer.singleShot(0, self._refresh_if_evidence_changed)
        self.evidence_watch.start()

    def hideEvent(self, event) -> None:
        self.evidence_watch.stop()
        super().hideEvent(event)

    def _has_active_worker(self) -> bool:
        return any(
            worker is not None
            for worker in (
                self.metadata_worker,
                self.blueprint_worker,
                self.build_worker,
                self.avb_worker,
                self.signing_worker,
                self.recovery_worker,
                self.media_backup_worker,
                self.online_worker,
            )
        )

    @staticmethod
    def _report_view_signature(report: BuildReadinessReport) -> tuple[object, ...]:
        """Return the semantic UI state, excluding volatile receipt timestamps/IDs."""

        return (
            tuple((gate.gate_id, gate.status.value, gate.evidence) for gate in report.gates),
            report.workspace_ready,
            report.build_ready,
            report.local_candidate_ready,
            report.signing_ready,
            report.flash_ready,
            report.blockers,
        )

    def _refresh_if_evidence_changed(self) -> None:
        if not self.isVisible() or self.autopilot_active or self._has_active_worker():
            return
        # A native file chooser, backup prompt, or nested Guardian dialog can return
        # focus to the parent window before Qt re-activates this modal surface.  The
        # evidence receipt is already durable at that point, so requiring OS focus
        # here would leave a visible amber card stale until the user clicked around.
        # Visibility plus the worker guards are sufficient; reassessment is read-only
        # and the semantic signature below prevents unnecessary repaints.
        # Tool installation may have completed in Forge Arsenal after this dialog was
        # created. Always assess with the studio's current verified tool snapshot.
        self.service.tool_statuses = self.studio.tool_statuses
        current = self.service.assess(
            self.project.project_id,
            tuple(self.studio.devices),
            persist=False,
        )
        if self.report is None or self._report_view_signature(
            current
        ) != self._report_view_signature(self.report):
            self.refresh(current)

    def _header(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("MissionHeader")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(28, 18, 28, 18)
        labels = QVBoxLayout()
        eyebrow = QLabel("ROM STUDIO  /  FORGE CONTROL")
        eyebrow.setObjectName("MissionEyebrow")
        title = QLabel("Know exactly what is ready—and what is not")
        title.setObjectName("MissionTitle")
        labels.addWidget(eyebrow)
        labels.addWidget(title)
        layout.addLayout(labels, 1)
        self.overall_badge = QLabel()
        self.overall_badge.setObjectName("GuardianBadge")
        layout.addWidget(self.overall_badge)
        return frame

    def _footer(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("MissionFooter")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(24, 10, 24, 12)
        layout.setSpacing(8)
        status_row = QHBoxLayout()
        self.status = QLabel(
            "Evidence checks are read-only. Local building runs only when explicitly requested and never invokes a phone transport."
        )
        self.status.setObjectName("MissionMuted")
        self.status.setWordWrap(True)
        status_row.addWidget(self.status, 1)
        self.process_progress = ProcessProgressBar()
        self.process_progress.setFixedWidth(180)
        status_row.addWidget(self.process_progress)
        layout.addLayout(status_row)
        refresh = QPushButton("Refresh evidence")
        refresh.clicked.connect(self.refresh)
        export = QPushButton("Export evidence bundle")
        export.clicked.connect(self._export_bundle)
        prepare = QPushButton("Prepare local build plan")
        prepare.setToolTip(
            "Verify the exact contract inputs and save a locked deterministic execution plan. This does not compile, sign, or touch a phone."
        )
        prepare.clicked.connect(self._prepare_build_plan)
        self.metadata_button = QPushButton("Prepare exact build inputs")
        self.metadata_button.setToolTip(
            "Extract only contract-required partitions, preserve filesystem metadata, and combine source-bound SELinux contexts locally. This never reads from or writes to the phone."
        )
        self.metadata_button.clicked.connect(self._prepare_rebuild_metadata)
        self.build_button = QPushButton("Build verified local candidate")
        self.build_button.setToolTip(
            "Execute the exact Device Pack plan in a new versioned output directory, then unpack and compare every logical partition. No phone command is available to this executor."
        )
        self.build_button.clicked.connect(self._execute_local_build)
        self.avb_button = QPushButton("Inspect AVB topology")
        self.avb_button.setToolTip(
            "Compare exact-source signing identity, rollback fields, and descriptor chains with the current local candidate. This never signs or touches a phone."
        )
        self.avb_button.clicked.connect(self._inspect_avb_topology)
        self.signing_button = QPushButton("Offline signing ceremony")
        self.signing_button.setToolTip(
            "Export exact unsigned artifacts for an external signer, or import and verify the signed results. ROMVERSE never stores or requests a private key and never touches a phone."
        )
        self.signing_button.clicked.connect(self._signing_ceremony)
        self.simulate_button = QPushButton("Run safe pipeline simulation")
        self.simulate_button.setObjectName("MissionNext")
        self.simulate_button.clicked.connect(self._simulate)
        self.autopilot_button = QPushButton("Auto-resolve && continue")
        self.autopilot_button.setObjectName("MissionNext")
        self.autopilot_button.setToolTip(
            "Resolve every safe local prerequisite in dependency order. ROMVERSE pauses only for authoritative input that software cannot create."
        )
        self.autopilot_button.clicked.connect(self._start_autopilot)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        build_actions = QHBoxLayout()
        build_actions.setSpacing(8)
        for button in (
            self.metadata_button,
            prepare,
            self.build_button,
            self.avb_button,
            self.signing_button,
        ):
            build_actions.addWidget(button, 1)
        layout.addLayout(build_actions)
        workflow_actions = QHBoxLayout()
        workflow_actions.setSpacing(8)
        workflow_actions.addWidget(refresh)
        workflow_actions.addWidget(export)
        workflow_actions.addStretch(1)
        workflow_actions.addWidget(self.autopilot_button)
        workflow_actions.addWidget(self.simulate_button)
        workflow_actions.addWidget(self.close_button)
        layout.addLayout(workflow_actions)
        return frame

    def reject(self) -> None:
        if any(
            worker is not None
            for worker in (
                self.metadata_worker,
                self.blueprint_worker,
                self.build_worker,
                self.avb_worker,
                self.signing_worker,
                self.recovery_worker,
                self.media_backup_worker,
            )
        ):
            self.status.setText(
                "Local preparation/build inspection is running; wait for its receipt."
            )
            return
        super().reject()

    def closeEvent(self, event) -> None:
        if any(
            worker is not None
            for worker in (
                self.metadata_worker,
                self.blueprint_worker,
                self.build_worker,
                self.avb_worker,
                self.signing_worker,
                self.recovery_worker,
                self.media_backup_worker,
            )
        ):
            event.ignore()
            self.status.setText(
                "Local preparation/build inspection is running; wait for its receipt."
            )
            return
        super().closeEvent(event)

    def refresh(self, report: BuildReadinessReport | None = None) -> None:
        self.service.tool_statuses = self.studio.tool_statuses
        self.report = report or self.service.assess(
            self.project.project_id,
            tuple(self.studio.devices),
        )
        while self.content.count():
            item = self.content.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self.gate_rows.clear()
        self.resolve_buttons.clear()
        unresolved = tuple(gate for gate in self.report.gates if gate.status is not GateStatus.PASS)
        if self.report.guardian_handoff_ready:
            banner = QFrame()
            banner.setObjectName("ReadyBanner")
            banner_layout = QHBoxLayout(banner)
            banner_layout.setContentsMargins(18, 14, 18, 14)
            copy = QVBoxLayout()
            heading = QLabel(
                "✓  FORGE COMPLETE  •  YOUR PROJECT IS READY"
                if self.report.flash_ready
                else "✓  YOUR PROJECT IS READY FOR GUARDIAN-CONTROLLED FLASH REVIEW"
            )
            heading.setObjectName("ReadyHeading")
            guidance = QLabel(
                "Every automatic build, signing, device-match, backup, and recovery gate is green. Choose whether Guardian should preserve or wipe user data, then review the exact device-bound manifest. Nothing has been flashed yet, and ROMVERSE will never relock the bootloader."
                if self.report.flash_ready
                else "ROMVERSE automatically resolved and verified the source, workspace, tools, build plan, local candidate, preserved OEM signature or applicable AVB evidence, exact phone identity, battery, boot state, Time Machine checkpoint, and pristine stock rollback images. Complete the guided backup prompt next; ROMVERSE will hash and verify the selected evidence automatically."
            )
            guidance.setObjectName("GateCopy")
            guidance.setWordWrap(True)
            copy.addWidget(heading)
            copy.addWidget(guidance)
            banner_layout.addLayout(copy, 1)
            review = QPushButton(
                "Choose flash mode"
                if self.report.flash_ready
                else "Complete final Guardian handoff"
            )
            review.setObjectName("MissionNext")
            review.setToolTip(
                "Choose keep-data or wipe-data preparation. ROMVERSE records the exact choice, then still requires manifest review and separate final consent before any device write. Bootloader relocking is permanently prohibited."
            )
            review.clicked.connect(lambda _checked=False: self._show_final_handoff(unresolved))
            banner_layout.addWidget(review)
            self.content.addWidget(banner)
        elif unresolved:
            priority = next(
                (gate for gate in unresolved if gate.status is GateStatus.BLOCKED),
                unresolved[0],
            )
            remediation = remediation_for(priority)
            banner = QFrame()
            banner.setObjectName("ResolutionBanner")
            banner_layout = QHBoxLayout(banner)
            banner_layout.setContentsMargins(18, 14, 18, 14)
            copy = QVBoxLayout()
            heading = QLabel("NEXT SAFE RESOLUTION")
            heading.setObjectName("CardHeading")
            guidance = QLabel(f"{priority.label}  •  {remediation.fixes[0]}")
            guidance.setObjectName("GateCopy")
            guidance.setWordWrap(True)
            copy.addWidget(heading)
            copy.addWidget(guidance)
            banner_layout.addLayout(copy, 1)
            resolve_next = QPushButton(self._resolution_button_label(remediation))
            resolve_next.setToolTip(remediation.tooltip)
            if remediation.action_id == "autopilot":
                resolve_next.clicked.connect(self._start_autopilot)
            elif remediation.action_id == "backup-guide":
                resolve_next.clicked.connect(lambda _checked=False: self.start_guided_backup())
            else:
                resolve_next.clicked.connect(
                    lambda _checked=False, gate=priority: self._show_resolution(gate)
                )
            banner_layout.addWidget(resolve_next)
            self.content.addWidget(banner)
        self.content.addWidget(self._boot_observation_card())
        self.content.addWidget(self._ascension_root_card())
        phases = (
            ("Workspace", "Source, extraction, Recipe, and plan evidence"),
            ("Build", "Toolchain and Device Pack compilation contract"),
            ("Signing", "Keys, AVB descriptors, and signed artifact verification"),
            ("Recovery", "Rollback evidence before device-changing work"),
            ("Flash", "Exact live-device safety evidence"),
            ("Guardian", "Final human-bound confirmation—not an automatic build failure"),
        )
        for phase, detail in phases:
            gates = tuple(gate for gate in self.report.gates if gate.phase == phase)
            if not gates:
                continue
            card = QFrame()
            card.setObjectName("BuildPhase")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(18, 15, 18, 15)
            heading = QLabel(f"{phase.upper()}  •  {detail}")
            heading.setObjectName("CardHeading")
            layout.addWidget(heading)
            for gate in gates:
                remediation = remediation_for(gate)
                row = QFrame()
                row.setProperty("gateStatus", gate.status.value)
                row.setToolTip(remediation.tooltip)
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(10, 8, 10, 8)
                symbol = {
                    GateStatus.PASS: "✓",
                    GateStatus.ATTENTION: "!",
                    GateStatus.BLOCKED: "×",
                }[gate.status]
                state = QLabel(symbol)
                state.setObjectName("GateSymbol")
                state.setFixedWidth(28)
                state.setToolTip(remediation.tooltip)
                label = QLabel(f"{gate.label}\n{gate.evidence}")
                label.setObjectName("GateCopy")
                label.setWordWrap(True)
                label.setToolTip(remediation.tooltip)
                badge = QLabel(gate.status.value.upper())
                badge.setObjectName("GateBadge")
                badge.setToolTip(remediation.tooltip)
                row_layout.addWidget(state)
                row_layout.addWidget(label, 1)
                if gate.status is not GateStatus.PASS:
                    resolve = QPushButton(self._resolution_button_label(remediation))
                    resolve.setObjectName("GateResolve")
                    resolve.setToolTip(remediation.tooltip)
                    if remediation.action_id == "autopilot":
                        resolve.clicked.connect(self._start_autopilot)
                    elif remediation.action_id == "backup-guide":
                        resolve.clicked.connect(lambda _checked=False: self.start_guided_backup())
                    else:
                        resolve.clicked.connect(
                            lambda _checked=False, current=gate: self._show_resolution(current)
                        )
                    row_layout.addWidget(resolve)
                    self.resolve_buttons[gate.gate_id] = resolve
                row_layout.addWidget(badge)
                layout.addWidget(row)
                self.gate_rows[gate.gate_id] = row
            self.content.addWidget(card)
        self.content.addStretch()
        if self.report.flash_ready:
            self.overall_badge.setText("✓  FLASH EVIDENCE READY")
        elif self.report.guardian_handoff_ready:
            self.overall_badge.setText("✓  PROJECT READY / GUARDIAN HANDOFF")
        elif self.report.build_ready:
            self.overall_badge.setText("◆  BUILD READY / FLASH LOCKED")
        elif self.report.workspace_ready:
            self.overall_badge.setText("◆  WORKSPACE READY / BUILD LOCKED")
        else:
            self.overall_badge.setText("!  EVIDENCE INCOMPLETE")
        if not self.autopilot_active:
            blocked_count = sum(gate.status is GateStatus.BLOCKED for gate in self.report.gates)
            attention_count = sum(gate.status is GateStatus.ATTENTION for gate in self.report.gates)
            self.status.setText(
                (
                    "Your project is ready for Guardian-controlled flash review  •  "
                    if self.report.guardian_handoff_ready
                    else "Readiness fingerprint  •  "
                )
                + f"{self.report.report_digest[:16]}…  •  {blocked_count} blocked  •  "
                f"{attention_count} need attention"
            )

    @staticmethod
    def _resolution_button_label(remediation) -> str:
        if remediation.action_id == "autopilot":
            return "Auto-resolve"
        if remediation.action_id == "backup-guide":
            return "Choose backup route"
        if remediation.action_id:
            return "Provide required evidence"
        return "View explanation"

    def _ascension_root_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("BuildPhase")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 15, 18, 15)
        guided_state = GuidedMissionStore(
            self.studio.store.projects_root / self.project.project_id
        ).load()
        heading = QLabel(
            "ASCENSION PROTOCOL  •  OPTIONAL ROOT ROUTE"
            if guided_state.root_choice != "ascension"
            else "ASCENSION PROTOCOL  •  DEVICE-AWARE ROOT PLAN"
        )
        heading.setObjectName("CardHeading")
        layout.addWidget(heading)
        plan_service = AscensionRootPlanService(self.studio.store)
        manifest_service = AscensionGuardianManifestService(
            self.studio.store,
            self.studio.pack_registry,
            getattr(self.studio, "attestation_store", None),
        )
        preparation = RootPatchPreparationService(self.studio.store)
        plan = next(
            (
                loaded
                for method in AscensionMethod
                if (loaded := plan_service.load(self.project.project_id, method)) is not None
            ),
            None,
        )
        patched = next(
            (
                receipt
                for method in AscensionMethod
                if (receipt := preparation.load_patched(self.project.project_id, method))
                is not None
            ),
            None,
        )
        integration = next(
            (
                receipt
                for method in AscensionMethod
                if (
                    receipt := RootRomIntegrationService(self.studio.store).load(
                        self.project.project_id, method
                    )
                )
                is not None
            ),
            None,
        )
        build_seal = next(
            (
                receipt
                for method in AscensionMethod
                if (
                    receipt := RootRomBuildHandoffService(self.studio.store).load(
                        self.project.project_id, method
                    )
                )
                is not None
            ),
            None,
        )
        row = QFrame()
        row.setProperty(
            "gateStatus",
            "pass" if plan is not None else "attention" if patched is not None else "attention",
        )
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(10, 8, 10, 8)
        symbol = QLabel("✓" if plan is not None else "!")
        symbol.setObjectName("GateSymbol")
        symbol.setFixedWidth(28)
        if guided_state.root_choice == "skip" and integration is None:
            copy = QLabel(
                "Genesis Sequence selected the unrooted route. No Ascension image is part of this build input.\n"
                "You may review the choice in Genesis before the build plan is frozen. Phone changed: NO."
            )
            row.setProperty("gateStatus", "pass")
        elif plan is not None:
            manifest = manifest_service.load(self.project.project_id, plan.method)
            device = next(
                (item for item in self.studio.devices if item.state is DeviceState.DEVICE),
                None,
            )
            device_matches = device is not None and plan_service.matches_device(plan, device)
            if manifest is not None and device_matches:
                copy = QLabel(
                    f"{plan.method.display_name} Guardian manifest compiled  •  {len(manifest.blockers)} unresolved safety gate(s)\n"
                    f"Target: {manifest.target_partition}  •  slot {manifest.target_slot or 'not yet proven'}  •  patched SHA-256 {manifest.patched_image_sha256[:16]}…\n"
                    "Authority: NONE  •  commands: NONE  •  final consent required  •  bootloader relock: PROHIBITED"
                )
                row.setProperty("gateStatus", "pass" if manifest.review_ready else "attention")
            else:
                copy = QLabel(
                    f"{plan.method.display_name} root plan {'ready' if device_matches else 'waiting for exact phone'}\n"
                    f"Target: {plan.target_partition}  •  patched SHA-256 {plan.patched_image_sha256[:16]}…  •  rollback {plan.rollback_record_digest[:16]}…\n"
                    "Open Ascension Protocol to compile the plain-language Guardian manifest. Commands: NONE."
                )
                row.setProperty("gateStatus", "attention")
        elif build_seal is not None:
            copy = QLabel(
                f"Ascension Build Seal verified for {build_seal.target_partition}  •  SHA-256 {build_seal.artifact_sha256[:16]}…\n"
                "Reconnect the exact authorized phone in Ascension Protocol to compile the command-free Guardian plan."
            )
        elif integration is not None:
            copy = QLabel(
                "Root image integrated into the isolated ROM with automatic rollback, but its build handoff is not sealed yet.\n"
                "Open Ascension Protocol and choose Seal rooted ROM build input. Phone changed: NO."
            )
        elif patched is not None:
            copy = QLabel(
                "Patched image verified, but it has not yet been integrated and sealed as a ROM build input.\n"
                "Open Ascension Protocol; ROMVERSE will snapshot, integrate, verify, and seal it before Guardian planning."
            )
        else:
            copy = QLabel(
                "Root is optional and has not been prepared. Ascension Protocol can scan the exact phone, recommend Magisk or KernelSU, acquire official tools, and verify a same-device patched image."
            )
        copy.setObjectName("GateCopy")
        copy.setWordWrap(True)
        open_ascension = QPushButton(
            "Review Genesis root choice"
            if guided_state.root_choice == "skip" and integration is None
            else "Open Ascension Protocol"
        )
        open_ascension.setObjectName("GateResolve")
        open_ascension.setToolTip(
            "Prepare or review a source-bound root plan. No root or flash command runs from this card."
        )
        if guided_state.root_choice == "skip" and integration is None:
            open_ascension.clicked.connect(self.studio._open_guided_setup)
        else:
            open_ascension.clicked.connect(self._open_ascension_protocol)
        row_layout.addWidget(symbol)
        row_layout.addWidget(copy, 1)
        row_layout.addWidget(open_ascension)
        layout.addWidget(row)
        return card

    def _open_ascension_protocol(self) -> None:
        from romverse.ui.ascension_protocol import AscensionProtocolDialog

        AscensionProtocolDialog(self.studio, self).exec()
        self.refresh()

    def start_guided_backup(self) -> None:
        """Open the established beginner backup chooser without advancing flash review."""

        if self.report is None:
            self.refresh()
        self._show_final_handoff((), backup_only=True)

    def _show_final_handoff(
        self,
        gates: tuple[BuildGate, ...],
        *,
        backup_only: bool = False,
    ) -> None:
        if self.report is None:
            return
        recovery = RecoveryEvidenceService(self.studio.store).assess(self.project.project_id)
        device = next(
            (item for item in self.studio.devices if item.state is DeviceState.DEVICE),
            None,
        )
        cloud_receipt = BackupHandoffService(self.studio.store).load(
            self.project.project_id,
            device,
        )
        if backup_only or (not recovery.external_backup_ready and cloud_receipt is None):
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Guardian handoff • choose your backup route")
            dialog.setIcon(QMessageBox.Icon.Information)
            dialog.setText(
                "Choose or update your phone backup"
                if recovery.external_backup_ready or cloud_receipt is not None
                else "Where is your phone backup?"
            )
            dialog.setInformativeText(
                (
                    "Current evidence: ROMVERSE has a hash-verified local backup archive. "
                    "You can create a fresh local-drive backup or replace the registered file."
                    if recovery.external_backup_ready
                    else (
                        f"Current evidence: you confirmed {cloud_receipt.provider} "
                        f"({cloud_receipt.last_backup_label}). ROMVERSE did not inspect its "
                        "private cloud contents. You can also create a verified local-drive backup."
                        if cloud_receipt is not None
                        else "ROMVERSE found no registered phone-data backup. Choose the route you want to use."
                    )
                )
                + "\n\nBack up to local drive copies only the shared-storage categories you select, "
                "shows progress, verifies every captured file, and registers the result. "
                "App-private data, credentials, messages, and secure folders still require "
                "their provider or app-specific backup. Neither route uploads your data."
            )
            choose_file = dialog.addButton(
                "Verify local backup file…",
                QMessageBox.ButtonRole.ActionRole,
            )
            create_backup = dialog.addButton(
                "Create cloud backup now…",
                QMessageBox.ButtonRole.ActionRole,
            )
            create_local_backup = dialog.addButton(
                "Back up to local drive…",
                QMessageBox.ButtonRole.ActionRole,
            )
            create_local_backup.setObjectName("Primary")
            create_local_backup.setDefault(True)
            create_local_backup.setToolTip(
                "Recommended: create, hash, verify, and register a read-only shared-storage backup."
            )
            choose_file.setToolTip(
                "Register and hash an independently created backup file without copying phone data."
            )
            confirm_cloud = dialog.addButton(
                "Confirm cloud backup…",
                QMessageBox.ButtonRole.ActionRole,
            )
            dialog.addButton("Not yet", QMessageBox.ButtonRole.RejectRole)
            dialog.exec()
            if dialog.clickedButton() is choose_file:
                selected, _filter = QFileDialog.getOpenFileName(
                    self,
                    "Select external phone backup",
                    str(Path.home()),
                    "All files (*)",
                )
                if selected:
                    self._verify_handoff_backup(Path(selected))
            elif dialog.clickedButton() is create_backup:
                if device is None:
                    QMessageBox.warning(
                        self,
                        "Connect the target phone",
                        "Connect and authorize the exact phone before starting its guided backup.",
                    )
                    return
                provider = PhoneBackupGuideDialog(device.display_name, self).selected_provider()
                if provider is None:
                    return
                self._confirm_cloud_backup(device, provider)
            elif dialog.clickedButton() is create_local_backup:
                self._prepare_phone_media_backup(device)
            elif dialog.clickedButton() is confirm_cloud:
                if device is None:
                    QMessageBox.warning(
                        self,
                        "Connect the target phone",
                        "ROMVERSE must bind the cloud confirmation to the exact authorized phone. Connect it through ADB and retry.",
                    )
                    return
                self._confirm_cloud_backup(device)
            return

        if self.report.flash_ready:
            self._prepare_guardian_flash_handoff(device)
            return

        if not self.report.guardian_handoff_ready:
            unresolved = tuple(
                gate.label for gate in self.report.gates if gate.status is not GateStatus.PASS
            )
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Guardian handoff • preparation continues")
            dialog.setIcon(QMessageBox.Icon.Information)
            dialog.setText("Your backup evidence is secured; the project is not yet flash-ready")
            dialog.setInformativeText(
                (
                    "ROMVERSE verified or recorded the backup route without changing the phone. "
                    "The remaining readiness evidence is:\n• " + "\n• ".join(unresolved[:6])
                    if unresolved
                    else "ROMVERSE verified or recorded the backup route without changing the phone."
                )
                + "\n\nROMVERSE can continue every safe local step, but it will not invent a "
                "signed device-write contract, physical recovery proof, or final consent."
            )
            continue_resolution = dialog.addButton(
                "Continue safe automatic resolution",
                QMessageBox.ButtonRole.AcceptRole,
            )
            dialog.addButton(QMessageBox.StandardButton.Close)
            dialog.exec()
            if dialog.clickedButton() is continue_resolution:
                QTimer.singleShot(0, self._start_autopilot)
            return

        dialog = QMessageBox(self)
        dialog.setWindowTitle("Guardian handoff • ready to continue")
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setText("Your project is ready for the Guardian stage")
        dialog.setInformativeText(
            (
                "ROMVERSE hash-verified the independently stored local backup"
                if recovery.external_backup_ready
                else f"You confirmed {cloud_receipt.provider} ({cloud_receipt.last_backup_label}); ROMVERSE did not inspect its cloud contents"
            )
            + ", plus every automatic source, build, signature-preservation or applicable AVB, device, rollback, and signed Device Pack flash-contract prerequisite.\n\nContinue to review the exact write manifest and give a separate final approval. Nothing is flashed by this prompt."
        )
        proceed = dialog.addButton(
            "I understand — continue to Guardian",
            QMessageBox.ButtonRole.AcceptRole,
        )
        dialog.addButton(QMessageBox.StandardButton.Close)
        dialog.exec()
        if dialog.clickedButton() is proceed:
            self.accept()

    def _prepare_guardian_flash_handoff(self, device: AndroidDevice | None) -> None:
        if self.report is None or not self.report.flash_ready:
            QMessageBox.warning(
                self,
                "Guardian handoff is not ready",
                "ROMVERSE must resolve every required card before flash mode can be selected.",
            )
            return
        if device is None:
            QMessageBox.warning(
                self,
                "Connect the exact target phone",
                "Reconnect and authorize the target phone. ROMVERSE will re-check its identity before preparing the final manifest.",
            )
            return
        mode = GuardianFlashModeDialog(device.display_name, self).value()
        if mode is None:
            return
        try:
            handoff = GuardianFlashHandoffService(self.studio.store).prepare(
                self.project.project_id,
                self.report,
                device,
                mode,
            )
        except (OSError, ProjectError) as exc:
            QMessageBox.warning(self, "Guardian handoff stopped safely", str(exc))
            return

        try:
            GuardianManifestReviewService(
                self.studio.store,
                self.studio.pack_registry,
            ).compile(
                self.project.project_id,
                self.report,
                device,
            )
        except (OSError, ProjectError) as exc:
            QMessageBox.warning(
                self,
                "Guardian manifest review could not be sealed",
                f"The flash-mode handoff remains recorded, but its command-free review packet could not be verified: {exc}",
            )
            return

        action = (
            "KEEP USER DATA"
            if handoff.mode is FlashMode.DIRTY_KEEP_DATA
            else "WIPE USER DATA AFTER FINAL APPROVAL"
        )
        self.status.setText(
            f"Guardian handoff prepared  •  {action}  •  {handoff.handoff_digest[:16]}…  •  "
            "bootloader relock: PROHIBITED  •  phone changed: NO"
        )
        complete = QMessageBox(self)
        complete.setWindowTitle("ROMVERSE • Guardian handoff prepared")
        complete.setIcon(QMessageBox.Icon.Information)
        complete.setText("Congratulations — your project is ready for exact Guardian review")
        complete.setInformativeText(
            f"Phone: {handoff.device_name} ({handoff.codename})\n"
            f"Mode: {handoff.mode.display_name}\n"
            f"Source: {handoff.source_sha256[:20]}…\n"
            f"Guardian receipt: {handoff.handoff_digest[:20]}…\n\n"
            "ROMVERSE recorded this exact project, source, phone, and data-handling choice. "
            "No device command has run. Guardian will now show the real manifest review and the "
            "exact evidence still required before any partition write or final consent can exist. "
            "Bootloader relocking is permanently prohibited."
        )
        return_to_genesis = complete.addButton(
            "Continue to Guardian review",
            QMessageBox.ButtonRole.AcceptRole,
        )
        complete.addButton(QMessageBox.StandardButton.Close)
        complete.exec()
        if complete.clickedButton() is return_to_genesis:
            self.guardian_manifest_requested = True
            self.accept()

    def _confirm_cloud_backup(
        self,
        device,
        selected_provider: CloudBackupProvider | None = None,
    ) -> None:
        confirmation = CloudBackupConfirmationDialog(
            device.display_name,
            self,
            selected_provider,
        ).values()
        if confirmation is None:
            return
        provider, last_backup = confirmation
        try:
            BackupHandoffService(self.studio.store).confirm_cloud(
                self.project.project_id,
                device,
                provider,
                last_backup,
                backup_completed=True,
                restore_access_confirmed=True,
                critical_data_scope_reviewed=True,
                limitations_acknowledged=True,
            )
        except ProjectError as exc:
            QMessageBox.warning(
                self,
                "Cloud backup confirmation stopped safely",
                str(exc),
            )
            return
        self.refresh()
        self.status.setText(
            f"{provider.value} confirmation recorded  •  exact device/project bound  •  cloud contents inspected: NO"
        )
        QTimer.singleShot(0, self._resume_after_backup)

    def _prepare_phone_media_backup(self, device: AndroidDevice | None) -> None:
        if device is None:
            QMessageBox.warning(
                self,
                "Connect the target phone",
                "Connect and authorize the exact phone before creating its local backup.",
            )
            return
        if self.studio.gateway is None or self.studio.adb_executable is None:
            resolved = self.studio._resolve_required_tools(
                ("ADB",),
                purpose=(
                    "The local-drive backup needs verified Android Platform Tools to read only "
                    "the shared-storage folders you choose. It cannot access app-private data."
                ),
                title="ROMVERSE • Resolve local-backup connection tools",
                success_message=(
                    "Android Platform Tools freshly verified for the local-drive backup."
                ),
                parent=self,
            )
            if (
                resolved
                and self.studio.gateway is not None
                and self.studio.adb_executable is not None
            ):
                # The resolver publishes the complete inventory to MainWindow, which creates the
                # Guardian gateway and every ADB-dependent service as one atomic runtime update.
                self.status.setText(
                    "Verified ADB runtime activated. Choose the local backup destination and scope."
                )
            if self.studio.gateway is None or self.studio.adb_executable is None:
                QMessageBox.warning(
                    self,
                    "Verified ADB is required",
                    "Android Platform Tools did not pass fresh verification, so ROMVERSE did not "
                    "prepare a phone backup plan.",
                )
                return
        settings = getattr(self.studio, "app_settings", None)
        default_destination = (
            Path(settings.backup_directory)
            if settings is not None and settings.backup_directory
            else None
        )
        selection = PhoneMediaBackupDialog(
            device.display_name,
            self,
            default_destination,
        ).values()
        if selection is None:
            return
        destination, scopes = selection
        service = PhoneMediaBackupService(
            self.studio.store.workspace,
            self.studio.adb_executable,
            self.studio.gateway,
            ApprovalStore(self.studio.store.workspace),
        )
        try:
            plan = service.prepare(device, destination, scopes)
        except (OSError, ProjectError) as exc:
            QMessageBox.warning(self, "Local backup plan stopped safely", str(exc))
            return
        review = QMessageBox(self)
        review.setWindowTitle("Guardian review • local phone backup")
        review.setIcon(QMessageBox.Icon.Warning)
        review.setText("Review the exact read-only backup plan")
        review.setInformativeText(
            f"Phone: {plan.device_name}\n"
            f"Destination: {plan.archive_path}\n"
            f"Selected: {', '.join(scope.value for scope in plan.scopes)}\n"
            f"Free space now: {_human_bytes(plan.free_bytes_before)}\n\n"
            "ROMVERSE will read only these shared-storage folders, create a verified ZIP, and "
            "register it as local Guardian evidence. App-private data and credentials are not "
            "included. The phone, partitions, data state, and bootloader are never changed."
        )
        approve = review.addButton(
            "Approve read-only backup",
            QMessageBox.ButtonRole.AcceptRole,
        )
        review.addButton(QMessageBox.StandardButton.Cancel)
        review.exec()
        if review.clickedButton() is not approve:
            return
        try:
            service.approve(plan)
        except (OSError, ProjectError, GuardianDeniedError) as exc:
            QMessageBox.warning(self, "Local backup approval stopped safely", str(exc))
            return
        self._start_phone_media_backup(service, plan)

    def _start_phone_media_backup(
        self,
        service: PhoneMediaBackupService,
        plan: PhoneMediaBackupPlan,
    ) -> None:
        if self.media_backup_worker is not None:
            return
        self.media_backup_worker = PhoneMediaBackupWorker(
            service,
            plan,
            RecoveryEvidenceService(self.studio.store),
            self.project.project_id,
        )
        self.media_backup_worker.signals.complete.connect(self._phone_media_backup_complete)
        self.media_backup_worker.signals.failed.connect(self._phone_media_backup_failed)
        self.media_backup_worker.signals.progress.connect(self.process_progress.report)
        self.media_backup_worker.signals.progress.connect(
            lambda value: self._progress_preparation_console("forge-phone-media-backup", value)
        )
        self.process_progress.begin()
        self.autopilot_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.status.setText(
            "Creating verified local-drive phone backup  •  shared storage only  •  phone changed: NO"
        )
        self._start_preparation_console("forge-phone-media-backup")
        start_background(self.media_backup_worker)

    @Slot(object)
    def _phone_media_backup_complete(self, result: object) -> None:
        if not isinstance(result, PhoneMediaBackupReceipt):
            self._phone_media_backup_failed("The backup worker returned no verifiable receipt")
            return
        self.media_backup_worker = None
        self.process_progress.finish()
        self.autopilot_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.refresh()
        self.status.setText(
            f"Local phone backup verified  •  {result.archive_name}  •  "
            f"{result.file_count} file(s)  •  SHA-256 {result.archive_sha256[:16]}…  •  "
            "phone changed: NO"
        )
        self._finish_preparation_console("forge-phone-media-backup", MissionState.SUCCEEDED)
        QTimer.singleShot(0, self._resume_after_backup)

    @Slot(str)
    def _phone_media_backup_failed(self, message: str) -> None:
        self.media_backup_worker = None
        self.process_progress.stop()
        self.autopilot_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.status.setText(message)
        self._finish_preparation_console("forge-phone-media-backup", MissionState.FAILED)
        QMessageBox.warning(
            self,
            "Local phone backup stopped safely",
            message + "\n\nNo phone state or bootloader setting was changed.",
        )

    def _verify_handoff_backup(self, source: Path) -> None:
        if self.recovery_worker is not None:
            return
        self.recovery_worker = RecoveryEvidenceWorker(
            RecoveryEvidenceService(self.studio.store),
            "register",
            self.project.project_id,
            "external_backup",
            source,
        )
        self.recovery_worker.signals.complete.connect(self._handoff_backup_complete)
        self.recovery_worker.signals.failed.connect(self._handoff_backup_failed)
        self.recovery_worker.signals.progress.connect(self.process_progress.report)
        self.recovery_worker.signals.progress.connect(
            lambda value: self._progress_preparation_console("forge-external-backup", value)
        )
        self.process_progress.begin(determinate=True)
        self.autopilot_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.status.setText("Hashing and verifying the selected external backup …")
        self._start_preparation_console("forge-external-backup")
        start_background(self.recovery_worker)

    @Slot(object)
    def _handoff_backup_complete(self, _record: object) -> None:
        self.recovery_worker = None
        self.process_progress.finish()
        self.autopilot_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.refresh()
        self.status.setText(
            "External backup verified  •  backup requirement complete  •  "
            "rechecking remaining prerequisites  •  phone changed: NO"
        )
        self._finish_preparation_console("forge-external-backup", MissionState.SUCCEEDED)
        QTimer.singleShot(0, self._resume_after_backup)

    def _resume_after_backup(self) -> None:
        """Reassess and continue; a backup receipt alone never implies flash readiness."""

        self.refresh()
        if self.report is None:
            return
        self.status.setText(
            "Backup evidence secured  •  ROMVERSE is reassessing the remaining readiness "
            "gates  •  phone changed: NO"
        )
        self._start_autopilot()

    @Slot(str)
    def _handoff_backup_failed(self, message: str) -> None:
        self.recovery_worker = None
        self.process_progress.stop()
        self.autopilot_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.status.setText(message)
        self._finish_preparation_console("forge-external-backup", MissionState.FAILED)
        QMessageBox.warning(self, "Backup verification stopped safely", message)

    def _start_autopilot(self) -> None:
        if self.report is not None and self.report.guardian_handoff_ready:
            unresolved = tuple(
                gate for gate in self.report.gates if gate.status is not GateStatus.PASS
            )
            self._show_final_handoff(unresolved)
            return
        if self.autopilot_active or any(
            worker is not None
            for worker in (
                self.metadata_worker,
                self.blueprint_worker,
                self.build_worker,
                self.avb_worker,
                self.signing_worker,
                self.recovery_worker,
                self.media_backup_worker,
            )
        ):
            return
        self.autopilot_active = True
        self.autopilot_completed.clear()
        self.autopilot_waiting_for = ""
        self.autopilot_button.setEnabled(False)
        self.autopilot_button.setText("ROMVERSE is resolving …")
        self.process_progress.begin()
        QTimer.singleShot(0, self._continue_autopilot)

    def _continue_autopilot(self) -> None:
        if not self.autopilot_active:
            return
        self.report = self.service.assess(self.project.project_id, tuple(self.studio.devices))
        steps = resolution_plan(self.report)
        if not steps:
            self._finish_autopilot(
                "Every available readiness gate is satisfied. ROMVERSE is ready for the next Guardian-approved phase."
            )
            return
        step = steps[0]
        self.status.setText(f"ROMVERSE Autopilot  •  {step.title}  •  {step.explanation}")
        if step.kind is not ResolutionKind.AUTOMATIC:
            kind = (
                "verified input from you"
                if step.kind is ResolutionKind.GUIDED_INPUT
                else "authoritative external evidence"
            )
            self._finish_autopilot(
                f"Safe automatic work is complete. {step.title} now needs {kind}: {step.explanation}",
                waiting_gate=step.gate_id,
            )
            return

        action = step.action_id
        if action == "inspect":
            self.autopilot_waiting_for = "inspect"
            self.studio._start_worker("inspect")
        elif action == "prepare-tree":
            operation = (
                "extract"
                if self.studio.store.working_copy(self.project.project_id) is not None
                else "working-copy"
            )
            self.autopilot_waiting_for = operation
            self.studio._start_worker(operation)
        elif action == "plan":
            self.autopilot_waiting_for = "plan"
            self.studio._start_worker("plan")
        elif action == "tools":
            self._autopilot_tools()
        elif action == "source-blueprint":
            self._prepare_source_blueprint()
        elif action == "contract-plan":
            try:
                self.service.prepare_device_build_plan(self.project.project_id)
            except ProjectError:
                self.autopilot_waiting_for = "metadata"
                self._prepare_rebuild_metadata(from_autopilot=True)
                return
            self.autopilot_completed.append(step.title)
            QTimer.singleShot(0, self._continue_autopilot)
        elif action == "local-build":
            self.autopilot_waiting_for = "local-build"
            self._execute_local_build()
        elif action == "avb-inspect":
            self.autopilot_waiting_for = "avb"
            self._inspect_avb_topology()
        elif action == "recovery-evidence":
            self._autopilot_recovery()
        else:
            self._finish_autopilot(
                f"ROMVERSE reached {step.title}, but no safe automatic resolver is available."
            )

    def _autopilot_recovery(self) -> None:
        """Resolve every safe local recovery prerequisite before prompting the user."""

        snapshots = self.studio.store.list_snapshots(self.project.project_id)
        if not any(snapshot.schema_version == 2 for snapshot in snapshots):
            self.autopilot_waiting_for = "snapshot"
            self.process_progress.begin()
            self.status.setText(
                "ROMVERSE Autopilot  •  Time Machine checkpoint  •  Copying the isolated "
                "working baseline locally. Large projects can take several minutes; the "
                "protected source and connected phone remain unchanged."
            )
            self.studio._start_worker("snapshot")
            return

        service = RecoveryEvidenceService(self.studio.store)
        record = service.load(self.project.project_id)
        if record is not None and record.schema_version == 1:
            self.autopilot_waiting_for = "recovery-evidence"
            self.recovery_worker = RecoveryEvidenceWorker(
                service,
                "verify",
                self.project.project_id,
            )
            self.recovery_worker.signals.complete.connect(self._autopilot_recovery_complete)
            self.recovery_worker.signals.failed.connect(self._autopilot_recovery_failed)
            self.recovery_worker.signals.progress.connect(self.process_progress.report)
            self.recovery_worker.signals.progress.connect(
                lambda value: self._progress_preparation_console(
                    "forge-recovery-evidence",
                    value,
                )
            )
            self.process_progress.begin()
            self._set_action_buttons_enabled(False)
            self.status.setText(
                "ROMVERSE Autopilot  •  Recovery evidence  •  Rehashing the preserved "
                "backup and exact stock package before upgrading their evidence record."
            )
            self._start_preparation_console("forge-recovery-evidence")
            start_background(self.recovery_worker)
            return

        self._finish_autopilot(
            "The verified local Time Machine checkpoint is ready. Choose where to keep your "
            "personal phone backup and, when required, select the exact stock firmware package; "
            "ROMVERSE will hash, bind, and re-check both automatically.",
            waiting_gate="recovery",
        )

    @Slot(object)
    def _autopilot_recovery_complete(self, _record: object) -> None:
        if not self.autopilot_active or self.autopilot_waiting_for != "recovery-evidence":
            return
        self.recovery_worker = None
        self.autopilot_waiting_for = ""
        self.autopilot_completed.append("Recovery Evidence Verification")
        self.process_progress.finish()
        self._set_action_buttons_enabled(True)
        self._finish_preparation_console("forge-recovery-evidence", MissionState.SUCCEEDED)
        QTimer.singleShot(0, self._continue_autopilot)

    @Slot(str)
    def _autopilot_recovery_failed(self, message: str) -> None:
        if not self.autopilot_active or self.autopilot_waiting_for != "recovery-evidence":
            return
        self.recovery_worker = None
        self._set_action_buttons_enabled(True)
        self._finish_preparation_console("forge-recovery-evidence", MissionState.FAILED)
        self._finish_autopilot(
            "ROMVERSE preserved the existing recovery record but could not verify it: " + message,
            waiting_gate="recovery",
        )

    def _autopilot_tools(self) -> None:
        from romverse.infrastructure.provisioning import required_tools_for_source
        from romverse.infrastructure.tools import ToolVerifier
        from romverse.platform.host import current_host
        from romverse.ui.toolchain_center import (
            ToolchainSetupDialog,
            activate_verified_managed_tools,
        )

        pack = next(
            (
                item
                for item in self.studio.pack_registry.packs
                if item.pack_id == self.project.device_pack_id
            ),
            None,
        )
        contract = (
            pack.build_contract
            if pack is not None
            and pack.build_contract is not None
            and self.project.original is not None
            and pack.build_contract.source.archive_sha256 == self.project.original.sha256
            else None
        )
        inspection = self.studio.inspection.load_report(self.project.project_id)
        required = required_tools_for_source(
            contract,
            inspection.partition_signals if inspection is not None else (),
        )
        dialog = ToolchainSetupDialog(
            current_host(),
            self.studio.tool_statuses,
            self.studio.store.workspace,
            self,
            required_names=required or None,
            auto_start=True,
            auto_close=True,
        )
        dialog.exec()
        if dialog.last_success is not True:
            self._finish_autopilot(
                "Forge Arsenal did not complete every automatic requirement. "
                + (dialog.last_message or "Review the visible installation requirement and retry.")
            )
            return
        activate_verified_managed_tools(self.studio.store.workspace)
        self.studio.set_tool_statuses(
            ToolVerifier(current_host(), SubprocessRunner()).verify_extended()
        )
        tool_digest = hashlib.sha256(
            json.dumps(
                [asdict(item) for item in self.studio.tool_statuses],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        tool_evidence = None
        try:
            verified_tools = ToolchainVerificationStore(self.studio.store.workspace).record(
                self.studio.tool_statuses,
                required,
            )
            tool_digest = verified_tools.receipt_digest
            tool_evidence = (
                verified_tools.evidence_ref,
                ToolchainVerificationStore.FORMAT,
            )
        except (OSError, ValueError):
            tool_evidence = None
        self._record_online_fix_success(
            ("verify-platform-tools",),
            tool_digest,
            "Forge Arsenal verified the required Platform Tools and contract toolchain.",
            *(tool_evidence or ("", "")),
        )
        self.autopilot_completed.append("Forge Arsenal requirements")
        QTimer.singleShot(0, self._continue_autopilot)

    @Slot(str, object)
    def _autopilot_studio_complete(self, operation: str, _result: object) -> None:
        if not self.autopilot_active or operation != self.autopilot_waiting_for:
            return
        self.autopilot_completed.append(operation.replace("-", " ").title())
        self.autopilot_waiting_for = ""
        self.process_progress.finish()
        QTimer.singleShot(0, self._continue_autopilot)

    @Slot(str, int)
    def _autopilot_studio_progress(self, operation: str, value: int) -> None:
        if self.autopilot_active and operation == self.autopilot_waiting_for:
            self.process_progress.report(value)

    @Slot(str, str)
    def _autopilot_studio_failed(self, operation: str, message: str) -> None:
        if not self.autopilot_active or operation != self.autopilot_waiting_for:
            return
        self._finish_autopilot(f"ROMVERSE stopped safely while resolving {operation}: {message}")
        self._source_online_guidance(
            message,
            operation,
            tool_name="AVBTool" if operation == "avb" else "",
        )

    def _finish_autopilot(self, message: str, *, waiting_gate: str = "") -> None:
        completed = len(self.autopilot_completed)
        self.autopilot_active = False
        self.autopilot_waiting_for = ""
        self.autopilot_button.setEnabled(True)
        self.autopilot_button.setText(
            "Continue automatic resolution" if waiting_gate else "Auto-resolve && continue"
        )
        self.process_progress.finish()
        self.refresh()
        prompt_for_backup = bool(
            waiting_gate == "user-backup"
            or (
                self.report is not None
                and self.report.guardian_handoff_ready
                and not self.report.flash_ready
            )
        )
        if self.report is not None and self.report.guardian_handoff_ready:
            message = "Your project is ready for Guardian-controlled flash review. ROMVERSE resolved every safe automatic step; only final user-data backup confirmation and explicit device-write consent remain."
            waiting_gate = ""
            self.autopilot_button.setText("Review final Guardian handoff")
        prefix = f"{completed} safe step(s) completed automatically. " if completed else ""
        self.status.setText(prefix + message)
        if waiting_gate and self.report is not None:
            gate = next((item for item in self.report.gates if item.gate_id == waiting_gate), None)
            if gate is not None:
                button = self.resolve_buttons.get(waiting_gate)
                if button is not None:
                    button.setText("Provide required evidence")
                    button.setFocus()
        if prompt_for_backup:
            QTimer.singleShot(0, self.start_guided_backup)

    def _boot_observation_card(self) -> QFrame:
        service = BootObservationService(self.studio.store, self.studio.pack_registry)
        receipt = service.load(self.project.project_id)
        card = QFrame()
        card.setObjectName("BuildPhase")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(18, 15, 18, 15)
        copy = QVBoxLayout()
        heading = QLabel("BOOT OBSERVATORY  •  READ-ONLY POST-BUILD EVIDENCE")
        heading.setObjectName("CardHeading")
        if receipt is None:
            detail = QLabel(
                "No exact-device boot samples are recorded. This does not affect build output and cannot prove a flash.\n"
                f"Next: {service.next_step(receipt)}"
            )
        else:
            detail = QLabel(
                f"{receipt.status.value.upper()}  •  {len(receipt.samples)} sample(s)  •  "
                f"{receipt.diagnosis}\nNext: {service.next_step(receipt)}\n"
                "Flash-linked: NO  •  Verified first boot: NO"
            )
        detail.setObjectName("GateCopy")
        detail.setWordWrap(True)
        copy.addWidget(heading)
        copy.addWidget(detail)
        layout.addLayout(copy, 1)
        observe = QPushButton(
            "Record baseline sample" if receipt is None else "Record follow-up sample"
        )
        observe.setToolTip(
            "Record boot-completion, device uptime, active slot, and build identity from the current Guardian-approved read-only scan."
        )
        observe.clicked.connect(self._observe_boot)
        observe.setEnabled(bool(self.studio.devices))
        layout.addWidget(observe)
        return card

    def _observe_boot(self) -> None:
        if not self.studio.devices:
            self.status.setText(
                "Connect and authorize the exact target before observing boot state."
            )
            return
        service = BootObservationService(self.studio.store, self.studio.pack_registry)
        existing = service.load(self.project.project_id)
        wait = service.next_sample_wait_seconds(existing)
        if wait:
            self.status.setText(
                f"Boot Observatory is preserving sample spacing. Record the next read-only sample in about {wait} second(s)."
            )
            return
        try:
            receipt = service.observe(self.project.project_id, self.studio.devices[0])
        except (OSError, ProjectError) as exc:
            self.status.setText(str(exc))
            QMessageBox.warning(self, "Boot observation stopped safely", str(exc))
            return
        self.refresh()
        self.status.setText(
            f"Boot sample recorded  •  {receipt.status.value}  •  "
            f"{receipt.diagnosis}  •  phone changed: NO"
        )

    def _show_resolution(self, gate: BuildGate) -> None:
        remediation = remediation_for(gate)
        dialog = QMessageBox(self)
        dialog.setWindowTitle(f"Resolve • {gate.label}")
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setText(gate.label)
        dialog.setInformativeText(
            f"{remediation.summary}\n\nCurrent evidence:\n{gate.evidence}\n\n"
            "Recommended path:\n"
            + "\n".join(f"{index}. {fix}" for index, fix in enumerate(remediation.fixes, 1))
        )
        action = None
        if remediation.action_id:
            action = dialog.addButton(
                remediation.action_label or "Open relevant section",
                QMessageBox.ButtonRole.ActionRole,
            )
        dialog.addButton(QMessageBox.StandardButton.Close)
        dialog.exec()
        if action is not None and dialog.clickedButton() is action:
            self._open_resolution(remediation.action_id)

    def _open_resolution(self, action_id: str) -> None:
        if action_id == "autopilot":
            self._start_autopilot()
        elif action_id == "rom-studio":
            self.accept()
        elif action_id == "recipe-forge":
            self.accept()
            self.studio._guided_recipe()
        elif action_id == "toolchain":
            self.accept()
            self.studio.request_toolchain("build-readiness")
        elif action_id == "time-machine":
            self.accept()
            self.studio.request_time_machine()
        elif action_id == "device-packs":
            self.accept()
            self.studio.request_device_atlas()
        elif action_id == "device-center":
            self.accept()
            self.studio.request_device_center("build-readiness")
        elif action_id == "backup-guide":
            self.start_guided_backup()
        elif action_id == "ascension-protocol":
            self._open_ascension_protocol()

    def _prepare_source_blueprint(self) -> None:
        if any(
            worker is not None
            for worker in (
                self.blueprint_worker,
                self.metadata_worker,
                self.build_worker,
                self.avb_worker,
                self.signing_worker,
            )
        ):
            return
        service = FirmwareSourceIntelligenceService(
            self.studio.store,
            self.studio.tool_statuses,
            self.studio.filesystem_service.runner
            if self.studio.filesystem_service is not None
            else SubprocessRunner(),
        )
        self.blueprint_worker = SourceBlueprintWorker(service, self.project.project_id)
        self.blueprint_worker.signals.complete.connect(self._source_blueprint_complete)
        self.blueprint_worker.signals.failed.connect(self._source_blueprint_failed)
        self.blueprint_worker.signals.progress.connect(self.process_progress.report)
        self.blueprint_worker.signals.progress.connect(
            lambda value: self._progress_preparation_console("forge-source-blueprint", value)
        )
        self.autopilot_waiting_for = "source-blueprint"
        self.process_progress.begin()
        self.status.setText(
            "Identifying firmware format, selecting the correct adapter, and hashing exact local inputs … phone changed: NO"
        )
        self._set_action_buttons_enabled(False)
        self._start_preparation_console("forge-source-blueprint")
        start_background(self.blueprint_worker)

    @Slot(object)
    def _source_blueprint_complete(self, blueprint: object) -> None:
        if not isinstance(
            blueprint,
            (FastbootSourceBlueprint, OtaPayloadBlueprint, PartitionBundleBlueprint),
        ):
            self._source_blueprint_failed(
                "Firmware Source Intelligence returned no verifiable blueprint receipt"
            )
            return
        digest = str(getattr(blueprint, "blueprint_digest", ""))
        partitions = getattr(blueprint, "partitions", ())
        source_kind = str(getattr(blueprint, "source_kind", ""))
        self.blueprint_worker = None
        self.process_progress.finish()
        self._set_action_buttons_enabled(True)
        self.refresh()
        self.status.setText(
            f"Source-bound {source_kind} blueprint verified  •  {len(partitions)} partition record(s)  •  {digest[:16]}…  •  phone changed: NO"
        )
        self._finish_preparation_console("forge-source-blueprint", MissionState.SUCCEEDED)
        self._record_online_fix_success(
            ("inspect-payload-source", "classify-ota-source"),
            digest,
            "Firmware Source Intelligence classified and verified the exact source-bound blueprint.",
            (
                f"projects/{self.project.project_id}/"
                + (
                    FirmwareSourceIntelligenceService.OTA_NAME
                    if source_kind == "ota-payload"
                    else FirmwareSourceIntelligenceService.BUNDLE_NAME
                    if source_kind == "partition-bundle"
                    else "source-blueprint.romverse"
                )
            ),
            (
                "romverse.ota-source-blueprint"
                if source_kind == "ota-payload"
                else "romverse.partition-bundle-blueprint"
                if source_kind == "partition-bundle"
                else "romverse.source-blueprint"
            ),
        )
        if self.autopilot_active and self.autopilot_waiting_for == "source-blueprint":
            self.autopilot_completed.append("Source-bound build blueprint")
            self.autopilot_waiting_for = ""
            QTimer.singleShot(0, self._continue_autopilot)

    @Slot(str)
    def _source_blueprint_failed(self, message: str) -> None:
        self.blueprint_worker = None
        self.process_progress.stop()
        self._set_action_buttons_enabled(True)
        self._finish_preparation_console("forge-source-blueprint", MissionState.FAILED)
        if self.autopilot_active and self.autopilot_waiting_for == "source-blueprint":
            self._finish_autopilot(
                f"ROMVERSE could not derive the source blueprint automatically: {message}"
            )
        else:
            self.status.setText(message)
        self._source_online_guidance(message, "source-blueprint")

    def _set_action_buttons_enabled(self, enabled: bool) -> None:
        for button in (
            self.metadata_button,
            self.build_button,
            self.avb_button,
            self.signing_button,
            self.close_button,
        ):
            button.setEnabled(enabled)

    def _simulate(self) -> None:
        if self.report is None:
            return
        receipt = self.service.simulate(self.report)
        path = (
            self.studio.store.projects_root / self.project.project_id / self.service.SIMULATION_NAME
        )
        stages = "  →  ".join(f"{name}: {status}" for name, status in receipt.stages)
        self.status.setText(
            f"Simulation complete  •  {stages}  •  stopped at {receipt.stopped_at}. "
            f"Phone changed: NO. Receipt: {path.name}"
        )

    def _prepare_build_plan(self) -> None:
        try:
            plan = self.service.prepare_device_build_plan(self.project.project_id)
        except ProjectError as exc:
            self.status.setText(str(exc))
            QMessageBox.warning(self, "Build plan remains locked", str(exc))
            return
        self.refresh()
        self.status.setText(
            f"Locked local build plan saved  •  {plan.plan_digest[:16]}…  •  phone changed: NO"
        )

    def _prepare_rebuild_metadata(
        self, _checked: bool = False, *, from_autopilot: bool = False
    ) -> None:
        if (
            self.metadata_worker is not None
            or self.avb_worker is not None
            or self.signing_worker is not None
        ):
            return
        pack = next(
            (
                item
                for item in self.studio.pack_registry.packs
                if item.pack_id == self.project.device_pack_id
            ),
            None,
        )
        contract = pack.build_contract if pack is not None else None
        filesystems = self.studio.filesystem_service
        payloads = self.studio.payload_service
        fakeroot = next(
            (
                Path(item.path)
                for item in self.studio.tool_statuses
                if item.name == "Fakeroot" and item.available and item.path
            ),
            None,
        )
        if contract is None or filesystems is None or payloads is None or fakeroot is None:
            message = "ROMVERSE cannot prepare rebuild evidence until an exact source-bound Device Pack, Partition Atlas inputs, and verified Fakeroot are available."
            self.status.setText(message)
            if from_autopilot:
                self._finish_autopilot(
                    message
                    + " The remaining authoritative evidence cannot be guessed or generated safely.",
                    waiting_gate="device-pack-build" if contract is None else "tools",
                )
            else:
                self._start_autopilot()
            return
        metadata = RebuildMetadataService(
            self.studio.store,
            filesystems,
            filesystems.runner,
            fakeroot,
        )
        service = BuildInputPreparationService(
            self.studio.store,
            payloads,
            filesystems,
            metadata,
        )
        self.metadata_worker = RebuildMetadataWorker(
            service,
            self.project.project_id,
            contract,
        )
        self.metadata_worker.signals.complete.connect(self._metadata_complete)
        self.metadata_worker.signals.failed.connect(self._metadata_failed)
        self.metadata_button.setEnabled(False)
        self.build_button.setEnabled(False)
        self.avb_button.setEnabled(False)
        self.signing_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.metadata_button.setText("Preparing, please wait …")
        self.process_progress.begin()
        self.status.setText(
            "Reconciling local ownership and source-bound SELinux evidence … phone changed: NO"
        )
        self._start_preparation_console("forge-build-inputs")
        start_background(self.metadata_worker)

    @Slot(object)
    def _metadata_complete(self, result: object) -> None:
        if not isinstance(result, BuildInputPreparation):
            self._metadata_failed("Build preparation returned no verifiable evidence receipt")
            return
        count = len(getattr(result, "metadata_receipts", ()))
        self.metadata_worker = None
        self.process_progress.finish()
        self.metadata_button.setEnabled(True)
        self.metadata_button.setText("Prepare exact build inputs")
        self.build_button.setEnabled(True)
        self.avb_button.setEnabled(True)
        self.signing_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.refresh()
        self.status.setText(
            f"Rebuild evidence captured for {count} partition(s)  •  phone changed: NO"
        )
        self._finish_preparation_console("forge-build-inputs", MissionState.SUCCEEDED)
        if self.autopilot_active and self.autopilot_waiting_for == "metadata":
            self.autopilot_completed.append("Exact build inputs")
            self.autopilot_waiting_for = ""
            QTimer.singleShot(0, self._continue_autopilot)

    @Slot(str)
    def _metadata_failed(self, message: str) -> None:
        self.metadata_worker = None
        self.process_progress.stop()
        self.metadata_button.setEnabled(True)
        self.metadata_button.setText("Prepare exact build inputs")
        self.build_button.setEnabled(True)
        self.avb_button.setEnabled(True)
        self.signing_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.status.setText(message)
        self._finish_preparation_console("forge-build-inputs", MissionState.FAILED)
        if self.autopilot_active and self.autopilot_waiting_for == "metadata":
            self._finish_autopilot(
                f"ROMVERSE stopped safely while preparing exact build inputs: {message}"
            )
        else:
            QMessageBox.warning(self, "Rebuild evidence remains locked", message)
        self._source_online_guidance(message, "build-inputs")

    def _execute_local_build(self) -> None:
        if (
            self.build_worker is not None
            or self.metadata_worker is not None
            or self.avb_worker is not None
            or self.signing_worker is not None
        ):
            return
        executor = LocalDeviceBuildExecutor(
            self.studio.store,
            self.studio.pack_registry,
            self.studio.tool_statuses,
            self.studio.filesystem_service.runner
            if self.studio.filesystem_service is not None
            else SubprocessRunner(),
        )
        self.build_worker = LocalBuildWorker(executor, self.project.project_id)
        self.build_worker.signals.complete.connect(self._build_complete)
        self.build_worker.signals.failed.connect(self._build_failed)
        self.build_button.setEnabled(False)
        self.build_button.setText("Building and verifying …")
        self.process_progress.begin()
        self.metadata_button.setEnabled(False)
        self.avb_button.setEnabled(False)
        self.signing_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.status.setText(
            "Building a versioned local candidate, then unpacking and comparing every partition … phone changed: NO"
        )
        self._start_preparation_console("forge-local-candidate")
        start_background(self.build_worker)

    @Slot(object)
    def _build_complete(self, receipt: object) -> None:
        if not isinstance(receipt, LocalBuildReceipt):
            self._build_failed("Local build returned no verifiable candidate receipt")
            return
        outputs = getattr(receipt, "outputs", ())
        digest = getattr(receipt, "receipt_digest", "")
        self.build_worker = None
        self.process_progress.finish()
        self.build_button.setEnabled(True)
        self.build_button.setText("Build verified local candidate")
        self.metadata_button.setEnabled(True)
        self.avb_button.setEnabled(True)
        self.signing_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.refresh()
        self.status.setText(
            f"Local candidate verified  •  {len(outputs)} output(s)  •  receipt {digest[:16]}…  •  phone changed: NO"
        )
        self._finish_preparation_console("forge-local-candidate", MissionState.SUCCEEDED)
        if self.autopilot_active and self.autopilot_waiting_for == "local-build":
            self.autopilot_completed.append("Verified local candidate")
            self.autopilot_waiting_for = ""
            QTimer.singleShot(0, self._continue_autopilot)

    @Slot(str)
    def _build_failed(self, message: str) -> None:
        self.build_worker = None
        self.process_progress.stop()
        self.build_button.setEnabled(True)
        self.build_button.setText("Build verified local candidate")
        self.metadata_button.setEnabled(True)
        self.avb_button.setEnabled(True)
        self.signing_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.status.setText(message)
        self._finish_preparation_console("forge-local-candidate", MissionState.FAILED)
        if self.autopilot_active and self.autopilot_waiting_for == "local-build":
            self._finish_autopilot(f"Local build stopped safely: {message}")
        else:
            QMessageBox.warning(self, "Local build stopped safely", message)
        self._source_online_guidance(message, "local-build")

    def _inspect_avb_topology(self) -> None:
        if any(
            worker is not None
            for worker in (
                self.metadata_worker,
                self.build_worker,
                self.avb_worker,
                self.signing_worker,
            )
        ):
            return
        payloads = self.studio.payload_service
        avbtool = next(
            (
                Path(item.path)
                for item in self.studio.tool_statuses
                if item.name == "AVBTool" and item.available and item.path
            ),
            None,
        )
        if payloads is None or avbtool is None:
            required = tuple(
                name
                for name, missing in (
                    ("Payload Dumper", payloads is None),
                    ("AVBTool", avbtool is None),
                )
                if missing
            )
            if not self.studio._resolve_required_tools(
                required,
                purpose=(
                    "Forge Control selected only the missing read-only tools required to inspect "
                    "the current source's Android Verified Boot topology."
                ),
                title="ROMVERSE • Resolve AVB inspection tools",
                success_message="AVB inspection tools freshly verified for Forge Control.",
                parent=self,
            ):
                self.status.setText(
                    "AVB inspection remains paused until every selected tool verifies successfully."
                )
                return
            payloads = self.studio.payload_service
            avbtool = next(
                (
                    Path(item.path)
                    for item in self.studio.tool_statuses
                    if item.name == "AVBTool" and item.available and item.path
                ),
                None,
            )
        if payloads is None or avbtool is None:
            message = (
                "AVB inspection remains paused because Payload Dumper or AVBTool did not pass "
                "the fresh Forge Arsenal verification."
            )
            self.status.setText(message)
            QMessageBox.warning(self, "AVB evidence remains locked", message)
            return
        service = AvbEvidenceService(
            self.studio.store,
            self.studio.pack_registry,
            self.studio.tool_statuses,
            payloads,
            avbtool,
            payloads.runner,
        )
        self.avb_worker = AvbEvidenceWorker(service, self.project.project_id)
        self.avb_worker.signals.complete.connect(self._avb_complete)
        self.avb_worker.signals.failed.connect(self._avb_failed)
        self.avb_button.setEnabled(False)
        self.avb_button.setText("Inspecting AVB, please wait …")
        self.process_progress.begin()
        self.metadata_button.setEnabled(False)
        self.build_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.signing_button.setEnabled(False)
        self.status.setText(
            "Comparing exact source and local candidate AVB identities … phone changed: NO"
        )
        self._start_preparation_console("forge-avb-topology")
        start_background(self.avb_worker)

    @Slot(object)
    def _avb_complete(self, receipt: object) -> None:
        if not isinstance(receipt, AvbTopologyReceipt):
            self._avb_failed("AVB inspection returned no verifiable topology receipt")
            return
        diagnosis = str(getattr(receipt, "diagnosis", "AVB topology recorded"))
        self.avb_worker = None
        self.process_progress.finish()
        self.avb_button.setEnabled(True)
        self.avb_button.setText("Inspect AVB topology")
        self.metadata_button.setEnabled(True)
        self.build_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.signing_button.setEnabled(True)
        self.refresh()
        self.status.setText(f"{diagnosis}  •  phone changed: NO")
        self._finish_preparation_console("forge-avb-topology", MissionState.SUCCEEDED)
        receipt_digest = _object_digest(receipt)
        self._record_online_fix_success(
            ("inspect-avb-topology",),
            receipt_digest,
            "Typed AVB inspection completed and its exact topology receipt was verified.",
            f"projects/{self.project.project_id}/{AvbEvidenceService.RECEIPT_NAME}",
            "romverse.avb-topology",
        )
        if self.autopilot_active and self.autopilot_waiting_for == "avb":
            self.autopilot_completed.append("AVB topology")
            self.autopilot_waiting_for = ""
            QTimer.singleShot(0, self._continue_autopilot)

    @Slot(str)
    def _avb_failed(self, message: str) -> None:
        self.avb_worker = None
        self.process_progress.stop()
        self.avb_button.setEnabled(True)
        self.avb_button.setText("Inspect AVB topology")
        self.metadata_button.setEnabled(True)
        self.build_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.signing_button.setEnabled(True)
        self.status.setText(message)
        self._finish_preparation_console("forge-avb-topology", MissionState.FAILED)
        if self.autopilot_active and self.autopilot_waiting_for == "avb":
            self._finish_autopilot(f"AVB inspection stopped safely: {message}")
        else:
            QMessageBox.warning(self, "AVB inspection stopped safely", message)
        self._source_online_guidance(message, "avb", tool_name="AVBTool")

    def _source_online_guidance(
        self,
        message: str,
        category: str,
        *,
        tool_name: str = "",
    ) -> None:
        """Research a failure off-thread; remote text is never executed."""

        if self.online_worker is not None or not message.strip():
            return
        settings = getattr(self.studio, "app_settings", None)
        if settings is not None and not settings.online_intelligence_enabled:
            self.status.setText(
                f"{message}  •  Online intelligence is disabled in ROMVERSE Settings."
            )
            return
        device = next(iter(self.studio.devices), None)
        try:
            blueprint = FirmwareSourceIntelligenceService(
                self.studio.store,
                self.studio.tool_statuses,
                SubprocessRunner(),
            ).load(self.project.project_id)
        except (OSError, ProjectError, ValueError):
            blueprint = None
        verified_tool_name, verified_tool_version = self._verified_tool_evidence(tool_name)
        fingerprint = ErrorFingerprint.create(
            message,
            category=category,
            manufacturer=device.manufacturer if device is not None else "",
            model=device.model if device is not None else "",
            marketing_name=device.marketing_name if device is not None else "",
            codename=device.codename
            if device is not None
            else str(getattr(blueprint, "codename", "")),
            build_id=device.rom_display if device is not None else "",
            source_kind=str(getattr(blueprint, "source_kind", "")),
            tool_name=verified_tool_name,
            tool_version=verified_tool_version,
        )
        self.status.setText(
            f"{message}  •  ROMVERSE Intelligence is checking verified online sources …"
        )
        console = self._live_console_store()
        if console is not None:
            try:
                event = console.start(
                    source="ROMVERSE Intelligence",
                    stage="online-remediation",
                    title="Research verified repair evidence",
                    summary=f"Online diagnosis started for a bounded {category} fingerprint.",
                    explanation=(
                        "ROMVERSE is checking official, maintainer, and optional community "
                        "sources. Remote instructions have no execution authority."
                        + (
                            f" The fingerprint is bound to verified {verified_tool_name} "
                            f"{verified_tool_version or '(version unconfirmed)'}."
                            if verified_tool_name
                            else " No exact tool identity was available, so tool scope remains unconfirmed."
                        )
                    ),
                    next_action="Wait for source, freshness, scope, and confidence checks.",
                    project_id=self.project.project_id,
                    confidence=MissionConfidence.UNCONFIRMED,
                    guardian_protected=True,
                )
                self.online_mission_id = event.mission_id
            except LiveConsoleStoreError:
                self.online_mission_id = ""
        self.online_worker = OnlineRemediationWorker(
            OnlineRemediationService.connected(
                self.studio.store.workspace,
                include_community=(settings is None or settings.community_research_enabled),
            ),
            fingerprint,
        )
        self.online_worker.signals.complete.connect(self._online_guidance_complete)
        self.online_worker.signals.failed.connect(self._online_guidance_failed)
        start_background(self.online_worker)

    def _verified_tool_evidence(self, requested_name: str) -> tuple[str, str]:
        """Return current runtime tool evidence or keep the fingerprint explicitly unbound."""

        name = requested_name.strip()
        if not name:
            return "", ""
        status = next(
            (
                item
                for item in self.studio.tool_statuses
                if item.name == name and item.available and item.path
            ),
            None,
        )
        if status is None:
            return "", ""
        version = status.version.strip()
        if version.casefold() in {"unknown", "available"}:
            version = ""
        return status.name, version

    @Slot(object)
    def _online_guidance_complete(self, result: object) -> None:
        self.online_worker = None
        if not isinstance(result, OnlineFixReceipt):
            self._online_guidance_failed("Online remediation returned an invalid receipt")
            return
        self.online_receipt = result
        if not result.candidates:
            self.status.setText(result.diagnosis)
            self.status.setToolTip(
                "The exact failure fingerprint was cached. ROMVERSE did not invent a fix or weaken Guardian policy."
            )
            self._finish_online_console(
                MissionState.ATTENTION,
                result.diagnosis,
                "No source met the exact relevance boundary, so ROMVERSE kept the issue unconfirmed.",
                "Retry later or add exact firmware/device evidence; Guardian policy is unchanged.",
                MissionConfidence.UNCONFIRMED,
                result,
            )
            return
        top = result.candidates[0]
        verification = (
            "validated typed repair available"
            if top.confirmed_working and top.local_action_id
            else "guidance found; local verification required"
        )
        self.status.setText(
            f"Online intelligence  •  {top.authority.value.upper()}  •  "
            f"{top.confidence}% confidence  •  freshness {top.freshness.value}  •  "
            f"{verification}"
        )
        published = top.published_at or "Not supplied by the source"
        authorities = (
            ", ".join(authority.value for authority in top.corroborating_authorities)
            or top.authority.value
        )
        detail = [
            result.diagnosis,
            "",
            "Best matching evidence:",
            f"{top.title} ({top.authority.value})",
            top.summary,
            top.url,
            "",
            f"FRESHNESS: {top.freshness.value} (source date: {published})",
            (
                f"CORROBORATION: {top.corroboration_count} independent source(s); "
                f"authorities: {authorities}"
            ),
            f"SCOPE: {top.scope_match}",
            f"CONFIDENCE: {top.confidence}% — {top.confidence_reason}",
            "",
            "Remote instructions were not executed. Guardian policy is unchanged.",
        ]
        tooltip = "\n".join(detail)
        self.status.setToolTip(tooltip)
        self.overall_badge.setToolTip(tooltip)
        for row in self.gate_rows.values():
            existing = row.toolTip()
            row.setToolTip(f"{existing}\n\nONLINE INTELLIGENCE\n{tooltip}")
        self._finish_online_console(
            MissionState.SUCCEEDED,
            f"Research completed with {len(result.candidates)} source-attributed candidate(s).",
            (
                "The highest-ranked evidence was locally verified through a typed action."
                if top.confirmed_working
                else "Evidence was found, but local typed verification is still required."
            ),
            (
                "Review the verified typed repair receipt."
                if top.confirmed_working
                else "Continue only through a matching built-in typed action."
            ),
            MissionConfidence.VERIFIED if top.confirmed_working else MissionConfidence.MEDIUM,
            result,
        )

    @Slot(str)
    def _online_guidance_failed(self, message: str) -> None:
        self.online_worker = None
        self.status.setText(
            "Online intelligence is temporarily unavailable; the local error evidence was preserved. "
            + message
        )
        self._finish_online_console(
            MissionState.FAILED,
            "Online diagnosis could not complete.",
            "The local error evidence was preserved and no remote instruction was executed.",
            "Retry when connectivity returns or continue with deterministic local evidence.",
            MissionConfidence.UNCONFIRMED,
        )

    def _live_console_store(self) -> LiveConsoleEventStore | None:
        store = getattr(self.studio, "live_console_store", None)
        return store if isinstance(store, LiveConsoleEventStore) else None

    def _start_preparation_console(self, stage: str) -> None:
        store = self._live_console_store()
        if store is None:
            return
        title = self._preparation_console_title(stage)
        try:
            event = store.start(
                source="Forge Control",
                stage=stage,
                title=title,
                summary=f"{title} started from the guided readiness flow.",
                explanation=(
                    "The producing worker is performing bounded local or read-only evidence work. "
                    "No flash, wipe, unlock, root, or bootloader relock authority is granted."
                ),
                next_action="Wait for measured progress and a producer-confirmed terminal result.",
                project_id=self.project.project_id,
                confidence=MissionConfidence.NOT_APPLICABLE,
                guardian_protected=True,
            )
        except LiveConsoleStoreError:
            return
        self.preparation_missions[stage] = event.mission_id

    def _progress_preparation_console(self, stage: str, value: int) -> None:
        store = self._live_console_store()
        mission_id = self.preparation_missions.get(stage)
        if store is None or mission_id is None:
            return
        try:
            store.progress(
                mission_id,
                value,
                summary="The Forge Control worker reported measured progress.",
                next_action="Keep ROMVERSE open until its strict evidence receipt is committed.",
            )
        except LiveConsoleStoreError:
            return

    def _finish_preparation_console(self, stage: str, state: MissionState) -> None:
        store = self._live_console_store()
        mission_id = self.preparation_missions.pop(stage, None)
        if store is None or mission_id is None:
            return
        title = self._preparation_console_title(stage)
        succeeded = state is MissionState.SUCCEEDED
        try:
            store.finish(
                mission_id,
                state,
                summary=(
                    f"{title} completed with committed evidence."
                    if succeeded
                    else f"{title} stopped without a success receipt."
                ),
                explanation=(
                    "The producing service reported success; completion was not inferred from time or progress."
                    if succeeded
                    else "The detailed local card retains the cause. The shared console excludes private paths, identifiers, and raw failure text."
                ),
                next_action=(
                    "ROMVERSE will reassess readiness and continue every remaining safe step."
                    if succeeded
                    else "Review the local card, resolve the stated cause, and retry safely."
                ),
                confidence=MissionConfidence.VERIFIED,
            )
        except LiveConsoleStoreError:
            return

    @staticmethod
    def _preparation_console_title(stage: str) -> str:
        return {
            "forge-phone-media-backup": "Create guided local phone backup",
            "forge-external-backup": "Verify selected external backup",
            "forge-recovery-evidence": "Revalidate preserved recovery evidence",
            "forge-source-blueprint": "Compile source-bound firmware blueprint",
            "forge-build-inputs": "Prepare exact rebuild metadata",
            "forge-local-candidate": "Build and verify local ROM candidate",
            "forge-avb-topology": "Inspect exact AVB topology",
            "offline-signing-export": "Export offline signing request",
            "offline-signing-import": "Verify offline signed artifact bundle",
        }.get(stage, "Resolve Forge readiness evidence")

    def _finish_online_console(
        self,
        state: MissionState,
        summary: str,
        explanation: str,
        next_action: str,
        confidence: MissionConfidence,
        receipt: OnlineFixReceipt | None = None,
    ) -> None:
        if not self.online_mission_id:
            return
        store = self._live_console_store()
        mission_id = self.online_mission_id
        self.online_mission_id = ""
        if store is None:
            return
        evidence_refs = (
            ((f"knowledge/online-remediation/{receipt.fingerprint.fingerprint_id}.romverse"),)
            if receipt is not None
            else ()
        )
        try:
            store.finish(
                mission_id,
                state,
                summary=summary,
                explanation=explanation,
                next_action=next_action,
                confidence=confidence,
                evidence_refs=evidence_refs,
            )
        except LiveConsoleStoreError:
            return

    def _record_online_fix_success(
        self,
        action_ids: tuple[str, ...],
        receipt_digest: str,
        summary: str,
        evidence_ref: str,
        evidence_format: str,
    ) -> None:
        if (
            self.online_receipt is None
            or not receipt_digest
            or not evidence_ref
            or not evidence_format
        ):
            return
        candidate = next(
            (item for item in self.online_receipt.candidates if item.local_action_id in action_ids),
            None,
        )
        if candidate is None:
            return
        try:
            outcome = OnlineRemediationService(self.studio.store.workspace).record_verified_outcome(
                self.online_receipt.fingerprint,
                candidate,
                TypedLocalActionEvidence(
                    candidate.local_action_id,
                    receipt_digest,
                    evidence_ref,
                    evidence_format,
                ),
                summary,
            )
        except (OSError, ValueError):
            return
        settings = getattr(self.studio, "app_settings", None)
        synapse_knowledge = None
        if settings is not None and settings.synapse_contributions_enabled:
            try:
                fingerprint = self.online_receipt.fingerprint
                scope = SynapseScope.create(
                    operation=fingerprint.category or candidate.local_action_id,
                    source_kind=fingerprint.source_kind,
                    device_codename=fingerprint.codename,
                    build_family=fingerprint.build_id,
                    tool_name=fingerprint.tool_name,
                    tool_version=fingerprint.tool_version,
                )
                contribution = SynapseContribution.create(
                    fingerprint_id=fingerprint.fingerprint_id,
                    solution_id=candidate.local_action_id,
                    scope=scope,
                    source_family=candidate.source_id,
                    summary=summary,
                    successful=True,
                    locally_verified=True,
                    action_receipt_digest=receipt_digest,
                    verification_evidence_digest=outcome.outcome_digest,
                )
                synapse_knowledge = SynapseStore(self.studio.store.workspace).contribute(
                    contribution
                )
            except (OSError, ValueError, SynapseStoreError):
                synapse_knowledge = None
        self.online_receipt = None
        self.status.setText(
            self.status.text() + f"  •  ONLINE FIX VERIFIED WORKING ({candidate.local_action_id})"
        )
        self.status.setToolTip(
            f"VERIFIED WORKING FIX\n{candidate.title}\n{summary}\nOutcome {outcome.outcome_digest[:16]}…\nRemote text was never executed."
        )
        console = self._live_console_store()
        if console is not None and synapse_knowledge is not None:
            with suppress(LiveConsoleStoreError):
                console.note(
                    source="ROMVERSE Synapse",
                    stage="verified-contribution",
                    title="Verified repair outcome prepared",
                    summary=(
                        "A privacy-scrubbed verified outcome was added to the local Synapse mirror."
                    ),
                    explanation=(
                        f"Knowledge state: {synapse_knowledge.state.value}; confidence "
                        f"{synapse_knowledge.confidence}%. This remains guidance-only."
                    ),
                    next_action="A production Synapse service must authenticate any later upload.",
                    state=MissionState.INFORMATION,
                    confidence=MissionConfidence.HIGH,
                    project_id=self.project.project_id,
                    evidence_refs=("knowledge/synapse-cache-v1.json",),
                    dedupe_key=f"synapse-{synapse_knowledge.knowledge_id}",
                )

    def _signing_service(self) -> OfflineSigningCeremonyService | None:
        avbtool = next(
            (
                Path(item.path)
                for item in self.studio.tool_statuses
                if item.name == "AVBTool" and item.available and item.path
            ),
            None,
        )
        if avbtool is None:
            return None
        runner = (
            self.studio.filesystem_service.runner
            if self.studio.filesystem_service is not None
            else SubprocessRunner()
        )
        return OfflineSigningCeremonyService(
            self.studio.store,
            self.studio.pack_registry,
            self.studio.tool_statuses,
            avbtool,
            runner,
        )

    def _signing_ceremony(self) -> None:
        if any(
            worker is not None
            for worker in (
                self.metadata_worker,
                self.build_worker,
                self.avb_worker,
                self.signing_worker,
            )
        ):
            return
        service = self._signing_service()
        if service is None:
            if not self.studio._resolve_required_tools(
                ("AVBTool",),
                purpose=(
                    "Offline signing requires AVBTool only for request and returned-artifact "
                    "verification. Private keys always remain outside ROMVERSE."
                ),
                title="ROMVERSE • Resolve offline-signing verifier",
                success_message="AVBTool freshly verified for the offline signing ceremony.",
                parent=self,
            ):
                self.status.setText(
                    "Offline signing remains paused until AVBTool verifies successfully."
                )
                return
            service = self._signing_service()
            if service is None:
                QMessageBox.warning(
                    self,
                    "Offline signing remains locked",
                    "AVBTool did not pass the fresh Forge Arsenal verification.",
                )
                return
        eligible, reason = service.eligibility(self.project.project_id)
        if not eligible:
            self.status.setText(reason)
            QMessageBox.information(
                self,
                "Offline signing is not authorized for this project",
                f"{reason}\n\nROMVERSE will not substitute a generic key or weaken the Device Pack policy.",
            )
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Offline signing ceremony")
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setText("Private keys stay outside ROMVERSE")
        dialog.setInformativeText(
            "Export a content-addressed request for the exact local candidate, sign it in your protected external environment, then import the resulting product.img and vbmeta_system.img. ROMVERSE verifies the authorized public-key identity, AVB algorithm, rollback fields, descriptors, size, and hashes. No phone command is available here."
        )
        export = dialog.addButton("Export request", QMessageBox.ButtonRole.ActionRole)
        import_result = dialog.addButton("Import signed bundle", QMessageBox.ButtonRole.ActionRole)
        dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.exec()
        selected = dialog.clickedButton()
        if selected not in {export, import_result}:
            return
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose external signing request destination"
            if selected is export
            else "Choose signed artifact bundle",
            str(Path.home()),
        )
        if not folder:
            return
        operation = "export" if selected is export else "import"
        self.signing_worker = OfflineSigningWorker(
            service, operation, self.project.project_id, Path(folder)
        )
        self.signing_worker.signals.complete.connect(self._signing_complete)
        self.signing_worker.signals.failed.connect(self._signing_failed)
        self.signing_button.setEnabled(False)
        self.metadata_button.setEnabled(False)
        self.build_button.setEnabled(False)
        self.avb_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.signing_button.setText("Preparing evidence, please wait …")
        self.process_progress.begin()
        self.status.setText(
            "Exporting exact signing inputs … phone changed: NO"
            if operation == "export"
            else "Hashing and verifying signed AVB artifacts … phone changed: NO"
        )
        self._start_preparation_console(f"offline-signing-{operation}")
        start_background(self.signing_worker)

    @Slot(object)
    def _signing_complete(self, result: object) -> None:
        if not isinstance(result, (OfflineSigningRequest, OfflineSigningReceipt)):
            self._signing_failed("Offline signing returned no verifiable request or receipt")
            return
        operation = self.signing_worker.operation if self.signing_worker is not None else "import"
        self.signing_worker = None
        self.process_progress.finish()
        self.signing_button.setEnabled(True)
        self.signing_button.setText("Offline signing ceremony")
        self.metadata_button.setEnabled(True)
        self.build_button.setEnabled(True)
        self.avb_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.refresh()
        if isinstance(result, OfflineSigningRequest):
            self.status.setText(
                f"Signing request exported  •  {result.request_digest[:16]}…  •  "
                f"{result.output_path}  •  private key stored: NO"
            )
        elif isinstance(result, OfflineSigningReceipt):
            self.status.setText(
                f"Signed artifacts verified  •  receipt {result.receipt_digest[:16]}…  •  "
                "phone changed: NO"
            )
        self._finish_preparation_console(f"offline-signing-{operation}", MissionState.SUCCEEDED)

    @Slot(str)
    def _signing_failed(self, message: str) -> None:
        operation = self.signing_worker.operation if self.signing_worker is not None else "import"
        self.signing_worker = None
        self.process_progress.stop()
        self.signing_button.setEnabled(True)
        self.signing_button.setText("Offline signing ceremony")
        self.metadata_button.setEnabled(True)
        self.build_button.setEnabled(True)
        self.avb_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.status.setText(message)
        self._finish_preparation_console(f"offline-signing-{operation}", MissionState.FAILED)
        QMessageBox.warning(self, "Offline signing stopped safely", message)
        self._source_online_guidance(message, "signing", tool_name="AVBTool")

    def _export_bundle(self) -> None:
        if self.report is None:
            return
        bundle = self.service.export_evidence_bundle(self.report)
        self.status.setText(
            f"Evidence bundle saved  •  {bundle.output_path}  •  "
            f"{len(bundle.artifacts)} manifest(s)  •  {bundle.evidence_digest[:16]}…"
        )

    @staticmethod
    def _stylesheet() -> str:
        return """
            QScrollArea { border: none; background: #02050A; }
            QWidget { background: #02050A; }
            QFrame#BuildPhase {
                background: #050A12; border: 1px solid #203553; border-radius: 12px;
            }
            QFrame#ResolutionBanner {
                background: #071722; border: 1px solid #24BFD2; border-radius: 12px;
            }
            QFrame#ReadyBanner {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #082219,stop:0.55 #071B22,stop:1 #17102A);
                border: 1px solid #39D99B; border-radius: 12px;
            }
            QLabel#ReadyHeading { color: #5CF0B2; font-size: 14px; font-weight: 900; letter-spacing: 1px; }
            QFrame#FlashChoiceKeep, QFrame#FlashChoiceWipe {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #14233E,stop:1 #140B28);
                border: 1px solid #3E5F92; border-radius: 12px;
            }
            QFrame#FlashChoiceWipe { border-color: #934C91; }
            QRadioButton#FlashMode {
                color: #F3F7FF; background: transparent; font-size: 15px;
                font-weight: 900; spacing: 10px;
            }
            QRadioButton#FlashMode::indicator {
                width: 18px; height: 18px; border-radius: 9px;
                border: 2px solid #617CAC; background: #070C16;
            }
            QRadioButton#FlashMode::indicator:checked {
                border-color: #62F0C2; background: #25C98F;
            }
            QLabel#BootloaderInvariant {
                color: #8AF5D0; background: #061713; border: 1px solid #27896A;
                border-radius: 10px; padding: 12px; font-weight: 900;
            }
            QFrame[gateStatus="pass"] { background: #061710; border: 1px solid #176845; border-radius: 8px; }
            QFrame[gateStatus="attention"] { background: #181405; border: 1px solid #826A1D; border-radius: 8px; }
            QFrame[gateStatus="blocked"] { background: #1B080F; border: 1px solid #7C2742; border-radius: 8px; }
            QLabel#GateCopy { color: #DCE8FA; font-size: 13px; background: transparent; }
            QLabel#GateSymbol { color: #5CEBB0; font-size: 20px; font-weight: 900; background: transparent; }
            QLabel#GateBadge { color: #9EDFF5; font-weight: 900; font-size: 11px; background: transparent; }
            QPushButton#GateResolve {
                color: #DDF7FF; background: #0B2431; border: 1px solid #2CC8DB;
                border-radius: 7px; padding: 7px 11px; font-weight: 700;
            }
            QPushButton#GateResolve:hover { background: #12394A; border-color: #62EBF6; }
        """


def _object_digest(value: object) -> str:
    if is_dataclass(value) and not isinstance(value, type):
        payload = asdict(value)
    else:
        payload = {"type": type(value).__name__, "value": str(value)}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _human_bytes(value: int) -> str:
    size = float(max(0, value))
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def _display_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    except (TypeError, ValueError):
        return "invalid time"
