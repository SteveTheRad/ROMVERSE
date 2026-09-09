from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from romverse import DISPLAY_VERSION
from romverse.core.settings import ExperienceMode
from romverse.infrastructure.tools import ToolStatus


class SetupWizard(QDialog):
    def __init__(self, logo_path: Path, workspace: Path, tools: tuple[ToolStatus, ...]) -> None:
        super().__init__()
        self.setWindowTitle("Welcome to ROMVERSE")
        self.setMinimumSize(700, 610)
        self.setModal(True)
        self.selected_workspace = workspace
        self.selected_experience_mode = ExperienceMode.GUIDED

        root = QVBoxLayout(self)
        root.setContentsMargins(44, 38, 44, 38)
        root.setSpacing(18)

        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setPixmap(
            QPixmap(str(logo_path)).scaled(
                104,
                104,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        root.addWidget(logo)
        brand = QLabel("ROMVERSE")
        brand.setObjectName("Brand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(brand)
        build_identity = QLabel(f"{DISPLAY_VERSION}  •  INTERNAL DEVELOPMENT")
        build_identity.setObjectName("Warning")
        build_identity.setAccessibleName(f"ROMVERSE {DISPLAY_VERSION} internal development build")
        build_identity.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(build_identity)
        tagline = QLabel("BUILD. OPTIMIZE. PERFECT.")
        tagline.setObjectName("Eyebrow")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(tagline)

        intro = QLabel(
            "Continue in Guided Mode for ROMVERSE's clear, evidence-bound workflow. No phone is "
            "required during setup, and this screen cannot scan, flash, unlock, reboot, install, "
            "delete, or modify a phone. Command Deck will truthfully show whether Android Platform "
            "Tools or a connected device still need attention."
        )
        intro.setWordWrap(True)
        intro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(intro)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        title = QLabel("Tool verification")
        title.setObjectName("SectionTitle")
        card_layout.addWidget(title)
        for status in tools:
            row = QHBoxLayout()
            row.addWidget(QLabel(status.name))
            row.addStretch()
            value = QLabel(
                f"✓ {status.version or status.detail}" if status.available else f"! {status.detail}"
            )
            value.setObjectName("Good" if status.available else "Warning")
            row.addWidget(value)
            card_layout.addLayout(row)
        root.addWidget(card)

        workspace_label = QLabel("Workspace")
        workspace_label.setObjectName("SectionTitle")
        root.addWidget(workspace_label)
        workspace_row = QHBoxLayout()
        self.workspace_edit = QLineEdit(str(workspace))
        self.workspace_edit.setAccessibleName("ROMVERSE workspace path")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        workspace_row.addWidget(self.workspace_edit, 1)
        workspace_row.addWidget(browse)
        root.addLayout(workspace_row)
        hint = QLabel(
            "Folders are created only inside this location. Existing files are preserved."
        )
        hint.setObjectName("Muted")
        root.addWidget(hint)

        root.addStretch()
        credit = QLabel("Created by SteveTheRad  •  A RadForge Labs Project")
        credit.setObjectName("Muted")
        credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(credit)
        start = QPushButton("Continue in Guided Mode")
        start.setObjectName("Primary")
        start.setAccessibleName("Choose Guided Mode and open Command Deck")
        start.clicked.connect(self._accept)
        root.addWidget(start)

    def _browse(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Choose ROMVERSE workspace", self.workspace_edit.text()
        )
        if selected:
            self.workspace_edit.setText(selected)

    def _accept(self) -> None:
        path = Path(self.workspace_edit.text()).expanduser()
        if not str(path).strip():
            return
        self.selected_workspace = path
        self.accept()
