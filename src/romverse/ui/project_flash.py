"""Choose explicit image mappings or a supported source-declared installation."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from romverse.rom.models import ProjectError
from romverse.rom.project_flash import ProjectFlashPreparation
from romverse.rom.source_installation import SourceInstallationRecipe
from romverse.ui.background import ManagedRunnable, start_background
from romverse.ui.formatters import human_bytes
from romverse.ui.local_flash import LocalFlashDialog
from romverse.ui.source_operation_session import (
    ProjectPreparationRequest,
    SourceOperationPhase,
    SourceOperationSession,
    SourceOperationSnapshot,
)


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
        candidate_service=None,
        procedure_project_id="",
        procedure_path=None,
        wipe=False,
        reboot=True,
    ) -> None:
        super().__init__()
        self.service = service
        self.project_id = project_id
        self.candidate_choice = candidate_choice
        self.source_service = source_service
        self.candidate_service = candidate_service
        self.procedure_project_id = procedure_project_id
        self.procedure_path = procedure_path
        self.wipe = wipe
        self.reboot = reboot
        self.signals = PreparationSignals()

    def execute(self) -> None:
        try:
            if self.candidate_choice == "candidate-installation":
                if self.candidate_service is None:
                    raise ValueError("Rebuilt installation is unavailable in this context.")
                procedure = self.procedure_project_id
                if self.procedure_path is not None:
                    procedure = self.candidate_service.import_procedure(self.procedure_path)
                if not procedure:
                    raise ValueError("Choose the base installation package for this rebuilt ROM.")
                value = self.candidate_service.prepare(
                    self.project_id, procedure, wipe=self.wipe, reboot=self.reboot
                )
            elif self.candidate_choice == "source-installation":
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

    def __init__(
        self,
        service,
        project_id: str,
        parent=None,
        *,
        source_service=None,
        candidate_service=None,
        session: SourceOperationSession | None = None,
        source_sha256: str = "",
    ) -> None:
        super().__init__(parent)
        self._owns_session = session is None
        operation_session = session or SourceOperationSession(
            None,
            (),
            project_id=project_id,
            source_sha256=source_sha256,
            preparation_service=service,
            source_service=source_service,
            candidate_service=candidate_service,
        )
        if self._owns_session:
            operation_session.setParent(self)
        self.session = operation_session
        self.service = service
        self.project_id = project_id
        self.source_service = source_service
        self.candidate_service = candidate_service
        self.procedure_path: Path | None = None
        self._base_discovery_error = ""
        self.preparation: ProjectFlashPreparation | SourceInstallationRecipe | None = (
            operation_session.preparation
        )
        self.worker: ProjectPreparationWorker | None = operation_session.worker
        self.monitoring = False
        self.setWindowTitle("ROMVERSE · Choose installation route")
        self.resize(740, 430)
        self.setMinimumWidth(520)
        if self.screen() is not None:
            available = self.screen().availableGeometry()
            self.setMinimumWidth(min(520, available.width() - 40))
            self.resize(min(740, available.width() - 40), min(430, available.height() - 80))
        self.setModal(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        eyebrow = QLabel("GUIDED INSTALLATION  •  VERIFIED ROUTES")
        eyebrow.setObjectName("Eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("Choose your installation route")
        title.setWordWrap(True)
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        introduction = QLabel(
            "ROMVERSE prefers a complete, understood installation route when one is available. "
            "Complete routes preserve the package's declared order and slot actions. Manual "
            "image subsets remain available for explicit specialist mapping and are never "
            "represented as a full ROM installation."
        )
        introduction.setWordWrap(True)
        layout.addWidget(introduction)
        self.choice = QComboBox()
        self.choice.setAccessibleName("Installation route")
        if candidate_service is not None:
            self.choice.addItem(
                "Complete rebuilt ROM · verify exact procedure", "candidate-installation"
            )
        self.choice.addItem("Manual rebuilt image subset · explicit mapping", "built")
        self.choice.addItem("Manual protected-source subset · explicit mapping", "protected")
        if source_service is not None:
            self.choice.addItem(
                "Complete protected firmware · verify package procedure", "source-installation"
            )
        preferred = self.choice.findData(
            "candidate-installation"
            if candidate_service is not None
            else "source-installation"
            if source_service is not None
            else "built"
        )
        if preferred >= 0:
            self.choice.setCurrentIndex(preferred)
        layout.addWidget(self.choice)
        self.base_controls = QWidget()
        base_layout = QVBoxLayout(self.base_controls)
        base_layout.setContentsMargins(0, 0, 0, 0)
        base_hint = QLabel(
            "Base installation package · supplies the unchanged firmware and installation order. "
            "ROMVERSE checks it against your build and inserts the rebuilt images automatically."
        )
        base_hint.setWordWrap(True)
        base_layout.addWidget(base_hint)
        self.base_choice = QComboBox()
        self.base_choice.setAccessibleName("Base installation package")
        base_layout.addWidget(self.base_choice)
        self.base_file_button = QPushButton("Choose a base package ZIP…")
        self.base_file_button.clicked.connect(self._choose_base_file)
        base_layout.addWidget(self.base_file_button)
        self._refresh_base_choices()
        self.base_choice.currentIndexChanged.connect(self._base_choice_changed)
        layout.addWidget(self.base_controls)
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
            "Manual subset route: this is not a complete ROM installation. You must supply the "
            "correct partitions, slots and write order. ROMVERSE verifies the selected project "
            "images, but it does not infer the missing package procedure. Preparation never "
            "reboots or writes the phone."
        )
        self.limits = limits
        self.manual_limits = limits.text()
        limits.setWordWrap(True)
        limits.setObjectName("Warning")
        layout.addWidget(limits)
        self.choice.currentIndexChanged.connect(self._source_mode_changed)
        self._source_mode_changed()
        self.status = QLabel(
            self._base_discovery_error or "Choose a source, then verify its images."
        )
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
        actions.setContentsMargins(24, 8, 24, 20)
        self.close_button = QPushButton("Cancel")
        self.close_button.clicked.connect(self.reject)
        self.prepare_button = QPushButton("Verify and continue")
        self.prepare_button.setObjectName("Primary")
        self.prepare_button.clicked.connect(self._prepare)
        actions.addWidget(self.close_button)
        actions.addStretch(1)
        actions.addWidget(self.prepare_button)
        outer.addLayout(actions)
        self._source_mode_changed()
        operation_session.changed.connect(self._render_session)
        operation_session.preparation_finished.connect(self._session_prepared)
        self._restore_request()
        self._render_session(operation_session.snapshot())

    def _refresh_base_choices(self) -> None:
        previous = self.base_choice.currentData()
        self.base_choice.clear()
        self.base_choice.addItem("Select an imported base package, or choose a ZIP below", "")
        if self.candidate_service is None:
            return
        store = self.candidate_service.store
        try:
            for project in store.list_projects():
                if project.project_id != self.project_id and project.original is not None:
                    self.base_choice.addItem(project.name, project.project_id)
            if not previous:
                receipt = self.candidate_service.base.load(self.project_id)
                previous = receipt.procedure_project_id if receipt is not None else ""
            self._base_discovery_error = ""
        except (OSError, ValueError, ProjectError):
            self._base_discovery_error = (
                "The saved project/base selection could not be read. Check the selected ROM project "
                "and choose its base package; preparation will verify the current files again."
            )
        index = self.base_choice.findData(previous)
        if index > 0:
            self.base_choice.setCurrentIndex(index)
        elif self.base_choice.count() == 2:
            self.base_choice.setCurrentIndex(1)

    def _choose_base_file(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self,
            "Choose the base installation package",
            "",
            "Firmware installation package (*.zip)",
        )
        if not name:
            return
        self.procedure_path = Path(name)
        self.base_choice.setCurrentIndex(0)
        self.base_file_button.setText(f"Change selected package · {self.procedure_path.name}")
        self.base_file_button.setToolTip(str(self.procedure_path))
        self.status.setText(
            "Selected package will be protected and checked when you continue. No phone action."
        )

    def _base_choice_changed(self, *_args) -> None:
        if self.base_choice.currentData():
            self.procedure_path = None
            self.base_file_button.setText("Choose a base package ZIP…")
            self.base_file_button.setToolTip("")

    def _source_mode_changed(self, *_args) -> None:
        candidate = self.choice.currentData() == "candidate-installation"
        source = self.choice.currentData() in {"source-installation", "candidate-installation"}
        self.base_controls.setVisible(candidate)
        self.source_controls.setVisible(source)
        self.limits.setText(
            "Preferred complete route: ROMVERSE composes your rebuilt super and AVB image with "
            "unchanged base firmware checked against the exact build OTA. It preserves the "
            "understood package procedure; it is still an unlocked-device experiment, not an "
            "OEM-trusted or physically tested release. Preparation does not change the phone."
            if candidate
            else "Preferred complete route: ROMVERSE verifies that the package has an understood "
            "procedure with a complete declared image order, slot actions and optional "
            "erase/restart steps. It translates those declarations into controlled operations "
            "and never runs the package's shell scripts. Verification does not touch the phone."
            if source
            else self.manual_limits
        )
        if hasattr(self, "prepare_button"):
            self.prepare_button.setText(
                "Verify complete rebuilt ROM"
                if candidate
                else "Verify complete firmware route"
                if source
                else "Prepare manual image subset"
            )
        if source:
            available = self.screen().availableGeometry() if self.screen() is not None else None
            desired = 700 if candidate else 580
            height = min(desired, available.height() - 80) if available is not None else desired
            self.setMinimumHeight(height)
            self.resize(self.width(), max(self.height(), height))
        else:
            self.setMinimumHeight(0)

    def _restore_request(self) -> None:
        request = self.session.preparation_request
        if request is None:
            return
        choice = self.choice.findData(request.candidate_choice)
        if choice >= 0:
            self.choice.setCurrentIndex(choice)
        base = self.base_choice.findData(request.procedure_project_id)
        if base >= 0:
            self.base_choice.setCurrentIndex(base)
        self.procedure_path = request.procedure_path
        if request.procedure_path is not None:
            self.base_choice.setCurrentIndex(0)
            self.base_file_button.setText(
                f"Change selected package · {request.procedure_path.name}"
            )
            self.base_file_button.setToolTip(str(request.procedure_path))
        self.wipe.setChecked(request.wipe)
        self.reboot.setChecked(request.reboot)

    def _render_session(self, snapshot: object) -> None:
        if not isinstance(snapshot, SourceOperationSnapshot):
            return
        preparing = snapshot.phase is SourceOperationPhase.PREPARING
        self.worker = self.session.worker if preparing else None
        self.preparation = self.session.preparation
        self.choice.setEnabled(not preparing)
        self.source_controls.setEnabled(not preparing)
        self.base_controls.setEnabled(not preparing)
        self.prepare_button.setEnabled(not preparing)
        can_hide = preparing and self._can_hide_preparation()
        self.close_button.setEnabled(not preparing or can_hide)
        self.close_button.setText("Hide preparation" if can_hide else "Cancel")
        if preparing:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(snapshot.progress_value)
        self.status.setText(
            self._base_discovery_error
            if (
                self._base_discovery_error
                and snapshot.phase is SourceOperationPhase.CHOOSING
                and self.session.preparation_request is None
            )
            else snapshot.status
        )

    def _session_prepared(self, preparation: object) -> None:
        if preparation is not self.session.preparation:
            return
        self.preparation = preparation
        if self.isVisible():
            QDialog.accept(self)

    def _can_hide_preparation(self) -> bool:
        request = self.session.preparation_request
        return bool(
            not self._owns_session
            and request is not None
            and request.candidate_choice
            in {"candidate-installation", "source-installation"}
        )

    def _prepare(self) -> None:
        if self.session.busy:
            return
        if (
            self.choice.currentData() == "candidate-installation"
            and self.procedure_path is None
            and not self.base_choice.currentData()
        ):
            self.status.setText(
                "Choose the base package below; ROMVERSE will verify and map it for you."
            )
            self.base_file_button.setFocus()
            return
        request = ProjectPreparationRequest(
            project_id=self.project_id,
            source_sha256=self.session.source_sha256,
            candidate_choice=self.choice.currentData(),
            procedure_project_id=self.base_choice.currentData(),
            procedure_path=self.procedure_path,
            wipe=self.wipe.isChecked(),
            reboot=self.reboot.isChecked(),
        )
        worker = ProjectPreparationWorker(
            self.service,
            self.project_id,
            request.candidate_choice,
            source_service=self.source_service,
            candidate_service=self.candidate_service,
            procedure_project_id=request.procedure_project_id,
            procedure_path=request.procedure_path,
            wipe=request.wipe,
            reboot=request.reboot,
        )
        if (
            not self.session.start_preparation(worker, request, starter=start_background)
            and not self.session.preparation_error
        ):
            self.status.setText(
                "Preparation could not start because this mission changed. Reopen the project "
                "and verify the intended source."
            )

    def _show_error(self, message: str) -> None:
        self.worker = None
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText(message)
        self.choice.setEnabled(True)
        self.source_controls.setEnabled(True)
        self.base_controls.setEnabled(True)
        if self.procedure_path is None:
            self._refresh_base_choices()
        self.prepare_button.setEnabled(True)
        self.close_button.setEnabled(True)

    def done(self, result: int) -> None:
        if self.session.busy and not self._can_hide_preparation():
            return
        QDialog.done(self, result)

    def reject(self) -> None:
        self.done(QDialog.DialogCode.Rejected)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.session.busy and not self._can_hide_preparation():
            event.ignore()
        else:
            QDialog.closeEvent(self, event)


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
