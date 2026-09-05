from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from romverse.guardian.recovery_consent import GuardianRecoveryConsentReceiptService
from romverse.guardian.recovery_live_target import GuardianRecoveryLiveTargetReceipt
from romverse.guardian.recovery_preparation import GuardianRecoveryPreparation


class RecoveryConsentDialog(QDialog):
    """One clear human decision for an exact, currently verified Recovery plan."""

    def __init__(
        self,
        preparation: GuardianRecoveryPreparation,
        live_target: GuardianRecoveryLiveTargetReceipt,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm this Recovery plan")
        self.setModal(True)
        self.setMinimumWidth(720)
        self.setMinimumHeight(560)

        page = QVBoxLayout(self)
        page.setContentsMargins(24, 22, 24, 22)
        page.setSpacing(14)

        eyebrow = QLabel("RECOVERY CONSENT  •  ONE EXACT DECISION")
        eyebrow.setObjectName("Eyebrow")
        page.addWidget(eyebrow)
        title = QLabel(f"Confirm Recovery for {preparation.device_name}")
        title.setObjectName("Title")
        title.setTextFormat(Qt.TextFormat.PlainText)
        page.addWidget(title)

        summary = QLabel(
            f"ROMVERSE freshly matched {live_target.observed_product} in "
            f"{live_target.observed_entry_mode}. Review the complete sealed plan below. "
            "Recording consent does not start Recovery or change the phone."
        )
        summary.setObjectName("Muted")
        summary.setWordWrap(True)
        summary.setTextFormat(Qt.TextFormat.PlainText)
        page.addWidget(summary)

        consequence = QFrame()
        consequence.setObjectName("Card")
        consequence_layout = QVBoxLayout(consequence)
        consequence_layout.setContentsMargins(18, 15, 18, 15)
        consequence_title = QLabel(
            "THIS PLAN MAY ERASE USER DATA"
            if preparation.may_wipe_user_data
            else "USER-DATA ERASURE IS NOT DECLARED BY THIS PLAN"
        )
        consequence_title.setObjectName("Danger" if preparation.may_wipe_user_data else "Good")
        consequence_layout.addWidget(consequence_title)
        consequence_detail = QLabel(
            "Backups and Recovery evidence reduce risk but cannot guarantee that personal data "
            "will survive a repair. Continue only if you accept the complete consequence."
            if preparation.may_wipe_user_data
            else "Unexpected failure can still cause data loss. A verified backup remains "
            "important before any later execution."
        )
        consequence_detail.setWordWrap(True)
        consequence_detail.setTextFormat(Qt.TextFormat.PlainText)
        consequence_layout.addWidget(consequence_detail)
        page.addWidget(consequence)

        steps = QLabel()
        steps.setTextFormat(Qt.TextFormat.PlainText)
        steps.setWordWrap(True)
        steps.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        steps.setText(
            "\n\n".join(
                f"{item.order:02d}  {item.effect}\n"
                f"{item.from_mode} → {item.to_mode}"
                + ("  •  MAY ERASE USER DATA" if item.may_wipe_user_data else "")
                for item in GuardianRecoveryConsentReceiptService.consequences(preparation)
            )
        )
        scroll = QScrollArea()
        scroll.setObjectName("RecoveryConsentSteps")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(steps)
        page.addWidget(scroll, 1)

        boundary = QLabel(
            "By continuing, you confirm this exact phone and complete plan, accept the displayed "
            "data-loss risk, understand that unknown writes are never blindly retried, and agree "
            "that bootloader relocking is prohibited. Post-repair verification is still required. "
            "Consent expires with the phone check."
        )
        boundary.setObjectName("Muted")
        boundary.setWordWrap(True)
        boundary.setTextFormat(Qt.TextFormat.PlainText)
        page.addWidget(boundary)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.confirm_button = QPushButton("I understand — record consent")
        self.confirm_button.setObjectName("Primary")
        self.confirm_button.setAccessibleName(
            "Record short-lived consent for this exact Recovery plan"
        )
        self.confirm_button.clicked.connect(self.accept)
        buttons.addButton(self.confirm_button, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.rejected.connect(self.reject)
        page.addWidget(buttons)
