from __future__ import annotations

from contextlib import suppress
from dataclasses import replace
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from romverse.ascension.entry import AscensionEntryBrief, build_ascension_entry_brief
from romverse.ascension.integration import RootRomIntegrationService
from romverse.ascension.models import AscensionMethod
from romverse.ascension.route import AscensionRouteRecordService
from romverse.device.models import DeviceState
from romverse.infrastructure.local_store import LocalStoreError
from romverse.infrastructure.provisioning import required_tools_for_debloat
from romverse.nexus.events import (
    LiveConsoleEventStore,
    LiveConsoleStoreError,
    MissionConfidence,
    MissionState,
)
from romverse.rom.boot_observation import BootObservationService, BootObservationStatus
from romverse.rom.debloat import DebloatService
from romverse.rom.guided import (
    STAGES,
    GuidedAssessment,
    GuidedContext,
    GuidedFailure,
    GuidedMissionEngine,
    GuidedMissionState,
    GuidedMissionStore,
    GuidedStageStatus,
)
from romverse.rom.models import ProjectError
from romverse.rom.recipes import RecipeStore
from romverse.ui.background import ManagedRunnable, start_background
from romverse.ui.process_progress import ProcessProgressBar

_STAGE_LEARNING_QUERIES = {
    "project": "ROM Studio",
    "firmware": "firmware source",
    "provenance": "ROM inspection",
    "workspace": "ROM Studio",
    "device": "Device Atlas",
    "customize": "Recipes and ROM DNA",
    "validate_recipe": "Recipe safety",
    "debloat": "Incremental debloat safety",
    "root_choice": "Root state",
    "build_plan": "Build plans",
    "recovery": "Recovery checklist",
    "toolchain": "Exit code 127",
    "build_sign": "Dynamic partition and AVB validation",
    "flash": "Guardian safety",
    "first_boot": "First-boot evidence after a ROM change",
}

# Keep the advertised Genesis flight plan and its UI executor under one tested
# contract. A newly added or renamed stage must never degrade into an inert
# card that discovers the missing implementation only after a user clicks it.
GENESIS_STAGE_ACTIONS = frozenset(
    {
        "new-project",
        "import",
        "verify-inspect",
        "prepare-workspace",
        "check-device",
        "create-recipe",
        "validate-recipe",
        "guided-debloat",
        "choose-root",
        "plan-verify",
        "snapshot",
        "refresh-tools",
        "build-sign",
        "flash",
        "first-boot",
    }
)

if TYPE_CHECKING:
    from romverse.ui.rom_studio import RomStudio


class AscensionEntrySignals(QObject):
    complete = Signal(str, int, object)
    failed = Signal(str, int, str)


class AscensionEntryWorker(ManagedRunnable):
    """Resolve a source/device-bound root preview without blocking Genesis's UI."""

    def __init__(
        self,
        store,
        registry,
        project_id: str,
        generation: int,
        device,
        companion,
    ) -> None:
        super().__init__()
        self.store = store
        self.registry = registry
        self.project_id = project_id
        self.generation = generation
        self.device = device
        self.companion = companion
        self.signals = AscensionEntrySignals()

    @Slot()
    def execute(self) -> None:
        try:
            service = AscensionRouteRecordService(
                self.store,
                self.registry,
            )
            record = service.resolve(
                self.project_id,
                self.device,
                self.companion,
            )
            brief = build_ascension_entry_brief(
                record,
                device_matches=service.matches_device(record, self.device),
            )
            self.signals.complete.emit(self.project_id, self.generation, brief)
        except Exception as exc:  # UI boundary reports a safe, non-authorizing result
            self.signals.failed.emit(self.project_id, self.generation, str(exc))


class StageButton(QPushButton):
    def __init__(self, assessment: GuidedAssessment, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.stage_id = assessment.stage.stage_id
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(58)
        self.update_assessment(assessment)

    def update_assessment(self, assessment: GuidedAssessment) -> None:
        symbols = {
            GuidedStageStatus.COMPLETE: "✓",
            GuidedStageStatus.READY: "◆",
            GuidedStageStatus.ATTENTION: "!",
            GuidedStageStatus.LOCKED: "·",
            GuidedStageStatus.FUTURE: "◇",
        }
        self.setText(
            f"{symbols[assessment.status]}   {assessment.stage.number:02d}   "
            f"{assessment.stage.short_title}"
        )
        self.setProperty("stageStatus", assessment.status.value)
        status_note = {
            GuidedStageStatus.COMPLETE: "Verified",
            GuidedStageStatus.READY: "Ready",
            GuidedStageStatus.ATTENTION: "Needs attention",
            GuidedStageStatus.LOCKED: "Locked",
            GuidedStageStatus.FUTURE: "Future phase",
        }[assessment.status]
        guidance = [
            f"{assessment.stage.number:02d} • {assessment.stage.title}",
            f"State: {status_note}",
            "",
            assessment.stage.explanation,
            "",
            f"Result if completed: {assessment.next_outcome}",
        ]
        if assessment.blockers:
            guidance.append("")
            guidance.append("Possible fixes:")
            guidance.extend(f"• {item}" for item in assessment.blockers)
        else:
            guidance.append("")
            guidance.append("No blockers are currently detected.")
        self.setToolTip("\n".join(guidance))
        self.style().unpolish(self)
        self.style().polish(self)


class GuidedBuildMission(QDialog):
    """Evidence-driven ROM journey with explicit Guardian boundaries."""

    def __init__(self, studio: RomStudio) -> None:
        super().__init__(studio)
        self.studio = studio
        self.engine = GuidedMissionEngine()
        self.state = self._load_state()
        self.assessments: tuple[GuidedAssessment, ...] = ()
        self.selected_index = 0
        self.operation_queue: list[str] = []
        self.active_operation = ""
        self.failure: GuidedFailure | None = None
        self.stage_buttons: list[StageButton] = []
        self.autopilot_active = False
        self.live_mission_id = ""
        self.live_mission_project_id = ""
        self.live_mission_progress = 0
        self.live_paused = False
        self.root_entry_brief: AscensionEntryBrief = build_ascension_entry_brief(None)
        self.root_preview_project_id = ""
        self.root_preview_active = False
        self.root_preview_attempted = False
        self.root_preview_generation = 0

        self.setWindowTitle("ROMVERSE • Genesis Sequence")
        self.setModal(True)
        self.setMinimumSize(980, 680)
        self.resize(1180, 790)
        self.setStyleSheet(self._stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("MissionHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(28, 18, 28, 18)
        heading = QVBoxLayout()
        eyebrow = QLabel("ROM STUDIO  /  GENESIS SEQUENCE")
        eyebrow.setObjectName("MissionEyebrow")
        title = QLabel("Your guided journey from firmware to first boot")
        title.setObjectName("MissionTitle")
        heading.addWidget(eyebrow)
        heading.addWidget(title)
        header_layout.addLayout(heading, 1)
        self.guardian_badge = QLabel("◆  GUARDIAN ACTIVE")
        self.guardian_badge.setObjectName("GuardianBadge")
        header_layout.addWidget(self.guardian_badge)
        root.addWidget(header)

        progress_bar = QFrame()
        progress_bar.setObjectName("ProgressStrip")
        progress_layout = QHBoxLayout(progress_bar)
        progress_layout.setContentsMargins(28, 10, 28, 10)
        self.progress_copy = QLabel()
        self.progress_copy.setObjectName("MissionMuted")
        self.overall_progress = QProgressBar()
        self.overall_progress.setTextVisible(False)
        self.overall_progress.setFixedHeight(7)
        progress_layout.addWidget(self.progress_copy)
        progress_layout.addWidget(self.overall_progress, 1)
        root.addWidget(progress_bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        rail_scroll = QScrollArea()
        rail_scroll.setObjectName("StageRail")
        rail_scroll.setWidgetResizable(True)
        rail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rail_scroll.setFixedWidth(285)
        rail_host = QWidget()
        self.rail_layout = QVBoxLayout(rail_host)
        self.rail_layout.setContentsMargins(14, 18, 14, 18)
        self.rail_layout.setSpacing(6)
        rail_title = QLabel("MISSION STAGES")
        rail_title.setObjectName("MissionEyebrow")
        self.rail_layout.addWidget(rail_title)
        self.rail_layout.addSpacing(4)
        for index, stage in enumerate(STAGES):
            placeholder = GuidedAssessment(stage, GuidedStageStatus.LOCKED, (), (), "")
            button = StageButton(placeholder)
            button.clicked.connect(lambda _checked=False, i=index: self._select_stage(i))
            self.rail_layout.addWidget(button)
            self.stage_buttons.append(button)
        self.rail_layout.addStretch()
        rail_scroll.setWidget(rail_host)
        body.addWidget(rail_scroll)

        main_scroll = QScrollArea()
        main_scroll.setObjectName("MissionMain")
        main_scroll.setWidgetResizable(True)
        main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        main_host = QWidget()
        main = QVBoxLayout(main_host)
        main.setContentsMargins(34, 28, 34, 24)
        main.setSpacing(14)

        self.step_label = QLabel()
        self.step_label.setObjectName("MissionEyebrow")
        self.stage_title = QLabel()
        self.stage_title.setObjectName("StageTitle")
        self.stage_title.setWordWrap(True)
        self.stage_detail = QLabel()
        self.stage_detail.setObjectName("MissionBody")
        self.stage_detail.setWordWrap(True)
        main.addWidget(self.step_label)
        main.addWidget(self.stage_title)
        main.addWidget(self.stage_detail)

        self.status_banner = QFrame()
        self.status_banner.setObjectName("StatusBanner")
        status_layout = QHBoxLayout(self.status_banner)
        status_layout.setContentsMargins(18, 13, 18, 13)
        self.status_icon = QLabel("◆")
        self.status_icon.setObjectName("StatusIcon")
        self.status_text = QLabel()
        self.status_text.setObjectName("StatusText")
        self.status_text.setWordWrap(True)
        status_layout.addWidget(self.status_icon)
        status_layout.addWidget(self.status_text, 1)
        main.addWidget(self.status_banner)

        self.process_frame = QFrame()
        self.process_frame.setObjectName("ProcessCard")
        process_layout = QVBoxLayout(self.process_frame)
        process_layout.setContentsMargins(18, 11, 18, 11)
        process_layout.setSpacing(7)
        self.process_label = QLabel("ROMVERSE is processing this stage")
        self.process_label.setObjectName("MissionMuted")
        self.process_progress = ProcessProgressBar()
        process_layout.addWidget(self.process_label)
        process_layout.addWidget(self.process_progress)
        self.process_frame.setVisible(False)
        main.addWidget(self.process_frame)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        evidence_card, self.evidence = self._card("WHAT ROMVERSE FOUND")
        recommendation_card, self.recommendation = self._card("RECOMMENDATION")
        cards.addWidget(evidence_card, 1)
        cards.addWidget(recommendation_card, 1)
        main.addLayout(cards)

        next_card, self.next_outcome = self._card("WHAT HAPPENS NEXT")
        main.addWidget(next_card)

        self.diagnostic_card, diagnostic_body = self._card("ROMVERSE DIAGNOSIS")
        self.diagnostic_card.setObjectName("DiagnosticCard")
        self.diagnostic_title = QLabel()
        self.diagnostic_title.setObjectName("DiagnosticTitle")
        self.diagnostic_text = diagnostic_body
        diagnostic_layout = self.diagnostic_card.layout()
        diagnostic_layout.insertWidget(1, self.diagnostic_title)
        self.diagnostic_card.setVisible(False)
        main.addWidget(self.diagnostic_card)

        main.addStretch()
        main_scroll.setWidget(main_host)
        body.addWidget(main_scroll, 1)
        root.addLayout(body, 1)

        footer = QFrame()
        footer.setObjectName("MissionFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 14, 24, 14)
        footer_layout.setSpacing(10)
        self.back_button = QPushButton("←  Back")
        self.back_button.clicked.connect(self._back)
        self.learn_button = QPushButton("Learn this stage")
        self.learn_button.setObjectName("SecondaryAction")
        self.learn_button.setToolTip(
            "Save Genesis progress and open the verified ROMVERSE Archives guide for this stage."
        )
        self.learn_button.clicked.connect(self._open_stage_learning)
        self.save_button = QPushButton("Save && exit")
        self.save_button.clicked.connect(self.accept)
        self.skip_button = QPushButton("Continue to Nebula Debloat")
        self.skip_button.setObjectName("SecondaryAction")
        self.skip_button.clicked.connect(self._skip_customization)
        self.action_button = QPushButton()
        self.action_button.setObjectName("MissionAction")
        self.action_button.clicked.connect(self._run_stage)
        self.auto_button = QPushButton("Auto-resolve && continue")
        self.auto_button.setObjectName("MissionNext")
        self.auto_button.setToolTip(
            "Run consecutive safe local stages automatically. ROMVERSE pauses for firmware "
            "selection, customization choices, device authorization, backups, wipes, and final consent."
        )
        self.auto_button.clicked.connect(self._start_autopilot)
        self.next_button = QPushButton("Next  →")
        self.next_button.setObjectName("MissionNext")
        self.next_button.clicked.connect(self._next)
        footer_layout.addWidget(self.back_button)
        footer_layout.addWidget(self.learn_button)
        footer_layout.addWidget(self.save_button)
        footer_layout.addStretch()
        footer_layout.addWidget(self.skip_button)
        footer_layout.addWidget(self.auto_button)
        footer_layout.addWidget(self.action_button)
        footer_layout.addWidget(self.next_button)
        root.addWidget(footer)

        self.studio.operation_started.connect(self._operation_started)
        self.studio.operation_progress.connect(self._operation_progress)
        self.studio.operation_completed.connect(self._operation_completed)
        self.studio.operation_failed.connect(self._operation_failed)
        self.studio.device_context_changed.connect(self._root_device_context_changed)
        self.studio.device_scan_finished.connect(self._device_scan_finished)
        self._refresh(select_current=True)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        parent = self.parentWidget()
        if parent is not None:
            available = parent.window().geometry()
            self.resize(
                max(self.minimumWidth(), int(available.width() * 0.88)),
                max(self.minimumHeight(), int(available.height() * 0.88)),
            )
            frame = self.frameGeometry()
            frame.moveCenter(parent.window().frameGeometry().center())
            self.move(frame.topLeft())

    def closeEvent(self, event) -> None:
        self._save_state()
        self._pause_genesis_live("Genesis Sequence was closed and saved for later.")
        super().closeEvent(event)

    def accept(self) -> None:
        if not self._save_state():
            self._render_stage()
            return
        self._pause_genesis_live("Genesis Sequence was saved and paused.")
        super().accept()

    def _live_console_store(self) -> LiveConsoleEventStore | None:
        store = getattr(self.studio, "live_console_store", None)
        return store if isinstance(store, LiveConsoleEventStore) else None

    def _finish_genesis_live(
        self,
        state: MissionState,
        summary: str,
        explanation: str,
        next_action: str,
        confidence: MissionConfidence,
    ) -> None:
        mission_id = self.live_mission_id
        self.live_mission_id = ""
        self.live_mission_project_id = ""
        self.live_mission_progress = 0
        store = self._live_console_store()
        if store is None or not mission_id:
            return
        with suppress(LiveConsoleStoreError):
            store.finish(
                mission_id,
                state,
                summary=summary,
                explanation=explanation,
                next_action=next_action,
                confidence=confidence,
            )

    def _pause_genesis_live(self, summary: str) -> None:
        self.live_paused = True
        self._finish_genesis_live(
            MissionState.ATTENTION,
            summary,
            "Verified project evidence remains saved. No phone write, wipe, unlock, root, flash, or bootloader relock was performed by Genesis.",
            "Reopen Genesis Sequence to resume from the first stage that lacks verified evidence.",
            MissionConfidence.HIGH,
        )

    def _sync_genesis_live(self) -> None:
        store = self._live_console_store()
        if store is None or not self.assessments:
            return
        project = self.studio.current_project
        project_id = project.project_id if project is not None else ""
        if self.live_mission_id and project_id != self.live_mission_project_id:
            self._finish_genesis_live(
                MissionState.ATTENTION,
                "Genesis switched to a different project context.",
                "ROMVERSE closed the earlier timeline so evidence from two projects cannot be mixed.",
                "Continue with the newly selected project.",
                MissionConfidence.HIGH,
            )
        progress = self.engine.progress(self.assessments)
        if all(item.status is GuidedStageStatus.COMPLETE for item in self.assessments):
            refs = (f"projects/{project_id}/guided-mission.json",) if project_id else ()
            if self.live_mission_id:
                self._finish_genesis_live(
                    MissionState.SUCCEEDED,
                    "Genesis Sequence is complete with verified evidence for all 15 stages.",
                    "The protected source, local build route, Guardian evidence, flash receipt, and stable first boot are present. Bootloader relock remains prohibited.",
                    "Review the final evidence and keep the rollback material available.",
                    MissionConfidence.VERIFIED,
                )
            else:
                with suppress(LiveConsoleStoreError):
                    store.note(
                        source="Genesis Sequence",
                        stage="genesis-complete",
                        title="Genesis Sequence verified complete",
                        summary="All 15 stages are backed by current project evidence.",
                        explanation="ROMVERSE revalidated completion without inventing a device operation.",
                        next_action="Review the final evidence and retain rollback material.",
                        state=MissionState.INFORMATION,
                        progress_percent=100,
                        confidence=MissionConfidence.VERIFIED,
                        guardian_protected=True,
                        project_id=project_id,
                        evidence_refs=refs,
                        dedupe_key=f"genesis-complete-{project_id or 'workspace'}",
                    )
            self.live_paused = True
            return
        if self.live_paused:
            return
        if self.live_mission_id and progress < self.live_mission_progress:
            self._finish_genesis_live(
                MissionState.ATTENTION,
                "Genesis evidence changed and progress was recalculated.",
                "A previously completed stage no longer has matching evidence, so ROMVERSE closed the stale timeline.",
                "Review the first stage that now needs attention.",
                MissionConfidence.HIGH,
            )
        current = self.assessments[self.engine.current_index(self.assessments)]
        if not self.live_mission_id:
            refs = (f"projects/{project_id}/guided-mission.json",) if project_id else ()
            try:
                event = store.start(
                    source="Genesis Sequence",
                    stage="guided-rom-build",
                    title=f"Build {project.name if project is not None else 'a ROM'} through Genesis",
                    summary="ROMVERSE opened the evidence-driven 15-stage ROM journey.",
                    explanation="Genesis automates safe local stages and pauses for authoritative evidence, user choices, or Guardian consent.",
                    next_action=current.stage.recommendation,
                    project_id=project_id,
                    confidence=MissionConfidence.UNCONFIRMED,
                    guardian_protected=True,
                    evidence_refs=refs,
                )
            except LiveConsoleStoreError:
                return
            self.live_mission_id = event.mission_id
            self.live_mission_project_id = project_id
            self.live_mission_progress = 0
        blockers = " ".join(current.blockers[:2])
        explanation = current.stage.explanation
        if blockers:
            explanation += f" Current blocker: {blockers}"
        explanation += " Genesis cannot relock the bootloader."
        try:
            store.progress(
                self.live_mission_id,
                progress,
                summary=(
                    f"Stage {current.stage.number} of {len(STAGES)} — "
                    f"{current.stage.title} ({current.status.value})."
                ),
                explanation=explanation,
                next_action=current.stage.recommendation,
            )
            self.live_mission_progress = progress
        except LiveConsoleStoreError:
            self.live_mission_id = ""
            self.live_mission_project_id = ""
            self.live_mission_progress = 0

    def _card(self, title: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("MissionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 15, 18, 15)
        layout.setSpacing(7)
        heading = QLabel(title)
        heading.setObjectName("CardHeading")
        body = QLabel()
        body.setObjectName("CardBody")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(heading)
        layout.addWidget(body)
        return card, body

    def _load_state(self) -> GuidedMissionState:
        if self.studio.current_project is None:
            return GuidedMissionState()
        return GuidedMissionStore(
            self.studio.store.projects_root / self.studio.current_project.project_id
        ).load()

    def _save_state(self) -> bool:
        if self.studio.current_project is None:
            return False
        selected = STAGES[self.selected_index].stage_id
        self.state = replace(self.state, selected_stage=selected)
        try:
            GuidedMissionStore(
                self.studio.store.projects_root / self.studio.current_project.project_id
            ).save(self.state)
        except (LocalStoreError, OSError, ValueError) as exc:
            message = f"Genesis progress could not be stored safely: {exc}"
            self.state = replace(self.state, last_error=message)
            self.failure = GuidedFailure(
                "Genesis progress needs attention",
                message,
                (
                    "ROMVERSE kept the project and protected firmware unchanged.",
                    "Remove any linked or damaged guided-mission.json record, then reopen Genesis.",
                    "Do not continue until the current stage can be saved and restored.",
                ),
            )
            return False
        return True

    def _context(self) -> GuidedContext:
        return self.studio.guided_context(self.state)

    def _refresh(self, select_current: bool = False) -> None:
        current_project_id = (
            self.studio.current_project.project_id
            if self.studio.current_project is not None
            else ""
        )
        if self.root_preview_project_id and self.root_preview_project_id != current_project_id:
            self._reset_root_entry_preview()
        self.assessments = self.engine.assess(self._context())
        if select_current:
            # Resume at the first stage not supported by real evidence. This deliberately
            # outranks the last page viewed so a stale navigation choice cannot imply progress.
            self.selected_index = self.engine.current_index(self.assessments)
        self.overall_progress.setValue(self.engine.progress(self.assessments))
        complete = sum(item.status is GuidedStageStatus.COMPLETE for item in self.assessments)
        self.progress_copy.setText(f"{complete} OF {len(self.assessments)} STAGES VERIFIED")
        for index, (button, assessment) in enumerate(
            zip(self.stage_buttons, self.assessments, strict=True)
        ):
            button.update_assessment(assessment)
            button.setChecked(index == self.selected_index)
        self._sync_genesis_live()
        self._render_stage()

    def _reset_root_entry_preview(self) -> None:
        self.root_preview_generation += 1
        self.root_entry_brief = build_ascension_entry_brief(None)
        self.root_preview_project_id = ""
        self.root_preview_active = False
        self.root_preview_attempted = False

    @Slot()
    def _root_device_context_changed(self) -> None:
        self._reset_root_entry_preview()
        if self.assessments:
            self._refresh(select_current=False)

    def _ensure_root_entry_preview(self) -> None:
        project = self.studio.current_project
        if project is None or project.original is None:
            return
        if self.root_preview_project_id != project.project_id:
            self._reset_root_entry_preview()
            self.root_preview_project_id = project.project_id
        if self.root_preview_active or self.root_preview_attempted:
            return

        device = self.studio.devices[0] if self.studio.devices else None
        service = AscensionRouteRecordService(
            self.studio.store,
            self.studio.pack_registry,
        )
        existing = service.load(project.project_id)
        if existing is not None and service.matches_device(existing, device):
            self.root_entry_brief = build_ascension_entry_brief(
                existing,
                device_matches=True,
            )
            self.root_preview_attempted = True
            return

        self.root_preview_active = True
        self.root_preview_attempted = True
        worker = AscensionEntryWorker(
            self.studio.store,
            self.studio.pack_registry,
            project.project_id,
            self.root_preview_generation,
            device,
            getattr(self.studio, "companion_snapshot", None),
        )
        worker.signals.complete.connect(self._root_preview_complete)
        worker.signals.failed.connect(self._root_preview_failed)
        try:
            start_background(worker)
        except RuntimeError as exc:
            self.root_preview_active = False
            self.root_entry_brief = build_ascension_entry_brief(None, error=str(exc))

    @Slot(str, int, object)
    def _root_preview_complete(self, project_id: str, generation: int, brief: object) -> None:
        project = self.studio.current_project
        if (
            project is None
            or project.project_id != project_id
            or generation != self.root_preview_generation
        ):
            return
        self.root_preview_active = False
        if isinstance(brief, AscensionEntryBrief):
            self.root_entry_brief = brief
        if (
            self.assessments
            and self.assessments[self.selected_index].stage.stage_id == "root_choice"
        ):
            self._render_stage()

    @Slot(str, int, str)
    def _root_preview_failed(self, project_id: str, generation: int, message: str) -> None:
        project = self.studio.current_project
        if (
            project is None
            or project.project_id != project_id
            or generation != self.root_preview_generation
        ):
            return
        self.root_preview_active = False
        self.root_entry_brief = build_ascension_entry_brief(None, error=message)
        if (
            self.assessments
            and self.assessments[self.selected_index].stage.stage_id == "root_choice"
        ):
            self._render_stage()

    def _render_stage(self) -> None:
        assessment = self.assessments[self.selected_index]
        stage = assessment.stage
        if stage.stage_id == "root_choice" and assessment.status is not GuidedStageStatus.LOCKED:
            self._ensure_root_entry_preview()
        self.step_label.setText(
            f"STAGE {stage.number:02d} OF {len(STAGES):02d}  •  {assessment.status.value.upper()}"
        )
        self.stage_title.setText(stage.title)
        self.stage_detail.setText(stage.explanation)
        self.evidence.setText(
            "\n".join(f"✓  {item}" for item in assessment.evidence)
            if assessment.evidence
            else "No verified evidence has been recorded for this stage yet."
        )
        recommendation = stage.recommendation
        if assessment.blockers:
            recommendation += "\n\n" + "\n".join(f"•  {blocker}" for blocker in assessment.blockers)
        if stage.stage_id == "root_choice":
            recommendation += "\n\n" + self.root_entry_brief.guidance(
                scanning=self.root_preview_active,
            )
        self.recommendation.setText(recommendation)
        self.next_outcome.setText(assessment.next_outcome)

        status_copy = {
            GuidedStageStatus.COMPLETE: "Verified — this stage is backed by project evidence.",
            GuidedStageStatus.READY: "Ready — ROMVERSE can guide this step now.",
            GuidedStageStatus.ATTENTION: "Needs attention — follow the recommendation before continuing.",
            GuidedStageStatus.LOCKED: "Locked — complete the earlier highlighted stage first.",
            GuidedStageStatus.FUTURE: (
                "Post-flash verification phase — connect the exact phone and capture boot "
                "samples to complete first-boot health evidence."
            ),
        }[assessment.status]
        self.status_text.setText(status_copy)
        self.status_banner.setProperty("stageStatus", assessment.status.value)
        self.status_banner.style().unpolish(self.status_banner)
        self.status_banner.style().polish(self.status_banner)

        busy = bool(self.studio.worker or self.active_operation)
        self.action_button.setText("Processing stage …" if busy else stage.action_label)
        if (
            not busy
            and stage.stage_id == "flash"
            and any("handoff prepared" in item.casefold() for item in assessment.evidence)
        ):
            self.action_button.setText("Review exact write manifest")
        self.action_button.setToolTip(
            f"What: {stage.explanation}\n\nWhy: {stage.recommendation}\n\n"
            f"Result: {assessment.next_outcome}"
        )
        if stage.stage_id == "root_choice":
            self.action_button.setToolTip(
                self.root_entry_brief.guidance(scanning=self.root_preview_active)
            )
        build_control_available = stage.action in {"build-sign", "flash"} and not busy
        root_choice_available = stage.action == "choose-root" and not busy
        self.action_button.setEnabled(
            build_control_available
            or root_choice_available
            or (assessment.can_run and not busy and not stage.future_gate)
        )
        if stage.action == "choose-root" and assessment.status is GuidedStageStatus.COMPLETE:
            self.action_button.setText("Review root choice")
        self.auto_button.setEnabled(not busy and not self.autopilot_active)
        self.auto_button.setText(
            "ROMVERSE is resolving …" if self.autopilot_active else "Auto-resolve && continue"
        )
        self.next_button.setEnabled(
            assessment.status is GuidedStageStatus.COMPLETE
            and self.selected_index < len(self.assessments) - 1
            and not busy
        )
        self.back_button.setEnabled(self.selected_index > 0 and not busy)
        self.skip_button.setVisible(
            stage.stage_id == "customize" and assessment.status is not GuidedStageStatus.COMPLETE
        )
        self.skip_button.setEnabled(not busy)
        if self.failure is None:
            self.diagnostic_card.setVisible(False)
        else:
            self.diagnostic_card.setVisible(True)
            self.diagnostic_title.setText(self.failure.title)
            cleanup = (
                "\n\nROMVERSE also removed incomplete transaction files safely."
                if self.failure.safe_cleanup
                else ""
            )
            self.diagnostic_text.setText(
                self.failure.explanation
                + "\n\n"
                + "\n".join(f"•  {item}" for item in self.failure.recommendations)
                + cleanup
            )

    def _select_stage(self, index: int) -> None:
        self.selected_index = index
        self.failure = None
        self._save_state()
        self._refresh()

    def _back(self) -> None:
        if self.selected_index > 0:
            self._select_stage(self.selected_index - 1)

    def _next(self) -> None:
        if self.selected_index < len(self.assessments) - 1:
            self._select_stage(self.selected_index + 1)

    def _open_stage_learning(self) -> None:
        stage = self.assessments[self.selected_index].stage
        query = _STAGE_LEARNING_QUERIES[stage.stage_id]
        if not self._save_state():
            self._render_stage()
            return
        self.accept()
        self.studio.knowledge_requested.emit(query)

    def _skip_customization(self) -> None:
        self.state = replace(
            self.state,
            customization_skipped=False,
            recipe_skipped=True,
            recipe_validated=False,
            last_error="",
        )
        self.failure = None
        self._save_state()
        self._refresh()
        if self.autopilot_active:
            QTimer.singleShot(0, self._advance_autopilot)

    def _start_autopilot(self) -> None:
        if self.autopilot_active or self.studio.worker is not None or self.active_operation:
            return
        self.autopilot_active = True
        self.live_paused = False
        self.failure = None
        self._sync_genesis_live()
        self._render_stage()
        QTimer.singleShot(0, self._advance_autopilot)

    def _advance_autopilot(self) -> None:
        if not self.autopilot_active:
            return
        if self.studio.worker is not None or self.active_operation:
            return
        self._refresh(select_current=True)
        if all(assessment.status is GuidedStageStatus.COMPLETE for assessment in self.assessments):
            self._finish_autopilot(
                "Genesis Sequence complete. Every stage is backed by verified evidence."
            )
            return
        assessment = self.assessments[self.selected_index]
        stage = assessment.stage
        if assessment.status is GuidedStageStatus.LOCKED:
            self._finish_autopilot(
                "Complete the highlighted prerequisite before ROMVERSE can continue."
            )
            return
        if stage.stage_id == "customize":
            self._prompt_customization_choice()
            return
        if stage.stage_id == "root_choice":
            self._prompt_root_choice()
            return
        if stage.stage_id == "first_boot":
            self._run_first_boot_check()
            if self.failure is None and self._context().first_boot_verified:
                QTimer.singleShot(0, self._advance_autopilot)
            else:
                self._finish_autopilot(
                    "First-boot verification is now available in this stage. "
                    "Capture a stable Boot Observatory sample, then continue."
                )
            return
        if stage.stage_id in {"build_sign", "flash"}:
            # These stages open a full Guardian review surface. Pause Genesis first so
            # its own modal state cannot hide the child review or look indefinitely busy.
            before_stage = stage.stage_id
            self.autopilot_active = False
            self._render_stage()
            self._run_stage()
            self._refresh(select_current=True)
            after_stage = self.assessments[self.selected_index].stage.stage_id
            if after_stage != before_stage:
                self.autopilot_active = True
                QTimer.singleShot(0, self._advance_autopilot)
            else:
                self.status_text.setText(
                    "Automatic Genesis paused at the visible Guardian review. Complete its "
                    "highlighted requirement, then choose Auto-resolve & continue again."
                )
                self._pause_genesis_live(
                    "Genesis paused at the visible Guardian review for authoritative evidence or consent."
                )
            return

        before_stage = stage.stage_id
        self._run_stage()
        if self.studio.worker is not None or self.active_operation:
            return
        self._refresh(select_current=True)
        after_stage = self.assessments[self.selected_index].stage.stage_id
        if after_stage == before_stage:
            blockers = " ".join(assessment.blockers).strip()
            self._finish_autopilot(
                blockers
                or "ROMVERSE is waiting for the highlighted user choice or authoritative evidence."
            )
            return
        QTimer.singleShot(0, self._advance_autopilot)

    def _finish_autopilot(self, message: str) -> None:
        self.autopilot_active = False
        self._render_stage()
        self.status_text.setText(message)
        if all(item.status is GuidedStageStatus.COMPLETE for item in self.assessments):
            self._sync_genesis_live()
        else:
            self._pause_genesis_live(message)

    def _prompt_customization_choice(self) -> None:
        self.autopilot_active = False
        self._render_stage()
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Genesis Sequence • choose your ROM path")
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setText("Would you like to customize this ROM?")
        dialog.setInformativeText(
            "ROMVERSE has preserved and verified the base firmware. Choose the recommended route "
            "to review optional system apps in Nebula Debloat, or open Recipe Forge for other "
            "guided modifications first.\n\nNeither route changes the phone."
        )
        keep_base = dialog.addButton(
            "Continue to Nebula Debloat • Recommended",
            QMessageBox.ButtonRole.AcceptRole,
        )
        recipe_forge = dialog.addButton(
            "Open Recipe Forge",
            QMessageBox.ButtonRole.ActionRole,
        )
        dialog.addButton("Pause and review", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(keep_base)
        dialog.exec()
        if dialog.clickedButton() is keep_base:
            self.autopilot_active = True
            self._skip_customization()
            return
        if dialog.clickedButton() is recipe_forge:
            self.autopilot_active = True
            self._run_stage()
            self._refresh(select_current=True)
            current = self.assessments[self.selected_index].stage.stage_id
            if current == "customize":
                self._finish_autopilot(
                    "Recipe Forge was closed without a saved Recipe. Choose it again or keep the verified base unchanged."
                )
            else:
                QTimer.singleShot(0, self._advance_autopilot)
            return
        self.status_text.setText(
            "Genesis paused safely at your customization choice. No firmware or phone state changed."
        )
        self._pause_genesis_live("Genesis paused for the user's customization choice.")

    def _prompt_root_choice(self) -> None:
        resume_automatic = self.autopilot_active
        self.autopilot_active = False
        self._render_stage()
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Genesis Sequence • optional root")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText("Would you like ROMVERSE to root this ROM?")
        brief = self.root_entry_brief
        preview_state = "SCANNING" if self.root_preview_active else brief.status_label
        target = brief.patch_target or "not confirmed yet"
        dialog.setInformativeText(
            f"Root is completely optional.\n\nROMVERSE route: {preview_state}\n"
            f"Method: {brief.method_label}\nSource image: {target}\n"
            f"{brief.summary}\n\nChoose the Ascension route to continue the evidence scan and "
            "guided preparation, or continue Genesis with a standard unrooted ROM.\n\n"
            "Neither choice writes to the phone at this stage. Execution authority is NONE, "
            "and bootloader relocking is never permitted."
        )
        dialog.setDetailedText(brief.guidance(scanning=self.root_preview_active))
        rooted = dialog.addButton(
            brief.rooted_button_label,
            QMessageBox.ButtonRole.AcceptRole,
        )
        unrooted = dialog.addButton(
            "No • Continue unrooted",
            QMessageBox.ButtonRole.ActionRole,
        )
        dialog.addButton("Pause and review", QMessageBox.ButtonRole.RejectRole)
        if self.state.root_choice == "ascension":
            dialog.setDefaultButton(rooted)
        else:
            dialog.setDefaultButton(unrooted)
        dialog.exec()
        if dialog.clickedButton() is unrooted:
            if not self._select_unrooted_route():
                return
            self._resume_after_root_choice(resume_automatic)
            return
        if dialog.clickedButton() is rooted:
            self.state = replace(self.state, root_choice="ascension", last_error="")
            self._save_state()
            self.studio._open_ascension_protocol(self)
            self._refresh(select_current=True)
            if self._context().ascension_complete:
                self._resume_after_root_choice(resume_automatic)
            else:
                self.status_text.setText(
                    "Root was selected. Complete the highlighted Ascension Protocol stages, then "
                    "Genesis will continue from this exact point."
                )
                self._pause_genesis_live(
                    "Genesis paused while Ascension Protocol prepares the optional rooted ROM input."
                )
            return
        self.status_text.setText(
            "Genesis paused at the optional root choice. No firmware or phone state changed."
        )
        self._pause_genesis_live("Genesis paused for the user's optional root choice.")

    def _select_unrooted_route(self) -> bool:
        project = self.studio.current_project
        if project is None:
            return False
        integration_service = RootRomIntegrationService(self.studio.store)
        try:
            for method in AscensionMethod:
                if integration_service.load(project.project_id, method) is not None:
                    result = integration_service.rollback_latest(project.project_id, method)
                    if not result.success:
                        raise ProjectError(result.status)
        except ProjectError as exc:
            self.failure = self.engine.diagnose(str(exc))
            self.state = replace(self.state, last_error=f"root-choice: {exc}")
            self._save_state()
            self._refresh()
            return False
        self.state = replace(self.state, root_choice="skip", last_error="")
        self._save_state()
        self._refresh(select_current=True)
        return True

    def _resume_after_root_choice(self, resume_automatic: bool) -> None:
        if resume_automatic:
            self.autopilot_active = True
            self.live_paused = False
            self._sync_genesis_live()
            QTimer.singleShot(0, self._advance_autopilot)

    def _run_stage(self) -> None:
        assessment = self.assessments[self.selected_index]
        action = assessment.stage.action
        self.live_paused = False
        self._sync_genesis_live()
        self.failure = None
        if action == "new-project":
            self.studio._new_project()
            if self.studio.current_project is not None:
                self.state = self._load_state()
            self._refresh()
        elif action == "import":
            self.studio._import_original()
            self._refresh_if_idle()
        elif action == "verify-inspect":
            self._run_operations(["verify", "inspect"])
        elif action == "prepare-workspace":
            context = self._context()
            operations = []
            if not context.working_copy_ready:
                operations.append("working-copy")
            if not context.working_tree_ready:
                operations.append("extract")
            self._run_operations(operations)
        elif action == "check-device":
            if self.studio.device_scan_available:
                self.failure = None
                self.active_operation = "device-scan"
                self.process_label.setText("Scanning Android connection and refreshing Device DNA")
                self.process_progress.begin()
                self.process_frame.setVisible(True)
                self.status_text.setText(
                    "ROMVERSE is requesting a fresh read-only device scan. No phone state is changed."
                )
                self._render_stage()
                self.studio.device_scan_requested.emit()
                return
            context = self._context()
            if context.device is not None and context.device.state is DeviceState.UNAUTHORIZED:
                self.failure = self.engine.diagnose("ADB device unauthorized")
            elif context.device is None:
                self.failure = GuidedFailure(
                    "Waiting for the target phone",
                    "ROMVERSE scans automatically, but no Android device is currently visible.",
                    (
                        "Connect a data-capable USB cable and unlock the phone.",
                        "Enable Developer options and USB debugging, then accept the fingerprint.",
                    ),
                )
            self._refresh()
        elif action == "create-recipe":
            self.studio._guided_recipe(self)
            self.state = replace(
                self.state,
                customization_skipped=False,
                recipe_skipped=False,
            )
            self._save_state()
            self._refresh()
        elif action == "validate-recipe":
            if self.state.customization_skipped or self.state.recipe_skipped:
                self._refresh()
                return
            project = self.studio.current_project
            if project is None:
                return
            recipe = RecipeStore().load(self.studio.store.projects_root / project.project_id)
            if recipe is None:
                self.failure = self.engine.diagnose("Saved recipe is missing")
                self._refresh()
                return
            if any(step.operation != "inspect" for step in recipe.steps):
                self.studio._execute_recipe()
            else:
                self._run_operations(["preview-recipe"])
            self._refresh_if_idle()
        elif action == "guided-debloat":
            project = self.studio.current_project
            if project is None:
                return
            report = self.studio.inspection.load_report(project.project_id)
            if not self._resolve_required_tools(
                required_tools_for_debloat(report.partition_signals if report is not None else ()),
                purpose="Nebula Debloat needs these read-only tools to expose apps inside firmware images.",
            ):
                if self.autopilot_active:
                    self._finish_autopilot(
                        "Genesis paused because the exact read-only debloat tools are not verified yet."
                    )
                return
            from romverse.ui.debloat_sequence import NebulaDebloatDialog

            dialog = NebulaDebloatDialog(
                DebloatService(
                    self.studio.store,
                    self.studio.payload_service,
                    self.studio.filesystem_service,
                ),
                project.project_id,
                self,
            )
            dialog.exec()
            self._refresh(select_current=dialog.completed)
        elif action == "choose-root":
            self._prompt_root_choice()
        elif action == "plan-verify":
            self._run_operations(["plan", "verify-plan"])
        elif action == "snapshot":
            self._run_operations(["snapshot"])
        elif action == "first-boot":
            self._run_first_boot_check()
        elif action == "refresh-tools":
            self._resolve_required_tools(
                self._context().required_tools,
                purpose="Genesis must verify every source-bound build dependency before Forge Control.",
            )
            self._save_state()
            self._refresh()
        elif action == "build-sign":
            self.studio._open_build_control(self)
            self._refresh()
        elif action == "flash":
            if self._context().guardian_flash_handoff_ready:
                self.studio._open_guardian_manifest_review(self)
            else:
                # Never leave a visible action as a no-op. Until the mode handoff
                # exists this opens the evidence resolver, not a phone write.
                self.studio._open_build_control(self)
            self._refresh()
        else:
            self.failure = GuidedFailure(
                "This guided action is unavailable",
                f"Genesis has no registered implementation for {action or 'this stage'}.",
                (
                    "Save and reopen the project so ROMVERSE can re-evaluate its evidence.",
                    "Report this stage name if it remains visible; ROMVERSE did not change the phone.",
                ),
            )
            self.status_text.setText(
                "Genesis stopped safely instead of leaving an inert action. No phone state changed."
            )
            self._render_stage()

    def _run_first_boot_check(self) -> None:
        project = self.studio.current_project
        if project is None:
            self.failure = self.engine.diagnose("No project loaded")
            self._refresh()
            return
        context = self._context()
        if not context.flash_complete:
            self.failure = GuidedFailure(
                "Guardian flash receipt required",
                "A read-only boot baseline cannot prove that this ROM was installed or that this is its first boot.",
                (
                    "Complete the exact Guardian write-manifest review and authorized flash first.",
                    "Keep any Boot Observatory baseline as comparison evidence; it does not advance Genesis.",
                ),
            )
            self._refresh()
            return
        if context.device is None:
            self.failure = self.engine.diagnose(
                "No exact Android device visible for boot observation"
            )
            self._refresh()
            return
        if context.device.state is not DeviceState.DEVICE:
            self.failure = self.engine.diagnose("ADB device is not authorized")
            self._refresh()
            return
        service = BootObservationService(self.studio.store, self.studio.pack_registry)
        existing = service.load(project.project_id)
        wait = service.next_sample_wait_seconds(existing)
        if wait:
            self.failure = self.engine.diagnose(
                f"Boot observation cooldown active. Reconnect or wait {wait} second(s) for a valid sample."
            )
            self._refresh()
            return
        try:
            receipt = service.observe(project.project_id, context.device)
        except (OSError, ProjectError) as exc:
            self.failure = self.engine.diagnose(str(exc))
            self._refresh()
            return
        self.failure = None
        self.status_text.setText(
            f"Boot evidence recorded  •  {receipt.status.value}  •  {receipt.diagnosis}"
        )
        self._refresh(select_current=True)
        if receipt.status is BootObservationStatus.STABLE:
            self.status_text.setText(
                "First-boot checks are stable and linked to the verified Guardian flash receipt. "
                "Genesis Sequence is ready to complete."
            )
            if self.autopilot_active:
                QTimer.singleShot(0, self._advance_autopilot)
        else:
            self.failure = GuidedFailure(
                "First-boot check incomplete",
                f"Boot status is currently {receipt.status.value}.",
                (
                    service.next_step(receipt),
                    "Keep the device connected and capture the next sample when prompted.",
                ),
            )
            self._refresh()

    def _run_operations(self, operations: list[str]) -> None:
        if not operations:
            self._refresh()
            return
        self.operation_queue = operations
        self._start_next_operation()

    def _start_next_operation(self) -> None:
        if not self.operation_queue:
            self.active_operation = ""
            self._save_state()
            self._refresh(select_current=True)
            return
        operation = self.operation_queue.pop(0)
        self.active_operation = operation
        self.studio._start_worker(operation)
        if self.studio.worker is None:
            self.active_operation = ""
            self.operation_queue.clear()
            self.failure = self.engine.diagnose(
                "The requested operation could not start because a prerequisite is missing"
            )
            self._refresh()
        else:
            self._render_stage()

    def _refresh_if_idle(self) -> None:
        if self.studio.worker is None:
            self._refresh()
        else:
            self._render_stage()

    def _resolve_required_tools(self, required: tuple[str, ...], *, purpose: str) -> bool:
        required = tuple(dict.fromkeys(required))
        status_by_name = {item.name: item for item in self.studio.tool_statuses}
        missing = tuple(
            name
            for name in required
            if name not in status_by_name or not status_by_name[name].available
        )
        if not missing:
            return True

        resolved = self.studio._resolve_required_tools(
            required,
            purpose=purpose,
            title="ROMVERSE • Resolve Genesis requirements",
            success_message="Genesis requirements freshly verified.",
            parent=self,
        )
        refreshed = {item.name: item for item in self.studio.tool_statuses}
        remaining = tuple(
            name for name in required if name not in refreshed or not refreshed[name].available
        )
        if resolved and not remaining:
            self.failure = None
            return True
        detail = self.studio.operation_status.text().strip()
        self.failure = GuidedFailure(
            "Forge Arsenal still needs attention",
            detail
            or "ROMVERSE rescanned the computer, but not every required read-only tool is verified.",
            (
                f"Still required: {', '.join(remaining)}.",
                "Choose Install and verify requirements, approve any visible operating-system prompt, then retry.",
                "ROMVERSE will not claim an empty app scan or continue with guessed tool availability.",
            ),
        )
        self._refresh(select_current=True)
        return False

    @Slot(bool, str)
    def _device_scan_finished(self, succeeded: bool, message: str) -> None:
        if self.active_operation != "device-scan":
            return
        self.active_operation = ""
        if succeeded:
            self.process_progress.finish()
        else:
            self.process_progress.stop()
        self.process_frame.setVisible(False)
        if not succeeded:
            self.failure = self.engine.diagnose(message)
            self._refresh(select_current=True)
            if self.autopilot_active:
                self._finish_autopilot(
                    "ROMVERSE could not refresh the Android connection. The stale device result was cleared safely."
                )
            return

        project = self.studio.current_project
        if project is not None:
            self.studio._refresh_device_dna(project)
        self.failure = None
        self._refresh(select_current=True)
        current = self.assessments[self.selected_index]
        if current.stage.stage_id == "device":
            blockers = " ".join(current.blockers).strip()
            if self.autopilot_active:
                self._finish_autopilot(
                    blockers
                    or "The fresh scan completed, but exact device evidence still needs attention."
                )
            else:
                self.status_text.setText(
                    message or "Fresh device scan completed; review the evidence shown here."
                )
            return
        if self.autopilot_active:
            QTimer.singleShot(0, self._advance_autopilot)

    @Slot(str)
    def _operation_started(self, operation: str) -> None:
        self.active_operation = operation
        self.process_label.setText(f"{_operation_label(operation)}  •  please wait")
        self.process_progress.begin()
        self.process_frame.setVisible(True)
        self._render_stage()

    @Slot(str, int)
    def _operation_progress(self, operation: str, value: int) -> None:
        if operation != self.active_operation:
            return
        self.process_progress.report(value)
        self.process_label.setText(f"{_operation_label(operation)}  •  {value}%")
        store = self._live_console_store()
        if store is not None and self.live_mission_id:
            completed = sum(item.status is GuidedStageStatus.COMPLETE for item in self.assessments)
            progress = min(99, round(((completed + (value / 100)) * 100) / len(STAGES)))
            progress = max(progress, self.live_mission_progress)
            with suppress(LiveConsoleStoreError):
                store.progress(
                    self.live_mission_id,
                    progress,
                    summary=f"{_operation_label(operation)} is {value}% complete.",
                    explanation="ROMVERSE is running the current safe local Genesis operation against the isolated project workspace.",
                    next_action="Keep ROMVERSE open; the next stage will be selected from verified evidence.",
                )
                self.live_mission_progress = progress

    @Slot(str, object)
    def _operation_completed(self, operation: str, result: object) -> None:
        if operation != self.active_operation or not self.studio.is_validated_completion(
            operation, result
        ):
            self._operation_failed(
                operation,
                "Genesis rejected unexpected or stale ROM Studio terminal evidence",
            )
            return
        self.active_operation = ""
        self.process_progress.finish()
        self.process_frame.setVisible(False)
        if hasattr(result, "valid") and not result.valid:
            message = str(getattr(result, "status", "Verification did not pass"))
            self.operation_queue.clear()
            self.failure = self.engine.diagnose(message)
            self.state = replace(self.state, last_error=f"{operation}: {message}")
            self._save_state()
            self._refresh()
            return
        self.failure = None
        self.state = replace(self.state, last_error="")
        if operation in {"execute-recipe", "preview-recipe"}:
            self.state = replace(self.state, recipe_validated=True, last_error="")
        elif operation == "verify-plan" and getattr(result, "valid", False):
            self.state = replace(self.state, build_plan_verified=True, last_error="")
        self._save_state()
        if self.operation_queue:
            QTimer.singleShot(0, self._start_next_operation)
        else:
            self._refresh(select_current=True)
            if self.autopilot_active:
                QTimer.singleShot(0, self._advance_autopilot)

    @Slot(str, str)
    def _operation_failed(self, operation: str, message: str) -> None:
        self.active_operation = ""
        self.process_progress.stop()
        self.process_frame.setVisible(False)
        self.operation_queue.clear()
        self.failure = self.engine.diagnose(message)
        project_id = (
            self.studio.current_project.project_id
            if self.studio.current_project is not None
            else ""
        )
        if self.failure.safe_cleanup:
            self.engine.clean_partial_files(self.studio.store.workspace, project_id)
        self.state = replace(self.state, last_error=f"{operation}: {message}")
        self._save_state()
        self._pause_genesis_live(
            f"Genesis stopped safely during {_operation_label(operation)}: {message}"
        )
        self._refresh()
        if self.autopilot_active:
            self._finish_autopilot(
                "ROMVERSE stopped at this stage, explained the error, and preserved the verified earlier evidence."
            )

    @staticmethod
    def _stylesheet() -> str:
        return """
            QDialog { background: #02050A; color: #EEF4FF; }
            QFrame#MissionHeader { background: #040812; border-bottom: 1px solid #1C2E48; }
            QFrame#ProgressStrip { background: #060B14; border-bottom: 1px solid #15243B; }
            QLabel#MissionEyebrow, QLabel#CardHeading {
                color: #40DDF2; font-size: 11px; font-weight: 800; letter-spacing: 2px;
            }
            QLabel#MissionTitle { color: #FFFFFF; font-size: 22px; font-weight: 800; }
            QLabel#GuardianBadge {
                color: #42F0AD; background: #071A18; border: 1px solid #147A5B;
                border-radius: 12px; padding: 8px 13px; font-weight: 800;
            }
            QLabel#MissionMuted { color: #91A2C4; font-size: 11px; font-weight: 700; }
            QProgressBar { background: #0C1321; border: 1px solid #1C2D48; border-radius: 3px; }
            QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #9C43F2, stop:.52 #526EFF, stop:1 #21D9EE); border-radius: 3px; }
            QScrollArea#StageRail { background: #03070D; border: 0; border-right: 1px solid #17263D; }
            QScrollArea#StageRail > QWidget > QWidget { background: #03070D; }
            QScrollArea#MissionMain { background: #02050A; border: 0; }
            QScrollArea#MissionMain > QWidget > QWidget { background: #02050A; }
            QScrollBar:vertical {
                background: #050A12; width: 8px; margin: 2px; border: 0;
            }
            QScrollBar::handle:vertical {
                background: #334866; min-height: 34px; border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover { background: #576F98; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
            QPushButton {
                color: #C9D5EE; background: #09101C; border: 1px solid #243653;
                border-radius: 9px; padding: 9px 14px; font-weight: 700;
            }
            QPushButton:hover { color: #FFFFFF; border-color: #5978B5; background: #0D1727; }
            QPushButton:disabled { color: #53617A; border-color: #182338; background: #070B13; }
            QPushButton[stageStatus="complete"] { color: #66EFB7; border-color: #174D43; }
            QPushButton[stageStatus="ready"] { color: #E9D9FF; border-color: #6940A2; }
            QPushButton[stageStatus="attention"] { color: #FFD07A; border-color: #6A4C1E; }
            QPushButton[stageStatus="future"], QPushButton[stageStatus="locked"] { color: #74829D; }
            QPushButton:checked {
                color: #FFFFFF; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #24113A, stop:1 #0B1A32); border: 1px solid #A149EC;
            }
            QLabel#StageTitle { color: #FFFFFF; font-size: 28px; font-weight: 800; }
            QLabel#MissionBody { color: #BAC7DE; font-size: 14px; }
            QFrame#StatusBanner {
                background: #07131D; border: 1px solid #1C5061; border-radius: 10px;
            }
            QFrame#StatusBanner[stageStatus="complete"] { border-color: #177657; background: #061712; }
            QFrame#StatusBanner[stageStatus="attention"] { border-color: #7A5720; background: #171207; }
            QFrame#StatusBanner[stageStatus="future"] { border-color: #58377B; background: #11091B; }
            QFrame#ProcessCard {
                background: #07111E; border: 1px solid #29486A; border-radius: 10px;
            }
            QLabel#StatusIcon { color: #42DFF0; font-size: 18px; }
            QLabel#StatusText { color: #D9E5F7; font-weight: 700; }
            QFrame#MissionCard {
                background: #050A12; border: 1px solid #1B2B43; border-radius: 12px;
            }
            QLabel#CardBody { color: #AEBBD2; font-size: 13px; }
            QFrame#DiagnosticCard { background: #170A11; border: 1px solid #8C304D; border-radius: 12px; }
            QLabel#DiagnosticTitle { color: #FF789A; font-size: 17px; font-weight: 800; }
            QFrame#MissionFooter { background: #040812; border-top: 1px solid #1C2E48; }
            QPushButton#MissionAction {
                color: #061019; background: #39D9EF; border-color: #7DEFFF; padding: 11px 18px;
            }
            QPushButton#MissionAction:hover { background: #79EAF7; }
            QPushButton#MissionNext {
                color: #04140F; background: #35D69C; border-color: #71F1BE; padding: 11px 18px;
            }
            QPushButton#MissionNext:disabled { color: #506078; background: #09101A; border-color: #1D2B40; }
            QPushButton#SecondaryAction { color: #DFC2FF; border-color: #6E3D9B; }
        """


def _operation_label(operation: str) -> str:
    return {
        "import": "Copying and hashing protected firmware",
        "verify": "Verifying protected-source integrity",
        "inspect": "Inspecting bounded firmware metadata",
        "working-copy": "Creating the isolated working baseline",
        "snapshot": "Creating a verified Time Machine snapshot",
        "extract": "Extracting the contained working tree",
        "plan": "Generating the deterministic build plan",
        "verify-plan": "Verifying the build plan against the working tree",
        "preview-recipe": "Previewing every Recipe target",
        "execute-recipe": "Applying and verifying the approved Recipe",
    }.get(operation, operation.replace("-", " ").capitalize())
