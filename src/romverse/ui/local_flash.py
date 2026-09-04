from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from romverse.device.models import AndroidDevice
from romverse.guardian.local_flash import (
    LocalFlashPlan,
    LocalFlashResult,
    LocalFlashSelection,
    LocalFlashService,
)
from romverse.ui.background import ManagedRunnable, start_background
from romverse.ui.formatters import human_bytes


class LocalFlashSignals(QObject):
    complete = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int, str)


class LocalFlashWorker(ManagedRunnable):
    def __init__(
        self,
        service: LocalFlashService,
        device: AndroidDevice,
        selections: tuple[LocalFlashSelection, ...],
        *,
        plan: LocalFlashPlan | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.device = device
        self.selections = selections
        self.plan = plan
        self.cancel_requested = Event()
        self.signals = LocalFlashSignals()

    def execute(self) -> None:
        try:
            if self.plan is None:
                result = self.service.inspect(self.device, self.selections)
            else:
                result = self.service.execute(
                    self.plan,
                    accepted_digest=self.plan.plan_digest,
                    risk_accepted=True,
                    should_cancel=self.cancel_requested.is_set,
                    progress=self.signals.progress.emit,
                )
            self.signals.complete.emit(result)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class LocalFlashDiscoveryWorker(ManagedRunnable):
    def __init__(self, discover: Callable[[], list[AndroidDevice]]) -> None:
        super().__init__()
        self.discover = discover
        self.signals = LocalFlashSignals()
        self.plan = None

    def execute(self) -> None:
        try:
            self.signals.complete.emit(tuple(self.discover()))
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class LocalFlashDialog(QDialog):
    """Review explicit image mappings and execute only after final user confirmation."""

    operation_finished = Signal(object)

    def __init__(
        self,
        service: LocalFlashService,
        devices: tuple[AndroidDevice, ...],
        parent: QWidget | None = None,
        *,
        discover: Callable[[], list[AndroidDevice]] | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.devices = devices
        self.plan: LocalFlashPlan | None = None
        self.result: LocalFlashResult | None = None
        self.execution_error = ""
        self.last_attempt_device: AndroidDevice | None = None
        self.worker: LocalFlashWorker | LocalFlashDiscoveryWorker | None = None
        self.discover = discover
        self.recovery_requested = False
        self.setWindowTitle("ROMVERSE · Expert image flashing")
        self.resize(1060, 800)
        self.setMinimumSize(820, 640)
        if self.screen() is not None:
            available = self.screen().availableGeometry()
            self.setMinimumSize(min(820, available.width() - 40), min(640, available.height() - 80))
            self.resize(min(1060, available.width() - 40), min(800, available.height() - 80))
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(8)
        eyebrow = QLabel("ARCHITECT MODE  •  DIRECT DEVICE CONTROL")
        eyebrow.setObjectName("Eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("Flash or restore partition images")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        introduction = QLabel(
            "Choose the exact partition and image for each write. ROMVERSE checks the connected "
            "Fastboot target and file integrity, then shows the complete plan before you confirm. "
            "Use stock images here for a manual restore."
        )
        introduction.setWordWrap(True)
        introduction.setObjectName("Muted")
        layout.addWidget(introduction)

        target_row = QHBoxLayout()
        target_label = QLabel("Target phone")
        self.target = QComboBox()
        self.target.setAccessibleName("Phone to flash")
        target_label.setBuddy(self.target)
        for device in devices:
            self.target.addItem(
                f"{device.display_name} · {device.masked_serial()} · {device.state.value}"
            )
        self.target.currentIndexChanged.connect(self._invalidate)
        target_row.addWidget(target_label)
        target_row.addWidget(self.target, 1)
        self.refresh_button = QPushButton("Refresh phones")
        self.refresh_button.setEnabled(discover is not None)
        self.refresh_button.clicked.connect(self._refresh_devices)
        target_row.addWidget(self.refresh_button)
        layout.addLayout(target_row)

        mapping_hint = QLabel(
            "Write order is top to bottom. Enter explicit slot names such as boot_a when "
            "appropriate. Image filenames alone do not prove device compatibility."
        )
        mapping_hint.setWordWrap(True)
        mapping_hint.setObjectName("Muted")
        layout.addWidget(mapping_hint)
        self.images = QTableWidget(0, 2)
        self.images.setHorizontalHeaderLabels(("Destination partition", "Image file"))
        self.images.setAccessibleName("Ordered partition and image mappings")
        self.images.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.images.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.images.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.images.setColumnWidth(0, 230)
        self.images.verticalHeader().setDefaultSectionSize(42)
        self.images.setMinimumHeight(110)
        self.images.cellChanged.connect(self._invalidate)
        layout.addWidget(self.images, 2)
        edits = QHBoxLayout()
        self.add_button = QPushButton("Add image…")
        self.add_button.clicked.connect(self._choose_image)
        self.remove_button = QPushButton("Remove selected")
        self.remove_button.clicked.connect(self._remove_image)
        edits.addWidget(self.add_button)
        edits.addWidget(self.remove_button)
        edits.addStretch()
        self.review_button = QPushButton("Review images and target")
        self.review_button.setObjectName("Primary")
        self.review_button.clicked.connect(self._inspect)
        edits.addWidget(self.review_button)
        layout.addLayout(edits)

        self.status = QLabel(
            "Connect the intended phone in bootloader Fastboot or fastbootd, then add its images."
        )
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.review = QPlainTextEdit()
        self.review.setReadOnly(True)
        self.review.setMinimumHeight(120)
        self.review.setMaximumBlockCount(5000)
        self.review.setAccessibleName("Flash plan, warnings and operation results")
        self.review.setPlaceholderText(
            "Your reviewed writes, full hashes and warnings appear here."
        )
        layout.addWidget(self.review, 3)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setAccessibleName("Completed partition writes")
        layout.addWidget(self.progress)
        boundary = QLabel(
            "Flashing can cause data loss or prevent booting. You are responsible for your selected "
            "images and backup. A completed write does not establish a working ROM. This workflow "
            "leaves rebooting and boot verification as separate steps."
        )
        boundary.setObjectName("Warning")
        boundary.setWordWrap(True)
        layout.addWidget(boundary)
        actions = QHBoxLayout()
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.reject)
        self.cancel_button = QPushButton("Stop after current write")
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.setVisible(False)
        self.recovery_button = QPushButton("Open diagnosis and recovery")
        self.recovery_button.clicked.connect(self._open_recovery)
        self.recovery_button.setVisible(False)
        self.flash_button = QPushButton("Flash reviewed images…")
        self.flash_button.setObjectName("Primary")
        self.flash_button.setEnabled(False)
        self.flash_button.clicked.connect(self._confirm_flash)
        actions.addWidget(self.close_button)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.recovery_button)
        actions.addStretch()
        actions.addWidget(self.flash_button)
        layout.addLayout(actions)
        self._invalidate()

    def add_image(self, path: Path, partition: str = "") -> None:
        if self.worker is not None:
            return
        row = self.images.rowCount()
        self.images.insertRow(row)
        self.images.setItem(row, 0, QTableWidgetItem(partition))
        image_item = QTableWidgetItem(str(path))
        image_item.setFlags(image_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.images.setItem(row, 1, image_item)
        self.images.setCurrentCell(row, 0)
        self._invalidate()

    def _choose_image(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choose partition images", "", "Partition images (*.img *.bin);;All files (*)"
        )
        for path in paths:
            self.add_image(Path(path))

    def _remove_image(self) -> None:
        for row in sorted({item.row() for item in self.images.selectedItems()}, reverse=True):
            self.images.removeRow(row)
        self._invalidate()

    def _selections(self) -> tuple[LocalFlashSelection, ...]:
        return tuple(
            LocalFlashSelection(
                self.images.item(row, 0).text().strip(),
                Path(self.images.item(row, 1).text()),
            )
            for row in range(self.images.rowCount())
            if self.images.item(row, 0) is not None and self.images.item(row, 1) is not None
        )

    def _invalidate(self, *_args: object) -> None:
        self.plan = None
        self.flash_button.setEnabled(False)
        self.review_button.setEnabled(bool(self.devices) and self.images.rowCount() > 0)
        if self.worker is None:
            self.review.clear()
            if self.images.rowCount():
                self.status.setText(
                    "Review these mappings to check the current phone and image bytes."
                )

    def _inspect(self) -> None:
        if self.worker is not None or self.target.currentIndex() < 0:
            return
        self.plan = None
        self.review.clear()
        self.progress.setRange(0, 0)
        self.status.setText("Reading the target and hashing your images…")
        self._start(
            LocalFlashWorker(
                self.service, self.devices[self.target.currentIndex()], self._selections()
            )
        )

    def _refresh_devices(self) -> None:
        if self.worker is not None or self.discover is None:
            return
        self._invalidate()
        self.status.setText("Checking connected phones…")
        self.progress.setRange(0, 0)
        self._start(LocalFlashDiscoveryWorker(self.discover))

    def _start(self, worker: LocalFlashWorker | LocalFlashDiscoveryWorker) -> None:
        self.worker = worker
        self._set_busy(True, writing=worker.plan is not None)
        worker.signals.complete.connect(self._complete)
        worker.signals.failed.connect(self._failed)
        worker.signals.progress.connect(self._progress)
        try:
            start_background(worker)
        except RuntimeError as exc:
            self._failed(str(exc))

    def _set_busy(self, busy: bool, *, writing: bool = False) -> None:
        for widget in (
            self.target,
            self.images,
            self.add_button,
            self.remove_button,
            self.close_button,
        ):
            widget.setEnabled(not busy)
        self.review_button.setEnabled(
            not busy and bool(self.devices) and self.images.rowCount() > 0
        )
        self.refresh_button.setEnabled(not busy and self.discover is not None)
        self.flash_button.setEnabled(not busy and self.plan is not None)
        self.cancel_button.setVisible(busy and writing)
        self.cancel_button.setEnabled(busy and writing)
        self.recovery_button.setEnabled(not busy)
        self.recovery_button.setVisible(
            not busy
            and bool(self.execution_error or (self.result and self.result.phone_change_attempted))
        )

    def _complete(self, value: object) -> None:
        self.worker = None
        self.progress.setRange(0, 100)
        if isinstance(value, tuple) and all(isinstance(item, AndroidDevice) for item in value):
            self.devices = value
            self.target.blockSignals(True)
            self.target.clear()
            for device in value:
                self.target.addItem(
                    f"{device.display_name} · {device.masked_serial()} · {device.state.value}"
                )
            self.target.blockSignals(False)
            self.plan = None
            self.status.setText(
                "Choose the intended phone and review your image mappings."
                if value
                else "No phone detected. Connect in Fastboot or fastbootd and refresh."
            )
            self.progress.setValue(0)
        elif isinstance(value, LocalFlashPlan):
            self.plan = value
            lines = [
                f"TARGET  {value.device_name} · {value.masked_serial}",
                f"PRODUCT  {value.product}    MODE  {value.mode}",
                f"PLAN  {value.plan_digest}",
                "",
            ]
            for index, write in enumerate(value.writes, 1):
                lines.extend(
                    (
                        f"{index}. {write.partition} ← {write.image_name}",
                        f"   File: {human_bytes(write.size_bytes)} · Expanded: {human_bytes(write.expanded_size_bytes)}",
                        f"   SHA-256: {write.sha256}",
                        "",
                    )
                )
            if value.warnings:
                lines.append("REVIEW THESE RISKS")
                lines.extend(f"• {warning}" for warning in value.warnings)
            snapshot_bytes = sum(
                {write.sha256: write.size_bytes for write in value.writes}.values()
            )
            lines.extend(
                (
                    "",
                    f"STORAGE  Private image snapshots need {human_bytes(snapshot_bytes)} plus space for records.",
                    "ROMVERSE retains these approved image copies with the operation receipt for recovery.",
                )
            )
            self.review.setPlainText("\n".join(lines))
            self.status.setText(
                "Review complete. Read the exact writes and warnings before confirming."
            )
            self.progress.setValue(0)
        elif isinstance(value, LocalFlashResult):
            self.result = value
            self.plan = None
            self.status.setText(value.summary)
            self.review.appendPlainText(
                f"\nRESULT  {value.state}\n{value.summary}\nReceipt: {value.receipt_path}"
            )
            for item in value.results:
                self.review.appendPlainText(
                    f"\n{item.partition} · exit {item.returncode}\n{item.output}"
                )
            self.recovery_button.setVisible(value.phone_change_attempted)
            if value.state == "completed":
                self.progress.setValue(100)
            self.operation_finished.emit(value)
        else:
            self._failed("The operation returned an unsupported result. Recheck the phone state.")
            return
        self._set_busy(False)

    def _failed(self, message: str) -> None:
        if isinstance(self.worker, LocalFlashWorker) and self.worker.plan is not None:
            self.result = None
            self.execution_error = message
            self.recovery_button.setVisible(True)
        self.worker = None
        self.plan = None
        self.progress.setRange(0, 100)
        self.status.setText(message)
        self.review.appendPlainText(f"\nOperation stopped: {message}")
        self._set_busy(False)

    def _confirm_flash(self) -> None:
        plan = self.plan
        if plan is None or self.worker is not None:
            return
        question = QMessageBox(self)
        question.setIcon(QMessageBox.Icon.Warning)
        question.setWindowTitle("Confirm exact image writes")
        question.setText(
            f"Write {len(plan.writes)} image(s) to {plan.device_name} {plan.masked_serial}?"
        )
        question.setInformativeText(
            "These writes may erase data or stop the phone booting. Confirm only after reviewing "
            "the partition names, images and warnings. By choosing Flash images, you accept "
            "these risks for this exact plan."
        )
        question.setDetailedText(self.review.toPlainText())
        confirm = question.addButton("Flash images", QMessageBox.ButtonRole.AcceptRole)
        cancel = question.addButton(QMessageBox.StandardButton.Cancel)
        question.setDefaultButton(cancel)
        question.exec()
        if question.clickedButton() is not confirm:
            return
        if self.plan is not plan or self.worker is not None:
            self.status.setText("The selection changed during confirmation. Review the plan again.")
            return
        self.result = None
        self.execution_error = ""
        self.last_attempt_device = self.devices[self.target.currentIndex()]
        self.progress.setValue(0)
        self.status.setText("Rechecking the reviewed target and image bytes before writing…")
        self._start(
            LocalFlashWorker(
                self.service,
                self.devices[self.target.currentIndex()],
                self._selections(),
                plan=plan,
            )
        )

    def _progress(self, done: int, total: int, message: str) -> None:
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)
        self.status.setText(message)

    def _cancel(self) -> None:
        if isinstance(self.worker, LocalFlashWorker):
            self.worker.cancel_requested.set()
            self.cancel_button.setEnabled(False)
            self.status.setText(
                "Stop requested. The current write will finish before the sequence stops."
            )

    def _open_recovery(self) -> None:
        if self.worker is not None:
            return
        self.recovery_requested = True
        self.accept()

    def done(self, result: int) -> None:
        if self.worker is None:
            super().done(result)

    def reject(self) -> None:
        if self.worker is None:
            super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.worker is not None:
            event.ignore()
        else:
            super().closeEvent(event)
