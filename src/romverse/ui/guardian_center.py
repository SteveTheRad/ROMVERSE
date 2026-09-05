from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from romverse.applications.receipts import ApkReceiptRead, ApkReceiptStore
from romverse.backup.plans import BackupPlanRead, GuardianBackupPlanStore
from romverse.core.settings import ExperienceMode
from romverse.device.models import AndroidDevice
from romverse.guardian.approval import ApprovalRecord, ApprovalStore, ApprovalVerification
from romverse.guardian.audit import AuditVerification, GuardianAuditStore
from romverse.guardian.execution_gateway_contract import (
    GuardianExecutionGatewayContract,
    execution_plan_matches_manifest,
    gateway_contract_matches_plan,
)
from romverse.guardian.execution_plan import GuardianExecutionPlan
from romverse.guardian.manifest_review import GuardianManifestReview
from romverse.guardian.recovery_live_target import (
    GuardianRecoveryLiveTargetReceipt,
    GuardianRecoveryLiveTargetReceiptService,
    RecoveryLiveTargetValidationError,
)
from romverse.guardian.recovery_preparation import (
    GuardianRecoveryPreparation,
    GuardianRecoveryPreparationError,
    GuardianRecoveryPreparationService,
)
from romverse.guardian.runtime_package import (
    VerifiedGuardianRuntimePackage,
    current_guardian_runtime_platform,
    load_guardian_runtime_package,
    load_guardian_runtime_public_key,
    verify_guardian_runtime_package,
)
from romverse.nexus.planning import NexusObjective, NexusPlan
from romverse.repair.autopilot import RecoveryIncident, RecoveryRoute
from romverse.ui.background import ManagedRunnable, start_background
from romverse.ui.process_progress import ProcessProgressBar


@dataclass(frozen=True, slots=True)
class GuardianCenterSnapshot:
    verification: AuditVerification
    approval_verification: ApprovalVerification
    records: tuple[dict, ...]
    approvals: tuple[ApprovalRecord, ...]
    preflight: ApkReceiptRead
    preflight_exists: bool
    preflight_history_count: int
    install: ApkReceiptRead
    install_exists: bool
    install_history_count: int
    backup_plan: BackupPlanRead
    backup_plan_exists: bool
    backup_history_count: int


class GuardianCenterSignals(QObject):
    complete = Signal(object)
    failed = Signal(str)


class GuardianCenterWorker(ManagedRunnable):
    """Read and verify Guardian history away from the UI thread."""

    def __init__(self, audit: GuardianAuditStore) -> None:
        super().__init__()
        self.audit = audit
        self.signals = GuardianCenterSignals()

    @Slot()
    def execute(self) -> None:
        try:
            verification = self.audit.verify()
            workspace = self.audit.path.parent.parent
            approvals = ApprovalStore(workspace)
            approval_verification = approvals.verify()
            receipts = ApkReceiptStore(workspace)
            plans = GuardianBackupPlanStore(workspace)
            snapshot = GuardianCenterSnapshot(
                verification,
                approval_verification,
                self.audit.read_recent(50) if verification.valid else (),
                approvals.read_recent(10),
                receipts.load_latest_preflight(),
                receipts.latest_preflight_path.exists(),
                receipts.history_count("apk-preflight"),
                receipts.load_latest_install(),
                receipts.latest_install_path.exists(),
                receipts.history_count("apk-install"),
                plans.load_latest(),
                plans.latest_path.exists(),
                plans.history_count(),
            )
            with suppress(RuntimeError):
                self.signals.complete.emit(snapshot)
        except Exception as exc:
            with suppress(RuntimeError):
                self.signals.failed.emit(f"{type(exc).__name__}: {exc}")


class GuardianRuntimePackageSignals(QObject):
    complete = Signal(object)
    failed = Signal(str)


class GuardianRuntimePackageWorker(ManagedRunnable):
    """Inspect one local runtime candidate without launching or enrolling it."""

    def __init__(
        self,
        envelope_path: Path,
        release_public_key_path: Path,
        expected_release_key_id: str,
        expected_platform: str,
    ) -> None:
        super().__init__()
        self.envelope_path = envelope_path
        self.release_public_key_path = release_public_key_path
        self.expected_release_key_id = expected_release_key_id
        self.expected_platform = expected_platform
        self.signals = GuardianRuntimePackageSignals()

    @Slot()
    def execute(self) -> None:
        try:
            result = verify_guardian_runtime_package(
                envelope=load_guardian_runtime_package(self.envelope_path),
                release_public_key=load_guardian_runtime_public_key(self.release_public_key_path),
                expected_release_key_id=self.expected_release_key_id,
                package_directory=self.envelope_path.parent,
                expected_platform=self.expected_platform,
            )
            with suppress(RuntimeError):
                self.signals.complete.emit(result)
        except Exception as exc:
            with suppress(RuntimeError):
                self.signals.failed.emit(f"{type(exc).__name__}: {exc}")


class RecoveryLiveTargetSignals(QObject):
    complete = Signal(int, str, object)
    failed = Signal(int, str, str)


class RecoveryLiveTargetWorker(ManagedRunnable):
    """Run one bounded read-only Recovery target check off the UI thread."""

    def __init__(
        self,
        service: GuardianRecoveryLiveTargetReceiptService,
        preparation: GuardianRecoveryPreparation,
        device: AndroidDevice,
        attempt_number: int,
    ) -> None:
        super().__init__()
        self.service = service
        self.preparation = preparation
        self.device = device
        self.attempt_number = attempt_number
        self.signals = RecoveryLiveTargetSignals()

    @Slot()
    def execute(self) -> None:
        try:
            result = self.service.observe(self.preparation, self.device)
            with suppress(RuntimeError):
                self.signals.complete.emit(
                    self.attempt_number,
                    self.preparation.preparation_digest,
                    result,
                )
        except Exception as exc:
            with suppress(RuntimeError):
                self.signals.failed.emit(
                    self.attempt_number,
                    self.preparation.preparation_digest,
                    f"{type(exc).__name__}: {exc}",
                )


class GuardianCenter(QWidget):
    nexus_requested = Signal(str, str)
    time_machine_requested = Signal(str, str)
    rom_studio_requested = Signal(str, str)
    recovery_requested = Signal(str, str)
    recovery_home_requested = Signal()
    toolchain_requested = Signal()
    dashboard_state_changed = Signal(str, str, bool)
    REFRESH_DEBOUNCE_MS = 250

    def __init__(self, audit: GuardianAuditStore | None, *, auto_start: bool = True) -> None:
        super().__init__()
        self.audit = audit
        self.worker: GuardianCenterWorker | None = None
        self.runtime_worker: GuardianRuntimePackageWorker | None = None
        self.recovery_target_worker: RecoveryLiveTargetWorker | None = None
        self._experience_mode = ExperienceMode.GUIDED
        self._nexus_review_identity: tuple[str, str] | None = None
        self._backup_review_identity: tuple[str, str] | None = None
        self._studio_review_identity: tuple[str, str] | None = None
        self._recovery_review_identity: tuple[str, str] | None = None
        self._recovery_preparation_digest = ""
        self._recovery_preparation: GuardianRecoveryPreparation | None = None
        self._recovery_live_target_service: GuardianRecoveryLiveTargetReceiptService | None = None
        self._recovery_reviewed_device: AndroidDevice | None = None
        self._recovery_live_target_receipt: GuardianRecoveryLiveTargetReceipt | None = None
        self._recovery_target_generation = 0
        self._recovery_technical_text = ""
        self._recovery_details_expanded = False
        self._recovery_target_expiry_timer = QTimer(self)
        self._recovery_target_expiry_timer.setSingleShot(True)
        self._recovery_target_expiry_timer.timeout.connect(self._expire_recovery_target_receipt)
        self._dashboard_state = (
            "unverified",
            "Guardian's current audit and approval evidence has not yet been verified in this session.",
            False,
        )
        self._verified_dashboard_revision: object | None = None
        self._refresh_pending = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(self.REFRESH_DEBOUNCE_MS)
        self._refresh_timer.timeout.connect(self.refresh)
        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 30)
        page.setSpacing(18)

        header = QHBoxLayout()
        text = QVBoxLayout()
        eyebrow = QLabel("GUARDIAN CORE  •  POLICY BEFORE EXECUTION")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("Guardian Core")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Inspect ROMVERSE's safety decisions and verify the local tamper-evident operation trail."
        )
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        text.addWidget(eyebrow)
        text.addWidget(title)
        text.addWidget(subtitle)
        header.addLayout(text, 1)
        self.refresh_button = QPushButton("Verify audit trail")
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button)
        page.addLayout(header)

        self.dashboard_handoff = QFrame()
        self.dashboard_handoff.setObjectName("DiagnosticHandoffBar")
        dashboard_layout = QHBoxLayout(self.dashboard_handoff)
        dashboard_layout.setContentsMargins(18, 13, 18, 13)
        dashboard_layout.setSpacing(14)
        dashboard_copy = QVBoxLayout()
        self.dashboard_handoff_eyebrow = QLabel(
            "COMMAND DECK HANDOFF  •  CURRENT GUARDIAN EVIDENCE"
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
        dashboard_copy.addWidget(self.dashboard_handoff_eyebrow)
        dashboard_copy.addWidget(self.dashboard_handoff_title)
        dashboard_copy.addWidget(self.dashboard_handoff_detail)
        dashboard_layout.addLayout(dashboard_copy, 1)
        self.dashboard_handoff_badge = QLabel()
        dashboard_layout.addWidget(self.dashboard_handoff_badge)
        self.dashboard_handoff.setVisible(False)
        page.addWidget(self.dashboard_handoff)

        self.recovery_review = QFrame()
        self.recovery_review.setObjectName("RecoveryReviewCard")
        recovery_layout = QVBoxLayout(self.recovery_review)
        recovery_layout.setContentsMargins(20, 16, 20, 16)
        recovery_layout.setSpacing(8)
        recovery_header = QHBoxLayout()
        self.recovery_review_eyebrow = QLabel("RECOVERY AUTOPILOT HANDOFF  •  CONTEXT ONLY")
        self.recovery_review_eyebrow.setObjectName("Eyebrow")
        recovery_header.addWidget(self.recovery_review_eyebrow, 1)
        self.recovery_review_badge = QLabel("ADVISORY • ZERO AUTHORITY")
        self.recovery_review_badge.setObjectName("Warning")
        recovery_header.addWidget(self.recovery_review_badge)
        self.recovery_return_button = QPushButton("Return to Recovery incident")
        self.recovery_return_button.clicked.connect(self._return_to_recovery)
        recovery_header.addWidget(self.recovery_return_button)
        recovery_layout.addLayout(recovery_header)
        self.recovery_review_title = QLabel()
        self.recovery_review_title.setObjectName("SectionTitle")
        self.recovery_review_title.setTextFormat(Qt.TextFormat.PlainText)
        recovery_layout.addWidget(self.recovery_review_title)
        self.recovery_review_detail = QLabel()
        self.recovery_review_detail.setObjectName("Muted")
        self.recovery_review_detail.setTextFormat(Qt.TextFormat.PlainText)
        self.recovery_review_detail.setWordWrap(True)
        self.recovery_review_detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        recovery_layout.addWidget(self.recovery_review_detail)
        self.recovery_technical_button = QPushButton("View technical details")
        self.recovery_technical_button.setAccessibleName(
            "Show technical evidence for this Recovery plan"
        )
        self.recovery_technical_button.clicked.connect(self._toggle_recovery_details)
        recovery_layout.addWidget(self.recovery_technical_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.recovery_technical_detail = QLabel()
        self.recovery_technical_detail.setObjectName("EvidencePanel")
        self.recovery_technical_detail.setTextFormat(Qt.TextFormat.PlainText)
        self.recovery_technical_detail.setWordWrap(True)
        self.recovery_technical_detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.recovery_technical_scroll = QScrollArea()
        self.recovery_technical_scroll.setObjectName("RecoveryTechnicalScroll")
        self.recovery_technical_scroll.setAccessibleName(
            "Scrollable technical evidence for this Recovery plan"
        )
        self.recovery_technical_scroll.setWidgetResizable(True)
        self.recovery_technical_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.recovery_technical_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.recovery_technical_scroll.setMaximumHeight(300)
        self.recovery_technical_scroll.setWidget(self.recovery_technical_detail)
        self.recovery_technical_scroll.setVisible(False)
        recovery_layout.addWidget(self.recovery_technical_scroll)
        recovery_target_row = QHBoxLayout()
        self.recovery_target_status = QLabel()
        self.recovery_target_status.setObjectName("Muted")
        self.recovery_target_status.setTextFormat(Qt.TextFormat.PlainText)
        self.recovery_target_status.setWordWrap(True)
        self.recovery_target_status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        recovery_target_row.addWidget(self.recovery_target_status, 1)
        self.recovery_target_button = QPushButton("Check exact phone now")
        self.recovery_target_button.setObjectName("Primary")
        self.recovery_target_button.setAccessibleName(
            "Run the read-only exact-phone check for this Recovery preparation"
        )
        self.recovery_target_button.setToolTip(
            "Uses only USB discovery and allowlisted Fastboot identity reads. It cannot flash, "
            "reboot, wipe, unlock, relock, approve, or run Recovery."
        )
        self.recovery_target_button.clicked.connect(self._start_recovery_target_check)
        recovery_target_row.addWidget(self.recovery_target_button)
        recovery_layout.addLayout(recovery_target_row)
        self.recovery_review.setVisible(False)
        page.addWidget(self.recovery_review)
        self.recovery_focus_spacer = QWidget()
        self.recovery_focus_spacer.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )
        self.recovery_focus_spacer.setVisible(False)
        page.addWidget(self.recovery_focus_spacer, 1)

        self.nexus_review = QFrame()
        self.nexus_review.setObjectName("NexusReviewCard")
        review_layout = QVBoxLayout(self.nexus_review)
        review_layout.setContentsMargins(20, 16, 20, 16)
        review_layout.setSpacing(8)
        review_header = QHBoxLayout()
        self.nexus_review_eyebrow = QLabel("NEXUS PLAN REVIEW  •  CONTEXT ONLY")
        self.nexus_review_eyebrow.setObjectName("Eyebrow")
        review_header.addWidget(self.nexus_review_eyebrow, 1)
        self.nexus_review_badge = QLabel("ZERO AUTHORITY")
        self.nexus_review_badge.setObjectName("Warning")
        review_header.addWidget(self.nexus_review_badge)
        self.nexus_return_button = QPushButton("Return to Nexus Plan")
        self.nexus_return_button.clicked.connect(self._return_to_nexus)
        review_header.addWidget(self.nexus_return_button)
        review_layout.addLayout(review_header)
        self.nexus_review_title = QLabel()
        self.nexus_review_title.setObjectName("SectionTitle")
        review_layout.addWidget(self.nexus_review_title)
        self.nexus_review_detail = QLabel()
        self.nexus_review_detail.setObjectName("Muted")
        self.nexus_review_detail.setWordWrap(True)
        self.nexus_review_detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        review_layout.addWidget(self.nexus_review_detail)
        self.nexus_review.setVisible(False)
        page.addWidget(self.nexus_review)

        self.backup_review = QFrame()
        self.backup_review.setObjectName("BackupReviewCard")
        backup_layout = QVBoxLayout(self.backup_review)
        backup_layout.setContentsMargins(20, 16, 20, 16)
        backup_layout.setSpacing(8)
        backup_header = QHBoxLayout()
        self.backup_review_eyebrow = QLabel("TIME MACHINE PLAN REVIEW  •  EVIDENCE ONLY")
        self.backup_review_eyebrow.setObjectName("Eyebrow")
        backup_header.addWidget(self.backup_review_eyebrow, 1)
        self.backup_review_badge = QLabel("ZERO AUTHORITY")
        self.backup_review_badge.setObjectName("Warning")
        backup_header.addWidget(self.backup_review_badge)
        self.backup_return_button = QPushButton("Return to Time Machine")
        self.backup_return_button.clicked.connect(self._return_to_time_machine)
        backup_header.addWidget(self.backup_return_button)
        backup_layout.addLayout(backup_header)
        self.backup_review_title = QLabel()
        self.backup_review_title.setObjectName("SectionTitle")
        backup_layout.addWidget(self.backup_review_title)
        self.backup_review_detail = QLabel()
        self.backup_review_detail.setObjectName("Muted")
        self.backup_review_detail.setWordWrap(True)
        self.backup_review_detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        backup_layout.addWidget(self.backup_review_detail)
        self.backup_review.setVisible(False)
        page.addWidget(self.backup_review)

        self.studio_review = QFrame()
        self.studio_review.setObjectName("StudioReviewCard")
        studio_layout = QVBoxLayout(self.studio_review)
        studio_layout.setContentsMargins(20, 16, 20, 16)
        studio_layout.setSpacing(8)
        studio_header = QHBoxLayout()
        self.studio_review_eyebrow = QLabel("ROM STUDIO MANIFEST REVIEW  •  COMMAND-FREE EVIDENCE")
        self.studio_review_eyebrow.setObjectName("Eyebrow")
        studio_header.addWidget(self.studio_review_eyebrow, 1)
        self.studio_review_badge = QLabel("ZERO AUTHORITY")
        self.studio_review_badge.setObjectName("Warning")
        studio_header.addWidget(self.studio_review_badge)
        self.studio_return_button = QPushButton("Return to exact ROM project")
        self.studio_return_button.clicked.connect(self._return_to_rom_studio)
        studio_header.addWidget(self.studio_return_button)
        studio_layout.addLayout(studio_header)
        self.studio_review_title = QLabel()
        self.studio_review_title.setObjectName("SectionTitle")
        studio_layout.addWidget(self.studio_review_title)
        self.studio_review_detail = QLabel()
        self.studio_review_detail.setObjectName("Muted")
        self.studio_review_detail.setWordWrap(True)
        self.studio_review_detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        studio_layout.addWidget(self.studio_review_detail)
        self.studio_review.setVisible(False)
        page.addWidget(self.studio_review)

        self.hero = QFrame()
        self.hero.setObjectName("HeroCard")
        hero_layout = QHBoxLayout(self.hero)
        hero_layout.setContentsMargins(24, 20, 24, 20)
        state = QVBoxLayout()
        self.policy_title = QLabel("Read-only enforcement active")
        self.policy_title.setObjectName("HeroTitle")
        self.integrity_detail = QLabel()
        self.integrity_detail.setObjectName("Muted")
        state.addWidget(self.policy_title)
        state.addWidget(self.integrity_detail)
        hero_layout.addLayout(state, 1)
        self.integrity_badge = QLabel()
        hero_layout.addWidget(self.integrity_badge)
        page.addWidget(self.hero)
        self.progress = ProcessProgressBar()
        self.progress.setAccessibleName("Guardian evidence verification progress")
        self.progress.setToolTip(
            "Guardian is verifying bounded audit, approval, APK, and recovery evidence off the interface thread."
        )
        page.addWidget(self.progress)

        self.runtime_package_card = QFrame()
        self.runtime_package_card.setObjectName("Card")
        runtime_layout = QHBoxLayout(self.runtime_package_card)
        runtime_layout.setContentsMargins(20, 15, 20, 15)
        runtime_layout.setSpacing(14)
        runtime_copy = QVBoxLayout()
        runtime_eyebrow = QLabel("GUARDIAN RUNTIME  •  LOCAL CANDIDATE INSPECTOR")
        runtime_eyebrow.setObjectName("Eyebrow")
        self.runtime_package_title = QLabel("No runtime package inspected")
        self.runtime_package_title.setObjectName("SectionTitle")
        self.runtime_package_detail = QLabel(
            "Check a separately supplied signed runtime package and its release public key. "
            "Inspection never launches the file, enrolls trust, opens a phone, or unlocks final consent."
        )
        self.runtime_package_detail.setObjectName("Muted")
        self.runtime_package_detail.setWordWrap(True)
        self.runtime_package_detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        runtime_copy.addWidget(runtime_eyebrow)
        runtime_copy.addWidget(self.runtime_package_title)
        runtime_copy.addWidget(self.runtime_package_detail)
        self.runtime_package_progress = ProcessProgressBar()
        self.runtime_package_progress.setAccessibleName(
            "Guardian runtime package verification progress"
        )
        runtime_copy.addWidget(self.runtime_package_progress)
        runtime_layout.addLayout(runtime_copy, 1)
        runtime_actions = QVBoxLayout()
        self.runtime_package_badge = QLabel("NOT INSPECTED")
        self.runtime_package_badge.setObjectName("Warning")
        self.inspect_runtime_package_button = QPushButton("Inspect runtime candidate")
        self.inspect_runtime_package_button.setAccessibleName(
            "Inspect a signed Guardian runtime package candidate"
        )
        self.inspect_runtime_package_button.clicked.connect(self._choose_runtime_package)
        runtime_actions.addWidget(self.runtime_package_badge, 0, Qt.AlignmentFlag.AlignRight)
        runtime_actions.addWidget(self.inspect_runtime_package_button)
        runtime_actions.addStretch()
        runtime_layout.addLayout(runtime_actions)
        page.addWidget(self.runtime_package_card)

        metrics = QHBoxLayout()
        self.total_card, self.total_value = self._metric("AUDITED OPERATIONS")
        self.allowed_card, self.allowed_value = self._metric("RECENT ALLOWED")
        self.denied_card, self.denied_value = self._metric("RECENT DENIED")
        self.approval_card, self.approval_value = self._metric("APPROVALS ISSUED")
        metrics.addWidget(self.total_card, 1)
        metrics.addWidget(self.allowed_card, 1)
        metrics.addWidget(self.denied_card, 1)
        metrics.addWidget(self.approval_card, 1)
        page.addLayout(metrics)

        self.recent_title = QLabel("Recent Guardian decisions")
        self.recent_title.setObjectName("SectionTitle")
        page.addWidget(self.recent_title)
        self.body = QScrollArea()
        self.body.setWidgetResizable(True)
        self.body_content = QWidget()
        self.body_content.setObjectName("ScrollContent")
        self.body_layout = QVBoxLayout(self.body_content)
        self.body_layout.setContentsMargins(0, 0, 6, 0)
        self.body_layout.setSpacing(10)
        self.body.setWidget(self.body_content)
        page.addWidget(self.body, 1)

        self.boundary = QLabel(
            "Guardian records operation metadata and outcomes only. Device serials, stdout, and stderr are excluded. "
            "A failed integrity check blocks subsequent execution through this gateway."
        )
        self.boundary.setObjectName("Muted")
        self.boundary.setWordWrap(True)
        page.addWidget(self.boundary)
        if auto_start:
            self.refresh()
        else:
            self._refresh_pending = True
            self._empty(
                "No Guardian decisions have been verified for this view yet. Choose Verify audit "
                "trail to check the current local evidence; verification starts no phone action."
            )

    def current_dashboard_state(self) -> tuple[str, str, bool]:
        """Return the latest bounded Guardian summary owned by this page."""

        return self._dashboard_state

    def _set_recovery_focus(self, active: bool) -> None:
        """Fold unrelated Guardian dashboard surfaces during one Recovery handoff."""

        visible = not active
        self.refresh_button.setVisible(visible)
        self.hero.setVisible(visible)
        self.progress.setVisible(visible)
        self.runtime_package_card.setVisible(visible)
        self.total_card.setVisible(visible)
        self.allowed_card.setVisible(visible)
        self.denied_card.setVisible(visible)
        self.approval_card.setVisible(visible)
        self.recent_title.setVisible(visible)
        self.body.setVisible(visible)
        self.boundary.setVisible(visible)
        self.recovery_focus_spacer.setVisible(active)

    def open_dashboard_intent(self, action: str) -> bool:
        """Present the exact Guardian state claimed by Command Deck without authorizing work."""

        if str(action).strip() != "Guardian":
            return False
        self.dashboard_handoff.setVisible(True)
        self._render_dashboard_handoff()
        return True

    def invalidate_dashboard_if_evidence_changed(self) -> bool:
        """Retire a verified Command Deck claim after any audit/approval file revision."""

        if self._dashboard_state[0] != "verified" or self.audit is None:
            return False
        if self._verified_dashboard_revision == self._dashboard_evidence_revision():
            return False
        self._publish_dashboard_state(
            "review_due",
            "Guardian audit or approval evidence changed after the last verification and must be checked again.",
            False,
        )
        return True

    def _dashboard_evidence_revision(self) -> object:
        if self.audit is None:
            return None
        workspace = self.audit.path.parent.parent
        approval_path = ApprovalStore(workspace).path
        try:
            approval_stat = approval_path.lstat()
            approval_revision: object = (
                approval_stat.st_mode,
                approval_stat.st_dev,
                approval_stat.st_ino,
                approval_stat.st_size,
                approval_stat.st_mtime_ns,
                approval_stat.st_ctime_ns,
            )
        except FileNotFoundError:
            approval_revision = None
        except OSError:
            approval_revision = "unreadable"
        return self.audit.evidence_revision(), approval_revision

    def _publish_dashboard_state(self, state: str, detail: str, verified: bool) -> None:
        bounded_detail = " ".join(str(detail).replace("\x00", " ").split())[:360]
        value = (state, bounded_detail, bool(verified))
        if value == self._dashboard_state:
            return
        self._dashboard_state = value
        if not verified:
            self._verified_dashboard_revision = None
        if not self.dashboard_handoff.isHidden():
            self._render_dashboard_handoff()
        self.dashboard_state_changed.emit(*value)

    def _render_dashboard_handoff(self) -> None:
        state, detail, verified = self._dashboard_state
        titles = {
            "unverified": "Guardian evidence has not been verified yet",
            "review_due": "Guardian evidence needs re-verification",
            "verifying": "Guardian is verifying current evidence",
            "verified": "Guardian integrity is current",
            "locked": "Guardian execution is locked",
            "failed": "Guardian verification stopped safely",
            "unavailable": "Guardian audit is unavailable",
        }
        badges = {
            "unverified": "VERIFY REQUIRED",
            "review_due": "REVERIFY REQUIRED",
            "verifying": "VERIFYING",
            "verified": "INTEGRITY VERIFIED",
            "locked": "EXECUTION LOCKED",
            "failed": "VERIFY FAILED",
            "unavailable": "AUDIT UNAVAILABLE",
        }
        self.dashboard_handoff_title.setText(titles.get(state, titles["unverified"]))
        self.dashboard_handoff_detail.setText(
            f"{detail}  •  This view starts no approval, command, build, flash, or phone action."
        )
        self.dashboard_handoff_badge.setText(badges.get(state, badges["unverified"]))
        self.dashboard_handoff_badge.setObjectName(
            "Good" if verified else "Danger" if state in {"locked", "failed"} else "Warning"
        )
        self._repolish(self.dashboard_handoff_badge)

    def open_recovery_review(
        self,
        incident: RecoveryIncident,
        route: RecoveryRoute,
        preparation: GuardianRecoveryPreparation | None = None,
        live_target_service: GuardianRecoveryLiveTargetReceiptService | None = None,
        reviewed_device: AndroidDevice | None = None,
    ) -> bool:
        """Show one sealed Recovery route, optionally with exact prepared evidence."""

        if (
            not isinstance(incident, RecoveryIncident)
            or not isinstance(route, RecoveryRoute)
            or incident.repaired
            or not incident.integrity_verified
            or not incident.device_key
            or not incident.pack_id
            or route not in incident.routes
            or route.owner_route != "guardian_core"
            or not route.changes_device
            or not route.confirmation_required
            or route.execution_authority != "none"
            or not route.requirements
        ):
            return False
        if preparation is not None:
            try:
                GuardianRecoveryPreparationService.validate(preparation)
            except GuardianRecoveryPreparationError:
                return False
            if (
                preparation.incident_id != incident.incident_id
                or preparation.incident_record_digest != incident.record_digest
                or preparation.route_id != route.route_id
                or preparation.route_kind is not route.kind
                or preparation.project_id != incident.project_id
                or preparation.device_key != incident.device_key
                or preparation.device_pack_id != incident.pack_id
                or preparation.device_pack_sha256 != incident.pack_sha256
            ):
                return False
        self._recovery_target_generation += 1
        self.clear_nexus_review()
        self.clear_backup_review()
        self.clear_studio_review()
        self.recovery_review_eyebrow.setText(
            "RECOVERY AUTOPILOT  •  EXACT PREPARATION"
            if preparation is not None
            else "RECOVERY AUTOPILOT HANDOFF  •  CONTEXT ONLY"
        )
        self.recovery_review_title.setText(f"{route.title}  •  {incident.device_name}")
        self.recovery_review_badge.setText(
            "PREPARED • ZERO AUTHORITY" if preparation is not None else "ADVISORY • ZERO AUTHORITY"
        )
        self.recovery_review_badge.setObjectName("Warning")
        self._repolish(self.recovery_review_badge)
        requirements = "\n".join(f"• {item}" for item in route.requirements)
        evidence = "\n".join(f"• {item}" for item in route.evidence) or "• No additional evidence"
        prepared_detail = ""
        if preparation is not None:
            step_rows = "\n".join(
                f"• {step.order:02d}  {step.operation.value.replace('_', ' ')}  •  "
                f"{step.from_mode} → {step.to_mode}"
                + ("  •  MAY WIPE USER DATA" if step.may_wipe_user_data else "")
                for step in preparation.steps
            )
            prepared_detail = (
                "\nROMVERSE HAS PREPARED THE EXACT RECOVERY PLAN\n"
                "Guardian still needs a fresh live-phone check and your confirmation before "
                "anything can act.\n"
                "EXACT PREPARATION  •  CURRENT + SEALED\n"
                f"Protected source SHA-256 {preparation.source_original_sha256}\n"
                f"Device Pack {preparation.device_pack_id} v{preparation.device_pack_version}  •  "
                f"{preparation.device_pack_sha256[:20]}…\n"
                f"Signed transition {preparation.transition_contract_id}  •  "
                f"{preparation.transition_contract_digest[:20]}…\n"
                f"Recovery adapter {preparation.recovery_adapter_id}  •  "
                f"evidence {preparation.recovery_evidence_digest[:20]}…\n"
                f"Prepared operation sequence\n{step_rows}\n"
                f"Preparation {preparation.preparation_digest[:20]}…  •  "
                "Guardian live-target validation: required  •  User confirmation: required\n"
            )
        consequence = (
            "IMPORTANT  •  This prepared route may erase user data."
            if preparation is not None and preparation.may_wipe_user_data
            else "This review does not claim that personal data is guaranteed safe."
        )
        self.recovery_review_detail.setText(
            f"ROMVERSE {'prepared' if preparation is not None else 'identified'} this Recovery "
            f"route for {incident.device_name}.\n"
            f"WHY  •  {incident.diagnosis}\n"
            f"PROPOSED  •  {route.summary}\n"
            f"{consequence}\n"
            "Before anything can change, Guardian must freshly recognize the exact phone and "
            "you must confirm the complete Recovery plan. No action has started."
        )
        self._recovery_technical_text = (
            f"Incident {incident.incident_id[:12]}…  •  Project "
            f"{incident.project_id or 'not bound'}  •  Device Pack {incident.pack_id}\n"
            f"RECOVERY DIAGNOSIS  •  {incident.diagnosis}\n"
            f"PROPOSED ROUTE  •  Rank {route.rank}  •  {route.confidence}% confidence  •  "
            f"{route.risk.value} risk\n{route.summary}\n"
            f"REQUIRED BEFORE ANY ACTION\n{requirements}\n"
            f"CURRENT EVIDENCE\n{evidence}{prepared_detail}\n"
            "HANDOFF BOUNDARY  •  Context only  •  Approval: none  •  Execution: none  •  "
            "Phone changed: no  •  Bootloader relock: never"
        )
        self.recovery_technical_detail.setText(self._recovery_technical_text)
        self.recovery_technical_button.setVisible(True)
        self._set_recovery_details_expanded(self._experience_mode is ExperienceMode.EXPERT)
        self._recovery_review_identity = (incident.incident_id, route.route_id)
        self._recovery_preparation_digest = (
            preparation.preparation_digest if preparation is not None else ""
        )
        self._recovery_preparation = preparation
        self._recovery_live_target_service = live_target_service
        self._recovery_reviewed_device = reviewed_device
        self._recovery_live_target_receipt = None
        self._recovery_target_expiry_timer.stop()
        live_check_available = bool(
            preparation is not None
            and live_target_service is not None
            and isinstance(reviewed_device, AndroidDevice)
        )
        if live_check_available:
            self._render_recovery_target_ready()
        else:
            self.recovery_target_status.setText(
                "READ-ONLY PHONE CHECK NOT AVAILABLE  •  Verified ADB and Fastboot tools are "
                "required. This preparation remains sealed; no phone action started."
                if preparation is not None
                else "This advisory route has no exact prepared operation or live-phone check."
            )
        self.recovery_target_status.setObjectName(
            "Good" if live_check_available else "Warning" if preparation is not None else "Muted"
        )
        self._repolish(self.recovery_target_status)
        self.recovery_target_button.setVisible(preparation is not None)
        self.recovery_target_button.setEnabled(preparation is not None)
        self.recovery_target_button.setText(
            "Check exact phone now" if live_check_available else "Open Forge Arsenal"
        )
        self.recovery_return_button.setText("Return to Recovery incident")
        self.recovery_return_button.setEnabled(True)
        self._set_recovery_focus(True)
        self.recovery_review.setVisible(True)
        if live_check_available:
            self._start_recovery_target_check()
        return True

    @property
    def recovery_review_identity(self) -> tuple[str, str] | None:
        return self._recovery_review_identity

    @property
    def recovery_preparation_digest(self) -> str:
        return self._recovery_preparation_digest

    @property
    def recovery_live_target_receipt(self) -> GuardianRecoveryLiveTargetReceipt | None:
        return self._recovery_live_target_receipt

    @property
    def recovery_preparation(self) -> GuardianRecoveryPreparation | None:
        return self._recovery_preparation

    def set_experience_mode(self, mode: ExperienceMode) -> None:
        """Change evidence density without changing Recovery context or worker state."""

        self._experience_mode = ExperienceMode(mode)
        if self._recovery_review_identity is not None:
            self._set_recovery_details_expanded(self._experience_mode is ExperienceMode.EXPERT)
            if self._recovery_live_target_receipt is not None:
                self._render_recovery_target_receipt(self._recovery_live_target_receipt)

    def _toggle_recovery_details(self) -> None:
        self._set_recovery_details_expanded(not self._recovery_details_expanded)

    def _set_recovery_details_expanded(self, expanded: bool) -> None:
        self._recovery_details_expanded = bool(expanded and self._recovery_technical_text)
        self.recovery_technical_scroll.setVisible(self._recovery_details_expanded)
        self.recovery_technical_button.setText(
            "Hide technical details"
            if self._recovery_details_expanded
            else "View technical details"
        )
        self.recovery_technical_button.setAccessibleName(
            "Hide technical evidence for this Recovery plan"
            if self._recovery_details_expanded
            else "Show technical evidence for this Recovery plan"
        )

    def _render_recovery_target_receipt(
        self,
        receipt: GuardianRecoveryLiveTargetReceipt,
    ) -> None:
        self.recovery_target_status.setObjectName("Good")
        if self._experience_mode is ExperienceMode.GUIDED:
            self.recovery_target_status.setText(
                "EXACT PHONE VERIFIED  •  Guardian freshly confirmed that the connected "
                "Fastboot phone matches this Recovery plan. Nothing changed on the phone. "
                "Recovery confirmation remains locked."
            )
        else:
            slot = (
                f"  •  recorded pre-write slot {receipt.recorded_prewrite_slot.upper()}"
                if receipt.recorded_prewrite_slot
                else ""
            )
            self.recovery_target_status.setText(
                f"EXACT PHONE CONFIRMED  •  {receipt.observed_product}  •  "
                f"{receipt.observed_entry_mode.upper()}  •  bootloader unlocked{slot}\n"
                f"Receipt {receipt.receipt_digest[:20]}…  •  valid until {receipt.expires_at}  •  "
                "Recovery consent: locked  •  Execution: none  •  Phone changed: no"
            )
        self._repolish(self.recovery_target_status)

    def _render_recovery_target_ready(self) -> None:
        self.recovery_target_status.setText(
            "READY TO CHECK YOUR PHONE  •  ROMVERSE can now make sure this Recovery plan still "
            "matches the connected phone. Recovery confirmation remains locked."
            if self._experience_mode is ExperienceMode.GUIDED
            else "READY FOR READ-ONLY PHONE CHECK  •  ROMVERSE will confirm one exact Fastboot "
            "phone and its product, unlock and mode evidence. Recovery consent remains locked."
        )

    def revalidate_recovery_live_target(
        self,
        preparation: GuardianRecoveryPreparation,
        reviewed_device: AndroidDevice,
    ) -> bool:
        """Refresh retained read-only evidence against the latest exact-device scan."""

        if (
            preparation.preparation_digest != self._recovery_preparation_digest
            or self._recovery_preparation is None
            or self._recovery_live_target_service is None
        ):
            return False
        self._recovery_preparation = preparation
        self._recovery_reviewed_device = reviewed_device
        receipt = self._recovery_live_target_receipt
        if self.recovery_target_worker is not None and receipt is None:
            return True
        if receipt is None:
            try:
                self._recovery_live_target_service.validate_context(
                    preparation,
                    reviewed_device,
                )
            except RecoveryLiveTargetValidationError:
                self.recovery_target_status.setObjectName("Warning")
                self.recovery_target_status.setText(
                    "WAITING FOR THE EXACT FASTBOOT PHONE  •  ROMVERSE will enable the read-only "
                    "check automatically after the phone involved in this Recovery incident is "
                    "freshly recognized in the required mode."
                )
                self.recovery_target_button.setText("Check exact phone now")
                self.recovery_target_button.setEnabled(False)
                self._repolish(self.recovery_target_status)
                return False
            self.recovery_target_status.setObjectName("Good")
            self._render_recovery_target_ready()
            self.recovery_target_button.setText("Check exact phone now")
            self.recovery_target_button.setEnabled(True)
            self._repolish(self.recovery_target_status)
            self._start_recovery_target_check()
            return True
        current = self._recovery_live_target_service.load(preparation, reviewed_device)
        if current == receipt:
            return True
        self._recovery_live_target_receipt = None
        self._recovery_target_expiry_timer.stop()
        try:
            self._recovery_live_target_service.validate_context(preparation, reviewed_device)
        except RecoveryLiveTargetValidationError:
            self.recovery_live_target_unavailable()
        else:
            self.recovery_target_status.setObjectName("Warning")
            self.recovery_target_status.setText(
                "PHONE CHECK NO LONGER CURRENT  •  ROMVERSE is repeating the short-lived "
                "read-only check against the latest exact-phone scan. Nothing has changed on "
                "the phone."
            )
            self.recovery_target_button.setText("Check exact phone again")
            self.recovery_target_button.setEnabled(True)
            self._repolish(self.recovery_target_status)
            self._start_recovery_target_check()
        return False

    def recovery_live_target_unavailable(self) -> None:
        """Revoke retained live evidence while preserving immutable Recovery intent."""

        if self._recovery_preparation is None:
            return
        self._recovery_target_generation += 1
        self._recovery_reviewed_device = None
        self._recovery_live_target_receipt = None
        self._recovery_target_expiry_timer.stop()
        self.recovery_target_status.setObjectName("Warning")
        self.recovery_target_status.setText(
            "WAITING FOR THE PHONE IN THIS RECOVERY INCIDENT  •  Connect only that phone in "
            "the required Fastboot mode. ROMVERSE will continue the read-only check "
            "automatically after a fresh exact match. Nothing has changed on any phone."
        )
        self.recovery_target_button.setText("Waiting for exact phone")
        self.recovery_target_button.setEnabled(False)
        self._repolish(self.recovery_target_status)

    def recovery_review_stopped(self, reason: str) -> None:
        """Expire a Recovery handoff visibly without retaining action authority."""

        self._recovery_review_identity = None
        self._recovery_preparation_digest = ""
        self._recovery_preparation = None
        self._recovery_live_target_service = None
        self._recovery_reviewed_device = None
        self._recovery_live_target_receipt = None
        self._recovery_target_generation += 1
        self._recovery_technical_text = ""
        self._recovery_details_expanded = False
        self._recovery_target_expiry_timer.stop()
        self._set_recovery_focus(True)
        self.recovery_review_title.setText("Recovery route context expired safely")
        self.recovery_review_detail.setText(
            f"{reason}\nReturn to Recovery Bay and rebuild the route from fresh evidence. "
            "Approval: none  •  Execution: none  •  No action started."
        )
        self.recovery_review_badge.setText("CONTEXT REFUSED")
        self.recovery_review_badge.setObjectName("Danger")
        self.recovery_target_status.setObjectName("Danger")
        self.recovery_target_status.setText(
            "PHONE CHECK VOID  •  This Recovery context is no longer current. No retained "
            "receipt or action authority remains."
        )
        self.recovery_target_button.setVisible(False)
        self.recovery_target_button.setEnabled(False)
        self.recovery_return_button.setText("Return to Recovery Bay")
        self.recovery_return_button.setEnabled(True)
        self.recovery_technical_detail.clear()
        self.recovery_technical_scroll.setVisible(False)
        self.recovery_technical_button.setVisible(False)
        self._repolish(self.recovery_review_badge)
        self._repolish(self.recovery_target_status)
        self.recovery_review.setVisible(True)

    def clear_recovery_review(self) -> None:
        self._recovery_review_identity = None
        self._recovery_preparation_digest = ""
        self._recovery_preparation = None
        self._recovery_live_target_service = None
        self._recovery_reviewed_device = None
        self._recovery_live_target_receipt = None
        self._recovery_target_generation += 1
        self._recovery_technical_text = ""
        self._recovery_details_expanded = False
        self._recovery_target_expiry_timer.stop()
        self._set_recovery_focus(False)
        self.recovery_review.setVisible(False)
        self.recovery_review_title.clear()
        self.recovery_review_detail.clear()
        self.recovery_review_eyebrow.setText("RECOVERY AUTOPILOT HANDOFF  •  CONTEXT ONLY")
        self.recovery_review_badge.setText("ADVISORY • ZERO AUTHORITY")
        self.recovery_review_badge.setObjectName("Warning")
        self.recovery_target_status.clear()
        self.recovery_target_status.setObjectName("Muted")
        self.recovery_target_button.setVisible(False)
        self.recovery_target_button.setEnabled(False)
        self.recovery_target_button.setText("Check exact phone now")
        self.recovery_return_button.setText("Return to Recovery incident")
        self.recovery_technical_detail.clear()
        self.recovery_technical_scroll.setVisible(False)
        self.recovery_technical_button.setVisible(False)
        self.recovery_technical_button.setText("View technical details")
        self._repolish(self.recovery_review_badge)

    def _start_recovery_target_check(self) -> None:
        if self._recovery_preparation is not None and self._recovery_live_target_service is None:
            self.toolchain_requested.emit()
            return
        if (
            self.recovery_target_worker is not None
            or self._recovery_live_target_service is None
            or self._recovery_preparation is None
            or self._recovery_reviewed_device is None
        ):
            return
        self._recovery_live_target_receipt = None
        self.recovery_target_button.setEnabled(False)
        self.recovery_target_status.setObjectName("Muted")
        self.recovery_target_status.setText(
            "CHECKING YOUR PHONE…  •  ROMVERSE is making sure the Recovery plan still matches. "
            "Nothing can change on the phone during this check."
            if self._experience_mode is ExperienceMode.GUIDED
            else "Checking the exact Fastboot phone with read-only identity probes… No flash, "
            "reboot, wipe, unlock, relock, approval or Recovery action can run."
        )
        self._repolish(self.recovery_target_status)
        self._recovery_target_generation += 1
        attempt_number = self._recovery_target_generation
        worker = RecoveryLiveTargetWorker(
            self._recovery_live_target_service,
            self._recovery_preparation,
            self._recovery_reviewed_device,
            attempt_number,
        )
        self.recovery_target_worker = worker
        worker.signals.complete.connect(self._recovery_target_check_complete)
        worker.signals.failed.connect(self._recovery_target_check_failed)
        start_background(worker)

    @Slot(int, str, object)
    def _recovery_target_check_complete(
        self,
        attempt_number: int,
        preparation_digest: str,
        result: object,
    ) -> None:
        self.recovery_target_worker = None
        if attempt_number != self._recovery_target_generation:
            if self._recovery_reviewed_device is not None:
                QTimer.singleShot(0, self._start_recovery_target_check)
            return
        preparation = self._recovery_preparation
        if preparation is None or preparation_digest != self._recovery_preparation_digest:
            return
        if (
            not isinstance(result, GuardianRecoveryLiveTargetReceipt)
            or result.preparation_digest != preparation.preparation_digest
            or self._recovery_preparation_digest != preparation.preparation_digest
            or not result.identity_verified
            or result.recovery_consent_available
            or result.execution_authority != "none"
            or result.runtime_invoked
            or result.phone_changed
        ):
            self._recovery_target_check_failed(
                attempt_number,
                preparation_digest,
                "The returned evidence did not match this exact Recovery preparation",
            )
            return
        self._recovery_live_target_receipt = result
        self._render_recovery_target_receipt(result)
        self.recovery_target_button.setText("Check exact phone again")
        self.recovery_target_button.setEnabled(True)
        try:
            expires = datetime.fromisoformat(result.expires_at).astimezone(UTC)
            remaining_ms = max(
                1,
                int((expires - datetime.now(UTC)).total_seconds() * 1000) + 50,
            )
        except ValueError:
            remaining_ms = 1
        self._recovery_target_expiry_timer.start(min(remaining_ms, 2_147_483_647))

    @Slot(int, str, str)
    def _recovery_target_check_failed(
        self,
        attempt_number: int,
        preparation_digest: str,
        message: str,
    ) -> None:
        self.recovery_target_worker = None
        if attempt_number != self._recovery_target_generation:
            if self._recovery_reviewed_device is not None:
                QTimer.singleShot(0, self._start_recovery_target_check)
            return
        if preparation_digest != self._recovery_preparation_digest:
            return
        self._recovery_live_target_receipt = None
        self._recovery_target_expiry_timer.stop()
        clean = " ".join(str(message).replace("\x00", " ").split())[:500]
        self.recovery_target_status.setObjectName("Danger")
        if self._experience_mode is ExperienceMode.GUIDED:
            self.recovery_target_status.setText(
                "PHONE CHECK NEEDS ATTENTION  •  ROMVERSE could not prove that the connected "
                "phone and mode still match this Recovery plan. Reconnect the phone involved in "
                "the incident in Fastboot, then try again. Nothing changed on the phone."
            )
            if clean:
                self._recovery_technical_text = (
                    f"{self._recovery_technical_text}\nLIVE PHONE CHECK FAILURE\n{clean}"
                )
                self.recovery_technical_detail.setText(self._recovery_technical_text)
        else:
            self.recovery_target_status.setText(
                f"PHONE CHECK STOPPED SAFELY  •  {clean or 'The exact phone was not verified.'}\n"
                "No receipt remains current. No flash, reboot, wipe, approval, Recovery action or "
                "phone change was attempted."
            )
        self.recovery_target_button.setText("Retry exact phone check")
        self.recovery_target_button.setEnabled(
            self._recovery_preparation is not None
            and self._recovery_live_target_service is not None
            and self._recovery_reviewed_device is not None
        )
        self._repolish(self.recovery_target_status)

    @Slot()
    def _expire_recovery_target_receipt(self) -> None:
        if self._recovery_live_target_receipt is None:
            return
        self._recovery_live_target_receipt = None
        self.recovery_target_status.setObjectName("Warning")
        self.recovery_target_status.setText(
            "PHONE CHECK EXPIRED  •  Live identity evidence is intentionally short-lived. "
            "Check the exact phone again before any later Recovery confirmation."
        )
        self.recovery_target_button.setText("Check exact phone again")
        self.recovery_target_button.setEnabled(
            self._recovery_preparation is not None
            and self._recovery_live_target_service is not None
            and self._recovery_reviewed_device is not None
        )
        self._repolish(self.recovery_target_status)

    def open_nexus_review(self, plan: NexusPlan, project_name: str) -> bool:
        """Present a validated Nexus plan without approving or executing it."""

        if (
            not isinstance(plan, NexusPlan)
            or not plan.ready_for_guardian_review
            or plan.execution_authorized
            or plan.bootloader_relock_permitted
        ):
            return False
        clean_name = " ".join(project_name.replace("\x00", "").split())[:80]
        if not clean_name:
            return False
        self.clear_backup_review()
        self.clear_studio_review()
        self.clear_recovery_review()
        objective = {
            NexusObjective.BUILD_ROM: "Build a ROM",
            NexusObjective.ROOT_ROM: "Prepare optional root",
            NexusObjective.FLASH_DEVICE: "Prepare Guardian flash review",
        }[plan.objective]
        self.nexus_review_title.setText(f"{objective}  •  {clean_name}")
        self.nexus_review_badge.setText("ZERO AUTHORITY")
        self.nexus_review_badge.setObjectName("Warning")
        self._repolish(self.nexus_review_badge)
        requirements = "\n".join(f"• {item}" for item in plan.guardian_requirements)
        self.nexus_review_detail.setText(
            f"Plan {plan.plan_digest[:16]}…  •  Mission {plan.mission_id[:12]}…  •  "
            "current source-bound evidence\n"
            "REVIEW BOUNDARY  •  Approval: none  •  Execution: none  •  "
            "Bootloader relock: never\n"
            f"GUARDIAN MUST REVALIDATE\n{requirements}"
        )
        self._nexus_review_identity = (plan.project_id, plan.plan_digest)
        self.nexus_review.setVisible(True)
        return True

    @property
    def nexus_review_identity(self) -> tuple[str, str] | None:
        return self._nexus_review_identity

    def nexus_review_stopped(self, reason: str) -> None:
        """Keep an expired destination context readable without retaining authority."""

        self._nexus_review_identity = None
        self.nexus_review_title.setText("Nexus review context expired safely")
        self.nexus_review_detail.setText(
            f"{reason}\nRefresh and reopen the plan from Nexus. Approval: none  •  "
            "Execution: none  •  No action started."
        )
        self.nexus_review_badge.setText("CONTEXT REFUSED")
        self.nexus_review_badge.setObjectName("Danger")
        self._repolish(self.nexus_review_badge)
        self.nexus_review.setVisible(True)

    def clear_nexus_review(self) -> None:
        self._nexus_review_identity = None
        self.nexus_review.setVisible(False)
        self.nexus_review_title.clear()
        self.nexus_review_detail.clear()
        self.nexus_review_badge.setText("ZERO AUTHORITY")
        self.nexus_review_badge.setObjectName("Warning")
        self._repolish(self.nexus_review_badge)

    def open_backup_review(self, plan: BackupPlanRead) -> bool:
        """Present one integrity-verified readiness plan without granting authority."""

        if not isinstance(plan, BackupPlanRead):
            return False
        data = plan.data
        if (
            not plan.valid
            or not plan.integrity_verified
            or not isinstance(data, dict)
            or data.get("execution_locked") is not True
            or data.get("execution_authority") != "none"
            or data.get("phone_data_copied") is not False
        ):
            return False
        plan_id = data.get("plan_id")
        plan_digest = data.get("plan_digest")
        device_name = data.get("device_name")
        readiness = data.get("readiness")
        if (
            not isinstance(plan_id, str)
            or not isinstance(plan_digest, str)
            or not isinstance(device_name, str)
            or not isinstance(readiness, dict)
        ):
            return False
        clean_name = " ".join(device_name.replace("\x00", "").split())[:240]
        if not clean_name:
            return False
        self.clear_nexus_review()
        self.clear_studio_review()
        self.clear_recovery_review()
        self.backup_review_title.setText(f"Recovery readiness  •  {clean_name}")
        self.backup_review_badge.setText("ZERO AUTHORITY")
        self.backup_review_badge.setObjectName("Warning")
        self._repolish(self.backup_review_badge)
        battery = readiness.get("battery_percent")
        storage = readiness.get("storage_percent_used")
        self.backup_review_detail.setText(
            f"Plan {plan_id}  •  SHA-256 {plan_digest[:16]}…  •  "
            f"created {_display_time(str(data.get('created_at', '')))}\n"
            "READINESS EVIDENCE  •  "
            f"ADB authorized: {'yes' if readiness.get('adb_authorized') is True else 'no'}  •  "
            f"Battery: {battery if battery is not None else 'unknown'}%  •  "
            f"Storage used: {storage if storage is not None else 'unknown'}%  •  "
            f"Bootloader locked: {_display_bool(readiness.get('bootloader_locked'))}  •  "
            f"Verified Boot: {readiness.get('verified_boot') or 'unknown'}\n"
            "REVIEW BOUNDARY  •  Recovery-readiness evidence only  •  Phone data copied: no  •  "
            "Approval: none  •  Execution: none"
        )
        self._backup_review_identity = (plan_id, plan_digest)
        self.backup_review.setVisible(True)
        return True

    @property
    def backup_review_identity(self) -> tuple[str, str] | None:
        return self._backup_review_identity

    def backup_review_stopped(self, reason: str) -> None:
        """Expire a retained recovery plan visibly and without retaining authority."""

        self._backup_review_identity = None
        self.backup_review_title.setText("Recovery-readiness context expired safely")
        self.backup_review_detail.setText(
            f"{reason}\nRefresh and reopen the plan from Time Machine. Approval: none  •  "
            "Execution: none  •  No action started."
        )
        self.backup_review_badge.setText("CONTEXT REFUSED")
        self.backup_review_badge.setObjectName("Danger")
        self._repolish(self.backup_review_badge)
        self.backup_review.setVisible(True)

    def clear_backup_review(self) -> None:
        self._backup_review_identity = None
        self.backup_review.setVisible(False)
        self.backup_review_title.clear()
        self.backup_review_detail.clear()
        self.backup_review_badge.setText("ZERO AUTHORITY")
        self.backup_review_badge.setObjectName("Warning")
        self._repolish(self.backup_review_badge)

    def open_studio_review(
        self,
        manifest: GuardianManifestReview,
        project_name: str,
        execution_plan: GuardianExecutionPlan | None = None,
        gateway_contract: GuardianExecutionGatewayContract | None = None,
    ) -> bool:
        """Present one exact command-free Studio manifest as persistent evidence."""

        if (
            not isinstance(manifest, GuardianManifestReview)
            or not manifest.project_id
            or not manifest.manifest_digest
            or manifest.final_consent_available
            or manifest.execution_authority != "none"
            or manifest.phone_changed
            or manifest.bootloader_relock_allowed
            or manifest.command_manifest
        ):
            return False
        clean_name = " ".join(project_name.replace("\x00", "").split())[:80]
        if not clean_name:
            return False
        if execution_plan is not None and not execution_plan_matches_manifest(
            execution_plan,
            manifest,
        ):
            return False
        if gateway_contract is not None and not gateway_contract_matches_plan(
            gateway_contract,
            execution_plan,
        ):
            return False
        self.clear_nexus_review()
        self.clear_backup_review()
        self.clear_recovery_review()
        self.studio_review_title.setText(f"{clean_name}  •  {manifest.device_name}")
        self.studio_review_badge.setText("ZERO AUTHORITY")
        self.studio_review_badge.setObjectName("Warning")
        self._repolish(self.studio_review_badge)
        blockers = "\n".join(f"• {item}" for item in manifest.blockers)
        plan_detail = "\nINERT EXECUTION PLAN  •  not attached to this view"
        if execution_plan is not None:
            preconditions = sum(
                command.phase.value == "precondition" for command in execution_plan.commands
            )
            writes = sum(command.phase.value == "write" for command in execution_plan.commands)
            plan_detail = (
                f"\nINERT EXECUTION PLAN  •  {preconditions} preflight / {writes} write preview"
                f"  •  {execution_plan.plan_digest[:16]}…"
                f"\nPlan state  •  {execution_plan.plan_status.replace('-', ' ')}"
            )
        if gateway_contract is not None:
            orchestration = ""
            if gateway_contract.mode_transition_count:
                wipe = (
                    "  •  recovery may wipe: yes (automatic wipe forbidden)"
                    if gateway_contract.recovery_may_wipe_user_data
                    else "  •  recovery may wipe: no"
                )
                orchestration = (
                    f"\nSIGNED ORCHESTRATION  •  {gateway_contract.mode_transition_count} mode/slot "
                    f"transition(s) / {gateway_contract.recovery_action_count} recovery action(s)"
                    f"  •  adapter {gateway_contract.recovery_adapter_id}{wipe}"
                )
            plan_detail += (
                f"\nRESULT TEMPLATE  •  {gateway_contract.readback_count} immediate readback"
                f"{'s' if gateway_contract.readback_count != 1 else ''} / "
                f"{gateway_contract.post_boot_property_count} first-boot checks"
                f"  •  {gateway_contract.contract_digest[:16]}…"
                f"\nTemplate state  •  {gateway_contract.contract_status.replace('-', ' ')}"
                "  •  Runtime invoked: no"
                f"\nSIGNED RESULT VERIFIER v{gateway_contract.result_receipt_schema_version}  •  "
                "Ed25519 runtime signature + independent target/consent bindings required  •  "
                "Runtime trust: not enrolled"
                "\nLIVE TARGET CHECK v1  •  read-only exact Fastboot re-identification available  •  "
                "fresh receipt not captured by this review  •  two-minute validity  •  authority none"
                f"{orchestration}"
            )
        self.studio_review_detail.setText(
            f"Manifest {manifest.manifest_digest[:16]}…  •  handoff "
            f"{manifest.handoff_digest[:16]}…  •  project {manifest.project_id}\n"
            f"EXACT BINDING  •  {manifest.model} / {manifest.codename}  •  Pack "
            f"{manifest.device_pack_id} v{manifest.device_pack_version}  •  source "
            f"{manifest.source_sha256[:16]}…  •  mode {manifest.mode.display_name}\n"
            f"ARTIFACT REVIEW  •  {len(manifest.partition_writes)} image(s) hash-bound  •  "
            f"status {manifest.review_status.replace('-', ' ')}\n"
            f"{plan_detail}\n"
            f"REMAINING BLOCKERS\n{blockers}\n"
            "REVIEW BOUNDARY  •  Approval: none  •  Execution: none  •  Final consent: "
            "locked  •  Bootloader relock: never  •  Phone changed: no"
        )
        self._studio_review_identity = (manifest.project_id, manifest.manifest_digest)
        self.studio_review.setVisible(True)
        return True

    @property
    def studio_review_identity(self) -> tuple[str, str] | None:
        return self._studio_review_identity

    def studio_review_stopped(self, reason: str) -> None:
        """Expire a retained Studio manifest visibly and without retaining authority."""

        self._studio_review_identity = None
        self.studio_review_title.setText("ROM Studio manifest context expired safely")
        self.studio_review_detail.setText(
            f"{reason}\nReturn to Forge Control and compile a fresh exact Guardian review. "
            "Approval: none  •  Execution: none  •  No action started."
        )
        self.studio_review_badge.setText("CONTEXT REFUSED")
        self.studio_review_badge.setObjectName("Danger")
        self._repolish(self.studio_review_badge)
        self.studio_review.setVisible(True)

    def clear_studio_review(self) -> None:
        self._studio_review_identity = None
        self.studio_review.setVisible(False)
        self.studio_review_title.clear()
        self.studio_review_detail.clear()
        self.studio_review_badge.setText("ZERO AUTHORITY")
        self.studio_review_badge.setObjectName("Warning")
        self._repolish(self.studio_review_badge)

    def _return_to_rom_studio(self) -> None:
        if self._studio_review_identity is not None:
            self.rom_studio_requested.emit(*self._studio_review_identity)

    def _return_to_nexus(self) -> None:
        if self._nexus_review_identity is not None:
            self.nexus_requested.emit(*self._nexus_review_identity)

    def _return_to_time_machine(self) -> None:
        if self._backup_review_identity is not None:
            self.time_machine_requested.emit(*self._backup_review_identity)

    def _return_to_recovery(self) -> None:
        if self._recovery_review_identity is not None:
            self.recovery_requested.emit(*self._recovery_review_identity)
        else:
            self.recovery_home_requested.emit()

    def _choose_runtime_package(self) -> None:
        envelope_name, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Select signed Guardian runtime package",
            "",
            "ROMVERSE runtime package (*.json *.romverse);;All files (*)",
        )
        if not envelope_name:
            return
        public_key_name, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Select trusted Guardian runtime release public key",
            "",
            "PEM public key (*.pem);;All files (*)",
        )
        if not public_key_name:
            return
        release_key_id, accepted = QInputDialog.getText(
            self,
            "Confirm runtime release identity",
            "Enter the expected release key ID obtained with the public key:",
        )
        if not accepted or not release_key_id.strip():
            return
        self.inspect_runtime_candidate(
            Path(envelope_name),
            Path(public_key_name),
            release_key_id.strip(),
        )

    def inspect_runtime_candidate(
        self,
        envelope_path: Path,
        release_public_key_path: Path,
        expected_release_key_id: str,
        *,
        expected_platform: str | None = None,
    ) -> bool:
        """Start an integrity-only runtime package inspection."""

        if self.runtime_worker is not None:
            return False
        try:
            platform = expected_platform or current_guardian_runtime_platform()
        except Exception as exc:
            self._runtime_inspection_failed(f"{type(exc).__name__}: {exc}")
            return False
        worker = GuardianRuntimePackageWorker(
            Path(envelope_path),
            Path(release_public_key_path),
            str(expected_release_key_id),
            platform,
        )
        worker.signals.complete.connect(self._runtime_inspection_complete)
        worker.signals.failed.connect(self._runtime_inspection_failed)
        self.runtime_worker = worker
        self.inspect_runtime_package_button.setEnabled(False)
        self.inspect_runtime_package_button.setText("Inspecting exact bytes …")
        self.runtime_package_progress.begin(determinate=False)
        self.runtime_package_title.setText("Inspecting runtime package candidate")
        self.runtime_package_badge.setText("VERIFYING")
        self.runtime_package_badge.setObjectName("Warning")
        self.runtime_package_detail.setText(
            "Checking the selected release signature, runtime identity, safety policy, platform, "
            "and exact executable bytes off the interface thread. Nothing is being launched."
        )
        self._repolish(self.runtime_package_badge)
        start_background(worker)
        return True

    @Slot(object)
    def _runtime_inspection_complete(self, value: object) -> None:
        self.runtime_worker = None
        self.runtime_package_progress.finish()
        self.inspect_runtime_package_button.setEnabled(True)
        self.inspect_runtime_package_button.setText("Inspect another candidate")
        if not isinstance(value, VerifiedGuardianRuntimePackage):
            self._runtime_inspection_failed(
                "Guardian runtime inspection returned an unexpected result"
            )
            return
        manifest = value.manifest
        self.runtime_package_title.setText(
            f"Candidate verified  •  {manifest.runtime_id} {manifest.runtime_version}"
        )
        self.runtime_package_badge.setText("CHECK PASSED • NOT ENROLLED")
        self.runtime_package_badge.setObjectName("Good")
        self.runtime_package_detail.setText(
            f"Platform  •  {manifest.platform}  •  protocol {manifest.runtime_protocol_version}  •  "
            f"result schema {manifest.result_receipt_schema_version}\n"
            f"Artifact  •  {manifest.artifact.file_name}  •  {manifest.artifact.size_bytes:,} bytes  •  "
            f"SHA-256 {manifest.artifact.sha256}\n"
            f"Release identity  •  {value.release_key_id}  •  "
            f"public-key SHA-256 {value.release_public_key_sha256}\n"
            f"Manifest  •  SHA-256 {value.manifest_sha256}\n"
            f"Runtime signer  •  {manifest.runtime_signer.key_id}  •  "
            f"public-key SHA-256 {manifest.runtime_signer.public_key_sha256}\n"
            f"Adapter  •  {manifest.adapter_id} v{manifest.adapter_version}  •  forward-only policy\n"
            "RESULT  •  Package signature and current bytes verified under the selected public key. "
            "Trust is not enrolled.\n"
            "BOUNDARY  •  Execution authority: NONE  •  Runtime invoked: NO  •  Phone changed: NO"
        )
        self._repolish(self.runtime_package_badge)

    @Slot(str)
    def _runtime_inspection_failed(self, message: str) -> None:
        self.runtime_worker = None
        self.runtime_package_progress.stop()
        self.inspect_runtime_package_button.setEnabled(True)
        self.inspect_runtime_package_button.setText("Inspect runtime candidate")
        self.runtime_package_title.setText("Runtime candidate rejected safely")
        self.runtime_package_badge.setText("CANDIDATE REJECTED")
        self.runtime_package_badge.setObjectName("Danger")
        clean = " ".join(str(message).replace("\x00", " ").split())[:500]
        self.runtime_package_detail.setText(
            f"{clean}\nNo package was launched or enrolled. Execution authority remains NONE; "
            "runtime invoked: NO; phone changed: NO."
        )
        self._repolish(self.runtime_package_badge)

    @staticmethod
    def _metric(label: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        value = QLabel("0")
        value.setObjectName("HeroTitle")
        title = QLabel(label)
        title.setObjectName("Eyebrow")
        layout.addWidget(value)
        layout.addWidget(title)
        return card, value

    def refresh(self) -> None:
        self._refresh_timer.stop()
        self._refresh_pending = False
        if self.audit is None:
            self.integrity_badge.setText("AUDIT UNAVAILABLE")
            self.integrity_badge.setObjectName("Warning")
            self.integrity_detail.setText("No audit store is attached to this application session.")
            self._repolish(self.integrity_badge)
            self._publish_dashboard_state(
                "unavailable",
                "No Guardian audit store is attached to this application session.",
                False,
            )
            self._empty(
                "Guardian decisions will appear when the application execution gateway is active."
            )
            return
        if self.worker is not None:
            return
        worker = GuardianCenterWorker(self.audit)
        worker.signals.complete.connect(self._verification_complete)
        worker.signals.failed.connect(self._verification_failed)
        self.worker = worker
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("Verifying bounded evidence …")
        self.progress.begin(determinate=False)
        self.policy_title.setText("Verifying Guardian evidence")
        self.integrity_badge.setText("VERIFYING")
        self.integrity_badge.setObjectName("Warning")
        self.integrity_detail.setText(
            "Checking the tamper-evident operation trail, approvals, APK receipts, and recovery-readiness evidence in the background."
        )
        self._repolish(self.integrity_badge)
        self._publish_dashboard_state(
            "verifying",
            "Guardian is checking the current audit chain, approvals, and safety receipts in the background.",
            False,
        )
        start_background(worker)

    def request_refresh(self) -> None:
        """Refresh only when the Guardian page is actually being viewed."""

        self._refresh_pending = True
        if self.worker is None and self._dashboard_state[0] == "verified":
            self._publish_dashboard_state(
                "review_due",
                "Guardian evidence changed or was reopened and must be verified again before Command Deck can call it current.",
                False,
            )
        if self.isVisible() and self.worker is None:
            self._refresh_timer.start()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._refresh_pending and self.worker is None:
            self._refresh_timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._refresh_timer.stop()
        super().hideEvent(event)

    @Slot(object)
    def _verification_complete(self, value: object) -> None:
        self.worker = None
        self.progress.finish()
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText("Verify audit trail")
        if not isinstance(value, GuardianCenterSnapshot):
            self._verification_failed("Guardian verification returned an unexpected result")
            return
        self._render_snapshot(value)

    @Slot(str)
    def _verification_failed(self, message: str) -> None:
        self.worker = None
        self.progress.stop()
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText("Retry audit verification")
        self.policy_title.setText("Guardian verification stopped safely")
        self.integrity_badge.setText("VERIFICATION FAILED")
        self.integrity_badge.setObjectName("Danger")
        self.integrity_detail.setText(
            f"Guardian could not verify its local evidence: {message}\nNo stored approval can authorize an operation until verification succeeds."
        )
        self._repolish(self.integrity_badge)
        self._publish_dashboard_state(
            "failed",
            "Guardian could not complete its bounded verification; stored approvals cannot authorize an operation.",
            False,
        )
        self._empty(
            "Retry the bounded verification after reviewing the reported local evidence error."
        )

    def _render_snapshot(self, snapshot: GuardianCenterSnapshot) -> None:
        verification = snapshot.verification
        approval_verification = snapshot.approval_verification
        records = snapshot.records
        self.policy_title.setText(
            "Read-only enforcement active"
            if verification.valid and approval_verification.valid
            else "Guardian execution locked"
        )
        allowed = sum(bool(record.get("allowed")) for record in records)
        denied = sum(not bool(record.get("allowed")) for record in records)
        self.total_value.setText(str(verification.total_entries))
        self.allowed_value.setText(str(allowed))
        self.denied_value.setText(str(denied))
        self.approval_value.setText(str(approval_verification.total_entries))
        if verification.valid and approval_verification.valid:
            self.integrity_badge.setText("INTEGRITY VERIFIED")
            self.integrity_badge.setObjectName("Good")
        self.integrity_detail.setText(
            f"SHA-256 chain valid across {verification.total_entries} operation record"
            f"{'s' if verification.total_entries != 1 else ''}."
            f"\nGuardian approvals: {approval_verification.active_entries} active / "
            f"{approval_verification.total_entries} recorded / "
            f"{approval_verification.legacy_entries} legacy audit-only."
        )
        preflight = snapshot.preflight
        if preflight.valid and preflight.data is not None:
            data = preflight.data
            integrity = (
                f"digest {str(data.get('receipt_digest', ''))[:16]}…"
                if preflight.integrity_verified
                else "legacy / unverified"
            )
            self.integrity_detail.setText(
                self.integrity_detail.text()
                + f"\nLatest APK preflight: {data.get('status', 'unknown')} / {data.get('risk', 'unknown')}"
                + f"  •  {snapshot.preflight_history_count} saved"
                + f"\nReceipt {data.get('receipt_id', 'unavailable')}  •  {integrity}"
            )
        elif snapshot.preflight_exists:
            self.integrity_detail.setText(
                self.integrity_detail.text()
                + f"\nAPK preflight receipt rejected: {preflight.reason}"
            )
        install = snapshot.install
        if install.valid and install.data is not None:
            data = install.data
            outcome = "success" if data.get("success") else "failed safely"
            integrity = (
                f"digest {str(data.get('receipt_digest', ''))[:16]}…"
                if install.integrity_verified
                else "legacy / unverified"
            )
            self.integrity_detail.setText(
                self.integrity_detail.text()
                + f"\nLatest APK install result: {outcome} / return code {data.get('returncode', 'unknown')}"
                + f"  •  {snapshot.install_history_count} saved"
                + f"\nReceipt {data.get('receipt_id', 'unavailable')}  •  {integrity}"
            )
        elif snapshot.install_exists:
            self.integrity_detail.setText(
                self.integrity_detail.text() + f"\nAPK install receipt rejected: {install.reason}"
            )
        backup_plan = snapshot.backup_plan
        if backup_plan.valid and backup_plan.data is not None:
            data = backup_plan.data
            self.integrity_detail.setText(
                self.integrity_detail.text()
                + f"\nLatest recovery-readiness plan: {data.get('status', 'unknown')} / execution locked"
                + f"\nPlan created: {data.get('created_at', 'unknown')}"
                + f"  •  {snapshot.backup_history_count} saved"
                + (
                    f"  •  digest {str(data.get('plan_digest', ''))[:16]}…"
                    if backup_plan.integrity_verified
                    else "  •  legacy / unverified"
                )
            )
        elif snapshot.backup_plan_exists:
            self.integrity_detail.setText(
                self.integrity_detail.text()
                + f"\nRecovery-readiness plan rejected: {backup_plan.reason}"
            )
        if not verification.valid:
            self.integrity_badge.setText("INTEGRITY FAILURE")
            self.integrity_badge.setObjectName("Danger")
            self.integrity_detail.setText(verification.reason)
        elif not approval_verification.valid:
            self.integrity_badge.setText("APPROVAL INTEGRITY FAILURE")
            self.integrity_badge.setObjectName("Danger")
            self.integrity_detail.setText(
                "Guardian operation audit is intact, but approval history was rejected.\n"
                f"{approval_verification.reason}\nNo stored approval can authorize an operation."
            )
        if verification.valid and approval_verification.valid:
            self._verified_dashboard_revision = self._dashboard_evidence_revision()
            self._publish_dashboard_state(
                "verified",
                f"SHA-256 audit chain verified across {verification.total_entries} operation record"
                f"{'s' if verification.total_entries != 1 else ''}; "
                f"{approval_verification.active_entries} active approval"
                f"{'s' if approval_verification.active_entries != 1 else ''} revalidated.",
                True,
            )
        else:
            self._publish_dashboard_state(
                "locked",
                "Guardian rejected current audit or approval integrity; no stored approval can authorize an operation.",
                False,
            )
        self._repolish(self.integrity_badge)
        self._clear()
        approvals = snapshot.approvals
        if approvals:
            title = QLabel("Recent approvals")
            title.setObjectName("SectionTitle")
            self.body_layout.addWidget(title)
            for approval in approvals:
                card = QFrame()
                card.setObjectName("Card")
                card_layout = QVBoxLayout(card)
                detail = QLabel(
                    f"{_display_time(approval.issued_at)}  •  {approval.target}\n"
                    f"Plan digest  •  {approval.plan_digest[:16]}…\n"
                    + (
                        "LEGACY / AUDIT ONLY  •  cannot authorize an operation"
                        if approval.legacy
                        else f"Expires  •  {_display_time(approval.expires_at)}  •  SHA-256 chained"
                    )
                )
                detail.setObjectName("Muted")
                detail.setWordWrap(True)
                card_layout.addWidget(detail)
                self.body_layout.addWidget(card)
        if not records:
            message = (
                "Audit integrity must be restored before Guardian permits more operations."
                if not verification.valid
                else "No Guardian-controlled operations have run yet."
            )
            self._empty(message)
            return
        for record in records:
            self.body_layout.addWidget(self._record_card(record))
        self.body_layout.addStretch()

    @staticmethod
    def _record_card(record: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        detail = QVBoxLayout()
        title = QLabel(str(record.get("purpose", "Unknown operation")))
        title.setObjectName("SectionTitle")
        result = record.get("result", {})
        command = " ".join(
            [str(record.get("executable", "")), *map(str, record.get("arguments", []))]
        )
        metadata = QLabel(
            f"{_display_time(str(record.get('timestamp', '')))}  •  {record.get('category', 'unknown')}"
            f"  •  {record.get('target', 'unknown')}\n{command}\n"
            f"Result {result.get('returncode', 'not executed')}  •  {result.get('duration_ms', 0)} ms"
        )
        metadata.setObjectName("Muted")
        metadata.setWordWrap(True)
        metadata.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail.addWidget(title)
        detail.addWidget(metadata)
        layout.addLayout(detail, 1)
        badge = QLabel("ALLOWED" if record.get("allowed") else "DENIED")
        badge.setObjectName("Good" if record.get("allowed") else "Danger")
        layout.addWidget(badge)
        return card

    def _empty(self, message: str) -> None:
        self._clear()
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        label = QLabel(message)
        label.setObjectName("Muted")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.body_layout.addWidget(card)
        self.body_layout.addStretch()

    def _clear(self) -> None:
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)


def _display_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%d %b %Y • %H:%M:%S")
    except ValueError:
        return "Unknown time"


def _display_bool(value: object) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"
