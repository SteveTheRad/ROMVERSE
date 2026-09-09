from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from PySide6.QtCore import QEasingCurve, QObject, QPropertyAnimation, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
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
    VERIFIED_ROM_INSTALLATION_ACTION,
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
            GuidedStageStatus.FUTURE: "Optional install phase",
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


@dataclass(frozen=True, slots=True)
class MissionPhase:
    phase_id: str
    label: str
    stage_ids: tuple[str, ...]


MISSION_PHASES = (
    MissionPhase("scan", "SCAN", ("project", "firmware", "provenance", "workspace")),
    MissionPhase("match", "MATCH", ("device",)),
    MissionPhase(
        "build",
        "BUILD",
        ("customize", "validate_recipe", "debloat", "root_choice", "toolchain", "build_plan"),
    ),
    MissionPhase("verify", "VERIFY", ("build_sign",)),
    MissionPhase("backup", "BACKUP", ("recovery",)),
    MissionPhase("flash", "FLASH", ("flash",)),
    MissionPhase("diagnose", "DIAGNOSE", ("first_boot",)),
)

_PHASE_BY_STAGE = {stage_id: phase for phase in MISSION_PHASES for stage_id in phase.stage_ids}


class PhaseButton(QPushButton):
    def __init__(self, phase: MissionPhase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.phase = phase
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(48)
        self.setText(phase.label)
        self.setProperty("phaseStatus", GuidedStageStatus.LOCKED.value)

    def update_status(self, status: GuidedStageStatus, *, current: bool) -> None:
        symbols = {
            GuidedStageStatus.COMPLETE: "✓",
            GuidedStageStatus.READY: "◆",
            GuidedStageStatus.ATTENTION: "!",
            GuidedStageStatus.LOCKED: "·",
            GuidedStageStatus.FUTURE: "◇",
        }
        self.setText(f"{symbols[status]}  {self.phase.label}")
        self.setChecked(current)
        self.setProperty("phaseStatus", status.value)
        self.style().unpolish(self)
        self.style().polish(self)


class GuidedBuildMission(QDialog):
    """Evidence-driven ROM journey with explicit Guardian boundaries."""

    def __init__(self, studio: RomStudio, *, start_new_project: bool = False) -> None:
        super().__init__(studio)
        self.studio = studio
        self._closing = False
        self._start_new_project = bool(start_new_project)
        self.engine = GuidedMissionEngine()
        self.state = self._load_state()
        self.assessments: tuple[GuidedAssessment, ...] = ()
        self.selected_index = 0
        self.operation_queue: list[str] = []
        self.active_operation = ""
        self.failure: GuidedFailure | None = None
        self.stage_buttons: list[StageButton] = []
        self.phase_buttons: list[PhaseButton] = []
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
        self._details_user_choice: bool | None = None
        self._supporting_compact: bool | None = None
        self._automatic_source_recovery_key: tuple[str, str, str, int, int] | None = None

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
        header_layout.setSpacing(10)
        heading = QVBoxLayout()
        eyebrow = QLabel("ROM STUDIO  /  GENESIS SEQUENCE")
        eyebrow.setObjectName("MissionEyebrow")
        title = QLabel("Your guided journey from firmware to first boot")
        title.setObjectName("MissionTitle")
        heading.addWidget(eyebrow)
        heading.addWidget(title)
        header_layout.addLayout(heading, 1)
        self.mode_badge = QLabel("GUIDED  •  ARCANA")
        self.mode_badge.setObjectName("ModeBadge")
        self.mode_badge.setToolTip(
            "Genesis keeps the current task prominent and reveals supporting evidence on demand."
        )
        header_layout.addWidget(self.mode_badge)
        self.guardian_badge = QLabel("◆  CORE CHECKS ACTIVE")
        self.guardian_badge.setObjectName("GuardianBadge")
        self.guardian_badge.setToolTip(
            "Target identity, artifact integrity, command validity, and bootloader-relock prohibitions remain active."
        )
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

        phase_strip = QFrame()
        phase_strip.setObjectName("PhaseStrip")
        phase_layout = QHBoxLayout(phase_strip)
        phase_layout.setContentsMargins(24, 10, 24, 10)
        phase_layout.setSpacing(7)
        for phase in MISSION_PHASES:
            button = PhaseButton(phase)
            button.clicked.connect(
                lambda _checked=False, phase_id=phase.phase_id: self._select_phase(phase_id)
            )
            phase_layout.addWidget(button, 1)
            self.phase_buttons.append(button)
        root.addWidget(phase_strip)

        self.identity_deck = QFrame()
        self.identity_deck.setObjectName("IdentityDeck")
        identity_layout = QHBoxLayout(self.identity_deck)
        identity_layout.setContentsMargins(24, 12, 24, 12)
        identity_layout.setSpacing(10)
        self.firmware_identity_card, self.firmware_identity_title, self.firmware_identity_detail = (
            self._identity_card("FIRMWARE SOURCE")
        )
        self.compatibility_card, self.compatibility_title, self.compatibility_detail = (
            self._identity_card("COMPATIBILITY VERDICT")
        )
        self.device_identity_card, self.device_identity_title, self.device_identity_detail = (
            self._identity_card("LIVE DEVICE")
        )
        self.compatibility_card.setObjectName("CompatibilityCard")
        identity_layout.addWidget(self.firmware_identity_card, 1)
        identity_layout.addWidget(self.compatibility_card, 1)
        identity_layout.addWidget(self.device_identity_card, 1)
        root.addWidget(self.identity_deck)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        rail_scroll = QScrollArea()
        rail_scroll.setObjectName("StageRail")
        rail_scroll.setWidgetResizable(True)
        rail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rail_scroll.setFixedWidth(285)
        self.rail_scroll = rail_scroll
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
        self.main_layout = main

        self.task_card = QFrame()
        self.task_card.setObjectName("MissionTaskCard")
        task_layout = QVBoxLayout(self.task_card)
        task_layout.setContentsMargins(22, 19, 22, 18)
        task_layout.setSpacing(8)
        self.step_label = QLabel()
        self.step_label.setObjectName("MissionEyebrow")
        self.stage_title = QLabel()
        self.stage_title.setObjectName("StageTitle")
        self.stage_title.setWordWrap(True)
        self.stage_detail = QLabel()
        self.stage_detail.setObjectName("MissionBody")
        self.stage_detail.setWordWrap(True)
        task_layout.addWidget(self.step_label)
        task_layout.addWidget(self.stage_title)
        task_layout.addWidget(self.stage_detail)

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
        task_layout.addWidget(self.status_banner)
        main.addWidget(self.task_card)

        self.task_effect = QGraphicsOpacityEffect(self.task_card)
        self.task_effect.setOpacity(1.0)
        self.task_card.setGraphicsEffect(self.task_effect)
        self.stage_transition = QPropertyAnimation(self.task_effect, b"opacity", self)
        self.stage_transition.setDuration(170)
        self.stage_transition.setStartValue(0.72)
        self.stage_transition.setEndValue(1.0)
        self.stage_transition.setEasingCurve(QEasingCurve.Type.OutCubic)

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

        supporting_header = QFrame()
        supporting_header.setObjectName("SupportingHeader")
        supporting_header_layout = QHBoxLayout(supporting_header)
        supporting_header_layout.setContentsMargins(14, 8, 10, 8)
        supporting_header_layout.setSpacing(10)
        supporting_copy = QVBoxLayout()
        supporting_copy.setSpacing(1)
        supporting_title = QLabel("SUPPORTING EVIDENCE")
        supporting_title.setObjectName("CardHeading")
        self.supporting_summary = QLabel()
        self.supporting_summary.setObjectName("SupportingSummary")
        self.supporting_summary.setWordWrap(True)
        supporting_copy.addWidget(supporting_title)
        supporting_copy.addWidget(self.supporting_summary)
        supporting_header_layout.addLayout(supporting_copy, 1)
        self.details_button = QPushButton("Show evidence & guidance")
        self.details_button.setObjectName("DetailToggle")
        self.details_button.setCheckable(True)
        self.details_button.setAccessibleName("Show Genesis supporting evidence and guidance")
        self.details_button.toggled.connect(self._toggle_supporting_details)
        supporting_header_layout.addWidget(self.details_button)
        main.addWidget(supporting_header)

        self.supporting_panel = QFrame()
        self.supporting_panel.setObjectName("SupportingPanel")
        supporting_panel_layout = QVBoxLayout(self.supporting_panel)
        supporting_panel_layout.setContentsMargins(0, 0, 0, 0)
        supporting_panel_layout.setSpacing(0)
        self.supporting_grid = QGridLayout()
        self.supporting_grid.setContentsMargins(0, 0, 0, 0)
        self.supporting_grid.setHorizontalSpacing(12)
        self.supporting_grid.setVerticalSpacing(12)
        self.evidence_card, self.evidence = self._card("WHAT ROMVERSE FOUND")
        self.recommendation_card, self.recommendation = self._card("ROMVERSE GUIDANCE")
        self.supporting_grid.addWidget(self.evidence_card, 0, 0)
        self.supporting_grid.addWidget(self.recommendation_card, 0, 1)
        self.supporting_grid.setColumnStretch(0, 1)
        self.supporting_grid.setColumnStretch(1, 1)
        supporting_panel_layout.addLayout(self.supporting_grid)
        main.addWidget(self.supporting_panel)

        next_card, self.next_outcome = self._card("WHAT HAPPENS NEXT")
        next_card.setObjectName("OutcomeCard")
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
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(24, 11, 24, 13)
        footer_layout.setSpacing(8)
        utility_row = QHBoxLayout()
        utility_row.setSpacing(8)
        self.back_button = QPushButton("←  Back")
        self.back_button.clicked.connect(self._back)
        self.learn_button = QPushButton("Learn this stage")
        self.learn_button.setObjectName("SecondaryAction")
        self.learn_button.setToolTip(
            "Save Genesis progress and open the verified ROMVERSE Archives guide for this stage."
        )
        self.learn_button.clicked.connect(self._open_stage_learning)
        self.task_list_button = QPushButton("Show detailed tasks")
        self.task_list_button.setObjectName("SecondaryAction")
        self.task_list_button.setCheckable(True)
        self.task_list_button.toggled.connect(self._toggle_task_list)
        self.save_button = QPushButton("Save && exit")
        self.save_button.clicked.connect(self._save_or_finish)
        self.skip_button = QPushButton("Keep verified base unchanged • Recommended")
        self.skip_button.setObjectName("SecondaryAction")
        self.skip_button.clicked.connect(self._secondary_action)
        self.action_button = QPushButton()
        self.action_button.setObjectName("MissionAction")
        self.action_button.clicked.connect(self._run_stage)
        self.auto_button = QPushButton("Auto-resolve && continue")
        self.auto_button.setObjectName("MissionAutopilot")
        self.auto_button.setToolTip(
            "Run consecutive safe local stages automatically. ROMVERSE pauses for firmware "
            "selection, customization choices, device authorization, backups, wipes, and final consent."
        )
        self.auto_button.clicked.connect(self._start_autopilot)
        self.next_button = QPushButton("Next  →")
        self.next_button.setObjectName("MissionNext")
        self.next_button.clicked.connect(self._next)
        utility_row.addWidget(self.back_button)
        utility_row.addWidget(self.learn_button)
        utility_row.addWidget(self.task_list_button)
        utility_row.addWidget(self.save_button)
        utility_row.addStretch()
        utility_row.addWidget(self.auto_button)
        footer_layout.addLayout(utility_row)

        primary_row = QHBoxLayout()
        primary_row.setSpacing(8)
        primary_copy = QVBoxLayout()
        primary_copy.setSpacing(0)
        primary_label = QLabel("NEXT SAFE ACTION")
        primary_label.setObjectName("ActionEyebrow")
        self.action_context = QLabel()
        self.action_context.setObjectName("ActionContext")
        self.action_context.setWordWrap(True)
        primary_copy.addWidget(primary_label)
        primary_copy.addWidget(self.action_context)
        primary_row.addLayout(primary_copy, 1)
        primary_row.addWidget(self.skip_button)
        primary_row.addWidget(self.action_button)
        primary_row.addWidget(self.next_button)
        footer_layout.addLayout(primary_row)
        root.addWidget(footer)

        self.studio.operation_started.connect(self._operation_started)
        self.studio.operation_progress.connect(self._operation_progress)
        self.studio.operation_completed.connect(self._operation_completed)
        self.studio.operation_failed.connect(self._operation_failed)
        self.studio.device_context_changed.connect(self._root_device_context_changed)
        self.studio.device_scan_finished.connect(self._device_scan_finished)
        expert = self.studio.app_settings.experience_mode.value == "expert"
        self.task_list_button.setChecked(expert)
        self._toggle_task_list(expert)
        self._refresh(select_current=True)
        self._apply_responsive_layout()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Re-read the sealed project outcome on entry. An interrupted installation
        # should flow straight into read-only diagnosis instead of leaving Guided
        # users to find and press a second Recovery action.
        self._refresh(select_current=True)
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
        self._apply_responsive_layout()
        self._schedule_automatic_source_recovery()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def closeEvent(self, event) -> None:
        self._closing = True
        self.autopilot_active = False
        self._save_state()
        self._pause_genesis_live("Genesis Sequence was closed and saved for later.")
        super().closeEvent(event)

    def reject(self) -> None:
        if not self._closing:
            self._closing = True
            self.autopilot_active = False
            self._save_state()
            self._pause_genesis_live("Genesis Sequence was closed and saved for later.")
        super().reject()

    def accept(self) -> None:
        if not self._save_state():
            self._render_stage()
            return
        self._closing = True
        self.autopilot_active = False
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
        project = None if self._start_new_project else self.studio.current_project
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

    def _identity_card(self, label: str) -> tuple[QFrame, QLabel, QLabel]:
        card = QFrame()
        card.setObjectName("IdentityCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 11, 15, 11)
        layout.setSpacing(3)
        eyebrow = QLabel(label)
        eyebrow.setObjectName("IdentityEyebrow")
        title = QLabel()
        title.setObjectName("IdentityTitle")
        title.setWordWrap(True)
        detail = QLabel()
        detail.setObjectName("IdentityDetail")
        detail.setWordWrap(True)
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(detail)
        return card, title, detail

    def _toggle_task_list(self, visible: bool) -> None:
        self.rail_scroll.setVisible(bool(visible))
        self.task_list_button.blockSignals(True)
        self.task_list_button.setChecked(bool(visible))
        self.task_list_button.setText("Hide detailed tasks" if visible else "Show detailed tasks")
        self.task_list_button.blockSignals(False)

    def _apply_responsive_layout(self) -> None:
        """Keep the mission readable without hiding controls at the minimum window size."""

        if not hasattr(self, "supporting_grid"):
            return
        compact = self.width() < 1120
        if compact == self._supporting_compact:
            return
        self._supporting_compact = compact
        self.rail_scroll.setFixedWidth(238 if compact else 285)
        for button in self.stage_buttons:
            button.setMinimumHeight(50 if compact else 58)
        self.main_layout.setContentsMargins(
            22 if compact else 34,
            20 if compact else 28,
            22 if compact else 34,
            20 if compact else 24,
        )
        self.supporting_grid.removeWidget(self.evidence_card)
        self.supporting_grid.removeWidget(self.recommendation_card)
        if compact:
            self.supporting_grid.addWidget(self.evidence_card, 0, 0)
            self.supporting_grid.addWidget(self.recommendation_card, 1, 0)
            self.supporting_grid.setColumnStretch(0, 1)
            self.supporting_grid.setColumnStretch(1, 0)
        else:
            self.supporting_grid.addWidget(self.evidence_card, 0, 0)
            self.supporting_grid.addWidget(self.recommendation_card, 0, 1)
            self.supporting_grid.setColumnStretch(0, 1)
            self.supporting_grid.setColumnStretch(1, 1)

    def _toggle_supporting_details(self, visible: bool) -> None:
        self._details_user_choice = bool(visible)
        self._set_supporting_details(bool(visible))

    def _set_supporting_details(self, visible: bool) -> None:
        self.supporting_panel.setVisible(visible)
        self.details_button.blockSignals(True)
        self.details_button.setChecked(visible)
        self.details_button.setText(
            "Hide evidence & guidance" if visible else "Show evidence & guidance"
        )
        self.details_button.setAccessibleName(
            ("Hide" if visible else "Show") + " Genesis supporting evidence and guidance"
        )
        self.details_button.blockSignals(False)

    def _animate_stage_transition(self) -> None:
        self.stage_transition.stop()
        if self.studio.app_settings.reduced_motion or not self.isVisible():
            self.task_effect.setOpacity(1.0)
            return
        self.stage_transition.start()

    def _load_state(self) -> GuidedMissionState:
        if self._start_new_project:
            return GuidedMissionState()
        if self.studio.current_project is None:
            return GuidedMissionState()
        return GuidedMissionStore(
            self.studio.store.projects_root / self.studio.current_project.project_id
        ).load()

    def _save_state(self) -> bool:
        if self._start_new_project:
            return True
        if self.studio.current_project is None:
            # The initial projectless stage has no durable progress to lose. Save & exit
            # must still perform its documented close action instead of becoming inert.
            return self.selected_index == 0
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
        if self._start_new_project:
            return GuidedContext(
                device=self.studio.devices[0] if len(self.studio.devices) == 1 else None,
                observed_devices=tuple(self.studio.observed_devices),
                device_scan_error=self.studio.device_scan_error,
                device_pack_id=self.studio.suggested_pack_id,
            )
        return self.studio.guided_context(self.state)

    def _refresh(self, select_current: bool = False) -> None:
        if self._closing:
            return
        current_project_id = (
            self.studio.current_project.project_id
            if self.studio.current_project is not None
            else ""
        )
        if self.root_preview_project_id and self.root_preview_project_id != current_project_id:
            self._reset_root_entry_preview()
        self._display_context = self._context()
        self.assessments = self.engine.assess(self._display_context)
        if select_current:
            # Resume at the first stage not supported by real evidence. This deliberately
            # outranks the last page viewed so a stale navigation choice cannot imply progress.
            self.selected_index = self.engine.current_index(self.assessments)
        complete = sum(item.status is GuidedStageStatus.COMPLETE for item in self.assessments)
        local_build_complete = all(
            item.status is GuidedStageStatus.COMPLETE for item in self.assessments[:13]
        )
        install_deferred = local_build_complete and not self.state.install_requested
        self.overall_progress.setValue(
            100 if install_deferred else self.engine.progress(self.assessments)
        )
        self.progress_copy.setText(
            "13 OF 13 LOCAL BUILD STAGES VERIFIED  •  2 OPTIONAL INSTALL STAGES DEFERRED"
            if install_deferred
            else f"{complete} OF {len(self.assessments)} STAGES VERIFIED"
        )
        for index, (button, assessment) in enumerate(
            zip(self.stage_buttons, self.assessments, strict=True)
        ):
            button.update_assessment(assessment)
            button.setChecked(index == self.selected_index)
        self._refresh_phases()
        self._render_identity_deck()
        self._sync_genesis_live()
        self._render_stage()
        if self.isVisible():
            self._schedule_automatic_source_recovery()

    def _phase_status(self, phase: MissionPhase) -> GuidedStageStatus:
        relevant = tuple(
            assessment
            for assessment in self.assessments
            if assessment.stage.stage_id in phase.stage_ids
        )
        if relevant and all(item.status is GuidedStageStatus.COMPLETE for item in relevant):
            return GuidedStageStatus.COMPLETE
        for status in (
            GuidedStageStatus.ATTENTION,
            GuidedStageStatus.READY,
            GuidedStageStatus.FUTURE,
            GuidedStageStatus.LOCKED,
        ):
            if any(item.status is status for item in relevant):
                return status
        return GuidedStageStatus.LOCKED

    def _refresh_phases(self) -> None:
        if not self.assessments:
            return
        selected_stage_id = self.assessments[self.selected_index].stage.stage_id
        selected_phase = _PHASE_BY_STAGE[selected_stage_id]
        for button in self.phase_buttons:
            status = self._phase_status(button.phase)
            button.update_status(status, current=button.phase is selected_phase)
            button.setToolTip(
                f"{button.phase.label.title()} phase  •  "
                f"{sum(stage.stage.stage_id in button.phase.stage_ids and stage.status is GuidedStageStatus.COMPLETE for stage in self.assessments)} "
                f"of {len(button.phase.stage_ids)} detailed tasks verified"
            )

    def _select_phase(self, phase_id: str) -> None:
        phase = next(item for item in MISSION_PHASES if item.phase_id == phase_id)
        indexes = tuple(
            index
            for index, assessment in enumerate(self.assessments)
            if assessment.stage.stage_id in phase.stage_ids
        )
        target = next(
            (
                index
                for index in indexes
                if self.assessments[index].status is not GuidedStageStatus.COMPLETE
            ),
            indexes[-1],
        )
        self._select_stage(target)

    def _render_identity_deck(self) -> None:
        project = None if self._start_new_project else self.studio.current_project
        device = self.studio.devices[0] if len(self.studio.devices) == 1 else None
        if project is None:
            self.firmware_identity_title.setText("No firmware selected")
            self.firmware_identity_detail.setText("Create a project to begin")
        elif project.original is None:
            self.firmware_identity_title.setText("Awaiting firmware")
            self.firmware_identity_detail.setText(project.name)
        else:
            self.firmware_identity_title.setText(project.original.original_name)
            self.firmware_identity_detail.setText(
                f"Protected  •  SHA-256 {project.original.sha256[:12]}…"
            )

        if device is None:
            self.device_identity_title.setText(
                "Choose one device" if self.studio.observed_devices else "No device connected"
            )
            self.device_identity_detail.setText(
                f"{len(self.studio.observed_devices)} detected"
                if self.studio.observed_devices
                else "Connect by USB to scan Device DNA"
            )
        else:
            self.device_identity_title.setText(device.display_name)
            current_build = device.rom_display or device.build_id or "Build unconfirmed"
            self.device_identity_detail.setText(
                "SIMULATION ONLY • NOT HARDWARE VERIFIED"
                if device.is_simulated
                else f"{device.codename or 'Codename unconfirmed'}  •  {current_build}"
            )

        verdict = (
            "" if self._start_new_project else self.studio.upgrade_passport_status.text().strip()
        )
        self.compatibility_title.setText(verdict or "AWAITING COMPARISON")
        if project is not None and project.original is not None and device is not None:
            self.compatibility_detail.setText("Firmware ↔ Device DNA")
        elif project is not None and project.original is not None:
            self.compatibility_detail.setText("Firmware ready  •  device needed")
        else:
            self.compatibility_detail.setText("Add firmware and a live device")
        state = (
            "attention"
            if self._start_new_project
            else self.studio.upgrade_passport.property("upgradeState") or "attention"
        )
        self.compatibility_card.setProperty("upgradeState", state)
        self.compatibility_title.setProperty("upgradeState", state)
        for widget in (self.compatibility_card, self.compatibility_title):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

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

    def _saved_toolchain_review_available(self, assessment: GuidedAssessment) -> bool:
        """Keep a saved host-only tool review usable after live-device context expires.

        This does not complete or bypass Device DNA. It permits only the non-device-changing
        stage-10 verification/review when every surrounding local stage already has durable
        evidence and the integrity-checked mission was explicitly saved at Toolchain.
        """

        if (
            self._start_new_project
            or self.studio.current_project is None
            or self.state.selected_stage != "toolchain"
            or assessment.stage.stage_id != "toolchain"
            or assessment.status is not GuidedStageStatus.LOCKED
        ):
            return False
        durable_local_indexes = (0, 1, 2, 3, 5, 6, 7, 8)
        return all(
            self.assessments[index].status is GuidedStageStatus.COMPLETE
            for index in durable_local_indexes
        )

    def _render_stage(self) -> None:
        assessment = self.assessments[self.selected_index]
        stage = assessment.stage
        saved_toolchain_review = self._saved_toolchain_review_available(assessment)
        if stage.stage_id == "root_choice" and assessment.status is not GuidedStageStatus.LOCKED:
            self._ensure_root_entry_preview()
        status_label = assessment.status.value.upper()
        expert = self.studio.app_settings.experience_mode.value == "expert"
        self.mode_badge.setText("ARCHITECT  •  DEEP VIEW" if expert else "GUIDED  •  ARCANA")
        phase = _PHASE_BY_STAGE[stage.stage_id]
        self.step_label.setText(
            f"CURRENT PHASE  •  {phase.label}  /  TASK {stage.number:02d} OF {len(STAGES):02d}"
        )
        self.stage_title.setText(stage.title)
        self.stage_detail.setText(stage.explanation)
        self.evidence.setText(
            "\n".join(f"•  {item}" for item in assessment.evidence)
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
        evidence_count = len(assessment.evidence)
        blocker_count = len(assessment.blockers)
        self.supporting_summary.setText(
            f"{evidence_count} evidence item{'s' if evidence_count != 1 else ''}"
            + (
                f"  •  {blocker_count} item{'s' if blocker_count != 1 else ''} need attention"
                if blocker_count
                else "  •  no reported blocker"
            )
        )
        if self._details_user_choice is None:
            self._set_supporting_details(
                assessment.status
                in {
                    GuidedStageStatus.ATTENTION,
                    GuidedStageStatus.LOCKED,
                    GuidedStageStatus.FUTURE,
                }
                or self.failure is not None
                or expert
            )

        status_copy = {
            GuidedStageStatus.COMPLETE: "Verified — this stage is backed by project evidence.",
            GuidedStageStatus.READY: "Ready — ROMVERSE can guide this step now.",
            GuidedStageStatus.ATTENTION: "Needs attention — follow the recommendation before continuing.",
            GuidedStageStatus.LOCKED: "Locked — complete the earlier highlighted stage first.",
            GuidedStageStatus.FUTURE: (
                "Local ROM build complete — phone installation is optional and has not been "
                "requested. You can finish here without weakening Guardian."
                if stage.stage_id == "flash"
                else "Optional post-install verification is deferred. Separate Android boot "
                "checks are available through the local image workflow."
            ),
        }[assessment.status]
        if saved_toolchain_review:
            status_copy = (
                "Saved host-only tool review available. The prior live-device context has expired, "
                "so Device DNA remains incomplete for this session and grants no device or "
                "execution authority. Tool versions may still be reviewed safely."
            )
        local_outcome = getattr(self, "_display_context", GuidedContext())
        if stage.stage_id in {"flash", "first_boot"} and local_outcome.source_installation_state:
            if self._source_installation_needs_diagnosis(local_outcome):
                status_copy = (
                    f"Recorded installation needs diagnosis: "
                    f"{local_outcome.source_installation_state}. "
                    f"{local_outcome.source_installation_summary} "
                    "ROMVERSE will use the sealed action ledger and freshly scanned phone state; "
                    "it will not repeat an uncertain write."
                )
            else:
                status_copy = (
                    f"Recorded installation: {local_outcome.source_installation_state}. "
                    f"{local_outcome.source_installation_summary} "
                    f"Historical Android boot: "
                    f"{local_outcome.source_installation_boot_status or 'unverified'}. "
                    "Review results or observe boot without repeating installation. "
                    "Individual phone features still need separate tests."
                )
        elif (
            stage.stage_id == "flash"
            and local_outcome.local_image_state
            and not local_outcome.flash_complete
        ):
            status_copy = (
                f"Local image operation: {local_outcome.local_image_state}. "
                f"{local_outcome.local_image_summary} "
                "This is a local subset result, not full-ROM or production certification. "
                "Review it before deciding whether any further operation is needed."
            )
        elif (
            stage.stage_id == "first_boot"
            and local_outcome.local_image_state
            and not local_outcome.first_boot_verified
        ):
            status_copy = (
                "A local image outcome is recorded. Open the separate Android boot check to "
                "review reconnect and boot observations. Full-ROM, image readback and subsystem "
                "verification remain separate; this stage has not been certified complete."
            )
        self.status_text.setText(status_copy)
        self.status_icon.setText(
            {
                GuidedStageStatus.COMPLETE: "✓",
                GuidedStageStatus.READY: "◆",
                GuidedStageStatus.ATTENTION: "!",
                GuidedStageStatus.LOCKED: "•",
                GuidedStageStatus.FUTURE: "◇",
            }[assessment.status]
        )
        self.status_icon.setProperty("stageStatus", assessment.status.value)
        self.status_icon.style().unpolish(self.status_icon)
        self.status_icon.style().polish(self.status_icon)
        self.status_text.setAccessibleName(f"Stage status {status_label}: {status_copy}")
        self.status_banner.setProperty("stageStatus", assessment.status.value)
        self.status_banner.style().unpolish(self.status_banner)
        self.status_banner.style().polish(self.status_banner)
        self.task_card.setProperty("stageStatus", assessment.status.value)
        self.task_card.style().unpolish(self.task_card)
        self.task_card.style().polish(self.task_card)

        busy = bool(self.studio.worker or self.active_operation)
        self.action_button.setText("Processing stage …" if busy else stage.action_label)
        if not busy and stage.stage_id == "flash" and not self.state.install_requested:
            self.action_button.setText("Continue to optional flash setup")
        elif not busy and stage.stage_id == "flash":
            self.action_button.setText(VERIFIED_ROM_INSTALLATION_ACTION)
        if not busy and stage.stage_id == "flash" and local_outcome.local_image_state:
            self.action_button.setText("Continue local image workflow…")
        local_boot_available = bool(
            stage.stage_id == "first_boot" and local_outcome.local_image_state and not busy
        )
        if local_boot_available:
            self.action_button.setText("Review separate Android boot check…")
        source_result_available = bool(
            stage.stage_id in {"flash", "first_boot"}
            and local_outcome.source_installation_state
            and not busy
        )
        source_recovery_available = bool(
            source_result_available and self._source_installation_needs_diagnosis(local_outcome)
        )
        if source_result_available:
            self.action_button.setText(
                "Diagnose interrupted installation…"
                if source_recovery_available
                else "Review installation and boot results…"
            )
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
            or local_boot_available
            or source_result_available
            or (saved_toolchain_review and not busy)
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
        action_is_primary = self.action_button.isEnabled() and (
            saved_toolchain_review
            or assessment.status
            not in {
                GuidedStageStatus.COMPLETE,
                GuidedStageStatus.LOCKED,
            }
        )
        next_is_primary = self.next_button.isEnabled()
        self.action_button.setProperty("primary", action_is_primary)
        self.next_button.setProperty("primary", next_is_primary)
        for button in (self.action_button, self.next_button):
            button.style().unpolish(button)
            button.style().polish(button)
        if busy:
            self.action_context.setText("ROMVERSE is completing the current verified local task.")
        elif next_is_primary:
            self.action_context.setText("This task is verified. Continue to the next stage.")
        elif action_is_primary:
            self.action_context.setText(
                f"Choose “{self.action_button.text()}” to resolve this stage."
            )
        elif assessment.status is GuidedStageStatus.LOCKED:
            self.action_context.setText("Return to the highlighted prerequisite before continuing.")
        else:
            self.action_context.setText(
                "Review the visible evidence and choose the available route."
            )
        self.back_button.setEnabled(self.selected_index > 0 and not busy)
        self.save_button.setText(
            "Finish local build"
            if stage.stage_id == "flash" and not self.state.install_requested
            else "Save && exit"
        )
        defer_flash = (
            stage.stage_id == "flash"
            and self.state.install_requested
            and assessment.status is not GuidedStageStatus.COMPLETE
        )
        skip_customization = (
            stage.stage_id == "customize" and assessment.status is not GuidedStageStatus.COMPLETE
        )
        self.skip_button.setVisible(skip_customization or defer_flash)
        self.skip_button.setText(
            "Defer flash & finish local build"
            if defer_flash
            else "Keep verified base unchanged • Recommended"
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
        self._details_user_choice = None
        self._save_state()
        self._refresh()
        self._animate_stage_transition()

    def _back(self) -> None:
        if self.selected_index > 0:
            self._select_stage(self.selected_index - 1)

    def _next(self) -> None:
        if self.selected_index < len(self.assessments) - 1:
            self._select_stage(self.selected_index + 1)

    def _open_stage_learning(self) -> None:
        stage = self.assessments[self.selected_index].stage
        query = self._stage_learning_query(stage.stage_id)
        if not self._save_state():
            self._render_stage()
            return
        self.accept()
        self.studio.knowledge_requested.emit(query)

    def _stage_learning_query(self, stage_id: str) -> str:
        """Route Device DNA blockers to the matching recovery guide, not a generic page."""

        if stage_id != "device":
            return _STAGE_LEARNING_QUERIES[stage_id]
        context = self._context()
        device = context.device
        if device is not None:
            if device.state is DeviceState.UNAUTHORIZED:
                return "adb unauthorized"
            if device.state is DeviceState.OFFLINE:
                return "adb device offline"
            if device.is_fastboot:
                return "Phone detected in bootloader Fastboot or userspace fastbootd"
            if device.state in {DeviceState.RECOVERY, DeviceState.SIDELOAD}:
                return "Phone detected in Android recovery or ADB sideload mode"
            if device.state is DeviceState.UNKNOWN:
                return "Android device connection"
            return "Android device identity fields: brand, manufacturer, model, device, and product"
        if len(context.observed_devices) > 1:
            return "multiple devices"
        if context.device_scan_error:
            return "ADB transport failure"
        return "USB debugging Android connection"

    def _skip_customization(self) -> None:
        if not self._clear_rooted_input_for_unrooted_route():
            return
        self.state = replace(
            self.state,
            customization_skipped=True,
            recipe_skipped=True,
            recipe_validated=False,
            root_choice="skip",
            last_error="",
        )
        self.failure = None
        next_assessments = self.engine.assess(self._context())
        self.selected_index = self.engine.current_index(next_assessments)
        if not self._save_state():
            self._refresh(select_current=True)
            return
        self._refresh(select_current=True)
        if self.autopilot_active:
            QTimer.singleShot(0, self._advance_autopilot)

    def _secondary_action(self) -> None:
        assessment = self.assessments[self.selected_index]
        if assessment.stage.stage_id == "flash":
            self._defer_flash()
            return
        self._skip_customization()

    def _save_or_finish(self) -> None:
        assessment = self.assessments[self.selected_index]
        if assessment.stage.stage_id == "flash" and not self.state.install_requested:
            self._finish_local_build()
            return
        self.accept()

    def _finish_local_build(self) -> None:
        self.state = replace(
            self.state,
            selected_stage="flash",
            install_requested=False,
            last_error="",
        )
        if not self._save_state():
            self._render_stage()
            return
        self._finish_genesis_live(
            MissionState.SUCCEEDED,
            "Genesis local ROM build is complete.",
            "All 13 local build stages are verified. Optional image installation and full first-boot verification were deferred; finishing this local build did not change the phone.",
            "Use the verified local artifact, or reopen Genesis to review source-bound image preparation and any previously recorded local outcome.",
            MissionConfidence.VERIFIED,
        )
        super().accept()

    def _defer_flash(self) -> None:
        self.state = replace(self.state, install_requested=False, last_error="")
        self.failure = None
        self._save_state()
        self._refresh(select_current=True)
        self.status_text.setText(
            "Local ROM build complete. Flash setup was deferred; no phone state changed."
        )

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
        if self._closing or not self.autopilot_active:
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
        if stage.stage_id == "flash" and assessment.status is GuidedStageStatus.FUTURE:
            self._finish_autopilot(
                "Local ROM build complete: all 13 build stages are verified. Optional phone "
                "installation was not started. Choose Finish local build, or explicitly continue "
                "to local image preparation."
            )
            return
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
            if self._closing:
                return
            self._refresh(select_current=True)
            after_stage = self.assessments[self.selected_index].stage.stage_id
            if after_stage != before_stage:
                self.autopilot_active = True
                QTimer.singleShot(0, self._advance_autopilot)
            else:
                review_surface = (
                    "Forge Control" if before_stage == "build_sign" else "Guardian review"
                )
                self.status_text.setText(
                    f"Automatic Genesis paused at {review_surface}. Complete its "
                    "highlighted requirement, then choose Auto-resolve & continue again."
                )
                self._pause_genesis_live(
                    f"Genesis paused at {review_surface} for authoritative evidence or consent."
                )
            return

        before_stage = stage.stage_id
        self._run_stage()
        if self._closing:
            return
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
            "ROMVERSE has preserved and verified the base firmware. Choose the recommended "
            "unchanged route for no Recipe changes, no optional app removal, and a standard "
            "unrooted ROM; or open Recipe Forge for guided modifications.\n\nNeither route "
            "changes the phone."
        )
        keep_base = dialog.addButton(
            "Keep verified base unchanged • Recommended",
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

    def _clear_rooted_input_for_unrooted_route(self) -> bool:
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
        return True

    def _select_unrooted_route(self) -> bool:
        if not self._clear_rooted_input_for_unrooted_route():
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
        saved_toolchain_review = self._saved_toolchain_review_available(assessment)
        self.live_paused = False
        self._sync_genesis_live()
        self.failure = None
        context = self._context()
        if action in {"flash", "first-boot"} and context.source_installation_state:
            if self._source_installation_needs_diagnosis(context):
                self._handoff_source_installation_recovery()
            else:
                self._handoff_source_installation_history()
        elif action == "flash" and not self.state.install_requested:
            self._prompt_flash_choice()
        elif action == "new-project":
            previous_project_id = (
                self.studio.current_project.project_id
                if self.studio.current_project is not None
                else ""
            )
            self.studio._new_project()
            if self.studio.current_project is not None and (
                not self._start_new_project
                or self.studio.current_project.project_id != previous_project_id
            ):
                self._start_new_project = False
                self.state = self._load_state()
            self._refresh(select_current=True)
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
            if not self.studio.device_scan_available:
                project = self.studio.current_project
                source_sha256 = (
                    project.original.sha256
                    if project is not None and project.original is not None
                    else ""
                )
                self.failure = None
                self.active_operation = "device-scan"
                self.process_label.setText("Verifying Platform Tools for the pending device scan")
                self.process_progress.begin()
                self.process_frame.setVisible(True)
                self.status_text.setText(
                    "Genesis is handing this exact pending read-only scan to Forge Arsenal."
                )
                self._render_stage()
                resolved = self._resolve_required_tools(
                    ("ADB", "Fastboot"),
                    purpose=(
                        "Genesis stage 5 must freshly verify Android Platform Tools for the exact "
                        f"project {project.project_id if project is not None else 'unavailable'} "
                        f"and protected source {source_sha256[:16] or 'unavailable'}… before one "
                        "read-only device scan. No phone-changing command is authorized."
                    ),
                )
                if not resolved or not self.studio.device_scan_available:
                    self.active_operation = ""
                    self.process_progress.stop()
                    self.process_frame.setVisible(False)
                    if self.failure is None:
                        self.failure = GuidedFailure(
                            "Forge Arsenal still needs attention",
                            "Android Platform Tools are not freshly verified for this pending scan.",
                            (
                                "Choose Scan device & refresh DNA to reopen the same repair.",
                                "Install and verify ADB and Fastboot, then let Genesis retry once.",
                                "ROMVERSE will not claim device evidence while the tools are unavailable.",
                            ),
                        )
                    self._refresh(select_current=True)
                    return

            self.failure = None
            self.active_operation = "device-scan"
            self.process_label.setText("Scanning Android connection and refreshing Device DNA")
            self.process_progress.begin()
            self.process_frame.setVisible(True)
            self.status_text.setText(
                "ROMVERSE is requesting a fresh read-only device scan. No phone state is changed."
            )
            self._render_stage()
            # MainWindow starts a scan as soon as freshly verified Platform Tools are activated.
            # Emitting the pending request here is still required for standalone Studio owners;
            # MainWindow's scan guard coalesces it with an already-running activation scan.
            self.studio.device_scan_requested.emit()
            return
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
            resolved = self._resolve_required_tools(
                self._context().required_tools,
                purpose="Genesis must verify every source-bound build dependency before Forge Control.",
            )
            if not resolved:
                detail = (
                    self.failure.explanation
                    if self.failure is not None
                    else "Required host dependencies remain unverified."
                )
                self.state = replace(self.state, last_error=f"toolchain: {detail}")
                if saved_toolchain_review:
                    self.selected_index = 9
                    self._refresh(select_current=False)
                    self._save_state()
                    return
                self._save_state()
                self._refresh(select_current=True)
                return
            self.failure = None
            self.state = replace(self.state, last_error="")
            if saved_toolchain_review:
                self._refresh(select_current=False)
                self.selected_index = 10
                self._save_state()
                self._refresh(select_current=False)
                return
            self._refresh(select_current=True)
            self._save_state()
        elif action == "build-sign":
            self.studio._open_build_control(self)
            if self._closing:
                return
            self._refresh()
        elif action == "flash":
            context = self._context()
            if context.source_installation_state:
                if self._source_installation_needs_diagnosis(context):
                    self._handoff_source_installation_recovery()
                else:
                    self._handoff_source_installation_history()
                return
            project = self.studio.current_project
            self._handoff_project_images(
                project.project_id if project is not None else "",
                project.original.sha256
                if project is not None and project.original is not None
                else "",
            )
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

    def _prompt_flash_choice(self) -> None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Genesis Sequence • local build complete")
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setText("Your local ROM build is complete")
        dialog.setInformativeText(
            "All 13 local build stages have verified evidence. Flashing is a separate optional "
            "operation. You can finish here or let ROMVERSE verify the best available installation "
            "route. It prefers a complete, understood ROM procedure; manual verified-image subsets "
            "remain available when you deliberately need explicit mapping.\n\nYou will review the "
            "exact route, phone, compatibility and recovery warnings, and separately confirm before "
            "any phone write. A manual subset is not a full-ROM installation and no route is a "
            "production certificate. Opening preparation does not change the phone."
        )
        finish = dialog.addButton(
            "Finish local build • Recommended",
            QMessageBox.ButtonRole.AcceptRole,
        )
        continue_flash = dialog.addButton(
            VERIFIED_ROM_INSTALLATION_ACTION,
            QMessageBox.ButtonRole.ActionRole,
        )
        dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(finish)
        project = self.studio.current_project
        project_id = project.project_id if project is not None else ""
        source_sha256 = (
            project.original.sha256 if project is not None and project.original is not None else ""
        )
        dialog.exec()
        if dialog.clickedButton() is finish:
            self._finish_local_build()
            return
        if dialog.clickedButton() is continue_flash:
            self._handoff_project_images(project_id, source_sha256)

    def _handoff_project_images(self, project_id: str, source_sha256: str) -> bool:
        """Save and close Genesis before the desktop opens local image preparation."""

        current = self.studio.current_project
        if self.studio.worker is not None or self.active_operation or self.root_preview_active:
            self.status_text.setText("Wait for the current operation before image preparation.")
            return False
        if (
            not project_id
            or not source_sha256
            or current is None
            or current.project_id != project_id
            or current.original is None
            or current.original.sha256 != source_sha256
        ):
            self.status_text.setText(
                "The project or protected firmware source is missing or changed. Reopen Genesis."
            )
            return False
        self.autopilot_active = False
        self.state = replace(self.state, install_requested=True, last_error="")
        if not self._save_state():
            self._render_stage()
            return False
        self._pause_genesis_live(
            "Genesis paused for explicit local image preparation; no phone write has started."
        )
        super().accept()
        QTimer.singleShot(
            0,
            lambda: self.studio._request_project_flash(project_id, source_sha256=source_sha256),
        )
        return True

    def _handoff_source_installation_history(self) -> None:
        project = self.studio.current_project
        if (
            project is None
            or project.original is None
            or self.studio.worker is not None
            or self.active_operation
            or self.root_preview_active
        ):
            self.status_text.setText(
                "Wait for the current operation before reviewing saved results."
            )
            return
        project_id, source_sha256 = project.project_id, project.original.sha256
        self.autopilot_active = False
        self._pause_genesis_live("Reviewing saved installation results; no phone change requested.")
        super().accept()
        QTimer.singleShot(
            0, lambda: self.studio._request_source_installation_history(project_id, source_sha256)
        )

    @staticmethod
    def _source_installation_needs_diagnosis(context: GuidedContext) -> bool:
        state = context.source_installation_state.strip().casefold()
        return state in {"failed", "attention"} or (
            state == "cancelled" and context.source_installation_completed_count > 0
        )

    def _source_recovery_key(self, context: GuidedContext) -> tuple[str, str, str, int, int] | None:
        project = self.studio.current_project
        if (
            project is None
            or project.original is None
            or not self._source_installation_needs_diagnosis(context)
        ):
            return None
        return (
            project.project_id,
            project.original.sha256,
            context.source_installation_state.strip().casefold(),
            context.source_installation_completed_count,
            context.source_installation_expected_count,
        )

    def _schedule_automatic_source_recovery(self) -> None:
        """Queue one evidence-bound diagnosis handoff; never retry an installation."""

        if (
            not self.isVisible()
            or self.studio.worker is not None
            or self.active_operation
            or self.root_preview_active
        ):
            return
        context = getattr(self, "_display_context", None)
        if not isinstance(context, GuidedContext):
            context = self._context()
        key = self._source_recovery_key(context)
        if key is None or key == self._automatic_source_recovery_key:
            return
        self._automatic_source_recovery_key = key
        self.status_text.setText(
            "ROMVERSE found an interrupted installation. Checking what happened… "
            "No write or retry will run."
        )
        QTimer.singleShot(0, lambda expected=key: self._start_automatic_source_recovery(expected))

    def _start_automatic_source_recovery(self, expected: tuple[str, str, str, int, int]) -> None:
        if expected != self._automatic_source_recovery_key:
            return
        self._automatic_source_recovery_key = None
        if (
            not self.isVisible()
            or self.studio.worker is not None
            or self.active_operation
            or self.root_preview_active
        ):
            return
        context = self._context()
        if self._source_recovery_key(context) != expected:
            self.status_text.setText(
                "The project or protected firmware outcome changed. ROMVERSE did not attribute "
                "or retry the interrupted installation."
            )
            return
        self._handoff_source_installation_recovery()

    def _handoff_source_installation_recovery(self) -> None:
        project = self.studio.current_project
        if (
            project is None
            or project.original is None
            or self.studio.worker is not None
            or self.active_operation
            or self.root_preview_active
        ):
            self.status_text.setText(
                "Wait for the current operation before diagnosing the interrupted installation."
            )
            return
        project_id, source_sha256 = project.project_id, project.original.sha256
        self.autopilot_active = False
        self._pause_genesis_live(
            "Opening exact interrupted-installation diagnosis; no phone command or retry was requested."
        )
        super().accept()
        QTimer.singleShot(
            0,
            lambda: self.studio._request_source_installation_recovery(project_id, source_sha256),
        )

    def _run_first_boot_check(self) -> None:
        project = self.studio.current_project
        if project is None:
            self.failure = self.engine.diagnose("No project loaded")
            self._refresh()
            return
        context = self._context()
        if context.source_installation_state:
            if self._source_installation_needs_diagnosis(context):
                self._handoff_source_installation_recovery()
            else:
                self._handoff_source_installation_history()
            return
        if context.local_image_state and not context.flash_complete:
            self._handoff_project_images(
                project.project_id,
                project.original.sha256 if project.original is not None else "",
            )
            return
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
        existing = service.load(
            project.project_id,
            verified_flash=self.studio._latest_guardian_execution_result,
            device=context.device,
        )
        wait = service.next_sample_wait_seconds(existing)
        if wait:
            self.failure = self.engine.diagnose(
                f"Boot observation cooldown active. Reconnect or wait {wait} second(s) for a valid sample."
            )
            self._refresh()
            return
        try:
            receipt = service.observe(
                project.project_id,
                context.device,
                verified_flash=self.studio._latest_guardian_execution_result,
            )
        except (OSError, ProjectError) as exc:
            self.failure = self.engine.diagnose(str(exc))
            self._refresh()
            return
        self.failure = None
        self.status_text.setText(
            f"Boot evidence recorded  •  {receipt.status.value}  •  {receipt.diagnosis}"
        )
        knowledge_report = self.studio.scan_boot_observation_knowledge(receipt)
        self.studio.boot_observation_updated.emit(receipt, knowledge_report)
        self._refresh(select_current=True)
        if receipt.status is BootObservationStatus.STABLE:
            self.status_text.setText(
                "First-boot checks are stable and linked to the verified Guardian flash receipt. "
                "Genesis Sequence is ready to complete."
            )
            if self.autopilot_active:
                QTimer.singleShot(0, self._advance_autopilot)
        else:
            archive_guidance: tuple[str, ...] = ()
            if service.needs_knowledge_lookup(receipt):
                if knowledge_report is None:
                    archive_guidance = (
                        "The offline Archives scan could not complete; ROMVERSE did not guess a repair.",
                    )
                elif knowledge_report.matches:
                    archive_guidance = (
                        f"Offline Archives automatically found {len(knowledge_report.matches)} compatible diagnostic match(es).",
                        *(
                            f"{match.record.title} — {match.confidence.value} match; guidance only."
                            for match in knowledge_report.matches[:3]
                        ),
                    )
                else:
                    archive_guidance = (
                        "Offline Archives found no compatible local match; the cause remains unknown.",
                    )
            self.failure = GuidedFailure(
                "First-boot check incomplete",
                f"Boot status is currently {receipt.status.value}.",
                (
                    service.next_step(receipt),
                    *archive_guidance,
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
        self.studio._start_worker(
            operation,
            guided_evidence=operation in {"plan", "verify-plan"},
        )
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
            auto_start=False,
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
            blocker = current.blockers[0].strip() if current.blockers else ""
            if self.autopilot_active:
                self._finish_autopilot(
                    blocker
                    or "The fresh scan completed, but exact device evidence still needs attention."
                )
            else:
                self.status_text.setText(
                    blocker
                    or message
                    or "Fresh device scan completed; review the evidence shown here."
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
        if self.operation_queue:
            self._save_state()
            QTimer.singleShot(0, self._start_next_operation)
        else:
            self._refresh(select_current=True)
            self._save_state()
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
            QFrame#PhaseStrip { background: #040913; border-bottom: 1px solid #172941; }
            QPushButton[phaseStatus] {
                color: #73819B; background: #070C15; border: 1px solid #1B2A40;
                border-radius: 9px; padding: 8px 7px; font-size: 10px;
                font-weight: 850; letter-spacing: 1px;
            }
            QPushButton[phaseStatus="complete"] { color: #60E9B2; border-color: #185841; }
            QPushButton[phaseStatus="ready"] { color: #8DEAF3; border-color: #247083; }
            QPushButton[phaseStatus="attention"] { color: #FFD07A; border-color: #74501B; }
            QPushButton[phaseStatus="future"] { color: #B68BE8; border-color: #4F3470; }
            QPushButton[phaseStatus]:checked {
                color: #FFFFFF; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #23113B, stop:.48 #162148, stop:1 #082D38);
                border: 1px solid #67DFED;
            }
            QFrame#IdentityDeck { background: #03070D; border-bottom: 1px solid #142237; }
            QFrame#IdentityCard, QFrame#CompatibilityCard {
                background: #060C16; border: 1px solid #1A2C45; border-radius: 10px;
            }
            QFrame#CompatibilityCard { border-color: #274C61; }
            QFrame#CompatibilityCard[upgradeState="verified"] {
                background: #06140F; border-color: #1C805E;
            }
            QFrame#CompatibilityCard[upgradeState="attention"] {
                background: #151107; border-color: #77541C;
            }
            QFrame#CompatibilityCard[upgradeState="blocked"] {
                background: #17090E; border-color: #87304A;
            }
            QLabel#IdentityEyebrow {
                color: #58D9E9; font-size: 9px; font-weight: 850; letter-spacing: 1.4px;
            }
            QLabel#IdentityTitle { color: #F5F8FF; font-size: 13px; font-weight: 800; }
            QLabel#IdentityTitle[upgradeState="verified"] { color: #62E9B4; }
            QLabel#IdentityTitle[upgradeState="attention"] { color: #FFD07A; }
            QLabel#IdentityTitle[upgradeState="blocked"] { color: #FF819D; }
            QLabel#IdentityDetail { color: #8191AD; font-size: 10px; }
            QLabel#MissionEyebrow, QLabel#CardHeading {
                color: #40DDF2; font-size: 11px; font-weight: 800; letter-spacing: 2px;
            }
            QLabel#MissionTitle { color: #FFFFFF; font-size: 22px; font-weight: 800; }
            QLabel#ModeBadge {
                color: #E4D5FF; background: #170E29; border: 1px solid #5E3B84;
                border-radius: 11px; padding: 7px 11px; font-size: 10px;
                font-weight: 850; letter-spacing: 1px;
            }
            QLabel#GuardianBadge {
                color: #42F0AD; background: #071A18; border: 1px solid #147A5B;
                border-radius: 11px; padding: 7px 11px; font-size: 10px; font-weight: 850;
                letter-spacing: .6px;
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
            QFrame#MissionTaskCard {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 rgba(12,18,34,252), stop:.62 rgba(6,13,25,252),
                    stop:1 rgba(12,9,27,248));
                border: 1px solid #2B3C58; border-left: 3px solid #536C96;
                border-radius: 14px;
            }
            QFrame#MissionTaskCard[stageStatus="complete"] { border-left-color: #44E39A; }
            QFrame#MissionTaskCard[stageStatus="ready"] { border-left-color: #36DCEA; }
            QFrame#MissionTaskCard[stageStatus="attention"] { border-left-color: #FFB454; }
            QFrame#MissionTaskCard[stageStatus="locked"] { border-left-color: #66758E; }
            QFrame#MissionTaskCard[stageStatus="future"] { border-left-color: #A855F7; }
            QLabel#StageTitle { color: #FFFFFF; font-size: 28px; font-weight: 800; }
            QLabel#MissionBody { color: #BAC7DE; font-size: 14px; }
            QFrame#StatusBanner {
                background: #07131D; border: 1px solid #1C5061; border-radius: 10px;
            }
            QFrame#StatusBanner[stageStatus="complete"] { border-color: #177657; background: #061712; }
            QFrame#StatusBanner[stageStatus="attention"] { border-color: #7A5720; background: #171207; }
            QFrame#StatusBanner[stageStatus="locked"] { border-color: #34425A; background: #090E17; }
            QFrame#StatusBanner[stageStatus="future"] { border-color: #58377B; background: #11091B; }
            QFrame#ProcessCard {
                background: #07111E; border: 1px solid #29486A; border-radius: 10px;
            }
            QLabel#StatusIcon { color: #42DFF0; font-size: 18px; }
            QLabel#StatusIcon[stageStatus="complete"] { color: #44E39A; }
            QLabel#StatusIcon[stageStatus="attention"] { color: #FFB454; }
            QLabel#StatusIcon[stageStatus="locked"] { color: #74829D; }
            QLabel#StatusIcon[stageStatus="future"] { color: #C58AFF; }
            QLabel#StatusText { color: #D9E5F7; font-weight: 700; }
            QFrame#MissionCard {
                background: #050A12; border: 1px solid #1B2B43; border-radius: 12px;
            }
            QFrame#SupportingHeader {
                background: rgba(6,12,23,235); border: 1px solid #1D2C43;
                border-radius: 10px;
            }
            QFrame#SupportingPanel { background: transparent; border: 0; }
            QLabel#SupportingSummary { color: #8999B7; font-size: 11px; }
            QPushButton#DetailToggle {
                color: #D8C4F4; background: #110D1C; border-color: #513874;
                padding: 7px 11px; font-size: 11px;
            }
            QPushButton#DetailToggle:hover, QPushButton#DetailToggle:checked {
                color: #FFFFFF; background: #1D1231; border-color: #9660C8;
            }
            QFrame#OutcomeCard {
                background: rgba(5,16,25,245); border: 1px solid #214659;
                border-left: 3px solid #35D7E7; border-radius: 11px;
            }
            QLabel#CardBody { color: #AEBBD2; font-size: 13px; }
            QFrame#DiagnosticCard { background: #170A11; border: 1px solid #8C304D; border-radius: 12px; }
            QLabel#DiagnosticTitle { color: #FF789A; font-size: 17px; font-weight: 800; }
            QFrame#MissionFooter {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #040812, stop:.58 #060B16, stop:1 #0B0816);
                border-top: 1px solid #263958;
            }
            QLabel#ActionEyebrow {
                color: #42DDEA; font-size: 9px; font-weight: 850; letter-spacing: 1.5px;
            }
            QLabel#ActionContext { color: #98A8C3; font-size: 11px; }
            QPushButton#MissionAction {
                color: #B8DCE4; background: #09131C; border-color: #315865;
                padding: 11px 18px; min-height: 20px;
            }
            QPushButton#MissionAction:hover { color: #FFFFFF; background: #10242E; border-color: #62DBE8; }
            QPushButton#MissionAction[primary="true"] {
                color: #031116; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #49DCE9, stop:1 #34BDD8); border-color: #8AF3FA;
            }
            QPushButton#MissionAction[primary="true"]:hover { background: #78E8F2; }
            QPushButton#MissionNext {
                color: #8AAFA1; background: #091511; border-color: #285443;
                padding: 11px 18px; min-height: 20px;
            }
            QPushButton#MissionNext[primary="true"] {
                color: #04140F; background: #35D69C; border-color: #71F1BE;
            }
            QPushButton#MissionNext[primary="true"]:hover { background: #68E6B7; }
            QPushButton#MissionNext:disabled { color: #506078; background: #09101A; border-color: #1D2B40; }
            QPushButton#MissionAutopilot {
                color: #D9C6F2; background: #100C1C; border-color: #513471;
                padding: 9px 14px;
            }
            QPushButton#MissionAutopilot:hover { color: #FFFFFF; background: #211337; border-color: #A45DE3; }
            QPushButton#SecondaryAction { color: #DFC2FF; border-color: #6E3D9B; }
            QPushButton:focus { border: 2px solid #FFFFFF; }
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
