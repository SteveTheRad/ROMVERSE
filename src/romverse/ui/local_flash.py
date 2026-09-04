from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
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
from romverse.guardian.local_transition import (
    LocalDeviceTransitionService,
    LocalTransitionPlan,
    LocalTransitionResult,
    LocalTransitionTarget,
)
from romverse.rom.local_boot import (
    LocalBootReport,
    LocalBootService,
    LocalBootSession,
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


class LocalTransitionWorker(ManagedRunnable):
    def __init__(self, service, device, target, *, plan=None) -> None:
        super().__init__()
        self.service = service
        self.device = device
        self.target = target
        self.plan = plan
        self.cancel_requested = Event()
        self.signals = LocalFlashSignals()

    def execute(self) -> None:
        try:
            if self.plan is None:
                value = self.service.inspect(self.device, self.target)
            else:
                value = self.service.execute(
                    self.plan,
                    accepted_digest=self.plan.plan_digest,
                    risk_accepted=True,
                    should_cancel=self.cancel_requested.is_set,
                )
            self.signals.complete.emit(value)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class LocalBootWorker(ManagedRunnable):
    def __init__(self, service, device, *, session=None, flash_result=None, stop=False) -> None:
        super().__init__()
        self.service = service
        self.device = device
        self.session = session
        self.flash_result = flash_result
        self.stop = stop
        self.plan = None
        self.signals = LocalFlashSignals()

    def execute(self) -> None:
        try:
            if self.session is None:
                self.session = self.service.begin(self.device, self.flash_result)
            value = (
                self.service.stop(self.session) if self.stop else self.service.observe(self.session)
            )
            self.signals.complete.emit(value)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class LocalFlashDialog(QDialog):
    """Review explicit image mappings and execute only after final user confirmation."""

    operation_finished = Signal(object)
    transition_finished = Signal(object)
    boot_finished = Signal(object)

    def __init__(
        self,
        service: LocalFlashService,
        devices: tuple[AndroidDevice, ...],
        parent: QWidget | None = None,
        *,
        discover: Callable[[], list[AndroidDevice]] | None = None,
        transition_service: LocalDeviceTransitionService | None = None,
        boot_service: LocalBootService | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.devices = devices
        self.plan: LocalFlashPlan | None = None
        self.result: LocalFlashResult | None = None
        self.execution_error = ""
        self.last_attempt_device: AndroidDevice | None = None
        self.last_flash_device: AndroidDevice | None = None
        self.worker: (
            LocalFlashWorker
            | LocalFlashDiscoveryWorker
            | LocalTransitionWorker
            | LocalBootWorker
            | None
        ) = None
        self.discover = discover
        self.transition_service = transition_service
        self.boot_service = boot_service
        self.transition_result: LocalTransitionResult | None = None
        self.transition_error = ""
        self.transition_attempt_device: AndroidDevice | None = None
        self.boot_session: LocalBootSession | None = None
        self.boot_report: LocalBootReport | None = None
        self.boot_device: AndroidDevice | None = None
        self.boot_error = ""
        self.monitoring = False
        self._boot_stop_requested = False
        self._close_after_boot = False
        self.boot_timer = QTimer(self)
        self.boot_timer.setSingleShot(True)
        self.boot_timer.setInterval(5000)
        self.boot_timer.timeout.connect(self._poll_boot)
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
            "Prepare the phone, review exact image writes, then check Android boot. "
            "Stock images can be used for a manual restore."
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

        lifecycle = QHBoxLayout()
        self.mode_target = QComboBox()
        self.mode_target.setAccessibleName("Requested phone mode")
        self.mode_target.addItem("Bootloader · physical images", LocalTransitionTarget.BOOTLOADER)
        self.mode_target.addItem("fastbootd · logical images", LocalTransitionTarget.FASTBOOTD)
        self.mode_target.addItem("Android · reboot and check", LocalTransitionTarget.ANDROID)
        self.mode_button = QPushButton("Change mode…")
        self.mode_button.clicked.connect(self._change_mode)
        self.boot_button = QPushButton("Check Android boot")
        self.boot_button.clicked.connect(self._check_boot)
        self.boot_button.setToolTip(
            "Read-only boot monitoring; does not reboot or write the phone."
        )
        lifecycle.addWidget(self.mode_target, 1)
        lifecycle.addWidget(self.mode_button)
        lifecycle.addWidget(self.boot_button)
        layout.addLayout(lifecycle)

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
            "Choose the intended phone and mode, then add the exact images you want to write."
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
            "Flashing risks data loss and boot failure. Keep your own backup and correct images. "
            "Write completion, measured boot, image readback and subsystem health are separate results."
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
        self._set_busy(False)

    def add_image(self, path: Path, partition: str = "") -> None:
        if self.worker is not None or self.monitoring:
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
        self.review_button.setEnabled(
            self.worker is None
            and not self.monitoring
            and bool(self.devices)
            and self.images.rowCount() > 0
        )
        if self.worker is None and not self.monitoring:
            self.review.clear()
            if self.images.rowCount():
                self.status.setText(
                    "Review these mappings to check the current phone and image bytes."
                )
        self._set_busy(self.worker is not None)

    def _inspect(self) -> None:
        if self.worker is not None or self.monitoring or self.target.currentIndex() < 0:
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
        if self.worker is not None or self.monitoring or self.discover is None:
            return
        self._invalidate()
        self.status.setText("Checking connected phones…")
        self.progress.setRange(0, 0)
        self._start(LocalFlashDiscoveryWorker(self.discover))

    def _selected_device(self) -> AndroidDevice | None:
        index = self.target.currentIndex()
        return self.devices[index] if 0 <= index < len(self.devices) else None

    def _adopt_device(self, observed: AndroidDevice) -> None:
        """Refresh only the observed identity; never substitute another connected phone."""
        index = next(
            (i for i, item in enumerate(self.devices) if item.serial == observed.serial), None
        )
        if index is None:
            return
        devices = list(self.devices)
        devices[index] = observed
        self.devices = tuple(devices)
        self.target.setItemText(
            index, f"{observed.display_name} · {observed.masked_serial()} · {observed.state.value}"
        )

    def _change_mode(self) -> None:
        device = self._selected_device()
        if (
            self.worker is not None
            or self.monitoring
            or device is None
            or self.transition_service is None
        ):
            return
        self._invalidate()
        self.progress.setRange(0, 0)
        self.status.setText("Checking the selected phone before preparing a mode change…")
        self._start(
            LocalTransitionWorker(
                self.transition_service,
                device,
                LocalTransitionTarget(self.mode_target.currentData()),
            )
        )

    def _confirm_transition(self, plan, device, target) -> None:
        question = QMessageBox(self)
        question.setIcon(QMessageBox.Icon.Warning)
        question.setTextFormat(Qt.TextFormat.PlainText)
        question.setWindowTitle("Confirm phone mode change")
        question.setText(f"Restart {plan.device_name} {plan.masked_serial} into {target.value}?")
        question.setInformativeText(
            "The phone will disconnect briefly. Save your work on it first. "
            "This action does not flash images, erase data or change the active slot. "
            "Android boot will be checked separately after reconnection."
        )
        question.setDetailedText(
            "\n".join((f"From: {plan.source_mode}", f"Plan: {plan.plan_digest}", *plan.warnings))
        )
        confirm = question.addButton("Restart phone", QMessageBox.ButtonRole.AcceptRole)
        cancel = question.addButton(QMessageBox.StandardButton.Cancel)
        question.setDefaultButton(cancel)
        question.exec()
        if question.clickedButton() is not confirm:
            self.status.setText("Mode change cancelled. No reboot command was sent.")
            return
        if (
            self.worker is not None
            or self.monitoring
            or self._selected_device() is not device
            or self.mode_target.currentData() != target
        ):
            self.status.setText(
                "The target or requested mode changed. Prepare the mode change again."
            )
            return
        self.transition_error = ""
        self.transition_result = None
        self.transition_attempt_device = device
        self.last_attempt_device = device
        self.boot_report = None
        self.boot_error = ""
        self.progress.setRange(0, 0)
        self.status.setText("Rechecking the exact phone, then waiting for its requested mode…")
        self._start(LocalTransitionWorker(self.transition_service, device, target, plan=plan))

    def _check_boot(self) -> None:
        device = self._selected_device()
        if device is not None and self.worker is None and not self.monitoring:
            self._start_boot(device)

    def _start_boot(self, device: AndroidDevice) -> None:
        if self.boot_service is None or self.worker is not None or self.monitoring:
            return
        self._invalidate()
        self.monitoring = True
        self._boot_stop_requested = False
        self._close_after_boot = False
        self.boot_session = None
        self.boot_report = None
        self.boot_error = ""
        # Bind only the operation performed on this phone, never another combo entry.
        linked = (
            self.result
            if (
                self.result is not None
                and self.result.state == "completed"
                and self.last_flash_device is not None
                and self.last_flash_device.serial == device.serial
            )
            else None
        )
        # Keep the reviewed pre-write aliases for receipt binding. A ROM may change
        # its product/region name; fresh boot observations still check its codename.
        baseline = self.last_flash_device if linked is not None else device
        self.boot_device = baseline
        self.status.setText("Watching this phone for Android boot and a measured stable interval…")
        self.progress.setRange(0, 0)
        self._start(LocalBootWorker(self.boot_service, baseline, flash_result=linked))

    def _poll_boot(self) -> None:
        if not self.monitoring or self.worker is not None or self.boot_session is None:
            return
        self._start(
            LocalBootWorker(
                self.boot_service,
                self.boot_device,
                session=self.boot_session,
                stop=self._boot_stop_requested,
            )
        )

    def _stop_boot(self, *, close_after: bool = False) -> None:
        self._close_after_boot = self._close_after_boot or close_after
        self.boot_timer.stop()
        self._boot_stop_requested = True
        self.cancel_button.setEnabled(False)
        self.status.setText("Stopping boot monitoring after the current read-only check…")
        if self.worker is None:
            self._poll_boot()

    def _complete_boot(self, report: LocalBootReport) -> None:
        if (
            report.latest_device is not None
            and self.boot_device is not None
            and report.latest_device.serial != self.boot_device.serial
        ):
            self.boot_error = "The boot check returned another phone's observations. No boot success was accepted."
            self.monitoring = False
            self.boot_timer.stop()
            self._failed(self.boot_error)
            return
        self.boot_report = report
        self.status.setText(report.summary)
        if report.latest_device is not None:
            self._adopt_device(report.latest_device)
        self.review.setPlainText(
            f"ANDROID BOOT CHECK  ·  {report.status}\n{report.summary}\n\n"
            f"Samples: {report.sample_count} · Elapsed: {report.elapsed_seconds:.0f} seconds\n"
            "This read-only observation is not image readback, a full subsystem test, "
            "or a public release certification.\n\n"
            f"Receipt: {report.receipt_path}"
        )
        if report.latest_device is not None:
            observed = report.latest_device
            self.review.appendPlainText(
                f"\nMEASURED PHONE\nProduct: {observed.product} · Device: {observed.codename}\n"
                f"Android: {observed.android_version or 'Not reported'} · Build: {observed.build_id or 'Not reported'}\n"
                f"Slot: {observed.slot_suffix or 'Not reported'} · Uptime: {observed.uptime_seconds} seconds\n"
                f"Build fingerprint: {observed.build_fingerprint or 'Not reported'}"
            )
        if not report.terminal:
            if self._boot_stop_requested:
                self._poll_boot()
            else:
                self.progress.setRange(0, 0)
                self.boot_timer.start()
                self._set_busy(True)
            return
        self.monitoring = False
        self.boot_timer.stop()
        self.progress.setRange(0, 100)
        stable = report.status == "stable" and report.boot_observed
        self.progress.setValue(100 if stable else 0)
        self.progress.setFormat("Observed boot window complete" if stable else "Boot check ended")
        if (
            stable
            and self.transition_attempt_device is not None
            and self.boot_device is not None
            and self.transition_attempt_device.serial == self.boot_device.serial
        ):
            self.transition_error = ""
        self.boot_finished.emit(report)
        self._set_busy(False)
        if report.status == "attention":
            self.recovery_requested = True
            self.accept()
        elif self._close_after_boot:
            super().done(QDialog.DialogCode.Rejected)

    def _start(self, worker) -> None:
        self.worker = worker
        self.progress.setFormat("%p%")
        self.progress.setAccessibleName(
            "Android boot observation"
            if isinstance(worker, LocalBootWorker)
            else "Phone mode observation"
            if isinstance(worker, LocalTransitionWorker)
            else "Partition image review and writes"
        )
        self._set_busy(
            True, writing=isinstance(worker, LocalFlashWorker) and worker.plan is not None
        )
        worker.signals.complete.connect(self._receive_complete)
        worker.signals.failed.connect(self._receive_failed)
        worker.signals.progress.connect(self._receive_progress)
        try:
            start_background(worker)
        except RuntimeError as exc:
            self._failed(str(exc))

    @Slot(object)
    def _receive_complete(self, value: object) -> None:
        if self.worker is not None and self.sender() is self.worker.signals:
            self._complete(value)

    @Slot(str)
    def _receive_failed(self, message: str) -> None:
        if self.worker is not None and self.sender() is self.worker.signals:
            self._failed(message)

    @Slot(int, int, str)
    def _receive_progress(self, done: int, total: int, message: str) -> None:
        if self.worker is not None and self.sender() is self.worker.signals:
            self._progress(done, total, message)

    def _set_busy(self, busy: bool, *, writing: bool = False) -> None:
        busy = busy or self.monitoring
        writing = writing or (
            isinstance(self.worker, LocalFlashWorker) and self.worker.plan is not None
        )
        for widget in (
            self.target,
            self.images,
            self.add_button,
            self.remove_button,
            self.close_button,
        ):
            widget.setEnabled(not busy)
        self.review_button.setEnabled(
            not busy and self._selected_device() is not None and self.images.rowCount() > 0
        )
        self.refresh_button.setEnabled(not busy and self.discover is not None)
        self.flash_button.setEnabled(not busy and self.plan is not None)
        self.mode_target.setEnabled(not busy and self.transition_service is not None)
        self.mode_button.setEnabled(
            not busy and self._selected_device() is not None and self.transition_service is not None
        )
        self.boot_button.setEnabled(
            not busy and self._selected_device() is not None and self.boot_service is not None
        )
        transitioning = (
            isinstance(self.worker, LocalTransitionWorker) and self.worker.plan is not None
        )
        cancellable = writing or transitioning or self.monitoring
        self.cancel_button.setText(
            "Stop boot check"
            if self.monitoring
            else "Stop waiting"
            if transitioning
            else "Stop after current write"
        )
        self.cancel_button.setVisible(busy and cancellable)
        self.cancel_button.setEnabled(
            busy and cancellable and not (self.monitoring and self._boot_stop_requested)
        )
        self.recovery_button.setEnabled(not busy)
        self.recovery_button.setVisible(
            not busy
            and bool(
                self.execution_error
                or self.transition_error
                or self.boot_error
                or self.boot_report
                or (self.result and self.result.phone_change_attempted)
            )
        )

    def _complete(self, value: object) -> None:
        finished = self.worker
        self.worker = None
        self.progress.setRange(0, 100)
        if isinstance(finished, LocalBootWorker):
            if isinstance(value, LocalBootReport):
                self.boot_session = finished.session
                self._complete_boot(value)
            else:
                self.worker = finished
                self._failed(
                    "The boot observer returned an unsupported result. No boot success was accepted."
                )
            return
        if isinstance(value, LocalTransitionPlan) and isinstance(finished, LocalTransitionWorker):
            self._set_busy(False)
            self._confirm_transition(value, finished.device, finished.target)
            return
        if isinstance(value, LocalTransitionResult):
            self.transition_result = value
            self.plan = None
            self.status.setText(value.summary)
            self.review.appendPlainText(
                f"\nMODE CHANGE  {value.summary}\nReceipt: {value.receipt_path}"
            )
            self.transition_finished.emit(value)
            if value.observed_device is not None:
                self._adopt_device(value.observed_device)
            if value.state != "completed" and value.phone_change_attempted:
                self.transition_error = value.summary
            if (
                (value.state == "completed" or value.command_completed)
                and value.state != "cancelled"
                and isinstance(finished, LocalTransitionWorker)
                and finished.target is LocalTransitionTarget.ANDROID
                and self.boot_service is not None
            ):
                self._start_boot(value.observed_device or finished.device)
                return
        elif isinstance(value, tuple) and all(isinstance(item, AndroidDevice) for item in value):
            selected = self._selected_device()
            self.devices = value
            self.target.blockSignals(True)
            self.target.clear()
            for device in value:
                self.target.addItem(
                    f"{device.display_name} · {device.masked_serial()} · {device.state.value}"
                )
            if selected is not None:
                self.target.setCurrentIndex(
                    next((i for i, item in enumerate(value) if item.serial == selected.serial), -1)
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
                self.progress.setFormat("Image writes completed · boot unchecked")
                self.mode_target.setCurrentIndex(
                    self.mode_target.findData(LocalTransitionTarget.ANDROID)
                )
                self.status.setText(
                    value.summary + " Next: choose Change mode to restart Android and check boot."
                )
            self.operation_finished.emit(value)
        else:
            self.worker = finished
            self._failed("The operation returned an unsupported result. Recheck the phone state.")
            return
        self._set_busy(False)

    def _failed(self, message: str) -> None:
        if isinstance(self.worker, LocalFlashWorker) and self.worker.plan is not None:
            self.result = None
            self.execution_error = message
            self.recovery_button.setVisible(True)
        elif isinstance(self.worker, LocalTransitionWorker) and self.worker.plan is not None:
            self.transition_error = message
        elif isinstance(self.worker, LocalBootWorker):
            self.boot_error = message
            self.monitoring = False
            self.boot_timer.stop()
        self.worker = None
        self.plan = None
        self.progress.setRange(0, 100)
        self.status.setText(message)
        self.review.appendPlainText(f"\nOperation stopped: {message}")
        self._set_busy(False)
        if self._close_after_boot:
            super().done(QDialog.DialogCode.Rejected)

    def _confirm_flash(self) -> None:
        plan = self.plan
        if plan is None or self.worker is not None or self.monitoring:
            return
        question = QMessageBox(self)
        question.setIcon(QMessageBox.Icon.Warning)
        question.setTextFormat(Qt.TextFormat.PlainText)
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
        self.last_flash_device = self.last_attempt_device
        self.boot_report = None
        self.boot_error = ""
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
        if self.monitoring:
            self._stop_boot()
        elif isinstance(self.worker, LocalTransitionWorker):
            self.worker.cancel_requested.set()
            self.cancel_button.setEnabled(False)
            self.status.setText(
                "Stop requested. A reboot already sent cannot be undone; recheck the phone afterward."
            )
        elif isinstance(self.worker, LocalFlashWorker):
            self.worker.cancel_requested.set()
            self.cancel_button.setEnabled(False)
            self.status.setText(
                "Stop requested. The current write will finish before the sequence stops."
            )

    def _open_recovery(self) -> None:
        if self.worker is not None or self.monitoring:
            return
        self.recovery_requested = True
        self.accept()

    def done(self, result: int) -> None:
        if self.monitoring:
            self._stop_boot(close_after=True)
        elif self.worker is None:
            self.boot_timer.stop()
            super().done(result)

    def reject(self) -> None:
        if self.monitoring:
            self._stop_boot(close_after=True)
        elif self.worker is None:
            self.boot_timer.stop()
            super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.monitoring:
            event.ignore()
            self._stop_boot(close_after=True)
        elif self.worker is not None:
            event.ignore()
        else:
            self.boot_timer.stop()
            super().closeEvent(event)
