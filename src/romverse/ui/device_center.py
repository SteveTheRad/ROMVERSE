from __future__ import annotations

import json
import os
from contextlib import suppress
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
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from romverse.core.activity import ActivityStore, ActivityStoreError
from romverse.core.privacy import WorkspacePrivacy
from romverse.core.settings import ExperienceMode
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device.root_identity import review_root_identity
from romverse.ui.cosmic_icons import quick_action_icon
from romverse.ui.formatters import human_bytes
from romverse.ui.mini_chart import MiniChart
from romverse.ui.process_progress import ProcessProgressBar


class RingGauge(QWidget):
    def __init__(
        self,
        label: str,
        color: str,
        value: int = 0,
        detail: str = "—",
        glyph: str = "◇",
    ) -> None:
        super().__init__()
        self.label = label
        self.color = QColor(color)
        self.value = max(0, min(100, value))
        self.detail = detail
        self.glyph = glyph
        self.setMinimumSize(118, 160)

    def set_metric(self, value: int, detail: str) -> None:
        self.value = max(0, min(100, value))
        self.detail = detail
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width()
        circle = min(96, width - 16)
        rect = QRectF((width - circle) / 2, 5, circle, circle)
        painter.setPen(QPen(QColor("#111827"), 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, 0, 360 * 16)
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
        painter.drawText(rect.adjusted(0, 23, 0, 0), Qt.AlignmentFlag.AlignCenter, f"{self.value}%")
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
        self.value = 0
        self.detail = "—"
        self.setMinimumSize(180, 180)

    def set_metric(self, value: int, detail: str) -> None:
        self.value = max(0, min(100, value))
        self.detail = detail
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.width(), self.height()) - 28
        rect = QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)
        painter.setPen(QPen(QColor("#151B2B"), 24))
        painter.drawArc(rect, 0, 360 * 16)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0, QColor("#C35CFF"))
        gradient.setColorAt(1, QColor("#347BFF"))
        painter.setPen(QPen(QBrush(gradient), 24, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        painter.drawArc(rect, 90 * 16, -int(360 * 16 * self.value / 100))
        painter.setPen(QColor("#F4F7FF"))
        painter.drawText(
            rect.adjusted(0, -12, 0, 0), Qt.AlignmentFlag.AlignCenter, f"{self.value}%"
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
    action_requested = Signal(str)

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
        self.scan_progress = ProcessProgressBar()
        self.scan_progress.setToolTip(
            "ROMVERSE is collecting read-only ADB identity and health evidence."
        )
        page.addWidget(self.scan_progress)

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
        self._selected_index = 0
        self.show_empty("Scanning for devices…")

    def set_experience_mode(self, mode: ExperienceMode) -> None:
        """Apply progressive disclosure without changing device or project state."""

        self._experience_mode = mode
        self._apply_quick_action_visibility()

    def _apply_quick_action_visibility(self) -> None:
        expert = self._experience_mode is ExperienceMode.EXPERT
        command_console = self.quick_action_buttons.get("Command Console")
        if command_console is not None:
            command_console.setVisible(expert)

    def set_scanning(self, scanning: bool) -> None:
        self.refresh.setEnabled(not scanning)
        self.refresh.setText("Scanning…" if scanning else "Scan now")
        if scanning:
            self.scan_progress.begin()
        else:
            self.scan_progress.finish()
        if scanning and not self.devices:
            self.status_badge.setText("SCANNING")
            self.status_badge.setObjectName("Warning")
            self.status_badge.style().unpolish(self.status_badge)
            self.status_badge.style().polish(self.status_badge)

    def set_devices(self, devices: list[AndroidDevice]) -> None:
        self.devices = devices
        self._selected_index = 0
        self.last_scan_label.setText(
            f"Last scan: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )
        self.selector.blockSignals(True)
        self.selector.clear()
        for device in devices:
            self.selector.addItem(f"{device.display_name}  •  {device.masked_serial()}")
        self.selector.setVisible(len(devices) > 1)
        self.selector.blockSignals(False)
        if devices:
            device = devices[0]
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
            if device.battery_percent is not None:
                self.battery_history.append(float(device.battery_percent))
            if device.battery_temperature_c is not None:
                self.temperature_history.append(float(device.battery_temperature_c))
            self.connection_history.append(
                1.0
                if device.state is DeviceState.DEVICE
                else 0.5
                if device.state is DeviceState.UNAUTHORIZED
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
            self.render_device(devices[0])
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
                "Connect with USB debugging enabled, authorize this computer, then scan again."
            )
            self._set_badge("NOT CONNECTED", "Warning")
            self.show_empty(
                "ADB is ready, but no device is visible. Try `adb devices -l` in a terminal to confirm the connection."
            )

    def _record_device_scan(self, device: AndroidDevice) -> None:
        if self.activity_store is None or self.workspace is None:
            return
        state = device.state
        outcome = "success" if state is DeviceState.DEVICE else "attention"
        title = (
            "Device scan completed"
            if state is DeviceState.DEVICE
            else f"Device scan: {state.value}"
        )
        detail = (
            f"{device.display_name} • Android {device.android_version or 'unknown'} • read-only evidence captured"
            if state is DeviceState.DEVICE
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
        if self.devices and self.devices[0].state is DeviceState.DEVICE:
            self.action_requested.emit("Optimize")
            return
        self.refresh_requested.emit()

    def refresh_activity(self) -> None:
        """Re-render cached device evidence so the durable activity card stays current."""
        if 0 <= self._selected_index < len(self.devices):
            self.render_device(self.devices[self._selected_index])

    def show_error(self, message: str) -> None:
        self.device_name.setText("Device Engine needs attention")
        self.device_note.setText(message)
        self._set_badge("ADB ERROR", "Danger")
        self.show_empty(
            "ROMVERSE did not run any device-changing command. Check ADB installation and USB permissions, then retry."
        )

    def show_empty(self, text: str) -> None:
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
        self.body_layout.addWidget(card)
        self.body_layout.addStretch()

    def _export_snapshot(self) -> None:
        if not self.devices:
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
        else:
            self._set_badge(device.state.value.upper(), "Warning")

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

        health_card = QFrame()
        health_card.setObjectName("DashboardCard")
        health_layout = QVBoxLayout(health_card)
        health_layout.setContentsMargins(16, 12, 16, 12)
        health_layout.addWidget(self._dashboard_heading("SYSTEM HEALTH"))
        gauges = QHBoxLayout()
        temperature = int(device.battery_temperature_c or 0)
        storage = int(device.storage.percent_used or 0)
        battery = int(device.battery_percent or 0)
        cpu = RingGauge("CPU", "#A84EFF", min(100, max(4, temperature)), f"{temperature} °C", "▣")
        ram = RingGauge(
            "RAM",
            "#3F7DFF",
            int(device.memory.percent_used or 0),
            (
                f"{human_bytes((device.memory.total_bytes or 0) - (device.memory.available_bytes or 0))} / {human_bytes(device.memory.total_bytes)}"
                if device.memory.total_bytes is not None
                else "Unavailable"
            ),
            "▤",
        )
        disk = RingGauge("Storage", "#2BC8E7", storage, human_bytes(device.storage.used_bytes), "▥")
        charge = RingGauge("Battery", "#EC51C8", battery, device.battery_status or "Unknown", "▯")
        for gauge in (cpu, ram, disk, charge):
            gauges.addWidget(gauge, 1)
        health_layout.addLayout(gauges)
        status = QFrame()
        status.setObjectName("HealthStrip")
        status_layout = QHBoxLayout(status)
        status_layout.setContentsMargins(14, 8, 14, 8)
        pulse = QLabel("〰")
        pulse.setStyleSheet("color:#2CD9EA; font-size:24px;")
        summary = QLabel(
            "System status is <span style='color:#2DE7DA'>Optimal</span><br><span style='color:#9AA5BD'>Guardian read-only monitoring active</span>"
        )
        summary.setTextFormat(Qt.TextFormat.RichText)
        run = QPushButton("⌁  Run System Scan")
        run.clicked.connect(self.refresh_requested)
        status_layout.addWidget(pulse)
        status_layout.addWidget(summary)
        status_layout.addStretch()
        status_layout.addWidget(run)
        health_layout.addWidget(status)
        top.addWidget(health_card, 7)
        top_host = QWidget()
        top_host.setLayout(top)
        self.body_layout.addWidget(top_host)

        actions = QFrame()
        actions.setObjectName("DashboardCard")
        actions_layout = QVBoxLayout(actions)
        actions_layout.setContentsMargins(16, 10, 16, 12)
        actions_layout.addWidget(self._dashboard_heading("QUICK ACTIONS"))
        action_row = QHBoxLayout()
        action_specs = (
            (
                "rocket",
                "#9D48FF",
                "#C266FF",
                "ROM Forge",
                "Open ROM Studio and begin a Genesis Sequence or advanced Architect Mode workflow.",
            ),
            (
                "terminal",
                "#377DFF",
                "#55A0FF",
                "Command Console",
                "Open the Guardian-bounded console for approved host and read-only ADB checks.",
            ),
            (
                "trash",
                "#18CBEA",
                "#51E7F5",
                "App Cleanse",
                "Review removable packages; Guardian Core approval is required before any change.",
            ),
            (
                "sliders",
                "#19BCD4",
                "#43E5EF",
                "Quantum Tune",
                "Open Quantum Optimizer for live health evidence and safe recommendations.",
            ),
            (
                "puzzle",
                "#F126C7",
                "#C946F4",
                "Module Forge",
                "Open Device Atlas to inspect compatible profiles and future module workflows.",
            ),
            (
                "cloud_upload",
                "#A83EF0",
                "#D56BFF",
                "Time Snapshot",
                "Open Time Machine and create a Guardian-reviewed backup plan.",
            ),
            (
                "restore",
                "#3977FF",
                "#6097FF",
                "Time Restore",
                "Open Time Machine to review recovery and restore plans.",
            ),
        )
        self.quick_action_buttons = {}
        for icon_name, start, end, label, tooltip in action_specs:
            button = QToolButton()
            button.setText(label)
            button.setIcon(quick_action_icon(icon_name, 42, start, end))
            button.setIconSize(QSize(42, 42))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setObjectName("QuickAction")
            button.setToolTip(tooltip)
            button.setMinimumHeight(92)
            if label in {
                "Quantum Tune",
                "App Cleanse",
                "Module Forge",
                "Command Console",
            } or label in {
                "ROM Forge",
                "Time Snapshot",
                "Time Restore",
                "View Full Log",
            }:
                button.clicked.connect(
                    lambda _checked=False, target=label: self.action_requested.emit(target)
                )
            self.quick_action_buttons[label] = button
            action_row.addWidget(button, 1)
        self._apply_quick_action_visibility()
        actions_layout.addLayout(action_row)
        self.body_layout.addWidget(actions)

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
        full_log = QPushButton("☷  View Full Log")
        full_log.clicked.connect(lambda _checked=False: self.action_requested.emit("View Full Log"))
        activity_layout.addWidget(full_log)
        lower.addWidget(activity, 1)

        storage_card = QFrame()
        storage_card.setObjectName("DashboardCard")
        storage_layout = QVBoxLayout(storage_card)
        storage_layout.setContentsMargins(16, 12, 16, 12)
        storage_layout.addWidget(self._dashboard_heading("STORAGE USAGE"))
        storage_body = QHBoxLayout()
        donut = StorageDonut()
        donut.set_metric(storage, f"{human_bytes(device.storage.used_bytes)} used")
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
        storage_layout.addWidget(manage)
        lower.addWidget(storage_card, 1)
        lower_host = QWidget()
        lower_host.setLayout(lower)
        self.body_layout.addWidget(lower_host)

        if device.errors:
            warning = InfoCard("Partial scan")
            warning.add_value("Some details unavailable", "\n".join(device.errors))
            self.body_layout.addWidget(warning)
        self.body_layout.addStretch()

    @staticmethod
    def _dashboard_heading(text: str) -> QLabel:
        heading = QLabel(text)
        heading.setObjectName("DashboardHeading")
        return heading

    def _select(self, index: int) -> None:
        if 0 <= index < len(self.devices):
            self._selected_index = index
            self.render_device(self.devices[index])

    def _set_badge(self, text: str, style: str) -> None:
        self.status_badge.setText(text)
        self.status_badge.setObjectName(style)
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)

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
