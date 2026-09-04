from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from romverse.rom.first_light import (
    FirstLightEvidenceKind,
    FirstLightOverall,
    FirstLightReport,
    FirstLightService,
    FirstLightStatus,
)
from romverse.rom.models import ProjectError

STATUS_COPY = {
    FirstLightStatus.WORKING: "Working",
    FirstLightStatus.DEGRADED: "Degraded",
    FirstLightStatus.UNTESTED: "Untested",
    FirstLightStatus.FAILED: "Failed",
    FirstLightStatus.NOT_APPLICABLE: "Not applicable",
}


class FirstLightOrbit(QWidget):
    """Motion-safe subsystem map; its colours come only from recorded evidence."""

    def __init__(
        self,
        report: FirstLightReport,
        parent=None,
        *,
        reduced_motion: bool = False,
    ) -> None:
        super().__init__(parent)
        self.report = report
        self.phase = 0
        self.setMinimumSize(360, 310)
        self.setAccessibleName("First Light subsystem validation orbit")
        self.timer = QTimer(self)
        self.timer.setInterval(85)
        self.timer.timeout.connect(self._advance)
        if not reduced_motion:
            self.timer.start()

    def set_report(self, report: FirstLightReport) -> None:
        self.report = report
        self.update()

    def _advance(self) -> None:
        self.phase = (self.phase + 1) % 180
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        background = QLinearGradient(0, 0, self.width(), self.height())
        background.setColorAt(0, QColor("#071426"))
        background.setColorAt(0.58, QColor("#070D19"))
        background.setColorAt(1, QColor("#170A29"))
        painter.fillRect(self.rect(), background)
        center_x = self.width() / 2
        center_y = self.height() / 2
        radius_x = max(112.0, self.width() * 0.38)
        radius_y = max(92.0, self.height() * 0.34)
        pulse = abs(90 - self.phase) / 90
        painter.setPen(QPen(QColor(88, 211, 237, 42), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(
            QRectF(center_x - radius_x, center_y - radius_y, radius_x * 2, radius_y * 2)
        )
        colours = {
            FirstLightStatus.WORKING: QColor("#59E7B1"),
            FirstLightStatus.DEGRADED: QColor("#FFB84A"),
            FirstLightStatus.UNTESTED: QColor("#5F7393"),
            FirstLightStatus.FAILED: QColor("#FF5B78"),
            FirstLightStatus.NOT_APPLICABLE: QColor("#8C9AB0"),
        }
        for index, item in enumerate(self.report.subsystems):
            angle = (math.tau * index / len(self.report.subsystems)) - math.pi / 2
            x = center_x + math.cos(angle) * radius_x
            y = center_y + math.sin(angle) * radius_y
            colour = colours[item.status]
            glow = QColor(colour)
            glow.setAlpha(28 + int(25 * pulse) if item.status is FirstLightStatus.WORKING else 24)
            painter.setPen(QPen(glow, 8))
            painter.setBrush(colour)
            painter.drawEllipse(QRectF(x - 5, y - 5, 10, 10))
        overall_colour = {
            FirstLightOverall.VERIFIED: QColor("#59E7B1"),
            FirstLightOverall.DEGRADED: QColor("#FFB84A"),
            FirstLightOverall.FAILED: QColor("#FF5B78"),
            FirstLightOverall.INCOMPLETE: QColor("#9D68F5"),
        }[self.report.overall]
        painter.setPen(
            QPen(
                QColor(overall_colour.red(), overall_colour.green(), overall_colour.blue(), 50), 14
            )
        )
        painter.setBrush(QColor("#081523"))
        painter.drawEllipse(QRectF(center_x - 61, center_y - 61, 122, 122))
        painter.setPen(QPen(overall_colour, 2.3))
        painter.drawEllipse(QRectF(center_x - 61, center_y - 61, 122, 122))
        passed = sum(
            item.status in {FirstLightStatus.WORKING, FirstLightStatus.NOT_APPLICABLE}
            for item in self.report.subsystems
        )
        painter.setPen(QColor("#F4FAFF"))
        painter.drawText(
            QRectF(center_x - 55, center_y - 42, 110, 84),
            Qt.AlignmentFlag.AlignCenter,
            f"FIRST LIGHT\n{passed} / {len(self.report.subsystems)}\n{self.report.overall.value.upper()}",
        )
        painter.setPen(QColor("#8296B4"))
        painter.drawText(
            QRectF(18, self.height() - 26, self.width() - 36, 18),
            Qt.AlignmentFlag.AlignCenter,
            "COLOUR MEANS RECORDED EVIDENCE — NEVER ASSUMED SUCCESS",
        )


class FirstLightObservationDialog(QDialog):
    def __init__(self, subsystem, parent=None) -> None:
        super().__init__(parent)
        self.subsystem = subsystem
        self.observation: tuple[FirstLightStatus, str, str] | None = None
        self.setWindowTitle(f"ROMVERSE • Record {subsystem.label}")
        self.setMinimumSize(700, 430)
        self.resize(760, 470)
        self.setStyleSheet(FirstLightDialog.stylesheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        eyebrow = QLabel("FIRST LIGHT  /  USER-OBSERVED CHECK")
        eyebrow.setObjectName("FirstEyebrow")
        title = QLabel(subsystem.label)
        title.setObjectName("FirstTitle")
        detail = QLabel(
            "Record what was actually tested on the phone. ROMVERSE labels this as a user "
            "observation; it does not turn it into an automated measurement."
        )
        detail.setObjectName("FirstCopy")
        detail.setWordWrap(True)
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(detail)
        self.status = QComboBox()
        for value in (
            FirstLightStatus.WORKING,
            FirstLightStatus.DEGRADED,
            FirstLightStatus.FAILED,
            FirstLightStatus.NOT_APPLICABLE,
            FirstLightStatus.UNTESTED,
        ):
            self.status.addItem(STATUS_COPY[value], value)
        self.status.setCurrentIndex(max(0, self.status.findData(subsystem.status)))
        self.evidence = QTextEdit()
        self.evidence.setMaximumHeight(105)
        self.evidence.setPlaceholderText(
            "What did you test, and what did you observe? Include repeatable details."
        )
        if subsystem.status is not FirstLightStatus.UNTESTED:
            self.evidence.setPlainText(subsystem.evidence)
        self.note = QLineEdit(subsystem.note)
        self.note.setPlaceholderText(
            "Optional context, environment, cable, vehicle, app, or conditions"
        )
        for label, widget in (
            ("RESULT", self.status),
            ("OBSERVED EVIDENCE", self.evidence),
            ("OPTIONAL NOTE", self.note),
        ):
            field = QLabel(label)
            field.setObjectName("FirstEyebrow")
            layout.addWidget(field)
            layout.addWidget(widget)
        provenance = QLabel(
            "Evidence source: USER OBSERVED  •  No phone command runs from this dialog."
        )
        provenance.setObjectName("FirstNotice")
        provenance.setWordWrap(True)
        layout.addWidget(provenance)
        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save measured result")
        save.setObjectName("FirstPrimary")
        save.clicked.connect(self._save)
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)

    def _save(self) -> None:
        evidence = self.evidence.toPlainText().strip()
        if not evidence:
            QMessageBox.warning(
                self,
                "Observed evidence required",
                "Describe the check and the result. ROMVERSE will not infer a pass.",
            )
            return
        self.observation = (
            FirstLightStatus(self.status.currentData()),
            evidence,
            self.note.text(),
        )
        self.accept()


class FirstLightDialog(QDialog):
    def __init__(
        self,
        service: FirstLightService,
        report: FirstLightReport,
        parent=None,
        *,
        reduced_motion: bool = False,
        knowledge_lookup=None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.report = report
        self.knowledge_lookup = knowledge_lookup
        self.setWindowTitle("ROMVERSE • First Light")
        self.setMinimumSize(1080, 720)
        self.resize(1360, 900)
        self.setStyleSheet(self.stylesheet())
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._header())
        scroll = QScrollArea()
        scroll.setObjectName("FirstScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        content = QVBoxLayout(host)
        content.setContentsMargins(28, 22, 28, 22)
        content.setSpacing(15)
        overview = QFrame()
        overview.setObjectName("FirstPanel")
        overview_layout = QGridLayout(overview)
        overview_layout.setContentsMargins(18, 18, 18, 18)
        overview_layout.setSpacing(15)
        self.orbit = FirstLightOrbit(report, self, reduced_motion=reduced_motion)
        overview_layout.addWidget(self.orbit, 0, 0, 4, 1)
        self.identity = QLabel()
        self.identity.setObjectName("FirstIdentity")
        self.identity.setWordWrap(True)
        self.baseline = QLabel()
        self.baseline.setObjectName("FirstCopy")
        self.baseline.setWordWrap(True)
        explanation = QLabel(
            "First Light begins only after a stable, Guardian-linked first boot. Read-only "
            "identity checks are automatic; hardware and daily-use checks remain explicitly "
            "user- or Companion-observed. Unknown stays untested."
        )
        explanation.setObjectName("FirstCopy")
        explanation.setWordWrap(True)
        overview_layout.addWidget(self._eyebrow("EVIDENCE CHAIN"), 0, 1)
        overview_layout.addWidget(self.identity, 1, 1)
        overview_layout.addWidget(self._eyebrow("BEFORE / AFTER BASELINE"), 2, 1)
        overview_layout.addWidget(self.baseline, 3, 1)
        overview_layout.addWidget(explanation, 4, 0, 1, 2)
        overview_layout.setColumnStretch(0, 3)
        overview_layout.setColumnStretch(1, 5)
        content.addWidget(overview)
        section = QFrame()
        section.setObjectName("FirstPanel")
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(18, 15, 18, 18)
        section_layout.addWidget(self._eyebrow("SUBSYSTEM FLIGHT CHECKS"))
        self.checks = QGridLayout()
        self.checks.setSpacing(10)
        section_layout.addLayout(self.checks)
        content.addWidget(section)
        content.addStretch(1)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)
        root.addWidget(self._footer())
        self._render()

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
        frame.setObjectName("FirstHeader")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(30, 21, 30, 21)
        copy = QVBoxLayout()
        copy.addWidget(self._eyebrow("FIRST LIGHT  •  POST-FLASH VALIDATION"))
        title = QLabel("Prove the new ROM works beyond the boot animation")
        title.setObjectName("FirstTitle")
        subtitle = QLabel(
            "Guardian-linked boot • baseline comparison • subsystem evidence • offline diagnosis routing"
        )
        subtitle.setObjectName("FirstCopy")
        subtitle.setWordWrap(True)
        copy.addWidget(title)
        copy.addWidget(subtitle)
        layout.addLayout(copy, 1)
        self.badge = QLabel()
        self.badge.setObjectName("FirstBadge")
        layout.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)
        return frame

    def _footer(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("FirstFooter")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(22, 11, 22, 13)
        self.footer_status = QLabel()
        self.footer_status.setObjectName("FirstCopy")
        self.footer_status.setWordWrap(True)
        layout.addWidget(self.footer_status)
        actions = QHBoxLayout()
        self.refresh_button = QPushButton("Reload evidence")
        self.refresh_button.clicked.connect(self._reload)
        self.diagnose_button = QPushButton("Scan offline Archives")
        self.diagnose_button.clicked.connect(self._diagnose)
        self.export_button = QPushButton("Export tester report")
        self.export_button.setObjectName("FirstPrimary")
        self.export_button.clicked.connect(self._export)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.diagnose_button)
        actions.addWidget(self.export_button)
        actions.addStretch(1)
        actions.addWidget(close)
        layout.addLayout(actions)
        return frame

    def _render(self) -> None:
        self.orbit.set_report(self.report)
        passed = sum(
            item.status in {FirstLightStatus.WORKING, FirstLightStatus.NOT_APPLICABLE}
            for item in self.report.subsystems
        )
        problems = sum(
            item.status in {FirstLightStatus.DEGRADED, FirstLightStatus.FAILED}
            for item in self.report.subsystems
        )
        self.badge.setText(self.report.overall.value.upper())
        self.badge.setProperty("state", self.report.overall.value)
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)
        self.identity.setText(
            f"Expected build: {self.report.expected_build_id}\n"
            f"Observed build: {self.report.observed_build_id or 'unavailable'}\n"
            f"Pack: {self.report.pack_id}  •  Guardian: "
            f"{self.report.guardian_execution_receipt_digest[:16]}…\n"
            f"Boot receipt: {self.report.boot_observation_digest[:16]}…"
        )
        self.baseline.setText(self._baseline_copy())
        self._clear(self.checks)
        for index, item in enumerate(self.report.subsystems):
            self.checks.addWidget(self._check_card(item), index // 2, index % 2)
        self.diagnose_button.setEnabled(FirstLightService.needs_knowledge_lookup(self.report))
        self.footer_status.setText(
            f"{passed} of {len(self.report.subsystems)} resolved  •  {problems} need attention  •  "
            f"PUBLIC RELEASE READY: {'YES' if self.report.public_release_ready else 'NO'}  •  "
            "PHONE CHANGED BY FIRST LIGHT: NO"
        )

    def _baseline_copy(self) -> str:
        if not self.report.baseline_changes:
            return (
                "No verified pre-flash Device Passport was available at the Guardian operation "
                "time. Post-flash checks remain valid, but before/after fields stay unknown."
            )
        return "\n".join(
            f"{item.label}: {item.before}  →  {item.after}  [{item.state.upper()}]"
            for item in self.report.baseline_changes
        )

    def _check_card(self, item) -> QWidget:
        card = QFrame()
        card.setObjectName("FirstCheck")
        card.setProperty("state", item.status.value)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(13, 11, 13, 11)
        copy = QVBoxLayout()
        heading = QLabel(f"{item.label}  •  {STATUS_COPY[item.status].upper()}")
        heading.setObjectName("FirstCheckTitle")
        detail = QLabel(
            f"{item.evidence}\nSource: {item.evidence_kind.value}"
            + (f"  •  Note: {item.note}" if item.note else "")
        )
        detail.setObjectName("FirstCopy")
        detail.setWordWrap(True)
        copy.addWidget(heading)
        copy.addWidget(detail)
        layout.addLayout(copy, 1)
        action = QPushButton(
            "Verified automatically"
            if item.subsystem_id in self.service.AUTOMATED_IDS
            else "Record result"
        )
        action.setEnabled(item.subsystem_id not in self.service.AUTOMATED_IDS)
        if action.isEnabled():
            action.clicked.connect(lambda _checked=False, value=item: self._record(value))
        layout.addWidget(action)
        return card

    def _record(self, subsystem) -> None:
        dialog = FirstLightObservationDialog(subsystem, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.observation is None:
            return
        status, evidence, note = dialog.observation
        try:
            self.report = self.service.record_observation(
                self.report,
                subsystem.subsystem_id,
                status,
                FirstLightEvidenceKind.USER,
                evidence,
                note,
            )
        except (OSError, ProjectError) as exc:
            QMessageBox.warning(self, "First Light result was not saved", str(exc))
            return
        self._render()
        if FirstLightService.needs_knowledge_lookup(self.report):
            self._diagnose(automatic=True)

    def _reload(self) -> None:
        current = self.service.load(self.report.project_id)
        if current is None:
            QMessageBox.warning(
                self,
                "First Light evidence unavailable",
                "The saved report is missing or failed integrity verification.",
            )
            return
        self.report = current
        self._render()

    def _diagnose(self, _checked=False, *, automatic: bool = False) -> None:
        failure = FirstLightService.knowledge_failure(self.report)
        if failure is None or self.knowledge_lookup is None:
            if not automatic:
                QMessageBox.information(
                    self,
                    "No diagnosis required",
                    "Record a degraded or failed subsystem before scanning the offline Archives.",
                )
            return
        try:
            result = self.knowledge_lookup(failure)
        except (OSError, ProjectError) as exc:
            self.footer_status.setText(f"Offline Archives scan could not complete: {exc}")
            return
        matches = len(result.matches) if result is not None else 0
        self.footer_status.setText(
            f"Offline Archives scanned automatically  •  {matches} compatible match(es)  •  "
            "guidance only; no repair or phone command was run"
        )

    def _export(self) -> None:
        destination = QFileDialog.getExistingDirectory(
            self,
            "Choose tester-report destination",
            str(Path.home()),
        )
        if not destination:
            return
        try:
            path = self.service.export_report(self.report, Path(destination))
        except (OSError, ProjectError) as exc:
            QMessageBox.warning(self, "Tester report was not exported", str(exc))
            return
        self.footer_status.setText(
            f"Tester report exported  •  {path}  •  raw device serial included: NO"
        )

    @staticmethod
    def _eyebrow(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("FirstEyebrow")
        return label

    @staticmethod
    def _clear(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    @staticmethod
    def stylesheet() -> str:
        return """
            QDialog, QWidget { background: #030710; color: #EAF3FF; }
            QLabel { background: transparent; }
            QScrollArea#FirstScroll { border: none; background: #030710; }
            QFrame#FirstHeader {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #07182B, stop:.58 #090D1D, stop:1 #1A0B2B);
                border-bottom: 1px solid #273B5B;
            }
            QFrame#FirstFooter { background: #060B14; border-top: 1px solid #213553; }
            QFrame#FirstPanel {
                background: #07101C; border: 1px solid #223A5A; border-radius: 13px;
            }
            QFrame#FirstCheck {
                background: #081321; border: 1px solid #2A3E5C; border-radius: 10px;
            }
            QFrame#FirstCheck[state="working"] { border-left: 3px solid #59E7B1; }
            QFrame#FirstCheck[state="failed"] { border-left: 3px solid #FF5B78; }
            QFrame#FirstCheck[state="degraded"] { border-left: 3px solid #FFB84A; }
            QFrame#FirstCheck[state="untested"] { border-left: 3px solid #60728F; }
            QFrame#FirstCheck[state="not-applicable"] { border-left: 3px solid #93A2B8; }
            QLabel#FirstEyebrow { color: #58DFF0; font-size: 10px; font-weight: 800; letter-spacing: 2px; }
            QLabel#FirstTitle { color: #F5F8FF; font-size: 25px; font-weight: 800; }
            QLabel#FirstIdentity { color: #EAF3FF; font-size: 13px; font-weight: 650; }
            QLabel#FirstCheckTitle { color: #F2F7FF; font-size: 12px; font-weight: 750; }
            QLabel#FirstCopy { color: #9AADC8; font-size: 11px; }
            QLabel#FirstNotice {
                color: #FFD487; background: #20170A; border: 1px solid #71501D;
                border-radius: 8px; padding: 9px;
            }
            QLabel#FirstBadge {
                color: #EEE8FF; background: #25163E; border: 1px solid #8F58E5;
                border-radius: 11px; padding: 8px 13px; font-weight: 800;
            }
            QLabel#FirstBadge[state="verified"] { color: #5DEDB7; background: #09251C; border-color: #2E9E76; }
            QLabel#FirstBadge[state="failed"] { color: #FF8095; background: #2B0A15; border-color: #A6324D; }
            QLabel#FirstBadge[state="degraded"] { color: #FFD07A; background: #291B08; border-color: #956621; }
            QPushButton {
                min-height: 35px; padding: 0 13px; color: #DCE8F8; background: #0A1625;
                border: 1px solid #315074; border-radius: 8px; font-weight: 700;
            }
            QPushButton:hover { border-color: #59DDEB; background: #0D2133; }
            QPushButton:disabled { color: #60728C; border-color: #1D2C41; background: #07101A; }
            QPushButton#FirstPrimary {
                color: #FFFFFF; background: #6840CC; border-color: #A26CF2;
            }
            QLineEdit, QTextEdit, QComboBox {
                color: #EEF5FF; background: #07111F; border: 1px solid #315078;
                border-radius: 8px; padding: 8px; selection-background-color: #7046D2;
            }
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border-color: #58DFF0; }
        """
