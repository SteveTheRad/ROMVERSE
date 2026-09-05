"""Choose explicit image mappings or a supported source-declared installation."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from romverse.rom.project_flash import ProjectFlashPreparation
from romverse.rom.source_installation import SourceInstallationRecipe
from romverse.ui.background import ManagedRunnable, start_background
from romverse.ui.formatters import human_bytes
from romverse.ui.local_flash import LocalFlashDialog


class PreparationSignals(QObject):
    complete = Signal(object)
    failed = Signal(str)


class ProjectPreparationWorker(ManagedRunnable):
    def __init__(
        self,
        service,
        project_id: str,
        candidate_choice: str,
        *,
        source_service=None,
        wipe=False,
        reboot=True,
    ) -> None:
        super().__init__()
        self.service = service
        self.project_id = project_id
        self.candidate_choice = candidate_choice
        self.source_service = source_service
        self.wipe = wipe
        self.reboot = reboot
        self.signals = PreparationSignals()

    def execute(self) -> None:
        try:
            if self.candidate_choice == "source-installation":
                if self.source_service is None:
                    raise ValueError("Source installation is unavailable in this context.")
                value = self.source_service.prepare(
                    self.project_id, wipe=self.wipe, reboot=self.reboot
                )
            else:
                value = self.service.prepare(
                    self.project_id, candidate_choice=self.candidate_choice
                )
            self.signals.complete.emit(value)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class ProjectPreparationDialog(QDialog):
    """Choose provenance explicitly, then hash in a managed background worker."""

    def __init__(self, service, project_id: str, parent=None, *, source_service=None) -> None:
        super().__init__(parent)
        self.service = service
        self.project_id = project_id
        self.source_service = source_service
        self.preparation: ProjectFlashPreparation | SourceInstallationRecipe | None = None
        self.worker: ProjectPreparationWorker | None = None
        self.monitoring = False
        self.setWindowTitle("ROMVERSE · Prepare installation")
        self.resize(740, 430)
        self.setMinimumWidth(520)
        if self.screen() is not None:
            available = self.screen().availableGeometry()
            self.setMinimumWidth(min(520, available.width() - 40))
            self.resize(min(740, available.width() - 40), min(430, available.height() - 80))
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        eyebrow = QLabel("GUIDED INSTALLATION  •  LOCAL IMAGES")
        eyebrow.setObjectName("Eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("Choose your installation route")
        title.setWordWrap(True)
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        introduction = QLabel(
            "ROMVERSE will verify the saved project evidence and image hashes. "
            "Your rebuilt candidate and the untouched original are separate choices; "
            "one is never silently substituted for the other."
            " A supported package procedure is a separate option for the protected source."
        )
        introduction.setWordWrap(True)
        layout.addWidget(introduction)
        self.choice = QComboBox()
        self.choice.setAccessibleName("Project image source")
        self.choice.addItem("My rebuilt candidate · saved successful build", "built")
        self.choice.addItem("Protected original · verified extracted images", "protected")
        if source_service is not None:
            self.choice.addItem(
                "Follow the package's supported installation procedure", "source-installation"
            )
        layout.addWidget(self.choice)
        self.source_controls = QWidget()
        options = QVBoxLayout(self.source_controls)
        options.setContentsMargins(0, 0, 0, 0)
        self.wipe = QCheckBox("Clean installation · erase all phone user data")
        self.wipe.setAccessibleName("Explicitly select data-erasing clean installation")
        self.reboot = QCheckBox("Restart Android after installation and check boot")
        self.reboot.setChecked(True)
        options.addWidget(self.wipe)
        options.addWidget(self.reboot)
        layout.addWidget(self.source_controls)
        limits = QLabel(
            "This prepares a manually mapped image operation, not an automatic full-ROM "
            "upgrade. You must supply the correct partitions, slots and write order. "
            "No Device Atlas certification is required for this local route. "
            "Preparing images does not reboot or write your phone."
        )
        self.limits = limits
        self.manual_limits = limits.text()
        limits.setWordWrap(True)
        limits.setObjectName("Warning")
        layout.addWidget(limits)
        self.choice.currentIndexChanged.connect(self._source_mode_changed)
        self._source_mode_changed()
        self.status = QLabel("Choose a source, then verify its images.")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        layout.addStretch(1)
        actions = QHBoxLayout()
        self.close_button = QPushButton("Cancel")
        self.close_button.clicked.connect(self.reject)
        self.prepare_button = QPushButton("Verify and continue")
        self.prepare_button.setObjectName("Primary")
        self.prepare_button.clicked.connect(self._prepare)
        actions.addWidget(self.close_button)
        actions.addStretch(1)
        actions.addWidget(self.prepare_button)
        layout.addLayout(actions)

    def _source_mode_changed(self, *_args) -> None:
        source = self.choice.currentData() == "source-installation"
        self.source_controls.setVisible(source)
        self.limits.setText(
            "A supported procedure supplies the complete declared image order, slot actions and "
            "optional erase/restart steps. ROMVERSE translates it into controlled operations; "
            "it never runs the package's shell scripts. Keeping data is not a guarantee of "
            "compatibility. Verification here does not touch the phone."
            if source
            else self.manual_limits
        )
        if source:
            available = self.screen().availableGeometry() if self.screen() is not None else None
            height = min(580, available.height() - 80) if available is not None else 580
            self.setMinimumHeight(height)
            self.resize(self.width(), max(self.height(), height))
        else:
            self.setMinimumHeight(0)

    def _prepare(self) -> None:
        if self.worker is not None:
            return
        self.preparation = None
        self.choice.setEnabled(False)
        self.source_controls.setEnabled(False)
        self.prepare_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.status.setText(
            "Checking project evidence and hashing images. Large files may take a while…"
        )
        worker = ProjectPreparationWorker(
            self.service,
            self.project_id,
            self.choice.currentData(),
            source_service=self.source_service,
            wipe=self.wipe.isChecked(),
            reboot=self.reboot.isChecked(),
        )
        self.worker = worker
        worker.signals.complete.connect(self._prepared)
        worker.signals.failed.connect(self._failed)
        try:
            start_background(worker)
        except RuntimeError as exc:
            self._show_error(str(exc))

    @Slot(object)
    def _prepared(self, preparation: object) -> None:
        if self.worker is None or self.sender() is not self.worker.signals:
            return
        if (
            not isinstance(preparation, (ProjectFlashPreparation, SourceInstallationRecipe))
            or preparation.project_id != self.project_id
        ):
            self._failed(
                "Preparation returned mismatched project evidence. No phone command was sent."
            )
            return
        self.worker = None
        self.preparation = preparation
        self.accept()

    @Slot(str)
    def _failed(self, message: str) -> None:
        if self.worker is None or self.sender() is not self.worker.signals:
            return
        self._show_error(message)

    def _show_error(self, message: str) -> None:
        self.worker = None
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText(message)
        self.choice.setEnabled(True)
        self.source_controls.setEnabled(True)
        self.prepare_button.setEnabled(True)
        self.close_button.setEnabled(True)

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


class ProjectFlashDialog(LocalFlashDialog):
    """Use the proven local lifecycle with a fixed, source-bound image inventory."""

    def __init__(self, service, devices, parent=None, *, preparation, **kwargs) -> None:
        self.preparation = preparation
        super().__init__(service, devices, parent, **kwargs)
        self.setWindowTitle("ROMVERSE · Guided local image installation")
        self.eyebrow.setText("GUIDED INSTALLATION  •  SOURCE-BOUND LOCAL IMAGES")
        self.title.setText("Review your local image operation")
        self.introduction.setText(
            f"{preparation.candidate_label}. Images are bound to this project's saved evidence. "
            "Choose images below; enter their exact destinations and order."
        )
        self.introduction.setTextFormat(Qt.TextFormat.PlainText)
        self.mapping_hint.setText(
            "Manual mapping · top-to-bottom write order. No partitions or slots are guessed. "
            "This is a selected-image operation, not a verified complete-ROM installation recipe."
        )
        self.image_choice = QComboBox()
        self.image_choice.setAccessibleName("Verified project image to add")
        for item in preparation.images:
            self.image_choice.addItem(f"{item.name} · {human_bytes(item.size_bytes)}")
        self.image_actions.insertWidget(0, self.image_choice, 1)
        self.add_button.setText("Add selected image")
        self.status.setText(
            "Add a verified image and enter its exact partition. Preparing a plan sends no writes."
        )

    def _choose_image(self) -> None:
        index = self.image_choice.currentIndex()
        if 0 <= index < len(self.preparation.images):
            # An image's name is deliberately not used as a destination guess.
            self.add_image(self.preparation.images[index].path)

    def _plan_context(self) -> tuple[str, ...]:
        return (
            f"PROJECT  {self.preparation.project_id}",
            f"CANDIDATE  {self.preparation.candidate_label}",
            f"SOURCE SHA-256  {self.preparation.source_sha256}",
            f"PREPARATION  {self.preparation.preparation_digest}",
            "SCOPE  User-mapped local image subset; not a complete-ROM or production certificate.",
            *self.preparation.warnings,
            "",
        )

    def _set_busy(self, busy: bool, *, writing: bool = False) -> None:
        super()._set_busy(busy, writing=writing)
        if hasattr(self, "image_choice"):
            self.image_choice.setEnabled(not busy and not self.monitoring)
