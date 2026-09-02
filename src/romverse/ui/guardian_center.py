from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from romverse.applications.receipts import ApkReceiptRead, ApkReceiptStore
from romverse.backup.plans import BackupPlanRead, GuardianBackupPlanStore
from romverse.guardian.approval import ApprovalRecord, ApprovalStore, ApprovalVerification
from romverse.guardian.audit import AuditVerification, GuardianAuditStore
from romverse.guardian.manifest_review import GuardianManifestReview
from romverse.nexus.planning import NexusObjective, NexusPlan
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


class GuardianCenter(QWidget):
    nexus_requested = Signal(str, str)
    time_machine_requested = Signal(str, str)
    rom_studio_requested = Signal(str, str)
    dashboard_state_changed = Signal(str, str, bool)
    REFRESH_DEBOUNCE_MS = 250

    def __init__(self, audit: GuardianAuditStore | None, *, auto_start: bool = True) -> None:
        super().__init__()
        self.audit = audit
        self.worker: GuardianCenterWorker | None = None
        self._nexus_review_identity: tuple[str, str] | None = None
        self._backup_review_identity: tuple[str, str] | None = None
        self._studio_review_identity: tuple[str, str] | None = None
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

        recent_title = QLabel("Recent Guardian decisions")
        recent_title.setObjectName("SectionTitle")
        page.addWidget(recent_title)
        self.body = QScrollArea()
        self.body.setWidgetResizable(True)
        self.body_content = QWidget()
        self.body_content.setObjectName("ScrollContent")
        self.body_layout = QVBoxLayout(self.body_content)
        self.body_layout.setContentsMargins(0, 0, 6, 0)
        self.body_layout.setSpacing(10)
        self.body.setWidget(self.body_content)
        page.addWidget(self.body, 1)

        boundary = QLabel(
            "Guardian records operation metadata and outcomes only. Device serials, stdout, and stderr are excluded. "
            "A failed integrity check blocks subsequent execution through this gateway."
        )
        boundary.setObjectName("Muted")
        boundary.setWordWrap(True)
        page.addWidget(boundary)
        if auto_start:
            self.refresh()
        else:
            self._refresh_pending = True

    def current_dashboard_state(self) -> tuple[str, str, bool]:
        """Return the latest bounded Guardian summary owned by this page."""

        return self._dashboard_state

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
        self.clear_nexus_review()
        self.clear_backup_review()
        self.studio_review_title.setText(f"{clean_name}  •  {manifest.device_name}")
        self.studio_review_badge.setText("ZERO AUTHORITY")
        self.studio_review_badge.setObjectName("Warning")
        self._repolish(self.studio_review_badge)
        blockers = "\n".join(f"• {item}" for item in manifest.blockers)
        self.studio_review_detail.setText(
            f"Manifest {manifest.manifest_digest[:16]}…  •  handoff "
            f"{manifest.handoff_digest[:16]}…  •  project {manifest.project_id}\n"
            f"EXACT BINDING  •  {manifest.model} / {manifest.codename}  •  Pack "
            f"{manifest.device_pack_id} v{manifest.device_pack_version}  •  source "
            f"{manifest.source_sha256[:16]}…  •  mode {manifest.mode.display_name}\n"
            f"ARTIFACT REVIEW  •  {len(manifest.partition_writes)} image(s) hash-bound  •  "
            f"status {manifest.review_status.replace('-', ' ')}\n"
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
