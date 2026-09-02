from __future__ import annotations

import json
import os
from contextlib import suppress
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from romverse.core.activity import ActivityStoreError
from romverse.device.models import AndroidDevice
from romverse.diagnostics.analyzer import DiagnosticAnalyzer
from romverse.diagnostics.history import DiagnosticHistoryError, DiagnosticHistoryStore
from romverse.diagnostics.models import DiagnosticReport, Finding, Severity
from romverse.diagnostics.optimizer import OptimizerSafetyError, RomverseCacheOptimizer
from romverse.knowledge.advisor import recommend_for_findings
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
    ) -> None:
        super().__init__()
        self.analyzer = analyzer
        self.history = history
        self.cache_optimizer = cache_optimizer or RomverseCacheOptimizer(history.workspace)
        self.score_history_path = self.history.root / "_health-score-history.json"
        self.devices: list[AndroidDevice] = []
        self.current_device: AndroidDevice | None = None
        self.current_report: DiagnosticReport | None = None
        self.finding_cards: dict[str, FindingCard] = {}
        self.action_plan_card: QFrame | None = None

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
            "Live health graphs, evidence-backed recommendations, and Guardian-safe optimization guidance."
        )
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        text.addWidget(eyebrow)
        text.addWidget(title)
        text.addWidget(subtitle)
        header.addLayout(text, 1)
        page.addLayout(header)
        actions = QHBoxLayout()
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
        self.selector = QComboBox()
        self.selector.setMinimumWidth(220)
        self.selector.setVisible(False)
        self.selector.currentIndexChanged.connect(self._select)
        actions.addWidget(self.selector)
        self.refresh = QPushButton("Refresh health data")
        self.refresh.clicked.connect(self.refresh_requested)
        actions.addWidget(self.refresh)
        self.optimize = QPushButton("Analyze && recommend")
        self.optimize.setToolTip(
            "Re-run read-only evidence checks and recommendations. No device changes are made."
        )
        self.optimize.clicked.connect(self._safe_optimization_review)
        actions.addWidget(self.optimize)
        self.clean_cache = QPushButton("Preview safe cleanup")
        self.clean_cache.setToolTip(
            "Preview stale ROMVERSE cache/temp files older than 24 hours. Projects, firmware, "
            "backups, tools, personal files, and the phone are always excluded."
        )
        self.clean_cache.clicked.connect(self._clean_romverse_cache)
        actions.addWidget(self.clean_cache)
        self.save_button = QPushButton("Save report")
        self.save_button.setObjectName("Primary")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save)
        actions.addWidget(self.save_button)
        page.addLayout(actions)

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
        page.addWidget(self.dashboard_handoff)

        self.overview = QFrame()
        self.overview.setObjectName("HeroCard")
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
        page.addWidget(self.overview)

        resource_card = QFrame()
        resource_card.setObjectName("Card")
        resources = QGridLayout(resource_card)
        resources.setContentsMargins(20, 16, 20, 16)
        resources.setHorizontalSpacing(18)
        resource_title = QLabel("LIVE RESOURCE GRAPH")
        resource_title.setObjectName("Eyebrow")
        resources.addWidget(resource_title, 0, 0, 1, 3)
        self.battery_graph = self._resource_graph("Battery", resources, 1, 0)
        self.storage_graph = self._resource_graph("Storage used", resources, 1, 1)
        self.health_graph = self._resource_graph("Health score", resources, 1, 2)
        page.addWidget(resource_card)

        self.score_history: list[float] = self._load_score_history()
        page.addWidget(QLabel("Health score trend (recent analyses)"))
        self.score_chart = MiniChart("#7dffb2")
        self.score_chart.set_values(self.score_history)
        page.addWidget(self.score_chart)
        self.last_analysis_label = QLabel("Last analysis: not yet completed")
        self.last_analysis_label.setObjectName("Muted")
        page.addWidget(self.last_analysis_label)

        self.body = QScrollArea()
        self.body.setWidgetResizable(True)
        self.body_content = QWidget()
        self.body_content.setObjectName("ScrollContent")
        self.body_layout = QVBoxLayout(self.body_content)
        self.body_layout.setContentsMargins(0, 0, 6, 0)
        self.body_layout.setSpacing(12)
        self.body.setWidget(self.body_content)
        page.addWidget(self.body, 1)

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

    def set_scanning(self, scanning: bool, *, show_progress: bool = True) -> None:
        self.refresh.setEnabled(not scanning)
        self.optimize.setEnabled(not scanning)
        self.clean_cache.setEnabled(not scanning)
        self.refresh.setText("Reading health data…" if scanning else "Refresh health data")
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
            self.save_button.setEnabled(False)
            self.device_name.setText("No device available")
            self.summary.setText("Connect a phone with USB debugging enabled and refresh evidence.")
            self.score.setText("—")
            self._set_resource_graph(self.battery_graph, None)
            self._set_resource_graph(self.storage_graph, None)
            self._set_resource_graph(self.health_graph, None)
            self._empty("No diagnostic claims are made without device evidence.")
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
                "Connect and authorize one phone, then choose Refresh health data. ROMVERSE "
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
        self.report_changed.emit(None)

    def _render(self, device: AndroidDevice) -> None:
        report = self.analyzer.analyze(device)
        self.current_device = device
        self.current_report = report
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
        for finding in report.findings:
            card = FindingCard(finding, evidence)
            self.finding_cards[finding.finding_id] = card
            self.body_layout.addWidget(card)

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
        self.body_layout.addWidget(limitations)
        self.body_layout.addStretch()
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
        boundary = QLabel(
            "Guardian boundary  •  recommendation only; no device change runs automatically"
        )
        boundary.setObjectName("Good")
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
