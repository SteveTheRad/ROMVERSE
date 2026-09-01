from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from romverse.device.dna import DeviceDnaStore
from romverse.nexus.compatibility import CompatibilityMatrixStore
from romverse.nexus.planning import (
    FlashMode,
    InsightExporter,
    NexusObjective,
    NexusPlan,
    NexusPlanner,
    NexusPlanStatus,
    RouteStageState,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


class NexusCenter(QWidget):
    """Visual Pathfinder, Foresight, and Insight surface for deterministic plans."""

    plan_updated = Signal(object)
    guardian_requested = Signal(str, str)
    rom_studio_requested = Signal(str, str)
    knowledge_article_requested = Signal(str)

    OBJECTIVES = {
        "Build a ROM": NexusObjective.BUILD_ROM,
        "Prepare optional root": NexusObjective.ROOT_ROM,
        "Prepare Guardian flash review": NexusObjective.FLASH_DEVICE,
    }
    FLASH_MODES = {
        "Choose later": FlashMode.UNSELECTED,
        "Dirty flash • preserve data intent": FlashMode.DIRTY_FLASH,
        "Flash and wipe data • erases user data": FlashMode.WIPE_DATA,
    }

    def __init__(self, store: RomProjectStore) -> None:
        super().__init__()
        self.store = store
        self.planner = NexusPlanner(store)
        self.projects = ()
        self.current_plan: NexusPlan | None = None

        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 30)
        page.setSpacing(16)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        eyebrow = QLabel("ROMVERSE NEXUS  •  PATHFINDER  •  FORESIGHT  •  INSIGHT")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("Nexus Mission Planner")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Understand the device, research compatibility, map the safest route, predict impact, "
            "and explain every decision before Guardian review. Nexus plans; it never grants execution."
        )
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        heading.addWidget(eyebrow)
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading, 1)
        self.refresh_button = QPushButton("Refresh evidence")
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button)
        page.addLayout(header)

        controls = QFrame()
        controls.setObjectName("Card")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(18, 16, 18, 16)
        selectors = QHBoxLayout()
        self.project_selector = QComboBox()
        self.project_selector.setMinimumWidth(240)
        self.project_selector.currentIndexChanged.connect(self._select_project)
        self.objective = QComboBox()
        self.objective.addItems(self.OBJECTIVES)
        self.objective.currentTextChanged.connect(self._objective_changed)
        self.flash_mode = QComboBox()
        self.flash_mode.addItems(self.FLASH_MODES)
        self.flash_mode.setToolTip(
            "Dirty flash expresses data-preservation intent; wipe data erases user data. "
            "Both still require a backup decision and Guardian review."
        )
        self.generate_button = QPushButton("Generate Nexus Plan")
        self.generate_button.setObjectName("Primary")
        self.generate_button.clicked.connect(self.generate_plan)
        selectors.addWidget(QLabel("Project"))
        selectors.addWidget(self.project_selector, 1)
        selectors.addWidget(QLabel("Objective"))
        selectors.addWidget(self.objective)
        selectors.addWidget(self.flash_mode)
        selectors.addWidget(self.generate_button)
        controls_layout.addLayout(selectors)
        self.status = QLabel(
            "Choose a project with current Device DNA and Compatibility Matrix evidence."
        )
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        controls_layout.addWidget(self.status)
        page.addWidget(controls)

        self.evidence_handoff = QFrame()
        self.evidence_handoff.setObjectName("DiagnosticHandoffBar")
        handoff_layout = QHBoxLayout(self.evidence_handoff)
        handoff_layout.setContentsMargins(18, 13, 18, 13)
        handoff_copy = QVBoxLayout()
        handoff_eyebrow = QLabel("NEXUS EVIDENCE PATH  •  NO PLAN GENERATED")
        handoff_eyebrow.setObjectName("Eyebrow")
        self.evidence_handoff_title = QLabel()
        self.evidence_handoff_title.setObjectName("SectionTitle")
        self.evidence_handoff_detail = QLabel()
        self.evidence_handoff_detail.setObjectName("Muted")
        self.evidence_handoff_detail.setWordWrap(True)
        handoff_copy.addWidget(handoff_eyebrow)
        handoff_copy.addWidget(self.evidence_handoff_title)
        handoff_copy.addWidget(self.evidence_handoff_detail)
        handoff_layout.addLayout(handoff_copy, 1)
        handoff_badge = QLabel("EVIDENCE REQUIRED  •  ZERO AUTHORITY")
        handoff_badge.setObjectName("Warning")
        handoff_layout.addWidget(handoff_badge)
        handoff_actions = QVBoxLayout()
        self.evidence_guide_button = QPushButton("Open verified evidence guide")
        self.evidence_guide_button.clicked.connect(
            lambda: self.knowledge_article_requested.emit("nexus-evidence-prerequisites")
        )
        self.evidence_studio_button = QPushButton("Open ROM Studio")
        self.evidence_studio_button.setObjectName("Primary")
        self.evidence_studio_button.clicked.connect(self._request_rom_studio)
        handoff_actions.addWidget(self.evidence_guide_button)
        handoff_actions.addWidget(self.evidence_studio_button)
        handoff_layout.addLayout(handoff_actions)
        self.evidence_handoff.setVisible(False)
        page.addWidget(self.evidence_handoff)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("NexusScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_host = QWidget()
        self.scroll_host.setObjectName("ScrollContent")
        self.content = QVBoxLayout(self.scroll_host)
        self.content.setContentsMargins(0, 0, 6, 12)
        self.content.setSpacing(14)

        self.route_card = QFrame()
        self.route_card.setObjectName("Card")
        self.route_layout = QVBoxLayout(self.route_card)
        self.route_layout.setContentsMargins(18, 16, 18, 16)
        self.route_layout.addWidget(self._section_title("PATHFINDER ROUTE MAP"))
        self.route_empty = QLabel("Generate a plan to see the current route and every gate.")
        self.route_empty.setObjectName("Muted")
        self.route_layout.addWidget(self.route_empty)
        self.content.addWidget(self.route_card)

        self.foresight_card = QFrame()
        self.foresight_card.setObjectName("Card")
        foresight_layout = QVBoxLayout(self.foresight_card)
        foresight_layout.setContentsMargins(18, 16, 18, 16)
        foresight_layout.addWidget(self._section_title("FORESIGHT • PREDICT → VERIFY → LEARN"))
        self.foresight = QLabel("No impact prediction has been generated.")
        self.foresight.setObjectName("Muted")
        self.foresight.setWordWrap(True)
        self.foresight.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        foresight_layout.addWidget(self.foresight)
        self.content.addWidget(self.foresight_card)

        self.insight_card = QFrame()
        self.insight_card.setObjectName("Card")
        insight_layout = QVBoxLayout(self.insight_card)
        insight_layout.setContentsMargins(18, 16, 18, 16)
        insight_layout.addWidget(self._section_title("INSIGHT • WHY AND EVIDENCE"))
        self.insight = QLabel("No decision timeline has been generated.")
        self.insight.setObjectName("Muted")
        self.insight.setWordWrap(True)
        self.insight.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        insight_layout.addWidget(self.insight)
        actions = QHBoxLayout()
        self.export_button = QPushButton("Export privacy-scrubbed Insight")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_insight)
        self.guardian_button = QPushButton("Review plan in Guardian Core")
        self.guardian_button.setEnabled(False)
        self.guardian_button.clicked.connect(self.request_guardian_review)
        self.open_studio_button = QPushButton("Open ROM Studio")
        self.open_studio_button.clicked.connect(self._request_rom_studio)
        actions.addWidget(self.export_button)
        actions.addWidget(self.guardian_button)
        actions.addWidget(self.open_studio_button)
        actions.addStretch(1)
        insight_layout.addLayout(actions)
        self.content.addWidget(self.insight_card)
        self.content.addStretch(1)
        self.scroll.setWidget(self.scroll_host)
        page.addWidget(self.scroll, 1)
        self._objective_changed(self.objective.currentText())
        self.refresh()

    def refresh(self) -> None:
        preferred = self.current_plan.project_id if self.current_plan is not None else ""
        self.projects = self.store.list_projects()
        self.project_selector.blockSignals(True)
        self.project_selector.clear()
        selected = 0
        for index, project in enumerate(self.projects):
            self.project_selector.addItem(project.name, project.project_id)
            if project.project_id == preferred:
                selected = index
        self.project_selector.blockSignals(False)
        if not self.projects:
            self.current_plan = None
            self.generate_button.setEnabled(False)
            self.status.setText("No ROM project exists yet. Create and import one in ROM Studio.")
            self.status.setObjectName("Warning")
            self._repolish(self.status)
            self._set_evidence_handoff(
                "Start with one protected ROM project",
                "Nexus needs a project and protected firmware source before it can derive Device "
                "DNA or a Compatibility Matrix. Open the verified guide for the evidence path, "
                "or continue to ROM Studio. No plan, approval, worker, or phone action has started.",
                True,
            )
            self._render(None)
            return
        self.project_selector.setCurrentIndex(selected)
        self._select_project(selected)

    def open_project(self, project_id: str) -> bool:
        """Select one current project for an evidence-bound Desktop handoff."""

        self.refresh()
        index = self.project_selector.findData(project_id)
        if index < 0:
            self.status.setText(
                "PROJECT HANDOFF STOPPED  •  The referenced project is no longer available  •  "
                "No action started"
            )
            self.status.setObjectName("Danger")
            self._repolish(self.status)
            return False
        if self.project_selector.currentIndex() == index:
            self._select_project(index)
        else:
            self.project_selector.setCurrentIndex(index)
        return True

    def generate_plan(self) -> None:
        project_id = self.project_selector.currentData()
        if not isinstance(project_id, str) or not project_id:
            return
        profile = DeviceDnaStore(self.store).load(project_id)
        matrix = CompatibilityMatrixStore(self.store).load(project_id)
        if profile is None or matrix is None:
            missing = self._missing_evidence(profile is None, matrix is None)
            self.status.setText(
                "Nexus needs current Device DNA and a Compatibility Matrix. Open ROM Studio; "
                "ROMVERSE will generate both automatically from protected evidence."
            )
            self.status.setObjectName("Warning")
            self._repolish(self.status)
            self._set_evidence_handoff(
                "Complete the project's evidence chain",
                f"Missing for {self.project_selector.currentText()}: {missing}. ROM Studio can "
                "derive these records from the protected source; Nexus will not infer them from "
                "a live phone or catalog identity. No plan or phone action has started.",
                True,
            )
            return
        try:
            plan = self.planner.plan(
                profile,
                matrix,
                self.OBJECTIVES[self.objective.currentText()],
                flash_mode=self.FLASH_MODES[self.flash_mode.currentText()],
            )
        except ProjectError as exc:
            self.status.setText(f"Nexus stopped safely: {exc}")
            self.status.setObjectName("Danger")
            self._repolish(self.status)
            return
        self.current_plan = plan
        self._set_evidence_handoff("", "", False)
        self._render(plan)
        self.plan_updated.emit(plan)

    def export_insight(self) -> None:
        if self.current_plan is None:
            return
        destination, _selected = QFileDialog.getSaveFileName(
            self,
            "Export privacy-scrubbed Insight",
            str(Path.home() / f"romverse-insight-{self.current_plan.plan_id[:8]}.json"),
            "JSON (*.json)",
        )
        if not destination:
            return
        try:
            output = InsightExporter.export(self.current_plan, Path(destination))
        except OSError as exc:
            QMessageBox.warning(self, "Insight not exported", str(exc))
            return
        self.status.setText(f"Privacy-scrubbed Insight exported to {output.name}.")
        self.status.setObjectName("Good")
        self._repolish(self.status)

    def request_guardian_review(self) -> None:
        """Hand off only the identity of the current, revalidated review plan."""

        plan = self.current_plan
        trusted = self.planner.plans.load(plan.project_id) if plan is not None else None
        if (
            plan is None
            or trusted is None
            or trusted.plan_digest != plan.plan_digest
            or not trusted.ready_for_guardian_review
            or trusted.execution_authorized
            or trusted.bootloader_relock_permitted
        ):
            self.guardian_handoff_stopped(
                "The displayed plan is no longer the current review-ready plan. Refresh evidence "
                "and regenerate it; Guardian received no context and no action started."
            )
            return
        self.status.setText(
            "GUARDIAN REVIEW CONTEXT READY  •  Current plan revalidated  •  "
            "Approval: NONE  •  Execution: NONE"
        )
        self.status.setObjectName("Good")
        self._repolish(self.status)
        self.guardian_requested.emit(trusted.project_id, trusted.plan_digest)

    def _request_rom_studio(self) -> None:
        """Carry the selected project and current Nexus plan identity into Studio."""

        selected = self.project_selector.currentData()
        project_id = selected if isinstance(selected, str) else ""
        plan = self.current_plan
        plan_digest = (
            plan.plan_digest
            if plan is not None and plan.project_id == project_id
            else ""
        )
        self.rom_studio_requested.emit(project_id, plan_digest)

    def guardian_handoff_stopped(self, reason: str) -> None:
        """Keep a failed review handoff visible even when notifications are disabled."""

        self.status.setText(f"GUARDIAN HANDOFF STOPPED  •  {reason}")
        self.status.setObjectName("Danger")
        self._repolish(self.status)

    def _select_project(self, index: int) -> None:
        if not 0 <= index < len(self.projects):
            return
        project_id = self.projects[index].project_id
        profile = DeviceDnaStore(self.store).load(project_id)
        matrix = CompatibilityMatrixStore(self.store).load(project_id)
        self.generate_button.setEnabled(profile is not None and matrix is not None)
        if profile is None or matrix is None:
            self.current_plan = None
            missing = self._missing_evidence(profile is None, matrix is None)
            self.status.setText(
                "Evidence pending  •  Open ROM Studio to create Device DNA and Compatibility Matrix."
            )
            self.status.setObjectName("Warning")
            self._set_evidence_handoff(
                "Complete Device DNA and Compatibility Matrix",
                f"Missing for {self.projects[index].name}: {missing}. ROM Studio derives the "
                "records from this exact protected project and source. Nexus grants no approval "
                "and will not generate a route until both records are current.",
                True,
            )
        else:
            self.current_plan = self.planner.plans.load(project_id)
            self.status.setText(
                "Evidence ready  •  Nexus can create a route without changing the ROM or phone."
            )
            self.status.setObjectName("Good")
            self._set_evidence_handoff("", "", False)
        self._repolish(self.status)
        self._render(self.current_plan)

    @staticmethod
    def _missing_evidence(profile_missing: bool, matrix_missing: bool) -> str:
        missing = []
        if profile_missing:
            missing.append("Device DNA")
        if matrix_missing:
            missing.append("Compatibility Matrix")
        return " and ".join(missing)

    def _set_evidence_handoff(self, title: str, detail: str, visible: bool) -> None:
        self.evidence_handoff_title.setText(title)
        self.evidence_handoff_detail.setText(detail)
        self.evidence_handoff.setVisible(visible)

    def _objective_changed(self, label: str) -> None:
        self.flash_mode.setVisible(self.OBJECTIVES[label] is NexusObjective.FLASH_DEVICE)

    def _render(self, plan: NexusPlan | None) -> None:
        while self.route_layout.count() > 2:
            item = self.route_layout.takeAt(2)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.route_empty.setVisible(plan is None)
        self.export_button.setEnabled(plan is not None)
        self.guardian_button.setEnabled(bool(plan and plan.ready_for_guardian_review))
        if plan is None:
            self.foresight.setText("No impact prediction has been generated.")
            self.insight.setText("No decision timeline has been generated.")
            return
        self.status.setText(
            (
                "READY FOR GUARDIAN REVIEW"
                if plan.status is NexusPlanStatus.READY_FOR_GUARDIAN
                else "EVIDENCE REQUIRED BEFORE GUARDIAN REVIEW"
            )
            + f"  •  {plan.objective.value.replace('-', ' ').upper()}  •  "
            "Execution authority: NONE  •  Bootloader relock: NEVER"
        )
        self.status.setObjectName(
            "Good" if plan.status is NexusPlanStatus.READY_FOR_GUARDIAN else "Warning"
        )
        self._repolish(self.status)
        for stage in plan.route:
            frame = QFrame()
            frame.setObjectName("Card")
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(14, 10, 14, 10)
            mark = {
                RouteStageState.COMPLETE: "✓",
                RouteStageState.CURRENT: "●",
                RouteStageState.UPCOMING: "○",
                RouteStageState.BLOCKED: "■",
                RouteStageState.ADAPTED: "↻",
            }[stage.state]
            label = QLabel(
                f"{mark}  {stage.label.upper()}  •  {stage.state.value.replace('-', ' ').upper()}"
            )
            label.setObjectName(
                "Good"
                if stage.state in {RouteStageState.COMPLETE, RouteStageState.ADAPTED}
                else "Danger"
                if stage.state is RouteStageState.BLOCKED
                else "Warning"
                if stage.state is RouteStageState.CURRENT
                else "Muted"
            )
            detail = QLabel(
                f"{stage.explanation}\nRecommendation: {stage.recommendation}"
                + (f"\nBranch: {stage.branch}" if stage.branch else "")
            )
            detail.setObjectName("Muted")
            detail.setWordWrap(True)
            layout.addWidget(label)
            layout.addWidget(detail)
            self.route_layout.addWidget(frame)
        self.foresight.setText(
            "\n\n".join(
                f"{item.area.upper()}  •  IMPACT {item.impact.value.upper()}\n"
                f"Prediction: {item.prediction}\nDependencies: {', '.join(item.dependencies)}\n"
                f"Verify: {item.verification}\nConfidence: {item.confidence.value}"
                for item in plan.predictions
            )
        )
        research = (
            "\n\nRESEARCH REQUIRED\n"
            + "\n".join(f"• {item}" for item in plan.research_requirements)
            if plan.research_requirements
            else "\n\nRESEARCH STATUS\n• Required compatibility evidence is present for planning."
        )
        self.insight.setText(
            "\n\n".join(
                f"{item.question}\nDecision: {item.answer}\nWhy: {item.why}\n"
                f"Sources: {', '.join(item.source_ids) or 'none'}  •  Confidence: {item.confidence.value}"
                for item in plan.decisions
            )
            + research
        )

    @staticmethod
    def _section_title(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionTitle")
        return label

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
