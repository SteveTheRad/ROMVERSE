from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, Qt, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileSystemModel,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from romverse.rom.filesystems import FilesystemManifest
from romverse.rom.models import ProjectError
from romverse.rom.payloads import PayloadManifest, PayloadPartition
from romverse.ui.formatters import human_bytes
from romverse.ui.guided_mission import GuidedBuildMission
from romverse.ui.process_progress import ProcessProgressBar


class PartitionWorkspace(QDialog):
    def __init__(self, studio) -> None:
        super().__init__(studio)
        self.studio = studio
        self.project = studio.current_project
        if self.project is None:
            raise ProjectError("Select a project before opening Partition Atlas")
        self.service = studio.payload_service
        self.manifest: PayloadManifest | None = None
        self._filesystem_plan = None
        self.busy = False

        self.setWindowTitle("ROMVERSE • Partition Atlas")
        self.setModal(True)
        self.setMinimumSize(1020, 690)
        self.resize(1220, 800)
        self.setStyleSheet(GuidedBuildMission._stylesheet() + self._extra_stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._header())

        body = QVBoxLayout()
        body.setContentsMargins(28, 22, 28, 18)
        body.setSpacing(14)
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.partition_count = self._stat_card(cards, "PARTITIONS", "—")
        self.selected_size = self._stat_card(cards, "RECOMMENDED SET", "—")
        self.extracted_count = self._stat_card(cards, "EXTRACTED", "—")
        self.safety_state = self._stat_card(cards, "GUARDIAN BUDGET", "Waiting")
        body.addLayout(cards)

        self.table = QTableWidget(0, 5)
        self.table.setObjectName("PartitionTable")
        self.table.setHorizontalHeaderLabels(
            ("Partition", "Category", "Estimated size", "Workspace state", "Protection")
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.itemChanged.connect(self._selection_changed)
        self.table.itemSelectionChanged.connect(self._show_partition_detail)
        body.addWidget(self.table, 1)

        detail = QFrame()
        detail.setObjectName("MissionCard")
        detail_layout = QHBoxLayout(detail)
        detail_layout.setContentsMargins(18, 14, 18, 14)
        detail_title = QLabel("PARTITION EVIDENCE")
        detail_title.setObjectName("CardHeading")
        self.detail = QLabel(
            "Scan payload.bin to build a verified partition map. No phone operation is performed."
        )
        self.detail.setObjectName("CardBody")
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail_layout.addWidget(detail_title)
        detail_layout.addWidget(self.detail, 1)
        body.addWidget(detail)

        self.progress = ProcessProgressBar()
        self.progress.setAccessibleName("Partition Atlas operation progress")
        self.progress.setToolTip(
            "Shows measured progress when real units are available; otherwise it remains "
            "animated without inventing a percentage."
        )
        body.addWidget(self.progress)
        root.addLayout(body, 1)

        footer = QFrame()
        footer.setObjectName("MissionFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 14, 24, 14)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        self.scan_button = QPushButton("Scan payload")
        self.scan_button.clicked.connect(self._scan)
        self.recommended_button = QPushButton("Select recommended")
        self.recommended_button.clicked.connect(self._select_recommended)
        self.expand_button = QPushButton("Expand filesystem")
        self.expand_button.setToolTip(
            "Expand the selected ext4, EROFS, or sparse partition into a contained browsable tree."
        )
        self.expand_button.clicked.connect(self._expand_filesystem)
        self.browse_button = QPushButton("Browse files")
        self.browse_button.clicked.connect(self._browse_files)
        self.extract_button = QPushButton("Extract selected")
        self.extract_button.setObjectName("MissionAction")
        self.extract_button.clicked.connect(self._extract)
        footer_layout.addWidget(self.close_button)
        footer_layout.addStretch()
        footer_layout.addWidget(self.scan_button)
        footer_layout.addWidget(self.recommended_button)
        footer_layout.addWidget(self.expand_button)
        footer_layout.addWidget(self.browse_button)
        footer_layout.addWidget(self.extract_button)
        root.addWidget(footer)

        studio.operation_started.connect(self._operation_started)
        studio.operation_progress.connect(self._operation_progress)
        studio.operation_completed.connect(self._operation_completed)
        studio.operation_failed.connect(self._operation_failed)
        self._refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        parent = self.parentWidget()
        if parent is not None:
            available = parent.window().geometry()
            self.resize(
                max(self.minimumWidth(), int(available.width() * 0.9)),
                max(self.minimumHeight(), int(available.height() * 0.9)),
            )
            frame = self.frameGeometry()
            frame.moveCenter(parent.window().frameGeometry().center())
            self.move(frame.topLeft())

    def _header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("MissionHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 18, 28, 18)
        heading = QVBoxLayout()
        eyebrow = QLabel("ROM STUDIO  /  PARTITION ATLAS")
        eyebrow.setObjectName("MissionEyebrow")
        title = QLabel("Map the architecture inside your OTA payload")
        title.setObjectName("MissionTitle")
        copy = QLabel(
            "Inspect, select, extract, classify, and hash partitions without connecting to or modifying the phone."
        )
        copy.setObjectName("MissionMuted")
        heading.addWidget(eyebrow)
        heading.addWidget(title)
        heading.addWidget(copy)
        layout.addLayout(heading, 1)
        badge = QLabel("◆  LOCAL EXTRACTION ONLY")
        badge.setObjectName("GuardianBadge")
        layout.addWidget(badge)
        return header

    @staticmethod
    def _stat_card(layout: QHBoxLayout, title: str, initial: str) -> QLabel:
        card = QFrame()
        card.setObjectName("MissionCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        heading = QLabel(title)
        heading.setObjectName("CardHeading")
        value = QLabel(initial)
        value.setObjectName("PartitionStat")
        card_layout.addWidget(heading)
        card_layout.addWidget(value)
        layout.addWidget(card, 1)
        return value

    def _refresh(self) -> None:
        self.manifest = self.service.load(self.project.project_id) if self.service else None
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        if self.manifest is not None:
            for partition in self.manifest.partitions:
                self._append_partition(partition)
        self.table.blockSignals(False)
        self._update_summary()

    def _append_partition(self, partition: PayloadPartition) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        name = QTableWidgetItem(partition.name)
        name.setData(Qt.ItemDataRole.UserRole, partition.name)
        name.setFlags(name.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        name.setCheckState(
            Qt.CheckState.Checked
            if partition.recommended and not partition.critical
            else Qt.CheckState.Unchecked
        )
        category = QTableWidgetItem(partition.category)
        size = QTableWidgetItem(human_bytes(partition.estimated_bytes))
        size.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        state = QTableWidgetItem(
            f"Extracted • {partition.image_format}" if partition.extracted_path else "Not extracted"
        )
        filesystem = (
            self.studio.filesystem_service.load(self.project.project_id, partition.name)
            if self.studio.filesystem_service is not None
            else None
        )
        if filesystem is not None:
            state.setText(f"Files browsable • {filesystem.file_count:,}")
        protection = QTableWidgetItem(
            "CRITICAL • excluded"
            if partition.critical
            else "Recommended"
            if partition.recommended
            else "Optional"
        )
        if partition.critical:
            protection.setForeground(QColor("#FF789A"))
            name.setForeground(QColor("#FF9BB2"))
        elif partition.extracted_path:
            state.setForeground(QColor("#5EEAAF"))
        for column, item in enumerate((name, category, size, state, protection)):
            if column:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, column, item)

    def _selected(self) -> tuple[str, ...]:
        return tuple(
            self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            for row in range(self.table.rowCount())
            if self.table.item(row, 0).checkState() is Qt.CheckState.Checked
        )

    def _select_recommended(self) -> None:
        if self.manifest is None:
            return
        by_name = {item.name: item for item in self.manifest.partitions}
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            partition = by_name[str(item.data(Qt.ItemDataRole.UserRole))]
            item.setCheckState(
                Qt.CheckState.Checked
                if partition.recommended and not partition.critical
                else Qt.CheckState.Unchecked
            )
        self.table.blockSignals(False)
        self._update_summary()

    def _selection_changed(self, _item: QTableWidgetItem) -> None:
        self._update_summary()

    def _update_summary(self) -> None:
        if self.manifest is None:
            self.partition_count.setText("Not scanned")
            self.selected_size.setText("—")
            self.extracted_count.setText("0")
            self.safety_state.setText("Waiting")
            self.scan_button.setEnabled(not self.busy and self.service is not None)
            self.recommended_button.setEnabled(False)
            self.extract_button.setEnabled(False)
            self.expand_button.setEnabled(False)
            self.browse_button.setEnabled(False)
            return
        selected = self._selected()
        selected_set = set(selected)
        selected_bytes = sum(
            item.estimated_bytes for item in self.manifest.partitions if item.name in selected_set
        )
        extracted = sum(bool(item.extracted_path) for item in self.manifest.partitions)
        self.partition_count.setText(str(len(self.manifest.partitions)))
        self.selected_size.setText(human_bytes(selected_bytes))
        self.extracted_count.setText(f"{extracted} / {len(self.manifest.partitions)}")
        try:
            plan = (
                self.service.plan_extraction(self.project.project_id, selected)
                if selected
                else None
            )
            self.safety_state.setText("SAFE" if plan and plan.safe else "Select partitions")
            self.safety_state.setObjectName(
                "PartitionStatSafe" if plan and plan.safe else "PartitionStat"
            )
            if plan is not None:
                self.detail.setText(plan.reason)
        except ProjectError as exc:
            plan = None
            self.safety_state.setText("BLOCKED")
            self.detail.setText(str(exc))
        self.safety_state.style().unpolish(self.safety_state)
        self.safety_state.style().polish(self.safety_state)
        self.scan_button.setEnabled(not self.busy)
        self.recommended_button.setEnabled(not self.busy)
        self.extract_button.setEnabled(bool(plan and plan.safe and not self.busy))
        self._update_filesystem_actions()

    def _show_partition_detail(self) -> None:
        if self.manifest is None:
            return
        row = self.table.currentRow()
        if row < 0:
            return
        name = str(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))
        partition = next(item for item in self.manifest.partitions if item.name == name)
        details = [
            f"{partition.name}  •  {partition.category}",
            f"Expected size  •  {human_bytes(partition.estimated_bytes)}",
            f"Protection  •  {'Critical firmware — excluded by default' if partition.critical else 'Working-tree eligible'}",
        ]
        if partition.extracted_path:
            details.extend(
                (
                    f"Image format  •  {partition.image_format}",
                    f"Actual size  •  {human_bytes(partition.actual_bytes)}",
                    f"SHA-256  •  {partition.sha256}",
                    f"Workspace  •  {partition.extracted_path}",
                )
            )
        filesystem = (
            self.studio.filesystem_service.load(self.project.project_id, partition.name)
            if self.studio.filesystem_service is not None
            else None
        )
        if filesystem is not None:
            details.extend(
                (
                    f"Browsable files  •  {filesystem.file_count:,}",
                    f"Browsable content  •  {human_bytes(filesystem.content_bytes)}",
                    f"Filesystem tree  •  {filesystem.tree_path}",
                )
            )
        self.detail.setText("\n".join(details))
        self._update_filesystem_actions()

    def _current_partition(self) -> PayloadPartition | None:
        if self.manifest is None or self.table.currentRow() < 0:
            return None
        name = str(self.table.item(self.table.currentRow(), 0).data(Qt.ItemDataRole.UserRole))
        return next((item for item in self.manifest.partitions if item.name == name), None)

    def _update_filesystem_actions(self) -> None:
        partition = self._current_partition()
        filesystem = None
        plan = None
        if partition is not None and self.studio.filesystem_service is not None:
            filesystem = self.studio.filesystem_service.load(
                self.project.project_id, partition.name
            )
            if partition.extracted_path and filesystem is None:
                try:
                    plan = self.studio.filesystem_service.plan(
                        self.project.project_id, partition.name
                    )
                except ProjectError:
                    plan = None
        self._filesystem_plan = plan
        missing_tools = bool(
            plan
            and not plan.safe
            and "unavailable" in plan.reason.casefold()
            and _filesystem_required_tools(plan.image_format)
        )
        self.expand_button.setEnabled(
            bool(plan and (plan.safe or missing_tools) and not self.busy and filesystem is None)
        )
        self.expand_button.setText(
            "Resolve filesystem tools" if missing_tools else "Expand filesystem"
        )
        self.expand_button.setToolTip(
            plan.reason
            if plan is not None
            else "Select an extracted ext4, EROFS, or sparse partition image."
        )
        self.browse_button.setEnabled(bool(filesystem is not None and not self.busy))

    def _expand_filesystem(self) -> None:
        partition = self._current_partition()
        if partition is None or self.studio.filesystem_service is None:
            return
        try:
            plan = self.studio.filesystem_service.plan(self.project.project_id, partition.name)
        except ProjectError as exc:
            QMessageBox.warning(self, "Filesystem unavailable", str(exc))
            return
        if not plan.safe and "unavailable" in plan.reason.casefold():
            required = _filesystem_required_tools(plan.image_format)
            if required and self.studio._resolve_required_tools(
                required,
                purpose=(
                    f"ROMVERSE identified {plan.image_format} for {partition.name}. "
                    "Only its required read-only filesystem tools are selected."
                ),
                title="ROMVERSE • Resolve filesystem tools",
                success_message=f"Read-only filesystem tools verified for {partition.name}.",
                parent=self,
            ):
                try:
                    plan = self.studio.filesystem_service.plan(
                        self.project.project_id, partition.name
                    )
                except ProjectError as exc:
                    QMessageBox.warning(self, "Filesystem unavailable", str(exc))
                    return
        if not plan.safe:
            QMessageBox.warning(self, "Filesystem expansion blocked", plan.reason)
            self._update_filesystem_actions()
            return
        self.studio._start_worker("expand-filesystem", partitions=(partition.name,))

    def _browse_files(self) -> None:
        partition = self._current_partition()
        if partition is None or self.studio.filesystem_service is None:
            return
        manifest = self.studio.filesystem_service.load(self.project.project_id, partition.name)
        if manifest is not None:
            PartitionFileExplorer(self.studio, manifest, self).exec()

    def _scan(self) -> None:
        if self.service is None:
            QMessageBox.warning(
                self,
                "Payload Dumper unavailable",
                "Install Payload Dumper through Forge Arsenal first.",
            )
            return
        self.studio._start_worker("scan-payload")

    def _extract(self) -> None:
        selected = self._selected()
        if not selected:
            return
        critical = tuple(
            item.name
            for item in self.manifest.partitions
            if item.name in selected and item.critical
        )
        if critical:
            answer = QMessageBox.question(
                self,
                "Extract critical firmware partitions?",
                "These boot-chain or radio partitions are excluded from modification by default:\n\n"
                + ", ".join(critical)
                + "\n\nExtraction is local and read-only, but Recipe targeting should remain locked. Continue?",
            )
            if answer is not QMessageBox.StandardButton.Yes:
                return
        self.studio._start_worker("extract-payload", partitions=selected)

    @Slot(str)
    def _operation_started(self, operation: str) -> None:
        if operation not in {"scan-payload", "extract-payload", "expand-filesystem"}:
            return
        self.busy = True
        self.progress.begin(determinate=False)
        self.detail.setText(
            "Expanding the selected filesystem into a contained browsable tree…"
            if operation == "expand-filesystem"
            else "Payload Dumper is extracting without a trustworthy percentage. Measured output-byte verification will appear when images exist…"
            if operation == "extract-payload"
            else "Verifying payload.bin and reading its partition manifest. The external partition scan has no trustworthy percentage…"
        )
        self._update_summary()

    @Slot(str, int)
    def _operation_progress(self, operation: str, value: int) -> None:
        if operation not in {"scan-payload", "extract-payload", "expand-filesystem"}:
            return
        self.progress.report(value)

    @Slot(str, object)
    def _operation_completed(self, operation: str, _result: object) -> None:
        if operation not in {"scan-payload", "extract-payload", "expand-filesystem"}:
            return
        self.busy = False
        self.progress.finish()
        self._refresh()

    @Slot(str, str)
    def _operation_failed(self, operation: str, message: str) -> None:
        if operation not in {"scan-payload", "extract-payload", "expand-filesystem"}:
            return
        self.busy = False
        self.progress.stop()
        self.detail.setText("ROMVERSE stopped safely: " + message)
        self._update_summary()

    @staticmethod
    def _extra_stylesheet() -> str:
        return """
            QLabel#PartitionStat { color: #EEF4FF; font-size: 21px; font-weight: 800; }
            QLabel#PartitionStatSafe { color: #55EAAF; font-size: 21px; font-weight: 800; }
            QTableWidget#PartitionTable {
                color: #DCE8FA; background: #040912; alternate-background-color: #07101B;
                gridline-color: #172841; border: 1px solid #243653; border-radius: 10px;
            }
            QTableWidget#PartitionTable::item { padding: 7px; }
            QTableWidget#PartitionTable::item:selected { background: #263264; color: #FFFFFF; }
            QHeaderView::section {
                color: #52DDF0; background: #080F1B; border: 0; border-bottom: 1px solid #263A59;
                padding: 9px; font-weight: 800;
            }
            QTreeView#TargetTree {
                color: #DCE8FA; background: #040912; alternate-background-color: #07101B;
                border: 1px solid #243653; border-radius: 10px; padding: 7px;
            }
            QTreeView#TargetTree::item { min-height: 28px; }
            QTreeView#TargetTree::item:selected { background: #263264; color: #FFFFFF; }
        """


class PartitionFileExplorer(QDialog):
    def __init__(
        self,
        studio,
        manifest: FilesystemManifest,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent or studio)
        self.studio = studio
        self.manifest = manifest
        self.tree_root = (studio.store.workspace / manifest.tree_path).resolve()
        self.selected_target = ""
        self.setWindowTitle(f"ROMVERSE • {manifest.partition} File Explorer")
        self.setMinimumSize(900, 650)
        self.resize(1080, 760)
        self.setStyleSheet(
            GuidedBuildMission._stylesheet() + PartitionWorkspace._extra_stylesheet()
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QFrame()
        header.setObjectName("MissionHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(28, 18, 28, 18)
        heading = QVBoxLayout()
        eyebrow = QLabel(f"PARTITION ATLAS  /  {manifest.partition.upper()} FILES")
        eyebrow.setObjectName("MissionEyebrow")
        title = QLabel("Explore the extracted Android filesystem")
        title.setObjectName("MissionTitle")
        copy = QLabel(
            f"{manifest.file_count:,} files  •  {human_bytes(manifest.content_bytes)}  •  read-only browsing"
        )
        copy.setObjectName("MissionMuted")
        heading.addWidget(eyebrow)
        heading.addWidget(title)
        heading.addWidget(copy)
        header_layout.addLayout(heading, 1)
        badge = QLabel("◆  CONTAINED TREE")
        badge.setObjectName("GuardianBadge")
        header_layout.addWidget(badge)
        root.addWidget(header)

        body = QVBoxLayout()
        body.setContentsMargins(28, 20, 28, 18)
        self.model = QFileSystemModel(self)
        self.model.setFilter(self.model.filter() | QDir.Filter.Hidden | QDir.Filter.NoDotAndDotDot)
        self.model.setRootPath(str(self.tree_root))
        self.tree = QTreeView()
        self.tree.setObjectName("TargetTree")
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(str(self.tree_root)))
        self.tree.setHeaderHidden(True)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        for column in (1, 2, 3):
            self.tree.hideColumn(column)
        self.tree.clicked.connect(self._selected)
        body.addWidget(self.tree, 1)
        card = QFrame()
        card.setObjectName("MissionCard")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(18, 13, 18, 13)
        label = QLabel("SELECTED TARGET")
        label.setObjectName("CardHeading")
        self.selection = QLabel("Choose a file or directory to send into Recipe Forge.")
        self.selection.setObjectName("CardBody")
        self.selection.setWordWrap(True)
        card_layout.addWidget(label)
        card_layout.addWidget(self.selection, 1)
        body.addWidget(card)
        root.addLayout(body, 1)

        footer = QFrame()
        footer.setObjectName("MissionFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 14, 24, 14)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        self.recipe_button = QPushButton("Open target in Recipe Forge")
        self.recipe_button.setObjectName("MissionAction")
        self.recipe_button.setEnabled(False)
        self.recipe_button.clicked.connect(self._open_recipe)
        footer_layout.addWidget(close)
        footer_layout.addStretch()
        footer_layout.addWidget(self.recipe_button)
        root.addWidget(footer)

    def _selected(self, index: QModelIndex) -> None:
        path = Path(self.model.filePath(index)).resolve(strict=False)
        project_tree = (
            self.studio.store.working_root / self.manifest.project_id / "tree"
        ).resolve()
        if (
            path == self.tree_root
            or not path.is_relative_to(self.tree_root)
            or not path.is_relative_to(project_tree)
            or path.is_symlink()
        ):
            self.selected_target = ""
            self.selection.setText(
                "Symbolic links and the filesystem root cannot be direct Recipe targets."
            )
        else:
            self.selected_target = path.relative_to(project_tree).as_posix()
            self.selection.setText(self.selected_target)
        self.recipe_button.setEnabled(bool(self.selected_target))

    def _open_recipe(self) -> None:
        if not self.selected_target:
            return
        from romverse.ui.guided_recipe import RecipeForgeSequence

        RecipeForgeSequence(
            self.studio,
            self,
            initial_target=self.selected_target,
        ).exec()


def _filesystem_required_tools(image_format: str) -> tuple[str, ...]:
    if image_format == "Android sparse image":
        # The normalized image reveals ext4 versus EROFS only after simg2img runs.
        return ("simg2img", "EXT4 Browser", "EROFS Verifier", "Fakeroot")
    if image_format == "ext4 filesystem":
        return ("EXT4 Browser",)
    if image_format == "EROFS filesystem":
        return ("EROFS Verifier", "Fakeroot")
    return ()
