from __future__ import annotations

import html
import json
from contextlib import suppress
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
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

from romverse.core.activity import ActivityStore, ActivityStoreError
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.registry import DevicePackRegistry
from romverse.diagnostics.analyzer import DiagnosticAnalyzer
from romverse.diagnostics.models import DiagnosticReport
from romverse.guardian.planning import (
    CheckStatus,
    GuardianPreflight,
    OperationManifest,
    PreflightAssessment,
    PreflightStatus,
)
from romverse.intelligence.action_evidence import TypedLocalActionEvidence
from romverse.intelligence.online_remediation import (
    ErrorFingerprint,
    OnlineFixReceipt,
    OnlineRemediationService,
    RemediationDecision,
    SourceAuthority,
    candidate_evidence_signal,
    synthesize_remediation,
)
from romverse.knowledge.advisor import ArchiveRecommendation, recommend_for_repair
from romverse.knowledge.lookup import OfflineKnowledgeService
from romverse.knowledge.models import KnowledgeFailure, KnowledgeLookupReport, KnowledgeQuery
from romverse.nexus.events import (
    LiveConsoleEventStore,
    LiveConsoleStoreError,
    MissionConfidence,
    MissionState,
)
from romverse.repair.autopilot import (
    RecoveryAutopilotContext,
    RecoveryAutopilotError,
    RecoveryAutopilotService,
    RecoveryIncident,
    RecoveryIncidentState,
    RecoveryRoute,
    RecoveryRouteKind,
    RecoveryTrigger,
)
from romverse.repair.host import (
    AdbHostRepairError,
    AdbHostRepairMode,
    AdbHostRepairPlan,
    AdbHostRepairResult,
    AdbHostRepairService,
    AdbHostRepairStatus,
)
from romverse.repair.knowledge import knowledge_for
from romverse.repair.sessions import RepairSession, RepairSessionError, RepairSessionStore
from romverse.repair.templates import (
    RepairAssessmentTemplates,
    RepairConcern,
    concern_for_finding,
)
from romverse.rom.boot_observation import BootObservationReceipt
from romverse.rom.recovery_evidence import RecoveryEvidenceAssessment
from romverse.ui.background import ManagedRunnable, start_background
from romverse.ui.process_progress import ProcessProgressBar


class HostRepairSignals(QObject):
    complete = Signal(object)
    failed = Signal(str)


class HostRepairWorker(ManagedRunnable):
    def __init__(self, service: AdbHostRepairService, plan: AdbHostRepairPlan) -> None:
        super().__init__()
        self.service = service
        self.plan = plan
        self.signals = HostRepairSignals()

    @Slot()
    def execute(self) -> None:
        try:
            self.signals.complete.emit(self.service.execute(self.plan))
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class RepairResearchSignals(QObject):
    complete = Signal(object)
    failed = Signal(str)


class RepairResearchWorker(ManagedRunnable):
    def __init__(
        self,
        service: OnlineRemediationService,
        fingerprint: ErrorFingerprint,
    ) -> None:
        super().__init__()
        self.service = service
        self.fingerprint = fingerprint
        self.signals = RepairResearchSignals()

    @Slot()
    def execute(self) -> None:
        try:
            self.signals.complete.emit(self.service.lookup(self.fingerprint))
        except (OSError, TypeError, ValueError) as exc:
            self.signals.failed.emit(str(exc))


class RepairCenter(QWidget):
    verification_scan_requested = Signal()
    runtime_tools_requested = Signal()
    solution_action_requested = Signal(str, str, str, str)
    knowledge_requested = Signal(str)
    knowledge_article_requested = Signal(str)
    diagnostic_requested = Signal(str)
    resolution_memory_updated = Signal()
    autopilot_route_requested = Signal(str, str)

    def __init__(
        self,
        analyzer: DiagnosticAnalyzer,
        templates: RepairAssessmentTemplates,
        preflight: GuardianPreflight,
        workspace: Path | None = None,
        activity_store: ActivityStore | None = None,
        pack_registry: DevicePackRegistry | None = None,
        host_repair_service: AdbHostRepairService | None = None,
        live_console_store: LiveConsoleEventStore | None = None,
        online_service: OnlineRemediationService | None = None,
        offline_service: OfflineKnowledgeService | None = None,
    ) -> None:
        super().__init__()
        self.analyzer = analyzer
        self.templates = templates
        self.preflight = preflight
        self.session_store = RepairSessionStore(workspace) if workspace is not None else None
        self.activity_store = activity_store
        self.pack_registry = pack_registry or DevicePackRegistry(())
        self.host_repair_service = host_repair_service
        self.live_console_store = live_console_store
        self.online_service = online_service
        self.offline_service = offline_service
        self.offline_report: KnowledgeLookupReport | None = None
        self.offline_error = ""
        self._offline_query_text = ""
        self.devices: list[AndroidDevice] = []
        self._report_payload: dict[str, object] | None = None
        self.current_device: AndroidDevice | None = None
        self.current_report: DiagnosticReport | None = None
        self.current_concern: RepairConcern | None = None
        self._diagnostic_context_id = ""
        self._applying_diagnostic_context = False
        self.active_session: RepairSession | None = None
        self.session_checks: list[QCheckBox] = []
        self._pending_verification_session = ""
        self.host_repair_plan: AdbHostRepairPlan | None = None
        self.host_repair_button: QPushButton | None = None
        self.host_repair_worker: HostRepairWorker | None = None
        self._host_repair_mission = ""
        self.online_worker: RepairResearchWorker | None = None
        self._online_current: ErrorFingerprint | None = None
        self._online_pending: ErrorFingerprint | None = None
        self._online_attempted: set[str] = set()
        self._online_receipts: dict[str, OnlineFixReceipt] = {}
        self._online_mission = ""
        self._intelligence_action_binding: tuple[str, str, str, str] | None = None
        self.autopilot_service = (
            RecoveryAutopilotService(workspace, self.pack_registry)
            if workspace is not None
            else None
        )
        self.autopilot_incident: RecoveryIncident | None = None
        self._autopilot_project_id = ""
        self._autopilot_boot_observation: BootObservationReceipt | None = None
        self._autopilot_recovery_evidence: RecoveryEvidenceAssessment | None = None
        self._autopilot_knowledge_report: KnowledgeLookupReport | None = None
        self._autopilot_message = ""
        self._autopilot_show_all_routes = False
        self.autopilot_route_buttons: list[QPushButton] = []

        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 30)
        page.setSpacing(18)
        header = QHBoxLayout()
        text = QVBoxLayout()
        eyebrow = QLabel("RECOVERY BAY  •  GUARDIAN PREFLIGHT")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("Recovery Bay")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Describe the problem, run fresh read-only diagnostics, and follow an evidence-led recovery session. Device-changing repairs remain Guardian-locked until a typed, verified action exists."
        )
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        text.addWidget(eyebrow)
        text.addWidget(title)
        text.addWidget(subtitle)
        header.addLayout(text, 1)
        self.device_selector = QComboBox()
        self.device_selector.setMinimumWidth(210)
        self.device_selector.setVisible(False)
        self.device_selector.currentIndexChanged.connect(self.build_plan)
        header.addWidget(self.device_selector)
        self.concern_selector = QComboBox()
        for concern in RepairConcern:
            # QVariant may round-trip StrEnum values as plain strings. Persist the
            # canonical value explicitly and normalize it again in build_plan.
            self.concern_selector.addItem(concern.value, concern.value)
        self.concern_selector.setMinimumWidth(260)
        self.concern_selector.currentIndexChanged.connect(self._concern_changed)
        header.addWidget(self.concern_selector)
        self.build_button = QPushButton("Build safety plan")
        self.build_button.setObjectName("Primary")
        self.build_button.setEnabled(False)
        self.build_button.clicked.connect(self.build_plan)
        header.addWidget(self.build_button)
        self.session_button = QPushButton("Start guided repair session")
        self.session_button.setToolTip(
            "Save a privacy-safe baseline, follow recommended checkpoints, then compare a fresh scan."
        )
        self.session_button.setEnabled(False)
        self.session_button.clicked.connect(self._start_session)
        header.addWidget(self.session_button)
        page.addLayout(header)

        symptom_row = QHBoxLayout()
        symptom_label = QLabel("Exact symptom or error")
        symptom_label.setObjectName("Muted")
        self.symptom_input = QLineEdit()
        self.symptom_input.setMaxLength(600)
        self.symptom_input.setPlaceholderText(
            "Optional: paste the exact error or briefly describe what happens"
        )
        self.symptom_input.setToolTip(
            "ROMVERSE removes paths, long identifiers, and digests before creating an online research fingerprint. Raw text is not stored in the research receipt."
        )
        self.symptom_input.editingFinished.connect(self.build_plan)
        symptom_row.addWidget(symptom_label)
        symptom_row.addWidget(self.symptom_input, 1)
        self.archives_button = QPushButton("Search local Archives")
        self.archives_button.setToolTip(
            "Search verified local known fixes for this symptom. This does not run a repair or send text online."
        )
        self.archives_button.clicked.connect(self._search_archives)
        symptom_row.addWidget(self.archives_button)
        page.addLayout(symptom_row)
        self.diagnostic_context_row = QFrame()
        self.diagnostic_context_row.setObjectName("DiagnosticHandoffBar")
        diagnostic_context_layout = QHBoxLayout(self.diagnostic_context_row)
        diagnostic_context_layout.setContentsMargins(12, 5, 6, 5)
        diagnostic_context_layout.setSpacing(10)
        self.diagnostic_context = QLabel("")
        self.diagnostic_context.setObjectName("Eyebrow")
        self.diagnostic_context.setAccessibleName("Quantum Optimizer diagnostic handoff")
        self.diagnostic_context.setWordWrap(True)
        self.diagnostic_context.setVisible(False)
        self.diagnostic_context.setToolTip(
            "This exact finding selected the repair category. It starts no repair and can be "
            "cleared by choosing another category."
        )
        diagnostic_context_layout.addWidget(self.diagnostic_context, 1)
        self.diagnostic_source_button = QPushButton("View source finding")
        self.diagnostic_source_button.setObjectName("QuickAction")
        self.diagnostic_source_button.setAccessibleName(
            "View this Recovery Bay plan's exact Quantum Optimizer source finding"
        )
        self.diagnostic_source_button.setToolTip(
            "Return to the exact current read-only finding that selected this plan."
        )
        self.diagnostic_source_button.clicked.connect(self._request_diagnostic_source)
        diagnostic_context_layout.addWidget(self.diagnostic_source_button)
        self.diagnostic_context_row.setVisible(False)
        page.addWidget(self.diagnostic_context_row)

        self.session_context_row = QFrame()
        self.session_context_row.setObjectName("DiagnosticHandoffBar")
        session_context_layout = QHBoxLayout(self.session_context_row)
        session_context_layout.setContentsMargins(18, 13, 18, 13)
        session_copy = QVBoxLayout()
        session_eyebrow = QLabel("ACTIVITY HANDOFF  •  EXACT VERIFIED REPAIR SESSION")
        session_eyebrow.setObjectName("Eyebrow")
        self.session_context_title = QLabel()
        self.session_context_title.setObjectName("SectionTitle")
        self.session_context_detail = QLabel()
        self.session_context_detail.setObjectName("Muted")
        self.session_context_detail.setWordWrap(True)
        self.session_context_detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        session_copy.addWidget(session_eyebrow)
        session_copy.addWidget(self.session_context_title)
        session_copy.addWidget(self.session_context_detail)
        session_context_layout.addLayout(session_copy, 1)
        self.session_context_badge = QLabel("READ-ONLY EVIDENCE")
        self.session_context_badge.setObjectName("Good")
        session_context_layout.addWidget(self.session_context_badge)
        self.session_context_row.setVisible(False)
        page.addWidget(self.session_context_row)

        self.feature_handoff = QFrame()
        self.feature_handoff.setObjectName("DiagnosticHandoffBar")
        feature_handoff_layout = QHBoxLayout(self.feature_handoff)
        feature_handoff_layout.setContentsMargins(18, 11, 18, 11)
        feature_copy = QVBoxLayout()
        feature_eyebrow = QLabel("FIND ANYTHING  •  EXACT NESTED FEATURE")
        feature_eyebrow.setObjectName("Eyebrow")
        self.feature_handoff_title = QLabel()
        self.feature_handoff_title.setObjectName("SectionTitle")
        self.feature_handoff_detail = QLabel()
        self.feature_handoff_detail.setObjectName("Muted")
        self.feature_handoff_detail.setWordWrap(True)
        feature_copy.addWidget(feature_eyebrow)
        feature_copy.addWidget(self.feature_handoff_title)
        feature_copy.addWidget(self.feature_handoff_detail)
        feature_handoff_layout.addLayout(feature_copy, 1)
        self.feature_handoff_badge = QLabel()
        feature_handoff_layout.addWidget(self.feature_handoff_badge)
        self.feature_handoff.setVisible(False)
        page.addWidget(self.feature_handoff)

        self.hero = QFrame()
        self.hero.setObjectName("HeroCard")
        hero_layout = QHBoxLayout(self.hero)
        hero_layout.setContentsMargins(24, 20, 24, 20)
        state = QVBoxLayout()
        self.plan_title = QLabel("Waiting for an authorized device…")
        self.plan_title.setObjectName("HeroTitle")
        self.plan_summary = QLabel(
            "ROMVERSE needs a Device Engine snapshot before it can evaluate preconditions."
        )
        self.plan_summary.setObjectName("Muted")
        self.plan_summary.setWordWrap(True)
        state.addWidget(self.plan_title)
        state.addWidget(self.plan_summary)
        self.resolve_runtime_button = QPushButton("Resolve Platform Tools and scan")
        self.resolve_runtime_button.setObjectName("Primary")
        self.resolve_runtime_button.setToolTip(
            "Verify ROMVERSE-managed Android Platform Tools, restore Device Engine, and run a fresh read-only scan."
        )
        self.resolve_runtime_button.clicked.connect(self._request_runtime_tools)
        self.resolve_runtime_button.setVisible(self.host_repair_service is None)
        state.addWidget(self.resolve_runtime_button, 0, Qt.AlignmentFlag.AlignLeft)
        hero_layout.addLayout(state, 1)
        self.status_badge = QLabel("NO PLAN")
        self.status_badge.setObjectName("Warning")
        hero_layout.addWidget(self.status_badge)
        page.addWidget(self.hero)

        self.autopilot_card = QFrame()
        self.autopilot_card.setObjectName("RecoveryCockpit")
        self.autopilot_card.setProperty("incidentState", "monitoring")
        autopilot_layout = QVBoxLayout(self.autopilot_card)
        autopilot_layout.setContentsMargins(22, 18, 22, 18)
        autopilot_layout.setSpacing(11)
        autopilot_header = QHBoxLayout()
        autopilot_copy = QVBoxLayout()
        autopilot_eyebrow = QLabel("RECOVERY AUTOPILOT  •  LIVE INCIDENT COMMAND CENTRE")
        autopilot_eyebrow.setObjectName("Eyebrow")
        self.autopilot_title = QLabel("Waiting for recovery evidence")
        self.autopilot_title.setObjectName("HeroTitle")
        self.autopilot_title.setWordWrap(True)
        autopilot_copy.addWidget(autopilot_eyebrow)
        autopilot_copy.addWidget(self.autopilot_title)
        autopilot_header.addLayout(autopilot_copy, 1)
        self.autopilot_badge = QLabel("MONITORING")
        self.autopilot_badge.setObjectName("Warning")
        autopilot_header.addWidget(self.autopilot_badge)
        autopilot_layout.addLayout(autopilot_header)
        self.autopilot_diagnosis = QLabel()
        self.autopilot_diagnosis.setObjectName("Muted")
        self.autopilot_diagnosis.setWordWrap(True)
        self.autopilot_diagnosis.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        autopilot_layout.addWidget(self.autopilot_diagnosis)

        self.autopilot_flight_path = QFrame()
        self.autopilot_flight_path.setObjectName("RecoveryFlightPath")
        flight_layout = QHBoxLayout(self.autopilot_flight_path)
        flight_layout.setContentsMargins(10, 10, 10, 10)
        flight_layout.setSpacing(8)
        self.autopilot_stages: list[QFrame] = []
        for number, label in enumerate(("DETECT", "DIAGNOSE", "ROUTE", "VERIFY"), 1):
            stage = QFrame()
            stage.setObjectName("RecoveryStage")
            stage.setProperty("state", "attention")
            stage_layout = QVBoxLayout(stage)
            stage_layout.setContentsMargins(10, 7, 10, 7)
            number_label = QLabel(f"{number:02d}")
            number_label.setObjectName("RecoveryStageNumber")
            value_label = QLabel(label)
            value_label.setObjectName("RecoveryStageValue")
            stage_layout.addWidget(number_label)
            stage_layout.addWidget(value_label)
            flight_layout.addWidget(stage, 1)
            self.autopilot_stages.append(stage)
        autopilot_layout.addWidget(self.autopilot_flight_path)

        self.autopilot_routes = QWidget()
        self.autopilot_routes_layout = QVBoxLayout(self.autopilot_routes)
        self.autopilot_routes_layout.setContentsMargins(0, 0, 0, 0)
        self.autopilot_routes_layout.setSpacing(8)
        autopilot_layout.addWidget(self.autopilot_routes)
        self.autopilot_boundary = QLabel(
            "RANKING IS ADVISORY • DEVICE CHANGES REQUIRE A TYPED OWNER AND CONFIRMATION • "
            "RECOVERED REQUIRES FRESH BOOT + RECONNECT PROOF"
        )
        self.autopilot_boundary.setObjectName("RecoveryBoundary")
        self.autopilot_boundary.setWordWrap(True)
        autopilot_layout.addWidget(self.autopilot_boundary)
        autopilot_actions = QHBoxLayout()
        self.autopilot_timeline_button = QPushButton("View incident timeline + routes")
        self.autopilot_timeline_button.clicked.connect(self._show_autopilot_timeline)
        self.autopilot_scan_button = QPushButton("Capture fresh read-only evidence")
        self.autopilot_scan_button.setObjectName("Primary")
        self.autopilot_scan_button.clicked.connect(self._request_autopilot_scan)
        autopilot_actions.addWidget(self.autopilot_timeline_button)
        autopilot_actions.addStretch()
        autopilot_actions.addWidget(self.autopilot_scan_button)
        autopilot_layout.addLayout(autopilot_actions)
        self.autopilot_card.setVisible(False)
        page.addWidget(self.autopilot_card)

        self.intelligence_card = QFrame()
        self.intelligence_card.setObjectName("Card")
        intelligence_layout = QVBoxLayout(self.intelligence_card)
        intelligence_layout.setContentsMargins(18, 14, 18, 14)
        intelligence_layout.setSpacing(8)
        intelligence_header = QHBoxLayout()
        self.intelligence_heading = QLabel("ROMVERSE INTELLIGENCE • AUTOMATIC REPAIR RESEARCH")
        self.intelligence_heading.setObjectName("Eyebrow")
        intelligence_header.addWidget(self.intelligence_heading)
        intelligence_header.addStretch()
        self.intelligence_toggle = QPushButton("HIDE RESEARCH DETAILS")
        self.intelligence_toggle.setCheckable(True)
        self.intelligence_toggle.setChecked(True)
        self.intelligence_toggle.setAccessibleName("Show or hide online research evidence")
        self.intelligence_toggle.setToolTip(
            "Fold only the research explanation. The assessment, Archives Advisor, and Guardian "
            "state remain unchanged."
        )
        self.intelligence_toggle.toggled.connect(self._set_intelligence_expanded)
        intelligence_header.addWidget(self.intelligence_toggle)
        self.intelligence_status = QLabel("")
        self.intelligence_status.setAccessibleName("ROMVERSE Intelligence status")
        self.intelligence_status.setWordWrap(True)
        self.intelligence_details = QWidget()
        self.intelligence_details.setObjectName("IntelligenceEvidenceContent")
        intelligence_details_layout = QVBoxLayout(self.intelligence_details)
        intelligence_details_layout.setContentsMargins(0, 0, 0, 0)
        intelligence_details_layout.setSpacing(7)
        self.intelligence_detail = QLabel("")
        self.intelligence_detail.setObjectName("Muted")
        self.intelligence_detail.setWordWrap(True)
        self.intelligence_decision = QLabel("")
        self.intelligence_decision.setObjectName("Good")
        self.intelligence_decision.setAccessibleName("ROMVERSE Smart Solution Brief")
        self.intelligence_decision.setWordWrap(True)
        self.intelligence_source = QLabel("")
        self.intelligence_source.setObjectName("Muted")
        self.intelligence_source.setAccessibleName("Ranked remediation evidence sources")
        self.intelligence_source.setWordWrap(True)
        self.intelligence_source.setOpenExternalLinks(True)
        self.intelligence_boundary = QLabel(
            "REMOTE TEXT: GUIDANCE ONLY • EXECUTION AUTHORITY: NONE • PHONE CHANGES: NONE"
        )
        self.intelligence_boundary.setObjectName("Warning")
        self.intelligence_boundary.setWordWrap(True)
        self.intelligence_progress = ProcessProgressBar()
        self.intelligence_retry = QPushButton("Retry verified research")
        self.intelligence_retry.clicked.connect(self._retry_online_research)
        self.intelligence_retry.setVisible(False)
        self.intelligence_action = QPushButton("Open matching ROMVERSE workflow")
        self.intelligence_action.setObjectName("Primary")
        self.intelligence_action.setAccessibleName(
            "Open the matching built-in ROMVERSE verification workflow"
        )
        self.intelligence_action.setToolTip(
            "Revalidate the saved research receipt, then open the matching built-in review "
            "surface. This button never runs remote instructions or starts a phone action."
        )
        self.intelligence_action.clicked.connect(self._request_intelligence_action)
        self.intelligence_action.setVisible(False)
        intelligence_layout.addLayout(intelligence_header)
        intelligence_layout.addWidget(self.intelligence_status)
        intelligence_details_layout.addWidget(self.intelligence_decision)
        intelligence_details_layout.addWidget(self.intelligence_detail)
        intelligence_details_layout.addWidget(self.intelligence_source)
        self.intelligence_details_scroll = QScrollArea()
        self.intelligence_details_scroll.setObjectName("IntelligenceEvidenceScroll")
        self.intelligence_details_scroll.setAccessibleName(
            "Scrollable ROMVERSE Smart Solution evidence"
        )
        self.intelligence_details_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.intelligence_details_scroll.setWidgetResizable(True)
        self.intelligence_details_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.intelligence_details_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.intelligence_details_scroll.setMinimumHeight(156)
        self.intelligence_details_scroll.setMaximumHeight(340)
        self.intelligence_details_scroll.setWidget(self.intelligence_details)
        self.intelligence_expanded_panel = QWidget()
        self.intelligence_expanded_panel.setObjectName("IntelligenceEvidenceContent")
        intelligence_expanded_layout = QVBoxLayout(self.intelligence_expanded_panel)
        intelligence_expanded_layout.setContentsMargins(0, 0, 0, 0)
        intelligence_expanded_layout.setSpacing(7)
        intelligence_expanded_layout.addWidget(self.intelligence_details_scroll)
        intelligence_expanded_layout.addWidget(self.intelligence_progress)
        intelligence_footer = QHBoxLayout()
        intelligence_footer.setContentsMargins(0, 0, 0, 0)
        intelligence_footer.setSpacing(12)
        intelligence_footer.addWidget(self.intelligence_boundary, 1)
        intelligence_footer.addWidget(self.intelligence_action)
        intelligence_expanded_layout.addLayout(intelligence_footer)
        intelligence_expanded_layout.addWidget(self.intelligence_retry)
        intelligence_layout.addWidget(self.intelligence_expanded_panel)
        self.intelligence_card.setVisible(False)
        page.addWidget(self.intelligence_card)

        self.host_action_card = QFrame()
        self.host_action_card.setObjectName("HeroCard")
        host_action_layout = QVBoxLayout(self.host_action_card)
        host_action_layout.setContentsMargins(18, 14, 18, 14)
        host_heading = QLabel("RECOVERY AUTOPILOT • ADB HOST REPAIR")
        host_heading.setObjectName("Eyebrow")
        self.host_action_state = QLabel("")
        self.host_action_detail = QLabel("")
        self.host_action_detail.setObjectName("Muted")
        self.host_action_detail.setWordWrap(True)
        self.host_action_fingerprint = QLabel("")
        self.host_action_fingerprint.setObjectName("Muted")
        self.host_action_fingerprint.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._host_action_button = QPushButton("Review and run ADB host recovery")
        self._host_action_button.setObjectName("Primary")
        self._host_action_button.setToolTip(
            "Approve only the exact host ADB restart. No Android-device command is part of this plan."
        )
        self._host_action_button.clicked.connect(self._run_host_repair)
        host_action_layout.addWidget(host_heading)
        host_action_layout.addWidget(self.host_action_state)
        host_action_layout.addWidget(self.host_action_detail)
        host_action_layout.addWidget(self.host_action_fingerprint)
        host_action_layout.addWidget(self._host_action_button)
        self.host_action_card.setVisible(False)
        page.addWidget(self.host_action_card)

        self.body = QScrollArea()
        self.body.setWidgetResizable(True)
        self.body_content = QWidget()
        self.body_content.setObjectName("ScrollContent")
        self.body_layout = QVBoxLayout(self.body_content)
        self.body_layout.setContentsMargins(0, 0, 6, 0)
        self.body_layout.setSpacing(12)
        self.body.setWidget(self.body_content)
        page.addWidget(self.body, 1)

        self.host_repair_progress = ProcessProgressBar()
        page.addWidget(self.host_repair_progress)

        footer = QHBoxLayout()
        self.digest = QLabel("")
        self.digest.setObjectName("Muted")
        self.digest.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        footer.addWidget(self.digest, 1)
        self.execute_button = QPushButton("Run fresh read-only diagnostics")
        self.execute_button.setObjectName("Primary")
        self.execute_button.setToolTip(
            "Run Device Engine again. If a guided session is active, ROMVERSE saves your checkpoints and compares the new evidence with its baseline."
        )
        self.execute_button.setEnabled(False)
        self.execute_button.clicked.connect(self._run_fresh_diagnostics)
        footer.addWidget(self.execute_button)
        self.export_button = QPushButton("Export report")
        self.export_button.setEnabled(False)
        self.export_button.setToolTip("Save this assessment as a privacy-safe JSON report.")
        self.export_button.clicked.connect(self._export_report)
        footer.addWidget(self.export_button)
        page.addLayout(footer)
        self._empty("Select a connected device and problem category to create a dry-run plan.")
        if self.autopilot_service is not None:
            self.autopilot_incident = next(
                (
                    incident
                    for incident in self.autopilot_service.list_recent()
                    if not incident.repaired
                ),
                None,
            )
            self._render_autopilot()

    def open_feature_destination(self, route: str) -> bool:
        """Reveal one Recovery Bay subsystem without starting research or repair."""

        destination = str(route).strip()
        if destination == "recovery_autopilot":
            active = self.autopilot_incident is not None
            self.feature_handoff_title.setText("Find Anything → Recovery Autopilot")
            self.feature_handoff_detail.setText(
                (
                    "The current private incident, detected mode, ranked recovery routes, and "
                    "verification boundary are displayed below."
                    if active
                    else "Recovery Autopilot opens automatically for measured flash or boot "
                    "failure evidence. You can also start a guided diagnosis from a current "
                    "Device Engine snapshot."
                )
                + " Navigation did not scan, restart ADB, research, repair, approve, build, "
                "flash, or change a phone."
            )
            self.feature_handoff_badge.setText(
                "CURRENT INCIDENT" if active else "EVIDENCE REQUIRED"
            )
            self.feature_handoff_badge.setObjectName("Good" if active else "Warning")
            focus = self.autopilot_timeline_button if active else self.concern_selector
        elif destination == "romverse_intelligence":
            active = self.intelligence_card.isVisible() and bool(
                self.intelligence_status.text().strip()
            )
            self.feature_handoff_title.setText("Find Anything → ROMVERSE Intelligence")
            self.feature_handoff_detail.setText(
                (
                    "The current source-attributed repair-research evidence is displayed below. "
                    "Remote text remains guidance-only and cannot become an operation."
                    if active
                    else "ROMVERSE Intelligence needs a current bounded error fingerprint from "
                    "an exact symptom, device error, or diagnostic finding before verified online "
                    "research can be requested."
                )
                + " Navigation did not submit text, start research, scan, repair, approve, build, "
                "flash, or change a phone."
            )
            self.feature_handoff_badge.setText(
                "GUIDANCE ONLY" if active else "FINGERPRINT REQUIRED"
            )
            self.feature_handoff_badge.setObjectName("Good" if active else "Warning")
            focus = self.intelligence_toggle if active else self.symptom_input
        else:
            return False
        for widget in (self.feature_handoff_badge, self.feature_handoff):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.feature_handoff.setVisible(True)
        focus.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def open_recovery_incident(
        self,
        trigger: RecoveryTrigger,
        *,
        project_id: str = "",
        message: str = "",
        boot_observation: BootObservationReceipt | None = None,
        knowledge_report: KnowledgeLookupReport | None = None,
        failure: KnowledgeFailure | None = None,
        recovery_evidence: RecoveryEvidenceAssessment | None = None,
        target_device: AndroidDevice | None = None,
        allow_current_device_fallback: bool = True,
    ) -> bool:
        """Open or refresh one evidence-backed incident without executing a route."""

        service = self.autopilot_service
        if service is None:
            return False
        device = target_device
        if device is None and allow_current_device_fallback:
            device = self.current_device or (
                self.devices[0] if len(self.devices) == 1 else None
            )
        prior_id = self.autopilot_incident.incident_id if self.autopilot_incident else ""
        self._autopilot_project_id = project_id.strip()[:100]
        self._autopilot_boot_observation = boot_observation
        self._autopilot_recovery_evidence = recovery_evidence
        self._autopilot_message = message.replace("\x00", " ").strip()[:1_000]
        resolved_knowledge = knowledge_report
        if resolved_knowledge is None and failure is not None and self.offline_service is not None:
            try:
                resolved_knowledge = (
                    self.offline_service.scan_after_device_failure(device, failure, limit=5)
                    if device is not None
                    else self.offline_service.scan_after_failure(None, failure, limit=5)
                )
            except (OSError, TypeError, ValueError) as exc:
                self.offline_error = str(exc)[:500]
        if resolved_knowledge is None and target_device is None and allow_current_device_fallback:
            resolved_knowledge = self.offline_report
        self._autopilot_knowledge_report = resolved_knowledge
        context = RecoveryAutopilotContext(
            trigger,
            device=device,
            project_id=self._autopilot_project_id,
            message=self._autopilot_message,
            boot_observation=boot_observation,
            knowledge_report=resolved_knowledge,
            recovery_evidence=recovery_evidence,
            host_repair_available=self.host_repair_service is not None,
        )
        try:
            self.autopilot_incident = service.open(context)
        except RecoveryAutopilotError as exc:
            self.digest.setText(f"Recovery incident could not be preserved  •  {exc}")
            return False
        self._render_autopilot()
        created = self.autopilot_incident.incident_id != prior_id
        if created:
            self._record_activity(
                "Recovery Autopilot incident opened",
                self.autopilot_incident.diagnosis,
                "attention",
            )
        return created

    def update_recovery_boot_observation(
        self,
        receipt: BootObservationReceipt,
        knowledge_report: KnowledgeLookupReport | None = None,
    ) -> None:
        """Apply a freshly verified boot receipt to the active incident."""

        incident = self.autopilot_incident
        if incident is None or (
            incident.project_id and receipt.project_id != incident.project_id
        ):
            return
        self._autopilot_boot_observation = receipt
        if knowledge_report is not None:
            self._autopilot_knowledge_report = knowledge_report
        self._refresh_autopilot(self.current_device)

    def _refresh_autopilot(self, device: AndroidDevice | None) -> None:
        service = self.autopilot_service
        incident = self.autopilot_incident
        if service is None or incident is None or incident.repaired:
            return
        context = RecoveryAutopilotContext(
            incident.trigger,
            device=device,
            project_id=self._autopilot_project_id or incident.project_id,
            message=self._autopilot_message,
            boot_observation=self._autopilot_boot_observation,
            knowledge_report=self._autopilot_knowledge_report or self.offline_report,
            recovery_evidence=self._autopilot_recovery_evidence,
            host_repair_available=self.host_repair_service is not None,
        )
        try:
            updated = service.refresh(incident.incident_id, context)
        except RecoveryAutopilotError as exc:
            self.digest.setText(f"Recovery incident refresh stopped safely  •  {exc}")
            return
        recovered_now = updated.repaired and not incident.repaired
        self.autopilot_incident = updated
        self._render_autopilot()
        if recovered_now:
            self._record_activity(
                "Recovery verified",
                "Fresh boot and reconnect evidence completed the Recovery Autopilot incident.",
                "success",
            )

    def _render_autopilot(self) -> None:
        incident = self.autopilot_incident
        self.autopilot_card.setVisible(incident is not None)
        if incident is None:
            return
        display_state = incident.state.value.replace("_", " ").upper()
        self.autopilot_title.setText(
            f"{incident.device_name}  •  {incident.mode.replace('-', ' ').upper()}"
        )
        self.autopilot_badge.setText(display_state)
        style = (
            "Good"
            if incident.state is RecoveryIncidentState.RECOVERED
            else "Danger"
            if incident.state is RecoveryIncidentState.EMERGENCY
            else "Warning"
        )
        self.autopilot_badge.setObjectName(style)
        self.autopilot_diagnosis.setText(
            f"{incident.diagnosis}\nIncident {incident.incident_id[:12]}…  •  "
            f"{len(incident.events)} tamper-evident timeline event(s)  •  "
            f"Device Pack {incident.pack_id or 'not proven'}  •  Before/after Device DNA + "
            f"partition evidence "
            f"{'CHANGED' if incident.before_evidence_digest != incident.after_evidence_digest else 'UNCHANGED'}"
        )
        self.autopilot_card.setProperty("incidentState", incident.state.value)
        self.autopilot_card.style().unpolish(self.autopilot_card)
        self.autopilot_card.style().polish(self.autopilot_card)
        self.autopilot_badge.style().unpolish(self.autopilot_badge)
        self.autopilot_badge.style().polish(self.autopilot_badge)

        stage_states = (
            "complete",
            "complete",
            "complete" if incident.routes or incident.repaired else "active",
            "complete"
            if incident.repaired
            else "active"
            if incident.state
            in {RecoveryIncidentState.STABILIZING, RecoveryIncidentState.VERIFYING}
            else "attention",
        )
        for stage, stage_state in zip(self.autopilot_stages, stage_states, strict=True):
            stage.setProperty("state", stage_state)
            stage.style().unpolish(stage)
            stage.style().polish(stage)

        while self.autopilot_routes_layout.count():
            item = self.autopilot_routes_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.autopilot_route_buttons = []
        visible_routes = (
            incident.routes if self._autopilot_show_all_routes else incident.routes[:4]
        )
        for route in visible_routes:
            self._add_autopilot_route(route)
        if len(incident.routes) > 4:
            routes_toggle = QPushButton(
                "Show highest-priority routes"
                if self._autopilot_show_all_routes
                else f"Show all {len(incident.routes)} ranked routes"
            )
            routes_toggle.setAccessibleName(
                "Collapse Recovery Autopilot route list"
                if self._autopilot_show_all_routes
                else "Show every ranked Recovery Autopilot route"
            )
            routes_toggle.clicked.connect(self._toggle_autopilot_routes)
            self.autopilot_routes_layout.addWidget(routes_toggle)
        if incident.repaired:
            verified = QFrame()
            verified.setObjectName("RecoveryVerification")
            verified.setProperty("state", "complete")
            verified_layout = QVBoxLayout(verified)
            verified_layout.setContentsMargins(14, 11, 14, 11)
            verified_title = QLabel("VERIFIED RECOVERY • FRESH BOOT + RECONNECT")
            verified_title.setObjectName("Good")
            verified_detail = QLabel(
                "The incident is green because current evidence satisfied the reboot boundary—not because a button was clicked or time elapsed."
            )
            verified_detail.setObjectName("Muted")
            verified_detail.setWordWrap(True)
            verified_layout.addWidget(verified_title)
            verified_layout.addWidget(verified_detail)
            self.autopilot_routes_layout.addWidget(verified)
        self.autopilot_boundary.setText(
            "VERIFIED RECOVERED • SAME DEVICE • AUTHORIZED ADB • BOOT COMPLETED • "
            "INCIDENT HISTORY SEALED"
            if incident.repaired
            else "RANKING IS ADVISORY • ARCHIVES GRANT NO EXECUTION AUTHORITY • DEVICE CHANGES "
            "REQUIRE A TYPED OWNER AND CONFIRMATION • RECOVERED REQUIRES FRESH BOOT + RECONNECT PROOF"
        )
        self.autopilot_scan_button.setVisible(not incident.repaired)

    def _add_autopilot_route(self, route: RecoveryRoute) -> None:
        card = QFrame()
        card.setObjectName("RecoveryVerification")
        card.setProperty(
            "state",
            "attention"
            if route.changes_device or route.risk.value in {"high", "destructive"}
            else "active",
        )
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        copy = QVBoxLayout()
        rank = QLabel(
            f"ROUTE {route.rank:02d}  •  {route.confidence}% CONFIDENCE  •  "
            f"{route.risk.value.upper()} RISK"
        )
        rank.setObjectName("Eyebrow")
        title = QLabel(route.title)
        title.setObjectName("SectionTitle")
        title.setWordWrap(True)
        summary = QLabel(route.summary)
        summary.setObjectName("Muted")
        summary.setWordWrap(True)
        boundary = QLabel(
            "PHONE CHANGE • YES • CONFIRMATION REQUIRED • EXECUTION AUTHORITY • NONE"
            if route.changes_device
            else f"PHONE CHANGE • NO • EXECUTION AUTHORITY • {route.execution_authority.upper()}"
        )
        boundary.setObjectName("Warning" if route.changes_device else "Good")
        boundary.setWordWrap(True)
        copy.addWidget(rank)
        copy.addWidget(title)
        copy.addWidget(summary)
        copy.addWidget(boundary)
        layout.addLayout(copy, 1)
        button = QPushButton("Review route")
        button.setObjectName("Primary" if route.rank == 1 else "")
        button.setAccessibleName(f"Review Recovery Autopilot route {route.rank}: {route.title}")
        button.setToolTip(
            "Revalidates this incident route and opens its typed owner. It does not infer or run a phone command."
        )
        button.clicked.connect(
            lambda _checked=False, route_id=route.route_id: self._review_autopilot_route(
                route_id
            )
        )
        layout.addWidget(button)
        self.autopilot_route_buttons.append(button)
        self.autopilot_routes_layout.addWidget(card)

    def _review_autopilot_route(self, route_id: str) -> None:
        service = self.autopilot_service
        incident = self.autopilot_incident
        if service is None or incident is None:
            return
        try:
            incident = service.load(incident.incident_id)
            route = next((item for item in incident.routes if item.route_id == route_id), None)
            if route is None:
                raise RecoveryAutopilotError("Recovery route no longer matches fresh evidence")
            self.autopilot_incident = service.record_route_result(
                incident.incident_id,
                route.route_id,
                "reviewed",
                "The user opened the typed route owner; no action was started by the ranking.",
            )
        except RecoveryAutopilotError as exc:
            self.digest.setText(f"Recovery route review stopped safely  •  {exc}")
            return
        self._render_autopilot()
        if route.kind is RecoveryRouteKind.HOST_ADB_REPAIR and self.host_repair_plan is not None:
            self._run_host_repair()
            return
        if route.owner_route != "recovery_bay":
            self.autopilot_route_requested.emit(route.owner_route, route.route_id)
            return
        detail = "\n".join(
            (
                route.summary,
                "",
                "Required evidence:",
                *(f"• {item}" for item in route.requirements),
                "",
                "This review did not start a phone action.",
            )
        )
        QMessageBox.information(self, route.title, detail)

    def _show_autopilot_timeline(self) -> None:
        incident = self.autopilot_incident
        if incident is None:
            return
        event_rows = [
            f"{event.sequence:02d}  •  {event.observed_at}  •  {event.mode.upper()}  •  "
            f"{event.title}\n{event.detail}\nEvidence SHA-256 {event.evidence_digest[:20]}…"
            for event in incident.events
        ]
        route_rows = [
            f"{route.rank:02d}  •  {route.risk.value.upper()} RISK  •  "
            f"{route.confidence}% CONFIDENCE  •  {route.title}\n"
            f"{route.summary}\n"
            f"Phone change: {'yes' if route.changes_device else 'no'}  •  "
            f"Confirmation: {'required' if route.confirmation_required else 'not required'}  •  "
            f"Execution authority: {route.execution_authority}\n"
            "Required evidence: " + "; ".join(route.requirements)
            for route in incident.routes
        ]
        QMessageBox.information(
            self,
            "Recovery Autopilot • incident timeline + ranked routes",
            "INCIDENT TIMELINE\n\n"
            + "\n\n".join(event_rows)
            + (
                "\n\nCURRENT RANKED ROUTES\n\n" + "\n\n".join(route_rows)
                if route_rows
                else ""
            )
            + "\n\nPrivacy: local pseudonymous evidence; raw device serial is not stored.",
        )

    def _toggle_autopilot_routes(self) -> None:
        self._autopilot_show_all_routes = not self._autopilot_show_all_routes
        self._render_autopilot()

    def _request_autopilot_scan(self) -> None:
        if self.autopilot_incident is None or self.autopilot_incident.repaired:
            return
        self.digest.setText(
            "Recovery Autopilot requested a fresh read-only Device Engine scan • phone changes: none"
        )
        self.verification_scan_requested.emit()

    def set_devices(self, devices: list[AndroidDevice]) -> None:
        self.devices = devices
        self.device_selector.blockSignals(True)
        self.device_selector.clear()
        for device in devices:
            self.device_selector.addItem(f"{device.display_name}  •  {device.masked_serial()}")
        authorized_index = next(
            (index for index, device in enumerate(devices) if device.state is DeviceState.DEVICE),
            0,
        )
        if devices:
            self.device_selector.setCurrentIndex(authorized_index)
        self.device_selector.setVisible(len(devices) > 1)
        self.device_selector.blockSignals(False)
        authorized = any(device.state is DeviceState.DEVICE for device in devices)
        self.build_button.setEnabled(bool(devices))
        self.execute_button.setEnabled(bool(devices))
        self.session_button.setEnabled(authorized and self.session_store is not None)
        if devices:
            if self._pending_verification_session:
                self._complete_pending_verification(devices)
            self.build_plan()
            self._refresh_autopilot(self.current_device)
        else:
            self._clear_intelligence_action()
            self._clear_diagnostic_context()
            self.host_action_card.setVisible(False)
            self.host_repair_plan = None
            self.host_repair_button = None
            self.plan_title.setText("No device available")
            self.plan_summary.setText("Connect and authorize a device, then refresh Device Portal.")
            self._set_badge("BLOCKED", "Danger")
            self.digest.clear()
            self._report_payload = None
            self.current_device = None
            self.current_report = None
            self.current_concern = None
            self.active_session = None
            self.export_button.setEnabled(False)
            self.session_button.setEnabled(False)
            self.execute_button.setEnabled(False)
            self._empty(
                "Guardian will not construct a repair plan without current device evidence."
            )
            self._refresh_autopilot(None)

    def set_host_repair_service(self, service: AdbHostRepairService | None) -> None:
        """Apply the currently verified host ADB runtime without retaining stale plans."""

        self.resolve_runtime_button.setVisible(service is None)
        if self.host_repair_service is service:
            return
        self.host_repair_service = service
        self.host_repair_plan = None
        self._refresh_autopilot(self.current_device)
        if self.host_repair_worker is not None:
            # The running worker owns the exact previously approved service and
            # plan. Its terminal callback requests a fresh scan, which rebuilds
            # this card against the new runtime.
            return
        self._configure_host_repair(
            device=self.current_device,
            concern=self.current_concern,
        )

    def _request_runtime_tools(self) -> None:
        self.plan_title.setText("Resolving Device Engine runtime…")
        self.plan_summary.setText(
            "ROMVERSE is verifying managed Android Platform Tools. A fresh read-only scan starts automatically after verification."
        )
        self.runtime_tools_requested.emit()
        if self.host_repair_service is None:
            self.plan_title.setText("Platform Tools still need attention")
            self.plan_summary.setText(
                "ROMVERSE did not obtain a freshly verified ADB runtime. No diagnostic or phone-changing action was started."
            )

    def show_error(self, message: str) -> None:
        self._clear_diagnostic_context()
        safe_message = message.replace("\x00", " ").strip()[:300] or "ADB discovery failed"
        self._scan_offline_host_failure(safe_message)
        self.host_action_card.setVisible(False)
        self.host_repair_plan = None
        self.host_repair_button = None
        self._maybe_research(
            ErrorFingerprint.create(
                safe_message,
                category="adb-host",
                tool_name="ADB",
            )
        )
        self.devices = []
        self.build_button.setEnabled(False)
        self.execute_button.setEnabled(False)
        self.plan_title.setText("Preflight unavailable")
        self.plan_summary.setText(safe_message)
        self._set_badge("BLOCKED", "Danger")
        self.digest.clear()
        self._report_payload = None
        self.export_button.setEnabled(False)
        self.host_repair_plan = None
        if self.host_repair_service is None:
            self._empty(
                "Resolve Device Engine access before creating a repair assessment.",
                add_stretch=False,
            )
            if self.offline_service is not None:
                self._render_offline_knowledge()
            self.body_layout.addStretch()
            return
        try:
            self.host_repair_plan = self.host_repair_service.plan(
                AdbHostRepairMode.RESTART,
                f"Device Engine scan failed: {safe_message}",
            )
        except AdbHostRepairError as exc:
            self._empty(f"ADB host recovery is unavailable: {exc}", add_stretch=False)
            if self.offline_service is not None:
                self._render_offline_knowledge()
            self.body_layout.addStretch()
            return
        self._clear()
        failure = QFrame()
        failure.setObjectName("Card")
        failure_layout = QVBoxLayout(failure)
        failure_copy = QLabel(
            "ROMVERSE could not complete ADB discovery. It can restart only the host ADB daemon, "
            "verify that daemon with a fresh device-list check, and then rescan."
        )
        failure_copy.setObjectName("Muted")
        failure_copy.setWordWrap(True)
        failure_layout.addWidget(failure_copy)
        self.body_layout.addWidget(failure)
        if self.offline_service is not None:
            self._render_offline_knowledge()
        self._render_host_repair(self.host_repair_plan)
        self.body_layout.addStretch()

    def build_plan(self, _index: int = -1, *, start_research: bool = True) -> None:
        index = self.device_selector.currentIndex()
        if not 0 <= index < len(self.devices):
            index = 0
        if not self.devices:
            return
        raw_concern = self.concern_selector.currentData()
        try:
            concern = (
                raw_concern
                if isinstance(raw_concern, RepairConcern)
                else RepairConcern(str(raw_concern))
            )
        except ValueError:
            concern = RepairConcern.BATTERY_HEAT
        device = self.devices[index]
        report = self.analyzer.analyze(device)
        self.current_device = device
        self.current_report = report
        self.current_concern = concern
        self._scan_offline_knowledge(device, report, concern)
        self.active_session = self._matching_session(device, concern)
        manifest = self.templates.build(concern, device, report)
        assessment = self.preflight.assess(manifest)
        self._render(manifest, assessment, report, concern)
        fingerprint = self._repair_fingerprint(device, report, concern)
        if fingerprint is not None:
            if start_research:
                self._maybe_research(fingerprint)
            else:
                self._online_current = fingerprint
                if self.online_service is None:
                    self._maybe_research(fingerprint)
                elif self.online_worker is None:
                    self.intelligence_card.setVisible(False)
        elif self.online_worker is None:
            self.intelligence_card.setVisible(False)

    def open_diagnostic_finding(self, finding_id: str) -> bool:
        """Select an exact repair concern from current typed diagnostic evidence."""

        normalized = finding_id.strip()[:120]
        concern = concern_for_finding(normalized)
        report = self.current_report
        finding = (
            next((item for item in report.findings if item.finding_id == normalized), None)
            if report is not None
            else None
        )
        if concern is None or finding is None:
            self._clear_diagnostic_context()
            return False
        index = self.concern_selector.findData(concern.value)
        if index < 0:
            self._clear_diagnostic_context()
            return False
        self._diagnostic_context_id = normalized
        self.diagnostic_context.setText(
            f"FROM QUANTUM OPTIMIZER  •  {normalized.upper()}  •  {finding.title.upper()}  "
            "•  CONTEXT ONLY — NO ACTION STARTED"
        )
        self.diagnostic_source_button.setVisible(True)
        self.diagnostic_context.setVisible(True)
        self.diagnostic_context_row.setVisible(True)
        self._applying_diagnostic_context = True
        try:
            if self.concern_selector.currentIndex() == index:
                self.build_plan(index, start_research=False)
            else:
                self.concern_selector.setCurrentIndex(index)
        finally:
            self._applying_diagnostic_context = False
        return True

    def open_general_assessment(self, *, evidence_changed: bool = False) -> None:
        """Present a no-action general intake when no exact current route can be proven."""

        self._clear_diagnostic_context()
        self.diagnostic_context.setAccessibleName("Command Deck general Recovery Bay intake")
        self.diagnostic_context.setText(
            "FROM COMMAND DECK  •  "
            + (
                "EXACT DIAGNOSTIC NEEDS FRESH EVIDENCE  •  REFRESH OR CHOOSE A PROBLEM"
                if evidence_changed
                else "NO CURRENT ACTIONABLE DIAGNOSTIC  •  CHOOSE A PROBLEM CATEGORY"
            )
            + "  •  NO ACTION STARTED"
        )
        self.diagnostic_source_button.setVisible(False)
        self.diagnostic_context.setVisible(True)
        self.diagnostic_context_row.setVisible(True)

    def open_session(self, session_id: str) -> bool:
        """Reverify and display one exact historical repair session without resuming it."""

        if self.session_store is None:
            return False
        try:
            session = self.session_store.load(session_id)
        except RepairSessionError:
            return False
        if not session.integrity_verified or session.session_id != session_id:
            return False
        verification = (
            f"  •  verification {session.verification_direction}  •  "
            f"health {session.initial_health_score} → {session.verification_health_score}"
            if session.verification_health_score is not None
            else "  •  fresh verification not yet recorded"
        )
        self.session_context_title.setText(
            f"{session.concern}  •  {session.status.replace('_', ' ')}"
        )
        self.session_context_detail.setText(
            f"Session {session.session_id}  •  {session.device_name}  •  "
            f"{len(session.reviewed_steps)}/{len(session.recommendations)} checkpoints reviewed"
            f"{verification}\n"
            f"Record SHA-256 {session.record_digest[:20]}…  •  Historical evidence only; "
            "no repair, verification scan, approval, or device action resumed."
        )
        self.session_context_badge.setText(
            "VERIFIED RESULT" if session.status == "verified" else "READ-ONLY EVIDENCE"
        )
        self.session_context_badge.setObjectName(
            "Good" if session.status == "verified" else "Warning"
        )
        self.session_context_badge.style().unpolish(self.session_context_badge)
        self.session_context_badge.style().polish(self.session_context_badge)
        self.session_context_row.setVisible(True)
        return True

    def show_diagnostic_handoff_error(self, finding_id: str) -> None:
        """Keep a failed source return visible when optional toasts are disabled."""

        normalized = finding_id.strip()[:120] or "unknown finding"
        self._clear_diagnostic_context()
        self.diagnostic_context.setAccessibleName(
            "Recovery Bay source handoff needs fresh evidence"
        )
        self.diagnostic_context.setText(
            f"SOURCE RETURN STOPPED  •  {normalized.upper()} IS NOT IN THE CURRENT REPORT  •  "
            "REFRESH DEVICE EVIDENCE  •  NO ACTION STARTED"
        )
        self.diagnostic_source_button.setVisible(False)
        self.diagnostic_context.setVisible(True)
        self.diagnostic_context_row.setVisible(True)

    def _concern_changed(self, index: int) -> None:
        if not self._applying_diagnostic_context:
            self._clear_diagnostic_context()
        self.build_plan(index, start_research=not self._applying_diagnostic_context)

    def _clear_diagnostic_context(self) -> None:
        self._diagnostic_context_id = ""
        self.diagnostic_context.clear()
        self.diagnostic_context.setAccessibleName("Quantum Optimizer diagnostic handoff")
        self.diagnostic_context.setVisible(False)
        self.diagnostic_source_button.setVisible(True)
        self.diagnostic_context_row.setVisible(False)

    def _request_diagnostic_source(self) -> None:
        if self._diagnostic_context_id:
            self.diagnostic_requested.emit(self._diagnostic_context_id)

    def _scan_offline_knowledge(
        self,
        device: AndroidDevice,
        report: DiagnosticReport,
        concern: RepairConcern,
    ) -> None:
        """Automatically rank the private archive from the current read-only evidence."""

        self.offline_report = None
        self.offline_error = ""
        self._offline_query_text = ""
        if self.offline_service is None:
            return

        def values(*items: str) -> tuple[str, ...]:
            return tuple(
                dict.fromkeys(
                    item.replace("\x00", " ").strip()[:500]
                    for item in items
                    if item and item.replace("\x00", " ").strip()
                )
            )

        typed = self.symptom_input.text().replace("\x00", " ").strip()[:600]
        self._offline_query_text = typed
        finding_text = tuple(
            f"{finding.title}. {finding.explanation}" for finding in report.findings
        )
        symptoms = values(typed, *device.errors[:6], *finding_text)
        finding_ids = values(*(finding.finding_id for finding in report.findings))
        bootloader_state = (
            "locked"
            if device.bootloader_locked is True
            else "unlocked"
            if device.bootloader_locked is False
            else ""
        )
        query = KnowledgeQuery(
            manufacturers=values(device.manufacturer),
            brands=values(device.brand),
            models=values(device.model, device.marketing_name),
            codenames=values(device.codename, device.product, device.vendor_device),
            build_ids=values(device.rom_display, device.build_id, device.build_incremental),
            android_versions=values(device.android_version),
            bootloader_states=values(bootloader_state),
            symptoms=symptoms,
            finding_ids=finding_ids,
            evidence_terms=values(
                concern.value,
                f"Android state {device.state.value}",
                *(finding.guidance for finding in report.findings),
            ),
        )
        try:
            self.offline_report = self.offline_service.lookup(
                query,
                trigger="recovery-bay",
                limit=5,
            )
        except (OSError, TypeError, ValueError) as exc:
            self.offline_error = str(exc)[:500]

    def _scan_offline_host_failure(self, message: str) -> None:
        """Diagnose an ADB discovery failure without requiring a device snapshot."""

        self.offline_report = None
        self.offline_error = ""
        self._offline_query_text = message
        if self.offline_service is None:
            return
        try:
            self.offline_report = self.offline_service.scan_after_failure(
                None,
                KnowledgeFailure(
                    phase="device-discovery",
                    message=message,
                    finding_ids=("adb.host.discovery",),
                    operation="Read-only ADB device discovery",
                ),
                limit=5,
            )
        except (OSError, TypeError, ValueError) as exc:
            self.offline_error = str(exc)[:500]

    def _render(
        self,
        manifest: OperationManifest,
        assessment: PreflightAssessment,
        report: DiagnosticReport | None = None,
        concern: RepairConcern | None = None,
    ) -> None:
        self.plan_title.setText(manifest.title)
        self.plan_summary.setText("  •  ".join(assessment.reasons))
        style = {
            PreflightStatus.READY: "Good",
            PreflightStatus.REVIEW: "Warning",
            PreflightStatus.BLOCKED: "Danger",
        }[assessment.status]
        self._set_badge(
            f"{assessment.status.value.upper()} • {assessment.risk.value.upper()} RISK",
            style,
        )
        self.digest.setText(f"Immutable plan fingerprint  •  SHA-256 {assessment.manifest_digest}")
        entry = knowledge_for(concern) if concern is not None else None
        archive_recommendations = (
            recommend_for_repair(
                concern,
                self.symptom_input.text(),
                report.findings if report is not None else (),
                manufacturer=(
                    self.current_device.manufacturer if self.current_device is not None else ""
                ),
                limit=3,
            )
            if concern is not None
            else ()
        )
        active_pack = (
            self.pack_registry.resolve(self.current_device).pack
            if self.current_device is not None
            else None
        )
        self._report_payload = {
            "schema_version": 1,
            "privacy": "local-report; serials omitted",
            "plan": {
                "manifest_id": manifest.manifest_id,
                "created_at": manifest.created_at,
                "title": manifest.title,
                "concern": manifest.concern,
                "digest": assessment.manifest_digest,
                "guardian_status": assessment.status.value,
                "risk": assessment.risk.value,
                "approval_required": assessment.approval_required,
                "execution_locked": assessment.execution_locked,
            },
            "findings": [
                {
                    "severity": finding.severity.value,
                    "title": finding.title,
                    "explanation": finding.explanation,
                    "guidance": finding.guidance,
                }
                for finding in (report.findings if report is not None else ())
            ],
            "evidence": [
                {"label": item.label, "value": item.value, "source": item.source}
                for item in (report.evidence if report is not None else ())
            ],
            "recommendations": list(entry.recommended_steps) if entry is not None else [],
            "archive_recommendations": [
                {
                    "article_key": recommendation.article.key,
                    "title": recommendation.article.title,
                    "reason": recommendation.reason,
                    "source": recommendation.article.source.label,
                    "source_authority": recommendation.article.source.authority,
                    "source_url": recommendation.article.source.url,
                    "automation_boundary": recommendation.article.automation,
                }
                for recommendation in archive_recommendations
            ],
            "offline_knowledge": (
                {
                    "trigger": self.offline_report.trigger,
                    "query_digest": self.offline_report.query_digest,
                    "archive_digest": self.offline_report.archive_digest,
                    "execution_authority": self.offline_report.execution_authority,
                    "matches": [
                        {
                            "record_id": match.record.record_id,
                            "title": match.record.title,
                            "match_confidence": match.confidence.value,
                            "record_confidence": match.record.confidence.value,
                            "corroboration_count": match.record.corroboration_count,
                            "source_ids": list(match.record.source_ids),
                        }
                        for match in self.offline_report.matches
                    ],
                }
                if self.offline_report is not None
                else {
                    "unavailable": bool(self.offline_error),
                    "execution_authority": "none",
                }
            ),
            "device_pack": (
                {
                    "pack_id": active_pack.pack_id,
                    "version": active_pack.version,
                    "sha256": active_pack.sha256,
                    "knowledge_sources": [
                        {
                            "source_id": source.source_id,
                            "label": source.label,
                            "authority": source.authority,
                            "scope": source.scope,
                            "verified_on": source.verified_on,
                            "url": source.url,
                        }
                        for source in active_pack.knowledge_sources
                    ],
                    "execution_authority": "none",
                }
                if active_pack is not None
                else None
            ),
            "limitations": list(report.limitations) if report is not None else [],
        }
        self.export_button.setEnabled(True)
        self._clear()

        heading = QLabel("Preconditions")
        heading.setObjectName("SectionTitle")
        self.body_layout.addWidget(heading)
        checks = QHBoxLayout()
        for precondition in manifest.preconditions:
            card = QFrame()
            card.setObjectName("Card")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(16, 14, 16, 14)
            status = QLabel(precondition.status.value.upper())
            status.setObjectName(
                "Good"
                if precondition.status is CheckStatus.PASS
                else "Danger"
                if precondition.status is CheckStatus.FAIL
                else "Warning"
            )
            title = QLabel(precondition.title)
            title.setWordWrap(True)
            evidence = QLabel(precondition.evidence)
            evidence.setObjectName("Muted")
            evidence.setWordWrap(True)
            layout.addWidget(status)
            layout.addWidget(title)
            layout.addWidget(evidence)
            checks.addWidget(card, 1)
        check_host = QWidget()
        check_host.setLayout(checks)
        self.body_layout.addWidget(check_host)

        if archive_recommendations:
            self._render_archive_advisor(archive_recommendations)
        if self.offline_service is not None:
            self._render_offline_knowledge()

        # Offline repair playbook: explain the issue, evidence, and next actions
        # in plain language alongside the Guardian preflight.  This remains
        # model-agnostic and intentionally never executes device changes.
        if concern is not None:
            entry = knowledge_for(concern)
            knowledge_heading = QLabel("Offline repair playbook")
            knowledge_heading.setObjectName("SectionTitle")
            self.body_layout.addWidget(knowledge_heading)
            overview = QLabel(entry.overview)
            overview.setWordWrap(True)
            self.body_layout.addWidget(overview)
            columns = QHBoxLayout()
            for title, values in (
                ("Likely causes", entry.likely_causes),
                ("Evidence to collect", entry.evidence_to_collect),
                ("Recommended next steps", entry.recommended_steps),
            ):
                card = QFrame()
                card.setObjectName("Card")
                layout = QVBoxLayout(card)
                layout.setContentsMargins(16, 14, 16, 14)
                label = QLabel(title)
                label.setObjectName("SectionTitle")
                layout.addWidget(label)
                for value in values:
                    item = QLabel(f"• {value}")
                    item.setWordWrap(True)
                    item.setObjectName("Muted")
                    layout.addWidget(item)
                columns.addWidget(card, 1)
            playbook_host = QWidget()
            playbook_host.setLayout(columns)
            self.body_layout.addWidget(playbook_host)
            risk = QLabel(f"Safety note  •  {entry.risk_note}")
            risk.setObjectName("Warning")
            risk.setWordWrap(True)
            self.body_layout.addWidget(risk)
            automation = QLabel(f"Safe automation  •  {entry.safe_automation}")
            automation.setObjectName("Muted")
            automation.setWordWrap(True)
            self.body_layout.addWidget(automation)
            if active_pack is not None:
                pack_card = QFrame()
                pack_card.setObjectName("Card")
                pack_layout = QVBoxLayout(pack_card)
                pack_layout.setContentsMargins(16, 14, 16, 14)
                pack_title = QLabel(f"Source-backed OEM context  •  {active_pack.display_name}")
                pack_title.setObjectName("SectionTitle")
                pack_copy = QLabel(
                    "ROMVERSE uses this integrity-checked Pack to explain OEM boundaries. "
                    "It does not grant repair, unlock, build, recovery, or flash authority."
                )
                pack_copy.setObjectName("Muted")
                pack_copy.setWordWrap(True)
                pack_layout.addWidget(pack_title)
                pack_layout.addWidget(pack_copy)
                if active_pack.knowledge_sources:
                    for source in active_pack.knowledge_sources:
                        link = QLabel(
                            f'• <a style="color:#43DDF2" href="{html.escape(source.url, quote=True)}">'
                            f"{html.escape(source.label)}</a>  —  "
                            f"{html.escape(source.scope)} (checked {source.verified_on})"
                        )
                        link.setOpenExternalLinks(True)
                        link.setWordWrap(True)
                        link.setObjectName("Muted")
                        pack_layout.addWidget(link)
                else:
                    no_sources = QLabel(
                        "No OEM-specific source is bundled for this Pack; guidance remains model-agnostic."
                    )
                    no_sources.setObjectName("Warning")
                    no_sources.setWordWrap(True)
                    pack_layout.addWidget(no_sources)
                self.body_layout.addWidget(pack_card)
            self._render_guided_session(entry.recommended_steps)

        if report is not None:
            findings_heading = QLabel("Current issue description")
            findings_heading.setObjectName("SectionTitle")
            self.body_layout.addWidget(findings_heading)
            for finding in report.findings:
                finding_card = QFrame()
                finding_card.setObjectName("Card")
                finding_layout = QVBoxLayout(finding_card)
                finding_layout.setContentsMargins(16, 12, 16, 12)
                finding_title = QLabel(f"{finding.severity.value.upper()}  •  {finding.title}")
                finding_title.setObjectName(
                    "Danger" if finding.severity.value in {"critical", "warning"} else "Good"
                )
                explanation = QLabel(finding.explanation)
                explanation.setWordWrap(True)
                guidance = QLabel(f"Recommended response  •  {finding.guidance}")
                guidance.setObjectName("Muted")
                guidance.setWordWrap(True)
                finding_layout.addWidget(finding_title)
                finding_layout.addWidget(explanation)
                finding_layout.addWidget(guidance)
                self.body_layout.addWidget(finding_card)

        workflow = QLabel("Dry-run workflow")
        workflow.setObjectName("SectionTitle")
        self.body_layout.addWidget(workflow)
        for number, step in enumerate(manifest.steps, start=1):
            card = QFrame()
            card.setObjectName("Card")
            layout = QHBoxLayout(card)
            layout.setContentsMargins(18, 14, 18, 14)
            number_label = QLabel(f"{number:02}")
            number_label.setObjectName("Eyebrow")
            detail = QVBoxLayout()
            title = QLabel(step.title)
            title.setObjectName("SectionTitle")
            purpose = QLabel(step.purpose)
            purpose.setObjectName("Muted")
            purpose.setWordWrap(True)
            effect = QLabel(f"Expected effect  •  {step.expected_effect}")
            effect.setObjectName("Muted")
            effect.setWordWrap(True)
            detail.addWidget(title)
            detail.addWidget(purpose)
            detail.addWidget(effect)
            category = QLabel(step.category.value.replace("_", " ").upper())
            category.setObjectName("Good" if step.category.value == "read_only" else "Warning")
            layout.addWidget(number_label)
            layout.addSpacing(8)
            layout.addLayout(detail, 1)
            layout.addWidget(category)
            self.body_layout.addWidget(card)
        self._configure_host_repair(device=self.current_device, concern=concern)
        self.body_layout.addStretch()

    def _render_offline_knowledge(self) -> None:
        card = QFrame()
        card.setObjectName("HeroCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 17, 20, 17)
        header = QHBoxLayout()
        title = QLabel("OFFLINE ARCHIVES BRAIN  •  AUTOMATIC EVIDENCE MATCH")
        title.setObjectName("Eyebrow")
        header.addWidget(title)
        header.addStretch()
        report = self.offline_report
        status = QLabel()
        if report is None:
            status.setText("UNAVAILABLE")
            status.setObjectName("Warning")
        elif report.conflicts:
            status.setText(
                f"{len(report.conflicts)} CONFLICT"
                f"{'S' if len(report.conflicts) != 1 else ''} • REVIEW REQUIRED"
            )
            status.setObjectName("Warning")
        elif report.matches:
            status.setText(
                f"{len(report.matches)} COMPATIBLE MATCH{'ES' if len(report.matches) != 1 else ''}"
            )
            status.setObjectName("Good")
        else:
            status.setText("NO COMPATIBLE MATCH")
            status.setObjectName("Warning")
        header.addWidget(status)
        layout.addLayout(header)

        if report is None:
            detail = QLabel(
                "The integrity-checked offline archive could not be queried. ROMVERSE kept the "
                "failure separate from the device assessment and did not guess a repair."
            )
            detail.setObjectName("Warning")
            detail.setWordWrap(True)
            layout.addWidget(detail)
        elif not report.matches:
            detail = QLabel(
                "No record matched the current device, build, symptom, and diagnostic evidence. "
                "The cause remains unknown; collect more exact evidence before taking action."
            )
            detail.setObjectName("Muted")
            detail.setWordWrap(True)
            layout.addWidget(detail)
        else:
            if report.conflicts:
                conflict = QLabel(
                    "CONFLICTING GUIDANCE • STOP BEFORE DEVICE CHANGES\n"
                    f"{report.safest_answer}"
                )
                conflict.setObjectName("Warning")
                conflict.setWordWrap(True)
                layout.addWidget(conflict)
            for index, match in enumerate(report.matches[:3], 1):
                source_names = ", ".join(source.label for source in match.provenance)
                match_title = QLabel(
                    f"{index}. {match.record.title}  •  {match.confidence.value.upper()} MATCH"
                )
                match_title.setObjectName("SectionTitle")
                match_title.setWordWrap(True)
                match_detail = QLabel(
                    f"{match.explanation}\n"
                    f"Scope: {match.record.scope.scope_note or 'Not specified'}\n"
                    f"Record confidence: {match.record.confidence.value}  •  "
                    f"corroborated outcome/report count: {match.record.corroboration_count}\n"
                    f"Sources: {source_names or 'No valid provenance'}"
                )
                match_detail.setObjectName("Muted")
                match_detail.setWordWrap(True)
                layout.addWidget(match_title)
                layout.addWidget(match_detail)
            open_matches = QPushButton("Review all matching offline evidence")
            open_matches.setObjectName("Primary")
            open_matches.setToolTip(
                "Open ROMVERSE Archives with this exact symptom. This starts no repair, "
                "command, flash, wipe, or phone action."
            )
            query = (
                self._offline_query_text[:160]
                or self.symptom_input.text().replace("\x00", " ").strip()[:160]
                or report.matches[0].record.title[:160]
            )
            open_matches.clicked.connect(
                lambda _checked=False, value=query: self.knowledge_requested.emit(value)
            )
            layout.addWidget(open_matches, 0, Qt.AlignmentFlag.AlignLeft)
        boundary = QLabel(
            "LOCAL EVIDENCE: GUIDANCE ONLY  •  EXECUTION AUTHORITY: NONE  •  PHONE CHANGES: NONE"
        )
        boundary.setObjectName("Warning")
        boundary.setWordWrap(True)
        layout.addWidget(boundary)
        self.body_layout.addWidget(card)

    def _render_archive_advisor(
        self,
        recommendations: tuple[ArchiveRecommendation, ...],
    ) -> None:
        primary = recommendations[0]
        card = QFrame()
        card.setObjectName("HeroCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 17, 20, 17)
        heading = QHBoxLayout()
        title = QLabel("ROMVERSE ARCHIVES ADVISOR")
        title.setObjectName("Eyebrow")
        status = QLabel(
            f"{len(recommendations)} VERIFIED MATCH{'ES' if len(recommendations) != 1 else ''}"
        )
        status.setObjectName("Good")
        heading.addWidget(title)
        heading.addStretch()
        heading.addWidget(status)
        heading.addSpacing(10)
        open_article = QPushButton("Open verified Archives guide")
        open_article.setObjectName("Primary")
        open_article.setAccessibleName(f"Open verified Archives guide: {primary.article.title}")
        open_article.setToolTip(
            "Open the exact local guide selected from this repair assessment. "
            "No device change starts automatically."
        )
        open_article.clicked.connect(
            lambda _checked=False, key=primary.article.key: self.knowledge_article_requested.emit(
                key
            )
        )
        heading.addWidget(open_article)
        layout.addLayout(heading)

        article_title = QLabel(primary.article.title)
        article_title.setObjectName("HeroTitle")
        article_title.setWordWrap(True)
        layout.addWidget(article_title)
        context = QLabel(
            f"{primary.reason}  •  {primary.article.source.authority}\n{primary.article.meaning}"
        )
        context.setObjectName("Muted")
        context.setWordWrap(True)
        layout.addWidget(context)
        if len(recommendations) > 1:
            related = QLabel(
                "Also matched  •  "
                + "  |  ".join(item.article.title for item in recommendations[1:])
            )
            related.setObjectName("Muted")
            related.setWordWrap(True)
            layout.addWidget(related)
        boundary = QLabel(primary.article.automation)
        boundary.setObjectName("Warning")
        boundary.setWordWrap(True)
        layout.addWidget(boundary)
        self.body_layout.addWidget(card)

    def _configure_host_repair(
        self,
        *,
        device: AndroidDevice | None,
        concern: RepairConcern | None,
    ) -> None:
        self.host_repair_plan = None
        self.host_repair_button = None
        self.host_action_card.setVisible(False)
        if (
            self.host_repair_service is None
            or concern is not RepairConcern.USB_ADB
            or device is None
        ):
            return
        if device.state is DeviceState.UNAUTHORIZED:
            self._render_host_repair(
                None,
                unavailable_reason=(
                    "The phone is waiting for its on-screen RSA authorization. Restarting the host "
                    "daemon cannot accept that prompt for you; unlock the phone and choose Allow."
                ),
            )
            return
        if device.state is DeviceState.DEVICE and not device.errors:
            self._render_host_repair(
                None,
                unavailable_reason=(
                    "ADB is authorized and the required read-only probes completed. ROMVERSE will not "
                    "restart a healthy host daemon without evidence that it is needed."
                ),
            )
            return
        try:
            self.host_repair_plan = self.host_repair_service.plan(
                AdbHostRepairMode.RESTART,
                f"ADB state {device.state.value}; {len(device.errors)} detailed probe error(s)",
            )
        except AdbHostRepairError as exc:
            self._render_host_repair(None, unavailable_reason=str(exc))
            return
        self._render_host_repair(self.host_repair_plan)

    def _render_host_repair(
        self,
        plan: AdbHostRepairPlan | None,
        *,
        unavailable_reason: str = "",
    ) -> None:
        self.host_action_card.setVisible(True)
        if plan is None:
            state = (
                "NO SAFE AUTOMATIC ACTION NEEDED"
                if "healthy" in unavailable_reason
                else "USER ACTION REQUIRED"
            )
            self.host_action_state.setText(state)
            self.host_action_state.setObjectName(
                "Good" if "healthy" in unavailable_reason else "Warning"
            )
            self.host_action_detail.setText(unavailable_reason)
            self.host_action_fingerprint.clear()
            self._host_action_button.setVisible(False)
            self.host_repair_button = None
            self._refresh_host_action_style()
            return
        self.host_action_state.setText("GUARDIAN REVIEW READY • HOST ONLY")
        self.host_action_state.setObjectName("Warning")
        self.host_action_detail.setText(
            "This action temporarily restarts the computer's ADB daemon, verifies it with `adb "
            "devices -l`, and requests a fresh ROMVERSE scan. It cannot run `adb -s`, cannot "
            "change phone data, and never permits bootloader relocking. Other ADB clients may "
            "disconnect briefly."
        )
        self.host_action_fingerprint.setText(f"Exact plan SHA-256  •  {plan.digest()}")
        self._host_action_button.setVisible(True)
        self._host_action_button.setEnabled(self.host_repair_worker is None)
        self._host_action_button.setObjectName("Primary")
        self.host_repair_button = self._host_action_button
        self._refresh_host_action_style()

    def _refresh_host_action_style(self) -> None:
        for widget in (self.host_action_state, self._host_action_button):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _run_host_repair(self) -> None:
        service = self.host_repair_service
        plan = self.host_repair_plan
        if service is None or plan is None or self.host_repair_worker is not None:
            return
        answer = QMessageBox.warning(
            self,
            "Approve ADB host recovery",
            "ROMVERSE will temporarily restart the ADB daemon on this computer.\n\n"
            "Other ADB tools may disconnect briefly. No command will target the phone, no phone "
            "data will change, and bootloader relocking remains permanently forbidden.\n\n"
            f"Plan SHA-256: {plan.digest()[:24]}…\n\nContinue?",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            self._record_autopilot_route_result(
                RecoveryRouteKind.HOST_ADB_REPAIR,
                "declined",
                "Host ADB recovery was declined; no action started.",
            )
            return
        self._record_autopilot_route_result(
            RecoveryRouteKind.HOST_ADB_REPAIR,
            "confirmed",
            "The exact host-only ADB plan was confirmed; no phone command is permitted.",
        )
        try:
            service.approve(plan)
        except Exception as exc:
            self.digest.setText(f"Guardian could not approve ADB host recovery  •  {exc}")
            self._record_autopilot_route_result(
                RecoveryRouteKind.HOST_ADB_REPAIR,
                "failed",
                f"Guardian could not approve the exact host plan: {exc}",
            )
            return
        worker = HostRepairWorker(service, plan)
        worker.signals.complete.connect(self._host_repair_complete)
        worker.signals.failed.connect(self._host_repair_failed)
        self.host_repair_worker = worker
        if self.host_repair_button is not None:
            self.host_repair_button.setEnabled(False)
        self.host_repair_progress.begin(determinate=False)
        self.digest.setText(
            "Recovery Autopilot is restarting and verifying the host ADB daemon • phone changes: none"
        )
        self._start_host_repair_console(plan)
        self._record_autopilot_route_result(
            RecoveryRouteKind.HOST_ADB_REPAIR,
            "started",
            "The confirmed host-only ADB daemon plan started; phone changes remain impossible.",
        )
        start_background(worker)

    @Slot(object)
    def _host_repair_complete(self, result: object) -> None:
        self.host_repair_worker = None
        self.host_repair_progress.finish()
        if not isinstance(result, AdbHostRepairResult):
            self._host_repair_failed("ADB host recovery returned an invalid result")
            return
        style = "Good" if result.status is AdbHostRepairStatus.SUCCEEDED else "Warning"
        receipt = (
            f" Receipt SHA-256 {result.receipt_digest[:20]}…"
            if result.receipt_saved
            else " The host action finished, but its local receipt could not be saved."
        )
        self.digest.setText(f"{result.summary}{receipt}")
        self._record_activity(
            "ADB host recovery completed"
            if result.status is not AdbHostRepairStatus.FAILED
            else "ADB host recovery needs attention",
            result.summary,
            "success" if result.status is AdbHostRepairStatus.SUCCEEDED else "attention",
        )
        self._record_online_host_outcome(result)
        self._finish_host_repair_console(result)
        self._record_autopilot_route_result(
            RecoveryRouteKind.HOST_ADB_REPAIR,
            "succeeded"
            if result.status is AdbHostRepairStatus.SUCCEEDED
            else "failed",
            result.summary
            + " A fresh Device Engine scan is still required before recovery can be verified.",
        )
        if self.host_repair_button is not None:
            self.host_repair_button.setEnabled(True)
            self.host_repair_button.setObjectName(style)
            self.host_repair_button.style().unpolish(self.host_repair_button)
            self.host_repair_button.style().polish(self.host_repair_button)
        self.verification_scan_requested.emit()

    @Slot(str)
    def _host_repair_failed(self, message: str) -> None:
        self.host_repair_worker = None
        self.host_repair_progress.stop()
        safe = message.replace("\x00", " ").strip()[:500] or "Unknown host recovery failure"
        self.digest.setText(f"Recovery Autopilot stopped safely  •  {safe}")
        if self.host_repair_button is not None:
            self.host_repair_button.setEnabled(True)
        self._record_activity("ADB host recovery stopped safely", safe, "attention")
        self._fail_host_repair_console(safe)
        self._record_autopilot_route_result(
            RecoveryRouteKind.HOST_ADB_REPAIR,
            "failed",
            safe,
        )

    def _record_autopilot_route_result(
        self,
        kind: RecoveryRouteKind,
        outcome: str,
        detail: str,
    ) -> None:
        service = self.autopilot_service
        incident = self.autopilot_incident
        if service is None or incident is None or incident.repaired:
            return
        route = next((item for item in incident.routes if item.kind is kind), None)
        if route is None:
            return
        try:
            self.autopilot_incident = service.record_route_result(
                incident.incident_id,
                route.route_id,
                outcome,
                detail,
            )
        except RecoveryAutopilotError:
            return
        self._render_autopilot()

    def _start_host_repair_console(self, plan: AdbHostRepairPlan) -> None:
        if self.live_console_store is None:
            return
        try:
            event = self.live_console_store.start(
                source="Recovery Autopilot",
                stage="adb-host-recovery",
                title="ADB host recovery started",
                summary="Guardian approved an exact host-daemon-only recovery plan.",
                explanation=(
                    "ROMVERSE is restarting the host ADB daemon and will verify it with a "
                    "read-only device list. No command targets a phone."
                ),
                next_action="Wait for the verified daemon result and automatic fresh scan.",
                guardian_protected=True,
                evidence_refs=(f"plan:{plan.digest()}",),
            )
        except LiveConsoleStoreError:
            return
        self._host_repair_mission = event.mission_id

    def _finish_host_repair_console(self, result: AdbHostRepairResult) -> None:
        if self.live_console_store is None or not self._host_repair_mission:
            return
        mission = self._host_repair_mission
        self._host_repair_mission = ""
        state = (
            MissionState.SUCCEEDED
            if result.status is AdbHostRepairStatus.SUCCEEDED
            else MissionState.ATTENTION
        )
        try:
            self.live_console_store.finish(
                mission,
                state,
                summary=result.summary,
                explanation=(
                    "The result came from the exact ADB command return codes and a fresh device-list "
                    "probe; ROMVERSE did not infer success from elapsed time."
                ),
                next_action="Review the automatic fresh Device Engine scan.",
                confidence=MissionConfidence.VERIFIED,
                evidence_refs=(
                    (
                        f"receipt:{result.receipt_digest}"
                        if result.receipt_digest
                        else "receipt:unavailable"
                    ),
                ),
            )
        except LiveConsoleStoreError:
            return

    def _fail_host_repair_console(self, message: str) -> None:
        if self.live_console_store is None or not self._host_repair_mission:
            return
        mission = self._host_repair_mission
        self._host_repair_mission = ""
        try:
            self.live_console_store.finish(
                mission,
                MissionState.FAILED,
                summary=f"ADB host recovery stopped safely: {message}",
                explanation="No phone-targeted command was available to this repair worker.",
                next_action="Review host ADB access, then retry the exact bounded recovery.",
                confidence=MissionConfidence.VERIFIED,
            )
        except LiveConsoleStoreError:
            return

    def set_online_service(self, service: OnlineRemediationService | None) -> None:
        """Apply the current Settings boundary without cancelling an in-flight safe lookup."""

        self.online_service = service
        self._online_attempted.clear()
        self._online_receipts.clear()
        if service is None:
            self._online_pending = None
            self._clear_intelligence_action()
            self.intelligence_card.setVisible(False)
            return
        if self.devices:
            self.build_plan()

    @Slot()
    def _search_archives(self) -> None:
        query = self.symptom_input.text().replace("\x00", " ").strip()[:160]
        if self.current_concern is not None:
            recommendations = recommend_for_repair(
                self.current_concern,
                query,
                self.current_report.findings if self.current_report is not None else (),
                manufacturer=(
                    self.current_device.manufacturer if self.current_device is not None else ""
                ),
                limit=1,
            )
            if recommendations:
                self.knowledge_article_requested.emit(recommendations[0].article.key)
                return
        if not query:
            query = self.concern_selector.currentText().strip()[:160] or "Recovery Bay"
        self.knowledge_requested.emit(query)

    def _repair_fingerprint(
        self,
        device: AndroidDevice,
        report: DiagnosticReport,
        concern: RepairConcern,
    ) -> ErrorFingerprint | None:
        typed = self.symptom_input.text().replace("\x00", " ").strip()
        if typed:
            message = typed
        elif device.errors:
            message = "; ".join(device.errors[:3])
        else:
            finding = next(
                (
                    item
                    for item in report.findings
                    if item.severity.value in {"critical", "warning", "advisory"}
                ),
                None,
            )
            if finding is None:
                return None
            message = f"{finding.title}. {finding.explanation}"
        return ErrorFingerprint.create(
            message,
            category=f"recovery-{concern.name.casefold().replace('_', '-')}",
            manufacturer=device.manufacturer,
            model=device.model,
            marketing_name=device.marketing_name,
            codename=device.codename,
            build_id=device.rom_display or device.build_id,
            tool_name="ADB" if concern is RepairConcern.USB_ADB else "",
        )

    def _maybe_research(self, fingerprint: ErrorFingerprint) -> None:
        self._online_current = fingerprint
        self._clear_intelligence_action()
        if self._report_payload is not None:
            self._report_payload["online_research"] = {
                "fingerprint_id": fingerprint.fingerprint_id,
                "raw_user_text_stored": False,
                "execution_authority": "guidance-only",
            }
        service = self.online_service
        if service is None:
            self.intelligence_card.setVisible(True)
            self.intelligence_progress.stop()
            self.intelligence_retry.setVisible(False)
            self._set_intelligence_status(
                "LOCAL ADVISOR ACTIVE • ONLINE RESEARCH OFF",
                "Enable verified online diagnostics in ROMVERSE Settings to check official and optional community evidence. Local guidance and Guardian remain available.",
                "Warning",
            )
            self.intelligence_source.clear()
            self.intelligence_decision.setText(
                "SMART SOLUTION BRIEF • LOCAL EVIDENCE ONLY\n"
                "NEXT SAFE MOVE • Use the matching Archives guide or enable verified online "
                "diagnostics; no phone action is inferred."
            )
            self._set_intelligence_expanded(False)
            return
        cached = self._online_receipts.get(fingerprint.fingerprint_id) or service.load(fingerprint)
        if cached is not None:
            self._online_receipts[fingerprint.fingerprint_id] = cached
            self._show_online_receipt(cached)
        if fingerprint.fingerprint_id in self._online_attempted:
            return
        if self.online_worker is not None:
            self._online_pending = fingerprint
            return
        self._start_online_research(fingerprint)

    def _start_online_research(self, fingerprint: ErrorFingerprint) -> None:
        service = self.online_service
        if service is None or self.online_worker is not None:
            return
        self._online_attempted.add(fingerprint.fingerprint_id)
        self.intelligence_card.setVisible(True)
        self._set_intelligence_expanded(True)
        self.intelligence_retry.setVisible(False)
        self._clear_intelligence_action()
        self.intelligence_source.clear()
        self.intelligence_decision.setText(
            "SMART SOLUTION BRIEF • EVIDENCE SYNTHESIS PENDING\n"
            "NEXT SAFE MOVE • Wait for vetted sources; no repair has started."
        )
        self.intelligence_progress.begin(determinate=False)
        self._set_intelligence_status(
            "CHECKING VERIFIED SOURCES…",
            "ROMVERSE is comparing official, maintainer, and enabled community evidence against a privacy-scrubbed error fingerprint. Remote text cannot execute.",
            "Warning",
        )
        worker = RepairResearchWorker(service, fingerprint)
        worker.signals.complete.connect(self._online_research_complete)
        worker.signals.failed.connect(self._online_research_failed)
        self.online_worker = worker
        self._start_online_research_console(fingerprint)
        start_background(worker)

    @Slot(object)
    def _online_research_complete(self, result: object) -> None:
        completed_service = self.online_worker.service if self.online_worker is not None else None
        self.online_worker = None
        self.intelligence_progress.stop()
        if completed_service is not self.online_service:
            self._fail_online_research_console(
                "Research settings changed before this result could be accepted"
            )
            pending = self._online_pending
            self._online_pending = None
            if pending is not None and self.online_service is not None:
                self._start_online_research(pending)
            else:
                self.intelligence_card.setVisible(False)
            return
        if not isinstance(result, OnlineFixReceipt):
            self._online_research_failed("Online remediation returned an invalid receipt")
            return
        self._online_receipts[result.fingerprint.fingerprint_id] = result
        while len(self._online_receipts) > 32:
            self._online_receipts.pop(next(iter(self._online_receipts)))
        if self._online_current is not None and (
            result.fingerprint.fingerprint_id == self._online_current.fingerprint_id
        ):
            self._show_online_receipt(result)
        self._finish_online_research_console(result)
        pending = self._online_pending
        self._online_pending = None
        if (
            pending is not None
            and pending.fingerprint_id not in self._online_attempted
            and self.online_service is not None
        ):
            self._start_online_research(pending)

    @Slot(str)
    def _online_research_failed(self, message: str) -> None:
        self.online_worker = None
        self.intelligence_progress.stop()
        safe = message.replace("\x00", " ").strip()[:400] or "Online lookup failed"
        self._clear_intelligence_action()
        if self.online_service is not None:
            self.intelligence_card.setVisible(True)
            self._set_intelligence_expanded(True)
            self.intelligence_retry.setVisible(True)
            self._set_intelligence_status(
                "ONLINE RESEARCH NEEDS ATTENTION",
                f"{safe}. Local evidence was preserved; no remote instruction executed and Guardian policy did not change.",
                "Warning",
            )
            self.intelligence_decision.setText(
                "SMART SOLUTION BRIEF • RESEARCH STOPPED SAFELY\n"
                "NEXT SAFE MOVE • Keep the current local evidence and use the matching Archives "
                "guide, or retry verified research when the connection is available."
            )
            self.intelligence_source.clear()
        self._fail_online_research_console(safe)
        pending = self._online_pending
        self._online_pending = None
        if pending is not None and self.online_service is not None:
            self._start_online_research(pending)

    def _show_online_receipt(self, receipt: OnlineFixReceipt) -> None:
        self.intelligence_card.setVisible(True)
        self._set_intelligence_expanded(True)
        self.intelligence_progress.stop()
        self._clear_intelligence_action()
        try:
            decision = self._synthesize_intelligence(receipt)
        except (OSError, TypeError, ValueError):
            self.intelligence_retry.setVisible(True)
            self.intelligence_source.clear()
            self.intelligence_decision.setText(
                "SMART SOLUTION BRIEF • EVIDENCE REVALIDATION FAILED\n"
                "NEXT SAFE MOVE • Preserve the current local assessment and retry verified "
                "research; no source recommendation or phone action was accepted."
            )
            self._set_intelligence_status(
                "ONLINE EVIDENCE NEEDS ATTENTION",
                "The research receipt changed or could not be revalidated. ROMVERSE discarded "
                "its proposed solution instead of trusting stale evidence.",
                "Warning",
            )
            return
        if not receipt.candidates:
            self.intelligence_retry.setVisible(True)
            self.intelligence_source.clear()
            self._show_intelligence_decision(decision)
            self._record_intelligence_decision(decision)
            self._set_intelligence_status(
                "NO VERIFIED MATCH FOUND",
                receipt.diagnosis,
                "Warning",
            )
            return
        self.intelligence_retry.setVisible(False)
        top = receipt.candidates[0]
        self._show_intelligence_decision(decision)
        self._record_intelligence_decision(decision)
        self._configure_intelligence_action(receipt, decision)
        locally_verified = top.source_id in decision.locally_verified_source_ids
        confidence = "LOCALLY VERIFIED WORKING" if locally_verified else "GUIDANCE • REVIEW"
        self._set_intelligence_status(
            f"{confidence} • {top.authority.value.upper()} • {top.confidence}%",
            (
                f"{top.summary}\n\nFreshness: {top.freshness.value} • Scope: {top.scope_match} • "
                f"Corroboration: {top.corroboration_count} independent source(s). "
                f"{top.confidence_reason}"
            ),
            "Good" if locally_verified else "Warning",
        )
        sources = []
        for index, candidate in enumerate(receipt.candidates[:5]):
            title = html.escape(candidate.title)
            url = html.escape(candidate.url, quote=True)
            role = "LEAD" if index == 0 else f"ALTERNATIVE {index}"
            verified = (
                " • LOCALLY VERIFIED"
                if candidate.source_id in decision.locally_verified_source_ids
                else ""
            )
            signal = candidate_evidence_signal(
                candidate,
                locally_verified=candidate.source_id in decision.locally_verified_source_ids,
            )
            typed = (
                " • MATCHING BUILT-IN ACTION"
                if candidate.local_action_id == "refresh-adb-evidence"
                and self.host_repair_plan is not None
                else ""
            )
            sources.append(
                f'{role} • <a style="color:#43DDF2" href="{url}">{title}</a> • '
                f"{candidate.authority.value.upper()} • {candidate.confidence}% • "
                f"{signal.replace('-', ' ').upper()} • "
                f"{html.escape(candidate.freshness.value)} • "
                f"{html.escape(candidate.scope_match)}{verified}{typed}"
            )
        self.intelligence_source.setText("<br/>".join(sources))
        self.intelligence_source.setToolTip(
            "Opening a source is a user review action. Web content cannot become a ROMVERSE command."
        )

    def _configure_intelligence_action(
        self,
        receipt: OnlineFixReceipt,
        decision: RemediationDecision,
    ) -> None:
        if not receipt.candidates:
            return
        lead = receipt.candidates[0]
        if (
            not lead.local_action_id
            or lead.authority not in {SourceAuthority.OFFICIAL, SourceAuthority.MAINTAINER}
            or decision.state.value not in {"typed-action-available", "locally-verified"}
            or decision.lead_source_id != lead.source_id
        ):
            return
        labels = {
            "refresh-adb-evidence": "Review USB / ADB verification",
            "verify-platform-tools": "Open Platform Tools verification",
            "inspect-payload-source": "Open firmware source inspection",
            "inspect-avb-topology": "Open Verified Boot inspection",
            "classify-ota-source": "Open OTA source classification",
        }
        label = labels.get(lead.local_action_id)
        if label is None:
            return
        self._intelligence_action_binding = (
            lead.local_action_id,
            receipt.fingerprint.fingerprint_id,
            receipt.receipt_digest,
            lead.source_id,
        )
        self.intelligence_action.setText(label)
        self.intelligence_action.setVisible(True)
        if self._report_payload is not None:
            current = self._report_payload.get("online_research")
            if isinstance(current, dict):
                current.update(
                    {
                        "lead_local_action_id": lead.local_action_id,
                        "built_in_review_available": True,
                        "built_in_review_started": False,
                    }
                )

    def _clear_intelligence_action(self) -> None:
        self._intelligence_action_binding = None
        self.intelligence_action.setVisible(False)
        self.intelligence_action.setEnabled(True)

    def validate_solution_handoff(
        self,
        action_id: str,
        fingerprint_id: str,
        receipt_digest: str,
        source_id: str,
    ) -> bool:
        """Re-derive one lead action from the current persisted evidence."""

        requested = (action_id, fingerprint_id, receipt_digest, source_id)
        if requested != self._intelligence_action_binding:
            return False
        service = self.online_service
        current = self._online_current
        if service is None or current is None or current.fingerprint_id != fingerprint_id:
            return False
        receipt = service.load(current)
        if receipt is None or receipt.receipt_digest != receipt_digest or not receipt.candidates:
            return False
        lead = receipt.candidates[0]
        if (
            lead.local_action_id != action_id
            or lead.source_id != source_id
            or lead.authority not in {SourceAuthority.OFFICIAL, SourceAuthority.MAINTAINER}
        ):
            return False
        try:
            decision = service.synthesize(receipt)
        except (OSError, TypeError, ValueError):
            return False
        return decision.lead_source_id == source_id and decision.state.value in {
            "typed-action-available",
            "locally-verified",
        }

    def solution_handoff_receipt(
        self,
        action_id: str,
        fingerprint_id: str,
        receipt_digest: str,
        source_id: str,
    ) -> OnlineFixReceipt | None:
        """Return only the revalidated receipt backing the current visible handoff."""

        if not self.validate_solution_handoff(
            action_id,
            fingerprint_id,
            receipt_digest,
            source_id,
        ):
            return None
        service = self.online_service
        current = self._online_current
        if service is None or current is None:
            return None
        return service.load(current)

    def _request_intelligence_action(self) -> None:
        binding = self._intelligence_action_binding
        if binding is None or not self.validate_solution_handoff(*binding):
            self.solution_handoff_stopped(
                "The saved research evidence changed before the built-in workflow opened"
            )
            return
        action_id, fingerprint_id, receipt_digest, source_id = binding
        if action_id == "refresh-adb-evidence":
            target = (
                self.host_repair_button
                if self.host_repair_button is not None and self.host_repair_button.isEnabled()
                else self.execute_button
                if self.execute_button.isEnabled()
                else self.resolve_runtime_button
            )
            target.setFocus(Qt.FocusReason.OtherFocusReason)
            self.digest.setText(
                "Smart Solution handoff verified  •  review the highlighted USB / ADB "
                "control  •  no scan, daemon restart, or phone action started"
            )
            return
        self.solution_action_requested.emit(
            action_id,
            fingerprint_id,
            receipt_digest,
            source_id,
        )

    def solution_handoff_stopped(self, reason: str) -> None:
        safe = reason.replace("\x00", " ").strip()[:300] or "Evidence no longer matches"
        self._clear_intelligence_action()
        if self._report_payload is not None:
            current = self._report_payload.get("online_research")
            if isinstance(current, dict):
                current.update(
                    {
                        "built_in_review_available": False,
                        "built_in_review_started": False,
                        "handoff_stopped_reason": safe,
                    }
                )
        self._set_intelligence_status(
            "SMART SOLUTION HANDOFF STOPPED",
            f"{safe}. Refresh the assessment before choosing another workflow. No worker, "
            "install, project change, or phone action started.",
            "Warning",
        )

    def _synthesize_intelligence(self, receipt: OnlineFixReceipt) -> RemediationDecision:
        service = self.online_service
        if service is None:
            return synthesize_remediation(receipt)
        return service.synthesize(receipt)

    def _show_intelligence_decision(self, decision: RemediationDecision) -> None:
        self.intelligence_decision.setText(
            f"SMART SOLUTION BRIEF • {decision.state.value.replace('-', ' ').upper()}\n"
            f"{decision.headline}\nWHY • {decision.rationale}\n"
            f"NEXT SAFE MOVE • {decision.next_safe_action}"
        )
        self.intelligence_decision.setObjectName(
            "Good" if decision.state.value == "locally-verified" else "Warning"
        )
        self.intelligence_decision.style().unpolish(self.intelligence_decision)
        self.intelligence_decision.style().polish(self.intelligence_decision)
        QTimer.singleShot(0, self._fit_intelligence_copy)

    def _fit_intelligence_copy(self) -> None:
        """Keep wrapped Smart Brief evidence readable without overlapping adjacent rows."""

        width = self.intelligence_decision.width()
        if width <= 0 or not self.intelligence_details.isVisible():
            return
        visible_rows: list[QWidget] = []
        for label in (
            self.intelligence_decision,
            self.intelligence_detail,
            self.intelligence_source,
        ):
            text = label.text()
            label.setMinimumHeight(0)
            required = label.heightForWidth(max(1, label.width())) if text else 0
            label.setMinimumHeight(required + 4 if required else 0)
            if label.isVisible() and text:
                visible_rows.append(label)

        details_layout = self.intelligence_details.layout()
        if details_layout is None:
            return
        spacing = details_layout.spacing() * max(0, len(visible_rows) - 1)
        content_height = spacing + sum(
            max(widget.minimumHeight(), widget.minimumSizeHint().height())
            for widget in visible_rows
        )
        self.intelligence_details.setMinimumHeight(content_height)
        details_layout.invalidate()
        details_layout.activate()
        self.intelligence_details.updateGeometry()
        self.intelligence_details_scroll.updateGeometry()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._fit_intelligence_copy)

    def _record_intelligence_decision(self, decision: RemediationDecision) -> None:
        if self._report_payload is None:
            return
        current = self._report_payload.get("online_research")
        if not isinstance(current, dict):
            return
        current.update(
            {
                "decision_state": decision.state.value,
                "headline": decision.headline,
                "rationale": decision.rationale,
                "next_safe_action": decision.next_safe_action,
                "lead_signal": decision.lead_signal,
                "lead_source_id": decision.lead_source_id,
                "evidence_source_ids": list(decision.evidence_source_ids),
                "locally_verified_source_ids": list(decision.locally_verified_source_ids),
                "candidate_count": decision.candidate_count,
                "execution_authority": decision.execution_authority,
                "phone_action_allowed": decision.phone_action_allowed,
            }
        )

    def _set_intelligence_status(self, status: str, detail: str, style: str) -> None:
        self.intelligence_status.setText(status)
        self.intelligence_status.setObjectName(style)
        self.intelligence_status.style().unpolish(self.intelligence_status)
        self.intelligence_status.style().polish(self.intelligence_status)
        self.intelligence_detail.setText(detail)

    @Slot(bool)
    def _set_intelligence_expanded(self, expanded: bool) -> None:
        self.intelligence_toggle.blockSignals(True)
        self.intelligence_toggle.setChecked(expanded)
        self.intelligence_toggle.setText(
            "HIDE RESEARCH DETAILS" if expanded else "SHOW RESEARCH DETAILS"
        )
        self.intelligence_toggle.blockSignals(False)
        self.intelligence_details.setVisible(expanded)
        self.intelligence_expanded_panel.setVisible(expanded)
        if expanded:
            QTimer.singleShot(0, self._fit_intelligence_copy)

    def _retry_online_research(self) -> None:
        fingerprint = self._online_current
        if fingerprint is None or self.online_service is None or self.online_worker is not None:
            return
        self._online_attempted.discard(fingerprint.fingerprint_id)
        self._start_online_research(fingerprint)

    def _record_online_host_outcome(self, result: AdbHostRepairResult) -> None:
        if (
            result.status is not AdbHostRepairStatus.SUCCEEDED
            or not result.receipt_saved
            or not result.receipt_digest
            or not result.receipt_ref
            or self.online_service is None
            or self._online_current is None
        ):
            return
        receipt = self._online_receipts.get(self._online_current.fingerprint_id)
        if receipt is None:
            return
        candidate = next(
            (
                item
                for item in receipt.candidates
                if item.local_action_id == "refresh-adb-evidence"
                and item.authority in {SourceAuthority.OFFICIAL, SourceAuthority.MAINTAINER}
            ),
            None,
        )
        if candidate is None:
            return
        try:
            outcome = self.online_service.record_verified_outcome(
                receipt.fingerprint,
                candidate,
                TypedLocalActionEvidence(
                    candidate.local_action_id,
                    result.receipt_digest,
                    result.receipt_ref,
                    "romverse.adb-host-repair",
                ),
                "Guardian-approved host ADB recovery completed, the daemon responded, and a fresh read-only device-list verification succeeded.",
            )
        except (OSError, ValueError):
            return
        self._show_online_receipt(receipt)
        if self.live_console_store is not None:
            with suppress(LiveConsoleStoreError):
                self.live_console_store.note(
                    source="ROMVERSE Intelligence",
                    stage="verified-repair-outcome",
                    title="Typed online fix verified locally",
                    summary="ADB host recovery was bound to its exact successful receipt.",
                    explanation=(
                        "Only the built-in typed host action was executed. Remote text remained "
                        "guidance-only and the phone was not changed."
                    ),
                    next_action="Use the automatic fresh scan to confirm the required connection evidence.",
                    state=MissionState.INFORMATION,
                    confidence=MissionConfidence.VERIFIED,
                    guardian_protected=True,
                    evidence_refs=(
                        f"knowledge/online-remediation/verified-outcomes/{outcome.fingerprint_id}",
                    ),
                    dedupe_key=f"verified-fix-{outcome.outcome_digest}",
                )

    def _start_online_research_console(self, fingerprint: ErrorFingerprint) -> None:
        if self.live_console_store is None:
            return
        try:
            event = self.live_console_store.start(
                source="ROMVERSE Intelligence",
                stage="recovery-research",
                title="Automatic repair research started",
                summary=f"Checking a bounded {fingerprint.category} error fingerprint.",
                explanation=(
                    "Official, maintainer, and enabled community sources are evidence only. "
                    "They cannot create an executable action."
                ),
                next_action="Wait for freshness, scope, corroboration, and confidence checks.",
                confidence=MissionConfidence.UNCONFIRMED,
                guardian_protected=True,
            )
        except LiveConsoleStoreError:
            return
        self._online_mission = event.mission_id

    def _finish_online_research_console(self, receipt: OnlineFixReceipt) -> None:
        if self.live_console_store is None or not self._online_mission:
            return
        mission = self._online_mission
        self._online_mission = ""
        found = bool(receipt.candidates)
        top = receipt.candidates[0] if found else None
        try:
            self.live_console_store.finish(
                mission,
                MissionState.SUCCEEDED if found else MissionState.ATTENTION,
                summary=receipt.diagnosis,
                explanation=(
                    "The highest-ranked source passed bounded URL, relevance, freshness, scope, "
                    "and confidence checks; it still has no execution authority."
                    if found
                    else "No source met the relevance boundary, so ROMVERSE did not invent a fix."
                ),
                next_action=(
                    "Continue only through a matching built-in typed action."
                    if top is not None and top.local_action_id
                    else "Review the source evidence or add a more exact error description."
                ),
                confidence=(
                    MissionConfidence.VERIFIED
                    if top is not None and top.confirmed_working
                    else MissionConfidence.MEDIUM
                    if found
                    else MissionConfidence.UNCONFIRMED
                ),
                evidence_refs=(
                    f"knowledge/online-remediation/{receipt.fingerprint.fingerprint_id}.romverse",
                ),
            )
        except LiveConsoleStoreError:
            return

    def _fail_online_research_console(self, message: str) -> None:
        if self.live_console_store is None or not self._online_mission:
            return
        mission = self._online_mission
        self._online_mission = ""
        try:
            self.live_console_store.finish(
                mission,
                MissionState.FAILED,
                summary=f"Automatic repair research stopped safely: {message}",
                explanation="Local error evidence was preserved and no remote instruction executed.",
                next_action="Retry when connectivity returns or continue with deterministic local evidence.",
                confidence=MissionConfidence.UNCONFIRMED,
            )
        except LiveConsoleStoreError:
            return

    def _matching_session(
        self,
        device: AndroidDevice,
        concern: RepairConcern,
    ) -> RepairSession | None:
        if self.session_store is None:
            return None
        key = self.session_store.privacy.pseudonym(device.serial)
        return next(
            (
                session
                for session in self.session_store.list_recent()
                if session.device_key == key and session.concern == concern.value
            ),
            None,
        )

    def _render_guided_session(self, recommendations: tuple[str, ...]) -> None:
        heading = QLabel("Guided repair session")
        heading.setObjectName("SectionTitle")
        self.body_layout.addWidget(heading)
        card = QFrame()
        card.setObjectName("HeroCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        session = self.active_session
        self.session_checks = []
        if session is None:
            copy = QLabel(
                "Start a session to preserve this evidence baseline, save checkpoint progress, "
                "and compare the result with a genuinely fresh Device Engine scan."
            )
            copy.setObjectName("Muted")
            copy.setWordWrap(True)
            layout.addWidget(copy)
        else:
            state = QLabel(
                f"{session.status.replace('_', ' ').upper()}  •  initial health signal {session.initial_health_score}"
            )
            state.setObjectName("Good" if session.status == "verified" else "Warning")
            layout.addWidget(state)
            for index, step in enumerate(recommendations):
                check = QCheckBox(f"I reviewed or tried this step: {step}")
                check.setChecked(index in session.reviewed_steps)
                check.setToolTip(
                    "This records your checkpoint only; it does not prove the issue is fixed."
                )
                layout.addWidget(check)
                self.session_checks.append(check)
            actions = QHBoxLayout()
            save = QPushButton("Save checkpoint progress")
            save.clicked.connect(self._save_session_progress)
            verify = QPushButton("Verify with a fresh scan")
            verify.setObjectName("Primary")
            verify.setToolTip(
                "Run Device Engine again and compare new read-only evidence with the saved baseline."
            )
            verify.clicked.connect(self._request_verification)
            actions.addWidget(save)
            actions.addWidget(verify)
            actions.addStretch()
            layout.addLayout(actions)
            if session.verification_summary:
                result = QLabel(session.verification_summary)
                result.setObjectName(
                    "Good" if "improved" in session.verification_summary else "Warning"
                )
                result.setWordWrap(True)
                layout.addWidget(result)
            boundary = QLabel(
                "Checkpoint ticks record what you reviewed; only the fresh evidence comparison can describe change. No repair is auto-claimed."
            )
            boundary.setObjectName("Muted")
            boundary.setWordWrap(True)
            layout.addWidget(boundary)
        self.body_layout.addWidget(card)

    def _start_session(self) -> None:
        if (
            self.session_store is None
            or self.current_device is None
            or self.current_device.state is not DeviceState.DEVICE
            or self.current_report is None
            or self.current_concern is None
        ):
            return
        entry = knowledge_for(self.current_concern)
        archive_recommendations = recommend_for_repair(
            self.current_concern,
            self.symptom_input.text(),
            self.current_report.findings,
            manufacturer=self.current_device.manufacturer,
            limit=1,
        )
        try:
            self.active_session = self.session_store.start(
                self.current_concern,
                self.current_device,
                self.current_report,
                entry.recommended_steps,
                tuple(item.article.key for item in archive_recommendations),
            )
        except RepairSessionError as exc:
            self.digest.setText(f"Guided session could not start  •  {exc}")
            return
        self._record_activity(
            "Guided repair session started",
            f"{self.current_concern.value} • privacy-safe evidence baseline recorded",
            "information",
            session_id=self.active_session.session_id,
        )
        self.build_plan()

    def _save_session_progress(self) -> None:
        if self.session_store is None or self.active_session is None:
            return
        reviewed = tuple(
            index for index, check in enumerate(self.session_checks) if check.isChecked()
        )
        try:
            self.active_session = self.session_store.update_reviewed(
                self.active_session.session_id,
                reviewed,
            )
        except RepairSessionError as exc:
            self.digest.setText(f"Progress was not saved  •  {exc}")
            return
        self.digest.setText(
            f"Repair progress saved  •  {len(reviewed)}/{len(self.session_checks)} checkpoints reviewed  •  no success claimed"
        )
        self.build_plan()

    def _request_verification(self) -> None:
        if self.active_session is None:
            return
        self._save_session_progress()
        if self.active_session is None:
            return
        self._pending_verification_session = self.active_session.session_id
        self.digest.setText("Requesting a fresh read-only Device Engine scan…")
        self.verification_scan_requested.emit()

    def _run_fresh_diagnostics(self) -> None:
        if not self.devices:
            return
        if self.active_session is not None:
            self._request_verification()
            return
        self.digest.setText(
            "Requesting a fresh read-only Device Engine scan  •  no settings or phone data will be changed"
        )
        self.verification_scan_requested.emit()

    def _complete_pending_verification(self, devices: list[AndroidDevice]) -> None:
        session_id = self._pending_verification_session
        self._pending_verification_session = ""
        if self.session_store is None:
            return
        try:
            session = self.session_store.load(session_id)
            device = next(
                item
                for item in devices
                if item.state is DeviceState.DEVICE
                and self.session_store.privacy.pseudonym(item.serial) == session.device_key
            )
            report = self.analyzer.analyze(device)
            self.active_session = self.session_store.verify(session_id, device, report)
        except (RepairSessionError, StopIteration) as exc:
            self.digest.setText(f"Fresh verification could not complete  •  {exc}")
            return
        self._record_activity(
            "Guided repair evidence verified",
            self.active_session.verification_summary,
            "success" if "improved" in self.active_session.verification_summary else "information",
            session_id=self.active_session.session_id,
        )
        self.resolution_memory_updated.emit()

    def _record_activity(
        self,
        title: str,
        detail: str,
        outcome: str,
        *,
        session_id: str = "",
    ) -> None:
        if self.activity_store is None:
            return
        with suppress(ActivityStoreError):
            self.activity_store.record(
                "repair",
                title,
                detail,
                outcome=outcome,
                source="Recovery Bay",
                source_route="recovery_bay" if session_id else "",
                context_type="repair-session" if session_id else "",
                context_id=session_id,
            )

    def _empty(self, message: str, *, add_stretch: bool = True) -> None:
        self._clear()
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        label = QLabel(message)
        label.setObjectName("Muted")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.body_layout.addWidget(card)
        if add_stretch:
            self.body_layout.addStretch()

    def _export_report(self) -> None:
        if self._report_payload is None:
            return
        destination, _ = QFileDialog.getSaveFileName(
            self, "Export repair assessment", "romverse-repair-assessment.json", "JSON (*.json)"
        )
        if not destination:
            return
        try:
            with open(destination, "w", encoding="utf-8") as handle:
                json.dump(self._report_payload, handle, indent=2)
                handle.write("\n")
            self.digest.setText(f"Report exported  •  {destination}")
        except OSError as exc:
            self.digest.setText(f"Report export failed  •  {exc}")

    def _clear(self) -> None:
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _set_badge(self, text: str, style: str) -> None:
        self.status_badge.setText(text)
        self.status_badge.setObjectName(style)
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)
