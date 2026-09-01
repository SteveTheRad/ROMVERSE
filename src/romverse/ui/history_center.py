from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from romverse.diagnostics.history import (
    DiagnosticHistoryError,
    DiagnosticHistoryStore,
    RejectedDiagnosticSnapshot,
    ReportComparison,
    StoredDiagnosticReport,
    StoredFinding,
)
from romverse.knowledge.advisor import article_key_for_diagnostic_finding
from romverse.ui.mini_chart import MiniChart


class HistoryCenter(QWidget):
    current_scan_requested = Signal()
    knowledge_article_requested = Signal(str)
    knowledge_requested = Signal(str)

    def __init__(
        self,
        store: DiagnosticHistoryStore,
    ) -> None:
        super().__init__()
        self.store = store
        self.reports: tuple[StoredDiagnosticReport, ...] = ()
        self.rejected: tuple[RejectedDiagnosticSnapshot, ...] = ()
        self.finding_guide_buttons: dict[str, QPushButton] = {}

        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 30)
        page.setSpacing(18)
        header = QHBoxLayout()
        text = QVBoxLayout()
        eyebrow = QLabel("HEALTH TIMELINE  •  LOCAL AND REDACTED")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("Health Timeline")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Review saved diagnostic snapshots and see which evidence-backed findings changed over time."
        )
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        text.addWidget(eyebrow)
        text.addWidget(title)
        text.addWidget(subtitle)
        header.addLayout(text, 1)
        refresh = QPushButton("Refresh history")
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        self.current_scan_button = QPushButton("Open current Quantum Optimizer")
        self.current_scan_button.setToolTip(
            "Open current read-only device evidence. Historical snapshots remain unchanged."
        )
        self.current_scan_button.clicked.connect(self.current_scan_requested)
        header.addWidget(self.current_scan_button)
        self.export_button = QPushButton("Export selected")
        self.export_button.setToolTip("Save a copy of the selected redacted diagnostic snapshot.")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export_selected)
        header.addWidget(self.export_button)
        page.addLayout(header)

        privacy = QFrame()
        privacy.setObjectName("HeroCard")
        privacy_layout = QHBoxLayout(privacy)
        privacy_layout.setContentsMargins(20, 16, 20, 16)
        privacy_title = QLabel("Privacy boundary active")
        privacy_title.setObjectName("Good")
        privacy_copy = QLabel(
            "Reports remain in your ROMVERSE workspace. Raw serials and build fingerprints are not stored."
        )
        privacy_copy.setObjectName("Muted")
        privacy_copy.setWordWrap(True)
        privacy_layout.addWidget(privacy_title)
        privacy_layout.addSpacing(14)
        privacy_layout.addWidget(privacy_copy, 1)
        page.addWidget(privacy)

        self.evidence_status = QLabel("No diagnostic snapshots have been verified yet.")
        self.evidence_status.setObjectName("Muted")
        self.evidence_status.setWordWrap(True)
        page.addWidget(self.evidence_status)

        trend_header = QLabel("Saved health score trend")
        trend_header.setObjectName("SectionTitle")
        page.addWidget(trend_header)
        self.score_chart = MiniChart("#7dffb2")
        self.score_chart.setToolTip(
            "Health scores from saved diagnostic snapshots, oldest to newest."
        )
        page.addWidget(self.score_chart)

        content = QHBoxLayout()
        content.setSpacing(16)
        self.report_list = QListWidget()
        self.report_list.setObjectName("HistoryList")
        self.report_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.report_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.report_list.setAccessibleName("Verified diagnostic history snapshots")
        self.report_list.setMinimumWidth(290)
        self.report_list.setMaximumWidth(350)
        self.report_list.currentRowChanged.connect(self._select)
        content.addWidget(self.report_list)

        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_content = QWidget()
        self.detail_content.setObjectName("ScrollContent")
        self.detail_layout = QVBoxLayout(self.detail_content)
        self.detail_layout.setContentsMargins(0, 0, 6, 0)
        self.detail_layout.setSpacing(12)
        self.detail_scroll.setWidget(self.detail_content)
        content.addWidget(self.detail_scroll, 1)
        page.addLayout(content, 1)

        self.footer = QLabel()
        self.footer.setObjectName("Muted")
        page.addWidget(self.footer)
        self.refresh()

    def refresh(self) -> None:
        selected_path = None
        row = self.report_list.currentRow()
        if 0 <= row < len(self.reports):
            selected_path = self.reports[row].path

        scan = self.store.scan_reports()
        self.reports = scan.reports
        self.rejected = scan.rejected
        legacy_count = sum(not report.integrity_verified for report in self.reports)
        if self.rejected:
            examples = "; ".join(f"{item.path.name}: {item.reason}" for item in self.rejected[:3])
            suffix = "" if len(self.rejected) <= 3 else f"; +{len(self.rejected) - 3} more"
            self._set_evidence_status(
                f"REJECTED EVIDENCE  •  {len(self.rejected)} snapshot file(s) failed verification. "
                f"They were preserved for review and excluded from trends. {examples}{suffix}",
                "Danger",
            )
        elif legacy_count:
            self._set_evidence_status(
                f"LEGACY EVIDENCE  •  {legacy_count} snapshot(s) predate integrity fingerprints. "
                "They remain readable but are never labelled verified.",
                "Warning",
            )
        elif self.reports:
            self._set_evidence_status(
                f"INTEGRITY VERIFIED  •  {len(self.reports)} snapshot fingerprint(s) passed SHA-256 verification.",
                "Good",
            )
        else:
            self._set_evidence_status("No diagnostic snapshots have been verified yet.", "Muted")
        self.score_chart.set_values(
            [float(report.health_score) for report in reversed(self.reports)]
        )
        self.report_list.blockSignals(True)
        self.report_list.clear()
        selected_row = 0
        for index, report in enumerate(self.reports):
            item = QListWidgetItem(
                f"{report.device_name}\n{_display_time(report.generated_at)}   •   "
                f"Score {report.health_score}   •   "
                f"{'VERIFIED' if report.integrity_verified else 'LEGACY'}"
            )
            item.setToolTip(f"{report.path.name}\n{report.verification_reason}")
            self.report_list.addItem(item)
            if report.path == selected_path:
                selected_row = index
        self.report_list.blockSignals(False)
        self.footer.setText(
            f"{len(self.reports)} accepted privacy-safe snapshot"
            f"{'s' if len(self.reports) != 1 else ''}  •  {len(self.rejected)} rejected"
        )
        if self.reports:
            self.export_button.setEnabled(True)
            self.report_list.setCurrentRow(selected_row)
            self._select(selected_row)
        else:
            self.export_button.setEnabled(False)
            self._empty(
                "No accepted snapshots are available. Open System Scan, review the live evidence, "
                "then select Save report. Rejected files remain preserved in the history folder."
            )

    def open_snapshot(self, snapshot_id: str) -> bool:
        """Re-verify and select one exact integrity-enveloped historical snapshot."""

        self.refresh()
        row = next(
            (
                index
                for index, report in enumerate(self.reports)
                if report.integrity_verified and report.snapshot_id == snapshot_id
            ),
            -1,
        )
        if row < 0:
            return False
        self.report_list.setCurrentRow(row)
        self.report_list.scrollToItem(self.report_list.item(row))
        self._select(row)
        return True

    def _select(self, row: int) -> None:
        if not 0 <= row < len(self.reports):
            return
        report = self.reports[row]
        previous = next(
            (
                candidate
                for candidate in self.reports[row + 1 :]
                if candidate.device_key == report.device_key
            ),
            None,
        )
        comparison = self.store.compare(report, previous) if previous else None
        self._render(report, comparison)

    def _export_selected(self) -> None:
        row = self.report_list.currentRow()
        if not 0 <= row < len(self.reports):
            return
        report = self.reports[row]
        destination, _ = QFileDialog.getSaveFileName(
            self, "Export diagnostic snapshot", report.path.name, "JSON (*.json)"
        )
        if not destination:
            return
        try:
            exported = self.store.export_report(report, Path(destination))
            integrity = "verified" if report.integrity_verified else "legacy / unverified"
            self.footer.setText(f"Exported redacted snapshot ({integrity}): {exported.name}")
        except (DiagnosticHistoryError, OSError) as exc:
            self.footer.setText(f"Export stopped safely: {exc}")

    def _render(
        self,
        report: StoredDiagnosticReport,
        comparison: ReportComparison | None,
    ) -> None:
        self._clear()
        self.finding_guide_buttons.clear()
        hero = QFrame()
        hero.setObjectName("HeroCard")
        layout = QHBoxLayout(hero)
        layout.setContentsMargins(22, 18, 22, 18)
        summary = QVBoxLayout()
        name = QLabel(report.device_name)
        name.setObjectName("HeroTitle")
        copy = QLabel(report.summary)
        copy.setObjectName("Muted")
        summary.addWidget(name)
        summary.addWidget(copy)
        layout.addLayout(summary, 1)
        score = QLabel(str(report.health_score))
        score.setObjectName("HeroTitle")
        layout.addWidget(score)
        self.detail_layout.addWidget(hero)

        change = QFrame()
        change.setObjectName("Card")
        change_layout = QVBoxLayout(change)
        change_layout.setContentsMargins(20, 17, 20, 17)
        change_title = QLabel("Change since previous snapshot")
        change_title.setObjectName("SectionTitle")
        change_layout.addWidget(change_title)
        if comparison is None:
            delta = QLabel("This is the first available snapshot for this device.")
            delta.setObjectName("Muted")
            change_layout.addWidget(delta)
        else:
            direction = "+" if comparison.score_delta > 0 else ""
            delta = QLabel(f"Health signal score: {direction}{comparison.score_delta}")
            delta.setObjectName(
                "Good"
                if comparison.score_delta > 0
                else "Danger"
                if comparison.score_delta < 0
                else "Muted"
            )
            change_layout.addWidget(delta)
            added = QLabel(
                "New findings: " + (", ".join(item.title for item in comparison.added) or "None")
            )
            added.setObjectName("Warning" if comparison.added else "Muted")
            added.setWordWrap(True)
            change_layout.addWidget(added)
            resolved = QLabel(
                "Resolved findings: "
                + (", ".join(item.title for item in comparison.resolved) or "None")
            )
            resolved.setObjectName("Good" if comparison.resolved else "Muted")
            resolved.setWordWrap(True)
            change_layout.addWidget(resolved)
        self.detail_layout.addWidget(change)

        historical_boundary = QLabel(
            "HISTORICAL SNAPSHOT  •  These findings describe saved evidence, not the phone's "
            "current state. Archives guidance is read-only and starts no repair."
        )
        historical_boundary.setObjectName("Warning")
        historical_boundary.setWordWrap(True)
        self.detail_layout.addWidget(historical_boundary)

        for finding in report.findings:
            card = QFrame()
            card.setObjectName("Card")
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(20, 15, 20, 15)
            title = QLabel(finding.title)
            title.setWordWrap(True)
            badge = QLabel(finding.severity.upper())
            badge.setObjectName(_severity_style(finding.severity))
            card_layout.addWidget(title, 1)
            card_layout.addWidget(badge)
            article_key = article_key_for_diagnostic_finding(finding.finding_id, finding.title)
            if article_key:
                guide = QPushButton("Open verified Archives guide")
                guide.setToolTip(
                    "Open the exact local guide mapped from this typed historical finding. "
                    "No current-state claim or device action is created."
                )
                guide.clicked.connect(
                    lambda _checked=False, key=article_key: self.knowledge_article_requested.emit(
                        key
                    )
                )
                card_layout.addWidget(guide)
                self.finding_guide_buttons[finding.finding_id] = guide
            elif finding.severity in {"advisory", "warning", "critical"}:
                guide = QPushButton("Search Archives")
                guide.setToolTip(
                    "Search local verified knowledge using this historical finding title. "
                    "ROMVERSE will not substitute an unrelated exact guide."
                )
                query = self._finding_query(finding)
                guide.clicked.connect(
                    lambda _checked=False, value=query: self.knowledge_requested.emit(value)
                )
                card_layout.addWidget(guide)
                self.finding_guide_buttons[finding.finding_id] = guide
            self.detail_layout.addWidget(card)

        metadata = QLabel(
            f"Captured {_display_time(report.generated_at)}  •  {report.path.name}\n"
            f"Evidence: {report.verification_reason}"
            + (
                f"  •  {report.snapshot_digest[:20]}…\n"
                if report.integrity_verified
                else f"  •  local content fingerprint {report.content_digest[:20]}…\n"
            )
            + "Comparison uses the local pseudonymous device key; no raw serial is retained."
        )
        metadata.setObjectName("Muted")
        metadata.setWordWrap(True)
        metadata.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail_layout.addWidget(metadata)
        self.detail_layout.addStretch()

    @staticmethod
    def _finding_query(finding: StoredFinding) -> str:
        if finding.finding_id == "connection.unavailable":
            return "ADB device connection unavailable"
        return finding.title

    def _set_evidence_status(self, text: str, object_name: str) -> None:
        self.evidence_status.setText(text)
        self.evidence_status.setObjectName(object_name)
        self.evidence_status.style().unpolish(self.evidence_status)
        self.evidence_status.style().polish(self.evidence_status)

    def _empty(self, message: str) -> None:
        self._clear()
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        label = QLabel(message)
        label.setObjectName("Muted")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        self.detail_layout.addWidget(card)
        self.detail_layout.addStretch()

    def _clear(self) -> None:
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()


def _display_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%d %b %Y • %H:%M")
    except ValueError:
        return "Unknown time"


def _severity_style(severity: str) -> str:
    return {
        "healthy": "Good",
        "information": "Eyebrow",
        "advisory": "Warning",
        "warning": "Warning",
        "critical": "Danger",
    }.get(severity, "Muted")
