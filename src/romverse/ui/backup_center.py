from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from romverse.backup.media import PhoneMediaBackupReceipt, PhoneMediaBackupService
from romverse.backup.plans import GuardianBackupPlanStore
from romverse.core.activity import ActivityStore, ActivityStoreError
from romverse.device.models import AndroidDevice, DeviceState
from romverse.rom.models import ProjectError, TimeMachineSnapshot
from romverse.rom.projects import RomProjectStore
from romverse.rom.recovery_evidence import RecoveryEvidenceService
from romverse.ui.background import (
    CoalescedProgress,
    ManagedRunnable,
    measured_percent,
    start_background,
)
from romverse.ui.phone_backup import PhoneMediaBackupDialog, PhoneMediaBackupWorker
from romverse.ui.process_progress import ProcessProgressBar


class TimeMachineSignals(QObject):
    complete = Signal(object)
    failed = Signal(str)
    progress = Signal(int)


class TimeMachineWorker(ManagedRunnable):
    def __init__(
        self,
        store: RomProjectStore,
        operation: str,
        project_id: str,
        snapshot: TimeMachineSnapshot,
    ) -> None:
        super().__init__()
        self.store = store
        self.operation = operation
        self.project_id = project_id
        self.snapshot = snapshot
        self.signals = TimeMachineSignals()

    @Slot()
    def execute(self) -> None:
        publish_progress = CoalescedProgress(self.signals.progress.emit)

        def progress(done: int, total: int) -> None:
            value = 100 if total <= 0 or done >= total else max(0, min(99, int(done * 100 / total)))
            publish_progress(value)

        try:
            if self.operation == "verify":
                publish_progress(0)
                result = self.store.verify_snapshot(self.snapshot, progress=progress)
                publish_progress(100)
            elif self.operation == "restore":
                self.store.restore_snapshot(
                    self.project_id,
                    self.snapshot.snapshot_id,
                    self.snapshot.sha256,
                )
                result = self.store.load_latest_restore_receipt(self.project_id)
                if result is None:
                    raise ProjectError("Time Machine restore receipt was not recorded")
            else:
                raise ProjectError("Unknown Time Machine operation")
            self.signals.complete.emit(result)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class RecoveryEvidenceWorker(ManagedRunnable):
    def __init__(
        self,
        service: RecoveryEvidenceService,
        operation: str,
        project_id: str,
        role: str = "",
        source: Path | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.operation = operation
        self.project_id = project_id
        self.role = role
        self.source = source
        self.signals = TimeMachineSignals()

    @Slot()
    def execute(self) -> None:
        publish_progress = CoalescedProgress(self.signals.progress.emit)

        def progress(done: int, total: int) -> None:
            value = measured_percent(done, total)
            if value is not None:
                publish_progress(value)

        try:
            if self.operation == "register" and self.source is not None:
                result = self.service.register(
                    self.project_id,
                    self.role,
                    self.source,
                    progress=progress,
                )
            elif self.operation == "verify":
                result = self.service.verify(self.project_id, progress=progress)
            else:
                raise ProjectError("Unknown recovery-evidence operation")
            self.signals.complete.emit(result)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class BackupCenter(QWidget):
    """Prepare a recovery-aware backup plan without running device-changing commands."""

    def __init__(
        self,
        workspace: Path,
        activity_store: ActivityStore | None = None,
        media_backup_service: PhoneMediaBackupService | None = None,
        default_backup_directory: Path | None = None,
    ) -> None:
        super().__init__()
        self.workspace = workspace
        self.activity_store = activity_store
        self.media_backup_service = media_backup_service
        self.default_backup_directory = default_backup_directory
        self.rom_store = RomProjectStore(workspace)
        self.recovery_evidence = RecoveryEvidenceService(self.rom_store)
        self.plan_store = GuardianBackupPlanStore(workspace)
        self.device: AndroidDevice | None = None
        self.projects = ()
        self.snapshots: tuple[TimeMachineSnapshot, ...] = ()
        self.worker: TimeMachineWorker | None = None
        self.evidence_worker: RecoveryEvidenceWorker | None = None
        self.media_backup_worker: PhoneMediaBackupWorker | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(12)
        eyebrow = QLabel("TIME MACHINE  •  GUARDIAN READINESS")
        eyebrow.setObjectName("Eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("Time Machine")
        title.setObjectName("Title")
        layout.addWidget(title)
        intro = QLabel(
            "Create a verified backup of user-accessible phone media to a local drive, prepare "
            "recovery evidence, and manage ROM Studio working-baseline snapshots. App-private "
            "data requires a separate Google, OEM, or app-specific backup; ROMVERSE never claims "
            "coverage it cannot verify."
        )
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.status = QLabel("Waiting for an authorized device scan.")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        columns = QHBoxLayout()
        columns.setSpacing(14)
        readiness = QFrame()
        readiness.setObjectName("Card")
        readiness_layout = QVBoxLayout(readiness)
        readiness_layout.setContentsMargins(18, 16, 18, 16)
        readiness_title = QLabel("DEVICE RECOVERY READINESS")
        readiness_title.setObjectName("SectionTitle")
        readiness_layout.addWidget(readiness_title)
        self.checks = QWidget()
        self.checks_layout = QVBoxLayout(self.checks)
        self.checks_layout.setContentsMargins(0, 0, 0, 0)
        readiness_layout.addWidget(self.checks)
        self.plan_button = QPushButton("Create Guardian backup plan")
        self.plan_button.setObjectName("Primary")
        self.plan_button.setToolTip(
            "Record current device identity and recovery-readiness evidence. No phone data is copied."
        )
        self.plan_button.setEnabled(False)
        self.plan_button.clicked.connect(self._create_plan)
        readiness_layout.addWidget(self.plan_button)
        self.review_button = QPushButton("Review latest plan")
        self.review_button.setToolTip(
            "Review the most recently recorded Guardian readiness evidence."
        )
        self.review_button.setEnabled(False)
        self.review_button.clicked.connect(self._review_latest_plan)
        readiness_layout.addWidget(self.review_button)
        phone_backup_title = QLabel("PHONE BACKUP TO LOCAL DRIVE")
        phone_backup_title.setObjectName("SectionTitle")
        readiness_layout.addWidget(phone_backup_title)
        phone_backup_copy = QLabel(
            "Copy selected Camera, Pictures, Videos, Downloads, and Documents folders into a "
            "verified ZIP on a drive you choose. ROMVERSE records per-file hashes and never "
            "writes to the phone."
        )
        phone_backup_copy.setObjectName("Muted")
        phone_backup_copy.setWordWrap(True)
        readiness_layout.addWidget(phone_backup_copy)
        self.phone_backup_button = QPushButton("Back up phone to local drive…")
        self.phone_backup_button.setObjectName("Primary")
        self.phone_backup_button.setToolTip(
            "Choose a destination and explicit shared-storage categories, review the exact "
            "read-only plan, then create and verify a local ZIP archive."
        )
        self.phone_backup_button.setEnabled(False)
        self.phone_backup_button.clicked.connect(self._prepare_phone_backup)
        readiness_layout.addWidget(self.phone_backup_button)
        self.phone_backup_progress = ProcessProgressBar()
        readiness_layout.addWidget(self.phone_backup_progress)
        self.phone_backup_result = QLabel(
            "Connect and authorize a phone to enable verified local backup."
            if self.media_backup_service is not None
            else "Install or verify Android Platform Tools in Forge Arsenal to enable local backup."
        )
        self.phone_backup_result.setObjectName("Muted")
        self.phone_backup_result.setWordWrap(True)
        readiness_layout.addWidget(self.phone_backup_result)
        self.result = QLabel("")
        self.result.setObjectName("Good")
        self.result.setWordWrap(True)
        readiness_layout.addWidget(self.result)
        readiness_layout.addStretch()
        columns.addWidget(readiness, 1)

        recovery = QFrame()
        recovery.setObjectName("Card")
        recovery_layout = QVBoxLayout(recovery)
        recovery_layout.setContentsMargins(18, 16, 18, 16)
        recovery_title = QLabel("LOCAL ROM RECOVERY")
        recovery_title.setObjectName("SectionTitle")
        recovery_copy = QLabel(
            "Verify or restore the isolated working baseline used by ROM Studio. Before restore, "
            "Time Machine preserves the current baseline, validates the selected snapshot, performs "
            "an atomic replacement, verifies the result, and writes a receipt."
        )
        recovery_copy.setObjectName("Muted")
        recovery_copy.setWordWrap(True)
        recovery_layout.addWidget(recovery_title)
        recovery_layout.addWidget(recovery_copy)
        self.project_selector = QComboBox()
        self.project_selector.setToolTip("Choose a ROM Studio project with local snapshots.")
        self.project_selector.currentIndexChanged.connect(self._project_selected)
        recovery_layout.addWidget(self.project_selector)
        self.snapshot_list = QListWidget()
        self.snapshot_list.setMinimumHeight(135)
        self.snapshot_list.currentItemChanged.connect(self._snapshot_selected)
        recovery_layout.addWidget(self.snapshot_list)
        self.snapshot_detail = QLabel("No ROM Studio snapshots found.")
        self.snapshot_detail.setObjectName("Muted")
        self.snapshot_detail.setWordWrap(True)
        self.snapshot_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        recovery_layout.addWidget(self.snapshot_detail)
        local_actions = QHBoxLayout()
        self.verify_snapshot_button = QPushButton("Verify snapshot")
        self.verify_snapshot_button.setToolTip(
            "Recompute SHA-256 for the selected local Time Machine snapshot."
        )
        self.verify_snapshot_button.clicked.connect(lambda: self._start_time_machine("verify"))
        self.restore_snapshot_button = QPushButton("Restore working baseline")
        self.restore_snapshot_button.setObjectName("Primary")
        self.restore_snapshot_button.setToolTip(
            "Restore only the selected project's isolated local working baseline after typed approval."
        )
        self.restore_snapshot_button.clicked.connect(self._approve_restore)
        local_actions.addWidget(self.verify_snapshot_button)
        local_actions.addWidget(self.restore_snapshot_button)
        recovery_layout.addLayout(local_actions)
        self.local_progress = ProcessProgressBar()
        recovery_layout.addWidget(self.local_progress)
        self.local_result = QLabel("")
        self.local_result.setObjectName("Muted")
        self.local_result.setWordWrap(True)
        recovery_layout.addWidget(self.local_result)
        evidence_title = QLabel("EXTERNAL SAFETY EVIDENCE")
        evidence_title.setObjectName("SectionTitle")
        recovery_layout.addWidget(evidence_title)
        evidence_copy = QLabel(
            "Register an independently stored phone backup and exact stock-recovery package. "
            "ROMVERSE hashes them in place, stores private locations locally, and detects later "
            "changes. Files are never copied into the project or sent to the phone."
        )
        evidence_copy.setObjectName("Muted")
        evidence_copy.setWordWrap(True)
        recovery_layout.addWidget(evidence_copy)
        evidence_actions = QHBoxLayout()
        self.backup_evidence_button = QPushButton("Register external backup")
        self.backup_evidence_button.setToolTip(
            "Select an independently stored backup archive. ROMVERSE reads and hashes it without copying it."
        )
        self.backup_evidence_button.clicked.connect(
            lambda: self._choose_recovery_evidence("external_backup")
        )
        self.stock_evidence_button = QPushButton("Register stock recovery")
        self.stock_evidence_button.setToolTip(
            "Select an externally stored byte-identical copy of the project's protected stock "
            "firmware. Its SHA-256 must match exactly."
        )
        self.stock_evidence_button.clicked.connect(
            lambda: self._choose_recovery_evidence("stock_recovery")
        )
        self.verify_evidence_button = QPushButton("Reverify both")
        self.verify_evidence_button.clicked.connect(self._verify_recovery_evidence)
        evidence_actions.addWidget(self.backup_evidence_button)
        evidence_actions.addWidget(self.stock_evidence_button)
        evidence_actions.addWidget(self.verify_evidence_button)
        recovery_layout.addLayout(evidence_actions)
        self.evidence_result = QLabel("Select a project to review external safety evidence.")
        self.evidence_result.setObjectName("Muted")
        self.evidence_result.setWordWrap(True)
        recovery_layout.addWidget(self.evidence_result)
        columns.addWidget(recovery, 1)
        layout.addLayout(columns, 1)

        boundary = QLabel(
            "Guardian boundary  •  Time Machine can restore local ROM workspace baselines only. "
            "It never reads, writes, flashes, wipes, or restores phone partitions."
        )
        boundary.setObjectName("Warning")
        boundary.setWordWrap(True)
        layout.addWidget(boundary)
        self._load_latest_plan()
        self.refresh_local_snapshots()

    def set_media_backup_service(self, service: PhoneMediaBackupService | None) -> None:
        self.media_backup_service = service
        ready = service is not None and self.device is not None and self.media_backup_worker is None
        self.phone_backup_button.setEnabled(ready)
        if service is not None:
            self.phone_backup_result.setText(
                "Verified Platform Tools are ready. Connect a phone to use local backup."
                if self.device is None
                else "Ready. Choose a local destination and the categories you want ROMVERSE to copy."
            )
        else:
            self.phone_backup_result.setText(
                "Install or verify Android Platform Tools in Forge Arsenal to enable local backup."
            )

    def set_devices(self, devices: list[AndroidDevice]) -> None:
        self.device = next((item for item in devices if item.state is DeviceState.DEVICE), None)
        self._clear_checks()
        if self.device is None:
            self.plan_button.setEnabled(False)
            self.phone_backup_button.setEnabled(False)
            self.status.setText(
                "No authorized device. Connect and authorize a phone, then scan again."
            )
            return
        device = self.device
        self.status.setText(f"Target: {device.display_name}  •  {device.masked_serial()}")
        battery_ok = device.battery_percent is not None and device.battery_percent >= 30
        storage_ok = device.storage.percent_used is not None and device.storage.percent_used < 90
        boot_ok = (
            device.bootloader_locked is True
            and str(device.verified_boot).strip().casefold() == "green"
        )
        checks = (
            ("Authorized ADB connection", True),
            ("Device identity and build evidence available", bool(device.build_id)),
            (
                "Battery at least 30% (observed)"
                if device.battery_percent is not None
                else "Battery level observed",
                battery_ok,
            ),
            (
                "Storage usage below 90% (observed)"
                if device.storage.percent_used is not None
                else "Storage capacity observed",
                storage_ok,
            ),
            (
                "Bootloader locked and Verified Boot green"
                if device.bootloader_locked is not None
                else "Bootloader / Verified Boot evidence observed",
                boot_ok,
            ),
        )
        for label, passed in checks:
            item = QLabel(("✓ " if passed else "• ") + label)
            item.setObjectName("Good" if passed else "Warning")
            self.checks_layout.addWidget(item)
        self.plan_button.setEnabled(True)
        self.phone_backup_button.setEnabled(
            self.media_backup_service is not None and self.media_backup_worker is None
        )
        if self.media_backup_service is not None:
            self.phone_backup_result.setText(
                "Ready. Choose a local destination and the categories you want ROMVERSE to copy."
            )

    def _prepare_phone_backup(self) -> None:
        device = self.device
        service = self.media_backup_service
        if device is None or service is None or self.media_backup_worker is not None:
            return
        selection = PhoneMediaBackupDialog(
            device.display_name,
            self,
            self.default_backup_directory,
        ).values()
        if selection is None:
            return
        destination, scopes = selection
        try:
            plan = service.prepare(device, destination, scopes)
        except Exception as exc:
            QMessageBox.warning(self, "Local backup could not start", str(exc))
            return

        scope_names = ", ".join(scope.value for scope in plan.scopes)
        answer = QMessageBox.question(
            self,
            "Review read-only local backup",
            f"Phone: {plan.device_name}\n"
            f"Destination: {plan.destination}\n"
            f"Archive: {Path(plan.archive_path).name}\n"
            f"Includes: {scope_names}\n\n"
            "ROMVERSE will read only these shared-storage folders, create a verified ZIP, "
            "and leave the phone and bootloader unchanged. App-private data, contacts, messages, "
            "credentials, eSIMs, and secure folders are not included.\n\n"
            "Approve this exact read-only backup plan?",
        )
        if answer is not QMessageBox.StandardButton.Yes:
            return
        try:
            service.approve(plan)
        except Exception as exc:
            QMessageBox.warning(self, "Guardian stopped the backup", str(exc))
            return
        project_id = str(self.project_selector.currentData() or "")
        self.media_backup_worker = PhoneMediaBackupWorker(
            service,
            plan,
            self.recovery_evidence if project_id else None,
            project_id,
        )
        self.media_backup_worker.signals.complete.connect(self._phone_backup_complete)
        self.media_backup_worker.signals.failed.connect(self._phone_backup_failed)
        self.media_backup_worker.signals.progress.connect(self.phone_backup_progress.report)
        self.phone_backup_progress.begin()
        self.phone_backup_result.setObjectName("Muted")
        self.phone_backup_result.setText(
            "Copying selected shared-storage folders, building the archive, and verifying hashes…"
        )
        self._repolish(self.phone_backup_result)
        self.phone_backup_button.setEnabled(False)
        self.plan_button.setEnabled(False)
        self._set_local_controls(False)
        self._set_evidence_controls(False)
        start_background(self.media_backup_worker)

    def set_default_backup_directory(self, path: Path | None) -> None:
        """Update the safe preselected location without starting a backup."""

        self.default_backup_directory = path

    @Slot(object)
    def _phone_backup_complete(self, result: object) -> None:
        self.media_backup_worker = None
        self.phone_backup_progress.finish()
        if not isinstance(result, PhoneMediaBackupReceipt):
            self._phone_backup_failed("The backup worker returned no verifiable receipt")
            return
        self.phone_backup_result.setObjectName("Good")
        self.phone_backup_result.setText(
            f"Verified local backup complete  •  {result.archive_name}  •  "
            f"{result.file_count} file(s)  •  SHA-256 {result.archive_sha256[:16]}…  •  "
            "phone changed: NO"
        )
        self._repolish(self.phone_backup_result)
        project_id = str(self.project_selector.currentData() or "")
        if project_id:
            self._refresh_recovery_evidence(project_id)
        self._restore_controls_after_phone_backup()
        self._record_activity(
            "Verified local phone backup created",
            f"{result.archive_name} • {result.file_count} file(s) • phone unchanged",
            "success",
        )
        QMessageBox.information(
            self,
            "Local backup verified",
            "ROMVERSE created and verified the local media archive. Keep the drive available "
            "through the final Guardian handoff, and separately verify your cloud/OEM backup "
            "for app-private data.",
        )

    @Slot(str)
    def _phone_backup_failed(self, message: str) -> None:
        self.media_backup_worker = None
        self.phone_backup_progress.stop()
        self.phone_backup_result.setObjectName("Danger")
        self.phone_backup_result.setText(
            f"Local phone backup stopped safely: {message}. No phone write was attempted."
        )
        self._repolish(self.phone_backup_result)
        self._restore_controls_after_phone_backup()

    def _restore_controls_after_phone_backup(self) -> None:
        self.plan_button.setEnabled(self.device is not None)
        self.phone_backup_button.setEnabled(
            self.device is not None and self.media_backup_service is not None
        )
        self._set_local_controls(self.snapshot_list.currentItem() is not None)
        self._set_evidence_controls(True)

    def _create_plan(self) -> None:
        if self.device is None:
            return
        try:
            record = self.plan_store.create(self.device)
        except OSError as exc:
            self.result.setObjectName("Danger")
            self.result.setText(f"Recovery-readiness plan was not saved: {exc}")
            self._repolish(self.result)
            return
        self.review_button.setEnabled(True)
        history_count = self.plan_store.history_count()
        self.result.setObjectName("Good")
        self.result.setText(
            f"Recovery-readiness plan recorded: {record.latest_path.name}  •  "
            f"{history_count} plan(s) saved  •  SHA-256 {record.plan_digest[:16]}…  •  "
            "no phone data copied."
        )
        self._repolish(self.result)
        self._record_activity(
            "Guardian recovery plan recorded",
            "Device readiness evidence was saved locally; no phone data was copied.",
            "information",
        )
        QMessageBox.information(
            self, "Backup plan ready", "Guardian readiness was recorded. No phone data was copied."
        )

    def _load_latest_plan(self) -> None:
        loaded = self.plan_store.load_latest()
        if not loaded.valid or loaded.data is None:
            if self.plan_store.latest_path.exists():
                self.result.setObjectName("Danger")
                self.result.setText(f"Latest recovery-readiness plan rejected: {loaded.reason}")
                self._repolish(self.result)
            return
        data = loaded.data
        self.result.setObjectName("Good" if loaded.integrity_verified else "Warning")
        self.result.setText(
            f"Latest plan: {data.get('status', 'unknown')}  •  "
            f"{self.plan_store.history_count()} plan(s) saved  •  "
            f"{'integrity verified' if loaded.integrity_verified else 'legacy / unverified'}  •  "
            "execution locked"
        )
        self._repolish(self.result)
        self.review_button.setEnabled(True)

    def refresh_local_snapshots(self, select_project_id: str = "") -> None:
        current_id = select_project_id or str(self.project_selector.currentData() or "")
        self.projects = self.rom_store.list_projects()
        self.project_selector.blockSignals(True)
        self.project_selector.clear()
        selected_index = -1
        for index, project in enumerate(self.projects):
            count = len(self.rom_store.list_snapshots(project.project_id))
            self.project_selector.addItem(
                f"{project.name}  •  {count} snapshot(s)", project.project_id
            )
            if project.project_id == current_id:
                selected_index = index
        self.project_selector.blockSignals(False)
        if self.projects:
            self.project_selector.setCurrentIndex(selected_index if selected_index >= 0 else 0)
            self._project_selected(self.project_selector.currentIndex())
        else:
            self.snapshots = ()
            self.snapshot_list.clear()
            self.snapshot_detail.setText(
                "No ROM Studio projects yet. Create a project and working copy, then take a Time Machine snapshot."
            )
            self._set_local_controls(False)
            self._set_evidence_controls(False)

    def _project_selected(self, index: int) -> None:
        if not 0 <= index < len(self.projects):
            return
        project = self.projects[index]
        self.snapshots = self.rom_store.list_snapshots(project.project_id)
        self.snapshot_list.clear()
        for snapshot in self.snapshots:
            state = "CURRENT • READY" if snapshot.schema_version == 2 else "LEGACY • VERIFY"
            item = QListWidgetItem(
                f"{snapshot.snapshot_id}  •  {state}\n"
                f"{_human_bytes(snapshot.size_bytes)}  •  {snapshot.sha256[:16]}…"
            )
            item.setData(Qt.ItemDataRole.UserRole, snapshot.snapshot_id)
            self.snapshot_list.addItem(item)
        if self.snapshots:
            self.snapshot_list.setCurrentRow(0)
        else:
            self.snapshot_detail.setText(
                "This project has no baseline snapshots. Open ROM Studio and choose Time Machine snapshot."
            )
            self._set_local_controls(False)
        receipt = self.rom_store.load_latest_restore_receipt(project.project_id)
        if receipt is not None:
            self.local_result.setText(
                f"Latest verified restore  •  {receipt.get('created_at')}  •  "
                f"snapshot {receipt.get('snapshot_id')}  •  device modified: no"
            )
        self._refresh_recovery_evidence(project.project_id)
        self._set_evidence_controls(self.evidence_worker is None)

    def _snapshot_selected(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            self._set_local_controls(False)
            return
        snapshot_id = str(current.data(Qt.ItemDataRole.UserRole))
        snapshot = next((item for item in self.snapshots if item.snapshot_id == snapshot_id), None)
        if snapshot is None:
            self._set_local_controls(False)
            return
        self.snapshot_detail.setText(
            f"Snapshot  •  {snapshot.snapshot_id}\n"
            f"Evidence  •  {'schema two / current' if snapshot.schema_version == 2 else 'legacy / full verification required'}\n"
            f"Created  •  {snapshot.created_at}\n"
            f"Size  •  {_human_bytes(snapshot.size_bytes)}\n"
            f"SHA-256  •  {snapshot.sha256}\n"
            + (
                "Ready for an approval-bound local restore; bytes are rehashed in the background before replacement."
                if snapshot.schema_version == 2
                else "Choose Verify snapshot first. ROMVERSE will hash it in the background and upgrade genuine evidence."
            )
        )
        self._set_local_controls(self.worker is None and self.evidence_worker is None)

    def _selected_local_snapshot(self) -> tuple[str, TimeMachineSnapshot] | None:
        project_id = str(self.project_selector.currentData() or "")
        item = self.snapshot_list.currentItem()
        if not project_id or item is None:
            return None
        snapshot_id = str(item.data(Qt.ItemDataRole.UserRole))
        snapshot = next(
            (entry for entry in self.snapshots if entry.snapshot_id == snapshot_id), None
        )
        return (project_id, snapshot) if snapshot is not None else None

    def _approve_restore(self) -> None:
        selected = self._selected_local_snapshot()
        if selected is None:
            return
        _project_id, snapshot = selected
        if snapshot.schema_version != 2:
            QMessageBox.information(
                self,
                "Verify this legacy snapshot first",
                "The snapshot is preserved, but it cannot authorize a restore until ROMVERSE fully hashes it and saves current schema-two evidence. Choose Verify snapshot, then review the result.",
            )
            return
        phrase = f"RESTORE {snapshot.sha256[:8].upper()}"
        entered, accepted = QInputDialog.getText(
            self,
            "Approve local baseline restore",
            "Time Machine will preserve the current local baseline, restore the selected "
            "snapshot atomically, verify SHA-256, and write a receipt. The phone is not touched.\n\n"
            f"Type {phrase} to continue:",
        )
        if not accepted:
            return
        if entered.strip() != phrase:
            QMessageBox.warning(
                self,
                "Restore not approved",
                "The approval phrase did not match. No local files were changed.",
            )
            return
        self._start_time_machine("restore")

    def _start_time_machine(self, operation: str) -> None:
        selected = self._selected_local_snapshot()
        if selected is None or self.worker is not None or self.evidence_worker is not None:
            return
        project_id, snapshot = selected
        self.worker = TimeMachineWorker(self.rom_store, operation, project_id, snapshot)
        self.local_progress.begin(determinate=operation == "verify")
        self.local_result.setObjectName("Muted")
        self.local_result.setText(
            "Verifying snapshot integrity…"
            if operation == "verify"
            else "Preserving current baseline, restoring atomically, and verifying…"
        )
        self._set_local_controls(False)
        self._set_evidence_controls(False)
        self.worker.signals.complete.connect(self._time_machine_complete)
        self.worker.signals.failed.connect(self._time_machine_failed)
        self.worker.signals.progress.connect(self.local_progress.report)
        start_background(self.worker)

    @Slot(object)
    def _time_machine_complete(self, result: object) -> None:
        operation = self.worker.operation if self.worker is not None else ""
        project_id = self.worker.project_id if self.worker is not None else ""
        self.worker = None
        self.local_progress.finish()
        self.local_result.setObjectName("Good")
        if operation == "verify":
            valid = bool(getattr(result, "valid", False))
            self.local_result.setText(
                "Snapshot integrity verified."
                if valid
                else f"Snapshot verification failed: {getattr(result, 'status', 'unknown error')}"
            )
            if not valid:
                self.local_result.setObjectName("Danger")
            self._record_activity(
                "Time Machine snapshot verified" if valid else "Snapshot verification failed",
                "Local ROM baseline integrity matched its recorded SHA-256."
                if valid
                else "The local snapshot did not match its recorded integrity evidence.",
                "success" if valid else "attention",
            )
        elif isinstance(result, dict):
            self.local_result.setText(
                "Local working baseline restored and verified  •  "
                f"receipt {str(result.get('receipt_id', ''))[:12]}…  •  "
                f"safety snapshot {result.get('pre_restore_snapshot_id')}  •  phone untouched"
            )
            self._record_activity(
                "Local ROM baseline restored",
                "Atomic restore verified • pre-restore safety snapshot preserved • phone untouched",
                "success",
            )
        self._repolish(self.local_result)
        self.refresh_local_snapshots(project_id)

    @Slot(str)
    def _time_machine_failed(self, message: str) -> None:
        operation = self.worker.operation if self.worker is not None else "operation"
        self.worker = None
        self.local_progress.stop()
        self.local_result.setObjectName("Danger")
        self.local_result.setText(f"Time Machine stopped safely: {message}")
        self._record_activity(
            "Time Machine stopped safely",
            f"{operation.replace('-', ' ').title()} did not complete; no phone operation was attempted.",
            "attention",
        )
        self._repolish(self.local_result)
        self._set_local_controls(self.snapshot_list.currentItem() is not None)
        self._set_evidence_controls(True)

    def _set_local_controls(self, enabled: bool) -> None:
        self.verify_snapshot_button.setEnabled(enabled)
        selected = self._selected_local_snapshot() if enabled else None
        self.restore_snapshot_button.setEnabled(
            bool(selected is not None and selected[1].schema_version == 2)
        )

    def _set_evidence_controls(self, enabled: bool) -> None:
        self.backup_evidence_button.setEnabled(enabled)
        self.stock_evidence_button.setEnabled(enabled)
        project_id = str(self.project_selector.currentData() or "")
        has_evidence = False
        if project_id:
            assessment = self.recovery_evidence.assess(project_id)
            has_evidence = assessment.external_backup_ready or assessment.stock_recovery_ready
        self.verify_evidence_button.setEnabled(enabled and has_evidence)

    def _choose_recovery_evidence(self, role: str) -> None:
        project_id = str(self.project_selector.currentData() or "")
        if not project_id or self.evidence_worker is not None or self.worker is not None:
            return
        label = "external phone backup" if role == "external_backup" else "stock recovery package"
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            f"Select {label}",
            str(Path.home()),
            "All files (*)",
        )
        if selected:
            self._start_recovery_evidence(
                "register",
                project_id,
                role,
                Path(selected),
            )

    def _verify_recovery_evidence(self) -> None:
        project_id = str(self.project_selector.currentData() or "")
        if not project_id or self.evidence_worker is not None or self.worker is not None:
            return
        self._start_recovery_evidence("verify", project_id)

    def _start_recovery_evidence(
        self,
        operation: str,
        project_id: str,
        role: str = "",
        source: Path | None = None,
    ) -> None:
        self.evidence_worker = RecoveryEvidenceWorker(
            self.recovery_evidence,
            operation,
            project_id,
            role,
            source,
        )
        self.evidence_worker.signals.complete.connect(self._recovery_evidence_complete)
        self.evidence_worker.signals.failed.connect(self._recovery_evidence_failed)
        self.evidence_worker.signals.progress.connect(self.local_progress.report)
        self.local_progress.begin(determinate=True)
        self.evidence_result.setObjectName("Muted")
        self.evidence_result.setText(
            "Hashing the selected external file, please wait …"
            if operation == "register"
            else "Recomputing recovery-evidence hashes, please wait …"
        )
        self._set_local_controls(False)
        self._set_evidence_controls(False)
        start_background(self.evidence_worker)

    @Slot(object)
    def _recovery_evidence_complete(self, _result: object) -> None:
        project_id = self.evidence_worker.project_id if self.evidence_worker is not None else ""
        self.evidence_worker = None
        self.local_progress.finish()
        self._refresh_recovery_evidence(project_id)
        self._set_local_controls(self.snapshot_list.currentItem() is not None)
        self._set_evidence_controls(True)
        self._record_activity(
            "Recovery evidence verified",
            "External backup/recovery hashes were recorded locally; no file was copied and the phone was untouched.",
            "success",
        )

    @Slot(str)
    def _recovery_evidence_failed(self, message: str) -> None:
        self.evidence_worker = None
        self.local_progress.stop()
        self.evidence_result.setObjectName("Danger")
        self.evidence_result.setText(f"Recovery evidence stopped safely: {message}")
        self._repolish(self.evidence_result)
        self._set_local_controls(self.snapshot_list.currentItem() is not None)
        self._set_evidence_controls(True)

    def _refresh_recovery_evidence(self, project_id: str) -> None:
        if not project_id:
            self.evidence_result.setText("Select a project to review external safety evidence.")
            return
        assessment = self.recovery_evidence.assess(project_id)
        self.evidence_result.setObjectName("Good" if assessment.ready else "Warning")
        self.evidence_result.setText("\n".join(assessment.evidence))
        self._repolish(self.evidence_result)

    def _record_activity(self, title: str, detail: str, outcome: str) -> None:
        if self.activity_store is None:
            return
        with suppress(ActivityStoreError):
            self.activity_store.record(
                "recovery",
                title,
                detail,
                outcome=outcome,
                source="Time Machine",
            )

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _review_latest_plan(self) -> None:
        loaded = self.plan_store.load_latest()
        if loaded.valid and loaded.data is not None:
            data = loaded.data
            readiness = data.get("readiness", {})
            lines = [
                f"Device: {data.get('device_name', 'Unknown')}",
                f"Created: {data.get('created_at', 'Unknown')}",
                f"ADB authorized: {'yes' if readiness.get('adb_authorized') else 'no'}",
                f"Battery: {readiness.get('battery_percent', 'unknown')}%",
                f"Storage used: {readiness.get('storage_percent_used', 'unknown')}%",
                f"Bootloader locked: {readiness.get('bootloader_locked', 'unknown')}",
                f"Verified Boot: {readiness.get('verified_boot', 'unknown')}",
                f"Integrity: {'verified' if loaded.integrity_verified else 'legacy / unverified'}",
                "\nExecution remains locked; no phone data was copied.",
            ]
            QMessageBox.information(self, "Latest Guardian backup plan", "\n".join(lines))
        else:
            self.review_button.setEnabled(False)

    def _clear_checks(self) -> None:
        while self.checks_layout.count():
            item = self.checks_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()


def _human_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"
