from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QObject, Qt, Signal, Slot
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
    def __init__(self, audit: GuardianAuditStore | None) -> None:
        super().__init__()
        self.audit = audit
        self.worker: GuardianCenterWorker | None = None
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
        self.refresh()

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
        if self.audit is None:
            self.integrity_badge.setText("AUDIT UNAVAILABLE")
            self.integrity_badge.setObjectName("Warning")
            self.integrity_detail.setText("No audit store is attached to this application session.")
            self._repolish(self.integrity_badge)
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
        start_background(worker)

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
