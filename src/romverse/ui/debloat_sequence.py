from __future__ import annotations

from contextlib import suppress

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from romverse.rom.debloat import (
    DebloatPlan,
    DebloatReceipt,
    DebloatRisk,
    DebloatScan,
    DebloatService,
    SystemAppCandidate,
)
from romverse.ui.background import CoalescedProgress, ManagedRunnable, start_background
from romverse.ui.process_progress import ProcessProgressBar


class DebloatSignals(QObject):
    complete = Signal(object)
    failed = Signal(str)
    progress = Signal(int)


class DebloatWorker(ManagedRunnable):
    def __init__(
        self,
        service: DebloatService,
        project_id: str,
        plan: DebloatPlan | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.project_id = project_id
        self.plan = plan
        self.signals = DebloatSignals()

    @Slot()
    def execute(self) -> None:
        publish_progress = CoalescedProgress(self.signals.progress.emit)
        try:
            result = (
                self.service.scan(self.project_id, publish_progress)
                if self.plan is None
                else self.service.apply(self.plan, publish_progress)
            )
            self.signals.complete.emit(result)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class DebloatAppRow(QFrame):
    COLORS = {
        DebloatRisk.SAFE: "#43E6A8",
        DebloatRisk.CAUTION: "#FFBE45",
        DebloatRisk.PROTECTED: "#FF527A",
    }

    def __init__(self, candidate: SystemAppCandidate) -> None:
        super().__init__()
        self.candidate = candidate
        self.setObjectName("AppRow")
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 11, 14, 11)
        row.setSpacing(12)

        self.checkbox = QCheckBox()
        self.checkbox.setObjectName("AppChoice")
        self.checkbox.setChecked(candidate.risk is DebloatRisk.SAFE)
        self.checkbox.setEnabled(candidate.risk is not DebloatRisk.PROTECTED)
        self.checkbox.setToolTip(candidate.reason)
        row.addWidget(self.checkbox)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {self.COLORS[candidate.risk]}; font-size: 16px;")
        dot.setToolTip(candidate.reason)
        row.addWidget(dot)

        copy = QVBoxLayout()
        name = QLabel(candidate.display_name)
        name.setObjectName("AppName")
        detail = QLabel(
            f"{candidate.partition}  •  {_format_bytes(candidate.size_bytes)}  •  "
            f"{candidate.relative_path}"
        )
        detail.setObjectName("Muted")
        detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        reason = QLabel(candidate.reason)
        reason.setObjectName("Muted")
        reason.setWordWrap(True)
        copy.addWidget(name)
        copy.addWidget(detail)
        copy.addWidget(reason)
        row.addLayout(copy, 1)

        state = QLabel(
            {
                DebloatRisk.SAFE: "SAFE TO REMOVE",
                DebloatRisk.CAUTION: "REVIEW",
                DebloatRisk.PROTECTED: "GUARDIAN LOCKED",
            }[candidate.risk]
        )
        state.setObjectName(candidate.risk.value.title())
        state.setToolTip(candidate.reason)
        row.addWidget(state)


class NebulaDebloatDialog(QDialog):
    """A visual, reversible system-app review inside Genesis Sequence."""

    def __init__(
        self,
        service: DebloatService,
        project_id: str,
        parent: QWidget | None = None,
        *,
        auto_start: bool = True,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.project_id = project_id
        self.scan: DebloatScan | None = None
        self.receipt: DebloatReceipt | None = None
        self.rows: dict[str, DebloatAppRow] = {}
        self.worker: DebloatWorker | None = None
        self.pending_plan: DebloatPlan | None = None
        self.completed = False
        self._pending_candidates: tuple[SystemAppCandidate, ...] = ()
        self._render_index = 0
        self._scan_summary = ""

        self.setWindowTitle("ROMVERSE • Nebula Debloat")
        self.setModal(True)
        self.setMinimumSize(900, 650)
        self.resize(1080, 760)
        self.setStyleSheet(self._stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("Header")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(26, 20, 26, 17)
        eyebrow = QLabel("GENESIS SEQUENCE  /  NEBULA DEBLOAT")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("Choose what leaves the ROM—not what leaves your phone")
        title.setObjectName("Title")
        detail = QLabel(
            "ROMVERSE scans only the isolated firmware tree. Green is recommended, orange "
            "needs your review, and red critical components are permanently locked. Every "
            "applied removal gets an automatic Time Machine rollback snapshot."
        )
        detail.setObjectName("Muted")
        detail.setWordWrap(True)
        header_layout.addWidget(eyebrow)
        header_layout.addWidget(title)
        header_layout.addWidget(detail)
        root.addWidget(header)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(26, 18, 26, 18)
        body_layout.setSpacing(12)

        summary = QHBoxLayout()
        self.status = QLabel("Preparing a bounded system-app scan …")
        self.status.setObjectName("Status")
        summary.addWidget(self.status, 1)
        self.safe_count = _pill("0 GREEN", "Safe")
        self.caution_count = _pill("0 ORANGE", "Caution")
        self.protected_count = _pill("0 RED", "Protected")
        summary.addWidget(self.safe_count)
        summary.addWidget(self.caution_count)
        summary.addWidget(self.protected_count)
        body_layout.addLayout(summary)

        self.progress = ProcessProgressBar()
        body_layout.addWidget(self.progress)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search app name, package hint, partition, or path…")
        self.search.setClearButtonEnabled(True)
        self.search.setEnabled(False)
        self.search.textChanged.connect(self._apply_filters)
        self.risk_filter = QComboBox()
        for label, value in (
            ("All safety levels", ""),
            ("Green • safe recommendations", DebloatRisk.SAFE.value),
            ("Orange • review carefully", DebloatRisk.CAUTION.value),
            ("Red • Guardian locked", DebloatRisk.PROTECTED.value),
        ):
            self.risk_filter.addItem(label, value)
        self.risk_filter.setEnabled(False)
        self.risk_filter.currentIndexChanged.connect(self._apply_filters)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.risk_filter)
        body_layout.addLayout(filters)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.list_widget)
        body_layout.addWidget(self.scroll, 1)

        controls = QHBoxLayout()
        self.green_button = QPushButton("Select green recommendations")
        self.green_button.clicked.connect(self._select_green)
        self.clear_button = QPushButton("Clear selection")
        self.clear_button.clicked.connect(self._clear)
        self.keep_button = QPushButton("Keep every app")
        self.keep_button.clicked.connect(lambda: self._apply(keep_all=True))
        self.apply_button = QPushButton("Apply reviewed removals & continue")
        self.apply_button.setObjectName("Primary")
        self.apply_button.clicked.connect(self._apply)
        controls.addWidget(self.green_button)
        controls.addWidget(self.clear_button)
        controls.addStretch()
        controls.addWidget(self.keep_button)
        controls.addWidget(self.apply_button)
        body_layout.addLayout(controls)
        root.addWidget(body, 1)

        self._set_controls(False)
        if auto_start:
            QTimer.singleShot(0, self._start_scan)

    def _start_scan(self) -> None:
        self.status.setText(
            "Discovering or safely materializing Android app filesystems … Measured app-record "
            "progress will appear once the complete inventory is known."
        )
        self.progress.begin(determinate=False)
        worker = DebloatWorker(self.service, self.project_id)
        worker.signals.progress.connect(self.progress.report)
        worker.signals.complete.connect(self._scan_complete)
        worker.signals.failed.connect(self._failed)
        self.worker = worker
        start_background(worker)

    @Slot(object)
    def _scan_complete(self, result: object) -> None:
        self.worker = None
        self.progress.finish()
        if not isinstance(result, DebloatScan):
            self._failed("Debloat scan returned an unexpected result")
            return
        persisted = self.service.load_scan(self.project_id)
        if persisted is None or persisted != result:
            self._failed(
                "Debloat scan evidence changed before the verified inventory could be displayed"
            )
            return
        self.scan = result
        if not result.candidates:
            self._clear_rows()
            self.safe_count.setText("0 GREEN")
            self.caution_count.setText("0 ORANGE")
            self.protected_count.setText("0 RED")
            discovery = self.service.load_discovery(self.project_id)
            partitions = (
                ", ".join(discovery.partitions)
                if discovery is not None and discovery.partitions
                else "verified Android tree"
            )
            self._scan_summary = (
                "Scan verified • 0 APK files examined • 0 reviewable app groups • "
                f"partitions: {partitions} • no app evidence invented"
            )
            self.status.setText(
                self._scan_summary + " • continue with no app changes"
            )
            self.search.setEnabled(False)
            self.risk_filter.setEnabled(False)
            self._set_controls(False)
            self.keep_button.setEnabled(True)
            self.keep_button.setText("Continue with no app changes")
            return
        self._clear_rows()
        self.safe_count.setText(f"{result.safe_count} GREEN")
        self.caution_count.setText(f"{result.caution_count} ORANGE")
        self.protected_count.setText(f"{result.protected_count} RED")
        self._scan_summary = (
            f"Scan verified • {len(result.candidates)} system app groups • "
            "green recommendations are preselected"
        )
        discovery = self.service.load_discovery(self.project_id)
        if discovery is not None:
            partitions = ", ".join(discovery.partitions) or "no recognized partition"
            self._scan_summary = (
                f"Scan verified • {discovery.apk_files_examined} APK files examined • "
                f"{discovery.candidate_groups} system app groups • "
                f"{discovery.excluded_apk_files} overlay/user-data/unrecognized APKs excluded • "
                f"partitions: {partitions} • green recommendations are preselected"
            )
        self._pending_candidates = result.candidates
        self._render_index = 0
        self.search.setEnabled(False)
        self.risk_filter.setEnabled(False)
        self.status.setText(
            f"Inventory verified • preparing 0 of {len(result.candidates)} app cards …"
        )
        self.progress.begin(determinate=True)
        self._render_next_batch(len(result.candidates) if len(result.candidates) <= 40 else 24)

    def _render_next_batch(self, batch_size: int = 24) -> None:
        total = len(self._pending_candidates)
        end = min(total, self._render_index + max(1, batch_size))
        for candidate in self._pending_candidates[self._render_index : end]:
            row = DebloatAppRow(candidate)
            self.rows[candidate.candidate_id] = row
            self.list_layout.insertWidget(self.list_layout.count() - 1, row)
        self._render_index = end
        self.progress.report(round(end * 100 / max(1, total)))
        if end < total:
            self.status.setText(f"Displaying app inventory • {end} of {total} cards ready …")
            QTimer.singleShot(0, self._render_next_batch)
            return
        self.progress.finish()
        self.status.setText(self._scan_summary)
        self.search.setEnabled(True)
        self.risk_filter.setEnabled(True)
        self._set_controls(True)
        self._apply_filters()

    def _apply_filters(self, _value: object = None) -> None:
        query = self.search.text().strip().casefold()
        risk = str(self.risk_filter.currentData() or "")
        visible = 0
        for row in self.rows.values():
            candidate = row.candidate
            haystack = " ".join(
                (
                    candidate.display_name,
                    candidate.package_hint,
                    candidate.partition,
                    candidate.relative_path,
                )
            ).casefold()
            matches = (not query or query in haystack) and (
                not risk or candidate.risk.value == risk
            )
            row.setVisible(matches)
            visible += int(matches)
        if self._render_index >= len(self._pending_candidates) and (query or risk):
            self.status.setText(
                f"Showing {visible} of {len(self.rows)} verified app groups • filters do not change selections"
            )
        elif self._render_index >= len(self._pending_candidates) and self._scan_summary:
            self.status.setText(self._scan_summary)

    def _apply(self, _checked: bool = False, *, keep_all: bool = False) -> None:
        if self.scan is None or self.worker is not None:
            return
        selected = (
            ()
            if keep_all
            else tuple(
                candidate_id for candidate_id, row in self.rows.items() if row.checkbox.isChecked()
            )
        )
        caution = tuple(
            self.rows[item].candidate.display_name
            for item in selected
            if self.rows[item].candidate.risk is DebloatRisk.CAUTION
        )
        if caution:
            response = QMessageBox.question(
                self,
                "Nebula Debloat • confirm orange apps",
                "Orange apps do not have enough evidence for a green recommendation.\n\n"
                + "\n".join(f"• {name}" for name in caution)
                + "\n\nRemove these reviewed apps from the isolated ROM tree?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response is not QMessageBox.StandardButton.Yes:
                return
        try:
            plan = self.service.create_plan(
                self.scan,
                selected,
                acknowledge_caution=bool(caution),
            )
        except Exception as exc:
            self._failed(str(exc))
            return
        self.pending_plan = plan
        self._set_controls(False)
        self.status.setText(
            "Recording a no-removal decision …"
            if plan.keep_all
            else f"Revalidating, snapshotting, and removing {len(plan.selected_ids)} reviewed "
            "app groups … Full-tree verification has no trustworthy total."
        )
        self.progress.begin(determinate=False)
        worker = DebloatWorker(self.service, self.project_id, plan)
        worker.signals.progress.connect(self.progress.report)
        worker.signals.complete.connect(self._apply_complete)
        worker.signals.failed.connect(self._failed)
        self.worker = worker
        start_background(worker)

    @Slot(object)
    def _apply_complete(self, result: object) -> None:
        self.worker = None
        self.progress.finish()
        plan = self.pending_plan
        self.pending_plan = None
        persisted = self.service.load_receipt(self.project_id)
        if (
            not isinstance(result, DebloatReceipt)
            or plan is None
            or persisted is None
            or persisted != result
            or result.project_id != self.project_id
            or result.plan_id != plan.plan_id
            or result.plan_digest != plan.plan_digest
            or not result.success
            or not result.protected_original_unchanged
            or result.phone_changed
        ):
            self._failed("Debloat operation returned unexpected or unverified terminal evidence")
            return
        self.receipt = result
        self.completed = True
        self.status.setObjectName("Success")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status.setText(
            (
                "✓ NEBULA DEBLOAT COMPLETE • No reviewable apps found • "
                "no app changes made • Genesis may continue"
                if self.scan is not None and not self.scan.candidates
                else "✓ NEBULA DEBLOAT COMPLETE • Every app was kept • Genesis may continue"
            )
            if result.keep_all
            else f"✓ NEBULA DEBLOAT COMPLETE • {result.removed_app_count} app groups removed • "
            f"{_format_bytes(result.reclaimed_bytes)} reclaimed • rollback verified"
        )
        for row in self.rows.values():
            row.checkbox.setEnabled(False)
        self.green_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self.keep_button.setEnabled(False)
        self.apply_button.setEnabled(True)
        self.apply_button.setText("Continue Genesis Sequence")
        with suppress(RuntimeError):
            self.apply_button.clicked.disconnect()
        self.apply_button.clicked.connect(self.accept)

    @Slot(str)
    def _failed(self, message: str) -> None:
        self.worker = None
        self.pending_plan = None
        self.progress.stop()
        discovery = self.service.load_discovery(self.project_id)
        evidence = (
            f" • Evidence: {discovery.apk_files_examined} APK files examined, "
            f"{discovery.recognized_apk_files} recognized, "
            f"{discovery.excluded_apk_files} excluded, phone changed: NO"
            if discovery is not None
            else ""
        )
        self.status.setText(f"Debloat stopped safely • {message}{evidence}")
        self.status.setObjectName("Error")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self._set_controls(self.scan is not None)

    def _select_green(self) -> None:
        for row in self.rows.values():
            row.checkbox.setChecked(row.candidate.risk is DebloatRisk.SAFE)

    def _clear(self) -> None:
        for row in self.rows.values():
            if row.checkbox.isEnabled():
                row.checkbox.setChecked(False)

    def _set_controls(self, enabled: bool) -> None:
        for button in (
            self.green_button,
            self.clear_button,
            self.keep_button,
            self.apply_button,
        ):
            button.setEnabled(enabled)

    def _clear_rows(self) -> None:
        self.rows.clear()
        self._pending_candidates = ()
        self._render_index = 0
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def reject(self) -> None:
        if self.worker is None:
            super().reject()

    @staticmethod
    def _stylesheet() -> str:
        return """
            QDialog { background: #02050A; color: #EEF4FF; }
            QFrame#Header { background: rgba(5, 10, 20, 235); border-bottom: 1px solid #1C3552; }
            QLabel#Eyebrow { color: #43DFF5; font-size: 11px; font-weight: 800; letter-spacing: 2px; }
            QLabel#Title { color: white; font-size: 24px; font-weight: 850; }
            QLabel#Muted { color: #9CB1D4; }
            QLabel#Status { color: #DCE9FF; font-size: 13px; font-weight: 700; }
            QLabel#Success { color: #43E6A8; font-size: 13px; font-weight: 800; }
            QLabel#Error { color: #FF6B8B; font-size: 13px; font-weight: 800; }
            QLabel#AppName { color: white; font-size: 14px; font-weight: 800; }
            QLabel#Safe, QLabel#Caution, QLabel#Protected {
                border-radius: 11px; padding: 5px 9px; font-size: 10px; font-weight: 900;
            }
            QLabel#Safe { color: #43E6A8; background: #072019; border: 1px solid #17694E; }
            QLabel#Caution { color: #FFBE45; background: #211904; border: 1px solid #775B08; }
            QLabel#Protected { color: #FF6B8B; background: #250711; border: 1px solid #7A1934; }
            QFrame#AppRow {
                background: rgba(9, 17, 31, 220); border: 1px solid #243A5B; border-radius: 10px;
            }
            QFrame#AppRow:hover { border-color: #40DDF2; background: rgba(12, 25, 43, 235); }
            QScrollArea { background: transparent; }
            QScrollArea > QWidget > QWidget { background: transparent; }
            QPushButton {
                color: #DCE9FF; background: rgba(12, 24, 43, 230); border: 1px solid #31527D;
                border-radius: 8px; padding: 10px 14px; font-weight: 750;
            }
            QPushButton:hover { border-color: #43DFF5; background: rgba(23, 48, 78, 240); }
            QPushButton:disabled { color: #536783; border-color: #1B2C44; background: #070C14; }
            QPushButton#Primary { color: #031019; background: #42D5EA; border-color: #72E9F8; }
            QPushButton#Primary:hover { background: #67E7F8; }
            QProgressBar#ProcessProgress {
                color: white; background: #080E19; border: 1px solid #243A5B;
                border-radius: 7px; text-align: center; min-height: 18px;
            }
            QProgressBar#ProcessProgress::chunk { background: #3AD5E9; border-radius: 6px; }
        """


def _pill(text: str, object_name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    return label


def _format_bytes(value: int) -> str:
    number = float(max(0, value))
    for unit in ("B", "KiB", "MiB", "GiB"):
        if number < 1024 or unit == "GiB":
            return f"{number:.0f} {unit}" if unit == "B" else f"{number:.1f} {unit}"
        number /= 1024
    return f"{number:.1f} GiB"
