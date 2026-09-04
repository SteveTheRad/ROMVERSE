from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from romverse.core.settings import ExperienceMode
from romverse.rom.models import ProjectError
from romverse.rom.simulation import (
    PartitionIntent,
    RomSimulationReceipt,
    RomSimulationService,
    SimulationPlanEdit,
    SimulationSeverity,
)
from romverse.ui.formatters import human_bytes


class DigitalTwinPhone(QWidget):
    """Animated, brand-neutral exploded partition model."""

    def __init__(
        self,
        receipt: RomSimulationReceipt,
        *,
        reduced_motion: bool = False,
    ) -> None:
        super().__init__()
        self.receipt = receipt
        self.pulse = 0
        self.setMinimumSize(330, 440)
        self.setAccessibleName("Animated exploded Android partition model")
        self.timer = QTimer(self)
        self.timer.setInterval(90)
        self.timer.timeout.connect(self._advance)
        if not reduced_motion:
            self.timer.start()

    def set_receipt(self, receipt: RomSimulationReceipt) -> None:
        self.receipt = receipt
        self.pulse = 0
        self.update()

    def _advance(self) -> None:
        self.pulse = (self.pulse + 1) % 120
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width()
        body = QRectF(width * 0.18, 22, width * 0.64, self.height() - 44)
        glow = QColor(48, 220, 238, 38 + abs(60 - self.pulse) // 2)
        painter.setPen(QPen(glow, 14))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(body.adjusted(-4, -4, 4, 4), 34, 34)
        painter.setPen(QPen(QColor("#3BCFE2"), 2))
        shell = QLinearGradient(body.topLeft(), body.bottomRight())
        shell.setColorAt(0, QColor("#08172A"))
        shell.setColorAt(0.55, QColor("#07101E"))
        shell.setColorAt(1, QColor("#140B25"))
        painter.setBrush(shell)
        painter.drawRoundedRect(body, 30, 30)
        painter.setPen(QPen(QColor("#536987"), 1))
        painter.drawRoundedRect(body.adjusted(9, 12, -9, -12), 23, 23)
        painter.setBrush(QColor("#5DE5F2"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(body.center().x() - 3, body.top() + 9, 6, 6))

        partitions = self.receipt.partitions[:12]
        if not partitions:
            painter.setPen(QPen(QColor("#91A2BC"), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for index in range(4):
                inset = 34 + index * 15
                painter.drawRoundedRect(body.adjusted(inset, inset, -inset, -inset), 12, 12)
            painter.setPen(QColor("#C9D7EA"))
            painter.drawText(
                body.adjusted(24, 0, -24, 0),
                Qt.AlignmentFlag.AlignCenter,
                "PARTITION MAP\nAWAITING EVIDENCE",
            )
            return

        active = (self.pulse // 10) % len(partitions)
        usable_height = body.height() - 76
        block_height = min(31.0, usable_height / max(1, len(partitions)))
        stack_height = block_height * len(partitions)
        top = body.center().y() - stack_height / 2
        for index, partition in enumerate(partitions):
            explode = abs(index - (len(partitions) - 1) / 2) * 1.8
            rect = QRectF(
                body.left() + 28 - explode,
                top + index * block_height,
                body.width() - 56 + explode * 2,
                block_height - 4,
            )
            is_active = index == active
            if partition.status is SimulationSeverity.BLOCKED:
                color = QColor("#FF557A")
            elif partition.intent is PartitionIntent.WRITE:
                color = QColor("#9B62F5")
            else:
                color = QColor("#36D5E7")
            painter.setPen(QPen(color.lighter(145) if is_active else color, 2))
            fill = QColor(color)
            fill.setAlpha(105 if is_active else 45)
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, 6, 6)
            painter.setPen(QColor("#FFFFFF") if is_active else QColor("#B9C9DF"))
            label = partition.name
            if partition.target_slot not in {"", "none", "unchanged"}:
                label += f"  •  SLOT {partition.target_slot.upper()}"
            painter.drawText(
                rect.adjusted(10, 0, -8, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                label.upper(),
            )
        painter.setPen(QColor("#64E8F4"))
        painter.drawText(
            QRectF(0, body.bottom() - 29, width, 18),
            Qt.AlignmentFlag.AlignCenter,
            "DEVICE DNA • DIGITAL TWIN",
        )


class ExpertSimulationEditor(QDialog):
    def __init__(self, receipt: RomSimulationReceipt, parent=None) -> None:
        super().__init__(parent)
        self.receipt = receipt
        self.edit: SimulationPlanEdit | None = None
        self.setWindowTitle("ROMVERSE • Expert Digital Twin Editor")
        self.setMinimumWidth(650)
        self.setStyleSheet(DigitalTwinDialog.stylesheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        heading = QLabel("EXPERT WHAT-IF REVISION")
        heading.setObjectName("TwinEyebrow")
        title = QLabel("Inspect a different simulated sequence")
        title.setObjectName("TwinTitle")
        detail = QLabel(
            "This changes only the simulation receipt. A moved or excluded operation loses "
            "Device Pack authority and cannot become a real mission until a new contract is "
            "independently reviewed."
        )
        detail.setObjectName("TwinCopy")
        detail.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(title)
        layout.addWidget(detail)
        form = QFormLayout()
        self.operation = QComboBox()
        for item in receipt.operations:
            self.operation.addItem(
                f"{item.order:02d}  •  {item.label}",
                item.operation_id,
            )
        self.action = QComboBox()
        self.action.addItem("Move operation", "move")
        self.action.addItem("Exclude operation", "exclude")
        self.order = QSpinBox()
        self.order.setRange(1, max(1, len(receipt.operations)))
        self.order.setValue(1)
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Why should this what-if change be investigated?")
        form.addRow("Operation", self.operation)
        form.addRow("Simulation change", self.action)
        form.addRow("New sequence position", self.order)
        form.addRow("Reason", self.reason)
        layout.addLayout(form)
        warning = QLabel(
            "EXPERT MODE DOES NOT BYPASS WRONG-DEVICE, ARTIFACT-INTEGRITY, "
            "DANGEROUS-COMMAND OR BOOTLOADER-RELOCK PROTECTION."
        )
        warning.setObjectName("TwinWarning")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        apply = QPushButton("Create inert revision")
        apply.setObjectName("TwinPrimary")
        apply.clicked.connect(self._apply)
        actions.addWidget(cancel)
        actions.addWidget(apply)
        layout.addLayout(actions)
        self.operation.currentIndexChanged.connect(self._sync_order)
        self._sync_order()

    def _sync_order(self) -> None:
        selected = str(self.operation.currentData())
        current = next(
            (item for item in self.receipt.operations if item.operation_id == selected),
            None,
        )
        if current is not None:
            self.order.setValue(current.order)

    def _apply(self) -> None:
        reason = self.reason.text().strip()
        if not reason:
            QMessageBox.warning(
                self,
                "Reason required",
                "Explain why this expert what-if change should be investigated.",
            )
            return
        self.edit = SimulationPlanEdit(
            str(self.operation.currentData()),
            str(self.action.currentData()),
            self.order.value(),
            reason,
        )
        self.accept()


class DigitalTwinDialog(QDialog):
    def __init__(
        self,
        service: RomSimulationService,
        receipt: RomSimulationReceipt,
        experience_mode: ExperienceMode,
        parent=None,
        *,
        reduced_motion: bool = False,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.receipt = receipt
        self.experience_mode = experience_mode
        self.reduced_motion = reduced_motion
        self.setWindowTitle("ROMVERSE • ROM Simulation Lab")
        self.setMinimumSize(1080, 720)
        self.resize(1320, 860)
        self.setStyleSheet(self.stylesheet())
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._header())
        scroll = QScrollArea()
        scroll.setObjectName("TwinScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        self.content = QVBoxLayout(host)
        self.content.setContentsMargins(30, 24, 30, 24)
        self.content.setSpacing(16)
        self.content.addWidget(self._overview())
        self.findings_layout = QVBoxLayout()
        self.content.addWidget(self._section("EVIDENCE FINDINGS", self.findings_layout))
        self.sequence_layout = QVBoxLayout()
        self.content.addWidget(self._section("REHEARSED COMMAND ORDER", self.sequence_layout))
        self.limits_layout = QVBoxLayout()
        self.content.addWidget(self._section("WHAT HARDWARE MUST STILL PROVE", self.limits_layout))
        self.content.addStretch(1)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)
        root.addWidget(self._footer())
        self._refresh()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        parent = self.parentWidget()
        if parent is not None:
            available = parent.window().geometry()
            self.resize(
                max(self.minimumWidth(), int(available.width() * 0.94)),
                max(self.minimumHeight(), int(available.height() * 0.94)),
            )
            frame = self.frameGeometry()
            frame.moveCenter(parent.window().frameGeometry().center())
            self.move(frame.topLeft())

    def _header(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("TwinHeader")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(30, 22, 30, 22)
        copy = QVBoxLayout()
        eyebrow = QLabel("ROM SIMULATION LAB  •  DEVICE DIGITAL TWIN")
        eyebrow.setObjectName("TwinEyebrow")
        title = QLabel("Rehearse the entire operation before touching hardware")
        title.setObjectName("TwinTitle")
        subtitle = QLabel(
            "Source-bound partition model • AVB and slot review • rollback rehearsal • zero device commands"
        )
        subtitle.setObjectName("TwinCopy")
        subtitle.setWordWrap(True)
        copy.addWidget(eyebrow)
        copy.addWidget(title)
        copy.addWidget(subtitle)
        layout.addLayout(copy, 1)
        self.result_badge = QLabel()
        self.result_badge.setObjectName("TwinResult")
        layout.addWidget(self.result_badge, 0, Qt.AlignmentFlag.AlignTop)
        return frame

    def _overview(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("TwinOverview")
        layout = QGridLayout(frame)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(18)
        self.phone = DigitalTwinPhone(
            self.receipt,
            reduced_motion=self.reduced_motion,
        )
        layout.addWidget(self.phone, 0, 0, 3, 1)
        identity = QFrame()
        identity.setObjectName("TwinPanel")
        identity_layout = QVBoxLayout(identity)
        identity_layout.setContentsMargins(18, 16, 18, 16)
        identity_heading = QLabel("TWIN IDENTITY")
        identity_heading.setObjectName("TwinEyebrow")
        self.identity = QLabel()
        self.identity.setObjectName("TwinPanelTitle")
        self.identity.setWordWrap(True)
        self.relationship = QLabel()
        self.relationship.setObjectName("TwinCopy")
        self.relationship.setWordWrap(True)
        identity_layout.addWidget(identity_heading)
        identity_layout.addWidget(self.identity)
        identity_layout.addWidget(self.relationship)
        layout.addWidget(identity, 0, 1)
        confidence = QFrame()
        confidence.setObjectName("TwinPanel")
        confidence_layout = QVBoxLayout(confidence)
        confidence_layout.setContentsMargins(18, 16, 18, 16)
        confidence_heading = QLabel("REHEARSAL CONFIDENCE")
        confidence_heading.setObjectName("TwinEyebrow")
        self.confidence_label = QLabel()
        self.confidence_label.setObjectName("TwinPanelTitle")
        self.confidence_bar = QProgressBar()
        self.confidence_bar.setTextVisible(True)
        confidence_layout.addWidget(confidence_heading)
        confidence_layout.addWidget(self.confidence_label)
        confidence_layout.addWidget(self.confidence_bar)
        layout.addWidget(confidence, 1, 1)
        metrics = QFrame()
        metrics.setObjectName("TwinPanel")
        metrics_layout = QGridLayout(metrics)
        metrics_layout.setContentsMargins(18, 16, 18, 16)
        self.metric_labels: list[QLabel] = []
        for index, heading in enumerate(
            ("WRITE VOLUME", "ESTIMATED TIME", "BATTERY FLOOR", "WORKSPACE")
        ):
            label = QLabel()
            label.setObjectName("TwinMetric")
            label.setWordWrap(True)
            metrics_layout.addWidget(self._metric(heading, label), index // 2, index % 2)
            self.metric_labels.append(label)
        layout.addWidget(metrics, 2, 1)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 2)
        return frame

    @staticmethod
    def _metric(heading: str, value: QLabel) -> QWidget:
        frame = QFrame()
        frame.setObjectName("TwinMetricCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        title = QLabel(heading)
        title.setObjectName("TwinMetricHeading")
        layout.addWidget(title)
        layout.addWidget(value)
        return frame

    @staticmethod
    def _section(title: str, body: QVBoxLayout) -> QWidget:
        frame = QFrame()
        frame.setObjectName("TwinSection")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        heading = QLabel(title)
        heading.setObjectName("TwinEyebrow")
        layout.addWidget(heading)
        layout.addLayout(body)
        return frame

    def _footer(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("TwinFooter")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(24, 14, 24, 14)
        self.footer_status = QLabel()
        self.footer_status.setObjectName("TwinCopy")
        self.footer_status.setWordWrap(True)
        layout.addWidget(self.footer_status, 1)
        self.expert_button = QPushButton("Expert what-if editor")
        self.expert_button.setEnabled(
            self.experience_mode is ExperienceMode.EXPERT and bool(self.receipt.operations)
        )
        self.expert_button.setToolTip(
            "Available in Architect Mode; edits remain simulation-only and lose signed authority."
        )
        self.expert_button.clicked.connect(self._expert_edit)
        self.mission_button = QPushButton("Continue as ROM Studio mission")
        self.mission_button.setObjectName("TwinPrimary")
        self.mission_button.clicked.connect(self._create_mission)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        layout.addWidget(self.expert_button)
        layout.addWidget(self.mission_button)
        layout.addWidget(close)
        return frame

    def _refresh(self) -> None:
        receipt = self.receipt
        blockers = sum(item.severity is SimulationSeverity.BLOCKED for item in receipt.findings)
        attention = sum(item.severity is SimulationSeverity.ATTENTION for item in receipt.findings)
        self.result_badge.setText(
            "REHEARSAL PASSED" if receipt.successful else f"{blockers} BLOCKER(S)"
        )
        self.result_badge.setProperty("resultState", "pass" if receipt.successful else "blocked")
        self.result_badge.style().unpolish(self.result_badge)
        self.result_badge.style().polish(self.result_badge)
        self.phone.set_receipt(receipt)
        self.identity.setText(
            f"{receipt.device_name}  •  {receipt.codename or 'codename unconfirmed'}"
        )
        self.relationship.setText(
            receipt.firmware_relationship or "Firmware relationship needs fresh Device DNA."
        )
        self.confidence_label.setText(
            f"{receipt.confidence_percent}%  •  {receipt.confidence_label}"
        )
        self.confidence_bar.setValue(receipt.confidence_percent)
        minutes, seconds = divmod(receipt.estimated_seconds, 60)
        battery = (
            f"{receipt.minimum_battery_percent}% minimum • "
            f"{receipt.observed_battery_percent}% observed"
            if receipt.observed_battery_percent >= 0
            else f"{receipt.minimum_battery_percent}% minimum • live reading required"
        )
        values = (
            f"{human_bytes(receipt.total_write_bytes)}\n{len(receipt.partitions)} mapped partition(s)",
            f"{minutes}m {seconds:02d}s\nmodel estimate",
            battery,
            f"{human_bytes(receipt.required_workspace_bytes)} needed\n"
            f"{human_bytes(receipt.available_workspace_bytes)} free",
        )
        for label, value in zip(self.metric_labels, values, strict=True):
            label.setText(value)
        self._clear(self.findings_layout)
        for finding in receipt.findings:
            self.findings_layout.addWidget(self._finding_card(finding))
        self._clear(self.sequence_layout)
        if receipt.operations:
            for operation in receipt.operations:
                self.sequence_layout.addWidget(self._operation_card(operation))
        else:
            empty = QLabel(
                "No exact command sequence can be generated until the missing contract evidence is supplied."
            )
            empty.setObjectName("TwinCopy")
            empty.setWordWrap(True)
            self.sequence_layout.addWidget(empty)
        self._clear(self.limits_layout)
        for unknown in receipt.hardware_unknowns:
            label = QLabel(f"◇  {unknown}")
            label.setObjectName("TwinCopy")
            label.setWordWrap(True)
            self.limits_layout.addWidget(label)
        self.mission_button.setEnabled(receipt.mission_ready)
        self.expert_button.setEnabled(
            self.experience_mode is ExperienceMode.EXPERT and bool(receipt.operations)
        )
        self.footer_status.setText(
            f"{len(receipt.operations)} operation(s) rehearsed  •  {blockers} blocked  •  "
            f"{attention} need attention  •  PHONE CHANGED: NO"
        )

    @staticmethod
    def _clear(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    @staticmethod
    def _finding_card(finding) -> QWidget:
        card = QFrame()
        card.setObjectName("TwinFinding")
        card.setProperty("severity", finding.severity.value)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 11, 14, 11)
        symbol = QLabel(
            "✓"
            if finding.severity is SimulationSeverity.VERIFIED
            else "!"
            if finding.severity is SimulationSeverity.ATTENTION
            else "×"
        )
        symbol.setObjectName("TwinSymbol")
        layout.addWidget(symbol)
        copy = QVBoxLayout()
        title = QLabel(finding.title)
        title.setObjectName("TwinFindingTitle")
        detail = QLabel(f"{finding.detail}  •  {finding.resolution}")
        detail.setObjectName("TwinCopy")
        detail.setWordWrap(True)
        copy.addWidget(title)
        copy.addWidget(detail)
        layout.addLayout(copy, 1)
        badge = QLabel(finding.severity.value.upper())
        badge.setObjectName("TwinFindingBadge")
        layout.addWidget(badge)
        return card

    @staticmethod
    def _operation_card(operation) -> QWidget:
        card = QFrame()
        card.setObjectName("TwinOperation")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        number = QLabel(f"{operation.order:02d}")
        number.setObjectName("TwinOrder")
        layout.addWidget(number)
        copy = QVBoxLayout()
        title = QLabel(operation.label)
        title.setObjectName("TwinFindingTitle")
        detail_parts = [
            operation.phase.upper(),
            operation.transport,
            f"slot {operation.target_slot}" if operation.target_slot else "",
            human_bytes(operation.size_bytes) if operation.size_bytes else "",
            f"~{operation.estimated_seconds}s",
        ]
        detail = QLabel("  •  ".join(part for part in detail_parts if part))
        detail.setObjectName("TwinCopy")
        copy.addWidget(title)
        copy.addWidget(detail)
        layout.addLayout(copy, 1)
        result = QLabel(operation.result)
        result.setObjectName("TwinOperationResult")
        result.setWordWrap(True)
        result.setMaximumWidth(330)
        layout.addWidget(result)
        return card

    def _expert_edit(self) -> None:
        editor = ExpertSimulationEditor(self.receipt, self)
        if editor.exec() != QDialog.DialogCode.Accepted or editor.edit is None:
            return
        try:
            self.receipt = self.service.revise(self.receipt, (editor.edit,))
        except ProjectError as exc:
            QMessageBox.warning(self, "Revision rejected", str(exc))
            return
        self._refresh()

    def _create_mission(self) -> None:
        try:
            mission = self.service.create_mission(self.receipt)
        except ProjectError as exc:
            QMessageBox.warning(self, "Mission remains locked", str(exc))
            return
        self.footer_status.setText(
            f"ROM Studio mission {mission.mission_id[:12]}… created from this exact rehearsal  •  "
            "Guardian final consent remains separate  •  PHONE CHANGED: NO"
        )
        self.mission_button.setEnabled(False)
        self.mission_button.setText("Mission prepared")

    @staticmethod
    def stylesheet() -> str:
        return """
            QDialog, QWidget { background: #02050A; color: #ECF5FF; }
            QLabel { background: transparent; }
            QScrollArea#TwinScroll { border: none; background: #02050A; }
            QFrame#TwinHeader {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #0B172A, stop:.54 #081222, stop:1 #180C2D);
                border-bottom: 1px solid #2E5274;
            }
            QFrame#TwinFooter {
                background: #050B14; border-top: 1px solid #203A58;
            }
            QFrame#TwinOverview, QFrame#TwinSection {
                background: #050B14; border: 1px solid #203A58; border-radius: 14px;
            }
            QFrame#TwinPanel {
                background: #07101D; border: 1px solid #284462; border-radius: 12px;
            }
            QFrame#TwinMetricCard {
                background: #050C17; border: 1px solid #1C3551; border-radius: 9px;
            }
            QLabel#TwinEyebrow {
                color: #55DFEE; font-size: 11px; font-weight: 900; letter-spacing: 1.4px;
            }
            QLabel#TwinTitle { color: #FFFFFF; font-size: 24px; font-weight: 900; }
            QLabel#TwinPanelTitle { color: #FFFFFF; font-size: 18px; font-weight: 850; }
            QLabel#TwinCopy { color: #9FAEC4; font-size: 12px; }
            QLabel#TwinMetricHeading {
                color: #748AA8; font-size: 9px; font-weight: 850; letter-spacing: 1px;
            }
            QLabel#TwinMetric { color: #EAF4FF; font-size: 13px; font-weight: 750; }
            QLabel#TwinResult {
                color: #FF7996; background: #240A13; border: 1px solid #96304A;
                border-radius: 12px; padding: 9px 14px; font-weight: 900;
            }
            QLabel#TwinResult[resultState="pass"] {
                color: #5DEDB0; background: #061B14; border-color: #187653;
            }
            QFrame#TwinFinding {
                background: #07101A; border: 1px solid #28405E; border-radius: 9px;
            }
            QFrame#TwinFinding[severity="verified"] { border-left: 3px solid #39DB9A; }
            QFrame#TwinFinding[severity="attention"] { border-left: 3px solid #F6B94F; }
            QFrame#TwinFinding[severity="blocked"] { border-left: 3px solid #F35C7A; }
            QLabel#TwinSymbol { color: #64E8B4; font-size: 19px; font-weight: 900; }
            QFrame#TwinFinding[severity="attention"] QLabel#TwinSymbol { color: #F6C66C; }
            QFrame#TwinFinding[severity="blocked"] QLabel#TwinSymbol { color: #FF7894; }
            QLabel#TwinFindingTitle { color: #F0F6FF; font-size: 13px; font-weight: 800; }
            QLabel#TwinFindingBadge {
                color: #A9C4DE; font-size: 9px; font-weight: 900; letter-spacing: 1px;
            }
            QFrame#TwinOperation {
                background: #060D17; border: 1px solid #1D354F; border-radius: 9px;
            }
            QLabel#TwinOrder {
                color: #57E1EF; background: #0B2431; border: 1px solid #266C7A;
                border-radius: 16px; min-width: 32px; min-height: 32px;
                font-size: 11px; font-weight: 900;
            }
            QLabel#TwinOperationResult { color: #86D8C0; font-size: 10px; font-weight: 750; }
            QLabel#TwinWarning {
                color: #FFD080; background: #211707; border: 1px solid #795921;
                border-radius: 9px; padding: 12px; font-weight: 800;
            }
            QProgressBar {
                color: #FFFFFF; background: #07101B; border: 1px solid #29445F;
                border-radius: 7px; min-height: 16px; text-align: center;
            }
            QProgressBar::chunk {
                border-radius: 6px;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #8E4DE8, stop:1 #35D7E6);
            }
            QPushButton {
                color: #D9E7F8; background: #0A1421; border: 1px solid #355577;
                border-radius: 9px; padding: 10px 15px; font-weight: 750;
            }
            QPushButton:hover { color: #FFFFFF; border-color: #58DCEB; background: #102237; }
            QPushButton:disabled { color: #526174; border-color: #263447; background: #070C13; }
            QPushButton#TwinPrimary {
                color: #071510; background: #43DEA4; border-color: #7EF1C4;
            }
            QLineEdit, QComboBox, QSpinBox {
                color: #F2F7FF; background: #07101E; border: 1px solid #355276;
                border-radius: 8px; padding: 9px;
            }
        """
