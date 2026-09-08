from __future__ import annotations

import json
import os
from contextlib import suppress
from datetime import datetime

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from romverse.core.activity import ActivityStoreError
from romverse.core.settings import ExperienceMode
from romverse.device.models import AndroidDevice
from romverse.diagnostics.analyzer import DiagnosticAnalyzer
from romverse.diagnostics.history import DiagnosticHistoryError, DiagnosticHistoryStore
from romverse.diagnostics.models import DiagnosticReport, Finding, Severity
from romverse.diagnostics.optimizer import OptimizerSafetyError, RomverseCacheOptimizer
from romverse.knowledge.advisor import recommend_for_findings
from romverse.knowledge.lookup import OfflineKnowledgeService
from romverse.knowledge.models import KnowledgeLookupReport
from romverse.repair.templates import actionable_repair_finding
from romverse.ui.mini_chart import MiniChart
from romverse.ui.process_progress import ProcessProgressBar

SEVERITY_UI = {
    Severity.HEALTHY: ("BASELINE CLEAR", "Good"),
    Severity.INFORMATION: ("INFORMATION", "Eyebrow"),
    Severity.ADVISORY: ("ADVISORY", "Warning"),
    Severity.WARNING: ("WARNING", "Warning"),
    Severity.CRITICAL: ("CRITICAL", "Danger"),
}


class FindingCard(QFrame):
    def __init__(self, finding: Finding, evidence: dict[str, str]) -> None:
        super().__init__()
        self.finding_id = finding.finding_id
        self.setObjectName("Card")
        self.setProperty("diagnosticFocus", False)
        self.setAccessibleName(f"Diagnostic finding: {finding.title}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 17, 20, 17)
        layout.setSpacing(8)
        self.source_context = QLabel("RECOVERY BAY SOURCE  •  EXACT FINDING")
        self.source_context.setObjectName("Eyebrow")
        self.source_context.setVisible(False)
        layout.addWidget(self.source_context)
        heading = QHBoxLayout()
        title = QLabel(finding.title)
        title.setObjectName("SectionTitle")
        label, style = SEVERITY_UI[finding.severity]
        badge = QLabel(label)
        badge.setObjectName(style)
        heading.addWidget(title, 1)
        heading.addWidget(badge)
        layout.addLayout(heading)
        explanation = QLabel(finding.explanation)
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        observed = [f"{key}: {evidence[key]}" for key in finding.evidence_ids if key in evidence]
        if observed:
            proof = QLabel("Evidence  •  " + "   |   ".join(observed))
            proof.setObjectName("Muted")
            proof.setWordWrap(True)
            layout.addWidget(proof)
        if finding.guidance:
            guidance = QLabel("Guidance  •  " + finding.guidance)
            guidance.setObjectName("Muted")
            guidance.setWordWrap(True)
            layout.addWidget(guidance)

    def set_focused(self, focused: bool) -> None:
        self.setProperty("diagnosticFocus", focused)
        self.source_context.setVisible(focused)
        self.style().unpolish(self)
        self.style().polish(self)


class DiagnosticsCenter(QWidget):
    refresh_requested = Signal()
    report_saved = Signal()
    repair_requested = Signal(str)
    knowledge_requested = Signal(str)
    knowledge_article_requested = Signal(str)
    report_changed = Signal(object)

    def __init__(
        self,
        analyzer: DiagnosticAnalyzer,
        history: DiagnosticHistoryStore,
        cache_optimizer: RomverseCacheOptimizer | None = None,
        knowledge_service: OfflineKnowledgeService | None = None,
    ) -> None:
        super().__init__()
        self.analyzer = analyzer
        self.history = history
        self.cache_optimizer = cache_optimizer or RomverseCacheOptimizer(history.workspace)
        self.knowledge_service = knowledge_service or OfflineKnowledgeService(history.workspace)
        self.score_history_path = self.history.root / "_health-score-history.json"
        self.devices: list[AndroidDevice] = []
        self.current_device: AndroidDevice | None = None
        self.current_report: DiagnosticReport | None = None
        self.finding_cards: dict[str, FindingCard] = {}
        self.action_plan_card: QFrame | None = None
        self.offline_report: KnowledgeLookupReport | None = None
        self._experience_mode = ExperienceMode.GUIDED
        self._reduced_motion = False
        self._pending_verification_finding = ""
        self._pending_verification_serial = ""
        self._pending_verification_score: int | None = None
        self._pending_verification_ids: frozenset[str] = frozenset()
        self._last_verification_state = ""
        self._details_user_open = False
        self.details_toggle: QPushButton | None = None
        self.details_container: QFrame | None = None
        self._cockpit_animation: QPropertyAnimation | None = None

        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 30)
        page.setSpacing(18)
        header = QHBoxLayout()
        text = QVBoxLayout()
        eyebrow = QLabel("QUANTUM OPTIMIZER  •  SYSTEM SCAN  •  GUARDIAN SAFE")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("Quantum Optimizer")
        title.setObjectName("Title")
        subtitle = QLabel(
            "One connected path from device evidence to diagnosis, local knowledge, guided action, and verified outcome."
        )
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        text.addWidget(eyebrow)
        text.addWidget(title)
        text.addWidget(subtitle)
        header.addLayout(text, 1)
        page.addLayout(header)
        actions = QHBoxLayout()
        self.selector = QComboBox()
        self.selector.setMinimumWidth(220)
        self.selector.setVisible(False)
        self.selector.currentIndexChanged.connect(self._select)
        actions.addWidget(self.selector)
        actions.addStretch(1)
        self.scan_status_row = QFrame()
        self.scan_status_row.setObjectName("ProcessStatusRow")
        self.scan_status_row.setFixedSize(126, 34)
        scan_status_layout = QHBoxLayout(self.scan_status_row)
        scan_status_layout.setContentsMargins(9, 5, 9, 5)
        scan_status_layout.setSpacing(6)
        self.scan_status_label = QLabel("SCAN")
        self.scan_status_label.setObjectName("ProcessStatusActive")
        scan_status_layout.addWidget(self.scan_status_label)
        self.scan_progress = ProcessProgressBar()
        self.scan_progress.setToolTip(
            "ROMVERSE is collecting read-only health evidence from the connected phone."
        )
        self.scan_progress.setFixedWidth(68)
        scan_status_layout.addWidget(self.scan_progress)
        self.scan_status_row.setVisible(False)
        actions.addWidget(self.scan_status_row)
        self.tools_toggle = QPushButton("Specialist tools")
        self.tools_toggle.setCheckable(True)
        self.tools_toggle.setToolTip(
            "Reveal report export and bounded ROMVERSE cache tools. These do not change the phone."
        )
        self.tools_toggle.toggled.connect(self._set_tools_visible)
        actions.addWidget(self.tools_toggle)
        self.refresh = QPushButton("Scan device health")
        self.refresh.setObjectName("Primary")
        self.refresh.clicked.connect(self.refresh_requested)
        actions.addWidget(self.refresh)
        page.addLayout(actions)

        self.utility_panel = QFrame()
        self.utility_panel.setObjectName("CockpitUtilityBar")
        utility_layout = QHBoxLayout(self.utility_panel)
        utility_layout.setContentsMargins(12, 8, 12, 8)
        utility_layout.addStretch(1)
        self.optimize = QPushButton("Analyze && recommend")
        self.optimize.setToolTip(
            "Re-run read-only evidence checks and recommendations. No device changes are made."
        )
        self.optimize.clicked.connect(self._safe_optimization_review)
        utility_layout.addWidget(self.optimize)
        self.clean_cache = QPushButton("Preview safe cleanup")
        self.clean_cache.setToolTip(
            "Preview stale ROMVERSE cache/temp files older than 24 hours. Projects, firmware, "
            "backups, tools, personal files, and the phone are always excluded."
        )
        self.clean_cache.clicked.connect(self._clean_romverse_cache)
        utility_layout.addWidget(self.clean_cache)
        self.save_button = QPushButton("Save report")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save)
        utility_layout.addWidget(self.save_button)
        self.utility_panel.setVisible(False)
        page.addWidget(self.utility_panel)

        self.flight_path = QFrame()
        self.flight_path.setObjectName("RecoveryFlightPath")
        flight_layout = QHBoxLayout(self.flight_path)
        flight_layout.setContentsMargins(14, 10, 14, 10)
        flight_layout.setSpacing(8)
        self.flight_stages: list[QFrame] = []
        self.flight_stage_values: list[QLabel] = []
        for number, label in enumerate(
            ("DEVICE EVIDENCE", "DIAGNOSIS", "ARCHIVES MATCH", "GUIDED ACTION", "VERIFY OUTCOME"),
            1,
        ):
            stage = QFrame()
            stage.setObjectName("RecoveryStage")
            stage.setProperty("state", "pending")
            stage_layout = QVBoxLayout(stage)
            stage_layout.setContentsMargins(11, 7, 11, 7)
            stage_layout.setSpacing(2)
            step = QLabel(f"{number:02d}")
            step.setObjectName("RecoveryStageNumber")
            value = QLabel(label)
            value.setObjectName("RecoveryStageValue")
            value.setWordWrap(True)
            stage_layout.addWidget(step)
            stage_layout.addWidget(value)
            flight_layout.addWidget(stage, 1)
            self.flight_stages.append(stage)
            self.flight_stage_values.append(value)
        page.addWidget(self.flight_path)

        self.body = QScrollArea()
        self.body.setWidgetResizable(True)
        self.body_content = QWidget()
        self.body_content.setObjectName("ScrollContent")
        self.cockpit_layout = QVBoxLayout(self.body_content)
        self.cockpit_layout.setContentsMargins(0, 0, 6, 0)
        self.cockpit_layout.setSpacing(12)
        self.cockpit_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        self.body.setWidget(self.body_content)
        page.addWidget(self.body, 1)

        self.verification_banner = QFrame()
        self.verification_banner.setObjectName("RecoveryVerification")
        self.verification_banner.setProperty("state", "pending")
        verification_layout = QHBoxLayout(self.verification_banner)
        verification_layout.setContentsMargins(16, 10, 16, 10)
        self.verification_title = QLabel()
        self.verification_title.setObjectName("SectionTitle")
        self.verification_detail = QLabel()
        self.verification_detail.setObjectName("Muted")
        self.verification_detail.setWordWrap(True)
        verification_copy = QVBoxLayout()
        verification_copy.addWidget(self.verification_title)
        verification_copy.addWidget(self.verification_detail)
        verification_layout.addLayout(verification_copy, 1)
        self.verification_banner.setVisible(False)
        self.cockpit_layout.addWidget(self.verification_banner)

        self.dashboard_handoff = QFrame()
        self.dashboard_handoff.setObjectName("DiagnosticHandoffBar")
        dashboard_handoff_layout = QHBoxLayout(self.dashboard_handoff)
        dashboard_handoff_layout.setContentsMargins(18, 13, 18, 13)
        dashboard_handoff_layout.setSpacing(14)
        dashboard_handoff_copy = QVBoxLayout()
        dashboard_handoff_eyebrow = QLabel("COMMAND DECK HANDOFF  •  CURRENT HEALTH EVIDENCE")
        dashboard_handoff_eyebrow.setObjectName("Eyebrow")
        self.dashboard_handoff_title = QLabel()
        self.dashboard_handoff_title.setObjectName("SectionTitle")
        self.dashboard_handoff_detail = QLabel()
        self.dashboard_handoff_detail.setObjectName("Muted")
        self.dashboard_handoff_detail.setWordWrap(True)
        self.dashboard_handoff_detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        dashboard_handoff_copy.addWidget(dashboard_handoff_eyebrow)
        dashboard_handoff_copy.addWidget(self.dashboard_handoff_title)
        dashboard_handoff_copy.addWidget(self.dashboard_handoff_detail)
        dashboard_handoff_layout.addLayout(dashboard_handoff_copy, 1)
        self.dashboard_handoff_badge = QLabel()
        dashboard_handoff_layout.addWidget(self.dashboard_handoff_badge)
        self.dashboard_handoff.setVisible(False)
        self.cockpit_layout.addWidget(self.dashboard_handoff)

        self.overview = QFrame()
        self.overview.setObjectName("RecoveryCockpit")
        overview_layout = QHBoxLayout(self.overview)
        overview_layout.setContentsMargins(24, 20, 24, 20)
        summary = QVBoxLayout()
        self.device_name = QLabel("Waiting for Device Engine…")
        self.device_name.setObjectName("HeroTitle")
        self.summary = QLabel("Connect and authorize a device to begin read-only analysis.")
        self.summary.setObjectName("Muted")
        summary.addWidget(self.device_name)
        summary.addWidget(self.summary)
        overview_layout.addLayout(summary, 1)
        score_box = QVBoxLayout()
        self.score = QLabel("—")
        self.score.setObjectName("HeroTitle")
        self.score.setAlignment(Qt.AlignmentFlag.AlignRight)
        score_label = QLabel("HEALTH SIGNAL SCORE")
        score_label.setObjectName("Eyebrow")
        score_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        score_box.addWidget(self.score)
        score_box.addWidget(score_label)
        overview_layout.addLayout(score_box)
        self.cockpit_layout.addWidget(self.overview)

        self.dynamic_content = QWidget()
        self.dynamic_content.setObjectName("ScrollContent")
        self.body_layout = QVBoxLayout(self.dynamic_content)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(12)
        self.body_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        self.cockpit_layout.addWidget(self.dynamic_content)

        self.resource_card = QFrame()
        self.resource_card.setObjectName("Card")
        resources = QGridLayout(self.resource_card)
        resources.setContentsMargins(20, 16, 20, 16)
        resources.setHorizontalSpacing(18)
        resource_title = QLabel("LIVE RESOURCE GRAPH")
        resource_title.setObjectName("Eyebrow")
        resources.addWidget(resource_title, 0, 0, 1, 3)
        self.battery_graph = self._resource_graph("Battery", resources, 1, 0)
        self.storage_graph = self._resource_graph("Storage used", resources, 1, 1)
        self.health_graph = self._resource_graph("Health score", resources, 1, 2)
        self.cockpit_layout.addWidget(self.resource_card)

        self.score_history: list[float] = self._load_score_history()
        self.score_history_label = QLabel("Health score trend (recent analyses)")
        self.cockpit_layout.addWidget(self.score_history_label)
        self.score_chart = MiniChart("#7dffb2")
        self.score_chart.set_values(self.score_history)
        self.cockpit_layout.addWidget(self.score_chart)
        self.last_analysis_label = QLabel("Last analysis: not yet completed")
        self.last_analysis_label.setObjectName("Muted")
        self.cockpit_layout.addWidget(self.last_analysis_label)
        self.cockpit_layout.addStretch()

        footer = QHBoxLayout()
        self.history_label = QLabel()
        self.history_label.setObjectName("Muted")
        self.saved_label = QLabel("")
        self.saved_label.setObjectName("Good")
        footer.addWidget(self.history_label)
        footer.addStretch()
        footer.addWidget(self.saved_label)
        page.addLayout(footer)
        self._update_history_label()
        self._empty("Diagnostics will appear after the next Device Engine scan.")
        self._set_flight_states(("active", "pending", "pending", "pending", "pending"))

    def set_experience_mode(self, mode: ExperienceMode) -> None:
        """Adjust information density without changing diagnostic or repair policy."""

        try:
            self._experience_mode = ExperienceMode(mode)
        except (TypeError, ValueError):
            self._experience_mode = ExperienceMode.GUIDED
        expert = self._experience_mode is ExperienceMode.EXPERT
        self.tools_toggle.setText("Hide specialist tools" if expert else "Specialist tools")
        self.tools_toggle.blockSignals(True)
        self.tools_toggle.setChecked(expert)
        self.tools_toggle.blockSignals(False)
        self.utility_panel.setVisible(expert)
        self._update_details_visibility()

    def set_reduced_motion(self, enabled: bool) -> None:
        self._reduced_motion = bool(enabled)

    def _set_tools_visible(self, visible: bool) -> None:
        self.utility_panel.setVisible(bool(visible))
        self.tools_toggle.setText("Hide specialist tools" if visible else "Specialist tools")

    def _toggle_details(self, visible: bool) -> None:
        self._details_user_open = bool(visible)
        self._update_details_visibility()

    def _update_details_visibility(self) -> None:
        if self.details_container is None or self.details_toggle is None:
            return
        visible = self._experience_mode is ExperienceMode.EXPERT or self._details_user_open
        self.details_container.setVisible(visible)
        self.details_toggle.blockSignals(True)
        self.details_toggle.setChecked(visible)
        self.details_toggle.setText(
            "Hide supporting evidence" if visible else "Show supporting evidence"
        )
        self.details_toggle.blockSignals(False)

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _set_flight_states(self, states: tuple[str, str, str, str, str]) -> None:
        for stage, state in zip(self.flight_stages, states, strict=True):
            stage.setProperty("state", state)
            self._repolish(stage)

    def _animate_cockpit(self) -> None:
        if self._reduced_motion or not self.isVisible():
            return
        effect = self.overview.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(self.overview)
            self.overview.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(170)
        animation.setStartValue(0.78)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._cockpit_animation = animation
        animation.start()

    def mark_repair_handoff(self, finding_id: str) -> None:
        """Remember the pre-action evidence so the next scan can compare outcomes."""

        report = self.current_report
        normalized = finding_id.strip()[:120]
        if report is None or not normalized:
            return
        self._pending_verification_finding = normalized
        self._pending_verification_serial = (
            self.current_device.serial if self.current_device is not None else ""
        )
        self._pending_verification_score = report.health_score
        self._pending_verification_ids = frozenset(
            finding.finding_id for finding in report.findings
        )
        self._last_verification_state = ""
        self.verification_title.setText("Outcome verification is ready")
        self.verification_detail.setText(
            "After completing or leaving the guided action, scan device health again. "
            "ROMVERSE will compare fresh evidence with this baseline; it will not assume the action worked."
        )
        self.verification_banner.setProperty("state", "pending")
        self._repolish(self.verification_banner)
        self.verification_banner.setVisible(True)
        self._set_flight_states(("complete", "complete", "complete", "complete", "active"))

    def _complete_pending_verification(
        self,
        device: AndroidDevice,
        report: DiagnosticReport,
    ) -> None:
        target = self._pending_verification_finding
        if not target:
            return
        if self._pending_verification_serial != device.serial:
            self.verification_title.setText("The original phone is required for comparison")
            self.verification_detail.setText(
                "This fresh scan belongs to a different device. ROMVERSE kept the original baseline and made no outcome claim."
            )
            self.verification_banner.setProperty("state", "attention")
            self._repolish(self.verification_banner)
            self.verification_banner.setVisible(True)
            return
        current_ids = frozenset(finding.finding_id for finding in report.findings)
        resolved = sorted(self._pending_verification_ids - current_ids)
        new = sorted(current_ids - self._pending_verification_ids)
        target_resolved = target not in current_ids
        previous_score = self._pending_verification_score
        score_delta = report.health_score - previous_score if previous_score is not None else 0
        state = "complete" if target_resolved else "attention"
        self._last_verification_state = state
        self.verification_title.setText(
            "Fresh evidence no longer reports the selected issue"
            if target_resolved
            else "Fresh evidence still reports the selected issue"
        )
        delta_text = f"{score_delta:+d}" if previous_score is not None else "unavailable"
        self.verification_detail.setText(
            f"Compared with the saved baseline: {len(resolved)} finding(s) cleared, "
            f"{len(new)} new, health score change {delta_text}. "
            "This is an evidence comparison, not proof that a particular action caused the change."
        )
        self.verification_banner.setProperty("state", state)
        self._repolish(self.verification_banner)
        self.verification_banner.setVisible(True)
        self._pending_verification_finding = ""
        self._pending_verification_serial = ""
        self._pending_verification_score = None
        self._pending_verification_ids = frozenset()

    def set_scanning(self, scanning: bool, *, show_progress: bool = True) -> None:
        self.refresh.setEnabled(not scanning)
        self.optimize.setEnabled(not scanning)
        self.clean_cache.setEnabled(not scanning)
        self.refresh.setText("Reading health data…" if scanning else "Scan device health")
        active = scanning and show_progress
        self.scan_status_row.setVisible(active)
        if active:
            self.scan_progress.begin()
        elif scanning:
            self.scan_progress.stop()
        else:
            self.scan_progress.finish()

    def _safe_optimization_review(self) -> None:
        """Request a fresh read-only snapshot for optimizer recommendations."""
        self.saved_label.setText("Analyzing device health and recommendations…")
        self.refresh_requested.emit()

    def _clean_romverse_cache(self) -> None:
        try:
            preview = self.cache_optimizer.preview()
        except (OptimizerSafetyError, OSError) as exc:
            QMessageBox.warning(
                self,
                "Safe cleanup unavailable",
                f"ROMVERSE stopped before changing any files.\n\n{exc}",
            )
            return
        if preview.file_count == 0:
            details = ["No stale ROMVERSE temporary files are ready for cleanup."]
            if preview.skipped_recent:
                details.append(
                    f"{preview.skipped_recent} recent file(s) were preserved by the 24-hour safety window."
                )
            if preview.skipped_unsafe:
                details.append(
                    f"{preview.skipped_unsafe} link or special-file item(s) were safely ignored."
                )
            details.append(
                "Projects, firmware, backups, tools, personal files, and phone data were not scanned."
            )
            QMessageBox.information(self, "ROMVERSE cache is already clean", "\n\n".join(details))
            self.saved_label.setText("Safe cleanup preview complete  •  nothing eligible")
            return
        answer = QMessageBox.question(
            self,
            "Confirm bounded ROMVERSE cleanup",
            f"The verified preview found {preview.file_count} stale temporary file(s), "
            f"recovering up to {self._format_bytes(preview.total_bytes)}.\n\n"
            "Fixed scope: ROMVERSE workspace/cache and workspace/temp only.\n"
            "Minimum age: 24 hours. Symlinks and changed files are rejected.\n\n"
            "Projects, original firmware, working ROMs, builds, reports, backups, tools, "
            "personal files, and the connected phone are excluded.\n\n"
            f"Plan fingerprint: {preview.plan_digest[:20]}…\n\nProceed?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.saved_label.setText("Safe cleanup cancelled  •  no files changed")
            return
        try:
            receipt = self.cache_optimizer.clean(preview)
        except (OptimizerSafetyError, OSError) as exc:
            QMessageBox.warning(
                self,
                "Safe cleanup stopped",
                f"ROMVERSE rejected the cleanup because its verified boundary changed.\n\n{exc}",
            )
            self.saved_label.setText("Safe cleanup stopped  •  review required")
            return
        self.saved_label.setText(
            f"Safe cleanup complete  •  {receipt.files_removed} file(s)  •  "
            f"{self._format_bytes(receipt.bytes_recovered)} recovered  •  receipt {receipt.receipt_id[:12]}…"
        )
        if receipt.files_changed_or_missing:
            QMessageBox.information(
                self,
                "Cleanup completed with preserved changes",
                f"ROMVERSE removed {receipt.files_removed} verified stale file(s).\n\n"
                f"{receipt.files_changed_or_missing} file(s) changed after preview and were preserved.\n"
                f"Receipt: {receipt.receipt_path}",
            )
        if self.history.activity_store is not None:
            with suppress(ActivityStoreError):
                self.history.activity_store.record(
                    "optimizer",
                    "ROMVERSE temporary cache cleaned",
                    f"{receipt.files_removed} stale file(s) removed • "
                    f"{self._format_bytes(receipt.bytes_recovered)} recovered • "
                    f"receipt {receipt.receipt_id[:12]}… • phone untouched",
                    outcome="success",
                    source="Quantum Optimizer",
                )

    @staticmethod
    def _format_bytes(size: int) -> str:
        value = float(size)
        units = ("B", "KB", "MB", "GB")
        unit = units[0]
        for unit in units:
            if value < 1024 or unit == units[-1]:
                break
            value /= 1024
        return f"{value:.1f} {unit}"

    def set_devices(self, devices: list[AndroidDevice]) -> None:
        self.dashboard_handoff.setVisible(False)
        self.devices = devices
        self.selector.blockSignals(True)
        self.selector.clear()
        for device in devices:
            self.selector.addItem(f"{device.display_name}  •  {device.masked_serial()}")
        self.selector.setVisible(len(devices) > 1)
        self.selector.blockSignals(False)
        self.saved_label.clear()
        if devices:
            self._render(devices[0])
        else:
            self.current_device = None
            self.current_report = None
            self.offline_report = None
            self.save_button.setEnabled(False)
            self.device_name.setText("No device available")
            self.summary.setText(
                "Connect a phone with USB debugging enabled, then choose Scan device health."
            )
            self.score.setText("—")
            self._set_resource_graph(self.battery_graph, None)
            self._set_resource_graph(self.storage_graph, None)
            self._set_resource_graph(self.health_graph, None)
            self._empty("No diagnostic claims are made without device evidence.")
            if self._pending_verification_finding:
                self.verification_title.setText("Reconnect the same phone to verify the outcome")
                self.verification_detail.setText(
                    "The pre-action baseline is retained locally. No result will be claimed until a fresh authorized scan is available."
                )
                self.verification_banner.setProperty("state", "pending")
                self._repolish(self.verification_banner)
                self.verification_banner.setVisible(True)
                self._set_flight_states(("active", "pending", "pending", "complete", "active"))
            else:
                self.verification_banner.setVisible(False)
                self._set_flight_states(("active", "pending", "pending", "pending", "pending"))
            self.report_changed.emit(None)

    def open_dashboard_intent(self, action: str) -> bool:
        """Present the current Health Review without silently launching another scan."""

        requested = str(action).strip()
        if requested not in {"Health Review", "System Scan"}:
            return False
        title_prefix = "System Scan" if requested == "System Scan" else "Health Review"
        report = self.current_report
        device = self.current_device
        if report is None or device is None:
            self._show_dashboard_handoff(
                f"{title_prefix} needs fresh Device Engine evidence",
                "Connect and authorize one phone, then choose Scan device health. ROMVERSE "
                "will not infer a health score from stale or absent telemetry. NO SCAN, "
                "OPTIMIZATION, CLEANUP, OR PHONE ACTION STARTED.",
                "EVIDENCE NEEDED",
                ready=False,
            )
            self.refresh.setFocus(Qt.FocusReason.OtherFocusReason)
            return True
        review_levels = {Severity.ADVISORY, Severity.WARNING, Severity.CRITICAL}
        actionable = tuple(
            finding for finding in report.findings if finding.severity in review_levels
        )
        ranking = {
            Severity.HEALTHY: 0,
            Severity.INFORMATION: 1,
            Severity.ADVISORY: 2,
            Severity.WARNING: 3,
            Severity.CRITICAL: 4,
        }
        priority = max(report.findings, key=lambda item: ranking[item.severity], default=None)
        priority_text = priority.title if priority is not None else "No findings reported"
        self._show_dashboard_handoff(
            f"{title_prefix} • {report.device_name} • score {report.health_score}",
            f"The current read-only report contains {len(report.findings)} finding(s); "
            f"{len(actionable)} need review. Highest priority: {priority_text}. The Recommended "
            "Action Plan below links exact findings to Archives and Recovery Bay. NO NEW SCAN, "
            "OPTIMIZATION, CLEANUP, OR PHONE ACTION STARTED.",
            "ALL CLEAR" if not actionable else f"{len(actionable)} REVIEW",
            ready=not actionable,
        )
        if self.action_plan_card is not None:
            self.body.ensureWidgetVisible(self.action_plan_card, 0, 24)
        self.refresh.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def _show_dashboard_handoff(
        self,
        title: str,
        detail: str,
        badge: str,
        *,
        ready: bool,
    ) -> None:
        self.dashboard_handoff_title.setText(title)
        self.dashboard_handoff_detail.setText(detail)
        self.dashboard_handoff_badge.setText(badge)
        self.dashboard_handoff_badge.setObjectName("Good" if ready else "Warning")
        self.dashboard_handoff_badge.style().unpolish(self.dashboard_handoff_badge)
        self.dashboard_handoff_badge.style().polish(self.dashboard_handoff_badge)
        self.dashboard_handoff.setVisible(True)

    def show_error(self, message: str) -> None:
        self.current_device = None
        self.current_report = None
        self.offline_report = None
        self.save_button.setEnabled(False)
        self.device_name.setText("Diagnostics unavailable")
        self.summary.setText(message)
        self.score.setText("—")
        self._set_resource_graph(self.battery_graph, None)
        self._set_resource_graph(self.storage_graph, None)
        self._set_resource_graph(self.health_graph, None)
        self._empty(
            "Device Engine must complete successfully before ROMVERSE can analyze evidence."
        )
        self._set_flight_states(("attention", "pending", "pending", "pending", "pending"))
        self.report_changed.emit(None)

    def _render(self, device: AndroidDevice) -> None:
        report = self.analyzer.analyze(device)
        self._complete_pending_verification(device, report)
        self.current_device = device
        self.current_report = report
        try:
            self.offline_report = self.knowledge_service.scan_after_diagnostic_report(
                device,
                report,
                limit=5,
            )
        except (OSError, ValueError, TypeError):
            self.offline_report = None
        self.device_name.setText(report.device_name)
        self.summary.setText(report.summary)
        self.score.setText(str(report.health_score))
        self._set_resource_graph(self.battery_graph, device.battery_percent)
        self._set_resource_graph(self.storage_graph, device.storage.percent_used)
        self._set_resource_graph(self.health_graph, report.health_score)
        self.last_analysis_label.setText(
            f"Last analysis: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )
        self.score_history.append(float(report.health_score))
        self.score_history = self.score_history[-30:]
        self._save_score_history()
        self.score_chart.set_values(self.score_history)
        self.save_button.setEnabled(True)
        self._clear_body()
        evidence = {item.evidence_id: item.value for item in report.evidence}
        self.action_plan_card = self._action_plan(report)
        self.body_layout.addWidget(self.action_plan_card)

        self.details_toggle = QPushButton("Show supporting evidence")
        self.details_toggle.setObjectName("CockpitDisclosure")
        self.details_toggle.setCheckable(True)
        self.details_toggle.setToolTip(
            "Reveal the individual findings and analysis boundaries behind the recommendation."
        )
        self.details_toggle.toggled.connect(self._toggle_details)
        self.body_layout.addWidget(self.details_toggle)
        self.details_container = QFrame()
        self.details_container.setObjectName("CockpitEvidencePanel")
        details_layout = QVBoxLayout(self.details_container)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(12)
        for finding in report.findings:
            card = FindingCard(finding, evidence)
            self.finding_cards[finding.finding_id] = card
            details_layout.addWidget(card)

        limitations = QFrame()
        limitations.setObjectName("Card")
        layout = QGridLayout(limitations)
        layout.setContentsMargins(20, 17, 20, 17)
        title = QLabel("Analysis boundaries")
        title.setObjectName("SectionTitle")
        layout.addWidget(title, 0, 0)
        copy = QLabel("\n".join(f"• {item}" for item in report.limitations))
        copy.setObjectName("Muted")
        copy.setWordWrap(True)
        layout.addWidget(copy, 1, 0)
        details_layout.addWidget(limitations)
        self.body_layout.addWidget(self.details_container)
        self.body_layout.addStretch()
        actionable = any(
            finding.severity in {Severity.ADVISORY, Severity.WARNING, Severity.CRITICAL}
            for finding in report.findings
        )
        archive_state = "complete" if self.offline_report is not None else "attention"
        if self._last_verification_state:
            action_state = "complete"
            verification_state = self._last_verification_state
        elif self._pending_verification_finding:
            action_state = "complete"
            verification_state = "active"
        elif actionable:
            action_state = "active"
            verification_state = "pending"
        else:
            action_state = "complete"
            verification_state = "active"
        self._set_flight_states(
            ("complete", "complete", archive_state, action_state, verification_state)
        )
        self._details_user_open = False
        self._update_details_visibility()
        self._animate_cockpit()
        self.report_changed.emit(report)

    def open_finding(self, finding_id: str) -> bool:
        """Reveal one exact current finding without changing diagnostic evidence."""

        normalized = finding_id.strip()[:120]
        report = self.current_report
        card = self.finding_cards.get(normalized)
        finding = (
            next((item for item in report.findings if item.finding_id == normalized), None)
            if report is not None
            else None
        )
        for candidate in self.finding_cards.values():
            candidate.set_focused(False)
        if card is None or finding is None:
            self.saved_label.setText("Recovery source changed  •  refresh current evidence")
            self.saved_label.setObjectName("Warning")
            self.saved_label.style().unpolish(self.saved_label)
            self.saved_label.style().polish(self.saved_label)
            return False
        self._details_user_open = True
        self._update_details_visibility()
        card.set_focused(True)
        self.saved_label.setText(f"Recovery Bay source  •  {normalized}  •  evidence view only")
        self.saved_label.setObjectName("Good")
        self.saved_label.style().unpolish(self.saved_label)
        self.saved_label.style().polish(self.saved_label)
        self.body.ensureWidgetVisible(card, 0, 24)
        return True

    def show_repair_handoff_error(self, finding_id: str) -> None:
        """Keep a failed Recovery Bay handoff visible when optional toasts are disabled."""

        normalized = finding_id.strip()[:120] or "unknown finding"
        self.saved_label.setText(
            f"Recovery handoff stopped  •  {normalized} needs fresh evidence  •  nothing started"
        )
        self.saved_label.setObjectName("Warning")
        self.saved_label.style().unpolish(self.saved_label)
        self.saved_label.style().polish(self.saved_label)

    def _action_plan(self, report: DiagnosticReport) -> QFrame:
        ranking = {
            Severity.HEALTHY: 0,
            Severity.INFORMATION: 1,
            Severity.ADVISORY: 2,
            Severity.WARNING: 3,
            Severity.CRITICAL: 4,
        }
        actionable = tuple(
            finding
            for finding in report.findings
            if finding.severity in {Severity.ADVISORY, Severity.WARNING, Severity.CRITICAL}
        )
        archive_recommendations = recommend_for_findings(report.findings, limit=3)
        archive_primary = archive_recommendations[0] if archive_recommendations else None
        offline_primary = (
            self.offline_report.matches[0]
            if self.offline_report is not None and self.offline_report.matches
            else None
        )
        priority = max(report.findings, key=lambda item: ranking[item.severity], default=None)
        repair_priority = actionable_repair_finding(report)
        card = QFrame()
        card.setObjectName("HeroCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 17, 20, 17)
        heading = QHBoxLayout()
        title = QLabel("RECOMMENDED ACTION PLAN")
        title.setObjectName("Eyebrow")
        status = QLabel(
            "ALL CLEAR" if not actionable else f"{len(actionable)} ITEM(S) NEED ATTENTION"
        )
        status.setObjectName("Good" if not actionable else "Warning")
        heading.addWidget(title)
        heading.addStretch()
        heading.addWidget(status)
        layout.addLayout(heading)
        next_step = QLabel(
            priority.title if actionable and priority is not None else "Continue normal monitoring"
        )
        next_step.setObjectName("HeroTitle")
        layout.addWidget(next_step)
        guidance = QLabel(
            priority.guidance
            if actionable and priority is not None and priority.guidance
            else "No immediate optimization is required. Refresh health data periodically to watch for changes."
        )
        guidance.setObjectName("Muted")
        guidance.setWordWrap(True)
        layout.addWidget(guidance)
        if actionable and archive_primary is not None:
            advisor = QLabel("ROMVERSE ARCHIVES ADVISOR  •  EXACT DIAGNOSTIC MATCH")
            advisor.setObjectName("Eyebrow")
            layout.addWidget(advisor)
            advisor_summary = QLabel(
                f"{archive_primary.article.title}  •  "
                f"{archive_primary.article.source.authority}\n"
                f"{archive_primary.article.meaning}"
            )
            advisor_summary.setObjectName("Muted")
            advisor_summary.setWordWrap(True)
            layout.addWidget(advisor_summary)
        brain = QFrame()
        brain.setObjectName("KnowledgeBrainStrip")
        brain_layout = QHBoxLayout(brain)
        brain_layout.setContentsMargins(14, 10, 14, 10)
        brain_copy = QVBoxLayout()
        brain_eyebrow = QLabel("OFFLINE ARCHIVES BRAIN  •  AUTOMATIC LOCAL SCAN")
        brain_eyebrow.setObjectName("KnowledgeBrainEyebrow")
        brain_copy.addWidget(brain_eyebrow)
        brain_title = QLabel(
            f"{len(self.offline_report.matches)} compatible knowledge match(es)"
            if self.offline_report is not None
            else "Local knowledge scan unavailable"
        )
        brain_title.setObjectName("KnowledgeBrainTitle")
        brain_copy.addWidget(brain_title)
        if offline_primary is not None:
            sources = (
                ", ".join(source.label for source in offline_primary.provenance[:2])
                or "local ROMVERSE evidence"
            )
            brain_detail_text = (
                f"Best match: {offline_primary.record.title}  •  "
                f"{offline_primary.confidence.value.upper()}  •  {sources}"
            )
        elif self.offline_report is not None:
            brain_detail_text = "No compatible local record matched this exact evidence. ROMVERSE did not broaden uncertainty into a repair instruction."
        else:
            brain_detail_text = "Diagnostics remain available, but the local archive could not be read for this scan."
        brain_detail = QLabel(brain_detail_text)
        brain_detail.setObjectName("KnowledgeBrainDetail")
        brain_detail.setWordWrap(True)
        brain_copy.addWidget(brain_detail)
        brain_layout.addLayout(brain_copy, 1)
        layout.addWidget(brain)
        boundary = QLabel(
            "Guardian boundary  •  guidance only; nothing changes the phone until the user reviews and deliberately confirms an exact action"
        )
        boundary.setObjectName("RecoveryBoundary")
        boundary.setWordWrap(True)
        layout.addWidget(boundary)
        if actionable:
            actions = QHBoxLayout()
            search_fixes = QPushButton(
                "Open verified fix in Archives"
                if archive_primary is not None
                else "Search known fixes"
            )
            if archive_primary is not None:
                search_fixes.setToolTip(
                    "Open the exact local guide selected from the typed diagnostic finding. "
                    "This does not start a device change."
                )
                search_fixes.clicked.connect(
                    lambda _checked=False, key=archive_primary.article.key: (
                        self.knowledge_article_requested.emit(key)
                    )
                )
            else:
                search_fixes.setToolTip(
                    "Search verified local ROMVERSE Archives guidance for the highest-priority finding."
                )
                search_fixes.clicked.connect(
                    lambda _checked=False, query=priority.title: self.knowledge_requested.emit(
                        query
                    )
                )
            actions.addWidget(search_fixes)
            actions.addStretch()
            if repair_priority is not None:
                open_repair = QPushButton("Open guided fix in Recovery Bay")
                open_repair.setObjectName("Primary")
                open_repair.setToolTip(
                    "Open the model-aware guided repair workflow for the highest-priority routed "
                    "finding. No device change starts automatically."
                )
                open_repair.clicked.connect(
                    lambda _checked=False, finding_id=repair_priority.finding_id: (
                        self.repair_requested.emit(finding_id)
                    )
                )
                actions.addWidget(open_repair)
            layout.addLayout(actions)
        return card

    def _save(self) -> None:
        if self.current_report is None or self.current_device is None:
            return
        try:
            path = self.history.save(self.current_report, self.current_device)
        except (DiagnosticHistoryError, OSError) as exc:
            self.saved_label.setText(f"Snapshot save stopped safely  •  {exc}")
            return
        self.saved_label.setText(f"Saved integrity-verified report  •  {path.name}")
        self._update_history_label()
        self.report_saved.emit()

    @staticmethod
    def _resource_graph(
        label: str, layout: QGridLayout, row: int, column: int
    ) -> tuple[QLabel, QProgressBar]:
        container = QFrame()
        container.setObjectName("DashboardCard")
        box = QVBoxLayout(container)
        box.setContentsMargins(14, 12, 14, 12)
        value = QLabel(f"{label}  •  —")
        value.setObjectName("Value")
        graph = QProgressBar()
        graph.setRange(0, 100)
        graph.setValue(0)
        graph.setTextVisible(False)
        box.addWidget(value)
        box.addWidget(graph)
        layout.addWidget(container, row, column)
        return value, graph

    @staticmethod
    def _set_resource_graph(graph: tuple[QLabel, QProgressBar], value: int | None) -> None:
        label, bar = graph
        name = label.text().split("  •  ", maxsplit=1)[0]
        if value is None:
            label.setText(f"{name}  •  —")
            bar.setValue(0)
            bar.setStyleSheet("")
            return
        normalized = max(0, min(100, int(value)))
        label.setText(f"{name}  •  {normalized}%")
        bar.setValue(normalized)
        if name == "Battery":
            color = "#FF6685" if normalized < 20 else "#FFB454" if normalized < 40 else "#28E7F5"
            message = "Low battery" if normalized < 20 else "Battery level"
        elif name == "Storage used":
            color = "#FF6685" if normalized >= 90 else "#FFB454" if normalized >= 75 else "#A855F7"
            message = "Storage pressure" if normalized >= 75 else "Storage usage"
        else:
            color = "#44E39A" if normalized >= 80 else "#28E7F5" if normalized >= 60 else "#FFB454"
            message = "Overall evidence-based health score"
        bar.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; }}")
        bar.setToolTip(f"{message}: {normalized}%")

    def _select(self, index: int) -> None:
        if 0 <= index < len(self.devices):
            self.saved_label.clear()
            self._render(self.devices[index])

    def _update_history_label(self) -> None:
        scan = self.history.scan_reports()
        count = len(scan.reports)
        self.history_label.setText(
            f"Local diagnostic history: {count} accepted report"
            f"{'s' if count != 1 else ''}  •  {len(scan.rejected)} rejected  •  identifiers redacted"
        )

    def _empty(self, message: str) -> None:
        self._clear_body()
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(26, 26, 26, 26)
        label = QLabel(message)
        label.setObjectName("Muted")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        self.body_layout.addWidget(card)
        self.body_layout.addStretch()

    def _clear_body(self) -> None:
        self.finding_cards.clear()
        self.action_plan_card = None
        self.details_toggle = None
        self.details_container = None
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _load_score_history(self) -> list[float]:
        try:
            payload = json.loads(self.score_history_path.read_text(encoding="utf-8"))
            values = payload.get("scores", []) if isinstance(payload, dict) else []
            return [max(0.0, min(100.0, float(value))) for value in values][-30:]
        except (OSError, ValueError, TypeError, AttributeError):
            return []

    def _save_score_history(self) -> None:
        try:
            self.score_history_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.score_history_path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps({"schema_version": 1, "scores": self.score_history}, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.score_history_path)
        except OSError:
            # A chart should never make diagnostics unusable if persistence is unavailable.
            return
