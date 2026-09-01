from __future__ import annotations

import re
from contextlib import suppress
from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFileSystemModel,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from romverse.nexus.events import (
    LiveConsoleEventStore,
    LiveConsoleStoreError,
    MissionConfidence,
    MissionState,
)
from romverse.rom.models import ProjectError
from romverse.rom.recipes import (
    RecipeDraft,
    RecipeDraftStore,
    RecipeStep,
    RecipeStore,
    RomRecipe,
    preview_recipe,
    preview_recipe_changes,
)
from romverse.ui.guided_mission import GuidedBuildMission
from romverse.ui.knowledge_center import KnowledgeGuideDialog


class RecipeStageButton(QPushButton):
    def __init__(self, number: int, title: str) -> None:
        super().__init__(f"·   {number:02d}   {title}")
        self.number = number
        self.title = title
        self.setCheckable(True)
        self.setMinimumHeight(58)

    def set_status(self, status: str, selected: bool) -> None:
        symbol = {"complete": "✓", "ready": "◆", "locked": "·"}[status]
        self.setText(f"{symbol}   {self.number:02d}   {self.title}")
        self.setProperty("stageStatus", status)
        self.setChecked(selected)
        self.style().unpolish(self)
        self.style().polish(self)


class RecipeForgeSequence(QDialog):
    STAGES = (
        "Identity",
        "Operation",
        "Target",
        "Configure",
        "Guardian review",
        "Complete",
    )
    OPERATIONS = {
        "inspect": (
            "Inspect only",
            "Read and verify the target without changing it. Best for learning a new firmware tree.",
            "READ ONLY",
        ),
        "replace_file": (
            "Replace file",
            "Replace one contained file using an external source. Automatic rollback data is created before execution.",
            "REVERSIBLE CHANGE",
        ),
        "set_property": (
            "Set property",
            "Update or add one key=value entry in a contained UTF-8 property file.",
            "REVERSIBLE CHANGE",
        ),
        "remove_package": (
            "Remove package or path",
            "Remove one contained file or directory from the working tree after snapshot protection.",
            "REVERSIBLE CHANGE",
        ),
    }

    def __init__(
        self,
        studio,
        parent: QWidget | None = None,
        initial_target: str = "",
    ) -> None:
        super().__init__(parent or studio)
        self.studio = studio
        self.project = studio.current_project
        if self.project is None:
            raise ProjectError("Select a ROM project before opening Recipe Forge")
        self.project_dir = studio.store.projects_root / self.project.project_id
        self.tree_root = studio.store.working_root / self.project.project_id / "tree"
        if not self.tree_root.is_dir():
            raise ProjectError("Extract a contained working tree before opening Recipe Forge")
        self.stage = 0
        self.operation = ""
        self.target = ""
        self.draft_steps: list[RecipeStep] = []
        self.saved_recipe: RomRecipe | None = None
        self.stage_buttons: list[RecipeStageButton] = []
        self.operation_buttons: dict[str, QPushButton] = {}
        self.live_mission_id = ""
        self.live_progress = 0
        self.draft_resumed = False
        self.source_original_sha256 = (
            self.project.original.sha256 if self.project.original is not None else ""
        )
        self.draft_store = RecipeDraftStore(self.project_dir, studio.store.workspace)
        self._restoring_draft = True
        self.draft_save_timer = QTimer(self)
        self.draft_save_timer.setSingleShot(True)
        self.draft_save_timer.setInterval(350)
        self.draft_save_timer.timeout.connect(self._save_draft_now)

        self.setWindowTitle("ROMVERSE • Recipe Forge")
        self.setModal(True)
        self.setMinimumSize(980, 680)
        self.resize(1180, 790)
        self.setStyleSheet(GuidedBuildMission._stylesheet() + self._extra_stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        strip = QFrame()
        strip.setObjectName("ProgressStrip")
        strip_layout = QHBoxLayout(strip)
        strip_layout.setContentsMargins(28, 10, 28, 10)
        self.progress_copy = QLabel()
        self.progress_copy.setObjectName("MissionMuted")
        self.progress_line = QFrame()
        self.progress_line.setObjectName("RecipeProgress")
        self.progress_line.setFixedHeight(7)
        strip_layout.addWidget(self.progress_copy)
        strip_layout.addWidget(self.progress_line, 1)
        root.addWidget(strip)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_stage_rail())
        self.pages = QStackedWidget()
        self.pages.setObjectName("RecipePages")
        self.pages.addWidget(self._identity_page())
        self.pages.addWidget(self._operation_page())
        self.pages.addWidget(self._target_page())
        self.pages.addWidget(self._configuration_page())
        self.pages.addWidget(self._review_page())
        self.pages.addWidget(self._complete_page())
        body.addWidget(self.pages, 1)
        root.addLayout(body, 1)
        root.addWidget(self._build_footer())

        self._load_existing_identity()
        if initial_target:
            path = (self.tree_root / initial_target).resolve(strict=False)
            root_path = self.tree_root.resolve()
            if (
                path != root_path
                and path.is_relative_to(root_path)
                and path.exists()
                and not path.is_symlink()
            ):
                self.target = path.relative_to(root_path).as_posix()
                kind = "Directory" if path.is_dir() else "File"
                self.target_label.setText(f"{kind}  •  {self.target}")
        self._restoring_draft = False
        self._render()
        if initial_target:
            self._schedule_draft_save()

    def closeEvent(self, event) -> None:
        if self.saved_recipe is None:
            self._save_draft_now()
            self._finish_recipe_live(
                MissionState.ATTENTION,
                "Recipe Forger was paused before a reviewed Recipe was saved.",
                "The isolated working tree and protected firmware were not changed by Recipe design.",
                "Reopen Recipe Forger to continue the reviewed design process.",
                MissionConfidence.HIGH,
            )
        super().closeEvent(event)

    def reject(self) -> None:
        if self.saved_recipe is None:
            self._save_draft_now()
            self._finish_recipe_live(
                MissionState.ATTENTION,
                "Recipe Forger was cancelled before saving.",
                "No Recipe execution occurred and no phone or protected firmware was changed.",
                "Reopen Recipe Forger when you are ready to design a bounded change.",
                MissionConfidence.HIGH,
            )
        super().reject()

    def _live_console_store(self) -> LiveConsoleEventStore | None:
        store = getattr(self.studio, "live_console_store", None)
        return store if isinstance(store, LiveConsoleEventStore) else None

    def _finish_recipe_live(
        self,
        state: MissionState,
        summary: str,
        explanation: str,
        next_action: str,
        confidence: MissionConfidence,
    ) -> None:
        mission_id = self.live_mission_id
        self.live_mission_id = ""
        self.live_progress = 0
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
                evidence_refs=(f"projects/{self.project.project_id}/recipe.romverse",),
            )

    def _sync_recipe_live(self, valid: bool, validation: str) -> None:
        store = self._live_console_store()
        if store is None:
            return
        if self.saved_recipe is not None:
            if self.live_mission_id:
                self._finish_recipe_live(
                    MissionState.SUCCEEDED,
                    f"Recipe {self.saved_recipe.name} was saved and execution remains locked.",
                    "ROMVERSE verified the contained targets and conflict scan. No Recipe was executed and no phone was changed.",
                    "Preview the saved Recipe, then request input-bound Guardian approval before local execution.",
                    MissionConfidence.VERIFIED,
                )
            else:
                with suppress(LiveConsoleStoreError):
                    store.note(
                        source="Recipe Forger",
                        stage="recipe-saved",
                        title=f"Recipe saved — {self.saved_recipe.name}",
                        summary="The reviewed Recipe manifest is saved and execution locked.",
                        explanation="ROMVERSE revalidated the saved Recipe without executing it.",
                        next_action="Preview its exact targets before requesting Guardian approval.",
                        state=MissionState.INFORMATION,
                        progress_percent=100,
                        confidence=MissionConfidence.VERIFIED,
                        guardian_protected=True,
                        project_id=self.project.project_id,
                        evidence_refs=(f"projects/{self.project.project_id}/recipe.romverse",),
                        dedupe_key=f"recipe-saved-{self.saved_recipe.digest()}",
                    )
            return
        if not self.live_mission_id:
            try:
                event = store.start(
                    source="Recipe Forger",
                    stage="recipe-design",
                    title=f"Forge a reviewed Recipe for {self.project.name}",
                    summary="ROMVERSE opened the six-stage Recipe design workflow.",
                    explanation="Recipe Forger designs contained working-tree changes; it cannot execute them or modify a phone.",
                    next_action="Give the Recipe a clear single-purpose identity.",
                    project_id=self.project.project_id,
                    confidence=MissionConfidence.UNCONFIRMED,
                    guardian_protected=True,
                    evidence_refs=(f"projects/{self.project.project_id}/guided-mission.json",),
                )
            except LiveConsoleStoreError:
                return
            self.live_mission_id = event.mission_id
            self.live_progress = 0
        progress = max(self.live_progress, round(self.stage * 100 / (len(self.STAGES) - 1)))
        try:
            store.progress(
                self.live_mission_id,
                progress,
                summary=f"Stage {self.stage + 1} of {len(self.STAGES)} — {self.STAGES[self.stage]}.",
                explanation=(
                    "Current inputs pass the stage checks."
                    if valid
                    else f"ROMVERSE is waiting for a valid input: {validation}"
                )
                + " Execution remains locked and the phone is not a Recipe target.",
                next_action=validation,
            )
            self.live_progress = progress
        except LiveConsoleStoreError:
            self.live_mission_id = ""
            self.live_progress = 0

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

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("MissionHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 18, 28, 18)
        heading = QVBoxLayout()
        eyebrow = QLabel("ROM STUDIO  /  RECIPE FORGE")
        eyebrow.setObjectName("MissionEyebrow")
        title = QLabel("Turn an idea into a safe, auditable ROM change")
        title.setObjectName("MissionTitle")
        heading.addWidget(eyebrow)
        heading.addWidget(title)
        layout.addLayout(heading, 1)
        badge = QLabel("◆  WORKING TREE ONLY")
        badge.setObjectName("GuardianBadge")
        layout.addWidget(badge)
        return header

    def _build_stage_rail(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("StageRail")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedWidth(285)
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(14, 18, 14, 18)
        layout.setSpacing(6)
        title = QLabel("FORGE STAGES")
        title.setObjectName("MissionEyebrow")
        layout.addWidget(title)
        layout.addSpacing(4)
        for index, name in enumerate(self.STAGES):
            button = RecipeStageButton(index + 1, name)
            button.clicked.connect(lambda _checked=False, i=index: self._visit_stage(i))
            layout.addWidget(button)
            self.stage_buttons.append(button)
        layout.addStretch()
        scroll.setWidget(host)
        return scroll

    def _page(self, eyebrow: str, title: str, detail: str) -> tuple[QWidget, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setObjectName("MissionMain")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(34, 28, 34, 24)
        layout.setSpacing(14)
        step = QLabel(eyebrow)
        step.setObjectName("MissionEyebrow")
        heading = QLabel(title)
        heading.setObjectName("StageTitle")
        heading.setWordWrap(True)
        copy = QLabel(detail)
        copy.setObjectName("MissionBody")
        copy.setWordWrap(True)
        layout.addWidget(step)
        layout.addWidget(heading)
        layout.addWidget(copy)
        scroll.setWidget(host)
        return scroll, layout

    def _card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("MissionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(9)
        heading = QLabel(title)
        heading.setObjectName("CardHeading")
        layout.addWidget(heading)
        return card, layout

    def _identity_page(self) -> QWidget:
        page, layout = self._page(
            "STAGE 01  •  RECIPE IDENTITY",
            "Name the change you want to create",
            "Give this Recipe a clear identity. It becomes part of the project evidence and can be reviewed before any change is applied.",
        )
        card, form = self._card("RECIPE DETAILS")
        name_label = QLabel("Recipe name")
        name_label.setObjectName("FieldLabel")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Example: Enable ROMVERSE system property")
        self.name_input.setMaxLength(80)
        description_label = QLabel("Purpose")
        description_label.setObjectName("FieldLabel")
        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Explain why this change belongs in the ROM")
        self.description_input.setMaxLength(240)
        form.addWidget(name_label)
        form.addWidget(self.name_input)
        form.addWidget(description_label)
        form.addWidget(self.description_input)
        layout.addWidget(card)
        recommendation, body = self._card("RECOMMENDATION")
        body_copy = QLabel(
            "Describe one goal, not an entire ROM release. Focused Recipes are easier to inspect, diagnose, reuse, and roll back."
        )
        body_copy.setObjectName("CardBody")
        body_copy.setWordWrap(True)
        body.addWidget(body_copy)
        layout.addWidget(recommendation)
        layout.addStretch()
        self.name_input.textChanged.connect(self._render)
        self.name_input.textChanged.connect(self._schedule_draft_save)
        self.description_input.textChanged.connect(self._schedule_draft_save)
        return page

    def _operation_page(self) -> QWidget:
        page, layout = self._page(
            "STAGE 02  •  CHOOSE AN OPERATION",
            "What should this Recipe do?",
            "Choose one bounded operation. ROMVERSE explains its effect and applies the matching Guardian protections automatically.",
        )
        grid = QGridLayout()
        grid.setSpacing(12)
        self.operation_group = QButtonGroup(self)
        self.operation_group.setExclusive(True)
        icons = {"inspect": "◎", "replace_file": "⇄", "set_property": "≡", "remove_package": "−"}
        for index, (operation, (title, detail, risk)) in enumerate(self.OPERATIONS.items()):
            card, card_layout = self._card(risk)
            button = QPushButton(f"{icons[operation]}   {title}")
            button.setObjectName("OperationTile")
            button.setCheckable(True)
            button.setMinimumHeight(48)
            button.setToolTip(detail)
            button.clicked.connect(
                lambda _checked=False, value=operation: self._choose_operation(value)
            )
            copy = QLabel(detail)
            copy.setObjectName("CardBody")
            copy.setWordWrap(True)
            copy.setMinimumHeight(48)
            card_layout.addWidget(button)
            card_layout.addWidget(copy)
            self.operation_group.addButton(button)
            self.operation_buttons[operation] = button
            grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(grid)
        boundary, boundary_layout = self._card("GUARDIAN BOUNDARY")
        copy = QLabel(
            "Every option targets only the isolated working tree. Protected firmware and connected phones are never Recipe targets. Mutations receive automatic rollback snapshots during execution."
        )
        copy.setObjectName("CardBody")
        copy.setWordWrap(True)
        boundary_layout.addWidget(copy)
        layout.addWidget(boundary)
        layout.addStretch()
        return page

    def _target_page(self) -> QWidget:
        page, layout = self._page(
            "STAGE 03  •  SELECT TARGET",
            "Choose the exact working-tree target",
            "Browse the contained extraction tree. ROMVERSE stores a relative path, so this Recipe cannot escape into the protected source or operating system.",
        )
        self.target_model = QFileSystemModel(self)
        self.target_model.setFilter(
            QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot
        )
        self.target_model.setRootPath(str(self.tree_root))
        self.target_tree = QTreeView()
        self.target_tree.setObjectName("TargetTree")
        self.target_tree.setModel(self.target_model)
        self.target_tree.setRootIndex(self.target_model.index(str(self.tree_root)))
        self.target_tree.setHeaderHidden(True)
        self.target_tree.setAnimated(False)
        self.target_tree.setSortingEnabled(True)
        self.target_tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        for column in (1, 2, 3):
            self.target_tree.hideColumn(column)
        self.target_tree.clicked.connect(self._target_clicked)
        self.target_tree.setMinimumHeight(300)
        layout.addWidget(self.target_tree, 1)
        selected_card, selected_layout = self._card("SELECTED TARGET")
        self.target_label = QLabel("Choose a file or directory from the working tree.")
        self.target_label.setObjectName("CardBody")
        self.target_label.setWordWrap(True)
        selected_layout.addWidget(self.target_label)
        layout.addWidget(selected_card)
        return page

    def _configuration_page(self) -> QWidget:
        page, layout = self._page(
            "STAGE 04  •  CONFIGURE",
            "Provide only what this operation needs",
            "Recipe Forge adapts this stage to the selected operation and validates every input before review.",
        )
        self.config_card, form = self._card("OPERATION SETTINGS")
        self.config_explanation = QLabel()
        self.config_explanation.setObjectName("CardBody")
        self.config_explanation.setWordWrap(True)
        form.addWidget(self.config_explanation)

        self.source_row = QWidget()
        source_layout = QHBoxLayout(self.source_row)
        source_layout.setContentsMargins(0, 0, 0, 0)
        self.source_input = QLineEdit()
        self.source_input.setReadOnly(True)
        self.source_input.setPlaceholderText("Choose the replacement file")
        choose_source = QPushButton("Browse…")
        choose_source.clicked.connect(self._choose_source)
        source_layout.addWidget(self.source_input, 1)
        source_layout.addWidget(choose_source)
        form.addWidget(self.source_row)

        self.property_row = QWidget()
        property_layout = QGridLayout(self.property_row)
        property_layout.setContentsMargins(0, 0, 0, 0)
        key_label = QLabel("Property key")
        key_label.setObjectName("FieldLabel")
        value_label = QLabel("Value")
        value_label.setObjectName("FieldLabel")
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("ro.romverse.feature")
        self.value_input = QLineEdit()
        self.value_input.setPlaceholderText("enabled")
        property_layout.addWidget(key_label, 0, 0)
        property_layout.addWidget(value_label, 0, 1)
        property_layout.addWidget(self.key_input, 1, 0)
        property_layout.addWidget(self.value_input, 1, 1)
        form.addWidget(self.property_row)

        self.remove_ack = QCheckBox(
            "I understand this path will be removed only from the isolated working tree and protected by a rollback snapshot when executed."
        )
        form.addWidget(self.remove_ack)
        layout.addWidget(self.config_card)
        target_card, target_layout = self._card("BOUND TARGET")
        self.config_target = QLabel()
        self.config_target.setObjectName("CardBody")
        self.config_target.setWordWrap(True)
        target_layout.addWidget(self.config_target)
        layout.addWidget(target_card)
        layout.addStretch()
        self.source_input.textChanged.connect(self._render)
        self.source_input.textChanged.connect(self._schedule_draft_save)
        self.key_input.textChanged.connect(self._render)
        self.key_input.textChanged.connect(self._schedule_draft_save)
        self.value_input.textChanged.connect(self._render)
        self.value_input.textChanged.connect(self._schedule_draft_save)
        self.remove_ack.toggled.connect(self._render)
        self.remove_ack.toggled.connect(self._schedule_draft_save)
        return page

    def _review_page(self) -> QWidget:
        page, layout = self._page(
            "STAGE 05  •  GUARDIAN REVIEW",
            "Review the complete Recipe contract",
            "Nothing is applied here. Recipe Forge validates and saves an execution-locked plan that must still be previewed and explicitly approved before it can change the working tree.",
        )
        summary_card, summary_layout = self._card("RECIPE MANIFEST")
        self.review_summary = QLabel()
        self.review_summary.setObjectName("ReviewSummary")
        self.review_summary.setWordWrap(True)
        self.review_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        summary_layout.addWidget(self.review_summary)
        layout.addWidget(summary_card)
        preview_card, preview_layout = self._card("CHANGE PREVIEW")
        self.change_preview = QLabel()
        self.change_preview.setObjectName("ChangePreview")
        self.change_preview.setWordWrap(True)
        self.change_preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        preview_layout.addWidget(self.change_preview)
        layout.addWidget(preview_card)
        safeguards, safeguards_layout = self._card("AUTOMATIC SAFEGUARDS")
        safeguard_copy = QLabel(
            "✓ Contained relative target\n"
            "✓ Protected original excluded\n"
            "✓ Execution remains locked\n"
            "✓ Input-bound Guardian approval required\n"
            "✓ Affected target snapshotted before mutation\n"
            "✓ Result verified with automatic failure rollback"
        )
        safeguard_copy.setObjectName("GoodCopy")
        safeguards_layout.addWidget(safeguard_copy)
        layout.addWidget(safeguards)
        self.replace_existing = QCheckBox("Replace the existing saved Recipe for this project")
        self.replace_existing.toggled.connect(self._render)
        self.replace_existing.toggled.connect(self._schedule_draft_save)
        layout.addWidget(self.replace_existing)
        layout.addStretch()
        return page

    def _complete_page(self) -> QWidget:
        page, layout = self._page(
            "STAGE 06  •  COMPLETE",
            "Recipe forged and ready for preview",
            "The Recipe manifest is saved with a stable digest. Return to ROM Studio to preview its resolved target before requesting Guardian execution approval.",
        )
        receipt, receipt_layout = self._card("FORGE RECEIPT")
        self.completion_summary = QLabel()
        self.completion_summary.setObjectName("ReviewSummary")
        self.completion_summary.setWordWrap(True)
        self.completion_summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        receipt_layout.addWidget(self.completion_summary)
        layout.addWidget(receipt)
        next_card, next_layout = self._card("NEXT RECOMMENDED ACTION")
        copy = QLabel(
            "Use Preview recipe in ROM Studio. If the target resolves exactly as expected, run the approved Recipe; ROMVERSE will snapshot, apply, verify, and roll back automatically on failure."
        )
        copy.setObjectName("CardBody")
        copy.setWordWrap(True)
        next_layout.addWidget(copy)
        layout.addWidget(next_card)
        layout.addStretch()
        return page

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("MissionFooter")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(24, 14, 24, 14)
        self.back_button = QPushButton("←  Back")
        self.back_button.clicked.connect(self._back)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.learn_button = QPushButton("Learn this stage")
        self.learn_button.setObjectName("SecondaryAction")
        self.learn_button.setToolTip(
            "Open verified beginner guidance without leaving Recipe Forger or losing this draft."
        )
        self.learn_button.clicked.connect(self._open_stage_learning)
        self.validation_label = QLabel()
        self.validation_label.setObjectName("MissionMuted")
        self.validation_label.setWordWrap(True)
        self.next_button = QPushButton("Next  →")
        self.next_button.setObjectName("MissionNext")
        self.next_button.clicked.connect(self._next)
        self.add_step_button = QPushButton("Add another step")
        self.add_step_button.setObjectName("SecondaryAction")
        self.add_step_button.clicked.connect(self._add_another_step)
        layout.addWidget(self.back_button)
        layout.addWidget(cancel)
        layout.addWidget(self.learn_button)
        layout.addWidget(self.validation_label, 1)
        layout.addWidget(self.add_step_button)
        layout.addWidget(self.next_button)
        return footer

    def _open_stage_learning(self) -> None:
        guide = KnowledgeGuideDialog(
            f"Recipe Forger stage {self.stage + 1}",
            f"Stage {self.stage + 1} of {len(self.STAGES)}  •  {self.STAGES[self.stage]}",
            self,
        )
        guide.exec()

    def _load_existing_identity(self) -> None:
        existing = RecipeStore().load(self.project_dir)
        draft = (
            self.draft_store.load(self.project.project_id, self.source_original_sha256)
            if self.source_original_sha256
            else None
        )
        if draft is not None:
            self._restore_draft(draft)
            self.draft_resumed = True
            self.replace_existing.setVisible(existing is not None)
            self.studio.operation_status.setText(
                f"Recipe Forger resumed a private draft at stage {self.stage + 1}. No Recipe was executed."
            )
            return
        if existing is not None:
            self.name_input.setText(existing.name)
            self.description_input.setText(existing.description)
            self.replace_existing.setVisible(True)
        else:
            self.replace_existing.setVisible(False)

    def _restore_draft(self, draft: RecipeDraft) -> None:
        self.name_input.setText(draft.name)
        self.description_input.setText(draft.description)
        self.operation = draft.operation
        if draft.operation in self.operation_buttons:
            self.operation_buttons[draft.operation].setChecked(True)
        self.source_input.setText(draft.source_input)
        self.key_input.setText(draft.property_key)
        self.value_input.setText(draft.property_value)
        self.remove_ack.setChecked(draft.remove_acknowledged)
        self.replace_existing.setChecked(draft.replace_existing)
        self.draft_steps = list(draft.steps)
        self.stage = min(draft.stage, 4)

        unsafe_steps = any(not self._restored_target_is_safe(step.target) for step in draft.steps)
        if unsafe_steps:
            self.draft_steps.clear()
            self.stage = min(self.stage, 1)
        if draft.target and self._restored_target_is_safe(draft.target):
            self.target = draft.target
            candidate = self.tree_root / draft.target
            kind = "Directory" if candidate.is_dir() else "File"
            self.target_label.setText(f"{kind}  •  {self.target}")
        else:
            self.target = ""
            if self.stage > 2:
                self.stage = 2
            self.target_label.setText("Choose a file or directory from the working tree.")
        if not self.operation and self.stage > 1:
            self.stage = 1

    def _restored_target_is_safe(self, target: str) -> bool:
        if not target:
            return False
        root = self.tree_root.resolve()
        candidate = (root / target).resolve(strict=False)
        return (
            candidate != root
            and candidate.is_relative_to(root)
            and candidate.exists()
            and not candidate.is_symlink()
        )

    def _schedule_draft_save(self, *_args) -> None:
        if self._restoring_draft or self.saved_recipe is not None:
            return
        self.draft_save_timer.start()

    def _save_draft_now(self) -> None:
        self.draft_save_timer.stop()
        if (
            self._restoring_draft
            or self.saved_recipe is not None
            or not self.source_original_sha256
            or not hasattr(self, "name_input")
        ):
            return
        draft = RecipeDraft(
            1,
            self.project.project_id,
            self.source_original_sha256,
            "",
            min(self.stage, 4),
            self.name_input.text(),
            self.description_input.text(),
            self.operation,
            self.target,
            self.source_input.text(),
            self.key_input.text(),
            self.value_input.text(),
            self.remove_ack.isChecked(),
            self.replace_existing.isChecked(),
            tuple(self.draft_steps),
        )
        try:
            self.draft_store.save(draft)
        except (OSError, ProjectError) as exc:
            self.studio.operation_status.setText(
                f"Recipe draft could not be preserved: {exc}. The working tree was not changed."
            )

    def _choose_operation(self, operation: str) -> None:
        self.operation = operation
        self._render()
        self._schedule_draft_save()

    def _target_clicked(self, index: QModelIndex) -> None:
        path = Path(self.target_model.filePath(index)).resolve(strict=False)
        root = self.tree_root.resolve()
        if path == root or not path.is_relative_to(root) or path.is_symlink():
            self.target = ""
            self.target_label.setText(
                "Choose a contained file or directory; the working-tree root and symbolic links cannot be targets."
            )
        else:
            self.target = path.relative_to(root).as_posix()
            kind = "Directory" if path.is_dir() else "File"
            self.target_label.setText(f"{kind}  •  {self.target}")
        self._render()
        self._schedule_draft_save()

    def _choose_source(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose replacement source",
            str(Path.home()),
            "All files (*)",
        )
        if selected:
            self.source_input.setText(selected)

    def _visit_stage(self, index: int) -> None:
        if index <= self.stage or (self.saved_recipe is not None and index == 5):
            self.stage = index
            self._render()
            self._schedule_draft_save()

    def _back(self) -> None:
        if self.stage > 0 and self.saved_recipe is None:
            self.stage -= 1
            self._render()
            self._schedule_draft_save()

    def _next(self) -> None:
        valid, message = self._validate_stage()
        if not valid:
            self.validation_label.setText(message)
            return
        if self.stage < 4:
            self.stage += 1
            self._render()
            self._schedule_draft_save()
            return
        if self.stage == 4:
            self._save_recipe()
            return
        self.accept()

    def _validate_stage(self) -> tuple[bool, str]:
        if self.stage == 0:
            if not self.name_input.text().strip():
                return False, "Enter a clear Recipe name to continue."
            return True, "Identity ready"
        if self.stage == 1:
            return (bool(self.operation), "Choose one bounded operation to continue.")
        if self.stage == 2:
            if not self.target:
                return False, "Select a contained target from the working tree."
            path = (self.tree_root / self.target).resolve(strict=False)
            if self.operation in {"replace_file", "set_property"} and not path.is_file():
                return False, "This operation requires an existing regular file target."
            return True, "Target contained and ready"
        if self.stage == 3:
            if self.operation == "replace_file":
                source = Path(self.source_input.text()).expanduser()
                if not source.is_file() or source.is_symlink():
                    return False, "Choose a regular replacement source file."
            elif self.operation == "set_property":
                key = self.key_input.text().strip()
                value = self.value_input.text()
                if not key or not re.fullmatch(r"[A-Za-z0-9._-]+", key):
                    return (
                        False,
                        "Property keys may use letters, numbers, dot, dash, and underscore.",
                    )
                if any(character in value for character in "\r\n\0"):
                    return False, "Property values cannot contain line breaks or null bytes."
                target = self.tree_root / self.target
                if target.stat().st_size > 16 * 1024 * 1024:
                    return False, "Property files must be no larger than 16 MiB."
                try:
                    target.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    return False, "The selected property target is not valid UTF-8 text."
            elif self.operation == "remove_package" and not self.remove_ack.isChecked():
                return False, "Acknowledge the isolated working-tree removal before review."
            return True, "Configuration validated"
        if self.stage == 4:
            conflict = self._recipe_conflict(self._draft_recipe())
            if conflict:
                return False, conflict
            existing = RecipeStore().load(self.project_dir)
            if existing is not None and not self.replace_existing.isChecked():
                return False, "Confirm replacement of the project's existing Recipe."
            return True, "Guardian review complete"
        return True, "Recipe saved"

    def _draft_recipe(self) -> RomRecipe:
        current = self._draft_current_step()
        steps = (*self.draft_steps, current)
        name = self.name_input.text().strip()
        recipe_id = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "recipe"
        return RomRecipe(
            1,
            recipe_id,
            name,
            self.description_input.text().strip()
            or "User-authored Guardian-controlled local Recipe",
            steps,
        )

    def _draft_current_step(self) -> RecipeStep:
        parameters: tuple[tuple[str, str], ...] = ()
        if self.operation == "replace_file":
            parameters = (("source", str(Path(self.source_input.text()).resolve())),)
        elif self.operation == "set_property":
            parameters = (
                ("key", self.key_input.text().strip()),
                ("value", self.value_input.text()),
            )
        return RecipeStep(
            f"step-{len(self.draft_steps) + 1}", self.operation, self.target, parameters
        )

    def _add_another_step(self) -> None:
        if self.stage != 4:
            return
        recipe = self._draft_recipe()
        conflict = self._recipe_conflict(recipe)
        if conflict:
            self.validation_label.setText(conflict)
            return
        self.draft_steps.append(recipe.steps[-1])
        self.operation = ""
        self.target = ""
        self.source_input.clear()
        self.key_input.clear()
        self.value_input.clear()
        self.remove_ack.setChecked(False)
        self.target_label.setText("Choose a file or directory from the working tree.")
        self.operation_group.setExclusive(False)
        for button in self.operation_buttons.values():
            button.setChecked(False)
        self.operation_group.setExclusive(True)
        self.stage = 1
        self._render()
        self._schedule_draft_save()

    @staticmethod
    def _recipe_conflict(recipe: RomRecipe) -> str:
        mutations = [step for step in recipe.steps if step.operation != "inspect"]
        for index, left in enumerate(mutations):
            left_path = Path(left.target)
            for right in mutations[index + 1 :]:
                right_path = Path(right.target)
                if left_path == right_path:
                    if left.operation == right.operation == "set_property":
                        left_key = dict(left.parameters).get("key")
                        right_key = dict(right.parameters).get("key")
                        if left_key != right_key:
                            continue
                    return (
                        f"Steps {left.step_id} and {right.step_id} both mutate {left.target}. "
                        "Combine or remove the conflicting step."
                    )
                if left_path in right_path.parents or right_path in left_path.parents:
                    return f"Steps {left.step_id} and {right.step_id} overlap parent and child targets."
        return ""

    def _save_recipe(self) -> None:
        try:
            recipe = self._draft_recipe()
            conflict = self._recipe_conflict(recipe)
            if conflict:
                raise ProjectError(conflict)
            preview = preview_recipe(recipe, self.tree_root)
            if preview.unresolved_targets:
                raise ProjectError("Recipe target no longer exists in the working tree")
            recipe_store = RecipeStore()
            recipe_store.save(self.project_dir, recipe)
            sealed_recipe = recipe_store.load(self.project_dir)
            if sealed_recipe is None or sealed_recipe.digest() != recipe.digest():
                raise ProjectError("The saved Recipe could not be reverified")
        except (OSError, ProjectError) as exc:
            QMessageBox.warning(self, "Recipe not saved", str(exc))
            return
        self.saved_recipe = sealed_recipe
        self.draft_save_timer.stop()
        self.draft_store.delete()
        self.stage = 5
        self.studio.operation_status.setText(
            "Recipe Forge complete. Preview the saved target before requesting Guardian execution approval."
        )
        self.studio.operation_status.setObjectName("Good")
        self.studio._repolish(self.studio.operation_status)
        self.studio.refresh(self.project.project_id)
        self._render()

    def _render(self) -> None:
        self.pages.setCurrentIndex(self.stage) if hasattr(self, "pages") else None
        for index, button in enumerate(self.stage_buttons):
            status = (
                "complete"
                if index < self.stage or (self.saved_recipe is not None and index == self.stage)
                else "ready"
                if index == self.stage
                else "locked"
            )
            button.set_status(status, index == self.stage)
        if not hasattr(self, "next_button"):
            return
        progress_notes = []
        if self.draft_resumed:
            progress_notes.append("DRAFT RESUMED")
        if self.draft_steps:
            progress_notes.append(f"{len(self.draft_steps)} STEP(S) ADDED")
        draft_note = "" if not progress_notes else "  •  " + "  •  ".join(progress_notes)
        self.progress_copy.setText(f"STAGE {self.stage + 1} OF {len(self.STAGES)}{draft_note}")
        progress = round(self.stage * 100 / (len(self.STAGES) - 1))
        self.progress_line.setStyleSheet(
            "QFrame#RecipeProgress { border-radius: 3px; "
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #9C43F2, stop:{progress / 100:.2f} #21D9EE, stop:{min(1.0, progress / 100 + 0.01):.2f} #101A2C, stop:1 #101A2C); }}"
        )
        valid, message = self._validate_stage()
        self.validation_label.setText(message)
        self._sync_recipe_live(valid, message)
        self.next_button.setEnabled(valid)
        self.next_button.setText(
            "Done" if self.stage == 5 else "Forge Recipe" if self.stage == 4 else "Next  →"
        )
        self.back_button.setEnabled(self.stage > 0 and self.saved_recipe is None)
        self.add_step_button.setVisible(self.stage == 4 and self.saved_recipe is None)
        if self.stage == 3:
            self._render_configuration()
        elif self.stage == 4:
            self._render_review()
        elif self.stage == 5 and self.saved_recipe is not None:
            operations = ", ".join(
                self.OPERATIONS[step.operation][0] for step in self.saved_recipe.steps
            )
            self.completion_summary.setText(
                f"Recipe  •  {self.saved_recipe.name}\n"
                f"Steps  •  {len(self.saved_recipe.steps)}\n"
                f"Operations  •  {operations}\n"
                + "\n".join(f"{step.step_id}  •  {step.target}" for step in self.saved_recipe.steps)
                + "\n"
                f"Digest  •  {self.saved_recipe.digest()}\n"
                f"Storage  •  Private schema {self.saved_recipe.persistence_schema_version}\n"
                "State  •  Saved and execution locked"
            )

    def _render_configuration(self) -> None:
        title, detail, risk = self.OPERATIONS[self.operation]
        self.config_explanation.setText(f"{title}  •  {risk}\n\n{detail}")
        self.config_target.setText(self.target)
        self.source_row.setVisible(self.operation == "replace_file")
        self.property_row.setVisible(self.operation == "set_property")
        self.remove_ack.setVisible(self.operation == "remove_package")

    def _render_review(self) -> None:
        recipe = self._draft_recipe()
        title, _detail, risk = self.OPERATIONS[self.operation]
        parameters = dict(recipe.steps[-1].parameters)
        configuration = "None required"
        if self.operation == "replace_file":
            configuration = f"Replacement  •  {Path(parameters['source']).name}"
        elif self.operation == "set_property":
            configuration = f"Property  •  {parameters['key']}={parameters['value']}"
        elif self.operation == "remove_package":
            configuration = "Removal acknowledged; rollback snapshot required"
        step_lines = "\n".join(
            f"{step.step_id}  •  {self.OPERATIONS[step.operation][0]}  →  {step.target}"
            for step in recipe.steps
        )
        conflict = self._recipe_conflict(recipe)
        self.review_summary.setText(
            f"Name  •  {recipe.name}\n"
            f"Purpose  •  {recipe.description}\n"
            f"Steps  •  {len(recipe.steps)}\n\n"
            f"{step_lines}\n\n"
            f"Current operation  •  {title}\n"
            f"Current risk class  •  {risk}\n"
            f"Current configuration  •  {configuration}\n"
            f"Recipe digest  •  {recipe.digest()}\n"
            f"Conflict scan  •  {conflict or 'CLEAR'}\n"
            "Execution  •  Locked until preview and explicit Guardian approval"
        )
        try:
            previews = preview_recipe_changes(recipe, self.tree_root)
            blocks = []
            for index, item in enumerate(previews, 1):
                state = "CHANGE" if item.changed else "NO CHANGE"
                blocks.append(
                    f"{index:02d}  •  {state}  •  {item.target}\n{item.summary}\n{item.detail}"
                )
            self.change_preview.setText("\n\n".join(blocks))
        except (OSError, ProjectError) as exc:
            self.change_preview.setText(f"Preview unavailable  •  {exc}")

    @staticmethod
    def _extra_stylesheet() -> str:
        return """
            QStackedWidget#RecipePages { background: #02050A; }
            QLineEdit {
                color: #EEF4FF; background: #070D17; border: 1px solid #263B5D;
                border-radius: 8px; padding: 10px 12px; selection-background-color: #6E42C8;
            }
            QLineEdit:focus { border-color: #39D9EF; }
            QLabel#FieldLabel { color: #B9C8E1; font-weight: 700; }
            QPushButton#OperationTile { text-align: left; padding: 11px 13px; font-size: 13px; }
            QPushButton#OperationTile:checked {
                color: #FFFFFF; background: #17112C; border: 2px solid #A64EF0;
            }
            QTreeView#TargetTree {
                color: #DCE8FA; background: #050A12; border: 1px solid #243653;
                border-radius: 10px; padding: 7px; alternate-background-color: #07101D;
            }
            QTreeView#TargetTree::item { min-height: 28px; }
            QTreeView#TargetTree::item:selected { background: #283061; color: #FFFFFF; }
            QCheckBox { color: #C7D4EA; spacing: 9px; }
            QCheckBox::indicator {
                width: 18px; height: 18px; border: 1px solid #526A93;
                border-radius: 4px; background: #07101A;
            }
            QCheckBox::indicator:checked { background: #36D39B; border-color: #76F2C1; }
            QLabel#ReviewSummary { color: #DCE7F8; font-family: monospace; font-size: 13px; }
            QLabel#ChangePreview {
                color: #BEEBFF; font-family: monospace; font-size: 12px;
                background: #050A12; border: 1px solid #1E4260;
                border-radius: 8px; padding: 12px;
            }
            QLabel#GoodCopy { color: #5EEAAF; font-size: 13px; }
        """
