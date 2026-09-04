from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from romverse.rom.models import ProjectError
from romverse.rom.release_forge import (
    ReleaseForgeAssessment,
    ReleaseForgePlan,
    ReleaseForgeService,
    ReleaseGateState,
    ReleasePackageKind,
    ReleaseTier,
)
from romverse.ui.background import ManagedRunnable, start_background
from romverse.ui.formatters import human_bytes


class ReleaseForgeSignals(QObject):
    complete = Signal(object)
    failed = Signal(str)


class ReleaseForgeWorker(ManagedRunnable):
    def __init__(self, operation) -> None:
        super().__init__()
        self.operation = operation
        self.signals = ReleaseForgeSignals()

    @Slot()
    def execute(self) -> None:
        try:
            result = self.operation()
            with suppress(RuntimeError):
                self.signals.complete.emit(result)
        except (OSError, ProjectError, TypeError, ValueError) as exc:
            with suppress(RuntimeError):
                self.signals.failed.emit(str(exc))


class CosmicAssemblyForge(QWidget):
    """Small motion-safe visual showing evidence converging into a release capsule."""

    def __init__(self, parent=None, *, reduced_motion: bool = False) -> None:
        super().__init__(parent)
        self.phase = 0
        self.sealed = False
        self.setMinimumHeight(214)
        self.setAccessibleName("Cosmic assembly forge visualisation")
        self.timer = QTimer(self)
        self.timer.setInterval(70)
        self.timer.timeout.connect(self._advance)
        if not reduced_motion:
            self.timer.start()

    def set_sealed(self, sealed: bool) -> None:
        self.sealed = sealed
        self.update()

    def _advance(self) -> None:
        self.phase = (self.phase + 1) % 180
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width()
        height = self.height()
        background = QLinearGradient(0, 0, width, height)
        background.setColorAt(0, QColor("#071426"))
        background.setColorAt(0.55, QColor("#090D1B"))
        background.setColorAt(1, QColor("#1A092A"))
        painter.fillRect(self.rect(), background)
        center_x = width * 0.72
        center_y = height * 0.5
        for index, label in enumerate(("SOURCE", "BUILD", "AVB", "SIM", "RECOVERY")):
            y = 28 + index * 34
            travel = 0 if self.sealed else ((self.phase + index * 27) % 90) / 90
            x = 28 + max(0, center_x - 225) * travel
            color = QColor("#59E7F3") if index % 2 == 0 else QColor("#A96BFF")
            painter.setPen(QPen(color, 1.5))
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 42))
            painter.drawRoundedRect(QRectF(x, y, 92, 22), 7, 7)
            painter.setPen(QColor("#EAF7FF"))
            painter.drawText(QRectF(x, y, 92, 22), Qt.AlignmentFlag.AlignCenter, label)
        glow = QColor("#5DECB2" if self.sealed else "#9F68F3")
        painter.setPen(QPen(QColor(glow.red(), glow.green(), glow.blue(), 64), 14))
        painter.setBrush(QColor("#091725"))
        capsule = QRectF(center_x - 64, center_y - 62, 128, 124)
        painter.drawRoundedRect(capsule, 28, 28)
        painter.setPen(QPen(glow, 2.5))
        painter.drawRoundedRect(capsule, 28, 28)
        painter.drawLine(capsule.left() + 16, center_y, capsule.right() - 16, center_y)
        painter.setPen(QColor("#F4FAFF"))
        painter.drawText(
            capsule.adjusted(8, 10, -8, -10),
            Qt.AlignmentFlag.AlignCenter,
            "SEALED\nCAPSULE" if self.sealed else "RELEASE\nFORGE",
        )
        painter.setPen(QColor("#7F94AF"))
        painter.drawText(
            QRectF(22, height - 29, width - 44, 18),
            Qt.AlignmentFlag.AlignLeft,
            "EVIDENCE IN  •  VERIFIED CAPSULE OUT  •  PUBLISHING AUTHORITY: NONE",
        )


class ReleaseForgeDialog(QDialog):
    def __init__(
        self,
        service: ReleaseForgeService,
        project_id: str,
        parent=None,
        *,
        reduced_motion: bool = False,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.project_id = project_id
        self.worker: ReleaseForgeWorker | None = None
        self.plan: ReleaseForgePlan | None = service.load_plan(project_id)
        self.bundle = service.load_bundle_receipt(project_id)
        self.assessment: ReleaseForgeAssessment | None = None
        self.reduced_motion = reduced_motion
        self.setWindowTitle("ROMVERSE • Release Forge")
        self.setMinimumSize(1080, 720)
        self.resize(1360, 900)
        self.setStyleSheet(self.stylesheet())
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._header())
        scroll = QScrollArea()
        scroll.setObjectName("ReleaseScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        content = QVBoxLayout(host)
        content.setContentsMargins(28, 22, 28, 22)
        content.setSpacing(15)
        content.addWidget(self._configuration())
        self.gates_layout = QVBoxLayout()
        content.addWidget(self._section("RELEASE EVIDENCE GATES", self.gates_layout))
        self.artifacts_layout = QVBoxLayout()
        content.addWidget(self._section("CAPSULE CONTENT", self.artifacts_layout))
        content.addStretch(1)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)
        root.addWidget(self._footer())
        self._refresh()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        parent = self.parentWidget()
        if parent is not None:
            available = parent.window().geometry()
            self.resize(
                max(self.minimumWidth(), int(available.width() * 0.94)),
                max(self.minimumHeight(), int(available.height() * 0.94)),
            )
            frame = self.frameGeometry()
            frame.moveCenter(parent.window().frameGeometry().center())
            self.move(frame.topLeft())

    def _header(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("ReleaseHeader")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(30, 21, 30, 21)
        copy = QVBoxLayout()
        eyebrow = QLabel("RELEASE FORGE  •  BUILD / SIGN / PACKAGE")
        eyebrow.setObjectName("ReleaseEyebrow")
        title = QLabel("Turn proven build evidence into a sealed release capsule")
        title.setObjectName("ReleaseTitle")
        subtitle = QLabel(
            "Deterministic artifacts • offline key custody • AVB evidence • checksums • no automatic publishing"
        )
        subtitle.setObjectName("ReleaseCopy")
        subtitle.setWordWrap(True)
        copy.addWidget(eyebrow)
        copy.addWidget(title)
        copy.addWidget(subtitle)
        layout.addLayout(copy, 1)
        self.readiness_badge = QLabel("ASSESSING")
        self.readiness_badge.setObjectName("ReleaseBadge")
        layout.addWidget(self.readiness_badge, 0, Qt.AlignmentFlag.AlignTop)
        return frame

    def _configuration(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("ReleasePanel")
        layout = QGridLayout(frame)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(15)
        self.forge = CosmicAssemblyForge(self, reduced_motion=self.reduced_motion)
        layout.addWidget(self.forge, 0, 0, 4, 1)
        version_label = QLabel("RELEASE VERSION")
        version_label.setObjectName("ReleaseEyebrow")
        self.version = QLineEdit(self.plan.version if self.plan else "1.0.0-dev.1")
        self.version.setAccessibleName("Release version")
        self.version.textChanged.connect(self._update_plan_actions)
        layout.addWidget(version_label, 0, 1)
        layout.addWidget(self.version, 1, 1)
        type_label = QLabel("RELEASE CLASS")
        type_label.setObjectName("ReleaseEyebrow")
        selectors = QHBoxLayout()
        self.tier = QComboBox()
        self.tier.setAccessibleName("Release tier")
        for item in ReleaseTier:
            self.tier.addItem(item.value.title(), item)
        self.kind = QComboBox()
        self.kind.setAccessibleName("Package type")
        for item in ReleasePackageKind:
            self.kind.addItem(item.value.title(), item)
        if self.plan is not None:
            self.tier.setCurrentIndex(list(ReleaseTier).index(self.plan.tier))
            self.kind.setCurrentIndex(list(ReleasePackageKind).index(self.plan.package_kind))
        self.tier.currentIndexChanged.connect(self._refresh)
        self.kind.currentIndexChanged.connect(self._refresh)
        selectors.addWidget(self.tier)
        selectors.addWidget(self.kind)
        layout.addWidget(type_label, 0, 2)
        layout.addLayout(selectors, 1, 2)
        changelog_label = QLabel("CHANGELOG  •  ONE ITEM PER LINE")
        changelog_label.setObjectName("ReleaseEyebrow")
        self.changelog = QTextEdit()
        self.changelog.setAccessibleName("Release changelog")
        self.changelog.setPlaceholderText("Describe verified changes…")
        self.changelog.setPlainText(
            "\n".join(self.plan.changelog) if self.plan else "Verified ROMVERSE build candidate"
        )
        self.changelog.setMaximumHeight(105)
        self.changelog.textChanged.connect(self._update_plan_actions)
        layout.addWidget(changelog_label, 2, 1, 1, 2)
        layout.addWidget(self.changelog, 3, 1, 1, 2)
        layout.setColumnStretch(0, 3)
        layout.setColumnStretch(1, 2)
        layout.setColumnStretch(2, 2)
        return frame

    @staticmethod
    def _section(title: str, body: QVBoxLayout) -> QWidget:
        frame = QFrame()
        frame.setObjectName("ReleasePanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 15, 18, 15)
        heading = QLabel(title)
        heading.setObjectName("ReleaseEyebrow")
        layout.addWidget(heading)
        layout.addLayout(body)
        return frame

    def _footer(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("ReleaseFooter")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(22, 12, 22, 13)
        self.status = QLabel(
            "Release Forge packages local evidence only. It cannot publish or issue phone commands."
        )
        self.status.setObjectName("ReleaseCopy")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh evidence")
        self.refresh_button.clicked.connect(self._refresh)
        self.assembly_button = QPushButton("Build signed final assembly")
        self.assembly_button.clicked.connect(self._assemble)
        self.plan_button = QPushButton("Prepare release plan")
        self.plan_button.clicked.connect(self._prepare)
        self.request_button = QPushButton("Export certificate request")
        self.request_button.clicked.connect(self._export_request)
        self.import_button = QPushButton("Import signed certificate")
        self.import_button.clicked.connect(self._import_certificate)
        self.bundle_button = QPushButton("Seal release capsule")
        self.bundle_button.setObjectName("ReleasePrimary")
        self.bundle_button.clicked.connect(self._bundle)
        self.export_button = QPushButton("Export verified capsule")
        self.export_button.clicked.connect(self._export_bundle)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        for button in (
            self.refresh_button,
            self.assembly_button,
            self.plan_button,
            self.request_button,
            self.import_button,
            self.bundle_button,
            self.export_button,
        ):
            actions.addWidget(button)
        actions.addStretch(1)
        actions.addWidget(close)
        layout.addLayout(actions)
        return frame

    def _refresh(self, *_args) -> None:
        if self.worker is not None:
            return
        try:
            self.plan = self.service.load_plan(self.project_id)
            self.bundle = self.service.load_bundle_receipt(self.project_id)
            self.assessment = self.service.assess(
                self.project_id,
                self._tier(),
                self._kind(),
                base_plan=self.plan if self._kind() is ReleasePackageKind.INCREMENTAL else None,
            )
        except ProjectError as exc:
            self.status.setText(str(exc))
            return
        self._render()

    def _render(self) -> None:
        if self.assessment is None:
            return
        self._clear(self.gates_layout)
        blockers = 0
        attention = 0
        for gate in self.assessment.gates:
            blockers += gate.state is ReleaseGateState.BLOCKED
            attention += gate.state is ReleaseGateState.ATTENTION
            self.gates_layout.addWidget(self._gate_card(gate))
        self._clear(self.artifacts_layout)
        if self.plan is not None:
            for artifact in self.plan.artifacts:
                label = QLabel(
                    f"{'✓ SIGNED' if artifact.signed else '◇ DEVELOPMENT'}  •  {artifact.name}  •  "
                    f"{human_bytes(artifact.size_bytes)}  •  {artifact.sha256[:20]}…"
                )
                label.setObjectName("ReleaseArtifact")
                self.artifacts_layout.addWidget(label)
        else:
            label = QLabel(
                "Prepare a release plan to freeze exact artifact hashes and capsule contents."
            )
            label.setObjectName("ReleaseCopy")
            self.artifacts_layout.addWidget(label)
        ready = blockers == 0
        self.readiness_badge.setText("READY TO PLAN" if ready else f"{blockers} BLOCKER(S)")
        self.readiness_badge.setProperty("state", "pass" if ready else "blocked")
        self.readiness_badge.style().unpolish(self.readiness_badge)
        self.readiness_badge.style().polish(self.readiness_badge)
        self.plan_button.setEnabled(ready)
        signing = next(
            (gate for gate in self.assessment.gates if gate.gate_id == "signing"),
            None,
        )
        assembly = next(
            (gate for gate in self.assessment.gates if gate.gate_id == "signed-assembly"),
            None,
        )
        self.assembly_button.setEnabled(
            signing is not None
            and signing.state is ReleaseGateState.PASS
            and assembly is not None
            and assembly.state is not ReleaseGateState.PASS
        )
        self._update_plan_actions()
        self.status.setText(
            f"{len(self.assessment.gates) - blockers - attention} verified  •  "
            f"{attention} attention  •  {blockers} blocked  •  PHONE CHANGED: NO  •  "
            "PUBLISHING AUTHORITY: NONE"
        )

    def _update_plan_actions(self, *_args) -> None:
        plan_matches = self._plan_matches_form()
        self.request_button.setEnabled(plan_matches)
        self.import_button.setEnabled(plan_matches)
        certificate_ready = bool(
            plan_matches
            and self.plan is not None
            and (
                not self.plan.public_certificate_required
                or self.service.load_certificate_signature(self.plan) is not None
            )
        )
        self.bundle_button.setEnabled(certificate_ready)
        bundle_ready = bool(
            self.bundle is not None
            and self.service.verify_bundle(self.bundle) is None
            and self.plan is not None
            and self.bundle.plan_digest == self.plan.plan_digest
        )
        self.export_button.setEnabled(bundle_ready)
        self.forge.set_sealed(bundle_ready)

    def _plan_matches_form(self) -> bool:
        if self.plan is None:
            return False
        entries = tuple(
            line.strip() for line in self.changelog.toPlainText().splitlines() if line.strip()
        )
        return bool(
            self.plan.version == self.version.text().strip()
            and self.plan.tier is self._tier()
            and self.plan.package_kind is self._kind()
            and self.plan.changelog == entries
        )

    @staticmethod
    def _gate_card(gate) -> QWidget:
        card = QFrame()
        card.setObjectName("ReleaseGate")
        card.setProperty("state", gate.state.value)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(13, 10, 13, 10)
        symbol = QLabel(
            "✓"
            if gate.state is ReleaseGateState.PASS
            else "!"
            if gate.state is ReleaseGateState.ATTENTION
            else "×"
        )
        symbol.setObjectName("ReleaseSymbol")
        layout.addWidget(symbol)
        copy = QVBoxLayout()
        title = QLabel(gate.label)
        title.setObjectName("ReleaseGateTitle")
        detail = QLabel(f"{gate.evidence}  •  Next: {gate.resolution}")
        detail.setObjectName("ReleaseCopy")
        detail.setWordWrap(True)
        copy.addWidget(title)
        copy.addWidget(detail)
        layout.addLayout(copy, 1)
        badge = QLabel(gate.state.value.upper())
        badge.setObjectName("ReleaseGateBadge")
        layout.addWidget(badge)
        return card

    @staticmethod
    def _clear(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if widget := item.widget():
                widget.deleteLater()

    def _tier(self) -> ReleaseTier:
        return ReleaseTier(self.tier.currentData())

    def _kind(self) -> ReleasePackageKind:
        return ReleasePackageKind(self.kind.currentData())

    def _prepare(self) -> None:
        entries = tuple(
            line.strip() for line in self.changelog.toPlainText().splitlines() if line.strip()
        )
        base = self.plan if self._kind() is ReleasePackageKind.INCREMENTAL else None
        self._run(
            "Freezing exact release inputs…",
            lambda: self.service.prepare_plan(
                self.project_id,
                self.version.text().strip(),
                self._tier(),
                self._kind(),
                entries,
                base_plan=base,
            ),
            "Release plan sealed from current evidence.",
        )

    def _assemble(self) -> None:
        self._run(
            "Rebuilding and unpacking the signed final super container…",
            lambda: self.service.assemble_signed_super(self.project_id),
            "Signed final assembly verified byte-for-byte.",
        )

    def _bundle(self) -> None:
        if self.plan is None:
            return
        self._run(
            "Writing deterministic capsule and re-verifying every member…",
            lambda: self.service.create_bundle(self.plan),
            "Release capsule sealed and independently re-verified.",
        )

    def _run(self, progress: str, operation, success: str) -> None:
        if self.worker is not None:
            return
        self.status.setText(progress + "  •  no phone commands")
        self._set_buttons(False)
        worker = ReleaseForgeWorker(operation)
        self.worker = worker
        worker.signals.complete.connect(lambda result: self._completed(result, success))
        worker.signals.failed.connect(self._failed)
        start_background(worker)

    @Slot(object)
    def _completed(self, _result, message: str) -> None:
        self.worker = None
        self._set_buttons(True)
        self._refresh()
        self.status.setText(message + "  •  PHONE CHANGED: NO")

    @Slot(str)
    def _failed(self, message: str) -> None:
        self.worker = None
        self._set_buttons(True)
        self.status.setText(message)
        QMessageBox.warning(self, "Release Forge paused", message)

    def _set_buttons(self, enabled: bool) -> None:
        for button in (
            self.refresh_button,
            self.assembly_button,
            self.plan_button,
            self.request_button,
            self.import_button,
            self.bundle_button,
            self.export_button,
        ):
            button.setEnabled(enabled)

    def _export_request(self) -> None:
        if self.plan is None:
            return
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Export release certificate request",
            str(Path.home() / self.service.CERTIFICATE_REQUEST_NAME),
            "JSON files (*.json)",
        )
        if target:
            try:
                path = self.service.export_certificate_request(self.plan, Path(target))
                self.status.setText(f"Certificate request exported to {path}")
            except ProjectError as exc:
                self._failed(str(exc))

    def _import_certificate(self) -> None:
        if self.plan is None:
            return
        envelope, _ = QFileDialog.getOpenFileName(
            self,
            "Choose signed certificate envelope",
            str(Path.home()),
            "JSON files (*.json)",
        )
        if not envelope:
            return
        public_key, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Ed25519 public key",
            str(Path.home()),
            "PEM public keys (*.pem);;All files (*)",
        )
        if not public_key:
            return
        key_id, accepted = QInputDialog.getText(
            self,
            "Release certificate identity",
            "Key ID shown by the external signer:",
        )
        if not accepted:
            return
        try:
            receipt = self.service.import_certificate_signature(
                self.plan,
                Path(envelope),
                Path(public_key),
                key_id,
            )
            self.status.setText(
                f"External certificate verified  •  key {receipt.key_id}  •  private key stored: NO"
            )
            self._update_plan_actions()
        except ProjectError as exc:
            self._failed(str(exc))

    def _export_bundle(self) -> None:
        if self.bundle is None:
            return
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose external release export folder",
            str(Path.home()),
        )
        if folder:
            try:
                output = self.service.export_bundle(self.bundle, Path(folder))
                self.status.setText(f"Verified release capsule exported to {output}")
            except ProjectError as exc:
                self._failed(str(exc))

    def reject(self) -> None:
        if self.worker is not None:
            self.status.setText("Release Forge is finishing the local evidence operation.")
            return
        super().reject()

    @staticmethod
    def stylesheet() -> str:
        return """
            QDialog, QWidget { background: #02050A; color: #EDF7FF; }
            QLabel { background: transparent; }
            QScrollArea#ReleaseScroll { border: none; background: #02050A; }
            QFrame#ReleaseHeader {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #08182A, stop:.52 #07101D, stop:1 #1A0B2A);
                border-bottom: 1px solid #294C6F;
            }
            QFrame#ReleaseFooter { background: #050B14; border-top: 1px solid #203A58; }
            QFrame#ReleasePanel {
                background: #050B14; border: 1px solid #203B58; border-radius: 13px;
            }
            QLabel#ReleaseEyebrow {
                color: #57E2EF; font-size: 10px; font-weight: 900; letter-spacing: 1.3px;
            }
            QLabel#ReleaseTitle { color: #FFFFFF; font-size: 24px; font-weight: 900; }
            QLabel#ReleaseCopy { color: #9FB0C7; font-size: 11px; }
            QLabel#ReleaseBadge {
                color: #FF809A; background: #260B15; border: 1px solid #8B3147;
                border-radius: 11px; padding: 9px 13px; font-weight: 900;
            }
            QLabel#ReleaseBadge[state="pass"] {
                color: #5DECB2; background: #061C15; border-color: #1A7655;
            }
            QFrame#ReleaseGate {
                background: #07101A; border: 1px solid #28405E; border-radius: 9px;
            }
            QFrame#ReleaseGate[state="pass"] { border-left: 3px solid #3BDB9B; }
            QFrame#ReleaseGate[state="attention"] { border-left: 3px solid #F5BA50; }
            QFrame#ReleaseGate[state="blocked"] { border-left: 3px solid #F35E7D; }
            QLabel#ReleaseSymbol { color: #67E8B5; font-size: 18px; font-weight: 900; }
            QFrame#ReleaseGate[state="attention"] QLabel#ReleaseSymbol { color: #F7C76C; }
            QFrame#ReleaseGate[state="blocked"] QLabel#ReleaseSymbol { color: #FF7A96; }
            QLabel#ReleaseGateTitle { color: #F1F7FF; font-size: 12px; font-weight: 850; }
            QLabel#ReleaseGateBadge {
                color: #A8BDD7; font-size: 9px; font-weight: 900; letter-spacing: 1px;
            }
            QLabel#ReleaseArtifact {
                color: #CDE3F7; background: #07111E; border: 1px solid #203B58;
                border-radius: 8px; padding: 10px; font-size: 11px; font-weight: 700;
            }
            QLineEdit, QComboBox, QTextEdit {
                color: #F3F8FF; background: #07101D; border: 1px solid #365677;
                border-radius: 8px; padding: 9px; selection-background-color: #7041B5;
            }
            QPushButton {
                color: #DBE9F8; background: #0A1421; border: 1px solid #355779;
                border-radius: 8px; padding: 9px 12px; font-weight: 750;
            }
            QPushButton:hover { color: white; border-color: #59DFED; background: #102238; }
            QPushButton:disabled { color: #536275; border-color: #273547; background: #070C13; }
            QPushButton#ReleasePrimary {
                color: #06150F; background: #44DDA4; border-color: #7BF1C4;
            }
        """
