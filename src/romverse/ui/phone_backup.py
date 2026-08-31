from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from romverse.backup.media import (
    PhoneMediaBackupPlan,
    PhoneMediaBackupService,
    PhoneMediaScope,
)
from romverse.rom.recovery_evidence import RecoveryEvidenceService
from romverse.ui.background import CoalescedProgress, ManagedRunnable


class PhoneMediaBackupDialog(QDialog):
    """Choose an explicit local destination and honest shared-storage coverage."""

    def __init__(
        self,
        device_name: str,
        parent: QWidget | None = None,
        default_destination: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Guardian • back up phone to local drive")
        self.setMinimumWidth(720)
        layout = QVBoxLayout(self)
        title = QLabel(f"Create a verified PC media backup for {device_name}")
        title.setObjectName("GateTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        copy = QLabel(
            "Choose an internal drive, secondary disk, or mounted external USB drive. ROMVERSE "
            "will copy only the shared-storage categories selected below, then create a ZIP with "
            "per-file SHA-256 evidence."
        )
        copy.setObjectName("GateCopy")
        copy.setWordWrap(True)
        layout.addWidget(copy)
        destination_row = QHBoxLayout()
        self.destination = QLineEdit()
        self.destination.setReadOnly(True)
        self.destination.setPlaceholderText("Choose a local drive or folder outside ROMVERSE")
        self.choose_destination = QPushButton("Choose local drive / folder…")
        self.choose_destination.clicked.connect(self._choose_destination)
        destination_row.addWidget(self.destination, 1)
        destination_row.addWidget(self.choose_destination)
        layout.addLayout(destination_row)
        self.free_space = QLabel("Free space will be checked before the backup begins.")
        self.free_space.setObjectName("MissionMuted")
        layout.addWidget(self.free_space)
        scope_title = QLabel("SHARED-STORAGE COVERAGE")
        scope_title.setObjectName("MissionEyebrow")
        layout.addWidget(scope_title)
        self.scope_checks: dict[PhoneMediaScope, QCheckBox] = {}
        defaults = {
            PhoneMediaScope.CAMERA,
            PhoneMediaScope.PICTURES,
            PhoneMediaScope.DOWNLOADS,
            PhoneMediaScope.DOCUMENTS,
        }
        for scope in PhoneMediaScope:
            check = QCheckBox(f"{scope.value}  •  {scope.remote_path}")
            check.setChecked(scope in defaults)
            check.toggled.connect(self._update_ready)
            self.scope_checks[scope] = check
            layout.addWidget(check)
        warning = QLabel(
            "Not included: app-private data, passwords, credentials, contacts, messages, eSIMs, "
            "authenticator secrets, secure folders, or cloud-only content. Review a cloud/OEM "
            "backup separately for those categories. This operation never changes the phone or bootloader."
        )
        warning.setObjectName("Warning")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self.start_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.start_button.setText("Review local backup plan")
        self.start_button.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if default_destination is not None and default_destination.is_dir():
            self._set_destination(default_destination)

    def _set_destination(self, path: Path) -> None:
        self.destination.setText(str(path))
        try:
            free = shutil.disk_usage(path).free
            self.free_space.setText(f"Available at destination  •  {_human_bytes(free)}")
        except OSError:
            self.free_space.setText("Destination free space could not be read.")
        self._update_ready()

    def _choose_destination(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose local backup drive or folder",
            self.destination.text().strip() or str(Path.home()),
        )
        if not folder:
            return
        path = Path(folder)
        self._set_destination(path)

    def _update_ready(self, _value: object = None) -> None:
        self.start_button.setEnabled(
            bool(self.destination.text().strip())
            and any(check.isChecked() for check in self.scope_checks.values())
        )

    def values(self) -> tuple[Path, tuple[PhoneMediaScope, ...]] | None:
        if self.exec() != QDialog.DialogCode.Accepted:
            return None
        scopes = tuple(scope for scope, check in self.scope_checks.items() if check.isChecked())
        return Path(self.destination.text()), scopes


class PhoneMediaBackupSignals(QObject):
    complete = Signal(object)
    failed = Signal(str)
    progress = Signal(int)


class PhoneMediaBackupWorker(ManagedRunnable):
    def __init__(
        self,
        service: PhoneMediaBackupService,
        plan: PhoneMediaBackupPlan,
        recovery: RecoveryEvidenceService | None = None,
        project_id: str = "",
    ) -> None:
        super().__init__()
        self.service = service
        self.plan = plan
        self.recovery = recovery
        self.project_id = project_id
        self.signals = PhoneMediaBackupSignals()

    @Slot()
    def execute(self) -> None:
        publish_progress = CoalescedProgress(self.signals.progress.emit)
        try:
            register_evidence = self.recovery is not None and bool(self.project_id)

            def backup_progress(done: int, total: int) -> None:
                if total <= 0:
                    return
                if done >= total:
                    if not register_evidence:
                        publish_progress(100)
                    return
                publish_progress(max(0, min(99, int(done * 100 / total))))

            receipt = self.service.execute(
                self.plan,
                backup_progress,
            )
            if register_evidence and self.recovery is not None:
                self.recovery.register_phone_media_backup(
                    self.project_id,
                    Path(self.plan.archive_path),
                    receipt,
                )
                publish_progress(100)
            self.signals.complete.emit(receipt)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


def _human_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"
