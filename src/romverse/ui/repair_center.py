from __future__ import annotations

import html
import json
from contextlib import suppress
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal, Slot
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
    SourceAuthority,
)
from romverse.nexus.events import (
    LiveConsoleEventStore,
    LiveConsoleStoreError,
    MissionConfidence,
    MissionState,
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
from romverse.repair.templates import RepairAssessmentTemplates, RepairConcern
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
    knowledge_requested = Signal(str)

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
        self.devices: list[AndroidDevice] = []
        self._report_payload: dict[str, object] | None = None
        self.current_device: AndroidDevice | None = None
        self.current_report: DiagnosticReport | None = None
        self.current_concern: RepairConcern | None = None
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
        self._online_verified: set[tuple[str, str, str]] = set()
        self._online_mission = ""

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
        self.concern_selector.currentIndexChanged.connect(self.build_plan)
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

        self.intelligence_card = QFrame()
        self.intelligence_card.setObjectName("Card")
        intelligence_layout = QVBoxLayout(self.intelligence_card)
        intelligence_layout.setContentsMargins(18, 14, 18, 14)
        self.intelligence_heading = QLabel("ROMVERSE INTELLIGENCE • AUTOMATIC REPAIR RESEARCH")
        self.intelligence_heading.setObjectName("Eyebrow")
        self.intelligence_status = QLabel("")
        self.intelligence_status.setWordWrap(True)
        self.intelligence_detail = QLabel("")
        self.intelligence_detail.setObjectName("Muted")
        self.intelligence_detail.setWordWrap(True)
        self.intelligence_source = QLabel("")
        self.intelligence_source.setObjectName("Muted")
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
        intelligence_layout.addWidget(self.intelligence_heading)
        intelligence_layout.addWidget(self.intelligence_status)
        intelligence_layout.addWidget(self.intelligence_detail)
        intelligence_layout.addWidget(self.intelligence_source)
        intelligence_layout.addWidget(self.intelligence_boundary)
        intelligence_layout.addWidget(self.intelligence_progress)
        intelligence_layout.addWidget(self.intelligence_retry)
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
        else:
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

    def set_host_repair_service(self, service: AdbHostRepairService | None) -> None:
        """Apply the currently verified host ADB runtime without retaining stale plans."""

        self.resolve_runtime_button.setVisible(service is None)
        if self.host_repair_service is service:
            return
        self.host_repair_service = service
        self.host_repair_plan = None
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
        safe_message = message.replace("\x00", " ").strip()[:300] or "ADB discovery failed"
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
            self._empty("Resolve Device Engine access before creating a repair assessment.")
            return
        try:
            self.host_repair_plan = self.host_repair_service.plan(
                AdbHostRepairMode.RESTART,
                f"Device Engine scan failed: {safe_message}",
            )
        except AdbHostRepairError as exc:
            self._empty(f"ADB host recovery is unavailable: {exc}")
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
        self._render_host_repair(self.host_repair_plan)
        self.body_layout.addStretch()

    def build_plan(self, _index: int = -1) -> None:
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
        self.active_session = self._matching_session(device, concern)
        manifest = self.templates.build(concern, device, report)
        assessment = self.preflight.assess(manifest)
        self._render(manifest, assessment, report, concern)
        fingerprint = self._repair_fingerprint(device, report, concern)
        if fingerprint is not None:
            self._maybe_research(fingerprint)
        elif self.online_worker is None:
            self.intelligence_card.setVisible(False)

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
            return
        try:
            service.approve(plan)
        except Exception as exc:
            self.digest.setText(f"Guardian could not approve ADB host recovery  •  {exc}")
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
        self._online_verified.clear()
        if service is None:
            self._online_pending = None
            self.intelligence_card.setVisible(False)
            return
        if self.devices:
            self.build_plan()

    @Slot()
    def _search_archives(self) -> None:
        query = self.symptom_input.text().replace("\x00", " ").strip()[:160]
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
                "ONLINE RESEARCH DISABLED",
                "Enable verified online diagnostics in ROMVERSE Settings to check official and optional community evidence. Local guidance and Guardian remain available.",
                "Warning",
            )
            self.intelligence_source.clear()
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
        self.intelligence_retry.setVisible(False)
        self.intelligence_source.clear()
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
        if self.online_service is not None:
            self.intelligence_card.setVisible(True)
            self.intelligence_retry.setVisible(True)
            self._set_intelligence_status(
                "ONLINE RESEARCH NEEDS ATTENTION",
                f"{safe}. Local evidence was preserved; no remote instruction executed and Guardian policy did not change.",
                "Warning",
            )
            self.intelligence_source.clear()
        self._fail_online_research_console(safe)
        pending = self._online_pending
        self._online_pending = None
        if pending is not None and self.online_service is not None:
            self._start_online_research(pending)

    def _show_online_receipt(self, receipt: OnlineFixReceipt) -> None:
        self.intelligence_card.setVisible(True)
        self.intelligence_progress.stop()
        if not receipt.candidates:
            self.intelligence_retry.setVisible(True)
            self.intelligence_source.clear()
            self._set_intelligence_status(
                "NO VERIFIED MATCH FOUND",
                receipt.diagnosis,
                "Warning",
            )
            return
        self.intelligence_retry.setVisible(False)
        top = receipt.candidates[0]
        locally_verified = (
            top.confirmed_working
            or (
                receipt.fingerprint.fingerprint_id,
                top.source_id,
                top.local_action_id,
            )
            in self._online_verified
        )
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
        title = html.escape(top.title)
        url = html.escape(top.url, quote=True)
        typed = (
            " • matching built-in action available below"
            if top.local_action_id == "refresh-adb-evidence" and self.host_repair_plan is not None
            else ""
        )
        self.intelligence_source.setText(
            f'<a style="color:#43DDF2" href="{url}">{title}</a>'
            f" • source date {html.escape(top.published_at or 'unconfirmed')}"
            f" • local action {html.escape(top.local_action_id or 'none')}{typed}"
        )
        self.intelligence_source.setToolTip(
            "Opening a source is a user review action. Web content cannot become a ROMVERSE command."
        )

    def _set_intelligence_status(self, status: str, detail: str, style: str) -> None:
        self.intelligence_status.setText(status)
        self.intelligence_status.setObjectName(style)
        self.intelligence_status.style().unpolish(self.intelligence_status)
        self.intelligence_status.style().polish(self.intelligence_status)
        self.intelligence_detail.setText(detail)

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
        self._online_verified.add(
            (receipt.fingerprint.fingerprint_id, candidate.source_id, candidate.local_action_id)
        )
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
        try:
            self.active_session = self.session_store.start(
                self.current_concern,
                self.current_device,
                self.current_report,
                entry.recommended_steps,
            )
        except RepairSessionError as exc:
            self.digest.setText(f"Guided session could not start  •  {exc}")
            return
        self._record_activity(
            "Guided repair session started",
            f"{self.current_concern.value} • privacy-safe evidence baseline recorded",
            "information",
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
        )

    def _record_activity(self, title: str, detail: str, outcome: str) -> None:
        if self.activity_store is None:
            return
        with suppress(ActivityStoreError):
            self.activity_store.record(
                "repair",
                title,
                detail,
                outcome=outcome,
                source="Recovery Bay",
            )

    def _empty(self, message: str) -> None:
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
