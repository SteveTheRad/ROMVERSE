from __future__ import annotations

import json
import os
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import as_file, files
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from romverse.core.activity import ActivityStore, ActivityStoreError
from romverse.core.privacy import WorkspacePrivacy
from romverse.core.settings import ExperienceMode
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device.root_identity import review_root_identity
from romverse.rom.guided import GenesisFlightPlan, GuidedStageStatus
from romverse.ui.cosmic_icons import quick_action_icon
from romverse.ui.formatters import human_bytes
from romverse.ui.mini_chart import MiniChart
from romverse.ui.process_progress import ProcessProgressBar


@dataclass(frozen=True, slots=True)
class RomStudioDeviceContext:
    """Exact Studio project evidence carried into Command Deck for a read-only scan."""

    project_id: str
    project_name: str
    source_sha256: str
    device_pack_id: str
    expected_model: str
    expected_codename: str
    intent: str


class RingGauge(QWidget):
    def __init__(
        self,
        label: str,
        color: str,
        value: int | None = None,
        detail: str = "—",
        glyph: str = "◇",
        display_text: str = "",
    ) -> None:
        super().__init__()
        self.label = label
        self.color = QColor(color)
        self.value = None if value is None else max(0, min(100, value))
        self.detail = detail
        self.glyph = glyph
        self.display_text = display_text
        self.setAccessibleName(f"{label}: {detail}")
        self.setMinimumSize(118, 160)

    def set_metric(self, value: int | None, detail: str, display_text: str = "") -> None:
        self.value = None if value is None else max(0, min(100, value))
        self.detail = detail
        self.display_text = display_text
        self.setAccessibleName(f"{self.label}: {detail}")
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width()
        circle = min(96, width - 16)
        rect = QRectF((width - circle) / 2, 5, circle, circle)
        painter.setPen(QPen(QColor("#111827"), 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, 0, 360 * 16)
        if self.value is not None:
            painter.setPen(QPen(self.color, 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(rect, 90 * 16, -int(360 * 16 * self.value / 100))
        painter.setPen(self.color)
        glyph_font = self.font()
        glyph_font.setPointSize(18)
        glyph_font.setBold(True)
        painter.setFont(glyph_font)
        painter.drawText(rect.adjusted(0, -19, 0, 0), Qt.AlignmentFlag.AlignCenter, self.glyph)
        value_font = self.font()
        value_font.setPointSize(11)
        value_font.setBold(True)
        painter.setFont(value_font)
        value_text = self.display_text or ("—" if self.value is None else f"{self.value}%")
        painter.drawText(rect.adjusted(0, 23, 0, 0), Qt.AlignmentFlag.AlignCenter, value_text)
        painter.setPen(QColor("#EDF4FF"))
        painter.drawText(
            QRectF(0, circle + 16, width, 24), Qt.AlignmentFlag.AlignCenter, self.label
        )
        painter.setPen(QColor("#9AA5BD"))
        painter.drawText(
            QRectF(0, circle + 40, width, 22), Qt.AlignmentFlag.AlignCenter, self.detail
        )


class PhoneMockup(QWidget):
    """Crisp device illustration used when no model-specific product image is installed."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(146, 250)
        resource = files("romverse.assets").joinpath("dashboard-phone.png")
        with as_file(resource) as image_path:
            self._image = QPixmap(str(image_path))

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._image.isNull():
            scaled = self._image.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            return
        body = QRectF(18, 4, 110, 240)
        painter.setPen(QPen(QColor("#53607A"), 2))
        painter.setBrush(QColor("#060912"))
        painter.drawRoundedRect(body, 17, 17)
        screen = QRectF(24, 10, 98, 228)
        gradient = QLinearGradient(screen.topLeft(), screen.bottomRight())
        gradient.setColorAt(0.0, QColor("#080C1C"))
        gradient.setColorAt(0.38, QColor("#5425A8"))
        gradient.setColorAt(0.68, QColor("#2738A3"))
        gradient.setColorAt(1.0, QColor("#070914"))
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(screen, 14, 14)
        painter.setPen(QPen(QColor(183, 98, 255, 130), 5))
        painter.drawArc(QRectF(31, 52, 94, 142), 35 * 16, 205 * 16)
        painter.setPen(QPen(QColor(40, 231, 245, 110), 3))
        painter.drawArc(QRectF(19, 79, 95, 126), 210 * 16, 155 * 16)
        painter.setBrush(QColor("#0B0D17"))
        painter.setPen(QPen(QColor("#3A4155"), 1))
        painter.drawEllipse(QRectF(65, 14, 16, 16))


class StorageDonut(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.value: int | None = None
        self.detail = "—"
        self.setMinimumSize(180, 180)

    def set_metric(self, value: int | None, detail: str) -> None:
        self.value = None if value is None else max(0, min(100, value))
        self.detail = detail
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.width(), self.height()) - 28
        rect = QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)
        painter.setPen(QPen(QColor("#151B2B"), 24))
        painter.drawArc(rect, 0, 360 * 16)
        if self.value is not None:
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0, QColor("#C35CFF"))
            gradient.setColorAt(1, QColor("#347BFF"))
            painter.setPen(
                QPen(QBrush(gradient), 24, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap)
            )
            painter.drawArc(rect, 90 * 16, -int(360 * 16 * self.value / 100))
        painter.setPen(QColor("#F4F7FF"))
        painter.drawText(
            rect.adjusted(0, -12, 0, 0),
            Qt.AlignmentFlag.AlignCenter,
            "—" if self.value is None else f"{self.value}%",
        )
        painter.setPen(QColor("#9AA5BD"))
        painter.drawText(rect.adjusted(0, 24, 0, 0), Qt.AlignmentFlag.AlignCenter, self.detail)


class InfoCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("Card")
        self.layout = QGridLayout(self)
        self.layout.setContentsMargins(20, 18, 20, 18)
        self.layout.setHorizontalSpacing(20)
        self.layout.setVerticalSpacing(12)
        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        self.layout.addWidget(heading, 0, 0, 1, 2)
        self.row = 1

    def add_value(self, label: str, value: str) -> None:
        key = QLabel(label)
        key.setObjectName("Muted")
        val = QLabel(value or "Unavailable")
        val.setObjectName("Value")
        val.setWordWrap(True)
        val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.layout.addWidget(key, self.row, 0)
        self.layout.addWidget(val, self.row, 1)
        self.row += 1


class DeviceCenter(QWidget):
    refresh_requested = Signal()
    device_selected = Signal(str)
    action_requested = Signal(str)
    runtime_tools_requested = Signal()
    rom_studio_requested = Signal(str, str, str)
    GUARDIAN_CARD_STATES = {
        "unverified": "VERIFY REQUIRED",
        "review_due": "REVERIFY REQUIRED",
        "verifying": "VERIFYING",
        "verified": "INTEGRITY VERIFIED",
        "locked": "EXECUTION LOCKED",
        "failed": "VERIFY FAILED",
        "unavailable": "AUDIT UNAVAILABLE",
    }

    def __init__(
        self,
        workspace: Path | None = None,
        activity_store: ActivityStore | None = None,
    ) -> None:
        super().__init__()
        self.workspace = workspace
        self.activity_store = activity_store or (
            ActivityStore(workspace) if workspace is not None else None
        )
        self._experience_mode = ExperienceMode.GUIDED
        self._project_name = ""
        self._project_has_firmware = False
        self._flight_plan: GenesisFlightPlan | None = None
        self._repair_finding_id = ""
        self._repair_finding_title = ""
        self._guardian_state = "unverified"
        self._guardian_detail = "Guardian's current audit and approval evidence has not yet been verified in this session."
        self._guardian_verified = False
        self._studio_device_context: RomStudioDeviceContext | None = None
        self.quick_action_buttons: dict[str, QToolButton] = {}
        self.metrics_history_path = (
            workspace / "logs" / "device-metrics-history.json" if workspace is not None else None
        )
        page = QVBoxLayout(self)
        page.setContentsMargins(18, 16, 18, 14)
        page.setSpacing(12)

        header = QHBoxLayout()
        text = QVBoxLayout()
        eyebrow = QLabel("←")
        eyebrow.setStyleSheet("color: #B45CFF; font-size: 26px; font-weight: 700;")
        title = QLabel("Command Deck")
        title.setObjectName("Title")
        title_row = QHBoxLayout()
        title_row.addWidget(eyebrow)
        title_row.addWidget(title)
        title_row.addStretch()
        text.addLayout(title_row)
        header.addLayout(text, 1)
        self.scan_status_row = QFrame()
        self.scan_status_row.setObjectName("ProcessStatusRow")
        self.scan_status_row.setFixedSize(220, 34)
        scan_status_layout = QHBoxLayout(self.scan_status_row)
        scan_status_layout.setContentsMargins(10, 5, 10, 5)
        scan_status_layout.setSpacing(8)
        self.scan_status_label = QLabel("DEVICE SCAN")
        self.scan_status_label.setObjectName("ProcessStatusActive")
        scan_status_layout.addWidget(self.scan_status_label)
        self.scan_progress = ProcessProgressBar()
        self.scan_progress.setToolTip(
            "ROMVERSE is collecting read-only ADB or Fastboot identity evidence and, when Android is running, health telemetry."
        )
        self.scan_progress.setFixedWidth(108)
        scan_status_layout.addWidget(self.scan_progress)
        self.scan_status_row.setVisible(False)
        header.addWidget(self.scan_status_row)
        self.selector = QComboBox()
        self.selector.setMinimumWidth(220)
        self.selector.setVisible(False)
        self.selector.currentIndexChanged.connect(self._select)
        header.addWidget(self.selector)
        self.refresh = QPushButton("↻  Scan")
        self.refresh.setObjectName("Primary")
        self.refresh.clicked.connect(self.refresh_requested)
        self.refresh.setVisible(False)
        header.addWidget(self.refresh)
        self.export_button = QPushButton("Theme ⌄")
        self.export_button.setToolTip("ROMVERSE Nebula Flow theme is active.")
        self.export_button.setEnabled(True)
        self.export_button.clicked.connect(
            lambda _checked=False: self.action_requested.emit("Theme")
        )
        header.addWidget(self.export_button)
        self.apk_button = QPushButton("⚙")
        self.apk_button.setToolTip("Command Deck settings and display controls.")
        self.apk_button.setEnabled(True)
        self.apk_button.clicked.connect(
            lambda _checked=False: self.action_requested.emit("Settings")
        )
        header.addWidget(self.apk_button)
        page.addLayout(header)

        self.studio_handoff = QFrame()
        self.studio_handoff.setObjectName("DiagnosticHandoffBar")
        studio_handoff_layout = QHBoxLayout(self.studio_handoff)
        studio_handoff_layout.setContentsMargins(18, 13, 18, 13)
        studio_handoff_layout.setSpacing(14)
        studio_copy = QVBoxLayout()
        self.studio_handoff_eyebrow = QLabel(
            "ROM STUDIO HANDOFF  •  EXACT PROJECT / READ-ONLY DEVICE EVIDENCE"
        )
        self.studio_handoff_eyebrow.setObjectName("Eyebrow")
        self.studio_handoff_title = QLabel()
        self.studio_handoff_title.setObjectName("SectionTitle")
        self.studio_handoff_detail = QLabel()
        self.studio_handoff_detail.setObjectName("Muted")
        self.studio_handoff_detail.setWordWrap(True)
        self.studio_handoff_detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        studio_copy.addWidget(self.studio_handoff_eyebrow)
        studio_copy.addWidget(self.studio_handoff_title)
        studio_copy.addWidget(self.studio_handoff_detail)
        studio_handoff_layout.addLayout(studio_copy, 1)
        self.studio_handoff_badge = QLabel()
        studio_handoff_layout.addWidget(self.studio_handoff_badge)
        studio_actions = QVBoxLayout()
        self.studio_scan_button = QPushButton("Scan exact target")
        self.studio_scan_button.setObjectName("Primary")
        self.studio_scan_button.setToolTip(
            "Run Device Engine's read-only identity and health scan. No reboot, unlock, root, "
            "flash, wipe, or relock command is allowed."
        )
        self.studio_scan_button.clicked.connect(self.refresh_requested)
        self.studio_return_button = QPushButton("Return to exact ROM project")
        self.studio_return_button.clicked.connect(self._return_to_rom_studio)
        studio_actions.addWidget(self.studio_scan_button)
        studio_actions.addWidget(self.studio_return_button)
        studio_handoff_layout.addLayout(studio_actions)
        self.studio_handoff.setVisible(False)
        page.addWidget(self.studio_handoff)

        self.feature_handoff = QFrame()
        self.feature_handoff.setObjectName("DiagnosticHandoffBar")
        feature_handoff_layout = QHBoxLayout(self.feature_handoff)
        feature_handoff_layout.setContentsMargins(18, 11, 18, 11)
        feature_copy = QVBoxLayout()
        feature_eyebrow = QLabel("FIND ANYTHING  •  EXACT NESTED FEATURE")
        feature_eyebrow.setObjectName("Eyebrow")
        self.feature_handoff_title = QLabel()
        self.feature_handoff_title.setObjectName("SectionTitle")
        self.feature_handoff_detail = QLabel()
        self.feature_handoff_detail.setObjectName("Muted")
        self.feature_handoff_detail.setWordWrap(True)
        feature_copy.addWidget(feature_eyebrow)
        feature_copy.addWidget(self.feature_handoff_title)
        feature_copy.addWidget(self.feature_handoff_detail)
        feature_handoff_layout.addLayout(feature_copy, 1)
        self.feature_handoff_badge = QLabel("READ ONLY")
        self.feature_handoff_badge.setObjectName("Good")
        feature_handoff_layout.addWidget(self.feature_handoff_badge)
        self.feature_handoff.setVisible(False)
        page.addWidget(self.feature_handoff)

        next_action = QFrame()
        next_action.setObjectName("HeroCard")
        next_layout = QHBoxLayout(next_action)
        next_layout.setContentsMargins(20, 14, 20, 14)
        next_text = QVBoxLayout()
        next_label = QLabel("NEXT BEST ACTION")
        next_label.setObjectName("Eyebrow")
        self.next_title = QLabel("Connect your Android device")
        self.next_title.setObjectName("HeroTitle")
        self.next_note = QLabel(
            "Read-only evidence first. Guardian approval is required before any device-changing operation."
        )
        self.next_note.setObjectName("Muted")
        self.next_note.setWordWrap(True)
        next_text.addWidget(next_label)
        next_text.addWidget(self.next_title)
        next_text.addWidget(self.next_note)
        next_layout.addLayout(next_text, 1)
        self.next_button = QPushButton("Scan for device")
        self.next_button.setObjectName("Primary")
        self.next_button.setToolTip("Scan for an Android device using the read-only Device Engine.")
        self.next_button.clicked.connect(self._perform_next_action)
        next_layout.addWidget(self.next_button)
        page.addWidget(next_action)
        next_action.setVisible(False)

        self.status_card = QFrame()
        self.status_card.setObjectName("HeroCard")
        hero = QHBoxLayout(self.status_card)
        hero.setContentsMargins(24, 20, 24, 20)
        status_text = QVBoxLayout()
        self.device_name = QLabel("Looking for an Android device…")
        self.device_name.setObjectName("HeroTitle")
        self.device_note = QLabel("Connect a phone with USB debugging enabled.")
        self.device_note.setObjectName("Muted")
        self.device_note.setWordWrap(True)
        status_text.addWidget(self.device_name)
        status_text.addWidget(self.device_note)
        hero.addLayout(status_text, 1)
        self.status_badge = QLabel("SCANNING")
        self.status_badge.setObjectName("Warning")
        hero.addWidget(self.status_badge)
        page.addWidget(self.status_card)
        self.status_card.setVisible(False)
        self.last_scan_label = QLabel("Last scan: not yet completed")
        self.last_scan_label.setObjectName("Muted")
        page.addWidget(self.last_scan_label)
        self.last_scan_label.setVisible(False)
        self.battery_history: list[float] = []
        self.temperature_history: list[float] = []
        self.connection_history: list[float] = []
        self.storage_history: list[float] = []
        self._load_metric_history()
        chart_row = QHBoxLayout()
        chart_labels = QHBoxLayout()
        chart_labels.addWidget(QLabel("Battery % (recent scans)"))
        chart_labels.addWidget(QLabel("Temperature °C (recent scans)"))
        chart_labels.addWidget(QLabel("Connection state (recent scans)"))
        chart_labels.addWidget(QLabel("Storage used % (recent scans)"))
        page.addLayout(chart_labels)
        for index in range(chart_labels.count()):
            if chart_labels.itemAt(index).widget() is not None:
                chart_labels.itemAt(index).widget().setVisible(False)
        self.battery_chart = MiniChart("#74d9ff")
        self.battery_chart.setToolTip(
            "Battery percentage recorded during the most recent device scans."
        )
        self.temperature_chart = MiniChart("#ff9f68")
        self.temperature_chart.setToolTip("Battery temperature in °C recorded during recent scans.")
        self.storage_chart = MiniChart("#b68cff")
        self.storage_chart.setToolTip("/data storage used percentage recorded during recent scans.")
        chart_row.addWidget(self.battery_chart)
        chart_row.addWidget(self.temperature_chart)
        self.connection_chart = MiniChart("#7dffb2")
        self.connection_chart.setToolTip(
            "Connection state: connected=1, limited/unauthorized=0.5, offline=0."
        )
        self.battery_chart.set_values(self.battery_history)
        self.temperature_chart.set_values(self.temperature_history)
        self.connection_chart.set_values(self.connection_history)
        self.storage_chart.set_values(self.storage_history)
        chart_row.addWidget(self.connection_chart)
        chart_row.addWidget(self.storage_chart)
        page.addLayout(chart_row)
        self.battery_chart.setVisible(False)
        self.temperature_chart.setVisible(False)
        self.connection_chart.setVisible(False)
        self.storage_chart.setVisible(False)

        self.body = QScrollArea()
        self.body.setWidgetResizable(True)
        self.body_content = QWidget()
        self.body_content.setObjectName("ScrollContent")
        self.body_layout = QVBoxLayout(self.body_content)
        self.body_layout.setContentsMargins(0, 0, 6, 0)
        self.body_layout.setSpacing(16)
        self.body.setWidget(self.body_content)
        page.addWidget(self.body, 1)
        self.devices: list[AndroidDevice] = []
        self._selected_index = -1
        self.show_empty("Scanning for devices…")

    def set_experience_mode(self, mode: ExperienceMode) -> None:
        """Apply progressive disclosure without changing device or project state."""

        self._experience_mode = mode
        self._apply_quick_action_visibility()

    def open_feature_destination(self, route: str) -> bool:
        """Reveal a Command Deck feature without starting a Device Engine scan."""

        destination = str(route).strip()
        if destination not in {"device_nexus", "device_engine"}:
            return False
        device = (
            self.devices[self._selected_index]
            if 0 <= self._selected_index < len(self.devices)
            else None
        )
        if destination == "device_engine" and device is None:
            self.feature_handoff_title.setText("Device Engine is ready for a read-only scan")
            self.feature_handoff_detail.setText(
                "Choose Scan for device when the phone is connected and authorized. Navigation "
                "did not invoke ADB, refresh tools, scan, command, build, flash, or change a phone."
            )
            self.feature_handoff_badge.setText("READY • NO SCAN STARTED")
            self.feature_handoff_badge.setObjectName("Good")
            self.next_button.setFocus(Qt.FocusReason.OtherFocusReason)
        elif destination == "device_engine":
            self.feature_handoff_title.setText(f"Device Engine evidence • {device.display_name}")
            self.feature_handoff_detail.setText(
                f"The current {device.state.value} snapshot for {device.masked_serial()} is "
                "already displayed below. Navigation did not refresh ADB, scan, command, build, "
                "flash, or change the phone."
            )
            self.feature_handoff_badge.setText("CURRENT • READ ONLY")
            self.feature_handoff_badge.setObjectName(
                "Good" if device.state is DeviceState.DEVICE else "Warning"
            )
            self.next_button.setFocus(Qt.FocusReason.OtherFocusReason)
        elif device is None:
            self.feature_handoff_title.setText("Device Portal needs a current Android identity")
            self.feature_handoff_detail.setText(
                "Connect and authorize a phone, then choose Scan. ROMVERSE opened the owning "
                "Command Deck only; NO SCAN, COMMAND, BUILD, FLASH, OR PHONE ACTION STARTED."
            )
            self.feature_handoff_badge.setText("EVIDENCE NEEDED")
            self.feature_handoff_badge.setObjectName("Warning")
        else:
            self.feature_handoff_title.setText(f"Device Portal • {device.display_name}")
            self.feature_handoff_detail.setText(
                f"Current {device.state.value} evidence is already displayed below for "
                f"{device.masked_serial()}. Navigation did not refresh, command, build, flash, "
                "or change the phone."
            )
            self.feature_handoff_badge.setText("CURRENT • READ ONLY")
            self.feature_handoff_badge.setObjectName(
                "Good" if device.state is DeviceState.DEVICE else "Warning"
            )
            self.next_button.setFocus(Qt.FocusReason.OtherFocusReason)
        self._repolish(self.feature_handoff_badge)
        self.feature_handoff.setVisible(True)
        self.body.verticalScrollBar().setValue(0)
        return True

    def set_workspace_context(
        self,
        project_name: str,
        has_firmware: bool,
        flight_plan: GenesisFlightPlan | None = None,
    ) -> None:
        """Refresh Command Deck cards from the actual active ROM Studio project."""

        changed = (
            self._project_name != project_name
            or self._project_has_firmware != bool(has_firmware)
            or self._flight_plan != flight_plan
        )
        self._project_name = project_name
        self._project_has_firmware = bool(has_firmware)
        self._flight_plan = flight_plan
        if not changed:
            return
        if self.devices:
            self.render_device(self.devices[self._selected_index])
        else:
            self.show_empty(
                "No Android device is connected. ROM Studio remains available for safe local firmware work."
            )

    def set_repair_context(self, finding_id: str = "", title: str = "") -> None:
        """Refresh Command Deck repair wording from current typed diagnostic evidence."""

        normalized_id = finding_id.strip()[:120]
        normalized_title = " ".join(title.replace("\x00", " ").split())[:160]
        if (normalized_id, normalized_title) == (
            self._repair_finding_id,
            self._repair_finding_title,
        ):
            return
        self._repair_finding_id = normalized_id
        self._repair_finding_title = normalized_title
        if self.devices:
            self.render_device(self.devices[self._selected_index])

    def set_guardian_state(self, state: str, detail: str, verified: bool) -> None:
        """Update Guardian's Command Deck claim from its owning verified lifecycle."""

        normalized_state = str(state).strip().casefold()
        if normalized_state not in self.GUARDIAN_CARD_STATES:
            normalized_state = "unverified"
        normalized_detail = " ".join(str(detail).replace("\x00", " ").split())[:360]
        if not normalized_detail:
            normalized_detail = "Guardian evidence needs a current bounded verification."
        evidence_ready = normalized_state == "verified" and bool(verified)
        self._guardian_state = normalized_state
        self._guardian_detail = normalized_detail
        self._guardian_verified = evidence_ready
        button = self.quick_action_buttons.get("Guardian")
        if button is None:
            return
        status = self.GUARDIAN_CARD_STATES[normalized_state]
        button.setText(f"Guardian\n{status}")
        button.setToolTip(
            f"{normalized_detail} Open Guardian Core for the current bounded evidence and "
            "verification controls."
        )
        button.setAccessibleName(f"Guardian: {status.title()}")
        button.setAccessibleDescription(normalized_detail)
        button.setProperty("guardianState", normalized_state)
        button.setProperty("evidenceReady", evidence_ready)
        self._repolish(button)

    def _apply_quick_action_visibility(self) -> None:
        expert = self._experience_mode is ExperienceMode.EXPERT
        command_console = self.quick_action_buttons.get("Command Console")
        if command_console is not None:
            command_console.setVisible(expert)

    def set_scanning(self, scanning: bool, *, show_progress: bool = True) -> None:
        self.refresh.setEnabled(not scanning)
        self.refresh.setText("Scanning…" if scanning else "Scan now")
        active = scanning and show_progress
        self.scan_status_row.setVisible(active)
        if active:
            self.scan_progress.begin()
        elif scanning:
            self.scan_progress.stop()
        else:
            self.scan_progress.finish()
        if scanning and not self.devices:
            self.status_badge.setText("SCANNING")
            self.status_badge.setObjectName("Warning")
            self.status_badge.style().unpolish(self.status_badge)
            self.status_badge.style().polish(self.status_badge)

    def set_devices(self, devices: list[AndroidDevice], selected_serial: str = "") -> None:
        self.devices = devices
        selected = next(
            (index for index, device in enumerate(devices) if device.serial == selected_serial),
            0 if len(devices) == 1 else -1,
        )
        self._selected_index = selected
        self.last_scan_label.setText(
            f"Last scan: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )
        self.selector.blockSignals(True)
        self.selector.clear()
        if len(devices) > 1:
            self.selector.addItem("Choose one connected device…", "")
        for device in devices:
            self.selector.addItem(
                f"{device.display_name}  •  {device.masked_serial()}", device.serial
            )
        self.selector.setCurrentIndex(selected + 1 if len(devices) > 1 and selected >= 0 else 0)
        self.selector.setVisible(len(devices) > 1)
        self.selector.blockSignals(False)
        if selected >= 0:
            device = devices[selected]
            self._record_device_scan(device)
            if device.state is DeviceState.DEVICE:
                self.next_title.setText("Run a safe health review")
                self.next_note.setText(
                    "Your phone is authorized and ready for evidence-backed optimization recommendations."
                )
                self.next_button.setText("Review health")
                self.next_button.setToolTip("Open Quantum Optimizer for the connected device.")
            elif device.state is DeviceState.UNAUTHORIZED:
                self.next_title.setText("Authorize this computer on your phone")
                self.next_note.setText(
                    "Unlock the phone, approve the USB debugging fingerprint, then scan again."
                )
                self.next_button.setText("Scan again")
                self.next_button.setToolTip("Retry device detection after approving USB debugging.")
            elif device.is_fastboot:
                self.next_title.setText("Review the detected bootloader identity")
                self.next_note.setText(
                    "Device Atlas can match this read-only product identity to its exact build requirements. Android health checks remain unavailable in this mode."
                )
                self.next_button.setText("Open Device Atlas")
                self.next_button.setToolTip(
                    "Review the detected Fastboot identity and Device Pack requirements. No phone command is started."
                )
            if device.battery_percent is not None:
                self.battery_history.append(float(device.battery_percent))
            if device.battery_temperature_c is not None:
                self.temperature_history.append(float(device.battery_temperature_c))
            self.connection_history.append(
                1.0
                if device.state is DeviceState.DEVICE
                else 0.5
                if device.state is DeviceState.UNAUTHORIZED
                else 0.75
                if device.is_fastboot
                else 0.0
            )
            if device.storage.percent_used is not None:
                self.storage_history.append(float(device.storage.percent_used))
            self.battery_history = self.battery_history[-30:]
            self.temperature_history = self.temperature_history[-30:]
            self.connection_history = self.connection_history[-30:]
            self.storage_history = self.storage_history[-30:]
            self._save_metric_history()
            self.battery_chart.set_values(self.battery_history)
            self.temperature_chart.set_values(self.temperature_history)
            self.connection_chart.set_values(self.connection_history)
            self.storage_chart.set_values(self.storage_history)
            self.render_device(device)
        elif devices:
            self.next_title.setText("Choose the device you want to use")
            self.next_note.setText(
                "More than one Android transport is connected. Select one above before ROMVERSE binds diagnostics, firmware, backup, or terminal actions."
            )
            self.next_button.setText("Choose a device above")
            self.next_button.setToolTip(
                "Select one exact connected device from the device chooser."
            )
            self.device_name.setText(f"{len(devices)} Android devices detected")
            self.device_note.setText(
                "No device is active yet. This prevents work intended for one phone from being applied to another."
            )
            self._set_badge("SELECT ONE DEVICE", "Warning")
            self.show_empty(
                "Choose one connected device above. ROMVERSE has not bound any device-changing workflow to a phone."
            )
        else:
            self.next_title.setText("Connect your Android device")
            self.next_note.setText(
                "Use a data-capable USB cable, enable USB debugging, then let Device Engine scan safely."
            )
            self.next_button.setText("Scan for device")
            self.next_button.setToolTip(
                "Scan for an Android device using the read-only Device Engine."
            )
            self.device_name.setText("No Android device detected")
            self.device_note.setText(
                "Connect with USB debugging enabled, or connect a phone already in bootloader/fastbootd mode, then scan again."
            )
            self._set_badge("NOT CONNECTED", "Warning")
            self.show_empty(
                "No Android transport is visible. ROMVERSE checks verified ADB and Fastboot runtimes without rebooting or changing a phone."
            )
        self._render_studio_handoff()

    def open_rom_studio_context(self, context: RomStudioDeviceContext) -> bool:
        """Show one exact project-to-device prerequisite without starting a scan."""

        if not self._valid_studio_context(context):
            return False
        self._studio_device_context = context
        self.studio_return_button.setEnabled(True)
        self.studio_scan_button.setEnabled(True)
        self._render_studio_handoff()
        self.studio_handoff.setVisible(True)
        return True

    def studio_handoff_stopped(self, reason: str) -> None:
        """Expire an exact Studio handoff visibly without changing device or project state."""

        self._studio_device_context = None
        self.studio_handoff_title.setText("ROM Studio device context expired safely")
        self.studio_handoff_detail.setText(
            f"{reason}. Reopen Command Deck from the exact Studio project. "
            "NO SCAN, PROJECT WORKER, BUILD, ROOT, FLASH, OR PHONE-CHANGING ACTION STARTED."
        )
        self.studio_handoff_badge.setText("CONTEXT REFUSED")
        self.studio_handoff_badge.setObjectName("Danger")
        self._repolish(self.studio_handoff_badge)
        self.studio_return_button.setEnabled(False)
        self.studio_scan_button.setEnabled(False)
        self.studio_handoff.setVisible(True)

    @staticmethod
    def _valid_studio_context(context: RomStudioDeviceContext) -> bool:
        return bool(
            isinstance(context, RomStudioDeviceContext)
            and context.project_id.strip()
            and context.project_name.strip()
            and len(context.project_id) <= 80
            and len(context.project_name) <= 120
            and len(context.device_pack_id) <= 160
            and len(context.expected_model) <= 160
            and len(context.expected_codename) <= 120
            and context.intent in {"build-readiness", "ascension-refresh"}
            and len(context.source_sha256) == 64
            and all(character in "0123456789abcdef" for character in context.source_sha256)
        )

    def _render_studio_handoff(self) -> None:
        context = self._studio_device_context
        if context is None:
            return
        selected = (
            self.devices[self._selected_index]
            if 0 <= self._selected_index < len(self.devices)
            else None
        )
        authorized = (
            (selected,) if selected is not None and selected.state is DeviceState.DEVICE else ()
        )
        expected_model = context.expected_model.casefold().strip()
        expected_codename = context.expected_codename.casefold().strip()
        matches = tuple(
            device
            for device in authorized
            if (not expected_model or device.model.casefold().strip() == expected_model)
            and (
                not expected_codename
                or device.codename.casefold().strip() == expected_codename
                or device.product.casefold().strip() == expected_codename
            )
        )
        expected = (
            " / ".join(
                value for value in (context.expected_model, context.expected_codename) if value
            )
            or "target identity not yet derived"
        )
        pack = context.device_pack_id or "not bound"
        purpose = (
            "Ascension requested a fresh read-only target check"
            if context.intent == "ascension-refresh"
            else "Forge Control requested current target evidence"
        )
        if matches:
            state = f"EXACT TARGET PRESENT  •  {matches[0].display_name}"
            badge = "TARGET MATCH • READ ONLY"
            style = "Good"
        elif authorized:
            observed = " • ".join(device.display_name for device in authorized[:3])
            state = f"Authorized device does not match expected {expected}; observed {observed}"
            badge = "TARGET MISMATCH"
            style = "Danger"
        else:
            state = f"No authorized device currently matches expected {expected}"
            badge = "SCAN TARGET"
            style = "Warning"
        self.studio_handoff_title.setText(f"{purpose}  •  {context.project_name}")
        self.studio_handoff_detail.setText(
            f"Project {context.project_id}  •  protected source {context.source_sha256[:16]}…  •  "
            f"Pack {pack}  •  {state}. Device Engine may collect identity and health evidence only; "
            "NO REBOOT, UNLOCK, ROOT, BUILD, FLASH, WIPE, OR RELOCK ACTION STARTED."
        )
        self.studio_handoff_badge.setText(badge)
        self.studio_handoff_badge.setObjectName(style)
        self._repolish(self.studio_handoff_badge)
        self.studio_scan_button.setText(
            "Refresh exact target evidence" if authorized else "Scan exact target"
        )
        self.studio_handoff.setVisible(True)

    def _return_to_rom_studio(self) -> None:
        context = self._studio_device_context
        if context is not None:
            self.rom_studio_requested.emit(
                context.project_id,
                context.source_sha256,
                context.intent,
            )

    def _record_device_scan(self, device: AndroidDevice) -> None:
        if self.activity_store is None or self.workspace is None:
            return
        state = device.state
        outcome = (
            "success"
            if (state is DeviceState.DEVICE or device.is_fastboot) and not device.errors
            else "attention"
        )
        title = (
            "Device scan completed"
            if state is DeviceState.DEVICE
            else "Fastboot identity captured"
            if device.is_fastboot
            else f"Device scan: {state.value}"
        )
        detail = (
            f"{device.display_name} • Android {device.android_version or 'unknown'} • read-only evidence captured"
            if state is DeviceState.DEVICE
            else f"{device.display_name} • {state.value} • read-only identity evidence captured"
            if device.is_fastboot
            else device.connection_note or "Device authorization needs attention"
        )
        device_key = WorkspacePrivacy(self.workspace).pseudonym(device.serial)
        with suppress(ActivityStoreError):
            self.activity_store.record(
                "device",
                title,
                detail,
                outcome=outcome,
                source="Device Engine",
                dedupe_key=f"device-scan:{device_key}:{state.value}",
                dedupe_seconds=900,
            )

    def _perform_next_action(self) -> None:
        device = (
            self.devices[self._selected_index]
            if 0 <= self._selected_index < len(self.devices)
            else None
        )
        if device is not None and device.state is DeviceState.DEVICE:
            self.action_requested.emit("Optimize")
            return
        if device is not None and device.is_fastboot:
            self.action_requested.emit("Device DNA")
            return
        if self.devices:
            return
        self.refresh_requested.emit()

    def refresh_activity(self) -> None:
        """Re-render cached device evidence so the durable activity card stays current."""
        if 0 <= self._selected_index < len(self.devices):
            self.render_device(self.devices[self._selected_index])

    def show_error(self, message: str) -> None:
        self.device_name.setText("Device Engine needs attention")
        self.device_note.setText(message)
        self._set_badge("DEVICE ENGINE ERROR", "Danger")
        self.show_empty(
            "ROMVERSE did not run any device-changing command. Resolve verified Android Platform Tools in place, then Device Engine will recheck ADB and Fastboot automatically.",
            action_text="Resolve Platform Tools",
            action=self.runtime_tools_requested.emit,
        )

    def show_empty(self, text: str, *, action_text: str = "", action=None) -> None:
        self._clear_body()
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(26, 26, 26, 26)
        label = QLabel(text)
        label.setObjectName("Muted")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        if action_text and action is not None:
            button = QPushButton(action_text)
            button.setObjectName("Primary")
            button.setToolTip(
                "Verify ROMVERSE-managed Android Platform Tools and start a fresh read-only device scan."
            )
            button.clicked.connect(action)
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignCenter)
        self.body_layout.addWidget(card)
        self.body_layout.addWidget(self._build_flight_plan_card())
        self._add_command_cards(connected=False)
        self._add_telemetry_panel(None)
        self.body_layout.addStretch()

    def _add_command_cards(self, *, connected: bool) -> None:
        """Render one status-aware launch point for each approved major workflow."""

        project_ready = self._project_has_firmware
        project_status = (
            "CONTINUE PROJECT"
            if project_ready
            else "IMPORT FIRMWARE"
            if self._project_name
            else "CREATE PROJECT"
        )
        device_status = "DEVICE READY" if connected else "CONNECT DEVICE"
        repair_topic = {
            "battery": "BATTERY / HEAT",
            "storage": "STORAGE",
            "connection": "USB / ADB",
            "scan": "USB / ADB",
            "boot": "SYSTEM",
            "security": "SYSTEM",
        }.get(self._repair_finding_id.partition(".")[0], "GUIDED")
        repair_status = f"{repair_topic} PLAN READY" if self._repair_finding_id else device_status
        repair_tooltip = (
            f"Open Recovery Bay for the exact current finding: {self._repair_finding_title}. "
            "Navigation starts no repair."
            if self._repair_finding_id
            else "Open Recovery Bay for diagnosis, evidence-backed fixes, and verification."
        )
        cards = QFrame()
        cards.setObjectName("DashboardCard")
        cards_layout = QVBoxLayout(cards)
        cards_layout.setContentsMargins(16, 12, 16, 14)
        cards_layout.addWidget(self._dashboard_heading("MISSION COMMANDS"))
        context = QLabel(
            (
                f"Active workspace: {self._project_name}  •  {project_status.replace('_', ' ')}"
                if self._project_name
                else "No active ROM workspace  •  start safely in Build ROM"
            )
            + f"  •  {device_status.replace('_', ' ')}"
        )
        context.setObjectName("Muted")
        context.setWordWrap(True)
        cards_layout.addWidget(context)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        for column in range(3):
            grid.setColumnStretch(column, 1)
        action_specs = (
            (
                "rocket",
                "#9D48FF",
                "#C266FF",
                "Build ROM",
                project_status,
                "Open ROM Studio for Genesis Sequence, Recipe Forge, Device DNA, and verified build preparation.",
            ),
            (
                "puzzle",
                "#F126C7",
                "#C946F4",
                "Device DNA",
                "REVIEW EVIDENCE" if project_ready else "NEEDS FIRMWARE",
                "Review compatibility profiles and evidence-backed device capabilities in Device Atlas.",
            ),
            (
                "sliders",
                "#6A6DFF",
                "#35DFF2",
                "Pre-Build Simulation",
                "READY" if project_ready else "NEEDS FIRMWARE",
                "Open ROM Studio to generate an execution-locked dry-run plan before any build or flash.",
            ),
            (
                "puzzle",
                "#B54EFF",
                "#39DFF2",
                "Recipes",
                project_status,
                "Open Recipe Forge inside ROM Studio for reusable, previewed, rollback-protected changes.",
            ),
            (
                "sliders",
                "#19BCD4",
                "#43E5EF",
                "Health Review",
                device_status,
                "Open Quantum Optimizer for real health evidence and safe recommendations.",
            ),
            (
                "restore",
                "#3977FF",
                "#6097FF",
                "Repair Phone",
                repair_status,
                repair_tooltip,
            ),
            (
                "sliders",
                "#A54BFF",
                "#5D87FF",
                "Guardian",
                self.GUARDIAN_CARD_STATES[self._guardian_state],
                f"{self._guardian_detail} Open Guardian Core for the current bounded evidence and verification controls.",
            ),
            (
                "cloud_upload",
                "#A83EF0",
                "#D56BFF",
                "Rescue & Backup",
                "PLAN RECOVERY",
                "Open Time Machine for local backup, recovery evidence, and restore planning.",
            ),
            (
                "restore",
                "#548BFF",
                "#35DBF0",
                "Timeline",
                "VIEW HISTORY",
                "Open Health Timeline for saved diagnostic snapshots and health changes over time.",
            ),
            (
                "terminal",
                "#377DFF",
                "#55A0FF",
                "Live Operations",
                "REAL EVENTS",
                "Open Live Console for genuine Nexus mission progress and explanations.",
            ),
            (
                "cloud_upload",
                "#25C9E8",
                "#6A7DFF",
                "Wireless Transfer",
                "OPEN LINK",
                "Open ROMVERSE Link for authenticated Desktop and Companion connectivity.",
            ),
            (
                "puzzle",
                "#C35CFF",
                "#35E7F5",
                "ROMVERSE Lab",
                "EXPERT WORKSPACE",
                "Open ROMVERSE Nexus and specialist planning tools. Guardian remains fully active.",
            ),
        )
        self.quick_action_buttons = {}
        for index, (icon_name, start, end, label, status, tooltip) in enumerate(action_specs):
            button = QToolButton()
            display_label = label.replace("&", "&&")
            button.setText(f"{display_label}\n{status.replace('_', ' ')}")
            button.setIcon(quick_action_icon(icon_name, 40, start, end))
            button.setIconSize(QSize(40, 40))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setObjectName("QuickAction")
            button.setToolTip(tooltip)
            button.setAccessibleName(f"{label}: {status.replace('_', ' ').title()}")
            if label == "Repair Phone" and self._repair_finding_id:
                button.setProperty("diagnosticFinding", self._repair_finding_id)
                button.setProperty("evidenceReady", True)
                button.setAccessibleDescription(self._repair_finding_title)
            if label == "Guardian":
                button.setProperty("guardianState", self._guardian_state)
                button.setProperty("evidenceReady", self._guardian_verified)
                button.setAccessibleDescription(self._guardian_detail)
            button.setMinimumHeight(102)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(
                lambda _checked=False, target=label: self.action_requested.emit(target)
            )
            self.quick_action_buttons[label] = button
            grid.addWidget(button, index // 3, index % 3)
        cards_layout.addLayout(grid)
        self.body_layout.addWidget(cards)
        self._apply_quick_action_visibility()

    def _build_flight_plan_card(self) -> QFrame:
        """Render the exact evidence-derived resume point from Genesis Sequence."""

        plan = self._flight_plan
        card = QFrame()
        card.setObjectName("GenesisFlightPlan")
        card.setAccessibleName("Genesis Flight Plan")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(self._dashboard_heading("GENESIS FLIGHT PLAN"))
        header.addStretch()
        status = QLabel(
            "UNCONFIRMED" if plan is None else plan.status.value.replace("_", " ").upper()
        )
        status.setObjectName(
            "Good"
            if plan is not None
            and plan.status in {GuidedStageStatus.COMPLETE, GuidedStageStatus.READY}
            else "Danger"
            if plan is not None and plan.has_saved_error
            else "Warning"
        )
        status.setAccessibleName(f"Genesis status: {status.text().title()}")
        header.addWidget(status)
        layout.addLayout(header)

        stage_number = plan.stage_number if plan is not None else 1
        stage_total = plan.stage_total if plan is not None else 15
        route = QLabel(f"CURRENT ROUTE  •  STAGE {stage_number:02d} OF {stage_total:02d}")
        route.setObjectName("FlightPlanRoute")
        layout.addWidget(route)
        title = QLabel(plan.stage_title if plan is not None else "Create the mission workspace")
        title.setObjectName("FlightPlanTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        progress = QProgressBar()
        progress.setObjectName("FlightPlanProgress")
        progress.setRange(0, 100)
        progress.setValue(plan.progress_percent if plan is not None else 0)
        verified = plan.verified_stages if plan is not None else 0
        progress.setFormat(f"{verified} of {stage_total} stages verified  •  %p%")
        progress.setAccessibleName(f"Genesis progress: {verified} of {stage_total} stages verified")
        progress.setTextVisible(True)
        layout.addWidget(progress)

        if plan is None:
            guidance = (
                "Open Genesis Sequence to calculate the route from the active ROM project. "
                "No stage is marked complete without stored evidence."
            )
        elif plan.has_saved_error:
            guidance = (
                "Genesis saved an issue that needs review. ROMVERSE preserved the project and "
                "will show the explanation and safe recovery choices inside the sequence."
            )
        elif plan.blockers:
            guidance = "Needs attention: " + "  •  ".join(plan.blockers[:2])
        else:
            guidance = plan.recommendation
        note = QLabel(guidance)
        note.setObjectName(
            "FlightPlanDanger"
            if plan is not None and plan.has_saved_error
            else "FlightPlanWarning"
            if plan is not None and plan.blockers
            else "Muted"
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        facts = QGridLayout()
        facts.setHorizontalSpacing(8)
        facts.setVerticalSpacing(8)
        project_name = plan.project_name if plan is not None else self._project_name or "No project"
        fact_specs = (
            ("Active project", project_name),
            ("Root route", plan.root_route if plan is not None else "Decision pending"),
            (
                "Recovery checkpoint",
                "VERIFIED" if plan is not None and plan.recovery_ready else "NOT YET VERIFIED",
            ),
            (
                "Guardian handoff",
                "READY" if plan is not None and plan.guardian_ready else "NOT YET READY",
            ),
        )
        for index, (label, value) in enumerate(fact_specs):
            tile = QFrame()
            tile.setObjectName("FlightPlanTile")
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(10, 8, 10, 8)
            tile_layout.setSpacing(2)
            key = QLabel(label.upper())
            key.setObjectName("TelemetryLabel")
            val = QLabel(value)
            val.setObjectName("TelemetryValue")
            val.setWordWrap(True)
            tile_layout.addWidget(key)
            tile_layout.addWidget(val)
            facts.addWidget(tile, index // 2, index % 2)
        layout.addLayout(facts)

        footer = QHBoxLayout()
        next_step = QLabel(
            f"NEXT  •  {plan.action_label}" if plan is not None else "NEXT  •  CREATE ROM PROJECT"
        )
        next_step.setObjectName("FlightPlanNext")
        next_step.setWordWrap(True)
        footer.addWidget(next_step, 1)
        self.flight_plan_button = QPushButton("Continue Genesis Sequence")
        self.flight_plan_button.setObjectName("Primary")
        self.flight_plan_button.setAccessibleName("Continue Genesis Sequence")
        self.flight_plan_button.setToolTip(
            "Open Genesis at the first stage that does not yet have verified evidence."
        )
        self.flight_plan_button.clicked.connect(
            lambda _checked=False: self.action_requested.emit("Continue Genesis")
        )
        footer.addWidget(self.flight_plan_button)
        layout.addLayout(footer)
        return card

    def _add_telemetry_panel(self, device: AndroidDevice | None) -> None:
        """Render truthful current readings and persisted read-only scan history."""

        panel = QFrame()
        panel.setObjectName("DashboardCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(self._dashboard_heading("TELEMETRY & READINESS"))
        explanation = QLabel(
            "Current values come from the active read-only device scan. Graphs retain up to "
            "30 recent scans on this PC; a dash means ROMVERSE has no trustworthy reading."
        )
        explanation.setObjectName("Muted")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        gauges = QHBoxLayout()
        gauges.setSpacing(10)
        if device is None:
            source_value = 100 if self._project_has_firmware else 40 if self._project_name else None
            source_detail = (
                "Firmware loaded"
                if self._project_has_firmware
                else "Project created"
                if self._project_name
                else "Create a project"
            )
            gauge_specs = (
                ("Device link", "#31DCEB", None, "Awaiting device", "⌁", ""),
                ("ROM source", "#A957FF", source_value, source_detail, "◇", ""),
                ("Device evidence", "#4F7CFF", None, "Awaiting scan", "◎", ""),
                ("Guardian policy", "#44E39A", 100, "Always enforced", "◈", ""),
            )
        else:
            coverage, known, total = self._evidence_coverage(device)
            temperature = device.battery_temperature_c
            thermal_scale = (
                max(0, min(100, round(float(temperature) * 100 / 60)))
                if temperature is not None
                else None
            )
            gauge_specs = (
                (
                    "Battery",
                    "#EC51C8",
                    device.battery_percent,
                    device.battery_status or "Status unconfirmed",
                    "▯",
                    "",
                ),
                (
                    "Thermal",
                    "#FF9F68",
                    thermal_scale,
                    "Battery sensor" if temperature is not None else "Unconfirmed",
                    "♨",
                    f"{temperature:.1f}°C" if temperature is not None else "",
                ),
                (
                    "Storage used",
                    "#2BC8E7",
                    device.storage.percent_used,
                    human_bytes(device.storage.used_bytes)
                    if device.storage.used_bytes is not None
                    else "Unconfirmed",
                    "▥",
                    "",
                ),
                (
                    "Memory used",
                    "#4F7CFF",
                    device.memory.percent_used,
                    human_bytes(device.memory.total_bytes)
                    if device.memory.total_bytes is not None
                    else "Unconfirmed",
                    "▤",
                    "",
                ),
                (
                    "Evidence",
                    "#44E39A",
                    coverage,
                    f"{known} of {total} signals",
                    "◎",
                    "",
                ),
            )
        for label, color, value, detail, glyph, display_text in gauge_specs:
            gauge = RingGauge(label, color, value, detail, glyph, display_text)
            if label == "Thermal":
                gauge.setToolTip(
                    "The center value is the measured battery-sensor temperature. The ring uses "
                    "a transparent 0–60 °C display scale; it is not a CPU utilization reading."
                )
            gauges.addWidget(gauge, 1)
        layout.addLayout(gauges)

        statistics = QFrame()
        statistics.setObjectName("TelemetryStats")
        stats_grid = QGridLayout(statistics)
        stats_grid.setContentsMargins(12, 10, 12, 10)
        stats_grid.setHorizontalSpacing(10)
        stats_grid.setVerticalSpacing(10)
        for column in range(3):
            stats_grid.setColumnStretch(column, 1)
        for index, (label, value, tooltip) in enumerate(self._telemetry_facts(device)):
            tile = QFrame()
            tile.setObjectName("TelemetryTile")
            tile.setToolTip(tooltip)
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(11, 9, 11, 9)
            tile_layout.setSpacing(3)
            key = QLabel(label.upper())
            key.setObjectName("TelemetryLabel")
            val = QLabel(value)
            val.setObjectName("TelemetryValue")
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            tile_layout.addWidget(key)
            tile_layout.addWidget(val)
            stats_grid.addWidget(tile, index // 3, index % 3)
        layout.addWidget(statistics)

        history = QFrame()
        history.setObjectName("TelemetryHistory")
        history_layout = QGridLayout(history)
        history_layout.setContentsMargins(12, 10, 12, 10)
        history_layout.setHorizontalSpacing(12)
        history_layout.setVerticalSpacing(6)
        history_specs = (
            (
                "Battery history",
                "#74D9FF",
                self.battery_history,
                self._latest_metric(self.battery_history, "%"),
                "Battery percentage from recent read-only scans.",
            ),
            (
                "Thermal history",
                "#FF9F68",
                self.temperature_history,
                self._latest_metric(self.temperature_history, " °C"),
                "Battery-sensor temperature from recent read-only scans.",
            ),
            (
                "Connection history",
                "#7DFFB2",
                self.connection_history,
                self._connection_history_status(),
                "Connected=1, authorization needed=0.5, offline=0.",
            ),
            (
                "Storage history",
                "#B68CFF",
                self.storage_history,
                self._latest_metric(self.storage_history, "% used"),
                "/data storage usage from recent read-only scans.",
            ),
        )
        for column, (title, color, values, latest, tooltip) in enumerate(history_specs):
            history_layout.setColumnStretch(column, 1)
            heading = QLabel(title)
            heading.setObjectName("TelemetryChartTitle")
            heading.setToolTip(tooltip)
            chart = MiniChart(color)
            chart.set_values(values)
            chart.setToolTip(tooltip)
            detail = QLabel(latest)
            detail.setObjectName("Muted")
            history_layout.addWidget(heading, 0, column)
            history_layout.addWidget(chart, 1, column)
            history_layout.addWidget(detail, 2, column)
        layout.addWidget(history)
        self.body_layout.addWidget(panel)

    def _telemetry_facts(self, device: AndroidDevice | None) -> tuple[tuple[str, str, str], ...]:
        if device is None:
            return (
                (
                    "Active workspace",
                    self._project_name or "No project selected",
                    "The local ROM Studio project currently supplying Command Deck context.",
                ),
                (
                    "Firmware source",
                    "Loaded" if self._project_has_firmware else "Not loaded",
                    "A loaded source means firmware exists in the protected local workspace.",
                ),
                ("Device link", "Not connected", "No authorized live device is available."),
                (
                    "Device DNA",
                    "UNCONFIRMED",
                    "Device DNA cannot be confirmed until trustworthy device and firmware evidence exists.",
                ),
                (
                    "Guardian boundary",
                    "Read-only policy active",
                    "Command Deck telemetry never changes the phone.",
                ),
                (
                    "History retained",
                    f"{max(map(len, self._metric_histories()), default=0)} of 30 scans",
                    "Only bounded local metric history is shown; device serials are not graphed.",
                ),
            )
        bootloader = (
            "Locked"
            if device.bootloader_locked is True
            else "Unlocked"
            if device.bootloader_locked is False
            else "UNCONFIRMED"
        )
        slot = device.slot_suffix.removeprefix("_").upper() or "UNCONFIRMED"
        ab_state = (
            "A/B"
            if device.ab_update is True
            else "Single-slot reported"
            if device.ab_update is False
            else "UNCONFIRMED"
        )
        virtual_ab = (
            " • Virtual A/B"
            if device.virtual_ab is True
            else " • Virtual A/B not reported"
            if device.virtual_ab is False
            else ""
        )
        root_state = (
            "Evidence detected"
            if device.root_detected is True
            else "No root evidence detected"
            if device.root_detected is False
            else "UNCONFIRMED"
        )
        return (
            (
                "Identity",
                f"{device.display_name} • {device.codename or 'codename UNCONFIRMED'}",
                "Marketing identity and codename collected by Device Engine.",
            ),
            (
                "Platform",
                " • ".join(filter(None, (device.soc_platform, device.abi))) or "UNCONFIRMED",
                "SoC platform and ABI reported by the connected device.",
            ),
            (
                "Android / build",
                " • ".join(filter(None, (device.android_version, device.build_id)))
                or "UNCONFIRMED",
                "Android release and build identity from the current scan.",
            ),
            (
                "Security patch",
                device.security_patch or "UNCONFIRMED",
                "Reported Android security patch level.",
            ),
            (
                "Slot architecture",
                f"Slot {slot} • {ab_state}{virtual_ab}",
                "Active slot and update architecture; unknown fields stay unconfirmed.",
            ),
            (
                "Boot trust",
                f"Bootloader {bootloader} • Verified Boot {device.verified_boot or 'UNCONFIRMED'}",
                "Evidence only. ROMVERSE never recommends or performs bootloader relocking.",
            ),
            (
                "Encryption",
                " • ".join(filter(None, (device.encryption_state, device.encryption_type)))
                or "UNCONFIRMED",
                "Encryption state and type reported by the device.",
            ),
            (
                "Root state",
                root_state,
                "Read-only root signals; absence of evidence is not proof of an unmodified device.",
            ),
            (
                "Transport / uptime",
                f"{device.transport.upper()} • {self._format_uptime(device.uptime_seconds)}",
                "Current connection transport and reported device uptime.",
            ),
        )

    @staticmethod
    def _evidence_coverage(device: AndroidDevice) -> tuple[int, int, int]:
        signals = (
            bool(device.marketing_name or (device.manufacturer and device.model)),
            bool(device.codename),
            bool(device.soc_platform),
            bool(device.android_version),
            bool(device.build_id),
            bool(device.security_patch),
            device.storage.total_bytes is not None,
            device.memory.total_bytes is not None,
            device.bootloader_locked is not None,
            bool(device.verified_boot and device.verified_boot.casefold() != "unknown"),
            bool(device.encryption_state or device.encryption_type),
            bool(device.slot_suffix) or device.ab_update is not None,
        )
        known = sum(signals)
        return round(known * 100 / len(signals)), known, len(signals)

    def _metric_histories(self) -> tuple[list[float], ...]:
        return (
            self.battery_history,
            self.temperature_history,
            self.connection_history,
            self.storage_history,
        )

    @staticmethod
    def _latest_metric(values: list[float], suffix: str) -> str:
        return f"Latest: {values[-1]:g}{suffix}" if values else "No scans recorded"

    def _connection_history_status(self) -> str:
        if not self.connection_history:
            return "No scans recorded"
        latest = self.connection_history[-1]
        status = (
            "Connected" if latest >= 1 else "Authorization needed" if latest >= 0.5 else "Offline"
        )
        return f"Latest: {status}"

    @staticmethod
    def _format_uptime(seconds: int | None) -> str:
        if seconds is None:
            return "uptime UNCONFIRMED"
        days, remainder = divmod(max(0, seconds), 86_400)
        hours, minutes = divmod(remainder, 3_600)
        minutes //= 60
        if days:
            return f"uptime {days}d {hours}h"
        return f"uptime {hours}h {minutes}m"

    def _export_snapshot(self) -> None:
        if not (0 <= self._selected_index < len(self.devices)):
            return
        device = self.devices[self._selected_index]
        destination, _ = QFileDialog.getSaveFileName(
            self, "Export device snapshot", "romverse-device-snapshot.json", "JSON (*.json)"
        )
        if not destination:
            return
        payload = {
            "schema_version": 1,
            "privacy": "redacted",
            "device_key": WorkspacePrivacy(self.workspace).pseudonym(device.serial)
            if self.workspace is not None
            else "local-session",
            "state": device.state.value,
            "transport": device.transport,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "product": device.product,
            "codename": device.codename,
            "android_version": device.android_version,
            "api_level": device.api_level,
            "build_id": device.build_id,
            "rom_display": device.rom_display,
            "security_patch": device.security_patch,
            "battery_percent": device.battery_percent,
            "battery_temperature_c": device.battery_temperature_c,
            "storage": {
                "total_bytes": device.storage.total_bytes,
                "used_bytes": device.storage.used_bytes,
                "available_bytes": device.storage.available_bytes,
                "percent_used": device.storage.percent_used,
            },
            "memory": {
                "total_bytes": device.memory.total_bytes,
                "available_bytes": device.memory.available_bytes,
                "percent_used": device.memory.percent_used,
            },
            "bootloader_locked": device.bootloader_locked,
            "verified_boot": str(device.verified_boot).strip().casefold(),
            "root_detected": device.root_detected,
            "root_manager_candidate": device.root_manager_candidate,
            "root_manager_evidence": device.root_manager_evidence,
            "errors": list(device.errors),
        }
        try:
            Path(destination).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            self.device_note.setText(f"Redacted snapshot exported: {Path(destination).name}")
        except OSError:
            self.device_note.setText("Snapshot export failed; no device data was changed.")

    def render_device(self, device: AndroidDevice) -> None:
        self._clear_body()
        root_review = review_root_identity(
            device.root_detected,
            device.root_manager_candidate,
            root_signal_source=device.root_signal_source,
            manager_evidence=device.root_manager_evidence,
        )
        self.device_name.setText(device.display_name)
        self.device_note.setText(device.connection_note)
        if device.state is DeviceState.DEVICE:
            self._set_badge("CONNECTED • READ ONLY", "Good")
        elif device.state is DeviceState.UNAUTHORIZED:
            self._set_badge("AUTHORIZATION NEEDED", "Warning")
        elif device.is_fastboot:
            self._set_badge(
                f"{device.state.value.upper()} • {'PARTIAL' if device.errors else 'READ ONLY'}",
                "Warning" if device.errors else "Good",
            )
        else:
            self._set_badge(device.state.value.upper(), "Warning")

        if device.is_fastboot:
            self._render_fastboot_device(device)
            return
        if device.state is not DeviceState.DEVICE:
            self.show_empty(device.connection_note)
            return

        top = QHBoxLayout()
        top.setSpacing(12)
        overview = QFrame()
        overview.setObjectName("DashboardCard")
        overview_layout = QVBoxLayout(overview)
        overview_layout.setContentsMargins(16, 12, 16, 14)
        overview_layout.addWidget(self._dashboard_heading("DEVICE PORTAL"))
        overview_body = QHBoxLayout()
        overview_body.addWidget(PhoneMockup())
        facts = QVBoxLayout()
        model = QLabel(device.display_name)
        model.setObjectName("DashboardHero")
        facts.addWidget(model)
        codename = QLabel(
            f"Codename: <span style='color:#B35CFF'>{device.codename or 'Unavailable'}</span>"
        )
        codename.setTextFormat(Qt.TextFormat.RichText)
        facts.addWidget(codename)
        fact_rows = (
            ("◉", "Android Version", device.android_version or "Unavailable"),
            ("✣", "ROM / Display", device.rom_display or "Unavailable"),
            ("⌘", "Build ID", device.build_id or "Unavailable"),
            ("△", "Kernel / ABI", device.abi or "Unavailable"),
            ("▣", "Security Patch", device.security_patch or "Unavailable"),
            ("▱", "Verified Boot", device.verified_boot.title()),
            ("◆", "Root Evidence", root_review.title),
            (
                "✦",
                "ROMVERSE Companion",
                device.companion_version
                or ("Connected" if device.companion_installed else "Not installed"),
            ),
        )
        for glyph, label, value in fact_rows:
            row = QHBoxLayout()
            icon = QLabel(glyph)
            icon.setStyleSheet("color:#B45CFF; font-size:16px;")
            key = QLabel(label)
            key.setObjectName("Muted")
            val = QLabel(value)
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            val.setWordWrap(True)
            row.addWidget(icon)
            row.addWidget(key)
            row.addStretch()
            row.addWidget(val, 1)
            facts.addLayout(row)
        overview_body.addLayout(facts, 1)
        overview_layout.addLayout(overview_body)
        top.addWidget(overview, 5)

        storage = device.storage.percent_used
        top.addWidget(self._build_flight_plan_card(), 7)
        top_host = QWidget()
        top_host.setLayout(top)
        self.body_layout.addWidget(top_host)

        self._add_command_cards(connected=True)

        lower = QHBoxLayout()
        lower.setSpacing(12)
        activity = QFrame()
        activity.setObjectName("DashboardCard")
        activity_layout = QVBoxLayout(activity)
        activity_layout.setContentsMargins(16, 12, 16, 12)
        activity_layout.addWidget(self._dashboard_heading("RECENT ACTIVITY"))
        try:
            recent = self.activity_store.list_recent(5) if self.activity_store else ()
            ledger_error = ""
        except ActivityStoreError as exc:
            recent = ()
            ledger_error = str(exc)
        for event in recent:
            row = QHBoxLayout()
            icon = QLabel(
                "✓" if event.outcome == "success" else "!" if event.outcome == "attention" else "◇"
            )
            icon.setStyleSheet(
                "color:#42E7B4; font-size:18px;"
                if event.outcome == "success"
                else "color:#FFB84D; font-size:18px;"
                if event.outcome == "attention"
                else "color:#37DFF2; font-size:18px;"
            )
            text = QVBoxLayout()
            text.addWidget(QLabel(event.title))
            muted = QLabel(
                f"{event.detail}  •  {_activity_time(event.recorded_at)}  •  {event.source}"
            )
            muted.setObjectName("Muted")
            muted.setWordWrap(True)
            text.addWidget(muted)
            row.addWidget(icon)
            row.addLayout(text, 1)
            activity_layout.addLayout(row)
        if not recent:
            empty = QLabel(ledger_error or "No completed activity has been recorded yet.")
            empty.setObjectName("Danger" if ledger_error else "Muted")
            empty.setWordWrap(True)
            activity_layout.addWidget(empty)
        full_log = QPushButton("☷  View Activity Center")
        full_log.setAccessibleName("Open Activity Center for all recorded ROMVERSE outcomes")
        full_log.clicked.connect(
            lambda _checked=False: self.action_requested.emit("View Activity Center")
        )
        activity_layout.addWidget(full_log)
        lower.addWidget(activity, 1)

        storage_card = QFrame()
        storage_card.setObjectName("DashboardCard")
        storage_layout = QVBoxLayout(storage_card)
        storage_layout.setContentsMargins(16, 12, 16, 12)
        storage_layout.addWidget(self._dashboard_heading("STORAGE USAGE"))
        storage_body = QHBoxLayout()
        donut = StorageDonut()
        donut.set_metric(
            storage,
            f"{human_bytes(device.storage.used_bytes)} used"
            if device.storage.used_bytes is not None
            else "Unconfirmed",
        )
        storage_body.addWidget(donut, 1)
        details = QVBoxLayout()
        details.addStretch()
        for color, label, value in (
            ("#B65CFF", "Used", human_bytes(device.storage.used_bytes)),
            ("#4A83FF", "Available", human_bytes(device.storage.available_bytes)),
            ("#2ABBD8", "Capacity", human_bytes(device.storage.total_bytes)),
            ("#727B91", "Mount", "/data"),
        ):
            row = QHBoxLayout()
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{color};")
            row.addWidget(dot)
            row.addWidget(QLabel(label))
            row.addStretch()
            row.addWidget(QLabel(value))
            details.addLayout(row)
        details.addStretch()
        storage_body.addLayout(details, 1)
        storage_layout.addLayout(storage_body)
        manage = QPushButton("▣  Manage Storage")
        manage.setToolTip("Review storage evidence and safe cleanup guidance.")
        manage.setAccessibleName("Manage Storage in Quantum Optimizer")
        manage.clicked.connect(lambda _checked=False: self.action_requested.emit("Optimize"))
        storage_layout.addWidget(manage)
        lower.addWidget(storage_card, 1)
        lower_host = QWidget()
        lower_host.setLayout(lower)
        self.body_layout.addWidget(lower_host)

        self._add_telemetry_panel(device)

        if device.errors:
            warning = InfoCard("Partial scan")
            warning.add_value("Some details unavailable", "\n".join(device.errors))
            self.body_layout.addWidget(warning)
        self.body_layout.addStretch()

    def _render_fastboot_device(self, device: AndroidDevice) -> None:
        identity = InfoCard("BOOTLOADER IDENTITY  •  GUARDIAN READ ONLY")
        identity.add_value("Detected product / codename", device.codename or "Unconfirmed")
        identity.add_value("Transport mode", device.state.value.upper())
        identity.add_value("Current slot", device.slot_suffix or "Not reported")
        identity.add_value(
            "Bootloader state",
            "Unlocked"
            if device.bootloader_locked is False
            else "Locked"
            if device.bootloader_locked is True
            else "Not reported",
        )
        identity.add_value("Evidence", device.fastboot_capability or "Fastboot observed")
        self.body_layout.addWidget(identity)

        handoff = QFrame()
        handoff.setObjectName("DiagnosticHandoffBar")
        layout = QHBoxLayout(handoff)
        layout.setContentsMargins(18, 14, 18, 14)
        copy = QVBoxLayout()
        heading = QLabel("DEVICE ATLAS  •  EXACT REQUIREMENTS NEXT")
        heading.setObjectName("DashboardHeading")
        detail = QLabel(
            "ROMVERSE can use this product identity to select and review a Device Pack, build contract, and host-tool requirements. Battery, Android version, storage, root, and live health evidence are intentionally unknown until Android boots. Fastboot detection grants no build, flash, wipe, unlock, reboot, or relock authority."
        )
        detail.setObjectName("Muted")
        detail.setWordWrap(True)
        copy.addWidget(heading)
        copy.addWidget(detail)
        layout.addLayout(copy, 1)
        open_atlas = QPushButton("Review Device DNA  →")
        open_atlas.setObjectName("Primary")
        open_atlas.setAccessibleName(
            "Open Device Atlas for the detected read-only Fastboot identity"
        )
        open_atlas.clicked.connect(lambda _checked=False: self.action_requested.emit("Device DNA"))
        layout.addWidget(open_atlas)
        self.body_layout.addWidget(handoff)
        self._add_command_cards(connected=False)
        if device.errors:
            warning = InfoCard("PARTIAL FASTBOOT EVIDENCE")
            warning.add_value("Unsupported or unavailable variables", "\n".join(device.errors))
            self.body_layout.addWidget(warning)
        self.body_layout.addStretch()

    @staticmethod
    def _dashboard_heading(text: str) -> QLabel:
        heading = QLabel(text)
        heading.setObjectName("DashboardHeading")
        return heading

    def _select(self, index: int) -> None:
        device_index = index - 1 if len(self.devices) > 1 else index
        if 0 <= device_index < len(self.devices):
            self._selected_index = device_index
            device = self.devices[device_index]
            self.render_device(device)
            self.device_selected.emit(device.serial)
        elif self.devices:
            self._selected_index = -1
            self.device_selected.emit("")

    def _set_badge(self, text: str, style: str) -> None:
        self.status_badge.setText(text)
        self.status_badge.setObjectName(style)
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _clear_body(self) -> None:
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout() is not None:
                self._delete_layout(item.layout())

    @staticmethod
    def _delete_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _load_metric_history(self) -> None:
        if self.metrics_history_path is None:
            return
        try:
            payload = json.loads(self.metrics_history_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("schema_version") != 1:
                return
            for name in ("battery", "temperature", "connection", "storage"):
                values = payload.get(name, [])
                if not isinstance(values, list):
                    continue
                cleaned = [float(value) for value in values if isinstance(value, (int, float))]
                setattr(self, f"{name}_history", cleaned[-30:])
        except (OSError, ValueError, TypeError):
            return

    def _save_metric_history(self) -> None:
        if self.metrics_history_path is None:
            return
        try:
            self.metrics_history_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.metrics_history_path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "battery": self.battery_history,
                        "temperature": self.temperature_history,
                        "connection": self.connection_history,
                        "storage": self.storage_history,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.metrics_history_path)
        except OSError:
            return


def _activity_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%d %b • %H:%M")
    except ValueError:
        return "unknown time"
