from __future__ import annotations

import hashlib
import json
import math
import random
import time
from contextlib import suppress
from dataclasses import dataclass, replace
from html import escape
from importlib.resources import as_file, files
from pathlib import Path
from threading import Event

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QObject,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QFont,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
    QShortcut,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from romverse import DISPLAY_VERSION
from romverse.ascension.companion import AscensionCompanionStatusService
from romverse.ascension.releases import OfficialRootReleaseService
from romverse.backup.media import PhoneMediaBackupService
from romverse.companion.raw_terminal import RawTerminalFeed
from romverse.companion.usb_assist import UsbPairingAssistService
from romverse.core.activity import (
    ActivityStore,
    ActivityStoreError,
    validate_activity_context,
)
from romverse.core.privacy import WorkspacePrivacy
from romverse.core.settings import AppSettings, DesktopTheme, ExperienceMode
from romverse.device.adb import AdbClient
from romverse.device.apk_install import ApkInstallService
from romverse.device.catalog import (
    DeviceCatalogCancelled,
    DeviceCatalogError,
    DeviceCatalogUpdate,
    GooglePlayDeviceCatalog,
)
from romverse.device.dna import CapabilityState, DeviceDnaProfile
from romverse.device.engine import DeviceEngine
from romverse.device.fastboot import FastbootClient
from romverse.device.identity import DeviceIdentityResolver
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.attestations import DevicePackAttestationStore
from romverse.device_packs.registry import DevicePackRegistry
from romverse.device_packs.validation import DevicePackValidationReport, ValidationState
from romverse.diagnostics.analyzer import DiagnosticAnalyzer
from romverse.diagnostics.history import DiagnosticHistoryStore
from romverse.diagnostics.models import DiagnosticReport
from romverse.galaxy.network import (
    GalaxyNetworkError,
    GalaxyServiceTrust,
    load_galaxy_service_trust,
)
from romverse.guardian.approval import ApprovalStore
from romverse.guardian.audit import GuardianAuditStore
from romverse.guardian.gateway import ExecutionGateway
from romverse.guardian.manifest_review import (
    GuardianManifestReview,
    GuardianManifestReviewService,
)
from romverse.guardian.planning import GuardianPreflight
from romverse.guardian.policy import GuardianPolicy
from romverse.guardian.recovery_live_target import GuardianRecoveryLiveTargetReceiptService
from romverse.guardian.recovery_preparation import (
    GuardianRecoveryPreparationError,
    GuardianRecoveryPreparationService,
)
from romverse.infrastructure.process import CommandRunner, SubprocessRunner
from romverse.infrastructure.provisioning import required_tools_for_source
from romverse.infrastructure.tools import ToolStatus
from romverse.intelligence.online_remediation import OnlineRemediationService
from romverse.intelligence.synapse import SynapseStore
from romverse.knowledge.advisor import article_for_key
from romverse.knowledge.archives import catalog_metrics
from romverse.knowledge.lookup import OfflineKnowledgeService
from romverse.knowledge.models import KnowledgeFailure, KnowledgeLookupReport
from romverse.knowledge.resolution_memory import ArchivesResolutionMemory
from romverse.knowledge.updates import KnowledgeUpdateService
from romverse.legal import load_privacy_document, load_terms_document
from romverse.nexus.compatibility import CompatibilityMatrix, CompatibilityStatus
from romverse.nexus.events import (
    LiveConsoleEventStore,
    LiveConsoleStoreError,
    MissionConfidence,
    MissionState,
)
from romverse.nexus.planning import NexusPlan, NexusPlanStatus
from romverse.platform.host import HostPlatform, current_host
from romverse.repair.autopilot import RecoveryAutopilotError, RecoveryRouteKind, RecoveryTrigger
from romverse.repair.host import AdbHostRepairReceiptStore, AdbHostRepairService
from romverse.repair.sessions import RepairSessionStore
from romverse.repair.templates import RepairAssessmentTemplates, actionable_repair_finding
from romverse.rom.boot_observation import (
    BootFailureKind,
    BootObservationReceipt,
    BootObservationService,
    BootObservationStatus,
)
from romverse.rom.first_light import FirstLightReport, FirstLightService
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.readiness import BuildReadinessService
from romverse.rom.recovery_evidence import RecoveryEvidenceService
from romverse.rom.source_intelligence import FirmwareSourceIntelligenceService
from romverse.ui.about_state import OriginDiscoveryError, OriginDiscoveryStore
from romverse.ui.activity_center import ActivityCenter
from romverse.ui.apk_center import ApkCenter
from romverse.ui.background import (
    CoalescedProgress,
    ManagedRunnable,
    measured_percent,
    shutdown_background_tasks,
    start_background,
)
from romverse.ui.backup_center import BackupCenter
from romverse.ui.command_palette import CommandPaletteDialog, NavigationCommand
from romverse.ui.companion_center import CompanionCenter
from romverse.ui.connectivity import OnlineStatusBadge
from romverse.ui.cosmic_icons import sidebar_icon
from romverse.ui.device_center import DeviceCenter, RomStudioDeviceContext
from romverse.ui.device_packs_center import DevicePacksCenter
from romverse.ui.diagnostics_center import DiagnosticsCenter
from romverse.ui.formatters import human_bytes
from romverse.ui.galaxy_center import GalaxyCenter
from romverse.ui.guardian_center import GuardianCenter
from romverse.ui.history_center import HistoryCenter
from romverse.ui.knowledge_center import ARCHIVE_ARTICLES, KnowledgeCenter
from romverse.ui.live_console import LiveConsoleCenter
from romverse.ui.members_center import MembersCenter
from romverse.ui.nexus_center import NexusCenter
from romverse.ui.notifications import DesktopNotificationCenter, NotificationKind
from romverse.ui.origin_story import ORIGIN_SCENES
from romverse.ui.recovery_operation_session import (
    RecoveryOperationSession,
    RecoveryOperationSessionError,
)
from romverse.ui.repair_center import RepairCenter
from romverse.ui.rom_studio import RomStudio, confirm_expert_mode
from romverse.ui.terminal_center import TerminalCenter
from romverse.ui.theme import STYLESHEET, apply_dark_palette
from romverse.ui.toolchain_center import (
    DevicePackToolchainContext,
    RepairToolchainContext,
    StudioProjectToolchainContext,
    ToolchainCenter,
)
from romverse.ui.vocabulary import (
    EXPERT_ONLY_NESTED_FEATURES,
    FEATURES,
    NESTED_FEATURE_OWNERS,
    feature,
)
from romverse.ui.workspace_shell import (
    EXPERT_ONLY_ROUTES,
    NAVIGATION_GROUPS,
    WorkspaceShellState,
    navigation_section,
)
from romverse.updates import (
    DesktopUpdateCancelled,
    DesktopUpdateCandidate,
    DesktopUpdateService,
    StagedDesktopUpdate,
)

ROMVERSE_WEBSITE_URL = "https://romverse.app/"
RADFORGE_LABS_URL = "https://radforgelabs.com/"
FACEBOOK_URL = "https://www.facebook.com/ROMVERSEOfficial"
REDDIT_URL = "https://www.reddit.com/user/ROMVERSE/"
GITHUB_URL = "https://github.com/SteveTheRad/ROMVERSE"
DESKTOP_WINDOW_TITLE = f"ROMVERSE Studio {DISPLAY_VERSION}"
DESKTOP_SIDEBAR_VERSION = f"ROMVERSE  {DISPLAY_VERSION}"

DESKTOP_THEMES: dict[DesktopTheme, tuple[str, str]] = {
    DesktopTheme.NEBULA_FLOW: ("Nebula Flow", ""),
    DesktopTheme.AURORA: (
        "Aurora",
        "QFrame#DashboardCard, QFrame#AboutTrustDock { border-color:#2B6C78; } "
        "QLabel#DashboardHeading, QLabel#Eyebrow { color:#36E1D2; } "
        "QPushButton#QuickAction:hover { border-color:#2DE7DA; }",
    ),
    DesktopTheme.VIOLET_NIGHT: (
        "Violet Night",
        "QFrame#DashboardCard, QFrame#AboutTrustDock { border-color:#563F83; } "
        "QLabel#DashboardHeading, QLabel#Eyebrow { color:#D18CFF; } "
        "QPushButton#QuickAction:hover { border-color:#D18CFF; }",
    ),
    DesktopTheme.NEBULA_ROSE: (
        "Nebula Rose",
        "QFrame#DashboardCard, QFrame#AboutTrustDock { border-color:#7D3E6D; } "
        "QLabel#DashboardHeading, QLabel#Eyebrow { color:#FF8AD8; } "
        "QPushButton#QuickAction:hover { border-color:#FF70C9; background:rgba(67,20,58,245); } "
        "QLabel#Good { color:#69F2C0; }",
    ),
    DesktopTheme.DEEP_SPACE: (
        "Deep Space",
        "QFrame#DashboardCard, QFrame#AboutTrustDock { border-color:#293C67; } "
        "QLabel#DashboardHeading, QLabel#Eyebrow { color:#78A8FF; } "
        "QPushButton#QuickAction:hover { border-color:#78A8FF; background:rgba(19,34,73,245); }",
    ),
    DesktopTheme.SOLAR_FLARE: (
        "Solar Flare",
        "QFrame#DashboardCard, QFrame#AboutTrustDock { border-color:#806137; } "
        "QLabel#DashboardHeading, QLabel#Eyebrow { color:#FFC46B; } "
        "QPushButton#QuickAction:hover { border-color:#FFB454; background:rgba(67,43,18,245); }",
    ),
    DesktopTheme.QUANTUM_MINT: (
        "Quantum Mint",
        "QFrame#DashboardCard, QFrame#AboutTrustDock { border-color:#2E776D; } "
        "QLabel#DashboardHeading, QLabel#Eyebrow { color:#65F0D1; } "
        "QPushButton#QuickAction:hover { border-color:#65F0D1; background:rgba(15,62,56,245); }",
    ),
}


@dataclass(frozen=True, slots=True)
class AboutRuntimeEvidence:
    """Bounded, read-only facts shown on About instead of marketing telemetry."""

    device_pack_count: int
    device_pack_issue_count: int
    catalog_valid: bool
    catalog_fresh: bool
    catalog_entry_count: int
    catalog_reason: str
    archive_guide_count: int
    archive_known_fix_count: int
    archive_category_count: int
    project_count: int
    tool_ready_count: int
    tool_count: int
    live_ledger_valid: bool
    live_event_count: int
    live_active_count: int
    guardian_state: str
    guardian_detail: str
    guardian_verified: bool

    def __post_init__(self) -> None:
        counts = (
            self.device_pack_count,
            self.device_pack_issue_count,
            self.catalog_entry_count,
            self.archive_guide_count,
            self.archive_known_fix_count,
            self.archive_category_count,
            self.project_count,
            self.tool_ready_count,
            self.tool_count,
            self.live_event_count,
            self.live_active_count,
        )
        if any(value < 0 for value in counts):
            raise ValueError("About runtime evidence counts cannot be negative")
        if self.tool_ready_count > self.tool_count:
            raise ValueError("About runtime evidence has more ready tools than verified tools")
        if not self.catalog_valid and self.catalog_entry_count:
            raise ValueError("Rejected device catalog evidence cannot expose trusted entries")
        if not self.live_ledger_valid and (self.live_event_count or self.live_active_count):
            raise ValueError("Rejected Live Console evidence cannot expose trusted event counts")
        if self.live_active_count > self.live_event_count:
            raise ValueError("Active Live Console events cannot exceed the verified ledger")
        guardian_states = {
            "unverified",
            "review_due",
            "verifying",
            "verified",
            "locked",
            "failed",
            "unavailable",
        }
        if self.guardian_state not in guardian_states:
            raise ValueError("About runtime evidence has an invalid Guardian state")
        if self.guardian_verified is not (self.guardian_state == "verified"):
            raise ValueError("About runtime evidence has contradictory Guardian verification")
        if (
            not isinstance(self.guardian_detail, str)
            or not self.guardian_detail.strip()
            or "\x00" in self.guardian_detail
            or len(self.guardian_detail) > 360
        ):
            raise ValueError("About runtime evidence has invalid Guardian detail")


def _sidebar_nav_tooltip(label: str, subtitle: str) -> str:
    """Return a compact wrapped hint instead of a workspace-covering single line."""

    return (
        "<qt><table width='220' cellspacing='0' cellpadding='0'>"
        f"<tr><td><b>{escape(label)}</b></td></tr>"
        f"<tr><td><span style='color: #B9C7E8;'>{escape(subtitle)}</span></td></tr>"
        "</table></qt>"
    )


def _sidebar_device_art_kind(device: AndroidDevice) -> str:
    """Choose product art only when the connected identity proves that exact device."""

    codename = device.codename.strip().casefold()
    model = device.model.strip().casefold()
    marketing_name = device.marketing_name.strip().casefold()
    if codename == "popsicle" and (model == "2509fpn0bc" or marketing_name == "xiaomi 17 pro max"):
        return "xiaomi-17-pro-max"
    return "generic-android"


def _device_scan_failure_copy(message: str) -> tuple[str, str, str]:
    """Keep the persistent status truthful while the detailed page holds raw evidence."""

    normalized = " ".join(message.split()).casefold()
    if "guardian audit" in normalized or "audit integrity" in normalized:
        return (
            "⌁  Guardian evidence needs attention",
            "●  Guardian ledger needs attention",
            "Evidence verification paused the scan • ROMVERSE will retry safely",
        )
    if "permission denied" in normalized or "insufficient permissions" in normalized:
        return (
            "⌁  USB permission needs attention",
            "●  USB permission needs attention",
            "Reconnect the data cable or review USB access • automatic retry is active",
        )
    if "daemon" in normalized or "server version" in normalized:
        return (
            "⌁  ADB service is restarting",
            "●  Reconnecting Device Engine",
            "ROMVERSE is restoring the local ADB service • automatic retry is active",
        )
    if any(
        marker in normalized
        for marker in (
            "adb transport",
            "device offline",
            "transport closed",
            "transport error",
            "no devices/emulators",
        )
    ):
        return (
            "⌁  Reconnecting Device Engine",
            "●  Reconnecting device",
            "ROMVERSE is waiting for a stable USB/ADB link • automatic retry is active",
        )
    if "timed out" in normalized or "timeout" in normalized:
        return (
            "⌁  Device scan timed out",
            "●  Device response delayed",
            "ROMVERSE stopped the slow probe safely • automatic retry is active",
        )
    return (
        "⌁  Device scan needs attention",
        "●  Device Engine needs attention",
        "Open Device Engine for details • automatic retry is active",
    )


def _device_scan_failure_is_transient(message: str) -> bool:
    """Identify failures that should begin as recovery, not a persistent red alarm."""

    normalized = " ".join(message.split()).casefold()
    return any(
        marker in normalized
        for marker in (
            "adb transport",
            "daemon",
            "device offline",
            "no devices/emulators",
            "server version",
            "timed out",
            "timeout",
            "transport closed",
            "transport error",
        )
    )


def _generic_phone_pixmap(width: int = 60, height: int = 84) -> QPixmap:
    """Render neutral, crisp phone art without inventing a manufacturer or model."""

    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    scale_x = width / 60.0
    scale_y = height / 84.0
    body = QRectF(8 * scale_x, 2 * scale_y, 44 * scale_x, 80 * scale_y)
    body_gradient = QLinearGradient(body.topLeft(), body.bottomRight())
    body_gradient.setColorAt(0.0, QColor("#6DEBFF"))
    body_gradient.setColorAt(0.48, QColor("#4F7CFF"))
    body_gradient.setColorAt(1.0, QColor("#B45CFF"))
    painter.setPen(QPen(QColor("#A5F5FF"), max(1.2, 1.4 * scale_x)))
    painter.setBrush(body_gradient)
    painter.drawRoundedRect(body, 8 * scale_x, 8 * scale_y)

    screen = body.adjusted(4 * scale_x, 6 * scale_y, -4 * scale_x, -8 * scale_y)
    screen_gradient = QLinearGradient(screen.topLeft(), screen.bottomRight())
    screen_gradient.setColorAt(0.0, QColor("#071222"))
    screen_gradient.setColorAt(0.6, QColor("#0A1630"))
    screen_gradient.setColorAt(1.0, QColor("#170E31"))
    painter.setPen(QPen(QColor(90, 220, 246, 115), max(0.8, scale_x)))
    painter.setBrush(screen_gradient)
    painter.drawRoundedRect(screen, 5 * scale_x, 5 * scale_y)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#6DEBFF"))
    painter.drawEllipse(QPointF(width / 2.0, 6.5 * scale_y), 1.5 * scale_x, 1.5 * scale_y)
    painter.setBrush(QColor(180, 92, 255, 175))
    painter.drawEllipse(
        QPointF(width * 0.68, height * 0.34),
        8 * scale_x,
        13 * scale_y,
    )
    painter.setBrush(QColor(45, 218, 242, 145))
    painter.drawEllipse(
        QPointF(width * 0.42, height * 0.53),
        10 * scale_x,
        16 * scale_y,
    )
    painter.setPen(QPen(QColor("#C7F8FF"), max(1.0, 1.2 * scale_x)))
    painter.drawLine(
        QPointF(width * 0.39, height * 0.91),
        QPointF(width * 0.61, height * 0.91),
    )
    painter.end()
    return pixmap


class ScanSignals(QObject):
    complete = Signal(list)
    failed = Signal(str)


class ScanWorker(ManagedRunnable):
    def __init__(self, engine: DeviceEngine) -> None:
        super().__init__()
        self.engine = engine
        self.signals = ScanSignals()

    @Slot()
    def execute(self) -> None:
        try:
            self.signals.complete.emit(self.engine.scan_reconnect_safe())
        except Exception as exc:  # UI boundary converts adapter failures to visible state
            self.signals.failed.emit(str(exc))


class DeviceCatalogSignals(QObject):
    complete = Signal(object)
    failed = Signal(str)
    cancelled = Signal()


class DeviceCatalogWorker(ManagedRunnable):
    def __init__(self, catalog: GooglePlayDeviceCatalog) -> None:
        super().__init__()
        self.catalog = catalog
        self.signals = DeviceCatalogSignals()
        self._cancel_requested = Event()

    def cancel(self) -> None:
        """Withdraw permission before any downloaded catalog can be activated."""

        self._cancel_requested.set()

    @Slot()
    def execute(self) -> None:
        try:
            update = self.catalog.fetch(should_cancel=self._cancel_requested.is_set)
            if self._cancel_requested.is_set():
                self.signals.cancelled.emit()
                return
            self.signals.complete.emit(update)
        except DeviceCatalogCancelled:
            self.signals.cancelled.emit()
        except DeviceCatalogError as exc:
            self.signals.failed.emit(str(exc))
        except Exception:
            self.signals.failed.emit("Official Android device ID sync failed unexpectedly")


class LogoLabel(QLabel):
    double_clicked = Signal()

    def mouseDoubleClickEvent(self, event) -> None:
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)


class WebsiteBrandCrest(QWidget):
    """Native Qt presentation of the exact production romverse.app crest."""

    double_clicked = Signal()
    FLOAT_SECONDS = 6.2
    ORBIT_SECONDS = 34.0
    SCAN_SECONDS = 5.5
    HOVER_SECONDS = 0.6

    def __init__(
        self,
        image_path: Path,
        *,
        reduced_motion: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._source = QPixmap(str(image_path))
        self._scaled = QPixmap()
        self._started = time.monotonic()
        self._hover_started: float | None = None
        self._reduced_motion = bool(reduced_motion)
        self.setAccessibleName("ROMVERSE official website crest")
        self.setToolTip("Official ROMVERSE crest • double-click to discover The Origin")
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._motion_timer = QTimer(self)
        # The production motion curves are several seconds long; 20 FPS remains
        # visually smooth while avoiding needless 30 Hz wakeups on every page.
        self._motion_timer.setTimerType(Qt.TimerType.CoarseTimer)
        self._motion_timer.setInterval(50)
        self._motion_timer.timeout.connect(self.update)

    def pixmap(self) -> QPixmap:
        """Expose the exact loaded source for lightweight UI and package checks."""

        return self._source

    def set_reduced_motion(self, enabled: bool) -> None:
        self._reduced_motion = bool(enabled)
        self._hover_started = None
        self._sync_motion()
        self.update()

    @property
    def reduced_motion(self) -> bool:
        return self._reduced_motion

    @property
    def motion_running(self) -> bool:
        return self._motion_timer.isActive()

    def showEvent(self, event) -> None:
        self._started = time.monotonic()
        self._sync_motion()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._motion_timer.stop()
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:
        side = max(1, round(min(self.width(), self.height()) * 0.89))
        self._scaled = self._source.scaled(
            side,
            side,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        super().resizeEvent(event)

    def enterEvent(self, event) -> None:
        if not self._reduced_motion:
            self._hover_started = time.monotonic()
            self._sync_motion()
        super().enterEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        side = float(min(self.width(), self.height()))
        center = QPointF(self.width() / 2, self.height() / 2)
        now = time.monotonic()
        elapsed = 0.0 if self._reduced_motion else max(0.0, now - self._started)

        halo = QRadialGradient(center, side * 0.48)
        halo.setColorAt(0.0, QColor(96, 56, 255, 58))
        halo.setColorAt(0.56, QColor(34, 197, 246, 18))
        halo.setColorAt(1.0, QColor(2, 5, 16, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(center, side * 0.48, side * 0.48)

        painter.save()
        painter.translate(center)
        painter.rotate((elapsed / self.ORBIT_SECONDS) * 360.0)
        orbit_pen = QPen(QColor(53, 222, 247, 112), max(1.0, side / 360.0))
        orbit_pen.setDashPattern((1.0, 8.0))
        painter.setPen(orbit_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        orbit_radius = side * 0.475
        painter.drawEllipse(
            QRectF(-orbit_radius, -orbit_radius, orbit_radius * 2, orbit_radius * 2)
        )
        painter.restore()

        lift = (1.0 - math.cos((elapsed / self.FLOAT_SECONDS) * math.tau)) / 2.0
        scale = 1.0 + 0.012 * lift
        art_side = side * 0.89 * scale
        float_offset = -(side * 10.0 / 470.0) * lift
        art_rect = QRectF(
            center.x() - art_side / 2,
            center.y() - art_side / 2 + float_offset,
            art_side,
            art_side,
        )
        clip = QPainterPath()
        clip.addEllipse(art_rect)
        painter.save()
        painter.setClipPath(clip)
        if not self._scaled.isNull():
            painter.drawPixmap(art_rect, self._scaled, QRectF(self._scaled.rect()))

        if not self._reduced_motion:
            cycle = (elapsed % self.SCAN_SECONDS) / self.SCAN_SECONDS
            if cycle <= 0.12:
                scan_y, scan_opacity = -0.15, 0.22
            elif cycle <= 0.65:
                progress = (cycle - 0.12) / 0.53
                scan_y, scan_opacity = -0.15 + progress * 1.30, 0.22 + progress * 0.43
            else:
                progress = (cycle - 0.65) / 0.35
                scan_y, scan_opacity = 1.15, 0.65 - progress * 0.47
            scan = QLinearGradient(art_rect.left(), 0, art_rect.right(), 0)
            scan.setColorAt(0.0, QColor(39, 220, 255, 0))
            scan.setColorAt(0.5, QColor(94, 236, 255, round(190 * scan_opacity)))
            scan.setColorAt(1.0, QColor(39, 220, 255, 0))
            painter.fillRect(
                QRectF(
                    art_rect.left(),
                    art_rect.top() + scan_y * art_rect.height(),
                    art_rect.width(),
                    2.0,
                ),
                QBrush(scan),
            )

        if self._hover_started is not None:
            hover = min(1.0, max(0.0, (now - self._hover_started) / self.HOVER_SECONDS))
            sweep_x = art_rect.left() - art_rect.width() * 0.38 + art_rect.width() * 1.76 * hover
            shimmer = QLinearGradient(
                sweep_x - art_rect.width() * 0.15,
                0,
                sweep_x + art_rect.width() * 0.15,
                0,
            )
            shimmer.setColorAt(0.0, QColor(255, 255, 255, 0))
            shimmer.setColorAt(0.5, QColor(255, 255, 255, 72))
            shimmer.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
            painter.fillRect(art_rect, QBrush(shimmer))
            if hover >= 1.0:
                self._hover_started = None
        painter.restore()

        rim_pen = QPen(QColor(107, 74, 255, 80), max(1.0, side / 420.0))
        painter.setPen(rim_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(art_rect)
        painter.end()

    def _sync_motion(self) -> None:
        if self.isVisible() and not self._reduced_motion:
            self._motion_timer.start()
        else:
            self._motion_timer.stop()


class BrandWordmark(QWidget):
    """Small dimensional ROMVERSE wordmark for the sidebar brand block."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(30)
        self.setMinimumWidth(190)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont("Inter", 20, QFont.Weight.Black)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.4)
        painter.setFont(font)
        text = "ROMVERSE"
        bounds = painter.fontMetrics().boundingRect(text)
        x = (self.width() - bounds.width()) / 2 - bounds.left()
        y = (self.height() - bounds.height()) / 2 - bounds.top()
        # Deep extrusion and a restrained violet halo create depth without blur.
        painter.setPen(QColor(4, 6, 18, 230))
        for offset in (5, 4, 3, 2):
            painter.drawText(int(x + offset * 0.55), int(y + offset), text)
        painter.setPen(QPen(QColor("#783DB8"), 1.6))
        painter.drawText(int(x), int(y), text)
        gradient = QLinearGradient(0, y - bounds.height(), 0, y + 3)
        gradient.setColorAt(0.0, QColor("#FFFFFF"))
        gradient.setColorAt(0.46, QColor("#D8E7FF"))
        gradient.setColorAt(0.72, QColor("#88B9FF"))
        gradient.setColorAt(1.0, QColor("#B45CFF"))
        painter.setPen(QPen(QBrush(gradient), 0.5))
        painter.drawText(int(x), int(y), text)
        painter.end()


class BrandProject(QWidget):
    """Readable project credit with the same luminous depth as the wordmark."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(24)
        self.setMinimumWidth(210)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = "A  RADFORGE LABS  PROJECT"
        font = QFont("Inter", 9, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.9)
        painter.setFont(font)
        bounds = painter.fontMetrics().boundingRect(text)
        x = (self.width() - bounds.width()) / 2 - bounds.left()
        y = (self.height() - bounds.height()) / 2 - bounds.top()
        painter.setPen(QColor(5, 7, 19, 235))
        painter.drawText(int(x + 1), int(y + 2), text)
        gradient = QLinearGradient(0, 0, self.width(), 0)
        gradient.setColorAt(0.0, QColor("#EEF4FF"))
        gradient.setColorAt(0.20, QColor("#B45CFF"))
        gradient.setColorAt(0.68, QColor("#8B9DFF"))
        gradient.setColorAt(1.0, QColor("#EEF4FF"))
        painter.setPen(QPen(QBrush(gradient), 0.5))
        painter.drawText(int(x), int(y), text)
        painter.end()


class PortalCanvas(QWidget):
    _SCENE_FOCUS = (0.10, 0.28, 0.49, 0.49, 0.70, 0.89, 0.89)

    def __init__(
        self,
        logo_path: Path,
        chronicle_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.logo = QPixmap(str(logo_path))
        self.chronicle = QPixmap(str(chronicle_path)) if chronicle_path else QPixmap()
        self.progress = 0.0
        self.scene_index = 0
        self.scene_progress = 0.0
        self.reduced_motion = False
        self._stars = tuple(
            (
                ((index * 83 + 17) % 997) / 997.0,
                ((index * 151 + 41) % 991) / 991.0,
                0.7 + (index % 4) * 0.35,
            )
            for index in range(68)
        )

    def set_progress(self, progress: float) -> None:
        self.progress = max(0.0, min(1.0, progress))
        self.update()

    def set_story_scene(self, index: int, progress: float = 0.0) -> None:
        self.scene_index = max(0, min(index, len(self._SCENE_FOCUS) - 1))
        self.scene_progress = 0.0 if self.reduced_motion else max(0.0, min(1.0, progress))
        self.update()

    def set_reduced_motion(self, enabled: bool) -> None:
        self.reduced_motion = bool(enabled)
        if self.reduced_motion:
            self.scene_progress = 0.0
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        progress = self.progress

        # The approved logo remains a separate, lossless layer. The generated
        # chronicle is illustration only, so public copy stays crisp and localizable.
        panel = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        panel_fill = QLinearGradient(panel.topLeft(), panel.bottomRight())
        panel_fill.setColorAt(0.0, QColor(9, 14, 38, 238))
        panel_fill.setColorAt(0.55, QColor(20, 10, 48, 232))
        panel_fill.setColorAt(1.0, QColor(3, 31, 39, 230))
        painter.setBrush(panel_fill)
        painter.setPen(QPen(QColor(2, 3, 10, 245), 7))
        painter.drawRoundedRect(panel, 12, 12)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(194, 159, 85, 225), 2))
        art_rect = panel.adjusted(6, 6, -6, -6)
        painter.drawRoundedRect(art_rect, 9, 9)

        if not self.chronicle.isNull() and art_rect.width() > 0 and art_rect.height() > 0:
            painter.save()
            clip = QPainterPath()
            clip.addRoundedRect(art_rect.adjusted(1, 1, -1, -1), 8, 8)
            painter.setClipPath(clip)

            image_width = float(self.chronicle.width())
            image_height = float(self.chronicle.height())
            target_ratio = art_rect.width() / art_rect.height()
            image_ratio = image_width / image_height
            if image_ratio > target_ratio:
                source_height = image_height
                source_width = source_height * target_ratio
            else:
                source_width = image_width
                source_height = source_width / target_ratio

            drift = 0.0 if self.reduced_motion else math.sin(self.scene_progress * math.pi) * 0.018
            zoom = 1.0 + drift
            source_width /= zoom
            source_height /= zoom
            focus = self._SCENE_FOCUS[self.scene_index]
            focus_x = image_width * focus
            source_x = max(0.0, min(image_width - source_width, focus_x - source_width / 2))
            vertical_drift = 0.0
            if not self.reduced_motion:
                vertical_drift = math.sin((self.scene_progress + self.scene_index) * math.pi) * 7.0
            source_y = max(
                0.0,
                min(
                    image_height - source_height,
                    (image_height - source_height) / 2 + vertical_drift,
                ),
            )
            painter.setOpacity(0.97)
            painter.drawPixmap(
                art_rect,
                self.chronicle,
                QRectF(source_x, source_y, source_width, source_height),
            )

            # A restrained moving pool of light leads the eye through each chapter.
            if self.progress >= 1.0:
                spotlight_x = art_rect.left() + art_rect.width() * focus
                spotlight = QRadialGradient(
                    QPointF(spotlight_x, art_rect.center().y()),
                    max(art_rect.width() * 0.42, art_rect.height()),
                )
                spotlight.setColorAt(0.0, QColor(8, 12, 30, 0))
                spotlight.setColorAt(0.35, QColor(8, 12, 30, 8))
                spotlight.setColorAt(0.72, QColor(2, 5, 18, 70))
                spotlight.setColorAt(1.0, QColor(2, 5, 18, 145))
                painter.setOpacity(1.0)
                painter.fillRect(art_rect, spotlight)

            lower_veil = QLinearGradient(art_rect.bottomLeft(), art_rect.topLeft())
            lower_veil.setColorAt(0.0, QColor(2, 5, 16, 105))
            lower_veil.setColorAt(0.42, QColor(2, 5, 16, 0))
            lower_veil.setColorAt(1.0, QColor(2, 5, 16, 10))
            painter.fillRect(art_rect, lower_veil)
            painter.restore()

        # Small celestial chapter markers make the artwork feel like a navigable atlas.
        marker_y = art_rect.bottom() - 13
        marker_width = min(170.0, art_rect.width() * 0.30)
        marker_start = art_rect.center().x() - marker_width / 2
        painter.setPen(Qt.PenStyle.NoPen)
        for index in range(len(self._SCENE_FOCUS)):
            marker_x = marker_start + index * marker_width / (len(self._SCENE_FOCUS) - 1)
            active = index == self.scene_index
            painter.setBrush(QColor("#F1CC77") if active else QColor(226, 214, 183, 135))
            radius = 3.8 if active else 2.1
            painter.drawEllipse(QPointF(marker_x, marker_y), radius, radius)

        # The surrounding stars bend toward the event horizon before the portal opens.
        gather = min(0.58, max(0.0, (progress - 0.03) / 0.48) * 0.58)
        star_fade = max(0.0, 1.0 - max(0.0, progress - 0.74) / 0.26)
        for index, (x_ratio, y_ratio, star_size) in enumerate(self._stars):
            origin = QPointF(x_ratio * self.width(), y_ratio * self.height())
            point = origin + (center - origin) * gather
            shimmer = 0.58 + 0.42 * math.sin(progress * 24 + index * 1.7)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(165, 219, 255, int(105 * shimmer * star_fade)))
            painter.drawEllipse(point, star_size, star_size)
            if 0.18 < progress < 0.58 and index % 4 == 0:
                painter.setPen(QPen(QColor(116, 103, 255, 55), 0.8))
                painter.drawLine(origin, point)

        opening = min(1.0, max(0.0, (progress - 0.08) / 0.34))
        collapse = max(0.0, 1.0 - max(0.0, progress - 0.62) / 0.18)
        portal_alpha = opening * collapse
        radius = 16 + min(self.width() * 0.19, 150) * opening

        painter.save()
        painter.setOpacity(portal_alpha)
        halo = QRadialGradient(center, radius * 1.72)
        halo.setColorAt(0.0, QColor(255, 255, 255, 235))
        halo.setColorAt(0.12, QColor(76, 220, 255, 210))
        halo.setColorAt(0.34, QColor(94, 93, 255, 155))
        halo.setColorAt(0.61, QColor(193, 62, 255, 88))
        halo.setColorAt(1.0, QColor(2, 4, 16, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(center, radius * 1.72, radius * 0.72)

        # Counter-rotating accretion bands give the portal depth without heavy effects.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        ring_specs = (
            (1.48, 0.52, QColor(205, 80, 255, 220), 4.2, 2140, 1),
            (1.30, 0.42, QColor(62, 219, 255, 230), 3.1, 1760, -1),
            (1.12, 0.34, QColor(112, 104, 255, 205), 2.0, 1320, 1),
        )
        for width_scale, height_scale, color, pen_width, span, direction in ring_specs:
            painter.setPen(QPen(color, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(
                int(center.x() - radius * width_scale),
                int(center.y() - radius * height_scale),
                int(radius * width_scale * 2),
                int(radius * height_scale * 2),
                int((progress * 7800 * direction) % 5760),
                span,
            )

        core = QRadialGradient(center, radius * 0.72)
        core.setColorAt(0.0, QColor(0, 0, 2, 255))
        core.setColorAt(0.72, QColor(1, 2, 9, 255))
        core.setColorAt(0.88, QColor(18, 10, 58, 250))
        core.setColorAt(1.0, QColor(107, 63, 255, 90))
        painter.setBrush(core)
        painter.setPen(QPen(QColor(126, 218, 255, 180), 1.2))
        painter.drawEllipse(center, radius * 0.67, radius * 0.67)

        painter.setPen(QPen(QColor(222, 236, 255, 150), 1.25))
        for index in range(14):
            angle = progress * 8.0 + index * math.pi / 7
            inner = center + QPointF(
                math.cos(angle) * radius * 0.82,
                math.sin(angle) * radius * 0.33,
            )
            outer = center + QPointF(
                math.cos(angle) * radius * (1.18 + (index % 3) * 0.12),
                math.sin(angle) * radius * (0.50 + (index % 2) * 0.08),
            )
            painter.drawLine(inner, outer)
        painter.restore()

        # The collapse produces one restrained supernova pulse and reveals the mark.
        pulse = max(0.0, 1.0 - abs(progress - 0.66) / 0.11)
        if pulse > 0:
            pulse_radius = radius * (0.45 + pulse * 1.75)
            flash = QRadialGradient(center, pulse_radius)
            flash.setColorAt(0.0, QColor(255, 255, 255, int(245 * pulse)))
            flash.setColorAt(0.20, QColor(82, 225, 255, int(210 * pulse)))
            flash.setColorAt(0.58, QColor(177, 66, 255, int(100 * pulse)))
            flash.setColorAt(1.0, QColor(10, 14, 44, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(flash)
            painter.drawEllipse(center, pulse_radius, pulse_radius)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(142, 215, 255, int(190 * pulse)), 2.0))
            painter.drawEllipse(center, pulse_radius * 1.6, pulse_radius * 0.48)
            burst_font = QFont("DejaVu Sans", 23, QFont.Weight.Black)
            burst_font.setItalic(True)
            painter.setFont(burst_font)
            burst_text = "THE RIFT OPENS"
            burst_bounds = painter.fontMetrics().boundingRect(burst_text)
            burst_x = int(center.x() - burst_bounds.width() / 2)
            burst_y = int(max(42, center.y() - radius * 0.62))
            painter.setPen(QPen(QColor(1, 2, 8, int(245 * pulse)), 6))
            painter.drawText(burst_x, burst_y, burst_text)
            painter.setPen(QColor(255, 218, 79, int(255 * pulse)))
            painter.drawText(burst_x, burst_y, burst_text)

        reveal = min(1.0, max(0.0, (progress - 0.69) / 0.22))
        if reveal > 0 and not self.logo.isNull():
            eased = 1.0 - (1.0 - reveal) ** 3
            icon_size = int(74 + 72 * eased)
            icon = self.logo.scaled(
                icon_size,
                icon_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.save()
            painter.setOpacity(reveal)
            icon_glow = QRadialGradient(center, icon_size * 0.78)
            icon_glow.setColorAt(0.0, QColor(112, 82, 255, 100))
            icon_glow.setColorAt(1.0, QColor(3, 5, 14, 0))
            painter.setBrush(icon_glow)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(center, icon_size * 0.82, icon_size * 0.82)
            icon_rect = QRectF(
                center.x() - icon.width() / 2,
                center.y() - icon.height() / 2,
                icon.width(),
                icon.height(),
            )
            seal = QPainterPath()
            seal.addEllipse(icon_rect)
            painter.setClipPath(seal)
            painter.drawPixmap(icon_rect, icon, QRectF(icon.rect()))
            painter.setClipping(False)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(231, 199, 115, int(220 * reveal)), 1.4))
            painter.drawEllipse(icon_rect.adjusted(1, 1, -1, -1))
            painter.restore()
        painter.end()


class ThanksPortal(QDialog):
    def __init__(
        self,
        logo_path: Path,
        parent: QWidget | None = None,
        *,
        first_discovery: bool = False,
        reduced_motion: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("ROMVERSE: The Origin")
        self.setModal(False)
        self.setMinimumSize(800, 740)
        self._fit_to_screen()
        self.setStyleSheet(
            "QDialog { background: #02040B; border: 1px solid #7E6B44; border-radius: 22px; }"
            "QLabel { color: #EDF4FF; background: transparent; }"
            "QProgressBar { background: rgba(15, 20, 43, 220); border: 1px solid "
            "rgba(96, 124, 190, 110); border-radius: 3px; min-height: 5px; max-height: 5px; }"
            "QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #A44CFF, stop:0.54 #36E7F5, stop:1 #E7C773); border-radius: 3px; }"
            "QFrame#OriginComicStage { background: rgba(5, 8, 20, 238); border: 3px solid #050611; "
            "border-top: 3px solid #C5A65E; border-radius: 15px; }"
            "QLabel#OriginIssue { color:#18233B; background:#E8D5A5; border:2px solid #8B713C; "
            "border-radius:5px; padding:5px 9px; font-size:10px; font-weight:900; letter-spacing:1px; }"
            "QLabel#OriginBurst { color:#FAEBC7; background:#43306F; border:1px solid #C29A50; "
            "border-radius:5px; padding:5px 11px; font-size:11px; font-weight:900; letter-spacing:1px; }"
            "QScrollArea#OriginStoryScroll { background: rgba(236, 221, 187, 238); "
            "border: 1px solid rgba(194, 154, 80, 210); border-radius: 9px; }"
        )
        self._reduced_motion = bool(reduced_motion)
        self._scene_index = 0
        self._scene_elapsed_ms = 0
        self._scene_running = False
        self._last_scene_tick = time.monotonic()
        self._sound_enabled = False
        self._cosmic_background = CosmicBackground(logo_path, self)
        self._cosmic_background.set_reduced_motion(self._reduced_motion)
        self._cosmic_background.lower()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(42, 20, 42, 24)
        layout.setSpacing(10)

        top = QHBoxLayout()
        self.chapter = QLabel()
        self.chapter.setStyleSheet(
            "color: #E7C773; font-size: 10px; font-weight: 800; letter-spacing: 2px;"
        )
        top.addWidget(self.chapter)
        top.addStretch(1)
        self.scene_counter = QLabel()
        self.scene_counter.setStyleSheet(
            "color: #8997B8; font-size: 10px; font-weight: 750; letter-spacing: 1px;"
        )
        top.addWidget(self.scene_counter)
        layout.addLayout(top)
        self.story_progress = QProgressBar()
        self.story_progress.setObjectName("OriginStoryProgress")
        self.story_progress.setRange(0, 1000)
        self.story_progress.setTextVisible(False)
        self.story_progress.setAccessibleName("The Origin story progress")
        layout.addWidget(self.story_progress)

        self.comic_stage = QFrame()
        self.comic_stage.setObjectName("OriginComicStage")
        comic_layout = QVBoxLayout(self.comic_stage)
        comic_layout.setContentsMargins(18, 14, 18, 15)
        comic_layout.setSpacing(7)
        comic_header = QHBoxLayout()
        self.issue_badge = QLabel("ROMVERSE ORIGIN  •  THE LIVING CHRONICLE")
        self.issue_badge.setObjectName("OriginIssue")
        comic_header.addWidget(self.issue_badge)
        comic_header.addStretch(1)
        self.comic_burst = QLabel("IGNITE!")
        self.comic_burst.setObjectName("OriginBurst")
        comic_header.addWidget(self.comic_burst)
        comic_layout.addLayout(comic_header)

        chronicle_resource = files("romverse.assets").joinpath(
            "romverse-origin-living-chronicle-v2.png"
        )
        with as_file(chronicle_resource) as chronicle_path:
            self.portal = PortalCanvas(
                logo_path,
                chronicle_path if chronicle_path.is_file() else None,
            )
        self.portal.set_reduced_motion(self._reduced_motion)
        self.portal.setAccessibleName("Illustrated ROMVERSE living chronicle")
        self.portal.setMinimumHeight(300)
        comic_layout.addWidget(self.portal)
        self.title = QLabel("ROMVERSE: THE ORIGIN  •  VOLUME I")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet(
            "color: #E7C773; font-size: 13px; font-weight: 800; letter-spacing: 3px;"
        )
        self.title_effect = QGraphicsOpacityEffect(self)
        self.title_effect.setOpacity(0.0)
        self.title.setGraphicsEffect(self.title_effect)
        comic_layout.addWidget(self.title)

        self.scene_title = QLabel()
        self.scene_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scene_title.setWordWrap(True)
        self.scene_title.setStyleSheet(
            "color: #E9D7A9; font-size: 23px; font-weight: 850; letter-spacing: 2px;"
        )
        comic_layout.addWidget(self.scene_title)
        self.constellation = QLabel()
        self.constellation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.constellation.setWordWrap(True)
        self.constellation.setStyleSheet(
            "color: #73EEFF; font-size: 10px; font-weight: 800; letter-spacing: 2px;"
        )
        comic_layout.addWidget(self.constellation)

        self.message = QLabel()
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setWordWrap(True)
        self.message.setStyleSheet(
            "font-family: 'DejaVu Sans', sans-serif; font-size: 14px; "
            "line-height: 128%; letter-spacing: 0.2px; color: #17223B; padding: 14px 22px;"
        )
        self.message_effect = QGraphicsOpacityEffect(self)
        self.message_effect.setOpacity(0.0)
        self.message.setGraphicsEffect(self.message_effect)
        self.message_scroll = QScrollArea()
        self.message_scroll.setObjectName("OriginStoryScroll")
        self.message_scroll.setWidgetResizable(True)
        self.message_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.message_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.message_scroll.viewport().setStyleSheet("background: transparent;")
        self.message_scroll.setWidget(self.message)
        comic_layout.addWidget(self.message_scroll, 1)
        layout.addWidget(self.comic_stage, 1)

        self.discovery_notice = QLabel(
            "SECRET AWARD UNLOCKED  •  BEYOND THE VERSE\n"
            "You discovered the story behind ROMVERSE. Discovery is recorded locally; "
            "account XP is never simulated."
        )
        self.discovery_notice.setVisible(first_discovery)
        self.discovery_notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.discovery_notice.setWordWrap(True)
        self.discovery_notice.setStyleSheet(
            "background: rgba(9, 38, 31, 210); color: #72FFB2; border: 1px solid "
            "rgba(114, 255, 178, 120); border-radius: 10px; padding: 10px 15px; "
            "font-size: 10px; font-weight: 800; letter-spacing: 1px;"
        )
        layout.addWidget(self.discovery_notice)

        accessibility = QHBoxLayout()
        self.sound_button = QPushButton("SOUND OFF")
        self.sound_button.setCheckable(True)
        self.sound_button.setAccessibleName("Toggle The Origin cinematic sound")
        self.sound_button.clicked.connect(self._toggle_sound)
        accessibility.addWidget(self.sound_button)
        self.reduced_effects = QCheckBox("REDUCED EFFECTS")
        self.reduced_effects.setChecked(self._reduced_motion)
        self.reduced_effects.setAccessibleName("Reduce The Origin motion and effects")
        self.reduced_effects.toggled.connect(self._set_reduced_effects)
        self.reduced_effects.setStyleSheet(
            "color: #AAB6D4; font-size: 10px; font-weight: 750; letter-spacing: 1px;"
        )
        accessibility.addWidget(self.reduced_effects)
        accessibility.addStretch(1)
        self.pause_button = QPushButton("PAUSE")
        self.pause_button.setCheckable(True)
        self.pause_button.setAccessibleName("Pause or resume The Origin")
        self.pause_button.clicked.connect(self._toggle_pause)
        accessibility.addWidget(self.pause_button)
        for button in (self.sound_button, self.pause_button):
            button.setStyleSheet(
                "QPushButton { background: rgba(8, 12, 28, 220); color: #AAB6D4; "
                "border: 1px solid rgba(105, 125, 175, 120); border-radius: 8px; "
                "padding: 8px 12px; font-size: 9px; font-weight: 800; letter-spacing: 1px; }"
                "QPushButton:checked { color: #73EEFF; border-color: #63ECF8; }"
            )
        layout.addLayout(accessibility)

        controls = QHBoxLayout()
        self.previous_button = QPushButton("←  PREVIOUS")
        self.previous_button.clicked.connect(self._previous_scene)
        controls.addWidget(self.previous_button)
        self.skip_button = QPushButton("SKIP TO FINALE")
        self.skip_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.skip_button.setAccessibleName("Skip The Origin to its finale")
        self.skip_button.setStyleSheet(
            "QPushButton { background: rgba(8, 12, 28, 220); color: #AAB6D4; "
            "border: 1px solid rgba(105, 125, 175, 120); border-radius: 10px; "
            "padding: 10px 18px; font-size: 11px; font-weight: 750; }"
            "QPushButton:hover { color: white; border-color: #63ECF8; }"
        )
        self.skip_button.clicked.connect(self._skip_to_finale)
        controls.addWidget(self.skip_button)
        controls.addStretch(1)
        self.return_button = QPushButton("RETURN TO ROMVERSE")
        self.return_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.return_button.setEnabled(True)
        self.return_button.setAccessibleName("Exit The Origin and return to ROMVERSE")
        self.return_button.setStyleSheet(
            "QPushButton { background: rgba(17, 24, 57, 238); color: #AFC8FF; "
            "border: 1px solid #365AA5; border-radius: 10px; padding: 10px 24px; "
            "font-size: 11px; font-weight: 800; letter-spacing: 2px; }"
            "QPushButton:hover { color: white; border-color: #63ECF8; "
            "background: rgba(32, 28, 78, 245); }"
            "QPushButton:disabled { color: rgba(175, 200, 255, 55); "
            "border-color: rgba(54, 90, 165, 55); }"
        )
        self.return_button.clicked.connect(self.close)
        controls.addWidget(self.return_button)
        self.next_button = QPushButton("NEXT  →")
        self.next_button.clicked.connect(self._next_scene)
        controls.addWidget(self.next_button)
        for button in (self.previous_button, self.next_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                "QPushButton { background: rgba(20, 22, 55, 230); color: #E3C5FF; "
                "border: 1px solid rgba(180, 92, 255, 140); border-radius: 10px; "
                "padding: 10px 16px; font-size: 10px; font-weight: 800; }"
                "QPushButton:hover { color: white; border-color: #63ECF8; }"
                "QPushButton:disabled { color: #4C5570; border-color: #242B44; }"
            )
        layout.addLayout(controls)

        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(0.16)
        self._media_player = QMediaPlayer(self)
        self._media_player.setAudioOutput(self._audio_output)
        ambient_resource = files("romverse.assets").joinpath("origin-ambient.wav")
        with as_file(ambient_resource) as ambient_path:
            if ambient_path.is_file():
                self._media_player.setSource(QUrl.fromLocalFile(str(ambient_path)))
                self._media_player.setLoops(QMediaPlayer.Loops.Infinite)
            else:
                self.sound_button.setEnabled(False)
                self.sound_button.setText("SOUND UNAVAILABLE")

        self._progress = 0.0
        self._portal_timer = QTimer(self)
        self._portal_timer.setInterval(33)
        self._portal_timer.timeout.connect(self._advance_portal)
        self._scene_timer = QTimer(self)
        self._scene_timer.setInterval(50)
        self._scene_timer.timeout.connect(self._advance_scene)
        self._render_scene(0)
        if self._reduced_motion:
            self._progress = 1.0
            self.portal.set_progress(1.0)
            self.title_effect.setOpacity(1.0)
            self.message_effect.setOpacity(1.0)
            self._begin_story()
        else:
            self._portal_timer.start()

    def resizeEvent(self, event) -> None:
        self._cosmic_background.setGeometry(self.rect())
        super().resizeEvent(event)

    def showEvent(self, event) -> None:
        self._fit_to_screen()
        super().showEvent(event)

    def _fit_to_screen(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1040, 900)
            return
        available = screen.availableGeometry()
        width = min(1240, max(800, int(available.width() * 0.88)))
        height = min(1000, max(740, int(available.height() * 0.92)))
        self.resize(width, height)

    def _advance_portal(self) -> None:
        self._progress = min(1.0, self._progress + 0.0075)
        self.portal.set_progress(self._progress)
        if self._progress > 0.58:
            self.title_effect.setOpacity(min(1.0, (self._progress - 0.58) / 0.12))
        if self._progress > 0.69:
            self.message_effect.setOpacity(min(1.0, (self._progress - 0.69) / 0.24))
        if self._progress > 0.91:
            self.return_button.setEnabled(True)
        if self._progress >= 1.0:
            self._portal_timer.stop()
            self._begin_story()

    def _begin_story(self) -> None:
        self._scene_running = True
        self._last_scene_tick = time.monotonic()
        if not self.pause_button.isChecked():
            self._scene_timer.start()

    def _render_scene(self, index: int) -> None:
        self._scene_index = max(0, min(index, len(ORIGIN_SCENES) - 1))
        self._scene_elapsed_ms = 0
        self._last_scene_tick = time.monotonic()
        scene = ORIGIN_SCENES[self._scene_index]
        self.portal.set_story_scene(self._scene_index)
        self.chapter.setText(scene.eyebrow.replace("SCENE", "PANEL"))
        self.scene_counter.setText(f"{self._scene_index + 1:02d} / {len(ORIGIN_SCENES):02d}")
        self.comic_burst.setText(
            ("IGNITE!", "UNITE!", "VERIFY!", "BUILD!", "TOGETHER!", "EXPAND!", "ROMVERSE!")[
                self._scene_index
            ]
        )
        self.scene_title.setText(scene.title)
        self.constellation.setText(scene.constellation)
        self.message.setText(scene.body)
        self.message_scroll.verticalScrollBar().setValue(0)
        self.previous_button.setEnabled(self._scene_index > 0)
        at_finale = self._scene_index == len(ORIGIN_SCENES) - 1
        self.next_button.setText("FINISH" if at_finale else "NEXT  →")
        self.skip_button.setVisible(not at_finale)
        self._update_story_progress()
        if not self._reduced_motion and self._progress >= 1.0:
            self.message_effect.setOpacity(0.0)
            fade = QPropertyAnimation(self.message_effect, b"opacity", self)
            fade.setDuration(500)
            fade.setStartValue(0.0)
            fade.setEndValue(1.0)
            fade.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._message_fade = fade
            fade.start(QAbstractAnimation.DeletionPolicy.KeepWhenStopped)
        else:
            self.message_effect.setOpacity(1.0)

    def _advance_scene(self) -> None:
        if not self._scene_running or self.pause_button.isChecked():
            return
        now = time.monotonic()
        elapsed = max(0, int((now - self._last_scene_tick) * 1000))
        self._last_scene_tick = now
        self._scene_elapsed_ms += elapsed
        scene = ORIGIN_SCENES[self._scene_index]
        self.portal.set_story_scene(
            self._scene_index,
            self._scene_elapsed_ms / max(1, scene.duration_ms),
        )
        if self._scene_elapsed_ms >= scene.duration_ms:
            if self._scene_index < len(ORIGIN_SCENES) - 1:
                self._render_scene(self._scene_index + 1)
            else:
                self._scene_timer.stop()
                self._scene_running = False
        self._update_story_progress()

    def _update_story_progress(self) -> None:
        completed = sum(scene.duration_ms for scene in ORIGIN_SCENES[: self._scene_index])
        current = min(self._scene_elapsed_ms, ORIGIN_SCENES[self._scene_index].duration_ms)
        total = sum(scene.duration_ms for scene in ORIGIN_SCENES)
        self.story_progress.setValue(int((completed + current) * 1000 / total))

    def _previous_scene(self) -> None:
        if self._scene_index > 0:
            self._render_scene(self._scene_index - 1)

    def _next_scene(self) -> None:
        if self._scene_index >= len(ORIGIN_SCENES) - 1:
            self.close()
            return
        self._render_scene(self._scene_index + 1)

    def _skip_to_finale(self) -> None:
        self._render_scene(len(ORIGIN_SCENES) - 1)

    def _toggle_pause(self, paused: bool) -> None:
        self.pause_button.setText("RESUME" if paused else "PAUSE")
        if paused:
            self._scene_timer.stop()
        else:
            self._last_scene_tick = time.monotonic()
            if self._scene_running:
                self._scene_timer.start()

    def _toggle_sound(self, enabled: bool) -> None:
        self._sound_enabled = bool(enabled)
        self.sound_button.setText("SOUND ON" if enabled else "SOUND OFF")
        if enabled:
            self._media_player.play()
        else:
            self._media_player.pause()

    def _set_reduced_effects(self, enabled: bool) -> None:
        self._reduced_motion = bool(enabled)
        self._cosmic_background.set_reduced_motion(self._reduced_motion)
        self.portal.set_reduced_motion(self._reduced_motion)
        if enabled and self._portal_timer.isActive():
            self._portal_timer.stop()
            self._progress = 1.0
            self.portal.set_progress(1.0)
            self.title_effect.setOpacity(1.0)
            self.message_effect.setOpacity(1.0)
            self._begin_story()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._portal_timer.stop()
        self._scene_timer.stop()
        self._media_player.stop()
        super().closeEvent(event)


class PlaceholderPage(QWidget):
    def __init__(self, eyebrow: str, title: str, detail: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.addStretch()
        eye = QLabel(eyebrow)
        eye.setObjectName("Eyebrow")
        heading = QLabel(title)
        heading.setObjectName("Title")
        copy = QLabel(detail)
        copy.setObjectName("Muted")
        copy.setWordWrap(True)
        layout.addWidget(eye)
        layout.addWidget(heading)
        layout.addWidget(copy)
        layout.addStretch(2)


class UpdateCheckSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)


class UpdateCheckWorker(ManagedRunnable):
    def __init__(self, service: DesktopUpdateService, channel: str) -> None:
        super().__init__()
        self.service = service
        self.channel = channel
        self.signals = UpdateCheckSignals()

    def execute(self) -> None:
        try:
            self.signals.completed.emit(self.service.check(self.channel))
        except Exception as exc:  # surfaced as a bounded, non-authorizing status
            self.signals.failed.emit(str(exc))


class UpdateStageSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    progress = Signal(int)


class UpdateStageWorker(ManagedRunnable):
    def __init__(
        self,
        service: DesktopUpdateService,
        candidate: DesktopUpdateCandidate,
        destination: Path,
    ) -> None:
        super().__init__()
        self.service = service
        self.candidate = candidate
        self.destination = destination
        self.signals = UpdateStageSignals()
        self._cancel_requested = Event()

    def cancel(self) -> None:
        self._cancel_requested.set()

    def execute(self) -> None:
        progress = CoalescedProgress(self.signals.progress.emit)

        def publish(done: int, total: int) -> None:
            value = measured_percent(done, total)
            if value is not None:
                # Transfer completion is not operation completion: the signed
                # receipt must still be persisted and reloaded successfully.
                progress(min(99, value))

        try:
            staged = self.service.stage(
                self.candidate,
                self.destination,
                progress=publish,
                should_cancel=self._cancel_requested.is_set,
            )
            progress(100)
            self.signals.completed.emit(staged)
        except DesktopUpdateCancelled:
            self.signals.cancelled.emit()
        except Exception as exc:  # surfaced without granting install authority
            self.signals.failed.emit(str(exc))


class SettingsDialog(QDialog):
    def __init__(
        self,
        workspace: Path,
        settings: AppSettings,
        parent: QWidget | None = None,
        update_service: DesktopUpdateService | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("ROMVERSE Settings")
        self.setMinimumWidth(680)
        self.resize(780, 760)
        self._settings = settings
        self._update_service = update_service
        self._update_worker: UpdateCheckWorker | None = None
        self._update_stage_worker: UpdateStageWorker | None = None
        self._update_candidate: DesktopUpdateCandidate | None = None
        self._staged_update: StagedDesktopUpdate | None = None
        self._update_destination = workspace / "desktop-updates"
        self._close_after_update_cancel = False
        layout = QVBoxLayout(self)
        title = QLabel("Command Deck Settings")
        title.setObjectName("Title")
        layout.addWidget(title)
        subtitle = QLabel("Changes apply to this running session and remain Guardian-safe.")
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        form_host = QWidget()
        form = QFormLayout(form_host)
        form.setContentsMargins(0, 0, 10, 0)
        self.experience_mode = QComboBox()
        self.experience_mode.addItem(
            "Guided Mode · ROMVERSE Arcana",
            ExperienceMode.GUIDED.value,
        )
        self.experience_mode.addItem(
            "Expert Mode · Architect workspace",
            ExperienceMode.EXPERT.value,
        )
        selected_mode = self.experience_mode.findData(settings.experience_mode.value)
        self.experience_mode.setCurrentIndex(max(0, selected_mode))
        form.addRow("Experience", self.experience_mode)
        self.experience_note = QLabel()
        self.experience_note.setObjectName("Muted")
        self.experience_note.setWordWrap(True)
        form.addRow("Mode behavior", self.experience_note)
        self.experience_mode.currentIndexChanged.connect(self._update_experience_note)
        self._update_experience_note()
        self.desktop_theme = QComboBox()
        for theme, (label, _override) in DESKTOP_THEMES.items():
            self.desktop_theme.addItem(label, theme.value)
        selected_theme = self.desktop_theme.findData(settings.desktop_theme.value)
        self.desktop_theme.setCurrentIndex(max(0, selected_theme))
        self.desktop_theme.setToolTip(
            "Choose a visual identity. Themes change presentation only; projects, evidence, "
            "Guardian, and phone authority remain unchanged."
        )
        form.addRow("Desktop theme", self.desktop_theme)
        self.interval = QSpinBox()
        self.interval.setRange(3, 300)
        self.interval.setValue(settings.scan_interval_seconds)
        self.interval.setSuffix(" seconds")
        form.addRow("Device scan interval", self.interval)
        self.online_intelligence = QCheckBox("Use verified online diagnostics and sources")
        self.online_intelligence.setChecked(settings.online_intelligence_enabled)
        self.online_intelligence.setToolTip(
            "Controls every optional online diagnostic/source connection, including the header "
            "reachability monitor and official Android ID refresh. Existing verified local "
            "evidence remains available read-only when disabled."
        )
        form.addRow("Online intelligence", self.online_intelligence)
        self.community_research = QCheckBox("Include community reports as guidance only")
        self.community_research.setChecked(settings.community_research_enabled)
        form.addRow("Community research", self.community_research)
        self.synapse_contributions = QCheckBox(
            "Prepare privacy-scrubbed verified outcomes for Synapse contribution"
        )
        self.synapse_contributions.setChecked(settings.synapse_contributions_enabled)
        form.addRow("Synapse contributions", self.synapse_contributions)
        self.auto_tools = QCheckBox("Acquire hash-verified build tools when required")
        self.auto_tools.setChecked(settings.auto_download_verified_tools)
        form.addRow("Forge Arsenal", self.auto_tools)
        self.desktop_notifications = QCheckBox("Show milestone and attention notifications")
        self.desktop_notifications.setChecked(settings.desktop_notifications_enabled)
        self.desktop_notifications.setToolTip(
            "Show non-blocking ROMVERSE alerts in the app, or through the desktop when ROMVERSE is in the background."
        )
        form.addRow("Notifications", self.desktop_notifications)
        self.reduced_motion = QCheckBox("Reduce decorative motion and rare space events")
        self.reduced_motion.setChecked(settings.reduced_motion)
        form.addRow("Accessibility", self.reduced_motion)

        backup_row = QHBoxLayout()
        self.backup_directory = QLineEdit(settings.backup_directory)
        self.backup_directory.setPlaceholderText("Use the ROMVERSE workspace backup vault")
        choose_backup = QPushButton("Choose …")
        choose_backup.clicked.connect(self._choose_backup_directory)
        backup_row.addWidget(self.backup_directory, 1)
        backup_row.addWidget(choose_backup)
        form.addRow("Local backup destination", backup_row)

        self.members_issuer = QLineEdit(settings.members_issuer)
        self.members_issuer.setPlaceholderText("Official HTTPS issuer supplied by RadForge Labs")
        form.addRow("Members issuer", self.members_issuer)
        self.members_client_id = QLineEdit(settings.members_client_id)
        self.members_client_id.setPlaceholderText("Public OAuth device client ID")
        form.addRow("Members client ID", self.members_client_id)
        workspace_label = QLabel(str(workspace))
        workspace_label.setObjectName("Muted")
        workspace_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Workspace", workspace_label)
        guardian = QLabel("Active · read-only policy")
        guardian.setObjectName("Good")
        form.addRow("Guardian", guardian)
        privacy = QLabel("Enabled · serials masked in UI and exports")
        privacy.setObjectName("Good")
        form.addRow("Device privacy", privacy)
        provider_keys = QLabel("Server-side only · provider keys are never stored in Studio")
        provider_keys.setObjectName("Good")
        form.addRow("AI credentials", provider_keys)
        ai_policy = QLabel("Locked · no public AI provider or client-side usage service")
        ai_policy.setObjectName("Muted")
        form.addRow("AI usage policy", ai_policy)
        notifications = QLabel(
            "Available · foreground alerts stay inside ROMVERSE; background alerts use the "
            "desktop notification area when supported"
        )
        notifications.setObjectName("Muted")
        notifications.setWordWrap(True)
        form.addRow("Notification delivery", notifications)
        self.update_channel = QComboBox()
        self.update_channel.addItem("Stable releases", "stable")
        self.update_channel.addItem("Preview release candidates", "preview")
        selected_channel = self.update_channel.findData(settings.update_channel)
        self.update_channel.setCurrentIndex(max(0, selected_channel))
        self.update_channel.currentIndexChanged.connect(self._update_channel_changed)
        form.addRow("Update channel", self.update_channel)
        update_row = QVBoxLayout()
        self.update_status = QLabel()
        self.update_status.setObjectName("Muted")
        self.update_status.setWordWrap(True)
        self.check_updates_button = QPushButton("Check for signed update")
        configured = bool(update_service is not None and update_service.trust.configured)
        self.check_updates_button.setEnabled(configured)
        self.check_updates_button.setToolTip(
            "Checks signed metadata only. ROMVERSE never installs an update automatically."
            if configured
            else "A production publisher key and signed release channel have not been packaged yet."
        )
        self.check_updates_button.clicked.connect(self._check_for_update)
        if configured:
            self.update_status.setText(
                "Ready · checks require the packaged publisher key, an exact signed channel, "
                "a newer compatible version, and one matching platform artifact. Installation "
                "is never automatic."
            )
        else:
            reason = (
                update_service.trust.reason
                if update_service is not None
                else "Publisher trust is unavailable in this build."
            )
            self.update_status.setText(
                f"Verification and safe staging are ready · {reason} No update will be trusted "
                "until the production public key and signed channel are packaged by RadForge Labs."
            )
        update_row.addWidget(self.update_status)
        update_row.addWidget(self.check_updates_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.update_progress = QProgressBar()
        self.update_progress.setRange(0, 100)
        self.update_progress.setValue(0)
        self.update_progress.setFormat("%p% downloaded and verified")
        self.update_progress.setAccessibleName("Signed desktop update progress")
        self.update_progress.setVisible(False)
        update_row.addWidget(self.update_progress)
        update_actions = QHBoxLayout()
        self.stage_update_button = QPushButton("Download & verify signed update")
        self.stage_update_button.setVisible(False)
        self.stage_update_button.clicked.connect(self._stage_update)
        update_actions.addWidget(self.stage_update_button)
        self.open_staged_update_button = QPushButton("Open verified download folder")
        self.open_staged_update_button.setVisible(False)
        self.open_staged_update_button.clicked.connect(self._open_staged_update)
        update_actions.addWidget(self.open_staged_update_button)
        update_actions.addStretch(1)
        update_row.addLayout(update_actions)
        form.addRow("Application updates", update_row)
        destructive = QLabel("Locked · explicit approval required; bootloader relock forbidden")
        destructive.setObjectName("Good")
        form.addRow("Guardian invariants", destructive)
        form_scroll = QScrollArea()
        form_scroll.setObjectName("SettingsScroll")
        form_scroll.setWidgetResizable(True)
        form_scroll.setFrameShape(QFrame.Shape.NoFrame)
        form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        form_scroll.setWidget(form_host)
        layout.addWidget(form_scroll, 1)
        self.form_scroll = form_scroll
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _choose_backup_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Choose local backup destination",
            self.backup_directory.text() or str(Path.home()),
        )
        if selected:
            self.backup_directory.setText(selected)

    def _update_experience_note(self) -> None:
        mode = ExperienceMode(self.experience_mode.currentData())
        if mode is ExperienceMode.GUIDED:
            message = (
                "ROMVERSE Arcana keeps the next safe action prominent and folds away specialist "
                "surfaces until the workflow needs them. Projects and evidence stay unchanged."
            )
        else:
            message = (
                "Architect workspace reveals Command Console, ROMVERSE Nexus, and Forge Arsenal. "
                "Guided Guardian sequencing is off after explicit risk acceptance. Exact target, "
                "artifact-integrity, and command-validity checks remain active."
            )
        self.experience_note.setText(message)

    def accept(self) -> None:
        selected = ExperienceMode(self.experience_mode.currentData())
        if (
            selected is ExperienceMode.EXPERT
            and self._settings.experience_mode is not ExperienceMode.EXPERT
            and not confirm_expert_mode(self)
        ):
            guided = self.experience_mode.findData(ExperienceMode.GUIDED.value)
            self.experience_mode.setCurrentIndex(max(0, guided))
            return
        super().accept()

    @Slot()
    def _check_for_update(self) -> None:
        if self._update_service is None or self._update_worker is not None:
            return
        self._update_candidate = None
        self._staged_update = None
        self.stage_update_button.setVisible(False)
        self.open_staged_update_button.setVisible(False)
        self.update_progress.setVisible(False)
        self.update_channel.setEnabled(False)
        self.check_updates_button.setEnabled(False)
        self.update_status.setText(
            "Checking the signed release channel without downloading or installing an update…"
        )
        worker = UpdateCheckWorker(
            self._update_service,
            str(self.update_channel.currentData()),
        )
        self._update_worker = worker
        worker.signals.completed.connect(self._update_check_completed)
        worker.signals.failed.connect(self._update_check_failed)
        start_background(worker)

    @Slot(object)
    def _update_check_completed(self, candidate: DesktopUpdateCandidate) -> None:
        self._update_worker = None
        self.update_channel.setEnabled(True)
        self.check_updates_button.setEnabled(True)
        if candidate.available and candidate.artifact is not None:
            self._update_candidate = candidate
            self.update_status.setText(
                f"Verified signed update available · ROMVERSE {candidate.manifest.version} · "
                f"{candidate.artifact.platform} · {human_bytes(candidate.artifact.size_bytes)}. "
                "Downloading requires confirmation; installation remains a separate manual step "
                "and cannot change Android-device authority."
            )
            self.stage_update_button.setText("Download & verify signed update")
            self.stage_update_button.setEnabled(True)
            self.stage_update_button.setVisible(True)
        else:
            self._update_candidate = None
            self.update_status.setText(
                f"ROMVERSE {candidate.current_version} is current on this signed channel."
            )

    @Slot(str)
    def _update_check_failed(self, message: str) -> None:
        self._update_worker = None
        self._update_candidate = None
        self.update_channel.setEnabled(True)
        self.check_updates_button.setEnabled(True)
        detail = " ".join(str(message).replace("\x00", " ").split())[:400]
        self.update_status.setText(
            f"Update check stopped safely · {detail or 'signed release evidence was unavailable'}"
        )

    @Slot()
    def _stage_update(self) -> None:
        if self._update_stage_worker is not None:
            self._cancel_update_stage()
            return
        candidate = self._update_candidate
        service = self._update_service
        if service is None or candidate is None or candidate.artifact is None:
            self.update_status.setText(
                "Download stopped safely · check the signed release channel again first."
            )
            return
        artifact = candidate.artifact
        answer = QMessageBox.question(
            self,
            "Download verified ROMVERSE update?",
            f"ROMVERSE {candidate.manifest.version}\n"
            f"{artifact.platform} · {human_bytes(artifact.size_bytes)}\n\n"
            f"Save to:\n{self._update_destination}\n\n"
            "ROMVERSE will download and verify the signed size, SHA-256, publisher identity, "
            "and private staging receipt. It will not run an installer, replace this app, "
            "change the workspace, or communicate with an Android device.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            self.update_status.setText(
                "Download cancelled before it started · no update files were created."
            )
            return
        self._staged_update = None
        self.update_channel.setEnabled(False)
        self.check_updates_button.setEnabled(False)
        self.open_staged_update_button.setVisible(False)
        self.stage_update_button.setText("Cancel download")
        self.stage_update_button.setEnabled(True)
        self.update_progress.setRange(0, 0)
        self.update_progress.setVisible(True)
        self.update_status.setText(
            "Downloading into private staging storage and verifying every byte… "
            "No installer or Android-device action can start from this step."
        )
        worker = UpdateStageWorker(service, candidate, self._update_destination)
        self._update_stage_worker = worker
        worker.signals.progress.connect(self._update_stage_progress)
        worker.signals.completed.connect(
            lambda result, active=worker: self._update_stage_completed(active, result)
        )
        worker.signals.failed.connect(
            lambda message, active=worker: self._update_stage_failed(active, message)
        )
        worker.signals.cancelled.connect(lambda active=worker: self._update_stage_cancelled(active))
        start_background(worker)

    @Slot(int)
    def _update_stage_progress(self, percent: int) -> None:
        if self._update_stage_worker is None:
            return
        self.update_progress.setRange(0, 100)
        self.update_progress.setValue(max(0, min(100, int(percent))))

    def _update_stage_completed(
        self,
        worker: UpdateStageWorker,
        result: object,
    ) -> None:
        if self._update_stage_worker is not worker:
            return
        candidate = self._update_candidate
        artifact = candidate.artifact if candidate is not None else None
        expected_root = self._update_destination.absolute()
        expected_release = expected_root / candidate.manifest.release_id if candidate else None
        valid = bool(
            isinstance(result, StagedDesktopUpdate)
            and candidate is not None
            and artifact is not None
            and result.release_id == candidate.manifest.release_id
            and result.version == candidate.manifest.version
            and result.channel == candidate.manifest.channel
            and result.platform == artifact.platform
            and result.sha256 == artifact.sha256
            and result.size_bytes == artifact.size_bytes
            and result.execution_authority == "none"
            and result.automatic_install is False
            and result.artifact_path == expected_release / artifact.file_name
            and result.receipt_path == expected_release / "staged-update.romverse"
            and result.artifact_path.is_file()
            and result.receipt_path.is_file()
        )
        self._update_stage_worker = None
        if not valid:
            self._finish_update_stage_failure(
                "verified staging did not return the exact expected evidence"
            )
            return
        self._staged_update = result
        self.update_progress.setRange(0, 100)
        self.update_progress.setValue(100)
        self.update_channel.setEnabled(True)
        self.check_updates_button.setEnabled(True)
        self.stage_update_button.setText("Verified update staged")
        self.stage_update_button.setEnabled(False)
        self.open_staged_update_button.setVisible(True)
        self.update_status.setText(
            f"Signed update downloaded and verified · {result.artifact_path.name} · SHA-256 "
            f"{result.sha256[:16]}… · private receipt saved. Installation has not run."
        )
        if self._close_after_update_cancel:
            self._close_after_update_cancel = False
            super().reject()

    def _update_stage_failed(self, worker: UpdateStageWorker, message: str) -> None:
        if self._update_stage_worker is not worker:
            return
        self._update_stage_worker = None
        detail = " ".join(str(message).replace("\x00", " ").split())[:400]
        self._finish_update_stage_failure(
            detail or "signed artifact or staging evidence was unavailable"
        )

    def _finish_update_stage_failure(self, detail: str) -> None:
        self._staged_update = None
        self.update_progress.setVisible(False)
        self.update_channel.setEnabled(True)
        self.check_updates_button.setEnabled(True)
        self.stage_update_button.setText("Download & verify signed update")
        self.stage_update_button.setEnabled(self._update_candidate is not None)
        self.update_status.setText(f"Update download stopped safely · {detail}")
        if self._close_after_update_cancel:
            self._close_after_update_cancel = False
            super().reject()

    def _cancel_update_stage(self) -> None:
        worker = self._update_stage_worker
        if worker is None:
            return
        worker.cancel()
        self.stage_update_button.setText("Cancelling download…")
        self.stage_update_button.setEnabled(False)
        self.update_status.setText(
            "Cancelling safely and removing any incomplete private download…"
        )

    def _update_stage_cancelled(self, worker: UpdateStageWorker) -> None:
        if self._update_stage_worker is not worker:
            return
        self._update_stage_worker = None
        self._staged_update = None
        self.update_progress.setVisible(False)
        self.update_channel.setEnabled(True)
        self.check_updates_button.setEnabled(True)
        self.stage_update_button.setText("Download & verify signed update")
        self.stage_update_button.setEnabled(self._update_candidate is not None)
        self.update_status.setText(
            "Update download cancelled safely · no incomplete artifact or receipt was retained."
        )
        if self._close_after_update_cancel:
            self._close_after_update_cancel = False
            super().reject()

    @Slot()
    def _open_staged_update(self) -> None:
        staged = self._staged_update
        if staged is None:
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(staged.artifact_path.parent))):
            self.update_status.setText(
                f"The verified update remains staged at {staged.artifact_path.parent}, but the "
                "desktop could not open that folder automatically. Installation has not run."
            )

    @Slot()
    def _update_channel_changed(self) -> None:
        if self._update_worker is not None or self._update_stage_worker is not None:
            return
        self._update_candidate = None
        self._staged_update = None
        self.stage_update_button.setVisible(False)
        self.open_staged_update_button.setVisible(False)
        self.update_progress.setVisible(False)
        if self._update_service is not None and self._update_service.trust.configured:
            self.update_status.setText(
                "Release channel changed · check its signed metadata before downloading anything."
            )

    def reject(self) -> None:
        if self._update_stage_worker is not None:
            self._close_after_update_cancel = True
            self._cancel_update_stage()
            return
        super().reject()

    def values(self) -> AppSettings:
        return AppSettings(
            schema_version=5,
            onboarding_complete=self._settings.onboarding_complete,
            workspace_path=self._settings.workspace_path,
            experience_mode=ExperienceMode(self.experience_mode.currentData()),
            desktop_theme=DesktopTheme(self.desktop_theme.currentData()),
            scan_interval_seconds=self.interval.value(),
            mask_device_serials=True,
            online_intelligence_enabled=self.online_intelligence.isChecked(),
            community_research_enabled=self.community_research.isChecked(),
            auto_download_verified_tools=self.auto_tools.isChecked(),
            synapse_contributions_enabled=self.synapse_contributions.isChecked(),
            ai_daily_reasoning_budget=self._settings.ai_daily_reasoning_budget,
            ai_concurrency_limit=self._settings.ai_concurrency_limit,
            desktop_notifications_enabled=self.desktop_notifications.isChecked(),
            reduced_motion=self.reduced_motion.isChecked(),
            backup_directory=self.backup_directory.text().strip(),
            update_channel=str(self.update_channel.currentData()),
            members_issuer=self.members_issuer.text().strip(),
            members_client_id=self.members_client_id.text().strip(),
        )


class TermsDialog(QDialog):
    """Readable local view of the packaged Terms draft; it records no acceptance."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        document = load_terms_document()
        self.document = document
        self.setWindowTitle("ROMVERSE Terms & Conditions")
        self.setModal(False)
        self.resize(860, 720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        self.status = QLabel(
            f"{document.status}\nVersion {document.version}\nSHA-256 {document.sha256}"
        )
        self.status.setObjectName("Warning")
        self.status.setAccessibleName("Terms document review status and integrity digest")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(62)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)

        self.content = QTextBrowser()
        self.content.setObjectName("TermsDocument")
        self.content.setAccessibleName("ROMVERSE Terms and Conditions internal review draft")
        self.content.setOpenExternalLinks(False)
        self.content.setMarkdown(document.text)
        layout.addWidget(self.content, 1)

        boundary = QLabel(
            "Reading this internal draft records no acceptance and grants no device, build, "
            "account, billing, network, or execution authority."
        )
        boundary.setObjectName("Muted")
        boundary.setWordWrap(True)
        layout.addWidget(boundary)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)


class PrivacyDialog(QDialog):
    """Layered local Privacy view with the current user-controlled network state."""

    def __init__(
        self,
        settings: AppSettings | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        document = load_privacy_document()
        self.document = document
        self.settings = settings or AppSettings()
        self.setWindowTitle("ROMVERSE Privacy & Data")
        self.setModal(False)
        self.resize(900, 760)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        self.status = QLabel(
            f"{document.status}\nVersion {document.version}\nSHA-256 {document.sha256}"
        )
        self.status.setObjectName("Warning")
        self.status.setAccessibleName("Privacy document review status and integrity digest")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(62)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)

        summary = QFrame()
        summary.setObjectName("PrivacySummary")
        summary_layout = QGridLayout(summary)
        summary_layout.setContentsMargins(14, 12, 14, 12)
        summary_layout.setHorizontalSpacing(18)
        summary_layout.setVerticalSpacing(7)
        summary_title = QLabel("CURRENT DESKTOP DATA CONTROLS")
        summary_title.setObjectName("Eyebrow")
        summary_layout.addWidget(summary_title, 0, 0, 1, 2)
        community_value = (
            "ENABLED"
            if (
                self.settings.online_intelligence_enabled
                and self.settings.community_research_enabled
            )
            else "PAUSED • LOCAL ONLY"
            if self.settings.community_research_enabled
            else "DISABLED"
        )
        controls = (
            ("Device identifiers", "MASKED + LOCAL PSEUDONYM", True),
            (
                "Official online research",
                "ENABLED" if self.settings.online_intelligence_enabled else "LOCAL ONLY",
                not self.settings.online_intelligence_enabled,
            ),
            (
                "Community research",
                community_value,
                not (
                    self.settings.online_intelligence_enabled
                    and self.settings.community_research_enabled
                ),
            ),
            (
                "Synapse contribution",
                "OPTED IN • SERVICE UNAVAILABLE"
                if self.settings.synapse_contributions_enabled
                else "OFF",
                not self.settings.synapse_contributions_enabled,
            ),
            (
                "Verified tool downloads",
                "ENABLED" if self.settings.auto_download_verified_tools else "ASK / MANUAL",
                not self.settings.auto_download_verified_tools,
            ),
        )
        self.control_values: dict[str, QLabel] = {}
        for row, (label, value, privacy_preferred) in enumerate(controls, start=1):
            name = QLabel(label)
            name.setObjectName("Muted")
            current = QLabel(value)
            current.setObjectName("Good" if privacy_preferred else "Warning")
            current.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            current.setAccessibleName(f"{label}: {value}")
            summary_layout.addWidget(name, row, 0)
            summary_layout.addWidget(current, row, 1)
            self.control_values[label] = current
        summary_note = QLabel(
            "These are the settings in force when this window opened. This view is read-only: "
            "it does not scan, upload, contribute, pair, download, or change a setting."
        )
        summary_note.setObjectName("Muted")
        summary_note.setWordWrap(True)
        summary_layout.addWidget(summary_note, len(controls) + 1, 0, 1, 2)
        layout.addWidget(summary)

        self.content = QTextBrowser()
        self.content.setObjectName("PrivacyDocument")
        self.content.setAccessibleName("ROMVERSE Privacy Notice internal review draft")
        self.content.setOpenExternalLinks(False)
        self.content.setMarkdown(document.text)
        layout.addWidget(self.content, 1)

        boundary = QLabel(
            "Reading this internal draft records no acceptance, changes no privacy setting, "
            "starts no network request, and grants no device or execution authority."
        )
        boundary.setObjectName("Muted")
        boundary.setWordWrap(True)
        layout.addWidget(boundary)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)


class AboutPage(QWidget):
    logo_double_clicked = Signal()
    route_requested = Signal(str)
    knowledge_article_requested = Signal(str)

    def __init__(
        self,
        logo_path: Path,
        brand_path: Path | None = None,
        app_icon_path: Path | None = None,
        workspace: Path | None = None,
        reduced_motion: bool = False,
        privacy_settings: AppSettings | None = None,
    ) -> None:
        super().__init__()
        self._privacy_settings = privacy_settings or AppSettings()
        self._origin_store = OriginDiscoveryStore(workspace) if workspace is not None else None
        self._origin_state_path = (
            self._origin_store.path if self._origin_store is not None else None
        )
        self._origin_state_error = ""
        try:
            self.origin_discovered = self._origin_store.load() if self._origin_store else False
        except OriginDiscoveryError as exc:
            self.origin_discovered = False
            self._origin_state_error = str(exc)
        self.last_origin_was_first = False
        self._compact_brand_layout: bool | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        self.about_scroll = scroll
        scroll.setObjectName("AboutScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        canvas = QWidget()
        self.about_canvas = canvas
        canvas.setObjectName("ScrollContent")
        outer = QHBoxLayout(canvas)
        self.about_outer = outer
        outer.setContentsMargins(30, 26, 30, 30)
        outer.setSpacing(0)
        outer.addStretch(1)
        content = QWidget()
        self.about_content = content
        content.setObjectName("AboutContent")
        content.setMaximumWidth(1120)
        layout = QVBoxLayout(content)
        self.about_layout = layout
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        outer.addWidget(content, 30)
        outer.addStretch(1)
        scroll.setWidget(canvas)
        root.addWidget(scroll)

        eyebrow = QLabel("PRODUCT FAMILY  •  RADFORGE LABS")
        eyebrow.setObjectName("Eyebrow")
        eyebrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(eyebrow)
        heading = QLabel("ABOUT ROMVERSE & ITS CREATOR")
        heading.setObjectName("Title")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)
        brand_intro = QLabel(
            "The product, the independent studio, the person behind the vision, and every verified place to follow the journey."
        )
        brand_intro.setObjectName("Muted")
        brand_intro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_intro.setWordWrap(True)
        layout.addWidget(brand_intro)

        self.brand_stage = QFrame()
        self.brand_stage.setObjectName("RadForgeStudioIdentity")
        self.brand_stage.setStyleSheet(
            "QFrame#RadForgeStudioIdentity { background: rgba(5, 9, 20, 224); "
            "border: 1px solid rgba(122, 108, 230, 145); "
            "border-top: 2px solid rgba(99, 236, 248, 205); border-radius: 18px; }"
        )
        self.brand_stage_layout = QHBoxLayout(self.brand_stage)
        self.brand_stage_layout.setContentsMargins(22, 14, 22, 14)
        self.brand_stage_layout.setSpacing(12)

        romverse_identity = QVBoxLayout()
        romverse_label = QLabel("ROMVERSE PRODUCT IDENTITY")
        romverse_label.setObjectName("Eyebrow")
        romverse_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo = WebsiteBrandCrest(
            brand_path or app_icon_path or logo_path,
            reduced_motion=reduced_motion,
        )
        self.logo.setObjectName("AboutLogo")
        self.logo.setAccessibleName("Official ROMVERSE website logo")
        self.logo.double_clicked.connect(self._request_origin)
        romverse_identity.addWidget(romverse_label)
        romverse_identity.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignHCenter)
        self.brand_stage_layout.addLayout(romverse_identity, 5)

        self.brand_bridge = QFrame()
        self.brand_bridge.setObjectName("BrandBridge")
        bridge_layout = QVBoxLayout(self.brand_bridge)
        bridge_layout.setContentsMargins(8, 8, 8, 8)
        bridge_layout.addStretch(1)
        created = QLabel("CREATED BY")
        created.setAlignment(Qt.AlignmentFlag.AlignCenter)
        created.setStyleSheet(
            "color:#FFAA45; font-size:10px; font-weight:850; letter-spacing:1.5px;"
        )
        bridge_mark = QLabel("◇")
        bridge_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bridge_mark.setStyleSheet("color:#63ECF8; font-size:28px;")
        handoff = QLabel("A RADFORGE\nLABS PROJECT")
        handoff.setAlignment(Qt.AlignmentFlag.AlignCenter)
        handoff.setStyleSheet("color:#C9D6F1; font-size:9px; font-weight:750; letter-spacing:1px;")
        bridge_layout.addWidget(created)
        bridge_layout.addWidget(bridge_mark)
        bridge_layout.addWidget(handoff)
        bridge_layout.addStretch(1)
        self.brand_stage_layout.addWidget(self.brand_bridge, 1)

        studio_identity = QVBoxLayout()
        studio_heading = QLabel("OFFICIAL STUDIO IDENTITY")
        studio_heading.setObjectName("RadForgeStudioHeading")
        studio_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        studio_heading.setStyleSheet(
            "color: #FFAA45; font-size: 11px; font-weight: 850; letter-spacing: 2px;"
        )
        self.radforge_company_logo = QLabel()
        self.radforge_company_logo.setObjectName("RadForgeOfficialLogo")
        self.radforge_company_logo.setAccessibleName("Official RadForge Labs company logo")
        self.radforge_company_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.radforge_company_logo.setStyleSheet("background: transparent; border: 0;")
        radforge_logo_resource = files("romverse.assets").joinpath(
            "radforge-labs-official-logo-transparent.png"
        )
        with as_file(radforge_logo_resource) as radforge_logo_path:
            self._radforge_logo_source = QPixmap(str(radforge_logo_path))
        studio_glow = QGraphicsDropShadowEffect(self.radforge_company_logo)
        studio_glow.setColor(QColor(255, 130, 24, 115))
        studio_glow.setBlurRadius(22)
        studio_glow.setOffset(0, 2)
        self.radforge_company_logo.setGraphicsEffect(studio_glow)
        studio_identity.addWidget(studio_heading)
        studio_identity.addWidget(
            self.radforge_company_logo,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
        self.brand_stage_layout.addLayout(studio_identity, 5)
        layout.addWidget(self.brand_stage)

        self.founder_spotlight = QFrame()
        self.founder_spotlight.setObjectName("FounderSpotlight")
        founder_layout = QHBoxLayout(self.founder_spotlight)
        founder_layout.setContentsMargins(24, 20, 24, 20)
        founder_layout.setSpacing(20)
        founder_monogram = QLabel("SR")
        founder_monogram.setObjectName("FounderMonogram")
        founder_monogram.setFixedSize(86, 86)
        founder_monogram.setAlignment(Qt.AlignmentFlag.AlignCenter)
        founder_monogram.setAccessibleName("SteveTheRad creator monogram")
        founder_layout.addWidget(founder_monogram)
        founder_copy = QVBoxLayout()
        founder_eyebrow = QLabel("FROM THE FOUNDER  •  STEVETHERAD")
        founder_eyebrow.setObjectName("Eyebrow")
        founder_title = QLabel("Built from curiosity. Driven by possibility.")
        founder_title.setObjectName("HeroTitle")
        founder_message = QLabel(
            "I created ROMVERSE to make Android ROM development more understandable, more capable, and safer—without taking away the freedom that makes Android special. Whether you are here to build, test, learn, help, or simply explore: thank you for becoming part of its story."
        )
        founder_message.setObjectName("Muted")
        founder_message.setWordWrap(True)
        founder_copy.addWidget(founder_eyebrow)
        founder_copy.addWidget(founder_title)
        founder_copy.addWidget(founder_message)
        founder_layout.addLayout(founder_copy, 1)
        founder_signature = QLabel("STEVE\nFOUNDER & CREATOR\nRADFORGE LABS")
        founder_signature.setObjectName("FounderSignature")
        founder_signature.setAlignment(Qt.AlignmentFlag.AlignCenter)
        founder_layout.addWidget(founder_signature)
        layout.addWidget(self.founder_spotlight)

        mission = QLabel(
            "BUILD  •  OPTIMIZE  •  PERFECT\n"
            "A safe, intelligent workspace for shaping the Android universe."
        )
        mission.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mission.setStyleSheet(
            "background: rgba(12, 17, 48, 190); border: 1px solid rgba(99, 236, 248, 90); "
            "border-radius: 13px; padding: 14px 24px; color: #BFCBFF; "
            "font-size: 14px; letter-spacing: 1px;"
        )
        mission.setWordWrap(True)
        mission.setToolTip("ROMVERSE unites device care, diagnostics, repair, and creation.")
        layout.addWidget(mission)

        build_facts = QHBoxLayout()
        build_facts.setSpacing(10)
        for label, value, accent in (
            ("DESKTOP BUILD", DISPLAY_VERSION, "#63ECF8"),
            ("CHANNEL", "INTERNAL ALPHA", "#B45CFF"),
            ("SAFETY", "GUARDIAN BOUNDARY", "#72FFB2"),
            ("ABOUT AUTHORITY", "NAVIGATION ONLY", "#FFB454"),
        ):
            fact = QFrame()
            fact.setObjectName("TelemetryTile")
            fact_layout = QVBoxLayout(fact)
            fact_layout.setContentsMargins(12, 9, 12, 9)
            fact_label = QLabel(label)
            fact_label.setObjectName("TelemetryLabel")
            fact_value = QLabel(value)
            fact_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fact_value.setStyleSheet(
                f"color:{accent}; font-size:11px; font-weight:800; letter-spacing:0.6px;"
            )
            fact_value.setAccessibleName(f"{label.title()}: {value}")
            fact_layout.addWidget(fact_label)
            fact_layout.addWidget(fact_value)
            build_facts.addWidget(fact, 1)
        layout.addLayout(build_facts)

        self.runtime_panel = QFrame()
        self.runtime_panel.setObjectName("AboutEvidencePanel")
        runtime_layout = QVBoxLayout(self.runtime_panel)
        runtime_layout.setContentsMargins(18, 16, 18, 17)
        runtime_layout.setSpacing(12)
        runtime_header = QHBoxLayout()
        runtime_header.setSpacing(12)
        runtime_heading = QVBoxLayout()
        runtime_heading.setSpacing(3)
        runtime_eyebrow = QLabel("ROMVERSE NOW  •  VERIFIED LOCAL EVIDENCE")
        runtime_eyebrow.setObjectName("Eyebrow")
        runtime_title = QLabel("One universe, measured by its real systems")
        runtime_title.setObjectName("SectionTitle")
        runtime_intro = QLabel(
            "These facts are recalculated from this workspace. They are never demo counters, "
            "cloud estimates, or execution approvals."
        )
        runtime_intro.setObjectName("Muted")
        runtime_intro.setWordWrap(True)
        runtime_heading.addWidget(runtime_eyebrow)
        runtime_heading.addWidget(runtime_title)
        runtime_heading.addWidget(runtime_intro)
        runtime_header.addLayout(runtime_heading, 1)
        self.runtime_scope = QLabel("AWAITING WORKSPACE EVIDENCE")
        self.runtime_scope.setObjectName("Warning")
        self.runtime_scope.setAccessibleName("About page local evidence status")
        self.runtime_scope.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.runtime_scope.setWordWrap(True)
        self.runtime_scope.setMinimumWidth(210)
        runtime_header.addWidget(self.runtime_scope)
        runtime_layout.addLayout(runtime_header)

        evidence_grid = QGridLayout()
        evidence_grid.setContentsMargins(0, 0, 0, 0)
        evidence_grid.setHorizontalSpacing(10)
        evidence_grid.setVerticalSpacing(10)
        evidence_specs = (
            (
                "guardian",
                "GUARDIAN EVIDENCE",
                "Current audit and approval integrity from Guardian Core",
                (("guardian_core", "Open Guardian Core"),),
            ),
            (
                "device",
                "DEVICE INTELLIGENCE",
                "Registry and official identity evidence",
                (("device_atlas", "Open Device Atlas"),),
            ),
            (
                "knowledge",
                "KNOWLEDGE MEMORY",
                "Searchable guidance and known-safe fixes",
                (("archives", "Open Archives"),),
            ),
            (
                "build",
                "BUILD WORKSPACE",
                "Projects plus the current host tool inventory",
                (("rom_studio", "ROM Studio"), ("forge_arsenal", "Forge Arsenal")),
            ),
            (
                "live",
                "EVIDENCE LEDGER",
                "Genuine subsystem outcomes and active missions",
                (("live_console", "Live Console"),),
            ),
        )
        self.evidence_cards: dict[str, QFrame] = {}
        self.evidence_values: dict[str, QLabel] = {}
        self.evidence_states: dict[str, QLabel] = {}
        self.evidence_details: dict[str, QLabel] = {}
        self.evidence_buttons: dict[str, QPushButton] = {}
        for index, (key, title, subtitle, actions) in enumerate(evidence_specs):
            card = QFrame()
            card.setObjectName("AboutEvidenceCard")
            card.setProperty("evidenceState", "waiting")
            card.setMinimumHeight(172)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(15, 13, 15, 13)
            card_layout.setSpacing(5)
            card_title = QLabel(title)
            card_title.setObjectName("AboutEvidenceTitle")
            card_subtitle = QLabel(subtitle)
            card_subtitle.setObjectName("Muted")
            card_subtitle.setWordWrap(True)
            value = QLabel("AWAITING LOCAL READ")
            value.setObjectName("AboutEvidenceValue")
            value.setAccessibleName(f"{title.title()} verified value")
            value.setWordWrap(True)
            state = QLabel("NOT YET REFRESHED")
            state.setObjectName("Warning")
            state.setAccessibleName(f"{title.title()} evidence state")
            state.setWordWrap(True)
            detail = QLabel("Open About inside a ROMVERSE workspace to calculate this evidence.")
            detail.setObjectName("Muted")
            detail.setWordWrap(True)
            card_layout.addWidget(card_title)
            card_layout.addWidget(card_subtitle)
            card_layout.addWidget(value)
            card_layout.addWidget(state)
            card_layout.addWidget(detail, 1)
            actions_layout = QHBoxLayout()
            actions_layout.setContentsMargins(0, 4, 0, 0)
            actions_layout.setSpacing(7)
            for route, label in actions:
                button = QPushButton(f"{label}  →")
                button.setObjectName("AboutEvidenceAction")
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setAccessibleName(f"Open {feature(route).title} from About evidence")
                button.clicked.connect(
                    lambda _checked=False, destination=route: self.route_requested.emit(destination)
                )
                actions_layout.addWidget(button)
                self.evidence_buttons[route] = button
            actions_layout.addStretch(1)
            card_layout.addLayout(actions_layout)
            if key == "guardian":
                card.setMinimumHeight(150)
                evidence_grid.addWidget(card, 0, 0, 1, 2)
            else:
                slot = index - 1
                evidence_grid.addWidget(card, 1 + slot // 2, slot % 2)
            self.evidence_cards[key] = card
            self.evidence_values[key] = value
            self.evidence_states[key] = state
            self.evidence_details[key] = detail
        evidence_grid.setColumnStretch(0, 1)
        evidence_grid.setColumnStretch(1, 1)
        runtime_layout.addLayout(evidence_grid)

        evidence_footer = QHBoxLayout()
        evidence_boundary = QLabel(
            "READ-ONLY OBSERVATION  •  Feature pages own their evidence  •  Guardian owns approvals"
        )
        evidence_boundary.setObjectName("Muted")
        evidence_boundary.setWordWrap(True)
        evidence_footer.addWidget(evidence_boundary, 1)
        self.evidence_guide = QPushButton("How this evidence works  →")
        self.evidence_guide.setObjectName("AboutEvidenceGuide")
        self.evidence_guide.setAccessibleName(
            "Open the verified Archives guide for About runtime evidence"
        )
        self.evidence_guide.clicked.connect(
            lambda: self.knowledge_article_requested.emit("about-live-evidence-unavailable")
        )
        evidence_footer.addWidget(self.evidence_guide)
        runtime_layout.addLayout(evidence_footer)
        layout.addWidget(self.runtime_panel)

        platform_panel = QFrame()
        platform_panel.setObjectName("AboutPanel")
        platform_panel.setStyleSheet(
            "QFrame#AboutPanel { background: rgba(9, 14, 38, 210); "
            "border: 1px solid rgba(113, 130, 220, 120); border-radius: 13px; }"
        )
        platforms = QHBoxLayout(platform_panel)
        platforms.setContentsMargins(24, 12, 24, 12)
        platforms.setSpacing(18)
        platform_svgs = {
            "Windows": b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96"><path fill="#09A9E8" d="M6 16 45 11v35H6zM51 10l39-5v41H51zM6 51h39v35L6 80zM51 51h39v41l-39-6z"/></svg>""",
            "Linux": b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96"><ellipse cx="48" cy="53" rx="27" ry="34" fill="#171B2C"/><ellipse cx="48" cy="58" rx="19" ry="27" fill="#F6F8FF"/><circle cx="39" cy="29" r="11" fill="#F6F8FF"/><circle cx="57" cy="29" r="11" fill="#F6F8FF"/><circle cx="40" cy="30" r="4" fill="#171B2C"/><circle cx="56" cy="30" r="4" fill="#171B2C"/><path d="M36 37q12-13 24 0l-12 9z" fill="#F5A900"/><ellipse cx="29" cy="84" rx="16" ry="6" fill="#F5A900"/><ellipse cx="67" cy="84" rx="16" ry="6" fill="#F5A900"/></svg>""",
            "Android": b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96"><g fill="#A4D65E" stroke="#A4D65E" stroke-width="3" stroke-linecap="round"><path d="M29 39a19 19 0 0 1 38 0v6H29z"/><rect x="31" y="43" width="34" height="25" rx="4"/><rect x="20" y="44" width="8" height="22" rx="4"/><rect x="68" y="44" width="8" height="22" rx="4"/><rect x="36" y="65" width="8" height="18" rx="4"/><rect x="52" y="65" width="8" height="18" rx="4"/><path d="M35 23l-5-8m31 8 5-8" fill="none"/></g><circle cx="40" cy="35" r="2" fill="#101735"/><circle cx="56" cy="35" r="2" fill="#101735"/></svg>""",
        }
        for name in ("Windows", "Linux", "Android"):
            platform = QWidget()
            item = QHBoxLayout(platform)
            item.setContentsMargins(0, 0, 0, 0)
            item.setSpacing(8)
            glyph = QLabel()
            glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
            glyph.setFixedSize(42, 42)
            glyph.setAccessibleName(f"{name} platform")
            pixmap = QPixmap()
            pixmap.loadFromData(platform_svgs[name], "SVG")
            glyph.setPixmap(
                pixmap.scaled(
                    38,
                    38,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            label = QLabel(name)
            label.setObjectName("Muted")
            item.addStretch(1)
            item.addWidget(glyph)
            item.addWidget(label)
            item.addStretch(1)
            platforms.addWidget(platform, 1)
        layout.addWidget(platform_panel)

        story = QGridLayout()
        story.setContentsMargins(0, 0, 0, 0)
        story.setHorizontalSpacing(12)
        story.setVerticalSpacing(12)
        story_items = (
            (
                "WHAT IS ROMVERSE?",
                "An intelligent Android ROM development, diagnostics, optimization, and recovery "
                "ecosystem. Desktop, Companion, evidence-backed safety, and verified device "
                "knowledge work together without hiding uncertainty.",
                "#63ECF8",
            ),
            (
                "THE ROMVERSE PROMISE",
                "Real progress—never simulated success.\nEvidence before assumptions—unknown stays "
                "unconfirmed.\nYour device, your decision.\nGuardian protects high-consequence "
                "workflows.\nPrivacy by design.",
                "#B45CFF",
            ),
            (
                "CREATED BY",
                "SteveTheRad  •  Founding Creator\nFounder & Creator of ROMVERSE\nA RadForge "
                "Labs Project",
                "#D9B6FF",
            ),
            (
                "RADFORGE LABS",
                "Building ambitious software differently. ROMVERSE is created with a philosophy "
                "of experimentation, craftsmanship, technical truth, and user-focused engineering.",
                "#72FFB2",
            ),
        )
        for index, (title, body, accent) in enumerate(story_items):
            card = QFrame()
            card.setObjectName("AboutStoryCard")
            card.setStyleSheet(
                "QFrame#AboutStoryCard { background: rgba(7, 12, 31, 218); "
                "border: 1px solid rgba(113, 130, 220, 105); "
                f"border-top: 2px solid {accent}; border-radius: 13px; }}"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 15, 18, 16)
            card_layout.setSpacing(7)
            card_title = QLabel(title)
            card_title.setStyleSheet(
                f"color: {accent}; font-size: 12px; font-weight: 800; letter-spacing: 1px;"
            )
            card_body = QLabel(body)
            card_body.setWordWrap(True)
            card_body.setStyleSheet("color: #D8E2F8; font-size: 13px;")
            card_layout.addWidget(card_title)
            card_layout.addWidget(card_body, 1)
            story.addWidget(card, index // 2, index % 2)
        layout.addLayout(story)

        self.origin_replay = QPushButton("🌌  EXPERIENCE THE ORIGIN AGAIN")
        self.origin_replay.setObjectName("OriginReplay")
        self.origin_replay.setAccessibleName("Replay ROMVERSE The Origin")
        self.origin_replay.setCursor(Qt.CursorShape.PointingHandCursor)
        self.origin_replay.setMinimumHeight(48)
        self.origin_replay.setVisible(self.origin_discovered)
        self.origin_replay.clicked.connect(self._replay_origin)
        self.origin_replay.setStyleSheet(
            "QPushButton { background: rgba(27, 14, 55, 220); color: #E3C5FF; "
            "border: 1px solid rgba(180, 92, 255, 170); border-radius: 11px; "
            "font-size: 12px; font-weight: 800; letter-spacing: 1px; padding: 10px 18px; }"
            "QPushButton:hover { border-color: #63ECF8; color: white; }"
        )
        layout.addWidget(self.origin_replay)
        self.origin_state_note = QLabel(self._origin_state_error)
        self.origin_state_note.setObjectName("Danger")
        self.origin_state_note.setAccessibleName("Origin discovery local storage status")
        self.origin_state_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.origin_state_note.setWordWrap(True)
        self.origin_state_note.setVisible(bool(self._origin_state_error))
        layout.addWidget(self.origin_state_note)

        websites_heading = QLabel("OFFICIAL WEBSITES")
        websites_heading.setObjectName("Eyebrow")
        websites_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(websites_heading)
        websites_intro = QLabel(
            "Verified destinations only—ROMVERSE never invents or guesses a creator or community account."
        )
        websites_intro.setObjectName("Muted")
        websites_intro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        websites_intro.setWordWrap(True)
        layout.addWidget(websites_intro)

        website_grid = QGridLayout()
        website_grid.setContentsMargins(0, 0, 0, 0)
        website_grid.setHorizontalSpacing(12)
        website_grid.setVerticalSpacing(12)

        def official_website_card(
            object_name: str,
            title: str,
            domain: str,
            description: str,
            url: str,
            accent: str,
            icon_svg: bytes,
            accessible_name: str,
        ) -> tuple[QFrame, QLabel, QPushButton]:
            card = QFrame()
            card.setObjectName(object_name)
            card.setMinimumHeight(118)
            card.setStyleSheet(
                f"QFrame#{object_name} {{ background: rgba(8, 13, 36, 224); "
                "border: 1px solid rgba(113, 130, 220, 125); "
                f"border-top: 2px solid {accent}; border-radius: 13px; }}"
            )
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(18, 16, 16, 16)
            card_layout.setSpacing(14)

            icon = QLabel()
            icon.setFixedSize(44, 44)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon.setAccessibleName(title)
            icon.setStyleSheet("background: transparent; border: 0;")
            pixmap = QPixmap()
            pixmap.loadFromData(icon_svg, "SVG")
            icon.setPixmap(
                pixmap.scaled(
                    42,
                    42,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            card_layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)

            copy = QVBoxLayout()
            copy.setContentsMargins(0, 0, 0, 0)
            copy.setSpacing(3)
            website_title = QLabel(title)
            website_title.setStyleSheet("color: #EDF4FF; font-size: 14px; font-weight: 800;")
            website_domain = QLabel(domain)
            website_domain.setStyleSheet(f"color: {accent}; font-size: 12px; font-weight: 750;")
            website_description = QLabel(description)
            website_description.setObjectName("Muted")
            website_description.setWordWrap(True)
            copy.addWidget(website_title)
            copy.addWidget(website_domain)
            copy.addWidget(website_description)
            card_layout.addLayout(copy, 1)

            open_button = QPushButton("Visit  →")
            open_button.setCursor(Qt.CursorShape.PointingHandCursor)
            open_button.setMinimumSize(94, 44)
            open_button.setAccessibleName(accessible_name)
            open_button.clicked.connect(
                lambda _checked=False, destination=url, destination_title=title: (
                    self._open_external(destination, destination_title)
                )
            )
            open_button.setStyleSheet(
                "QPushButton { background: rgba(20, 29, 65, 210); color: #EFF7FF; "
                f"font-weight: 800; border: 1px solid {accent}; border-radius: 9px; "
                "padding: 8px 14px; }"
                "QPushButton:hover { background: rgba(35, 48, 94, 230); color: white; "
                "border-color: #FFFFFF; }"
                "QPushButton:focus { border: 2px solid #FFFFFF; }"
            )
            card_layout.addWidget(open_button, 0, Qt.AlignmentFlag.AlignVCenter)
            return card, icon, open_button

        romverse_website_svg = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">
          <defs><linearGradient id="g" x1="5" y1="5" x2="43" y2="43"><stop stop-color="#B45CFF"/><stop offset="1" stop-color="#63ECF8"/></linearGradient></defs>
          <circle cx="24" cy="24" r="19" fill="#101735" stroke="url(#g)" stroke-width="2"/>
          <path d="M8 24h32M24 5c6 5 9 11 9 19s-3 14-9 19M24 5c-6 5-9 11-9 19s3 14 9 19M11 15h26M11 33h26" fill="none" stroke="url(#g)" stroke-width="1.7" stroke-linecap="round"/>
          <circle cx="36" cy="11" r="3" fill="#FFFFFF"/><path d="m36 4 1.2 4.8L42 10l-4.8 1.2L36 16l-1.2-4.8L30 10l4.8-1.2z" fill="#63ECF8"/>
        </svg>"""
        radforge_website_svg = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">
          <defs><linearGradient id="f" x1="7" y1="6" x2="41" y2="42"><stop stop-color="#72FFB2"/><stop offset="1" stop-color="#63ECF8"/></linearGradient></defs>
          <path d="m24 4 17 10v20L24 44 7 34V14z" fill="#101735" stroke="url(#f)" stroke-width="2"/>
          <path d="M16 34V14h9.2c5.1 0 8.2 2.8 8.2 7.1 0 3.1-1.6 5.4-4.5 6.5L34 34h-5.3l-4.4-5.7h-3.5V34zm4.8-9.8h4c2.4 0 3.7-1 3.7-2.9 0-2-1.3-2.9-3.7-2.9h-4z" fill="url(#f)"/>
        </svg>"""
        (
            romverse_website_card,
            self.romverse_website_icon,
            self.romverse_website_link,
        ) = official_website_card(
            "RomverseWebsiteCard",
            "ROMVERSE",
            "romverse.app",
            "Product home, development updates, and the growing ROMVERSE ecosystem.",
            ROMVERSE_WEBSITE_URL,
            "#B45CFF",
            romverse_website_svg,
            "Open the official ROMVERSE website",
        )
        (
            radforge_website_card,
            self.radforge_website_icon,
            self.radforge_website_link,
        ) = official_website_card(
            "RadForgeWebsiteCard",
            "RADFORGE LABS",
            "radforgelabs.com",
            "Meet the independent studio and the philosophy behind ROMVERSE.",
            RADFORGE_LABS_URL,
            "#72FFB2",
            radforge_website_svg,
            "Open the official RadForge Labs website",
        )
        website_grid.addWidget(romverse_website_card, 0, 0)
        website_grid.addWidget(radforge_website_card, 0, 1)
        website_grid.setColumnStretch(0, 1)
        website_grid.setColumnStretch(1, 1)
        layout.addLayout(website_grid)

        connect_heading = QLabel("CONNECT WITH ROMVERSE")
        connect_heading.setObjectName("Eyebrow")
        connect_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(connect_heading)
        facebook_card = QWidget()
        facebook_card.setObjectName("FacebookCard")
        facebook_card.setMinimumHeight(78)
        facebook_card.setStyleSheet(
            "QWidget#FacebookCard { background: rgba(9, 14, 38, 220); "
            "border: 1px solid rgba(88, 141, 235, 145); "
            "border-left: 3px solid #1877F2; border-radius: 13px; }"
        )
        facebook_card_layout = QHBoxLayout(facebook_card)
        facebook_card_layout.setContentsMargins(18, 13, 16, 13)
        facebook_card_layout.setSpacing(14)
        self.facebook_icon = QLabel()
        self.facebook_icon.setFixedSize(36, 36)
        self.facebook_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.facebook_icon.setAccessibleName("Facebook")
        self.facebook_icon.setStyleSheet("background: transparent; border: 0;")
        facebook_svg = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="10" fill="#1877F2"/>
            <path fill="#FFFFFF" d="M13.6 22v-7.1h2.4l.4-2.9h-2.8v-1.8c0-.84.24-1.41 1.45-1.41h1.53V6.2c-.27-.04-1.18-.12-2.25-.12-2.23 0-3.76 1.36-3.76 3.86V12H8.05v2.9h2.52V22z"/>
        </svg>"""
        facebook_pixmap = QPixmap()
        facebook_pixmap.loadFromData(facebook_svg, "SVG")
        self.facebook_icon.setPixmap(
            facebook_pixmap.scaled(
                34,
                34,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        facebook_card_layout.addWidget(self.facebook_icon)
        card_text = QVBoxLayout()
        card_text.setContentsMargins(0, 0, 0, 0)
        card_text.setSpacing(2)
        facebook_title = QLabel("Facebook")
        facebook_title.setStyleSheet("color: #EDF4FF; font-size: 14px; font-weight: 750;")
        facebook_subtitle = QLabel("Follow ROMVERSEOfficial")
        facebook_subtitle.setObjectName("Muted")
        card_text.addWidget(facebook_title)
        card_text.addWidget(facebook_subtitle)
        facebook_card_layout.addLayout(card_text, 1)
        self.facebook_link = QPushButton("Open page  →")
        self.facebook_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.facebook_link.setMinimumHeight(42)
        self.facebook_link.setAccessibleName("Open ROMVERSE on Facebook")
        self.facebook_link.clicked.connect(
            lambda: self._open_external(FACEBOOK_URL, "ROMVERSE on Facebook")
        )
        self.facebook_link.setStyleSheet(
            "background: rgba(17, 34, 70, 190); color: #DDF8FF; font-weight: 750; "
            "border: 1px solid rgba(99, 236, 248, 145); border-radius: 9px; "
            "padding: 8px 14px;"
        )
        facebook_card_layout.addWidget(self.facebook_link)
        layout.addWidget(facebook_card)
        reddit_card = QWidget()
        reddit_card.setObjectName("RedditCard")
        reddit_card.setMinimumHeight(78)
        reddit_card.setStyleSheet(
            "QWidget#RedditCard { background: rgba(9, 14, 38, 220); "
            "border: 1px solid rgba(255, 109, 58, 145); "
            "border-left: 3px solid #FF4500; border-radius: 13px; }"
        )
        reddit_layout = QHBoxLayout(reddit_card)
        reddit_layout.setContentsMargins(18, 13, 16, 13)
        reddit_layout.setSpacing(14)
        self.reddit_icon = QLabel()
        self.reddit_icon.setFixedSize(36, 36)
        self.reddit_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reddit_icon.setAccessibleName("Reddit")
        reddit_svg = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="10" fill="#FF4500"/>
          <path fill="#fff" d="M18.7 11.2a1.7 1.7 0 0 0-2.9-1.2c-1-.6-2.2-1-3.6-1.1l.7-3.1 2.2.5a1.3 1.3 0 1 0 .2-.9l-2.7-.6a.5.5 0 0 0-.6.4l-.8 3.7c-1.3.1-2.5.5-3.4 1.1a1.7 1.7 0 1 0-1.9 2.7v.5c0 2.4 2.7 4.3 6.1 4.3s6.1-1.9 6.1-4.3v-.5c.4-.3.6-.9.6-1.5Zm-10.2 1.4a1.1 1.1 0 1 1 2.2 0 1.1 1.1 0 0 1-2.2 0Zm6.2 2.5c-.7.7-1.6 1-2.7 1s-2-.3-2.7-1a.4.4 0 0 1 .6-.6c.5.5 1.2.7 2.1.7s1.6-.2 2.1-.7a.4.4 0 1 1 .6.6Zm-1.4-2.5a1.1 1.1 0 1 1 2.2 0 1.1 1.1 0 0 1-2.2 0Z"/>
        </svg>"""
        reddit_pixmap = QPixmap()
        reddit_pixmap.loadFromData(reddit_svg, "SVG")
        self.reddit_icon.setPixmap(
            reddit_pixmap.scaled(
                34,
                34,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        reddit_layout.addWidget(self.reddit_icon)
        reddit_text = QVBoxLayout()
        reddit_text.setContentsMargins(0, 0, 0, 0)
        reddit_text.setSpacing(2)
        reddit_title = QLabel("Reddit")
        reddit_title.setStyleSheet("color: #EDF4FF; font-size: 14px; font-weight: 750;")
        reddit_subtitle = QLabel("Follow u/ROMVERSE")
        reddit_subtitle.setObjectName("Muted")
        reddit_text.addWidget(reddit_title)
        reddit_text.addWidget(reddit_subtitle)
        reddit_layout.addLayout(reddit_text, 1)
        self.reddit_link = QPushButton("Open profile  →")
        self.reddit_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reddit_link.setMinimumHeight(42)
        self.reddit_link.setAccessibleName("Open ROMVERSE on Reddit")
        self.reddit_link.clicked.connect(
            lambda: self._open_external(REDDIT_URL, "ROMVERSE on Reddit")
        )
        self.reddit_link.setStyleSheet(
            "background: rgba(57, 25, 18, 205); color: #FFF0EA; font-weight: 750; "
            "border: 1px solid rgba(255, 109, 58, 170); border-radius: 9px; "
            "padding: 8px 14px;"
        )
        reddit_layout.addWidget(self.reddit_link)
        layout.addWidget(reddit_card)
        github_card = QWidget()
        github_card.setObjectName("GitHubCard")
        github_card.setMinimumHeight(78)
        github_card.setStyleSheet(
            "QWidget#GitHubCard { background: rgba(9, 14, 38, 220); "
            "border: 1px solid rgba(181, 193, 216, 135); "
            "border-left: 3px solid #D8E2F8; border-radius: 13px; }"
        )
        github_layout = QHBoxLayout(github_card)
        github_layout.setContentsMargins(18, 13, 16, 13)
        github_layout.setSpacing(14)
        self.github_icon = QLabel()
        self.github_icon.setFixedSize(36, 36)
        self.github_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.github_icon.setAccessibleName("GitHub")
        self.github_icon.setStyleSheet("background: transparent; border: 0;")
        github_svg = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
          <rect x="2" y="2" width="20" height="20" rx="6" fill="#D8E2F8"/>
          <path d="M8 7.5v5.2c0 1.7 1.3 3 3 3h2m3-8.2v3.2c0 1.7-1.3 3-3 3h-2" fill="none" stroke="#111827" stroke-width="1.8" stroke-linecap="round"/>
          <circle cx="8" cy="6.8" r="1.8" fill="#6D4AFF"/><circle cx="16" cy="6.8" r="1.8" fill="#24C7D9"/><circle cx="11" cy="16" r="1.8" fill="#A855F7"/>
        </svg>"""
        github_pixmap = QPixmap()
        github_pixmap.loadFromData(github_svg, "SVG")
        self.github_icon.setPixmap(
            github_pixmap.scaled(
                34,
                34,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        github_layout.addWidget(self.github_icon)
        github_text = QVBoxLayout()
        github_text.setContentsMargins(0, 0, 0, 0)
        github_text.setSpacing(2)
        github_title = QLabel("GitHub")
        github_title.setStyleSheet("color: #EDF4FF; font-size: 14px; font-weight: 750;")
        github_subtitle = QLabel("SteveTheRad / ROMVERSE source and releases")
        github_subtitle.setObjectName("Muted")
        github_text.addWidget(github_title)
        github_text.addWidget(github_subtitle)
        github_layout.addLayout(github_text, 1)
        self.github_link = QPushButton("Open repository  →")
        self.github_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.github_link.setMinimumHeight(42)
        self.github_link.setAccessibleName("Open the official ROMVERSE GitHub repository")
        self.github_link.clicked.connect(
            lambda: self._open_external(GITHUB_URL, "ROMVERSE on GitHub")
        )
        self.github_link.setStyleSheet(
            "background: rgba(28, 35, 54, 205); color: #F3F6FF; font-weight: 750; "
            "border: 1px solid rgba(216, 226, 248, 160); border-radius: 9px; "
            "padding: 8px 14px;"
        )
        github_layout.addWidget(self.github_link)
        layout.addWidget(github_card)
        self.external_status = QLabel()
        self.external_status.setObjectName("Warning")
        self.external_status.setAccessibleName("Official link opening status")
        self.external_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.external_status.setWordWrap(True)
        self.external_status.setVisible(False)
        layout.addWidget(self.external_status)
        family_heading = QLabel("ONE UNIVERSE  •  EVERY MISSION CONNECTED")
        family_heading.setObjectName("Eyebrow")
        family_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(family_heading)
        family = QGridLayout()
        family.setContentsMargins(0, 0, 0, 0)
        family.setHorizontalSpacing(12)
        family.setVerticalSpacing(12)
        family_items = (
            ("ROMVERSE", "Build and customize", "#C45CFF", "rom_studio"),
            ("GUARDIAN", "Safety and protection", "#63ECF8", "guardian_core"),
            ("COMPANION", "Desktop and phone connection", "#D26BFF", "companion_link"),
            ("GALAXY", "Community and discovery", "#63ECF8", "galaxy"),
        )
        self.family_buttons: dict[str, QPushButton] = {}
        for index, (name, detail, color, route) in enumerate(family_items):
            card = QPushButton(f"{name}\n{detail}\nOPEN  →")
            card.setObjectName("AboutFamilyButton")
            card.setMinimumHeight(78)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setAccessibleName(f"Open {name}: {detail}")
            card.clicked.connect(
                lambda _checked=False, destination=route: self.route_requested.emit(destination)
            )
            card.setStyleSheet(
                "QPushButton { background: rgba(9, 14, 38, 210); border: 1px solid rgba(113, 130, 220, 120); "
                f"border-top: 2px solid {color}; border-radius: 11px; padding: 11px 10px; "
                f"color: {color}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}"
                "QPushButton:hover { background: rgba(22, 26, 62, 232); border-color: #FFFFFF; color: #FFFFFF; }"
                "QPushButton:focus { border: 2px solid #FFFFFF; }"
            )
            family.addWidget(card, index // 2, index % 2)
            self.family_buttons[route] = card
        layout.addLayout(family)
        trust = QLabel(
            "TRUST & TRANSPARENCY\nGuardian never treats unknown evidence as healthy, never "
            "simulates success, and never authorizes bootloader relocking. Membership, public "
            "services, automatic updates, and community activity are shown only when genuinely available."
        )
        trust.setWordWrap(True)
        trust.setAlignment(Qt.AlignmentFlag.AlignCenter)
        trust.setStyleSheet(
            "background: rgba(7, 12, 31, 210); border: 1px solid rgba(99, 236, 248, 85); "
            "border-radius: 12px; padding: 15px 22px; color: #C9D6F1; font-size: 12px;"
        )
        layout.addWidget(trust)

        trust_dock = QFrame()
        trust_dock.setObjectName("AboutTrustDock")
        trust_dock_layout = QVBoxLayout(trust_dock)
        trust_dock_layout.setContentsMargins(18, 16, 18, 17)
        trust_dock_layout.setSpacing(11)
        trust_header = QHBoxLayout()
        trust_copy = QVBoxLayout()
        trust_eyebrow = QLabel("TRUST DOCK  •  LOCAL PROOF, NOT MARKETING LINKS")
        trust_eyebrow.setObjectName("Eyebrow")
        trust_title = QLabel("Privacy, licences, legal status, and release provenance")
        trust_title.setObjectName("SectionTitle")
        trust_detail = QLabel(
            "Read the packaged Terms and Privacy review drafts or open one exact ROMVERSE "
            "Archives record. This internal alpha has not issued effective public documents; "
            "legal approval, complete provider/contact details, third-party notices, and signed "
            "release binding remain release gates."
        )
        trust_detail.setObjectName("Muted")
        trust_detail.setWordWrap(True)
        trust_copy.addWidget(trust_eyebrow)
        trust_copy.addWidget(trust_title)
        trust_copy.addWidget(trust_detail)
        trust_header.addLayout(trust_copy, 1)
        self.legal_state = QLabel("INTERNAL ALPHA\nDRAFT TERMS + PRIVACY • LEGAL REVIEW REQUIRED")
        self.legal_state.setObjectName("Warning")
        self.legal_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.legal_state.setAccessibleName(
            "Internal alpha; draft Terms and Privacy Notice are included but remain unissued"
        )
        self.legal_state.setMinimumWidth(220)
        trust_header.addWidget(self.legal_state)
        trust_dock_layout.addLayout(trust_header)

        legal_actions = QHBoxLayout()
        legal_actions.setSpacing(10)
        self.terms_button = QPushButton("READ DRAFT TERMS & CONDITIONS  →")
        self.terms_button.setObjectName("AboutTermsAction")
        self.terms_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.terms_button.setAccessibleName(
            "Read the packaged ROMVERSE Terms and Conditions internal review draft"
        )
        self.terms_button.setToolTip(
            "Open the local versioned draft. Reading it records no contractual acceptance."
        )
        self.terms_button.clicked.connect(self._show_terms)
        legal_actions.addWidget(self.terms_button, 1)
        self.privacy_button = QPushButton("PRIVACY & DATA CONTROLS  →")
        self.privacy_button.setObjectName("AboutPrivacyAction")
        self.privacy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.privacy_button.setAccessibleName(
            "Read the packaged ROMVERSE Privacy Notice and current data-control state"
        )
        self.privacy_button.setToolTip(
            "Open a local read-only view. It changes no setting and starts no network request."
        )
        self.privacy_button.clicked.connect(self._show_privacy)
        legal_actions.addWidget(self.privacy_button, 1)
        trust_dock_layout.addLayout(legal_actions)

        trust_actions = QGridLayout()
        trust_actions.setContentsMargins(0, 0, 0, 0)
        trust_actions.setHorizontalSpacing(9)
        trust_actions.setVerticalSpacing(9)
        trust_specs = (
            (
                "desktop-legal-publication-boundary",
                "TERMS STATUS",
                "Draft included; legal review required",
                "caution",
            ),
            (
                "desktop-local-privacy-boundary",
                "PRIVACY BOUNDARY",
                "Local-first and setting-controlled",
                "verified",
            ),
            (
                "desktop-licence-notice-inventory",
                "LICENCES & NOTICES",
                "Source licence present; notices gated",
                "attention",
            ),
            (
                "desktop-release-provenance",
                "CHANGELOG & BUILD PROOF",
                "Installed artifact evidence required",
                "proof",
            ),
        )
        self.trust_buttons: dict[str, QPushButton] = {}
        for index, (key, title, state, kind) in enumerate(trust_specs):
            display_title = title.replace("&", "&&")
            button = QPushButton(f"{display_title}\n{state}\nOPEN VERIFIED RECORD  →")
            button.setObjectName("AboutTrustAction")
            button.setProperty("trustState", kind)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setAccessibleName(f"Open {title.title()} verified Archives record")
            button.setToolTip(
                "Open the exact local Archives record and retain a safe return path to About."
            )
            button.clicked.connect(
                lambda _checked=False, article_key=key: self.knowledge_article_requested.emit(
                    article_key
                )
            )
            trust_actions.addWidget(button, index // 2, index % 2)
            self.trust_buttons[key] = button
        trust_actions.setColumnStretch(0, 1)
        trust_actions.setColumnStretch(1, 1)
        trust_dock_layout.addLayout(trust_actions)
        layout.addWidget(trust_dock)

        thanks = QLabel(
            "Thank you for being part of ROMVERSE.\n\nWhether you're building your first ROM, "
            "developing your hundredth, testing a new device, helping another member or simply "
            "exploring what Android can become—you're part of the journey.\n\n— SteveTheRad\n27.08.2026"
        )
        thanks.setWordWrap(True)
        thanks.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thanks.setStyleSheet("color: #D9B6FF; font-size: 13px; padding: 18px;")
        layout.addWidget(thanks)
        footer = QLabel(
            "One membership. Every ROMVERSE experience included.\n"
            "Internal alpha  •  Proprietary source licence present  •  "
            "Public legal and signed-release pack still gated"
        )
        footer.setObjectName("Muted")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setWordWrap(True)
        layout.addWidget(footer)
        self._apply_brand_layout()
        self._update_about_minimum_height()

    def _show_terms(self) -> None:
        previous = getattr(self, "terms_dialog", None)
        if previous is not None:
            previous.close()
        self.terms_dialog = TermsDialog(self)
        self.terms_dialog.show()
        self.terms_dialog.raise_()
        self.terms_dialog.activateWindow()

    def _show_privacy(self) -> None:
        previous = getattr(self, "privacy_dialog", None)
        if previous is not None:
            previous.close()
        self.privacy_dialog = PrivacyDialog(self._privacy_settings, self)
        self.privacy_dialog.show()
        self.privacy_dialog.raise_()
        self.privacy_dialog.activateWindow()

    def set_privacy_settings(self, settings: AppSettings) -> None:
        """Refresh the snapshot used by the next read-only Privacy dialog."""

        self._privacy_settings = settings

    def set_runtime_evidence(self, evidence: AboutRuntimeEvidence) -> None:
        """Render only the current workspace facts supplied by the owning services."""

        all_current = (
            evidence.device_pack_issue_count == 0
            and evidence.catalog_valid
            and evidence.catalog_fresh
            and evidence.live_ledger_valid
            and evidence.guardian_verified
        )
        self.runtime_scope.setText(
            "READ-ONLY  •  CURRENT WORKSPACE  •  NO EXECUTION AUTHORITY"
            if all_current
            else "READ-ONLY  •  CURRENT WORKSPACE  •  EVIDENCE NEEDS ATTENTION"
        )
        self.runtime_scope.setObjectName("Good" if all_current else "Warning")
        self._repolish(self.runtime_scope)

        guardian_labels = {
            "unverified": "VERIFY REQUIRED",
            "review_due": "REVERIFY REQUIRED",
            "verifying": "VERIFYING",
            "verified": "INTEGRITY VERIFIED",
            "locked": "EXECUTION LOCKED",
            "failed": "VERIFY FAILED",
            "unavailable": "AUDIT UNAVAILABLE",
        }
        guardian_label = guardian_labels[evidence.guardian_state]
        guardian_kind = (
            "verified"
            if evidence.guardian_verified
            else (
                "unavailable"
                if evidence.guardian_state in {"locked", "failed", "unavailable"}
                else "attention"
            )
        )
        guardian_detail = evidence.guardian_detail.rstrip(". ")
        self._set_evidence_lane(
            "guardian",
            "AUDIT + APPROVAL EVIDENCE",
            guardian_label,
            f"{guardian_detail}. About observes this state only; Guardian Core owns verification, approvals, and every execution lock.",
            guardian_kind,
        )

        pack_noun = "PACK" if evidence.device_pack_count == 1 else "PACKS"
        if evidence.catalog_valid:
            device_value = (
                f"{evidence.device_pack_count} DEVICE {pack_noun}  •  "
                f"{evidence.catalog_entry_count:,} OFFICIAL IDS"
            )
            if evidence.device_pack_issue_count:
                device_state = "PACK REGISTRY NEEDS ATTENTION"
                device_kind = "attention"
            elif evidence.catalog_fresh:
                device_state = "CURRENT  •  INTEGRITY CHECKED"
                device_kind = "verified"
            else:
                device_state = "INTEGRITY CHECKED  •  REFRESH DUE"
                device_kind = "attention"
            issue_copy = (
                f"{evidence.device_pack_issue_count} rejected Pack "
                f"issue{'s' if evidence.device_pack_issue_count != 1 else ''}. "
                if evidence.device_pack_issue_count
                else "No Device Pack load issues. "
            )
            device_detail = (
                f"{issue_copy}{evidence.catalog_reason}. Identity evidence never grants build, "
                "flash, or execution authority."
            )
        else:
            device_value = (
                f"{evidence.device_pack_count} DEVICE {pack_noun}  •  ID CATALOG UNAVAILABLE"
            )
            device_state = "OFFICIAL ID EVIDENCE UNAVAILABLE"
            device_kind = "unavailable"
            device_detail = (
                f"{evidence.catalog_reason}. Device Packs remain visible, but ROMVERSE will not "
                "invent an official retail identity."
            )
        self._set_evidence_lane("device", device_value, device_state, device_detail, device_kind)

        guide_noun = "GUIDE" if evidence.archive_guide_count == 1 else "GUIDES"
        fix_noun = "FIX" if evidence.archive_known_fix_count == 1 else "FIXES"
        knowledge_kind = "verified" if evidence.archive_guide_count else "unavailable"
        self._set_evidence_lane(
            "knowledge",
            f"{evidence.archive_guide_count} VERIFIED {guide_noun}  •  "
            f"{evidence.archive_known_fix_count} KNOWN {fix_noun}",
            (
                f"SEARCHABLE  •  {evidence.archive_category_count} CATEGORIES"
                if evidence.archive_guide_count
                else "VERIFIED CATALOG UNAVAILABLE"
            ),
            (
                "Packaged Archives guidance is evidence-labelled. Learned outcomes remain "
                "correlation until a typed workflow verifies them."
                if evidence.archive_guide_count
                else "No validated packaged Archives catalog is available."
            ),
            knowledge_kind,
        )

        build_kind = (
            "verified"
            if evidence.tool_count and evidence.tool_ready_count == evidence.tool_count
            else "attention"
        )
        project_noun = "PROJECT" if evidence.project_count == 1 else "PROJECTS"
        self._set_evidence_lane(
            "build",
            f"{evidence.project_count} LOCAL {project_noun}  •  "
            f"{evidence.tool_ready_count}/{evidence.tool_count} HOST TOOLS READY",
            (
                "CURRENT HOST INVENTORY VERIFIED"
                if build_kind == "verified"
                else f"{evidence.tool_count - evidence.tool_ready_count} HOST TOOLS NEED ATTENTION"
            ),
            "Project manifests and executable checks are current. Exact compile requirements "
            "still come from the selected source-bound Device Pack.",
            build_kind,
        )

        if evidence.live_ledger_valid:
            event_noun = "EVENT" if evidence.live_event_count == 1 else "EVENTS"
            live_state = (
                "LEDGER INTEGRITY VERIFIED"
                if evidence.live_event_count
                else "VERIFIED  •  NO EVENTS YET"
            )
            live_value = (
                f"{evidence.live_event_count} GENUINE {event_noun}  •  "
                f"{evidence.live_active_count} ACTIVE"
            )
            live_detail = (
                "The privacy-redacted local ledger reports only outcomes written by producing "
                "subsystems; viewing it starts no mission."
            )
            live_kind = "verified"
        else:
            live_state = "LEDGER INTEGRITY NEEDS ATTENTION"
            live_value = "EVENT COUNTS UNAVAILABLE"
            live_detail = (
                "ROMVERSE rejected the local ledger, so About will not display untrusted event "
                "or progress counts. Open Live Console for the bounded error."
            )
            live_kind = "unavailable"
        self._set_evidence_lane("live", live_value, live_state, live_detail, live_kind)
        QTimer.singleShot(0, self._update_about_minimum_height)

    def _set_evidence_lane(
        self,
        key: str,
        value: str,
        state: str,
        detail: str,
        kind: str,
    ) -> None:
        card = self.evidence_cards[key]
        card.setProperty("evidenceState", kind)
        self.evidence_values[key].setText(value)
        self.evidence_states[key].setText(state)
        self.evidence_states[key].setObjectName(
            "Good" if kind == "verified" else "Danger" if kind == "unavailable" else "Warning"
        )
        self.evidence_details[key].setText(detail)
        for widget in (card, self.evidence_states[key]):
            self._repolish(widget)

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._apply_brand_layout()
        super().resizeEvent(event)

    def _apply_brand_layout(self) -> None:
        compact = self.width() < 960
        if self._compact_brand_layout is compact:
            return
        self._compact_brand_layout = compact
        logo_size = 220 if compact else 310
        company_width = 260 if compact else 400
        company_height = round(company_width * 0.638)
        self.logo.setFixedSize(logo_size, logo_size)
        self.brand_bridge.setFixedWidth(120 if compact else 110)
        self.radforge_company_logo.setFixedSize(company_width, company_height)
        self.radforge_company_logo.setPixmap(
            self._radforge_logo_source.scaled(
                company_width - 10,
                company_height - 8,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.brand_stage.setMinimumHeight(280 if compact else 360)
        QTimer.singleShot(0, self._update_about_minimum_height)

    def _update_about_minimum_height(self) -> None:
        self.about_layout.activate()
        required_height = self.about_layout.sizeHint().height()
        self.about_content.setMinimumHeight(required_height)
        margins = self.about_outer.contentsMargins()
        self.about_canvas.setMinimumHeight(required_height + margins.top() + margins.bottom())

    def _open_external(self, url: str, title: str) -> None:
        if QDesktopServices.openUrl(QUrl(url)):
            self.external_status.setVisible(False)
            return
        self.external_status.setText(
            f"Could not open {title} in the default browser. No Desktop or device state changed."
        )
        self.external_status.setVisible(True)

    def _request_origin(self) -> None:
        self.last_origin_was_first = not self.origin_discovered
        if self.last_origin_was_first:
            self.origin_discovered = True
            if self._origin_store is not None:
                try:
                    self._origin_store.discover()
                    self.origin_state_note.setVisible(False)
                except OriginDiscoveryError as exc:
                    self.origin_state_note.setText(
                        f"The Origin is available for this session, but its local discovery record could not be preserved: {exc}"
                    )
                    self.origin_state_note.setVisible(True)
            self.origin_replay.setVisible(True)
        self.logo_double_clicked.emit()

    def _replay_origin(self) -> None:
        self.last_origin_was_first = False
        self.logo_double_clicked.emit()


class CosmicBackground(QWidget):
    def __init__(self, logo_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._background = QPixmap()
        self._logo = QPixmap(str(logo_path))
        self._reduced_motion = False
        self._activity_state = "idle"
        self._shooting = False
        self._star_progress = 0.0
        self._star_start = QPointF()
        self._star_end = QPointF()
        self._star_timer = QTimer(self)
        self._star_timer.timeout.connect(self._start_shooting_star)
        self._star_timer.start(14000)
        self._star_animation = QTimer(self)
        self._star_animation.setInterval(40)
        self._star_animation.timeout.connect(self._advance_star)
        self._blackhole = False
        self._blackhole_progress = 0.0
        self._blackhole_center = QPointF()
        self._blackhole_timer = QTimer(self)
        self._blackhole_timer.timeout.connect(self._start_blackhole)
        self._blackhole_timer.start(22000)
        self._blackhole_animation = QTimer(self)
        self._blackhole_animation.setInterval(40)
        self._blackhole_animation.timeout.connect(self._advance_blackhole)
        self._ufo = False
        self._ufo_progress = 0.0
        self._ufo_start = QPointF()
        self._ufo_end = QPointF()
        self._ufo_timer = QTimer(self)
        self._ufo_timer.timeout.connect(self._start_ufo)
        self._ufo_timer.start(18000)
        self._ufo_animation = QTimer(self)
        self._ufo_animation.setInterval(45)
        self._ufo_animation.timeout.connect(self._advance_ufo)
        self._battle = False
        self._battle_progress = 0.0
        self._battle_timer = QTimer(self)
        self._battle_timer.setSingleShot(True)
        self._battle_timer.timeout.connect(self._start_battle)
        self._battle_animation = QTimer(self)
        self._battle_animation.setInterval(45)
        self._battle_animation.timeout.connect(self._advance_battle)
        self._schedule_battle(first=True)

    def set_reduced_motion(self, enabled: bool) -> None:
        """Apply accessibility motion policy immediately and reversibly."""

        self._reduced_motion = bool(enabled)
        if self._reduced_motion:
            for timer in (
                self._star_timer,
                self._star_animation,
                self._blackhole_timer,
                self._blackhole_animation,
                self._ufo_timer,
                self._ufo_animation,
                self._battle_timer,
                self._battle_animation,
            ):
                timer.stop()
            self._shooting = False
            self._blackhole = False
            self._ufo = False
            self._battle = False
            self.update()
            return
        if self.isVisible():
            self._star_timer.start(14000)
            self._blackhole_timer.start(22000)
            self._ufo_timer.start(18000)
            if not self._battle_timer.isActive():
                self._schedule_battle(first=True)

    @Slot(str)
    def set_activity_state(self, state: str) -> None:
        """Shift the ambient nebula only when Command Deck's real mission state changes."""

        normalized = str(state).strip().casefold()
        if normalized not in {"idle", "device", "running", "recovery", "attention"}:
            normalized = "idle"
        if normalized == self._activity_state:
            return
        self._activity_state = normalized
        self._background = QPixmap()
        self.update()

    def paintEvent(self, _event) -> None:
        if self._background.size() != self.size():
            self._render_background()
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._background)
        if self._shooting:
            point = self._star_start + (self._star_end - self._star_start) * self._star_progress
            direction = self._star_end - self._star_start
            # A compact, tapered comet reads as ambient space motion instead of
            # resembling a horizontal application progress indicator.
            for fraction, alpha, width in (
                (0.050, 42, 1.0),
                (0.033, 95, 1.4),
                (0.018, 175, 1.8),
            ):
                tail = point - direction * fraction
                pen = QPen(QColor(135, 222, 255, alpha), width)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLine(tail, point)
            painter.setPen(QColor(255, 255, 255, 230))
            painter.drawEllipse(point, 2.2, 2.2)
        if self._blackhole:
            self._draw_blackhole(painter)
        if self._ufo:
            self._draw_ufo(painter)
        if self._battle:
            self._draw_battle(painter)
        painter.end()

    def _draw_blackhole(self, painter: QPainter) -> None:
        center = self._blackhole_center
        progress = self._blackhole_progress
        radius = 24 + min(progress, 0.55) * 70
        painter.save()
        painter.setOpacity(0.7 * (1.0 - max(0.0, progress - 0.72) / 0.28))
        painter.setPen(QColor(168, 85, 247, 130))
        painter.drawEllipse(center, radius * 1.55, radius * 0.48)
        painter.setPen(QColor(40, 231, 245, 150))
        painter.drawEllipse(center, radius * 1.35, radius * 0.38)
        hole = QRadialGradient(center, radius * 0.9)
        hole.setColorAt(0.0, QColor(0, 0, 0, 245))
        hole.setColorAt(0.72, QColor(4, 5, 16, 230))
        hole.setColorAt(1.0, QColor(168, 85, 247, 0))
        painter.setBrush(hole)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, radius, radius)
        if progress > 0.32:
            icon_progress = min(1.0, (progress - 0.32) / 0.42)
            fade = 1.0 - max(0.0, progress - 0.82) / 0.18
            painter.setOpacity(icon_progress * max(0.0, fade))
            icon_size = 58
            icon = self._logo.scaled(
                icon_size,
                icon_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            launch = QPointF(icon_progress * 180, -icon_progress * 90)
            point = center + launch
            painter.setPen(QColor(170, 225, 255, 100))
            painter.drawLine(point - launch * 0.24, point)
            painter.drawPixmap(point - QPointF(icon.width() / 2, icon.height() / 2), icon)
        painter.restore()

    def _start_blackhole(self) -> None:
        if self._reduced_motion or self._blackhole or self.width() < 100:
            return
        self._blackhole = True
        self._blackhole_progress = 0.0
        self._blackhole_center = QPointF(
            random.uniform(self.width() * 0.5, self.width() * 0.84),
            random.uniform(self.height() * 0.2, self.height() * 0.72),
        )
        self._blackhole_animation.start()

    def _advance_blackhole(self) -> None:
        dirty = self._blackhole_dirty_region()
        self._blackhole_progress += 0.018
        if self._blackhole_progress >= 1.0:
            self._blackhole = False
            self._blackhole_animation.stop()
        self.update(dirty)

    def _start_shooting_star(self) -> None:
        if self._reduced_motion or self._shooting or self.width() < 100:
            return
        self._shooting = True
        self._star_progress = 0.0
        # Enter from above and travel on an unmistakably diagonal path. The old
        # near-horizontal route could look like a blue progress bar at the top of
        # every page for roughly one second.
        start_x = random.uniform(self.width() * 0.08, self.width() * 0.48)
        self._star_start = QPointF(start_x, -24)
        self._star_end = QPointF(
            start_x + random.uniform(self.width() * 0.30, self.width() * 0.54),
            random.uniform(self.height() * 0.38, self.height() * 0.64),
        )
        self._star_animation.start()
        self.update(self._star_dirty_region(self._star_progress))

    def _advance_star(self) -> None:
        dirty = self._star_dirty_region(self._star_progress)
        self._star_progress += 0.035
        if self._star_progress >= 1.0:
            self._shooting = False
            self._star_animation.stop()
        else:
            dirty = dirty.united(self._star_dirty_region(self._star_progress))
        self.update(dirty)

    def _draw_ufo(self, painter: QPainter) -> None:
        point = self._ufo_start + (self._ufo_end - self._ufo_start) * self._ufo_progress
        painter.save()
        painter.setOpacity(0.65)
        painter.setPen(QPen(QColor("#63ECF8"), 1.5))
        painter.setBrush(QColor(40, 231, 245, 45))
        painter.drawEllipse(point, 18, 5)
        painter.setBrush(QColor(168, 85, 247, 65))
        painter.drawEllipse(point + QPointF(0, -3), 8, 5)
        painter.setPen(QPen(QColor(170, 225, 255, 70), 1))
        painter.drawLine(point + QPointF(-11, 5), point + QPointF(-5, 13))
        painter.drawLine(point + QPointF(11, 5), point + QPointF(5, 13))
        painter.restore()

    def _start_ufo(self) -> None:
        if self._reduced_motion or self._ufo or self.width() < 100:
            return
        self._ufo = True
        self._ufo_progress = 0.0
        y = random.uniform(self.height() * 0.15, self.height() * 0.75)
        self._ufo_start = QPointF(-60, y)
        self._ufo_end = QPointF(self.width() + 80, y + random.uniform(-80, 80))
        self._ufo_animation.start()

    def _advance_ufo(self) -> None:
        dirty = self._ufo_dirty_region(self._ufo_progress)
        self._ufo_progress += 0.012
        if self._ufo_progress >= 1.0:
            self._ufo = False
            self._ufo_animation.stop()
        else:
            dirty = dirty.united(self._ufo_dirty_region(self._ufo_progress))
        self.update(dirty)

    def _schedule_battle(self, *, first: bool = False) -> None:
        if self._reduced_motion:
            return
        minimum, maximum = (75_000, 135_000) if first else (150_000, 300_000)
        self._battle_timer.start(random.randint(minimum, maximum))

    def _start_battle(self) -> None:
        if self._reduced_motion:
            return
        self._schedule_battle()
        if (
            self._battle
            or self._blackhole
            or self._ufo
            or self.width() < 240
            or self.height() < 180
        ):
            return
        self._battle = True
        self._battle_progress = 0.0
        self._battle_animation.start()

    def _draw_battle(self, painter: QPainter) -> None:
        progress = self._battle_progress
        wave = math.sin(progress * math.pi * 2.0)
        first = QPointF(
            self.width() * (-0.10 + progress * 1.20),
            self.height() * (0.24 + wave * 0.045),
        )
        second = QPointF(
            self.width() * (1.10 - progress * 1.20),
            self.height() * (0.39 - wave * 0.045),
        )
        scale = max(3.5, min(7.0, self.width() / 280.0))

        def ship(point: QPointF, color: QColor, *, reverse: bool = False) -> None:
            painter.save()
            painter.translate(point)
            if reverse:
                painter.scale(-1.0, 1.0)
            painter.setOpacity(0.46)
            painter.setPen(QPen(color, 1.35))
            fill = QColor(color)
            fill.setAlpha(35)
            painter.setBrush(fill)
            painter.drawPolygon(
                QPolygonF(
                    (
                        QPointF(scale * 3.8, 0),
                        QPointF(-scale * 2.8, -scale * 1.8),
                        QPointF(-scale * 1.3, 0),
                        QPointF(-scale * 2.8, scale * 1.8),
                    )
                )
            )
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 70))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(-scale * 2.9, 0), scale * 0.65, scale * 0.65)
            painter.restore()

        ship(first, QColor("#35E7F5"))
        ship(second, QColor("#B45CFF"), reverse=True)
        cycle = int(progress * 42)
        if 0.20 < progress < 0.84 and cycle % 3 != 2:
            from_first = cycle % 2 == 0
            origin, target = (first, second) if from_first else (second, first)
            pulse_progress = (progress * 42) % 1.0
            pulse = origin + (target - origin) * pulse_progress
            color = QColor("#35E7F5" if from_first else "#C465FF")
            painter.setOpacity(0.20)
            painter.setPen(QPen(color, 1.0))
            painter.drawLine(origin, target)
            painter.setOpacity(0.62)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(pulse, 2.2, 2.2)
        painter.setOpacity(1.0)

    def _advance_battle(self) -> None:
        dirty = self._battle_dirty_region(self._battle_progress)
        self._battle_progress += 0.0043
        if self._battle_progress >= 1.0:
            self._battle = False
            self._battle_animation.stop()
        else:
            dirty = dirty.united(self._battle_dirty_region(self._battle_progress))
        self.update(dirty)

    def _star_dirty_region(self, progress: float) -> QRect:
        point = self._star_start + (self._star_end - self._star_start) * progress
        tail = point - (self._star_end - self._star_start) * 0.055
        return self._line_dirty_region(tail, point, padding=7)

    def _ufo_dirty_region(self, progress: float) -> QRect:
        point = self._ufo_start + (self._ufo_end - self._ufo_start) * progress
        return (
            QRectF(point.x() - 24, point.y() - 14, 48, 32).toAlignedRect().intersected(self.rect())
        )

    def _blackhole_dirty_region(self) -> QRect:
        # Includes the full accretion ring and the short logo launch path.
        center = self._blackhole_center
        return (
            QRectF(center.x() - 175, center.y() - 125, 370, 250)
            .toAlignedRect()
            .intersected(self.rect())
        )

    def _battle_dirty_region(self, progress: float) -> QRect:
        wave = math.sin(progress * math.pi * 2.0)
        first = QPointF(
            self.width() * (-0.10 + progress * 1.20),
            self.height() * (0.24 + wave * 0.045),
        )
        second = QPointF(
            self.width() * (1.10 - progress * 1.20),
            self.height() * (0.39 - wave * 0.045),
        )
        return self._line_dirty_region(first, second, padding=42)

    def _line_dirty_region(self, start: QPointF, end: QPointF, *, padding: int) -> QRect:
        left = min(start.x(), end.x()) - padding
        top = min(start.y(), end.y()) - padding
        width = abs(end.x() - start.x()) + padding * 2
        height = abs(end.y() - start.y()) + padding * 2
        return QRectF(left, top, width, height).toAlignedRect().intersected(self.rect())

    def showEvent(self, event) -> None:
        if not self._reduced_motion:
            self._star_timer.start(14000)
            self._blackhole_timer.start(22000)
            self._ufo_timer.start(18000)
            if not self._battle_timer.isActive():
                self._schedule_battle(first=True)
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        for timer_name in (
            "_star_timer",
            "_star_animation",
            "_blackhole_timer",
            "_blackhole_animation",
            "_ufo_timer",
            "_ufo_animation",
            "_battle_timer",
            "_battle_animation",
        ):
            timer = getattr(self, timer_name, None)
            if timer is not None:
                timer.stop()
        self._shooting = False
        self._blackhole = False
        self._ufo = False
        self._battle = False
        super().hideEvent(event)

    def _render_background(self) -> None:
        self._background = QPixmap(max(1, self.width()), max(1, self.height()))
        painter = QPainter(self._background)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0.0, QColor("#010307"))
        gradient.setColorAt(0.5, QColor("#040812"))
        gradient.setColorAt(1.0, QColor("#050712"))
        painter.fillRect(self.rect(), gradient)
        state_color = {
            "idle": QColor(33, 78, 142, 20),
            "device": QColor(22, 191, 218, 25),
            "running": QColor(111, 66, 255, 30),
            "recovery": QColor(255, 109, 52, 28),
            "attention": QColor(255, 181, 70, 27),
        }[self._activity_state]
        glow = QRadialGradient(self.width() * 0.72, self.height() * 0.2, self.width() * 0.6)
        glow.setColorAt(0.0, state_color)
        glow.setColorAt(0.55, QColor(state_color.red(), state_color.green(), state_color.blue(), 8))
        glow.setColorAt(1.0, QColor(7, 10, 22, 0))
        painter.fillRect(self.rect(), glow)
        painter.setPen(QColor(118, 246, 255, 90))
        for x, y, radius in (
            (0.82, 0.18, 2),
            (0.64, 0.34, 1),
            (0.91, 0.61, 1),
            (0.46, 0.13, 1),
            (0.74, 0.82, 1),
        ):
            painter.drawEllipse(int(self.width() * x), int(self.height() * y), radius, radius)
        painter.setPen(QColor(79, 124, 255, 32))
        painter.drawEllipse(
            int(self.width() * 0.58),
            int(self.height() * -0.18),
            int(self.width() * 0.7),
            int(self.height() * 0.55),
        )
        painter.end()


class MainWindow(QMainWindow):
    scan_interval_changed = Signal(int)
    settings_changed = Signal(object)

    def __init__(
        self,
        engine: DeviceEngine | None,
        logo_path: Path,
        workspace: Path,
        scan_interval: int = 8,
        audit_store: GuardianAuditStore | None = None,
        pack_registry: DevicePackRegistry | None = None,
        brand_path: Path | None = None,
        sidebar_logo_path: Path | None = None,
        host: HostPlatform | None = None,
        runner: CommandRunner | None = None,
        tool_statuses: tuple[ToolStatus, ...] = (),
        app_icon_path: Path | None = None,
        gateway: ExecutionGateway | None = None,
        adb_executable: Path | None = None,
        fastboot_executable: Path | None = None,
        attestation_store: DevicePackAttestationStore | None = None,
        app_settings: AppSettings | None = None,
        desktop_update_service: DesktopUpdateService | None = None,
        galaxy_service_trust: GalaxyServiceTrust | None = None,
    ) -> None:
        super().__init__()
        self.engine = engine
        self._workspace = workspace
        self._runtime_runner = runner or SubprocessRunner()
        self._audit_store = audit_store or GuardianAuditStore(workspace)
        self._runtime_gateway = gateway
        self._local_flash_dialog = None
        self._source_operation_session = None
        self._recovery_operation_session: RecoveryOperationSession | None = None
        self._expert_flash_pending = False
        self._pending_local_flash_recovery: tuple[AndroidDevice, str] | None = None
        self._pending_local_flash_recovery_project: tuple[str, str] | None = None
        self._pending_local_flash_recovery_result = None
        self._pending_local_flash_recovery_trigger = RecoveryTrigger.FLASH_FAILURE
        self._pending_source_installation_recovery: tuple[str, str] | None = None
        self._device_adb_executable = adb_executable
        self._device_fastboot_executable = fastboot_executable
        self.scan_interval_seconds = max(scan_interval, 3)
        self.app_settings = app_settings or AppSettings(
            onboarding_complete=True,
            workspace_path=str(workspace),
            scan_interval_seconds=self.scan_interval_seconds,
        )
        self.desktop_update_service = desktop_update_service
        if galaxy_service_trust is None:
            try:
                trust_resource = files("romverse.assets").joinpath("galaxy_service_trust.json")
                with as_file(trust_resource) as trust_path:
                    galaxy_service_trust = load_galaxy_service_trust(trust_path)
            except GalaxyNetworkError as exc:
                galaxy_service_trust = GalaxyServiceTrust(
                    False,
                    f"The packaged Galaxy trust root was rejected: {exc}",
                    "",
                    "",
                    (),
                    (),
                    (),
                )
        self.galaxy_service_trust = galaxy_service_trust
        self.scanning = False
        self.active_worker: ScanWorker | None = None
        self.device_catalog_worker: DeviceCatalogWorker | None = None
        self._catalog_auto_attempted = False
        self._device_runtime_generation = 0
        self._observed_devices: list[AndroidDevice] = []
        self._selected_device_serial = ""
        self._reconnect_retry_ms = 1_500
        self._scan_failure_count = 0
        self._workspace_shell_state = WorkspaceShellState()
        self._experience_mode = self.app_settings.experience_mode
        self.setWindowTitle(DESKTOP_WINDOW_TITLE)
        self.setWindowIcon(QIcon(str(app_icon_path or logo_path)))
        self.resize(1440, 900)
        self.setMinimumSize(1080, 700)

        root = CosmicBackground(logo_path)
        self.cosmic_background = root
        root.set_reduced_motion(self.app_settings.reduced_motion)
        root.setObjectName("AppRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)
        self.notification_center = DesktopNotificationCenter(
            root,
            self.windowIcon(),
            enabled=self.app_settings.desktop_notifications_enabled,
            reduced_motion=self.app_settings.reduced_motion,
        )

        sidebar = QFrame()
        self.sidebar = sidebar
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(263)
        side = QVBoxLayout(sidebar)
        self.sidebar_layout = side
        side.setContentsMargins(14, 16, 14, 14)
        side.setSpacing(3)
        brand_card = QFrame()
        brand_card.setObjectName("WebsiteBrandCard")
        brand_card.setFixedHeight(190)
        brand_card.setStyleSheet(
            "QFrame#WebsiteBrandCard { background: rgba(3, 6, 17, 188); "
            "border: 1px solid rgba(39, 220, 255, 82); border-radius: 18px; }"
        )
        brand_layout = QVBoxLayout(brand_card)
        brand_layout.setContentsMargins(4, 4, 4, 4)
        brand_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        logo = WebsiteBrandCrest(
            app_icon_path or brand_path or logo_path,
            reduced_motion=self.app_settings.reduced_motion,
            parent=brand_card,
        )
        logo.setAccessibleName("Official ROMVERSE website icon in the app sidebar")
        logo.setFixedSize(172, 172)
        brand_layout.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
        side.addWidget(brand_card)
        self._brand_card = brand_card
        self._brand_logo = logo
        self._brand_logo.double_clicked.connect(self._show_thanks)
        self._logo_path = logo_path
        self._about_icon_path = app_icon_path or logo_path
        self._thanks_portal: ThanksPortal | None = None
        side.addSpacing(4)
        self.experience_badge = QPushButton()
        self.experience_badge.setObjectName("ModeBadge")
        self.experience_badge.setFixedHeight(36)
        self.experience_badge.setStyleSheet(
            "QPushButton { background:rgba(8,16,31,180); border:1px solid #2B416B; "
            "border-radius:10px; color:#35E7F5; font-size:11px; font-weight:800; "
            "letter-spacing:1px; } QPushButton:hover { border-color:#B45CFF; color:#FFFFFF; }"
        )
        self.experience_badge.clicked.connect(self._open_settings)
        side.addWidget(self.experience_badge)
        side.addSpacing(3)
        self.command_palette_button = QPushButton("⌕  FIND ANYTHING     Ctrl K")
        self.command_palette_button.setObjectName("CommandPaletteButton")
        self.command_palette_button.setAccessibleName(
            "Find a ROMVERSE page with the command palette, keyboard shortcut Control K"
        )
        self.command_palette_button.setToolTip(
            "Search canonical ROMVERSE pages. Navigation only; no device or build operation is executed."
        )
        self.command_palette_button.clicked.connect(self._open_command_palette)
        side.addWidget(self.command_palette_button)
        side.addSpacing(3)

        self.stack = QStackedWidget()
        self.page_routes: dict[str, int] = {}
        self.activity_store = ActivityStore(workspace)
        self.offline_knowledge_service = OfflineKnowledgeService(workspace)
        self.nexus_events = LiveConsoleEventStore(workspace)
        self.raw_terminal_feed = RawTerminalFeed()
        self._live_missions: dict[str, str] = {}
        self.device_center = DeviceCenter(workspace, self.activity_store, self.nexus_events)
        self.device_center.mission_state_changed.connect(self.cosmic_background.set_activity_state)
        self.cosmic_background.set_activity_state(self.device_center.mission_visual_state)
        self.device_center.knowledge_requested.connect(self._open_knowledge_query)
        self.stack.addWidget(self.device_center)
        history_store = DiagnosticHistoryStore(workspace, self.activity_store)
        self.diagnostics_center = DiagnosticsCenter(
            DiagnosticAnalyzer(),
            history_store,
            knowledge_service=self.offline_knowledge_service,
        )
        self.diagnostics_center.repair_requested.connect(self._open_repair_finding)
        self.diagnostics_center.knowledge_requested.connect(self._open_knowledge_query)
        self.diagnostics_center.knowledge_article_requested.connect(self._open_knowledge_article)
        self.diagnostics_center.report_changed.connect(self._diagnostic_report_changed)
        self.stack.addWidget(self.diagnostics_center)
        self.history_center = HistoryCenter(history_store)
        self.history_center.current_scan_requested.connect(self._open_current_health_review)
        self.history_center.knowledge_article_requested.connect(self._open_knowledge_article)
        self.history_center.knowledge_requested.connect(self._open_knowledge_query)
        self.stack.addWidget(self.history_center)
        self.guardian_center = GuardianCenter(self._audit_store, auto_start=False)
        self.guardian_center.dashboard_state_changed.connect(self._guardian_dashboard_state_changed)
        self.device_center.set_guardian_state(*self.guardian_center.current_dashboard_state())
        self.stack.addWidget(self.guardian_center)
        resolved_registry = pack_registry or DevicePackRegistry(())
        self.device_catalog = GooglePlayDeviceCatalog(workspace)
        self.device_identity = DeviceIdentityResolver(
            workspace,
            resolved_registry,
            (self.device_catalog,),
        )
        host_repair_service = (
            AdbHostRepairService(
                adb_executable,
                gateway,
                ApprovalStore(workspace),
                AdbHostRepairReceiptStore(workspace),
            )
            if adb_executable is not None and gateway is not None
            else None
        )
        recovery_online_service = (
            OnlineRemediationService.connected(
                workspace,
                include_community=self.app_settings.community_research_enabled,
            )
            if self.app_settings.online_intelligence_enabled
            else None
        )
        self.repair_center = RepairCenter(
            DiagnosticAnalyzer(),
            RepairAssessmentTemplates(),
            GuardianPreflight(),
            workspace,
            self.activity_store,
            resolved_registry,
            host_repair_service,
            self.nexus_events,
            recovery_online_service,
            self.offline_knowledge_service,
        )
        self.repair_center.knowledge_requested.connect(self._open_knowledge_query)
        self.repair_center.knowledge_article_requested.connect(self._open_knowledge_article)
        self.repair_center.diagnostic_requested.connect(self._open_diagnostic_finding)
        self.guardian_center.recovery_requested.connect(self._return_guardian_recovery)
        self.guardian_center.recovery_home_requested.connect(self._open_recovery_home)
        self.stack.addWidget(self.repair_center)
        self.device_packs_center = DevicePacksCenter(
            resolved_registry,
            workspace,
            attestation_store,
            self.device_catalog,
            self.app_settings.online_intelligence_enabled,
            tool_statuses,
        )
        self.device_packs_center.catalog_refresh_requested.connect(self._refresh_device_catalog)
        self.device_packs_center.knowledge_article_requested.connect(self._open_knowledge_article)
        self.device_packs_center.knowledge_query_requested.connect(self._open_knowledge_query)
        self.device_packs_center.next_action_requested.connect(self._open_device_pack_next_action)
        self.device_packs_center.requirement_requested.connect(self._open_device_requirement)
        self.device_packs_center.readiness_changed.connect(self._record_device_pack_readiness)
        self.stack.addWidget(self.device_packs_center)
        self.rom_studio = RomStudio(
            RomProjectStore(workspace),
            resolved_registry,
            tool_statuses,
            attestation_store,
            gateway,
            adb_executable,
            self.app_settings,
            fastboot_executable=fastboot_executable,
        )
        self.rom_studio.live_console_store = self.nexus_events
        self.stack.addWidget(self.rom_studio)
        apk_service = (
            ApkInstallService(adb_executable, gateway, ApprovalStore(workspace))
            if adb_executable is not None and gateway is not None
            else None
        )
        self.apk_installer = ApkCenter(
            workspace,
            apk_service,
            self.activity_store,
            tool_statuses,
            self._runtime_runner,
        )
        self.apk_installer.runtime_tools_requested.connect(self._resolve_apk_runtime)
        self.apk_installer.inspection_tools_requested.connect(self._resolve_apk_inspection_tools)
        self.apk_installer.knowledge_article_requested.connect(self._open_knowledge_article)
        self.stack.addWidget(self.apk_installer)
        media_backup_service = (
            PhoneMediaBackupService(
                workspace,
                adb_executable,
                gateway,
                ApprovalStore(workspace),
            )
            if adb_executable is not None and gateway is not None
            else None
        )
        self.backup_center = BackupCenter(
            workspace,
            self.activity_store,
            media_backup_service,
            Path(self.app_settings.backup_directory)
            if self.app_settings.backup_directory
            else None,
            self.nexus_events,
        )
        self.backup_center.runtime_tools_requested.connect(self._resolve_backup_runtime)
        self.backup_center.guardian_requested.connect(self._open_backup_guardian_review)
        self.backup_center.rom_studio_requested.connect(self._return_time_machine_rom_studio)
        self.backup_center.rom_studio_setup_requested.connect(
            self._open_time_machine_rom_studio_setup
        )
        self.backup_center.recovery_requested.connect(self._return_time_machine_recovery)
        self.guardian_center.time_machine_requested.connect(self._return_guardian_time_machine)
        self.guardian_center.rom_studio_requested.connect(self._return_guardian_rom_studio)
        self.stack.addWidget(self.backup_center)
        self.knowledge_center = KnowledgeCenter(
            ArchivesResolutionMemory(RepairSessionStore(workspace)),
            SynapseStore(workspace),
            self.device_catalog,
            self.offline_knowledge_service,
            KnowledgeUpdateService(
                workspace,
                self.galaxy_service_trust.knowledge_keys,
                unavailable_reason=self.galaxy_service_trust.reason,
            ),
            reduced_motion=self.app_settings.reduced_motion,
        )
        self.knowledge_center.route_requested.connect(self._open_knowledge_route)
        self.rom_studio.offline_knowledge_updated.connect(
            self.knowledge_center.refresh_offline_archive
        )
        self.repair_center.resolution_memory_updated.connect(
            self.knowledge_center.refresh_resolution_memory
        )
        self.repair_center.resolution_memory_updated.connect(
            self.device_packs_center.refresh_history
        )
        self.knowledge_index = self.stack.addWidget(self.knowledge_center)
        self.terminal_center = TerminalCenter(gateway, adb_executable, self.raw_terminal_feed)
        self.terminal_center.runtime_tools_requested.connect(self._resolve_terminal_runtime)
        self.terminal_center.knowledge_article_requested.connect(self._open_knowledge_article)
        terminal_index = self.stack.addWidget(self.terminal_center)
        self.terminal_center_index = terminal_index
        self.live_console = LiveConsoleCenter(self.nexus_events)
        self.live_console.source_requested.connect(self._open_live_console_source)
        self.backup_center.live_console_changed.connect(self.live_console.refresh)
        live_console_index = self.stack.addWidget(self.live_console)
        self.live_console_index = live_console_index
        self.nexus_center = NexusCenter(self.rom_studio.store)
        self.stack.addWidget(self.nexus_center)
        self.nexus_center.guardian_requested.connect(self._open_nexus_guardian_review)
        self.nexus_center.knowledge_article_requested.connect(self._open_knowledge_article)
        self.nexus_center.rom_studio_requested.connect(self._open_nexus_rom_studio)
        self.nexus_center.plan_updated.connect(self._record_nexus_plan)
        self.guardian_center.nexus_requested.connect(self._return_guardian_nexus)
        resolved_host = host or current_host()
        resolved_runner = self._runtime_runner
        self.toolchain_center = ToolchainCenter(
            resolved_host, resolved_runner, tool_statuses, workspace
        )
        toolchain_index = self.stack.addWidget(self.toolchain_center)
        self.toolchain_index = toolchain_index
        self.toolchain_center.statuses_changed.connect(self._tool_statuses_changed)
        self.guardian_center.toolchain_requested.connect(self._open_guardian_recovery_toolchain)
        self.toolchain_center.device_pack_setup_requested.connect(self._setup_device_pack_toolchain)
        self.toolchain_center.device_pack_continue_requested.connect(
            self._continue_device_pack_toolchain
        )
        self.toolchain_center.device_atlas_requested.connect(self._return_forge_device_atlas)
        self.toolchain_center.studio_project_setup_requested.connect(
            self._setup_studio_project_toolchain
        )
        self.toolchain_center.studio_project_continue_requested.connect(
            self._return_forge_rom_studio
        )
        self.toolchain_center.knowledge_article_requested.connect(self._open_knowledge_article)
        self.rom_studio.tool_statuses_resolved.connect(self._tool_statuses_changed)
        self.rom_studio.set_tool_statuses(self.toolchain_center.statuses)
        self.rom_studio.toolchain_requested.connect(self._open_toolchain)
        self.rom_studio.time_machine_requested.connect(self._open_time_machine)
        self.rom_studio.device_packs_requested.connect(self._open_device_atlas_from_studio)
        self.rom_studio.guardian_review_requested.connect(self._open_studio_guardian_review)
        self.rom_studio.device_center_requested.connect(self._open_device_center_from_studio)
        self.rom_studio.knowledge_requested.connect(self._open_knowledge_query)
        self.rom_studio.experience_mode_requested.connect(self._set_experience_mode_from_studio)
        self.rom_studio.expert_flash_requested.connect(self._open_expert_flash)
        self.rom_studio.project_flash_requested.connect(self._open_project_flash)
        self.rom_studio.source_installation_history_requested.connect(
            self._open_source_installation_history
        )
        self.rom_studio.source_installation_recovery_requested.connect(
            self._open_source_installation_recovery
        )
        self.device_packs_center.rom_studio_requested.connect(
            self._continue_device_atlas_rom_studio
        )
        self.rom_studio.ascension_status_changed.connect(self._update_companion_ascension_status)
        usb_pairing_service = (
            UsbPairingAssistService(
                self._device_adb_executable,
                self._runtime_gateway,
                ApprovalStore(workspace),
                workspace,
            )
            if self._device_adb_executable is not None and self._runtime_gateway is not None
            else None
        )
        self.companion_center = CompanionCenter(
            self.nexus_events,
            self.raw_terminal_feed,
            workspace,
            usb_pairing_service=usb_pairing_service,
        )
        self.companion_center.set_nexus_plan(self.nexus_center.current_plan)
        current_project = self.rom_studio.current_project
        current_profile = (
            self.rom_studio.device_dna.profiles.load(current_project.project_id)
            if current_project is not None and current_project.original is not None
            else None
        )
        self.companion_center.set_device_dna(
            current_profile,
            current_project.name if current_project is not None else "",
        )
        self.companion_center.remote_snapshot_updated.connect(
            self.rom_studio.set_companion_snapshot
        )
        self.companion_center.remote_snapshot_updated.connect(
            lambda _snapshot: self._update_companion_ascension_status()
        )
        self._update_companion_ascension_status()
        companion_index = self.stack.addWidget(self.companion_center)
        self.companion_index = companion_index
        self.about_page = AboutPage(
            logo_path,
            brand_path,
            self._about_icon_path,
            workspace=workspace,
            reduced_motion=self.app_settings.reduced_motion,
            privacy_settings=self.app_settings,
        )
        self.about_page.logo_double_clicked.connect(self._show_thanks)
        self.about_page.route_requested.connect(self._navigate_route)
        self.about_page.knowledge_article_requested.connect(self._open_knowledge_article)
        about_index = self.stack.addWidget(self.about_page)
        self.galaxy_center = GalaxyCenter(
            workspace,
            self.activity_store,
            knowledge_update_service=self.knowledge_center.update_service,
            galaxy_trust=self.galaxy_service_trust,
            member_issuer=self.app_settings.members_issuer,
            member_session_provider=lambda: (
                self.members_center.session if hasattr(self, "members_center") else None
            ),
            contribution_opt_in=self.app_settings.synapse_contributions_enabled,
            reduced_motion=self.app_settings.reduced_motion,
        )
        self.galaxy_center.knowledge_article_requested.connect(self._open_knowledge_article)
        self.galaxy_center.route_requested.connect(self._navigate_route)
        self.galaxy_center.settings_requested.connect(self._open_settings)
        self.galaxy_center.offline_archive_updated.connect(
            self.knowledge_center.refresh_offline_archive
        )
        self.stack.addWidget(self.galaxy_center)
        self.members_center = MembersCenter(
            self.app_settings.members_issuer,
            self.app_settings.members_client_id,
        )
        self.members_center.settings_requested.connect(self._open_settings)
        self.members_center.knowledge_article_requested.connect(self._open_knowledge_article)
        members_index = self.stack.addWidget(self.members_center)
        self.activity_center = ActivityCenter(self.activity_store)
        self.activity_center.route_requested.connect(self._navigate_feature_route)
        self.activity_center.source_requested.connect(self._open_activity_source)
        activity_index = self.stack.addWidget(self.activity_center)
        self.page_routes = {
            "command_deck": self.stack.indexOf(self.device_center),
            "quantum_optimizer": self.stack.indexOf(self.diagnostics_center),
            "health_timeline": self.stack.indexOf(self.history_center),
            "activity_center": activity_index,
            "guardian_core": self.stack.indexOf(self.guardian_center),
            "recovery_bay": self.stack.indexOf(self.repair_center),
            "device_atlas": self.stack.indexOf(self.device_packs_center),
            "rom_studio": self.stack.indexOf(self.rom_studio),
            "app_launchpad": self.stack.indexOf(self.apk_installer),
            "time_machine": self.stack.indexOf(self.backup_center),
            "archives": self.stack.indexOf(self.knowledge_center),
            "command_console": self.stack.indexOf(self.terminal_center),
            "live_console": self.stack.indexOf(self.live_console),
            "nexus": self.stack.indexOf(self.nexus_center),
            "forge_arsenal": self.stack.indexOf(self.toolchain_center),
            "companion_link": self.stack.indexOf(self.companion_center),
            "members": members_index,
            "galaxy": self.stack.indexOf(self.galaxy_center),
            "about": about_index,
        }
        self._route_by_page_index = {
            page_index: route for route, page_index in self.page_routes.items()
        }
        self.nav_buttons: list[QPushButton] = []
        nav_scroll = QScrollArea()
        self.nav_scroll = nav_scroll
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setMinimumHeight(150)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        nav_scroll.viewport().setStyleSheet("background:#02050A;")
        nav_host = QWidget()
        self.nav_host = nav_host
        nav_layout = QVBoxLayout(nav_host)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(3)
        section_icons = {
            "command_deck": ("dashboard", "#B75CFF", "#587FFF"),
            "rom_studio": ("build", "#A44BFF", "#557EFF"),
            "quantum_optimizer": ("optimizer", "#25C9E8", "#4BEAF4"),
            "device_atlas": ("mods", "#F13ACB", "#B64DFF"),
            "recovery_bay": ("repair", "#31D7F2", "#6885FF"),
            "guardian_core": ("guardian", "#B65BFF", "#3F8FFF"),
            "app_launchpad": ("apk", "#7B64FF", "#2BE5F4"),
            "time_machine": ("backup", "#B54EFF", "#5B88FF"),
            "health_timeline": ("logs", "#548BFF", "#35DBF0"),
            "activity_center": ("logs", "#35DBF0", "#B45CFF"),
            "archives": ("knowledge", "#C95BFF", "#6B80FF"),
            "command_console": ("terminal", "#4C82FF", "#59A7FF"),
            "live_console": ("logs", "#38DFF2", "#9A64FF"),
            "nexus": ("galaxy", "#C35CFF", "#35E7F5"),
            "forge_arsenal": ("toolchain", "#21D2E9", "#7A75FF"),
            "companion_link": ("companion", "#E34BD8", "#397FFF"),
            "members": ("members", "#7C73FF", "#33E7D0"),
            "galaxy": ("galaxy", "#A54BFF", "#22DFF3"),
            "about": ("about", "#C35BFF", "#4A91FF"),
        }
        self._nav_icon_specs: dict[QPushButton, tuple[str, str, str]] = {}
        self.nav_section_labels: list[QLabel] = []
        for group in NAVIGATION_GROUPS:
            heading = QLabel(group.title)
            heading.setObjectName("NavSection")
            heading.setAccessibleName(f"{group.title.title()} navigation group")
            nav_layout.addWidget(heading)
            self.nav_section_labels.append(heading)
            for route in group.routes:
                name = feature(route)
                index = self.page_routes[route]
                active = route == "command_deck"
                # Escape ampersands so Qt displays them instead of treating them as
                # keyboard-mnemonic markers (for example, Backup & Restore).
                expanded_text = name.title.replace("&", "&&")
                button = QPushButton(expanded_text)
                icon_name, icon_start, icon_end = section_icons[route]
                button.setIcon(sidebar_icon(icon_name, 26, icon_start, icon_end, active=active))
                button.setIconSize(QSize(26, 26))
                button.setAccessibleName(f"Open {name.title}")
                button.setToolTip(_sidebar_nav_tooltip(name.title, name.subtitle))
                button.setToolTipDuration(4_000)
                button.setObjectName("Nav")
                button.setProperty("active", active)
                button.setProperty("collapsed", False)
                button.setProperty("expanded_text", expanded_text)
                button.setProperty("page_index", index)
                button.setProperty("route_key", route)
                button.setProperty("expert_only", route in EXPERT_ONLY_ROUTES)
                button.clicked.connect(lambda _checked=False, i=index: self._navigate(i))
                nav_layout.addWidget(button)
                self.nav_buttons.append(button)
                self._nav_icon_specs[button] = (icon_name, icon_start, icon_end)
        nav_layout.addStretch()
        nav_scroll.setWidget(nav_host)
        side.addWidget(nav_scroll, 1)

        self.sidebar_device_card = QFrame()
        self.sidebar_device_card.setObjectName("DeviceMiniCard")
        mini_layout = QVBoxLayout(self.sidebar_device_card)
        mini_layout.setContentsMargins(12, 10, 12, 10)
        mini_layout.setSpacing(6)
        self.sidebar_device_state = QLabel("●  Waiting for device")
        self.sidebar_device_state.setObjectName("Warning")
        self.sidebar_device_state.setWordWrap(True)
        mini_layout.addWidget(self.sidebar_device_state)
        device_row = QHBoxLayout()
        device_row.setContentsMargins(0, 0, 0, 0)
        device_row.setSpacing(9)
        self.sidebar_device_image = QLabel()
        self.sidebar_device_image.setFixedSize(64, 88)
        self.sidebar_device_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sidebar_device_image.setStyleSheet("background: transparent; border: 0;")
        phone_resource = files("romverse.assets").joinpath("sidebar-phone-white.png")
        with as_file(phone_resource) as phone_path:
            self._sidebar_exact_phone_pixmap = QPixmap(str(phone_path))
        self._sidebar_generic_phone_pixmap = _generic_phone_pixmap()
        self.sidebar_device_image.setPixmap(self._sidebar_generic_phone_pixmap)
        self.sidebar_device_image.setAccessibleName("Generic Android device silhouette")
        self.sidebar_device_image.setToolTip(
            "A connected phone's exact product artwork appears only when Device DNA proves it."
        )
        self.sidebar_device_image.setVisible(False)
        device_row.addWidget(self.sidebar_device_image, 0, Qt.AlignmentFlag.AlignVCenter)
        device_text = QVBoxLayout()
        device_text.setContentsMargins(0, 2, 0, 2)
        device_text.setSpacing(1)
        self.sidebar_device_name = QLabel("Android device")
        self.sidebar_device_name.setObjectName("Value")
        self.sidebar_device_name.setWordWrap(True)
        self.sidebar_device_name.setStyleSheet("color:#EDF4FF; font-size:12px; font-weight:700;")
        self.sidebar_device_detail = QLabel("Connect via ADB")
        self.sidebar_device_detail.setObjectName("Muted")
        self.sidebar_device_detail.setWordWrap(True)
        self.sidebar_device_detail.setStyleSheet("color:#8C9ABC; font-size:11px;")
        device_text.addWidget(self.sidebar_device_name)
        device_text.addWidget(self.sidebar_device_detail)
        device_row.addLayout(device_text, 1)
        mini_layout.addLayout(device_row)
        side.addWidget(self.sidebar_device_card)
        self.sidebar_version = QLabel(DESKTOP_SIDEBAR_VERSION)
        self.sidebar_version.setStyleSheet(
            "color:#B45CFF; font-weight:800; padding:8px 4px 2px 4px;"
        )
        side.addWidget(self.sidebar_version)
        root_layout.addWidget(sidebar)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.workspace_bar = QFrame()
        self.workspace_bar.setObjectName("WorkspaceBar")
        self.workspace_bar.setFixedHeight(54)
        workspace_bar_layout = QHBoxLayout(self.workspace_bar)
        workspace_bar_layout.setContentsMargins(13, 5, 18, 5)
        workspace_bar_layout.setSpacing(9)
        self.navigation_toggle = QToolButton()
        self.navigation_toggle.setObjectName("WorkspaceControl")
        self.navigation_toggle.setText("«")
        self.navigation_toggle.setCheckable(True)
        self.navigation_toggle.setAccessibleName("Collapse the Desktop navigation to an icon rail")
        self.navigation_toggle.setToolTip(
            "Collapse navigation to a permanent icon rail (Ctrl+B). Presentation only; page and operation state stay unchanged."
        )
        self.navigation_toggle.clicked.connect(self._toggle_navigation_rail)
        workspace_bar_layout.addWidget(self.navigation_toggle)
        self.workspace_search_button = QToolButton()
        self.workspace_search_button.setObjectName("WorkspaceControl")
        self.workspace_search_button.setText("⌕")
        self.workspace_search_button.setAccessibleName(
            "Find a canonical ROMVERSE page with the command palette"
        )
        self.workspace_search_button.setToolTip(
            "Find any ROMVERSE page (Ctrl+K). Navigation only; no operation is started."
        )
        self.workspace_search_button.clicked.connect(self._open_command_palette)
        workspace_bar_layout.addWidget(self.workspace_search_button)
        breadcrumb = QWidget()
        breadcrumb_layout = QVBoxLayout(breadcrumb)
        breadcrumb_layout.setContentsMargins(2, 0, 0, 0)
        breadcrumb_layout.setSpacing(0)
        self.workspace_section = QLabel("HOME")
        self.workspace_section.setObjectName("WorkspaceSection")
        self.workspace_route_title = QLabel(feature("command_deck").title)
        self.workspace_route_title.setObjectName("WorkspaceRouteTitle")
        self.workspace_route_title.setMinimumWidth(260)
        self.workspace_route_title.setAccessibleName(
            f"Current Desktop page: {feature('command_deck').title}"
        )
        breadcrumb_layout.addWidget(self.workspace_section)
        breadcrumb_layout.addWidget(self.workspace_route_title)
        workspace_bar_layout.addWidget(breadcrumb)
        workspace_bar_layout.addStretch(1)
        self.online_status = OnlineStatusBadge(
            monitoring_enabled=self.app_settings.online_intelligence_enabled
        )
        workspace_bar_layout.addWidget(self.online_status)
        self.focus_button = QToolButton()
        self.focus_button.setObjectName("FocusWorkspaceControl")
        self.focus_button.setText("FOCUS")
        self.focus_button.setCheckable(True)
        self.focus_button.setAccessibleName("Enter the Focus workspace")
        self.focus_button.setToolTip(
            "Temporarily hide navigation and connection chrome (Ctrl+Shift+F). The active page, evidence, and operations stay unchanged."
        )
        self.focus_button.clicked.connect(self._toggle_focus_mode)
        workspace_bar_layout.addWidget(self.focus_button)
        content_layout.addWidget(self.workspace_bar)
        content_layout.addWidget(self.stack, 1)
        self.connection_bar = QFrame()
        self.connection_bar.setObjectName("ConnectionBar")
        connection_layout = QHBoxLayout(self.connection_bar)
        connection_layout.setContentsMargins(22, 11, 22, 11)
        connection_layout.setSpacing(24)
        self.connection_state = QLabel("⌁  Waiting for ADB")
        self.connection_state.setObjectName("Warning")
        self.connection_device = QLabel("Device: —")
        self.connection_device.setObjectName("Muted")
        self.connection_android = QLabel("Android —")
        self.connection_android.setObjectName("Muted")
        self.connection_uptime = QLabel("Device uptime: —")
        self.connection_uptime.setObjectName("Muted")
        self.connection_clock = QLabel("")
        self.connection_clock.setObjectName("Muted")
        for widget in (
            self.connection_state,
            self.connection_device,
            self.connection_android,
            self.connection_uptime,
        ):
            connection_layout.addWidget(widget)
        connection_layout.addStretch(1)
        connection_layout.addWidget(self.connection_clock)
        content_layout.addWidget(self.connection_bar)
        root_layout.addWidget(content, 1)
        self._device_uptime_seconds: int | None = None
        self._device_uptime_seen_at = time.monotonic()
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._update_connection_bar)
        self._clock_timer.start()
        self._update_connection_bar()
        self._command_palette: CommandPaletteDialog | None = None
        self.command_palette_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self.command_palette_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.command_palette_shortcut.activated.connect(self._open_command_palette)
        self.navigation_rail_shortcut = QShortcut(QKeySequence("Ctrl+B"), self)
        self.navigation_rail_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.navigation_rail_shortcut.activated.connect(self._toggle_navigation_rail)
        self.focus_mode_shortcut = QShortcut(QKeySequence("Ctrl+Shift+F"), self)
        self.focus_mode_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.focus_mode_shortcut.activated.connect(self._toggle_focus_mode)
        self.focus_exit_shortcut = QShortcut(QKeySequence("Esc"), self)
        self.focus_exit_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.focus_exit_shortcut.activated.connect(self._leave_focus_mode)
        self.focus_exit_shortcut.setEnabled(False)

        self.device_center.refresh_requested.connect(self.scan)
        self.device_center.device_selected.connect(self._select_observed_device)
        self.device_center.runtime_tools_requested.connect(self._resolve_device_runtime)
        self.device_center.rom_studio_requested.connect(self._return_command_deck_rom_studio)
        self.device_center.action_requested.connect(self._handle_dashboard_action)
        self.diagnostics_center.refresh_requested.connect(self.scan)
        self.diagnostics_center.report_saved.connect(self.history_center.refresh)
        self.repair_center.verification_scan_requested.connect(self.scan)
        self.repair_center.runtime_tools_requested.connect(self._resolve_repair_runtime)
        self.repair_center.solution_action_requested.connect(self._open_repair_solution_action)
        self.repair_center.autopilot_route_requested.connect(self._open_autopilot_route)
        self.rom_studio.operation_started.connect(self._live_operation_started)
        self.rom_studio.operation_progress.connect(self._live_operation_progress)
        self.rom_studio.operation_completed.connect(self._record_rom_operation)
        self.rom_studio.operation_completed.connect(self._live_operation_completed)
        self.rom_studio.operation_failed.connect(self._record_rom_failure)
        self.rom_studio.operation_failed.connect(self._live_operation_failed)
        self.rom_studio.operation_failed.connect(self._open_recovery_from_rom_failure)
        self.rom_studio.device_scan_requested.connect(self.scan)
        self.rom_studio.device_scan_available = engine is not None
        self.rom_studio.device_dna_updated.connect(self._record_device_dna)
        self.rom_studio.guardian_flash_verified.connect(
            self.device_packs_center.record_verified_flash
        )
        self.rom_studio.boot_observation_updated.connect(self._handle_boot_observation)
        self.rom_studio.first_light_updated.connect(self._handle_first_light)
        self.rom_studio.compatibility_matrix_updated.connect(self._record_compatibility_matrix)
        self.rom_studio.compatibility_matrix_updated.connect(
            lambda _matrix: self.nexus_center.refresh()
        )
        self.timer = QTimer(self)
        self.timer.setInterval(self.scan_interval_seconds * 1000)
        self.timer.timeout.connect(self.scan)
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self.scan)
        if engine is not None:
            self.timer.start()
            QTimer.singleShot(250, self.scan)
        else:
            self.device_center.show_error(
                "Verified Android Platform Tools are not active yet. ROMVERSE can resolve them without restarting."
            )

        self._apply_experience_mode(self.app_settings.experience_mode)
        self.diagnostics_center.set_reduced_motion(self.app_settings.reduced_motion)
        self._apply_workspace_shell()
        self._apply_theme(self.app_settings.desktop_theme, persist=False)
        self._update_workspace_breadcrumb("command_deck")
        self._sync_command_deck_context()
        self._resize_branding()

    def resizeEvent(self, event) -> None:
        self._resize_branding()
        super().resizeEvent(event)

    def _resize_branding(self) -> None:
        if not hasattr(self, "_brand_logo"):
            return
        compact = self.width() < 1_340
        self.connection_uptime.setVisible(not compact)
        self.connection_clock.setVisible(self.width() >= 1_180)
        if self._workspace_shell_state.navigation_collapsed:
            self._brand_logo.setFixedSize(58, 58)
            self._brand_card.setFixedHeight(68)
            return
        # Keep the production crest prominent without starving navigation at
        # the supported minimum window height.
        brand_height = max(158, min(205, int(self.height() * 0.215)))
        crest_side = max(142, min(178, brand_height - 12))
        self._brand_logo.setFixedSize(crest_side, crest_side)
        self._brand_card.setFixedHeight(brand_height)

    @Slot()
    def _toggle_navigation_rail(self) -> None:
        """Toggle presentation width without changing the active route or its state."""

        if self._workspace_shell_state.focus_mode:
            return
        self._workspace_shell_state = self._workspace_shell_state.toggle_navigation()
        self._apply_workspace_shell()

    @Slot()
    def _toggle_focus_mode(self) -> None:
        """Enter or leave a reversible, presentation-only page workspace."""

        self._workspace_shell_state = self._workspace_shell_state.toggle_focus()
        self._apply_workspace_shell()

    @Slot()
    def _leave_focus_mode(self) -> None:
        if not self._workspace_shell_state.focus_mode:
            return
        self._workspace_shell_state = self._workspace_shell_state.toggle_focus()
        self._apply_workspace_shell()

    def _apply_workspace_shell(self) -> None:
        state = self._workspace_shell_state
        collapsed = state.navigation_collapsed
        focus = state.focus_mode
        self.sidebar.setVisible(not focus)
        self.connection_bar.setVisible(not focus)
        self.sidebar.setFixedWidth(78 if collapsed else 263)
        self.sidebar_layout.setContentsMargins(
            8 if collapsed else 14,
            11 if collapsed else 16,
            8 if collapsed else 14,
            11 if collapsed else 14,
        )
        self.navigation_toggle.setChecked(collapsed)
        self.navigation_toggle.setEnabled(not focus)
        self.navigation_toggle.setVisible(not focus)
        self.navigation_toggle.setText("»" if collapsed else "«")
        self.navigation_toggle.setAccessibleName(
            "Expand the Desktop navigation"
            if collapsed
            else "Collapse the Desktop navigation to an icon rail"
        )
        self.navigation_toggle.setToolTip(
            "Expand the permanent navigation (Ctrl+B)."
            if collapsed
            else "Collapse navigation to a permanent icon rail (Ctrl+B). Presentation only; page and operation state stay unchanged."
        )
        self.navigation_rail_shortcut.setEnabled(not focus)
        self.focus_exit_shortcut.setEnabled(focus)
        self.focus_button.setChecked(focus)
        self.focus_button.setProperty("active", focus)
        self.focus_button.setText("EXIT FOCUS  Esc" if focus else "FOCUS")
        self.focus_button.setAccessibleName(
            "Exit the Focus workspace" if focus else "Enter the Focus workspace"
        )
        self.focus_button.setToolTip(
            "Exit Focus and restore the same navigation and connection chrome (Esc)."
            if focus
            else "Temporarily hide navigation and connection chrome (Ctrl+Shift+F). The active page, evidence, and operations stay unchanged."
        )
        self.workspace_bar.setProperty("focusMode", focus)
        self.sidebar_device_card.setVisible(not collapsed)
        self.sidebar_version.setVisible(not collapsed)
        for heading in self.nav_section_labels:
            heading.setVisible(not collapsed)
        for button in self.nav_buttons:
            expanded_text = button.property("expanded_text")
            button.setText("" if collapsed else str(expanded_text))
            button.setProperty("collapsed", collapsed)
            button.style().unpolish(button)
            button.style().polish(button)
        self.command_palette_button.setText("⌕" if collapsed else "⌕  FIND ANYTHING     Ctrl K")
        mode_text = self.experience_badge.property("expanded_text")
        if isinstance(mode_text, str):
            self.experience_badge.setText(mode_text[:1] if collapsed else mode_text)
        for widget in (self.workspace_bar, self.focus_button, self.navigation_toggle):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self._resize_branding()
        current_route = self._route_by_page_index.get(self.stack.currentIndex())
        if current_route is not None:
            self._update_workspace_breadcrumb(current_route)

    def _update_workspace_breadcrumb(self, route: str) -> None:
        if route not in FEATURES:
            return
        section = navigation_section(route)
        name = feature(route)
        prefix = "FOCUS WORKSPACE  •  " if self._workspace_shell_state.focus_mode else ""
        self.workspace_section.setText(f"{prefix}{section}")
        self.workspace_route_title.setText(name.title)
        self.workspace_route_title.setAccessibleName(f"Current Desktop page: {name.title}")
        self.workspace_route_title.setToolTip(name.subtitle)

    def _update_connection_bar(self) -> None:
        if self._device_uptime_seconds is None:
            self.connection_uptime.setText("Device uptime: —")
        else:
            elapsed = self._device_uptime_seconds + int(
                time.monotonic() - self._device_uptime_seen_at
            )
            days, remainder = divmod(elapsed, 24 * 60 * 60)
            hours, remainder = divmod(remainder, 3600)
            minutes, _seconds = divmod(remainder, 60)
            day_prefix = f"{days}d " if days else ""
            self.connection_uptime.setText(f"Device uptime: {day_prefix}{hours:02d}:{minutes:02d}")
        self.connection_clock.setText(time.strftime("%H:%M"))

    def closeEvent(self, event) -> None:  # noqa: N802
        """Stop producers before Qt begins destroying their receiving widgets."""

        source_session = self._source_operation_session
        if source_session is not None and source_session.busy:
            event.ignore()
            if self._local_flash_dialog is not None:
                self._local_flash_dialog.raise_()
            else:
                QTimer.singleShot(
                    0,
                    lambda active=source_session: self._show_source_operation_session(active),
                )
            return
        if self._local_flash_dialog is not None and (
            self._local_flash_dialog.worker is not None or self._local_flash_dialog.monitoring
        ):
            event.ignore()
            self._local_flash_dialog.raise_()
            return
        if source_session is not None:
            source_session.dispose()
            self._source_operation_session = None
        if self._recovery_operation_session is not None:
            self._recovery_operation_session.deleteLater()
            self._recovery_operation_session = None
        self.timer.stop()
        self._reconnect_timer.stop()
        self._clock_timer.stop()
        self.notification_center.shutdown()
        self.companion_center.shutdown()
        shutdown_background_tasks()
        super().closeEvent(event)

    @Slot()
    def _show_thanks(self) -> None:
        self._thanks_portal = ThanksPortal(
            self._about_icon_path,
            self,
            first_discovery=self.about_page.last_origin_was_first,
            reduced_motion=self.app_settings.reduced_motion,
        )
        self._thanks_portal.show()

    @Slot()
    def scan(self) -> None:
        if (
            self.engine is None
            or self.scanning
            or self._local_flash_dialog is not None
            or (self._source_operation_session is not None and self._source_operation_session.busy)
            or self._expert_flash_pending
        ):
            return
        self._reconnect_timer.stop()
        self.scanning = True
        current = self.stack.currentWidget()
        self.device_center.set_scanning(True, show_progress=current is self.device_center)
        self.diagnostics_center.set_scanning(True, show_progress=current is self.diagnostics_center)
        self.device_packs_center.set_scanning(True)
        worker = ScanWorker(self.engine)
        self.active_worker = worker
        generation = self._device_runtime_generation
        worker.signals.complete.connect(
            lambda devices, active=generation: (
                self._scan_complete(devices) if active == self._device_runtime_generation else None
            )
        )
        worker.signals.failed.connect(
            lambda message, active=generation: (
                self._scan_failed(message) if active == self._device_runtime_generation else None
            )
        )
        start_background(worker)

    @Slot(list)
    def _scan_complete(self, devices: list[AndroidDevice]) -> None:
        previous_failures = self._scan_failure_count
        self.scanning = False
        self.active_worker = None
        self._scan_failure_count = 0
        devices = [self.device_identity.resolve_online(device) for device in devices]
        self._observed_devices = list(devices)
        observed_serials = {device.serial for device in devices}
        if len(devices) == 1:
            self._selected_device_serial = devices[0].serial
        elif self._selected_device_serial not in observed_serials:
            self._selected_device_serial = ""
        active_devices = [
            device for device in devices if device.serial == self._selected_device_serial
        ]
        self.device_center.set_scanning(False)
        self.device_center.set_devices(devices, self._selected_device_serial)
        self.diagnostics_center.set_scanning(False)
        self._set_active_device_context(active_devices)
        self.device_packs_center.set_scanning(False)
        if any(device.brand.strip() and device.codename.strip() for device in devices):
            self._maybe_refresh_device_catalog()
        stabilizing = any(
            device.connection_note.startswith("USB link detected;") for device in devices
        )
        unstable = any("USB reconnect is unstable" in device.connection_note for device in devices)
        if stabilizing or unstable:
            delay = self._reconnect_retry_ms
            self._reconnect_retry_ms = min(30_000, max(3_000, delay * 2))
            self.timer.setInterval(max(self.scan_interval_seconds * 1000, delay))
            QTimer.singleShot(delay, self.scan)
        else:
            self._reconnect_retry_ms = 1_500
            self._reconnect_timer.stop()
            self.timer.setInterval(self.scan_interval_seconds * 1000)
        self._render_active_device(active_devices[0] if active_devices else None, len(devices))
        self.rom_studio.device_scan_finished.emit(
            True,
            "Fresh device scan completed."
            if active_devices
            else "Fresh device scan completed; choose one of the connected Android devices."
            if devices
            else "Fresh device scan completed; no Android device is visible.",
        )
        if previous_failures and devices:
            self.notification_center.notify(
                "device.connection.restored",
                "Device connection restored",
                "ROMVERSE can read the connected device again and refreshed its current evidence.",
                NotificationKind.SUCCESS,
            )
        self._finish_local_flash_recovery(devices)
        self._resume_pending_source_installation_recovery()
        self._advance_recovery_operation_session(devices)

    @Slot(str)
    def _select_observed_device(self, serial: str) -> None:
        selected = next(
            (device for device in self._observed_devices if device.serial == serial),
            None,
        )
        self._selected_device_serial = selected.serial if selected is not None else ""
        active_devices = [selected] if selected is not None else []
        self._set_active_device_context(active_devices)
        self._render_active_device(selected, len(self._observed_devices))

    def _set_active_device_context(self, devices: list[AndroidDevice]) -> None:
        """Bind all action surfaces to the same explicitly selected device."""

        self.companion_center.set_device_snapshot(
            devices,
            observed_devices=self._observed_devices,
        )
        self.toolchain_center.set_device_communication_evidence(
            devices,
            observed_devices=self._observed_devices,
        )
        self._update_companion_ascension_status()
        self.diagnostics_center.set_devices(devices)
        self.guardian_center.request_refresh()
        self.repair_center.set_devices(devices)
        self.device_packs_center.set_devices(devices)
        if len(devices) == 1:
            device = devices[0]
            try:
                knowledge_report = self.offline_knowledge_service.scan_after_device_snapshot(
                    device,
                    limit=5,
                )
            except (OSError, TypeError, ValueError) as exc:
                self.device_center.set_knowledge_lookup(device.serial, None, str(exc))
                self.device_packs_center.set_knowledge_lookup(
                    device.serial,
                    None,
                    str(exc),
                )
            else:
                self.device_center.set_knowledge_lookup(device.serial, knowledge_report)
                self.device_packs_center.set_knowledge_lookup(device.serial, knowledge_report)
                self.knowledge_center.refresh_offline_archive(knowledge_report)
        else:
            self.device_center.set_knowledge_lookup("", None)
            self.device_packs_center.set_knowledge_lookup("", None)
        current_project = self.rom_studio.current_project
        current_profile = (
            self.rom_studio.device_dna.profiles.load(current_project.project_id)
            if current_project is not None and current_project.original is not None
            else None
        )
        self.device_packs_center.set_device_dna(current_profile)
        self.rom_studio.set_devices(
            devices,
            observed_devices=self._observed_devices,
        )
        self.apk_installer.set_devices(devices)
        self.backup_center.set_devices(devices)
        self.terminal_center.set_devices(devices)
        self.galaxy_center.set_devices(devices)
        # Genesis derives its device stage from ROM Studio. Refresh the Command
        # Deck only after every consumer has received the newly selected device,
        # otherwise its cached flight plan can continue to claim no phone is
        # connected while the live device card already shows one.
        self._sync_command_deck_context()

    def _render_active_device(self, device: AndroidDevice | None, observed_count: int) -> None:
        if device is not None:
            connected = device.state is DeviceState.DEVICE
            fastboot_connected = device.is_fastboot
            self.connection_state.setText(
                "⌁  Connected via ADB"
                if connected
                else f"⌁  Connected via {device.state.value.title()}"
                if fastboot_connected
                else f"⌁  {device.state.value.title()}"
            )
            self.connection_state.setObjectName(
                "Good" if (connected or fastboot_connected) and not device.errors else "Warning"
            )
            self.connection_device.setText(
                f"Device: {device.display_name} ({device.codename or 'unknown'})"
            )
            self.connection_android.setText(
                f"Android {device.android_version or '—'}"
                if connected
                else f"{device.state.value.title()} • Android telemetry unavailable"
                if fastboot_connected
                else "Android —"
            )
            self._device_uptime_seconds = device.uptime_seconds if connected else None
            self._device_uptime_seen_at = time.monotonic()
            self.sidebar_device_state.setText(
                "●  Device Connected"
                if connected
                else f"●  {device.state.value.title()} Connected"
                if fastboot_connected
                else f"●  {device.state.value.title()}"
            )
            self.sidebar_device_state.setObjectName(
                "Good" if (connected or fastboot_connected) and not device.errors else "Warning"
            )
            self._set_sidebar_device_art(device)
            self.sidebar_device_image.setVisible(connected or fastboot_connected)
            self.sidebar_device_name.setText(device.display_name)
            self.sidebar_device_detail.setText(
                f"{device.codename or 'Unknown codename'}\nAndroid {device.android_version or '—'} • {device.rom_display or 'ROM unavailable'}"
                if connected
                else f"{device.codename or 'Unknown product'}\n{device.state.value.title()} • identity only"
                if fastboot_connected
                else device.connection_note
            )
        elif observed_count > 1:
            self.connection_state.setText("⌁  Select a device")
            self.connection_state.setObjectName("Warning")
            self.connection_device.setText(f"Devices detected: {observed_count}")
            self.connection_android.setText("Android —")
            self._device_uptime_seconds = None
            self._device_uptime_seen_at = time.monotonic()
            self.sidebar_device_state.setText("●  Device selection required")
            self.sidebar_device_state.setObjectName("Warning")
            self.sidebar_device_image.setVisible(False)
            self.sidebar_device_name.setText(f"{observed_count} Android devices")
            self.sidebar_device_detail.setText("Choose one in Command Deck")
        else:
            self.connection_state.setText("⌁  No device connected")
            self.connection_state.setObjectName("Warning")
            self.connection_device.setText("Device: —")
            self.connection_android.setText("Android —")
            self._device_uptime_seconds = None
            self._device_uptime_seen_at = time.monotonic()
            self.sidebar_device_state.setText("●  No device connected")
            self.sidebar_device_state.setObjectName("Warning")
            self.sidebar_device_image.setVisible(False)
            self.sidebar_device_name.setText("Android device")
            self.sidebar_device_detail.setText("Connect via ADB or Fastboot")
        for widget in (
            self.connection_state,
            self.connection_device,
            self.connection_android,
            self.sidebar_device_state,
        ):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _maybe_refresh_device_catalog(self) -> None:
        if (
            self._catalog_auto_attempted
            or not self.app_settings.online_intelligence_enabled
            or not self.device_catalog.needs_refresh()
        ):
            return
        self._catalog_auto_attempted = True
        self._refresh_device_catalog()

    @Slot()
    def _refresh_device_catalog(self) -> None:
        if self.device_catalog_worker is not None:
            return
        if not self.app_settings.online_intelligence_enabled:
            self.device_packs_center.set_catalog_status(self.device_catalog.status())
            return
        self.device_packs_center.set_catalog_checking()
        worker = DeviceCatalogWorker(self.device_catalog)
        self.device_catalog_worker = worker
        worker.signals.complete.connect(
            lambda update, active=worker: self._device_catalog_complete(active, update)
        )
        worker.signals.failed.connect(
            lambda reason, active=worker: self._device_catalog_failed(active, reason)
        )
        worker.signals.cancelled.connect(
            lambda active=worker: self._device_catalog_cancelled(active)
        )
        start_background(worker)

    def _device_catalog_complete(
        self,
        worker: DeviceCatalogWorker,
        update: DeviceCatalogUpdate,
    ) -> None:
        if self.device_catalog_worker is not worker:
            return
        self.device_catalog_worker = None
        if not self.app_settings.online_intelligence_enabled:
            self.device_packs_center.set_catalog_status(self.device_catalog.status())
            return
        try:
            status = self.device_catalog.activate(update)
        except DeviceCatalogError as exc:
            self._device_catalog_activation_failed(str(exc))
            return
        self.device_packs_center.set_catalog_status(status)
        self.knowledge_center.refresh_device_catalog()
        if hasattr(self, "about_page") and self.stack.currentWidget() is self.about_page:
            self._refresh_about_evidence()
        self.notification_center.notify(
            "device.catalog.current",
            "Official Android device IDs updated",
            f"ROMVERSE verified {status.entry_count:,} Google Play catalog rows for read-only "
            "identity matching. Build and flash authority remain locked.",
            NotificationKind.SUCCESS,
        )
        if self.engine is not None:
            QTimer.singleShot(0, self.scan)

    def _device_catalog_activation_failed(self, reason: str) -> None:
        self.device_packs_center.catalog_refresh_failed(reason)
        self.knowledge_center.refresh_device_catalog()
        if hasattr(self, "about_page") and self.stack.currentWidget() is self.about_page:
            self._refresh_about_evidence()

    def _device_catalog_failed(
        self,
        worker: DeviceCatalogWorker,
        reason: str,
    ) -> None:
        if self.device_catalog_worker is not worker:
            return
        self.device_catalog_worker = None
        self._device_catalog_activation_failed(reason)

    def _device_catalog_cancelled(self, worker: DeviceCatalogWorker) -> None:
        if self.device_catalog_worker is not worker:
            return
        self.device_catalog_worker = None
        self.device_packs_center.set_catalog_status(self.device_catalog.status())
        self.knowledge_center.refresh_device_catalog()
        if self.app_settings.online_intelligence_enabled and self.device_catalog.needs_refresh():
            self._catalog_auto_attempted = False
            QTimer.singleShot(0, self._maybe_refresh_device_catalog)

    def _set_sidebar_device_art(self, device: AndroidDevice) -> None:
        kind = _sidebar_device_art_kind(device)
        if kind == "xiaomi-17-pro-max":
            pixmap = self._sidebar_exact_phone_pixmap.scaled(
                60,
                84,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.sidebar_device_image.setAccessibleName(
                f"Verified product image for {device.display_name}"
            )
            self.sidebar_device_image.setToolTip(
                f"Connected device: {device.display_name} • exact Device DNA artwork"
            )
        else:
            pixmap = self._sidebar_generic_phone_pixmap
            self.sidebar_device_image.setAccessibleName(
                f"Generic Android device silhouette for {device.display_name}"
            )
            self.sidebar_device_image.setToolTip(
                f"Connected device: {device.display_name} • exact product artwork unconfirmed"
            )
        self.sidebar_device_image.setPixmap(pixmap)

    @Slot(str)
    def _scan_failed(self, message: str) -> None:
        self.scanning = False
        self.active_worker = None
        self._observed_devices = []
        self._selected_device_serial = ""
        self._scan_failure_count += 1
        self._reconnect_retry_ms = min(30_000, max(3_000, self._reconnect_retry_ms * 2))
        self.timer.setInterval(max(self.scan_interval_seconds * 1000, self._reconnect_retry_ms))
        self.device_center.set_scanning(False)
        self.device_center.set_devices([])
        self.device_center.show_error(message)
        self.companion_center.set_device_snapshot([], scan_error=message)
        self.toolchain_center.set_device_communication_evidence([], scan_error=message)
        self.diagnostics_center.set_scanning(False)
        self.diagnostics_center.set_devices([])
        self.diagnostics_center.show_error(message)
        self.guardian_center.request_refresh()
        self.repair_center.set_devices([])
        self.repair_center.show_error(message)
        self.device_packs_center.set_scanning(False)
        self.device_packs_center.set_devices([])
        self.rom_studio.set_devices([], scan_error=message)
        self.apk_installer.set_devices([])
        self.backup_center.set_devices([])
        self.terminal_center.set_devices([])
        self.galaxy_center.set_devices([])
        self._sync_command_deck_context()
        self.rom_studio.device_scan_finished.emit(False, message)
        connection_copy, sidebar_copy, detail_copy = _device_scan_failure_copy(message)
        recovering = _device_scan_failure_is_transient(message) and self._scan_failure_count < 3
        self.connection_state.setText(connection_copy)
        self.connection_state.setObjectName("Warning" if recovering else "Danger")
        self.connection_device.setText("Device: —")
        self.connection_android.setText("Android —")
        self.sidebar_device_state.setText(sidebar_copy)
        self.sidebar_device_state.setObjectName("Warning" if recovering else "Danger")
        self.sidebar_device_image.setVisible(False)
        self.sidebar_device_name.setText("Android device")
        self.sidebar_device_detail.setText(detail_copy)
        for widget in (
            self.connection_state,
            self.connection_device,
            self.connection_android,
            self.sidebar_device_state,
        ):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        # A periodic timer may have a deliberately long user-selected interval.
        # Schedule one bounded recovery attempt as well so a transient Guardian or
        # USB interruption cannot leave the persistent sidebar red until that timer.
        self._reconnect_timer.start(self._reconnect_retry_ms)
        if self._scan_failure_count == 3:
            self.notification_center.notify(
                "device.connection.attention",
                "Device connection needs attention",
                message,
                NotificationKind.ATTENTION,
            )
        self._finish_local_flash_recovery([])
        self._resume_pending_source_installation_recovery()
        recovery_session = self._recovery_operation_session
        if recovery_session is not None:
            recovery_session.note_scan_unavailable(message)

    def _navigate(self, index: int) -> None:
        if index < 0 or index >= self.stack.count():
            self.notification_center.notify(
                "navigation.invalid-index",
                "ROMVERSE route needs attention",
                "The requested Desktop page is not registered. No workspace or device state changed.",
                NotificationKind.ATTENTION,
            )
            return
        self.stack.setCurrentIndex(index)
        current = self.stack.currentWidget()
        if self.scanning:
            self.device_center.set_scanning(True, show_progress=current is self.device_center)
            self.diagnostics_center.set_scanning(
                True, show_progress=current is self.diagnostics_center
            )
        if self.stack.currentWidget() is self.device_center:
            self._sync_command_deck_context()
            self.device_center.refresh_activity()
        elif self.stack.currentWidget() is self.history_center:
            self.history_center.refresh()
        elif self.stack.currentWidget() is self.activity_center:
            self.activity_center.refresh()
        elif self.stack.currentWidget() is self.backup_center:
            self.backup_center.refresh_local_snapshots()
        elif self.stack.currentWidget() is self.knowledge_center:
            self.knowledge_center.clear_source_context()
            self.knowledge_center.refresh_synapse_memory()
        elif self.stack.currentWidget() is self.guardian_center:
            self._revalidate_guardian_review_contexts()
            self.guardian_center.request_refresh()
        elif self.stack.currentWidget() is self.live_console:
            self.live_console.refresh()
        elif self.stack.currentWidget() is self.nexus_center:
            self.nexus_center.refresh()
        elif self.stack.currentWidget() is self.galaxy_center:
            self.galaxy_center.refresh()
        elif self.stack.currentWidget() is self.about_page:
            self._refresh_about_evidence()
        active_button: QPushButton | None = None
        for button in self.nav_buttons:
            active = button.property("page_index") == index
            button.setProperty("active", active)
            if active:
                active_button = button
            icon_name, icon_start, icon_end = self._nav_icon_specs[button]
            button.setIcon(sidebar_icon(icon_name, 26, icon_start, icon_end, active=active))
            button.style().unpolish(button)
            button.style().polish(button)
        if active_button is not None:
            self.nav_scroll.ensureWidgetVisible(active_button, 0, 24)
        route = self._route_by_page_index.get(index)
        if route is not None:
            self._update_workspace_breadcrumb(route)

    @Slot()
    def _refresh_about_evidence(self) -> None:
        """Recalculate About facts from the services that own each local record."""

        self.guardian_center.invalidate_dashboard_if_evidence_changed()
        guardian_state, guardian_detail, guardian_verified = (
            self.guardian_center.current_dashboard_state()
        )
        registry = self.device_packs_center.registry
        catalog_status = self.device_catalog.status()
        archive_metrics = catalog_metrics(ARCHIVE_ARTICLES)
        tool_statuses = self.toolchain_center.statuses
        try:
            events = self.nexus_events.list_recent()
        except LiveConsoleStoreError:
            events = ()
            live_ledger_valid = False
        else:
            live_ledger_valid = True
        self.about_page.set_runtime_evidence(
            AboutRuntimeEvidence(
                device_pack_count=len(registry.packs),
                device_pack_issue_count=len(registry.issues),
                catalog_valid=catalog_status.valid,
                catalog_fresh=catalog_status.fresh,
                catalog_entry_count=(catalog_status.entry_count if catalog_status.valid else 0),
                catalog_reason=catalog_status.reason,
                archive_guide_count=archive_metrics["guides"],
                archive_known_fix_count=archive_metrics["known_fixes"],
                archive_category_count=archive_metrics["categories"],
                project_count=len(self.rom_studio.store.list_projects()),
                tool_ready_count=sum(status.available for status in tool_statuses),
                tool_count=len(tool_statuses),
                live_ledger_valid=live_ledger_valid,
                live_event_count=len(events),
                live_active_count=sum(event.state is MissionState.RUNNING for event in events),
                guardian_state=guardian_state,
                guardian_detail=guardian_detail,
                guardian_verified=guardian_verified,
            )
        )

    @Slot(str, str, bool)
    def _guardian_dashboard_state_changed(
        self,
        state: str,
        detail: str,
        verified: bool,
    ) -> None:
        """Publish Guardian's one truth state to every visible summary surface."""

        self.device_center.set_guardian_state(state, detail, verified)
        if hasattr(self, "about_page") and self.stack.currentWidget() is self.about_page:
            self._refresh_about_evidence()

    def _navigate_route(self, route: str) -> bool:
        """Open one stable Desktop route or report the broken integration visibly."""

        index = self.page_routes.get(route, -1)
        if index < 0:
            safe_key = (
                "".join(
                    character if character.isalnum() or character in "._-" else "-"
                    for character in route.casefold()
                )[:60].strip("-")
                or "unknown"
            )
            self.notification_center.notify(
                f"navigation.missing.{safe_key}",
                "Feature route needs attention",
                f"ROMVERSE could not open the requested {route.replace('_', ' ')} page. "
                "No workspace or device state changed.",
                NotificationKind.ATTENTION,
            )
            return False
        self._navigate(index)
        return True

    @Slot(str, str)
    def _open_live_console_source(self, route: str, project_id: str) -> None:
        """Return one genuine console event to its canonical, current source context."""

        owner_route = NESTED_FEATURE_OWNERS.get(route, route)
        if project_id and owner_route in {"nexus", "rom_studio"}:
            try:
                self.rom_studio.store.get(project_id)
            except ProjectError:
                self.live_console.source_handoff_stopped(
                    "The event's project evidence is no longer available"
                )
                return
            if owner_route == "nexus" and not self.nexus_center.open_project(project_id):
                self.live_console.source_handoff_stopped(
                    "Nexus could not bind the event to its exact current project"
                )
                return
            if owner_route == "rom_studio":
                self.rom_studio.refresh(project_id)
        if not self._navigate_feature_route(route):
            self.live_console.source_handoff_stopped(
                "The producing Desktop feature or its exact nested destination is not registered"
            )

    @Slot(str, str, str)
    def _open_activity_source(
        self,
        route: str,
        context_type: str,
        context_id: str,
    ) -> None:
        """Re-verify and restore one privacy-safe Activity Center source context."""

        try:
            source_route, clean_type, clean_id = validate_activity_context(
                route,
                context_type,
                context_id,
            )
        except ActivityStoreError as exc:
            self.activity_center.source_handoff_stopped(str(exc))
            return

        if clean_type == "rom-project":
            try:
                self.rom_studio.store.get(clean_id)
            except ProjectError:
                self.activity_center.source_handoff_stopped(
                    "The event's exact ROM project evidence is no longer available"
                )
                return
            self.rom_studio.refresh(clean_id)
        elif clean_type == "diagnostic-snapshot":
            if not self.history_center.open_snapshot(clean_id):
                self.activity_center.source_handoff_stopped(
                    "The event's exact diagnostic snapshot is missing, legacy, or failed integrity verification"
                )
                return
        elif clean_type == "backup-plan":
            if not self.backup_center.open_backup_plan(clean_id):
                self.activity_center.source_handoff_stopped(
                    "The event's exact recovery-readiness plan is missing, legacy, or failed integrity verification"
                )
                return
        elif clean_type == "time-machine-snapshot":
            project_id, snapshot_id = clean_id.rsplit(".", 1)
            if not self.backup_center.open_snapshot(project_id, snapshot_id):
                self.activity_center.source_handoff_stopped(
                    "The event's exact Time Machine snapshot is missing, legacy, or failed record verification"
                )
                return
        elif clean_type == "project-vault-entry":
            project_id, entry_id = clean_id.rsplit(".", 1)
            if not self.backup_center.open_vault_entry(project_id, entry_id):
                self.activity_center.source_handoff_stopped(
                    "The event's exact Project Vault entry is missing or failed integrity validation"
                )
                return
        elif clean_type == "repair-session":
            if not self.repair_center.open_session(clean_id):
                self.activity_center.source_handoff_stopped(
                    "The event's exact guided repair session is missing or failed integrity verification"
                )
                return
        elif clean_type == "apk-install-receipt":
            if not self.apk_installer.open_install_receipt(clean_id):
                self.activity_center.source_handoff_stopped(
                    "The event's exact APK install receipt is missing, legacy, or failed integrity verification"
                )
                return
        elif clean_type == "galaxy-topic":
            if not self.galaxy_center.open_topic(clean_id):
                self.activity_center.source_handoff_stopped(
                    "The event's exact local Galaxy topic is missing or failed integrity verification"
                )
                return
        else:
            self.activity_center.source_handoff_stopped(
                "The event's source context is not supported by this ROMVERSE build"
            )
            return

        if not self._navigate_route(source_route):
            self.activity_center.source_handoff_stopped(
                "The producing Desktop feature is not registered"
            )
            return
        if clean_type == "galaxy-topic" and not self.galaxy_center.open_topic(clean_id):
            # Galaxy is refreshed when its page opens. Revalidate once more after that
            # refresh so an external edit cannot swap or remove the selected local topic
            # between the source check and the visible destination.
            self._navigate_route("activity_center")
            self.activity_center.source_handoff_stopped(
                "The event's exact local Galaxy topic changed while the handoff was opening"
            )

    @Slot()
    def _open_current_health_review(self) -> None:
        """Return from historical evidence to the current owner-controlled health report."""

        if self._navigate_route("quantum_optimizer"):
            self.diagnostics_center.open_dashboard_intent("Health Review")

    @Slot(str, str)
    def _continue_device_atlas_rom_studio(
        self,
        report_id: str,
        report_digest: str,
    ) -> None:
        """Start Genesis with the exact current Device Atlas evidence."""

        report = self.device_packs_center.active_report
        pack = self.device_packs_center.active_pack
        device = self.device_packs_center.active_device
        current_project = self.rom_studio.current_project
        if (
            pack is not None
            and current_project is not None
            and current_project.device_pack_id != pack.pack_id
        ):
            matching_projects = tuple(
                project
                for project in self.rom_studio.store.list_projects()
                if project.device_pack_id == pack.pack_id
            )
            if len(matching_projects) == 1:
                self.rom_studio.refresh(matching_projects[0].project_id)
            elif len(matching_projects) > 1:
                labels = tuple(
                    f"{project.name}  •  {project.project_id}  •  "
                    f"{project.original.original_name if project.original is not None else 'firmware not imported'}"
                    for project in matching_projects
                )
                choice, accepted = QInputDialog.getItem(
                    self,
                    "Choose ROM Mission project",
                    "More than one saved project matches this phone. Choose the project to continue:",
                    labels,
                    0,
                    False,
                )
                if not accepted:
                    self.device_packs_center.next_action_handoff_stopped(
                        "Project choice cancelled — Device Intelligence and saved projects are unchanged"
                    )
                    return
                if choice not in labels:
                    self.device_packs_center.next_action_handoff_stopped(
                        "The selected ROM project no longer matches the current saved choices"
                    )
                    return
                self.rom_studio.refresh(matching_projects[labels.index(choice)].project_id)
            else:
                self.device_packs_center.next_action_handoff_stopped(
                    "No saved ROM project matches this phone's current Device Pack; create a new project from ROM Studio"
                )
                return
        profile = self.device_packs_center.active_device_dna
        project = self.rom_studio.current_project
        stored_profile = (
            self.rom_studio.device_dna.profiles.load(project.project_id)
            if project is not None and project.original is not None
            else None
        )
        matrix = (
            self.rom_studio.compatibility.matrices.load(project.project_id)
            if stored_profile is not None
            else None
        )
        if (
            report is None
            or pack is None
            or device is None
            or report.report_id != report_id
            or report.report_digest != report_digest
            or report.pack_id != pack.pack_id
            or report.pack_version != pack.version
            or report.pack_sha256 != pack.sha256
            or report.manufacturer.casefold() != (device.manufacturer or "Unknown OEM").casefold()
            or report.model.casefold() != (device.model or "Unknown model").casefold()
            or report.product.casefold() != (device.product or "Unknown product").casefold()
            or report.codename.casefold()
            != (device.codename or device.product or "Unknown codename").casefold()
            or (stored_profile is not None and profile != stored_profile)
            or (
                profile is not None
                and not self.device_packs_center._profile_matches_device(profile, device)
            )
            or (
                matrix is not None
                and (profile is None or matrix.device_dna_digest != profile.profile_digest)
            )
        ):
            self.device_packs_center.next_action_handoff_stopped(
                "Start ROM Mission no longer matches the current device intelligence"
            )
            return
        if not self._navigate_route("rom_studio"):
            return
        if not self.rom_studio.open_device_atlas_handoff(
            report,
            "genesis",
            device=device,
            device_dna=profile,
            compatibility=matrix,
            launch_genesis=True,
        ):
            self._navigate_route("device_atlas")
            self.device_packs_center.next_action_handoff_stopped(
                "ROM Studio rejected changed or invalid Device Atlas evidence"
            )

    @Slot(str, str)
    def _return_time_machine_rom_studio(
        self,
        report_id: str,
        report_digest: str,
    ) -> None:
        """Return an unmet stock-recovery lane to Studio with its exact current report."""

        report = self.device_packs_center.active_report
        pack = self.device_packs_center.active_pack
        device = self.device_packs_center.active_device
        stock = (
            next(
                (check for check in report.checks if check.check_id == "stock-recovery-route"),
                None,
            )
            if report is not None
            else None
        )
        if (
            report is None
            or pack is None
            or device is None
            or self.backup_center.device_atlas_report_identity != (report_id, report_digest)
            or report.report_id != report_id
            or report.report_digest != report_digest
            or report.pack_id != pack.pack_id
            or report.pack_version != pack.version
            or report.pack_sha256 != pack.sha256
            or report.manufacturer != device.manufacturer
            or report.model != device.model
            or report.product != device.product
            or report.codename != device.codename
            or not report.build_contract_ready
            or report.flash_contract_ready
            or stock is None
            or stock.state is ValidationState.PASS
        ):
            self.backup_center.rom_studio_handoff_stopped(
                "The retained report no longer matches the current phone, exact Pack, or stock-recovery gate"
            )
            return
        if not self.rom_studio.open_device_atlas_handoff(
            report,
            "genesis",
            source="Time Machine",
        ):
            self.backup_center.rom_studio_handoff_stopped(
                "ROM Studio rejected the changed or incomplete exact build contract"
            )
            return
        self._navigate_route("rom_studio")

    @Slot(str)
    def _open_time_machine_rom_studio_setup(self, project_id: str) -> None:
        """Carry Time Machine's exact missing local-baseline prerequisite into Studio."""

        requested = str(project_id).strip()
        current = str(self.backup_center.project_selector.currentData() or "").strip()
        projects = self.backup_center.rom_store.list_projects()
        if requested:
            snapshots = self.backup_center.rom_store.list_snapshots(requested)
            valid = (
                current == requested
                and any(project.project_id == requested for project in projects)
                and not snapshots
            )
        else:
            valid = not current and not projects
        if not valid or not self.rom_studio.open_time_machine_setup_handoff(requested):
            self.backup_center.rom_studio_setup_handoff_stopped(
                "The displayed project or snapshot state changed before ROM Studio opened"
            )
            return
        self._navigate_route("rom_studio")

    @Slot(str, str)
    def _open_nexus_rom_studio(self, project_id: str, plan_digest: str) -> None:
        """Carry the selected Nexus project back to its exact ROM Studio evidence."""

        selected = self.nexus_center.project_selector.currentData()
        current_project_id = selected if isinstance(selected, str) else ""
        trusted = self.nexus_center.planner.plans.load(project_id) if project_id else None
        displayed = self.nexus_center.current_plan
        if (
            project_id != current_project_id
            or bool(plan_digest)
            != bool(displayed is not None and displayed.project_id == project_id)
            or (
                plan_digest
                and (
                    trusted is None
                    or displayed is None
                    or trusted.plan_digest != plan_digest
                    or displayed.plan_digest != plan_digest
                    or trusted.execution_authorized
                    or trusted.bootloader_relock_permitted
                )
            )
            or not self.rom_studio.open_nexus_handoff(project_id, plan_digest)
        ):
            self.nexus_center.status.setText(
                "ROM STUDIO HANDOFF STOPPED  •  The requested project or plan no longer matches "
                "the current Nexus evidence  •  "
                "No project worker, plan, build, or phone action started"
            )
            self.nexus_center.status.setObjectName("Danger")
            self.nexus_center._repolish(self.nexus_center.status)
            return
        self._navigate_route("rom_studio")

    @Slot(str, str, str, str)
    def _open_device_pack_next_action(
        self,
        route: str,
        article_key: str,
        check_id: str,
        report_digest: str,
    ) -> None:
        """Revalidate the current readiness advice before opening its zero-authority route."""

        report = self.device_packs_center.active_report
        action = self.device_packs_center.active_next_action
        if (
            report is None
            or action is None
            or report.report_digest != report_digest
            or action.route != route
            or action.article_key != article_key
            or action.check_id != check_id
        ):
            self.device_packs_center.next_action_handoff_stopped(
                "The requested readiness action no longer matches the current Device Pack report"
            )
            return
        if route == "archives":
            if not article_key or article_for_key(article_key) is None:
                self.device_packs_center.next_action_handoff_stopped(
                    "The exact verified Archives guide is unavailable"
                )
                return
            self._navigate_route("archives")
            if not self.knowledge_center.open_article(article_key, source_route="device_atlas"):
                self.device_packs_center.next_action_handoff_stopped(
                    "The exact verified Archives guide is unavailable"
                )
                return
            return
        if route == "time_machine":
            if not self.backup_center.open_device_atlas_readiness(report):
                self.device_packs_center.next_action_handoff_stopped(
                    "Time Machine rejected readiness context that is not a current stock-recovery gate"
                )
                return
            self._navigate_route("time_machine")
            return
        if route == "rom_studio":
            if not self.rom_studio.open_device_atlas_handoff(report, "build"):
                self.device_packs_center.next_action_handoff_stopped(
                    "ROM Studio rejected a changed or incomplete exact build contract"
                )
                return
            self._navigate_route("rom_studio")
            return
        self.device_packs_center.next_action_handoff_stopped(
            "The advised Desktop destination is not an approved readiness route"
        )

    @Slot(str, str, str, str)
    def _open_device_requirement(
        self,
        lane_id: str,
        route: str,
        article_key: str,
        report_digest: str,
    ) -> None:
        """Re-derive one requirements lane before opening its connected Desktop feature."""

        blueprint = self.device_packs_center.current_requirements()
        report = self.device_packs_center.active_report
        pack = self.device_packs_center.active_pack
        lane = blueprint.lane(lane_id) if blueprint is not None else None
        if (
            blueprint is None
            or report is None
            or pack is None
            or lane is None
            or blueprint.report_digest != report_digest
            or lane.route != route
            or lane.article_key != article_key
        ):
            self.device_packs_center.requirement_handoff_stopped(
                lane_id,
                "The requested lane no longer matches the current automatic requirements blueprint",
            )
            return
        if route == "archives":
            if not article_key or article_for_key(article_key) is None:
                self.device_packs_center.requirement_handoff_stopped(
                    lane_id,
                    "The exact verified requirements guide is unavailable",
                )
                return
            self._navigate_route("archives")
            if not self.knowledge_center.open_article(
                article_key,
                source_route="device_atlas",
            ):
                self.device_packs_center.requirement_handoff_stopped(
                    lane_id,
                    "The exact verified requirements guide is unavailable",
                )
            return
        if route == "forge_arsenal":
            if not self._open_device_pack_toolchain(
                pack.pack_id,
                pack.sha256,
                report.report_digest,
            ):
                self.device_packs_center.requirement_handoff_stopped(
                    lane_id,
                    "Forge Arsenal rejected requirements that are not bound to the current exact Pack",
                )
            return
        if route == "forge_arsenal_project":
            context = self._current_studio_toolchain_context(blueprint.project_id)
            if (
                not blueprint.project_scoped
                or context is None
                or context.source_sha256 != blueprint.project_source_sha256
                or context.source_kind != blueprint.source_kind
                or context.source_blueprint_digest != blueprint.source_blueprint_digest
                or context.source_plan_digest != blueprint.source_plan_digest
                or context.required_tools != blueprint.source_required_tools
                or not self.toolchain_center.open_studio_project_context(context)
            ):
                self.device_packs_center.requirement_handoff_stopped(
                    lane_id,
                    "Forge Arsenal rejected changed project, source-blueprint, or tool evidence",
                )
                return
            self._navigate_route("forge_arsenal")
            return
        if route == "time_machine":
            if not self.backup_center.open_device_atlas_readiness(report):
                self.device_packs_center.requirement_handoff_stopped(
                    lane_id,
                    "Time Machine rejected a flash lane that is not the current stock-recovery gate",
                )
                return
            self._navigate_route("time_machine")
            return
        if route == "rom_studio":
            intent = "artifact" if lane_id == "flash" else "build"
            if not self.rom_studio.open_device_atlas_handoff(report, intent):
                self.device_packs_center.requirement_handoff_stopped(
                    lane_id,
                    "ROM Studio rejected a changed or incomplete exact requirements contract",
                )
                return
            self._navigate_route("rom_studio")
            return
        if route == "rom_studio_project":
            intent = "artifact" if lane_id == "flash" else "build"
            if not self.rom_studio.open_device_atlas_source_handoff(
                blueprint.project_id,
                blueprint.project_source_sha256,
                blueprint.source_blueprint_digest,
                blueprint.source_plan_digest,
                blueprint.source_kind,
                intent,
            ):
                self.device_packs_center.requirement_handoff_stopped(
                    lane_id,
                    "ROM Studio rejected changed project or source-blueprint evidence",
                )
                return
            self._navigate_route("rom_studio")
            return
        self.device_packs_center.requirement_handoff_stopped(
            lane_id,
            "The requirements lane does not name an approved Desktop destination",
        )

    def _current_device_pack_toolchain_context(
        self,
        pack_id: str,
        pack_sha256: str,
        report_digest: str,
    ) -> DevicePackToolchainContext | None:
        """Resolve exact current Pack/tool evidence without trusting a retained UI request."""

        report = self.device_packs_center.active_report
        pack = self.device_packs_center.active_pack
        device = self.device_packs_center.active_device
        if (
            report is None
            or pack is None
            or device is None
            or pack.build_contract is None
            or report.pack_id != pack.pack_id
            or report.pack_version != pack.version
            or report.pack_sha256 != pack.sha256
            or pack.pack_id != pack_id
            or pack.sha256 != pack_sha256
            or report.report_digest != report_digest
            or report.manufacturer != device.manufacturer
            or report.model != device.model
            or report.product != device.product
            or report.codename != device.codename
        ):
            return None
        return DevicePackToolchainContext(
            report_digest=report.report_digest,
            pack_id=pack.pack_id,
            pack_sha256=pack.sha256,
            pack_name=pack.display_name,
            model=report.model,
            codename=report.codename,
            required_tools=pack.build_contract.required_tools,
            build_contract_ready=report.build_contract_ready,
            flash_contract_ready=report.flash_contract_ready,
        )

    def _open_device_pack_toolchain(
        self,
        pack_id: str,
        pack_sha256: str,
        report_digest: str,
    ) -> bool:
        context = self._current_device_pack_toolchain_context(
            pack_id,
            pack_sha256,
            report_digest,
        )
        if context is None or not self.toolchain_center.open_device_pack_context(context):
            return False
        self._navigate_route("forge_arsenal")
        return True

    @Slot(str, str, str)
    def _return_forge_device_atlas(
        self,
        pack_id: str,
        pack_sha256: str,
        report_digest: str,
    ) -> None:
        """Return Forge to the exact current Device Atlas Pack/report relationship."""

        context = self._current_device_pack_toolchain_context(
            pack_id,
            pack_sha256,
            report_digest,
        )
        if (
            context is None
            or not self.toolchain_center.device_pack_context_matches(context)
            or not self.device_packs_center.open_forge_return(
                pack_id,
                pack_sha256,
                report_digest,
            )
        ):
            self.toolchain_center.device_pack_context_changed(
                "The return request no longer matches the current phone, exact Pack, or readiness report"
            )
            return
        self._navigate_route("device_atlas")

    @Slot(str, str, str)
    def _setup_device_pack_toolchain(
        self,
        pack_id: str,
        pack_sha256: str,
        report_digest: str,
    ) -> None:
        context = self._current_device_pack_toolchain_context(
            pack_id,
            pack_sha256,
            report_digest,
        )
        if context is None or not self.toolchain_center.device_pack_context_matches(context):
            self.toolchain_center.device_pack_context_changed(
                "Device Atlas evidence changed after this Forge view was opened"
            )
            return
        self.toolchain_center.open_device_pack_setup(context)

    @Slot(str, str, str)
    def _continue_device_pack_toolchain(
        self,
        pack_id: str,
        pack_sha256: str,
        report_digest: str,
    ) -> None:
        context = self._current_device_pack_toolchain_context(
            pack_id,
            pack_sha256,
            report_digest,
        )
        if context is None or not self.toolchain_center.device_pack_context_matches(context):
            self.toolchain_center.device_pack_context_changed(
                "Device Atlas evidence changed after this Forge view was opened"
            )
            return
        if not context.build_contract_ready:
            self.toolchain_center.device_pack_handoff_stopped(
                "The exact host tools cannot replace an unresolved Device Pack build gate"
            )
            return
        if not self.toolchain_center.device_pack_requirements_ready():
            self.toolchain_center.device_pack_handoff_stopped(
                "One or more exact host requirements are no longer verified"
            )
            return
        self.rom_studio.set_tool_statuses(self.toolchain_center.statuses)
        report = self.device_packs_center.active_report
        if report is None or not self.rom_studio.open_device_atlas_handoff(
            report,
            "build",
            source="Forge Arsenal",
        ):
            self.toolchain_center.device_pack_handoff_stopped(
                "ROM Studio rejected changed Pack or host-tool evidence"
            )
            return
        self._navigate_route("rom_studio")

    @Slot(str, str)
    def _open_nexus_guardian_review(self, project_id: str, plan_digest: str) -> None:
        """Revalidate a zero-authority Nexus plan before showing Guardian context."""

        trusted = self.nexus_center.planner.plans.load(project_id)
        try:
            project = self.rom_studio.store.get(project_id)
        except ProjectError:
            project = None
        if (
            trusted is None
            or project is None
            or trusted.plan_digest != plan_digest
            or not trusted.ready_for_guardian_review
            or trusted.execution_authorized
            or trusted.bootloader_relock_permitted
            or not self.guardian_center.open_nexus_review(trusted, project.name)
        ):
            self.nexus_center.guardian_handoff_stopped(
                "The requested plan identity did not match current source-bound evidence. "
                "Refresh the Nexus plan; no approval or execution was created."
            )
            return
        self._navigate_route("guardian_core")

    @Slot(str, str)
    def _open_backup_guardian_review(self, plan_id: str, plan_digest: str) -> None:
        """Revalidate one recovery plan before showing evidence-only Guardian context."""

        trusted = self.backup_center.plan_store.load_latest()
        data = trusted.data
        if (
            not trusted.valid
            or not trusted.integrity_verified
            or not isinstance(data, dict)
            or data.get("plan_id") != plan_id
            or data.get("plan_digest") != plan_digest
            or not self.guardian_center.open_backup_review(trusted)
        ):
            self.backup_center.guardian_handoff_stopped(
                "The requested recovery plan did not match the latest integrity-verified evidence"
            )
            return
        self._navigate_route("guardian_core")

    @Slot(str, str)
    def _return_guardian_nexus(self, project_id: str, plan_digest: str) -> None:
        """Restore Guardian's retained plan to the exact current Nexus project."""

        trusted = self.nexus_center.planner.plans.load(project_id)
        try:
            self.rom_studio.store.get(project_id)
        except (OSError, ProjectError, TypeError, ValueError):
            trusted = None
        if (
            trusted is None
            or trusted.plan_digest != plan_digest
            or not trusted.ready_for_guardian_review
            or trusted.execution_authorized
            or trusted.bootloader_relock_permitted
            or not self.nexus_center.open_project(project_id)
            or self.nexus_center.current_plan is None
            or self.nexus_center.current_plan.plan_digest != plan_digest
        ):
            self.guardian_center.nexus_review_stopped(
                "The saved plan no longer matches the current source-bound Nexus evidence."
            )
            return
        self._navigate_route("nexus")

    @Slot(str, str)
    def _return_guardian_time_machine(self, plan_id: str, plan_digest: str) -> None:
        """Restore Guardian's retained recovery plan to the exact verified record."""

        trusted = self.backup_center.plan_store.load_latest()
        data = trusted.data
        if (
            not trusted.valid
            or not trusted.integrity_verified
            or not isinstance(data, dict)
            or data.get("plan_id") != plan_id
            or data.get("plan_digest") != plan_digest
            or data.get("execution_locked") is not True
            or data.get("execution_authority") != "none"
            or data.get("phone_data_copied") is not False
            or not self.backup_center.open_backup_plan(plan_id)
        ):
            self.guardian_center.backup_review_stopped(
                "The saved recovery plan no longer matches the latest integrity-verified evidence."
            )
            return
        self._navigate_route("time_machine")

    def _current_studio_guardian_manifest(
        self,
        project_id: str,
        manifest_digest: str,
    ) -> GuardianManifestReview | None:
        """Reload and revalidate a Studio manifest against current phone/readiness evidence."""

        service = GuardianManifestReviewService(
            self.rom_studio.store,
            self.rom_studio.pack_registry,
        )
        manifest = service.load(project_id)
        if manifest is None or manifest.manifest_digest != manifest_digest:
            return None
        readiness = BuildReadinessService(
            self.rom_studio.store,
            self.rom_studio.pack_registry,
            self.rom_studio.tool_statuses,
            self.rom_studio.attestation_store,
        )
        for device in self.rom_studio.devices:
            try:
                report = readiness.assess(project_id, (device,), persist=False)
            except (OSError, ProjectError, TypeError, ValueError):
                continue
            if service.matches_current(manifest, report, device):
                return manifest
        return None

    @Slot(str, str)
    def _open_studio_guardian_review(
        self,
        project_id: str,
        manifest_digest: str,
    ) -> None:
        """Open one freshly revalidated Studio manifest in persistent Guardian Core."""

        manifest = self._current_studio_guardian_manifest(project_id, manifest_digest)
        try:
            project = self.rom_studio.store.get(project_id)
        except ProjectError:
            project = None
        plan, contract = (
            self.rom_studio.guardian_execution_context(manifest)
            if manifest is not None
            else (None, None)
        )
        if (
            manifest is None
            or project is None
            or not self.guardian_center.open_studio_review(
                manifest,
                project.name,
                plan,
                contract,
            )
        ):
            self.rom_studio.outbound_handoff_stopped(
                "Guardian Core",
                "The requested manifest no longer matches current project, phone, or readiness evidence",
            )
            return
        self._navigate_route("guardian_core")

    @Slot(str, str)
    def _return_guardian_rom_studio(
        self,
        project_id: str,
        manifest_digest: str,
    ) -> None:
        """Return a current Guardian card to the exact Studio project and command group."""

        manifest = self._current_studio_guardian_manifest(project_id, manifest_digest)
        if manifest is None or not self.rom_studio.open_guardian_handoff(manifest):
            self.guardian_center.studio_review_stopped(
                "The saved manifest no longer matches current project, phone, or readiness evidence."
            )
            return
        self._navigate_route("rom_studio")

    def _revalidate_guardian_review_contexts(self) -> None:
        """Expire retained review cards when their exact evidence identity changes."""

        identity = self.guardian_center.nexus_review_identity
        if identity is not None:
            project_id, plan_digest = identity
            trusted = self.nexus_center.planner.plans.load(project_id)
            if (
                trusted is None
                or trusted.plan_digest != plan_digest
                or not trusted.ready_for_guardian_review
                or trusted.execution_authorized
                or trusted.bootloader_relock_permitted
            ):
                self.guardian_center.nexus_review_stopped(
                    "The saved plan no longer matches current source-bound evidence."
                )
        backup_identity = self.guardian_center.backup_review_identity
        if backup_identity is not None:
            backup_plan_id, backup_digest = backup_identity
            loaded = self.backup_center.plan_store.load_latest()
            data = loaded.data
            if (
                not loaded.valid
                or not loaded.integrity_verified
                or not isinstance(data, dict)
                or data.get("plan_id") != backup_plan_id
                or data.get("plan_digest") != backup_digest
            ):
                self.guardian_center.backup_review_stopped(
                    "The saved recovery plan no longer matches the latest integrity-verified evidence."
                )
        studio_identity = self.guardian_center.studio_review_identity
        if (
            studio_identity is not None
            and self._current_studio_guardian_manifest(*studio_identity) is None
        ):
            self.guardian_center.studio_review_stopped(
                "The saved Studio manifest no longer matches current project, phone, or readiness evidence."
            )
        recovery_identity = self.guardian_center.recovery_review_identity
        preparation_digest = self.guardian_center.recovery_preparation_digest
        if recovery_identity is not None and preparation_digest:
            preparation = self.guardian_center.recovery_preparation
            if preparation is None or preparation.preparation_digest != preparation_digest:
                self.guardian_center.recovery_review_stopped(
                    "The sealed Recovery preparation is no longer available."
                )
                return
            reviewed_device = self._current_recovery_reviewed_device(preparation.device_key)
            if reviewed_device is None:
                self.guardian_center.recovery_live_target_unavailable()
                return
            current = GuardianRecoveryPreparationService(
                self.rom_studio.store,
                self.rom_studio.pack_registry,
                self.repair_center.autopilot_service,
            ).load(*recovery_identity, [reviewed_device])
            if current is None or current.preparation_digest != preparation_digest:
                self.guardian_center.recovery_review_stopped(
                    "The exact phone, project, source, Device Pack, evidence, or prepared route is no longer current."
                )
            else:
                self.guardian_center.revalidate_recovery_live_target(current, reviewed_device)

    def _navigation_commands(self) -> tuple[NavigationCommand, ...]:
        """Expose pages and exact nested features available in the current experience."""

        commands: list[NavigationCommand] = []
        included: set[str] = set()
        for button in self.nav_buttons:
            if button.property("expert_only") and button.isHidden():
                continue
            route = button.property("route_key")
            if not isinstance(route, str) or route not in FEATURES:
                continue
            name = feature(route)
            commands.append(NavigationCommand(route, name.title, name.subtitle, name.legacy))
            included.add(route)
        for route in NESTED_FEATURE_OWNERS:
            if route in included or (
                route in EXPERT_ONLY_NESTED_FEATURES
                and self._experience_mode is not ExperienceMode.EXPERT
            ):
                continue
            name = feature(route)
            commands.append(NavigationCommand(route, name.title, name.subtitle, name.legacy))
        return tuple(commands)

    @Slot(str)
    def _navigate_feature_route(self, route: str) -> bool:
        """Resolve a palette destination to its exact owner without starting work."""

        if route in self.page_routes:
            return self._navigate_route(route)
        owner_route = NESTED_FEATURE_OWNERS.get(route)
        if owner_route is None:
            return False
        if not self._navigate_route(owner_route):
            return False
        if owner_route == "command_deck":
            opened = self.device_center.open_feature_destination(route)
        elif owner_route == "quantum_optimizer":
            opened = self.diagnostics_center.open_dashboard_intent(feature(route).title)
        elif owner_route == "rom_studio":
            opened = self.rom_studio.open_feature_destination(route)
        elif owner_route == "recovery_bay":
            opened = self.repair_center.open_feature_destination(route)
        elif owner_route == "archives":
            opened = self.knowledge_center.open_feature_destination(route)
        elif owner_route == "nexus":
            opened = self.nexus_center.open_feature_destination(route)
        else:
            opened = False
        if opened:
            return True
        self.notification_center.notify(
            f"navigation.feature.{route}",
            "Feature destination needs attention",
            f"ROMVERSE opened {feature(owner_route).title}, but {feature(route).title} could not "
            "revalidate its exact local destination. No worker or phone action started.",
            NotificationKind.ATTENTION,
        )
        return False

    @Slot()
    def _open_command_palette(self) -> None:
        if self._command_palette is not None:
            self._command_palette.raise_()
            self._command_palette.activateWindow()
            self._command_palette.search.setFocus()
            return
        dialog = CommandPaletteDialog(self._navigation_commands(), self)
        self._command_palette = dialog
        dialog.navigation_requested.connect(self._navigate_feature_route)
        dialog.finished.connect(lambda _result, opened=dialog: self._command_palette_closed(opened))
        dialog.open()

    def _command_palette_closed(self, dialog: CommandPaletteDialog) -> None:
        if self._command_palette is dialog:
            self._command_palette = None

    @Slot(object)
    def _set_experience_mode_from_studio(self, mode: object) -> None:
        """Persist the deliberate Architect control without weakening Guardian."""

        try:
            selected = ExperienceMode(mode)
        except (TypeError, ValueError):
            self.rom_studio.set_experience_mode(self._experience_mode)
            return
        changed = selected is not self.app_settings.experience_mode
        if changed:
            self.app_settings = replace(
                self.app_settings,
                schema_version=5,
                experience_mode=selected,
            )
            self.rom_studio.app_settings = self.app_settings
        self._apply_experience_mode(selected)
        if changed:
            self.settings_changed.emit(self.app_settings)

    def _apply_experience_mode(self, mode: ExperienceMode) -> None:
        """Reveal specialist surfaces without mutating the active workspace or route."""

        self._experience_mode = mode
        expert = mode is ExperienceMode.EXPERT
        mode_text = "EXPERT  •  ARCHITECT" if expert else "GUIDED  •  ARCANA"
        self.experience_badge.setProperty("expanded_text", mode_text)
        self.experience_badge.setAccessibleName(
            "Experience mode: Expert Architect" if expert else "Experience mode: Guided Arcana"
        )
        self.experience_badge.setText(
            mode_text[:1] if self._workspace_shell_state.navigation_collapsed else mode_text
        )
        self.experience_badge.setToolTip(
            "Expert Mode reveals specialist tools after risk acceptance. Guided Guardian "
            "sequencing is off; exact target, integrity, and command-validity guards remain active."
            if expert
            else "Guided Mode keeps the next safe action prominent and folds specialist tools."
        )
        for button in self.nav_buttons:
            if button.property("expert_only"):
                button.setVisible(expert)
        self.device_center.set_experience_mode(mode)
        self.diagnostics_center.set_experience_mode(mode)
        self.guardian_center.set_experience_mode(mode)
        self.rom_studio.set_experience_mode(mode)
        if self._local_flash_dialog is not None and hasattr(
            self._local_flash_dialog, "set_experience_mode"
        ):
            self._local_flash_dialog.set_experience_mode(mode)

    @Slot(str, object)
    def _record_rom_operation(self, operation: str, _result: object) -> None:
        labels = {
            "import": (
                "Protected firmware imported",
                "Source copied, hashed, and preserved as an immutable original.",
            ),
            "verify": (
                "Firmware integrity verified",
                "The protected source still matches its recorded SHA-256.",
            ),
            "inspect": (
                "Firmware structure inspected",
                "Bounded container metadata was inspected; no content was extracted.",
            ),
            "working-copy": (
                "Isolated working tree created",
                "A verified working baseline was created away from the protected original.",
            ),
            "snapshot": (
                "Time Machine snapshot created",
                "The local ROM working baseline was hashed and preserved.",
            ),
            "extract": (
                "Firmware extracted safely",
                "Content was extracted into the isolated project tree.",
            ),
            "plan": (
                "Build dry-run plan generated",
                "A deterministic, execution-locked build plan was recorded.",
            ),
            "verify-plan": (
                "Build plan inputs verified",
                "The extracted tree was checked against its saved plan.",
            ),
            "forge-bundle": (
                "Forge Bundle created and verified",
                "A deterministic, content-addressed working-tree bundle was saved as unsigned and non-flashable.",
            ),
            "verify-forge": (
                "Forge Bundle integrity verified",
                "The archive, safety manifest, exact member set, and file hashes passed verification.",
            ),
            "scan-payload": (
                "OTA payload mapped",
                "Payload metadata and partition evidence were recorded without changing a device.",
            ),
            "extract-payload": (
                "OTA partitions extracted",
                "Selected payload partitions were extracted and source-verified locally.",
            ),
            "expand-filesystem": (
                "Partition filesystem expanded",
                "Browsable content was expanded into the contained ROM tree.",
            ),
            "preview-recipe": (
                "Recipe preview completed",
                "Targets were resolved without applying changes.",
            ),
            "execute-recipe": (
                "Recipe applied and verified",
                "Approved local changes completed with automatic rollback protection.",
            ),
            "rollback-recipe": (
                "Recipe rollback verified",
                "Local targets were restored from the selected snapshot.",
            ),
        }
        title, detail = labels.get(
            operation,
            ("ROM Studio operation completed", operation.replace("-", " ").title()),
        )
        project_id = (
            self.rom_studio.current_project.project_id
            if self.rom_studio.current_project is not None
            else ""
        )
        self._record_activity(
            "rom-studio",
            title,
            detail,
            "success",
            "ROM Studio",
            source_route="rom_studio" if project_id else "",
            context_type="rom-project" if project_id else "",
            context_id=project_id,
        )
        if project_id:
            self.backup_center.capture_operation_checkpoint(project_id, operation)
        self._update_companion_ascension_status()
        self._sync_command_deck_context()

    def _sync_command_deck_context(self) -> None:
        """Project real ROM Studio state into the status-aware home Command Deck."""

        self.guardian_center.invalidate_dashboard_if_evidence_changed()
        project = self.rom_studio.current_project
        self.device_center.set_workspace_context(
            project.name if project is not None else "",
            bool(project is not None and project.original is not None),
            self.rom_studio.genesis_flight_plan(),
        )

    @Slot(str)
    def _live_operation_started(self, operation: str) -> None:
        project_id = (
            self.rom_studio.current_project.project_id
            if self.rom_studio.current_project is not None
            else ""
        )
        title = operation.replace("-", " ").title()
        try:
            event = self.nexus_events.start(
                source="ROM Studio",
                stage=operation,
                title=title,
                summary=f"ROM Studio started {title.casefold()}.",
                explanation=(
                    "This is a real local project operation. Guardian boundaries and protected "
                    "source rules remain active while it runs."
                ),
                next_action="ROMVERSE will report progress and a verified outcome here.",
                project_id=project_id,
                guardian_protected=True,
            )
        except LiveConsoleStoreError:
            return
        self._live_missions[operation] = event.mission_id
        self.live_console.refresh()
        self.device_center.refresh_mission_control()

    @Slot(str, int)
    def _live_operation_progress(self, operation: str, progress: int) -> None:
        mission_id = self._live_missions.get(operation)
        if mission_id is None:
            return
        try:
            self.nexus_events.progress(
                mission_id,
                progress,
                summary=f"ROM Studio is processing {operation.replace('-', ' ')}.",
                next_action="Keep ROMVERSE open while this stage completes.",
            )
        except LiveConsoleStoreError:
            return
        self.live_console.refresh()
        self.device_center.refresh_mission_control()

    @Slot(str, object)
    def _live_operation_completed(self, operation: str, _result: object) -> None:
        title = operation.replace("-", " ").title()
        self.notification_center.notify(
            f"rom-studio.{operation}.completed",
            "ROM Studio stage complete",
            f"{title} completed successfully. Review the verified project evidence before continuing.",
            NotificationKind.SUCCESS,
        )
        mission_id = self._live_missions.pop(operation, None)
        if mission_id is None:
            return
        try:
            self.nexus_events.finish(
                mission_id,
                MissionState.SUCCEEDED,
                summary=f"{title} completed and the producing service reported success.",
                explanation=(
                    "ROMVERSE received the operation result and updated the project from that "
                    "real result; the console did not infer completion from elapsed time."
                ),
                next_action="Review the project evidence and continue to the recommended stage.",
                confidence=MissionConfidence.VERIFIED,
            )
        except LiveConsoleStoreError:
            return
        self.live_console.refresh()
        self.device_center.refresh_mission_control()

    @Slot(str, str)
    def _live_operation_failed(self, operation: str, message: str) -> None:
        safe_message = (
            message.replace("\x00", " ").strip()[:350] or "No failure detail was reported."
        )
        self.notification_center.notify(
            f"rom-studio.{operation}.attention",
            "ROM Studio stopped safely",
            safe_message,
            NotificationKind.ATTENTION,
        )
        mission_id = self._live_missions.pop(operation, None)
        if mission_id is None:
            return
        try:
            self.nexus_events.finish(
                mission_id,
                MissionState.FAILED,
                summary=f"ROM Studio stopped safely: {safe_message}",
                explanation=(
                    "The operation did not report success. Protected originals remain unchanged, "
                    "and ROMVERSE has not advanced this stage."
                ),
                next_action="Review the explanation, let ROMVERSE resolve safe prerequisites, then retry.",
                confidence=MissionConfidence.VERIFIED,
            )
        except LiveConsoleStoreError:
            return
        self.live_console.refresh()
        self.device_center.refresh_mission_control()

    @Slot(object)
    def _record_device_pack_readiness(self, report: object) -> None:
        if not isinstance(report, DevicePackValidationReport):
            return
        if hasattr(self, "toolchain_center"):
            retained_identity = self.toolchain_center.device_pack_context_identity()
            if retained_identity is not None:
                current_context = self._current_device_pack_toolchain_context(
                    report.pack_id,
                    report.pack_sha256,
                    report.report_digest,
                )
                if current_context is None or not self.toolchain_center.rebind_device_pack_context(
                    current_context
                ):
                    self.toolchain_center.device_pack_context_changed()
        action = self.device_packs_center.validation_service.next_safe_action(report)
        blueprint = self.device_packs_center.current_requirements()
        lane_states = (
            " • ".join(f"{lane.lane_id}={lane.state.value}" for lane in blueprint.lanes)
            if blueprint is not None
            else "requirements blueprint unavailable"
        )
        build = "ready" if report.build_contract_ready else "locked"
        flash = "ready" if report.flash_contract_ready else "locked"
        try:
            self.nexus_events.note(
                source="Device Atlas",
                stage="device-pack-readiness",
                title="Device Pack readiness updated",
                summary=(
                    f"Device Atlas verified {report.passed_count} of {len(report.checks)} gates "
                    f"for {report.model} / {report.codename}; build is {build} and flash is {flash}."
                ),
                explanation=(
                    f"The report binds Device Pack {report.pack_id} v{report.pack_version} at "
                    f"SHA-256 {report.pack_sha256[:16]}…. Readiness remains separate from "
                    "Guardian approval and execution authority. Automatic Requirements "
                    f"Blueprint: {lane_states}."
                ),
                next_action=action.title,
                state=(
                    MissionState.INFORMATION
                    if report.build_contract_ready
                    else MissionState.ATTENTION
                ),
                confidence=MissionConfidence.VERIFIED,
                guardian_protected=True,
                dedupe_key=f"device-pack-readiness-{report.report_digest}",
            )
        except LiveConsoleStoreError:
            return
        self.live_console.refresh()

    @Slot(object)
    def _record_device_dna(self, profile: object) -> None:
        self.device_packs_center.set_device_dna(
            profile if isinstance(profile, DeviceDnaProfile) else None
        )
        if hasattr(self, "companion_center"):
            project_name = ""
            if isinstance(profile, DeviceDnaProfile):
                with suppress(ProjectError):
                    project_name = self.rom_studio.store.get(profile.project_id).name
            self.companion_center.set_device_dna(
                profile if isinstance(profile, DeviceDnaProfile) else None,
                project_name,
            )
        if not isinstance(profile, DeviceDnaProfile):
            return
        actionable = tuple(
            item for item in profile.capabilities if item.capability_id != "bootloader_relock"
        )
        unconfirmed = sum(item.state is CapabilityState.UNCONFIRMED for item in actionable)
        caution = sum(item.state is CapabilityState.CAUTION for item in actionable)
        unsupported = sum(item.state is CapabilityState.UNSUPPORTED for item in actionable)
        needs_attention = bool(unconfirmed or caution or unsupported)
        confidence = (
            MissionConfidence.UNCONFIRMED
            if unconfirmed
            else MissionConfidence.MEDIUM
            if caution
            else MissionConfidence.HIGH
        )
        try:
            self.nexus_events.note(
                source="Device DNA",
                stage="capability-map",
                title="Device DNA and Capability Map updated",
                summary=(
                    f"ROMVERSE compiled {len(profile.facts)} facts and "
                    f"{len(profile.capabilities)} capability decisions from available evidence."
                ),
                explanation=(
                    f"{unconfirmed} unconfirmed, {caution} caution, and {unsupported} unsupported "
                    "capabilities remain explicit. Bootloader relocking is never authorized."
                ),
                next_action=(
                    "Review the highlighted capability warnings before build or flash readiness."
                    if needs_attention
                    else "Continue to exact tool resolution and workspace preparation."
                ),
                state=MissionState.ATTENTION if needs_attention else MissionState.INFORMATION,
                confidence=confidence,
                guardian_protected=True,
                project_id=profile.project_id,
                evidence_refs=(f"projects/{profile.project_id}/device-dna.romverse",),
                dedupe_key=f"device-dna-{profile.profile_digest}",
            )
        except LiveConsoleStoreError:
            return
        self.live_console.refresh()

    @Slot(object)
    def _record_compatibility_matrix(self, matrix: object) -> None:
        if not isinstance(matrix, CompatibilityMatrix):
            return
        statuses = [item.status for item in matrix.decisions]
        unknown = statuses.count(CompatibilityStatus.UNKNOWN)
        limited = statuses.count(CompatibilityStatus.LIMITED_EVIDENCE)
        incompatible = statuses.count(CompatibilityStatus.KNOWN_INCOMPATIBLE)
        verified = statuses.count(CompatibilityStatus.VERIFIED)
        needs_attention = bool(unknown or limited or incompatible)
        confidence = (
            MissionConfidence.UNCONFIRMED
            if unknown
            else MissionConfidence.MEDIUM
            if limited or incompatible
            else MissionConfidence.HIGH
        )
        try:
            self.nexus_events.note(
                source="Compatibility Matrix",
                stage="compatibility-assessment",
                title="Compatibility Matrix updated",
                summary=(
                    f"ROMVERSE evaluated {len(matrix.decisions)} capability decisions: "
                    f"{verified} verified, {limited} limited, {unknown} unknown, "
                    f"and {incompatible} known incompatible."
                ),
                explanation=(
                    "Technically possible and proven compatible remain separate. This matrix "
                    "advises Guardian but cannot approve or bypass a protected operation."
                ),
                next_action=(
                    "Review limited, unknown, and incompatible rows before continuing."
                    if needs_attention
                    else "Continue to Pathfinder route planning and Guardian review."
                ),
                state=MissionState.ATTENTION if needs_attention else MissionState.INFORMATION,
                confidence=confidence,
                guardian_protected=True,
                project_id=matrix.project_id,
                evidence_refs=(f"projects/{matrix.project_id}/compatibility-matrix.romverse",),
                dedupe_key=f"compatibility-{matrix.matrix_digest}",
            )
        except LiveConsoleStoreError:
            return
        self.live_console.refresh()

    @Slot(object)
    def _record_nexus_plan(self, plan: object) -> None:
        if not isinstance(plan, NexusPlan):
            return
        self.companion_center.set_nexus_plan(plan)
        ready = plan.status is NexusPlanStatus.READY_FOR_GUARDIAN
        try:
            self.nexus_events.note(
                source="ROMVERSE Nexus",
                stage="pathfinder-route",
                title="Nexus Plan and Pathfinder route updated",
                summary=(
                    f"Nexus created a {plan.objective.value.replace('-', ' ')} route with "
                    f"{len(plan.route)} stages and {len(plan.predictions)} Foresight predictions."
                ),
                explanation=(
                    "Pathfinder used current Device DNA and Compatibility Matrix evidence. "
                    "The plan has no execution authority and never permits bootloader relocking."
                ),
                next_action=(
                    "Open Guardian Review and verify every requirement."
                    if ready
                    else "Resolve the listed research requirements, refresh evidence, and regenerate the route."
                ),
                state=MissionState.INFORMATION if ready else MissionState.ATTENTION,
                confidence=(MissionConfidence.HIGH if ready else MissionConfidence.UNCONFIRMED),
                guardian_protected=True,
                project_id=plan.project_id,
                evidence_refs=(f"projects/{plan.project_id}/nexus-plan.romverse",),
                dedupe_key=f"nexus-plan-{plan.plan_digest}",
            )
        except LiveConsoleStoreError:
            return
        self.live_console.refresh()

    @Slot(str, str)
    def _record_rom_failure(self, operation: str, _message: str) -> None:
        project_id = (
            self.rom_studio.current_project.project_id
            if self.rom_studio.current_project is not None
            else ""
        )
        self._record_activity(
            "rom-studio",
            "ROM Studio stopped safely",
            f"{operation.replace('-', ' ').title()} did not complete; protected originals were preserved.",
            "attention",
            "ROM Studio",
            source_route="rom_studio" if project_id else "",
            context_type="rom-project" if project_id else "",
            context_id=project_id,
        )
        if project_id:
            self.backup_center.capture_failure_checkpoint(project_id, operation)
        self._update_companion_ascension_status()

    @Slot(str, str)
    def _open_recovery_from_rom_failure(self, operation: str, message: str) -> None:
        """Open recovery only for an actual device-write runtime failure."""

        if operation not in {
            "device-flash",
            "flash-device",
            "guardian-execute",
            "guardian-runtime-flash",
        }:
            return
        project = self.rom_studio.current_project
        project_id = project.project_id if project is not None else ""
        device = self.rom_studio.devices[0] if len(self.rom_studio.devices) == 1 else None
        recovery_evidence = None
        if project is not None:
            with suppress(OSError, ProjectError):
                recovery_evidence = RecoveryEvidenceService(self.rom_studio.store).assess(
                    project_id,
                    device,
                )
        created = self.repair_center.open_recovery_incident(
            RecoveryTrigger.FLASH_FAILURE,
            project_id=project_id,
            message=message,
            recovery_evidence=recovery_evidence,
        )
        if created:
            self._navigate_route("recovery_bay")

    def _begin_recovery_result_handoff(
        self,
        preparation,
        execution_results,
    ) -> RecoveryOperationSession | None:
        """Make the app—not a screen—the owner of one existing Recovery result."""

        previous = self._recovery_operation_session
        if previous is not None:
            try:
                result = execution_results.load(preparation)
                requested_identity = (
                    preparation.preparation_digest,
                    result.result_digest,
                    result.incident_id,
                )
            except (AttributeError, OSError, ProjectError, TypeError, ValueError):
                return None
            if previous.identity == requested_identity:
                return previous
            if not previous.terminal:
                return None
        try:
            session = RecoveryOperationSession(
                preparation,
                execution_results,
                self.repair_center.autopilot_service,
                BootObservationService(
                    self.rom_studio.store,
                    self.rom_studio.pack_registry,
                ),
                parent=self,
            )
        except (OSError, ProjectError, RecoveryOperationSessionError):
            return None
        if previous is not None:
            previous.deleteLater()
        self._recovery_operation_session = session
        session.changed.connect(
            lambda snapshot, active=session: self._recovery_operation_changed(active, snapshot)
        )
        self._recovery_operation_changed(session, session.snapshot())
        return session

    def _advance_recovery_operation_session(self, devices: list[AndroidDevice]) -> None:
        """Feed one completed fresh app scan into the retained Recovery continuation."""

        session = self._recovery_operation_session
        if session is None or session.terminal:
            return
        session.accept_scan(tuple(devices))

    def _recovery_operation_changed(self, session, snapshot) -> None:
        """Present only evidence that still belongs to the app-owned exact session."""

        if (
            self._recovery_operation_session is not session
            or snapshot.incident_id != session.incident.incident_id
        ):
            return
        self.repair_center.adopt_recovery_operation_incident(session.incident)

    def _activate_source_operation_session(self, session) -> None:
        previous = self._source_operation_session
        if previous is session:
            return
        if previous is not None:
            if previous.busy:
                raise RuntimeError("Another local installation is still active")
            previous.dispose()
            previous.deleteLater()
        self._source_operation_session = session
        session.operation_finished.connect(self._record_source_installation_result)
        session.transition_finished.connect(self._record_local_transition_result)
        session.boot_finished.connect(self._record_local_boot_result)
        session.preparation_finished.connect(
            lambda preparation, active=session: self._source_preparation_finished(
                active, preparation
            )
        )
        session.preparation_failed.connect(
            lambda message, active=session: self._source_preparation_failed(active, message)
        )
        session.quiescent.connect(lambda active=session: self._source_operation_quiescent(active))

    def _source_preparation_finished(self, session, preparation) -> None:
        """Retain hidden verified preparation without interrupting the user's current screen."""

        from romverse.rom.source_installation import SourceInstallationRecipe

        if (
            self._source_operation_session is not session
            or self._local_flash_dialog is not None
            or not isinstance(preparation, SourceInstallationRecipe)
        ):
            return
        current = self.rom_studio.current_project
        if (
            current is None
            or current.project_id != session.project_id
            or current.original is None
            or current.original.sha256 != session.source_sha256
        ):
            self.rom_studio.operation_status.setText(
                "Preparation finished, but the selected project changed. Return to the original "
                "project to continue its verified mission."
            )
            return
        self.rom_studio.operation_status.setText(
            "Preparation verified and retained. Continue installation to review the exact phone "
            "and actions; ROMVERSE will not repeat the preparation."
        )

    def _source_preparation_failed(self, session, message: str) -> None:
        if self._source_operation_session is session and self._local_flash_dialog is None:
            self.rom_studio.operation_status.setText(
                "Preparation needs attention: "
                + message
                + " Continue installation to correct the retained choice and retry."
            )

    def _retire_source_operation_session(self, session) -> None:
        if self._source_operation_session is not session or session.busy:
            return
        session.dispose()
        self._source_operation_session = None
        session.deleteLater()

    def _source_operation_quiescent(self, session) -> None:
        """Record a detached operation once its changing or boot work stops."""

        if self._source_operation_session is not session:
            return
        self._finish_expert_dialog(session)
        if self._local_flash_dialog is None:
            if self.engine is not None:
                QTimer.singleShot(0, self.scan)
            else:
                self._finish_local_flash_recovery([])

    def _resume_source_operation_before_new_device_work(self) -> bool:
        """Keep a hidden source mission authoritative over new phone operations."""

        session = self._source_operation_session
        if session is None:
            return False
        self.rom_studio.operation_status.setText(
            "ROMVERSE reopened the current installation so its exact progress and result are not "
            "replaced by another phone operation."
        )
        self._show_source_operation_session(session)
        return True

    def _show_source_operation_session(self, session) -> None:
        """Attach a fresh presentation without recreating its plan or worker."""

        from romverse.ui.project_flash import ProjectPreparationDialog
        from romverse.ui.source_installation import SourceInstallationDialog

        if self._source_operation_session is not session:
            return
        if self._local_flash_dialog is not None:
            self._local_flash_dialog.raise_()
            return
        preparing = session.recipe is None
        if preparing:
            dialog = ProjectPreparationDialog(
                session.preparation_service,
                session.project_id,
                self,
                source_service=session.source_service,
                candidate_service=session.candidate_service,
                session=session,
                source_sha256=session.source_sha256,
            )
        else:
            dialog = SourceInstallationDialog(
                session.service,
                session.devices,
                self,
                recipe=session.recipe,
                session=session,
                experience_mode=self._experience_mode,
                discover=session.discover,
                transition_service=session.transition_service,
                boot_service=session.boot_service,
            )
            dialog.experience_mode_requested.connect(self._set_experience_mode_from_studio)
        self._local_flash_dialog = dialog
        self._reconnect_timer.stop()
        try:
            dialog.exec()
        finally:
            if self._local_flash_dialog is dialog:
                self._local_flash_dialog = None
            dialog.deleteLater()
        if preparing and session.recipe is not None and not session.busy:
            self._show_source_operation_session(session)
            return
        if not session.busy:
            self._retire_source_operation_session(session)
        if not session.busy:
            if self.engine is not None:
                self.scan()
            else:
                self._finish_local_flash_recovery([])

    @Slot(str)
    def _open_project_flash(self, project_id: str) -> None:
        """Prepare project images without entering Expert or production-certification setup."""
        from romverse.guardian.local_flash import LocalFlashService
        from romverse.guardian.local_transition import LocalDeviceTransitionService
        from romverse.guardian.source_installation import SourceInstallationExecutor
        from romverse.rom.candidate_installation import (
            CandidateInstallationRecipe,
            CandidateInstallationService,
        )
        from romverse.rom.local_boot import LocalBootService
        from romverse.rom.project_flash import (
            BoundProjectFlashService,
            BoundProjectTransitionService,
            ProjectFlashPreparationService,
        )
        from romverse.rom.source_installation import (
            SourceInstallationRecipe,
            SourceInstallationService,
        )
        from romverse.ui.project_flash import ProjectFlashDialog, ProjectPreparationDialog
        from romverse.ui.source_installation import SourceInstallationDialog
        from romverse.ui.source_operation_session import SourceOperationSession

        project = self.rom_studio.current_project
        active_source_session = self._source_operation_session
        if (
            project is not None
            and project.original is not None
            and active_source_session is not None
            and active_source_session.matches(project_id, project.original.sha256)
        ):
            self._show_source_operation_session(active_source_session)
            return
        if active_source_session is not None:
            if active_source_session.busy:
                self.rom_studio.operation_status.setText(
                    "Another installation is active. Reopen it before changing projects."
                )
                return
            self._retire_source_operation_session(active_source_session)
        if (
            project is None
            or project.project_id != project_id
            or project.original is None
            or self._local_flash_dialog is not None
            or self._expert_flash_pending
        ):
            return
        source_sha256 = project.original.sha256
        if self.scanning:
            self._expert_flash_pending = True
            self.rom_studio.operation_status.setText(
                "Waiting for the current phone scan to finish…"
            )
            QTimer.singleShot(
                200, lambda: self._continue_project_flash_open(project_id, source_sha256)
            )
            return
        if any(
            (
                self.rom_studio.worker,
                self.apk_installer.active_worker,
                self.backup_center.media_backup_worker,
                self.repair_center.host_repair_worker,
                self.terminal_center._worker,
            )
        ):
            QMessageBox.information(
                self,
                "Finish the current operation",
                "Wait for the active device or project operation before preparing image installation.",
            )
            return
        if self._device_fastboot_executable is None:
            QMessageBox.information(
                self,
                "Fastboot is required",
                "Locate Android Platform Tools in Forge Arsenal, then return to prepare installation.",
            )
            self._navigate_route("forge_arsenal")
            return
        source_session = None
        try:
            local = LocalFlashService(
                self._workspace,
                self._runtime_runner,
                self._device_fastboot_executable,
                audit=self._audit_store,
            )
            preparer = ProjectFlashPreparationService(
                self.rom_studio.store, self.rom_studio.pack_registry
            )
            source_service = SourceInstallationService(self.rom_studio.store)
            candidate_service = CandidateInstallationService(
                self.rom_studio.store,
                self.rom_studio.pack_registry,
                self.rom_studio.tool_statuses,
                self._runtime_runner,
            )
            transition_service = LocalDeviceTransitionService(local, self._device_adb_executable)
            boot_service = (
                LocalBootService(
                    local,
                    self._device_adb_executable,
                    timeout_seconds=900,
                )
                if self._device_adb_executable is not None
                else None
            )
            source_session = SourceOperationSession(
                None,
                tuple(self._observed_devices),
                project_id=project_id,
                source_sha256=source_sha256,
                preparation_service=preparer,
                source_service=source_service,
                candidate_service=candidate_service,
                installation_factory=lambda preparation: SourceInstallationExecutor(
                    candidate_service
                    if isinstance(preparation, CandidateInstallationRecipe)
                    else source_service,
                    local,
                    self._device_adb_executable,
                ),
                discover=self.engine.scan if self.engine is not None else None,
                transition_service=transition_service,
                boot_service=boot_service,
                guided_automation=True,
                parent=self,
            )
            self._activate_source_operation_session(source_session)
            preparation_dialog = ProjectPreparationDialog(
                preparer,
                project_id,
                self,
                source_service=source_service,
                candidate_service=candidate_service,
                session=source_session,
                source_sha256=source_sha256,
            )
        except (OSError, ValueError, ProjectError) as exc:
            if source_session is not None:
                self._retire_source_operation_session(source_session)
            QMessageBox.warning(self, "Local installation could not open", str(exc))
            return
        self._local_flash_dialog = preparation_dialog
        self._reconnect_timer.stop()
        dialog = None
        try:
            preparation_dialog.exec()
            preparation = preparation_dialog.preparation
            preparation_dialog.deleteLater()
            current = self.rom_studio.current_project
            if preparation is None:
                return
            if (
                current is None
                or current.project_id != project_id
                or current.original is None
                or current.original.sha256 != source_sha256
                or preparation.source_sha256 != source_sha256
            ):
                self.rom_studio.operation_status.setText(
                    "The project or source changed. Prepare the intended project's images again."
                )
                return
            if isinstance(preparation, SourceInstallationRecipe):
                dialog = SourceInstallationDialog(
                    source_session.service,
                    source_session.devices,
                    self,
                    recipe=preparation,
                    session=source_session,
                    experience_mode=self._experience_mode,
                    discover=source_session.discover,
                    transition_service=source_session.transition_service,
                    boot_service=source_session.boot_service,
                )
                dialog.experience_mode_requested.connect(self._set_experience_mode_from_studio)
            else:
                self._retire_source_operation_session(source_session)
                source_session = None
                bound = BoundProjectFlashService(preparer, preparation, local)
                transition = BoundProjectTransitionService(
                    preparer,
                    preparation,
                    LocalDeviceTransitionService(local, self._device_adb_executable),
                )
                dialog = ProjectFlashDialog(
                    bound,
                    tuple(self._observed_devices),
                    self,
                    preparation=preparation,
                    discover=self.engine.scan if self.engine is not None else None,
                    transition_service=transition,
                    boot_service=(
                        LocalBootService(local, self._device_adb_executable)
                        if self._device_adb_executable is not None
                        else None
                    ),
                )
                dialog.operation_finished.connect(self._record_local_flash_result)
                dialog.transition_finished.connect(self._record_local_transition_result)
                dialog.boot_finished.connect(self._record_local_boot_result)
            self._local_flash_dialog = dialog
            dialog.exec()
        except (OSError, ValueError, ProjectError) as exc:
            QMessageBox.warning(self, "Local installation stopped", str(exc))
        finally:
            self._local_flash_dialog = None
            if dialog is not None and source_session is None:
                self._finish_expert_dialog(dialog)
            if source_session is not None and not source_session.busy:
                self._retire_source_operation_session(source_session)
            if self.engine is not None and (source_session is None or not source_session.busy):
                self.scan()
            elif self.engine is None and (source_session is None or not source_session.busy):
                self._finish_local_flash_recovery([])

    @Slot(str)
    def _open_source_installation_history(self, project_id: str) -> None:
        """Saved outcomes and explicit read-only boot checks, never another installation."""
        from romverse.guardian.local_flash import LocalFlashService
        from romverse.rom.local_boot import LocalBootService
        from romverse.rom.source_installation_history import load_latest_source_installation
        from romverse.ui.source_installation_history import SourceInstallationHistoryDialog

        if self._resume_source_operation_before_new_device_work():
            return
        project = self.rom_studio.current_project
        if (
            project is None
            or project.project_id != project_id
            or self._local_flash_dialog is not None
            or self._expert_flash_pending
        ):
            return
        if self.scanning or any(
            (
                self.rom_studio.worker,
                self.apk_installer.active_worker,
                self.backup_center.media_backup_worker,
                self.repair_center.host_repair_worker,
                self.terminal_center._worker,
            )
        ):
            self.rom_studio.operation_status.setText(
                "Wait for the current scan or operation, then reopen installation results."
            )
            return
        dialog = None
        try:
            outcome = load_latest_source_installation(self.rom_studio.store, project_id)
            if outcome is None:
                QMessageBox.information(
                    self,
                    "No installation history",
                    "No supported source installation record matches this project's current source.",
                )
                return
            local = LocalFlashService(
                self._workspace,
                self._runtime_runner,
                self._device_fastboot_executable,
                audit=self._audit_store,
            )
            dialog = SourceInstallationHistoryDialog(
                local,
                tuple(self._observed_devices),
                self,
                outcome=outcome,
                discover=self.engine.scan if self.engine is not None else None,
                boot_service=(
                    LocalBootService(local, self._device_adb_executable, timeout_seconds=900)
                    if self._device_adb_executable is not None
                    and self._device_fastboot_executable is not None
                    else None
                ),
            )
            dialog.boot_finished.connect(self._record_local_boot_result)
            self._local_flash_dialog = dialog
            self._reconnect_timer.stop()
            dialog.exec()
        except (OSError, ValueError, ProjectError) as exc:
            QMessageBox.warning(self, "Installation history unavailable", str(exc))
        finally:
            self._local_flash_dialog = None
            if dialog is not None:
                self._finish_expert_dialog(dialog)
                if self.engine is not None:
                    self.scan()
                else:
                    self._finish_local_flash_recovery([])

    def _resume_pending_source_installation_recovery(self) -> None:
        pending = self._pending_source_installation_recovery
        if pending is None or self.scanning:
            return
        self._pending_source_installation_recovery = None
        self._open_source_installation_recovery(*pending)

    @staticmethod
    def _source_installation_knowledge_failure(outcome, trigger: RecoveryTrigger):
        failed = outcome.actions("failed")
        uncertain = outcome.actions("uncertain")
        focus = (failed or uncertain or outcome.actions("unattempted"))[:1]
        action = focus[0] if focus else None
        finding_ids = []
        if failed:
            finding_ids.append("source.installation.command_failed")
        if uncertain:
            finding_ids.append("source.installation.command_outcome_unknown")
        if not outcome.action_evidence or not outcome.record_digest:
            finding_ids.append("source.installation.history_unverified")
        if trigger in {RecoveryTrigger.BOOTLOOP, RecoveryTrigger.BOOT_ATTENTION}:
            finding_ids.append("source.installation.boot_attention")
        verified_inputs = [f"source SHA-256 {outcome.source_sha256}"]
        if outcome.recipe_digest:
            verified_inputs.append(f"recipe SHA-256 {outcome.recipe_digest}")
        if outcome.record_digest:
            verified_inputs.append(f"installation record SHA-256 {outcome.record_digest}")
        return KnowledgeFailure(
            phase="source-installation",
            message=outcome.summary,
            finding_ids=tuple(finding_ids),
            partition=(
                action.target if action is not None and action.action in {"flash", "erase"} else ""
            ),
            operation=(
                f"{action.action} {action.target}"
                if action is not None
                else "Reconstruct saved installation state"
            ),
            verified_inputs=tuple(verified_inputs),
        )

    @Slot(str, str)
    def _open_source_installation_recovery(self, project_id: str, source_sha256: str) -> None:
        """Diagnose a sealed installation outcome without boot, write or retry authority."""

        from romverse.rom.source_installation_history import (
            SourceInstallationOutcome,
            load_latest_source_installation,
        )

        if self._resume_source_operation_before_new_device_work():
            return
        project = self.rom_studio.current_project
        if (
            project is None
            or project.project_id != project_id
            or project.original is None
            or project.original.sha256 != source_sha256
        ):
            self.rom_studio.operation_status.setText(
                "The selected project or protected source changed. No recovery incident was attributed."
            )
            return
        if self.scanning:
            self._pending_source_installation_recovery = (project_id, source_sha256)
            self.rom_studio.operation_status.setText(
                "Finishing the fresh phone scan before opening interrupted-installation diagnosis…"
            )
            return
        if self._local_flash_dialog is not None:
            self.rom_studio.operation_status.setText(
                "Close the current installation view before opening saved-operation diagnosis."
            )
            return
        try:
            outcome = load_latest_source_installation(self.rom_studio.store, project_id)
        except (OSError, ProjectError, TypeError, ValueError) as exc:
            self.rom_studio.operation_status.setText(
                "Saved installation evidence could not be reconstructed: " + str(exc)
            )
            return
        if not isinstance(outcome, SourceInstallationOutcome):
            self.rom_studio.operation_status.setText(
                "No saved installation outcome matches this project and protected source."
            )
            return
        if outcome.project_id != project_id or outcome.source_sha256 != source_sha256:
            self.rom_studio.operation_status.setText(
                "Saved installation evidence no longer matches the selected project and source. "
                "No recovery incident was attributed."
            )
            return
        needs_diagnosis = outcome.state in {"failed", "attention"} or (
            outcome.state == "cancelled" and outcome.completed_count > 0
        )
        if not needs_diagnosis:
            self.rom_studio.operation_status.setText(
                "This saved installation no longer needs interruption diagnosis; opening its read-only results."
            )
            self._open_source_installation_history(project_id)
            return

        privacy = WorkspacePrivacy(self.rom_studio.store.workspace)
        matching = {
            device.serial: device
            for device in self._observed_devices
            if outcome.matches_operation_device(privacy, device)
        }
        target = next(iter(matching.values())) if len(matching) == 1 else None
        connection = (
            " The freshly scanned exact operation target is attached."
            if target is not None
            else " The recorded operation target is not currently verified as attached; reconnect that same phone before any device action."
        )
        message = f"{outcome.summary} {outcome.recovery_summary()}{connection}"
        failure = self._source_installation_knowledge_failure(
            outcome, RecoveryTrigger.FLASH_FAILURE
        )
        self.repair_center.open_recovery_incident(
            RecoveryTrigger.FLASH_FAILURE,
            project_id=project_id,
            message=message,
            failure=failure,
            target_device=target,
            # Never assign a sealed operation to whichever unrelated phone happens
            # to be selected after restart.
            allow_current_device_fallback=False,
            expected_device_key=outcome.operation_device_key,
        )
        self.rom_studio.operation_status.setText(
            "Interrupted-installation diagnosis opened for the exact scanned phone. No write was retried."
            if target is not None
            else "Interrupted-installation diagnosis opened without a phone target. Reconnect the recorded phone; no other device was assigned."
        )
        self._navigate_route("recovery_bay")

    def _continue_project_flash_open(self, project_id: str, source_sha256: str) -> None:
        if not self._expert_flash_pending:
            return
        project = self.rom_studio.current_project
        if (
            project is None
            or project.project_id != project_id
            or project.original is None
            or project.original.sha256 != source_sha256
        ):
            self._expert_flash_pending = False
            self.rom_studio.operation_status.setText(
                "The selected project changed. Open installation again."
            )
        elif self.scanning:
            QTimer.singleShot(
                200, lambda: self._continue_project_flash_open(project_id, source_sha256)
            )
        else:
            self._expert_flash_pending = False
            self._open_project_flash(project_id)

    @Slot()
    def _open_expert_flash(self) -> None:
        from romverse.guardian.local_flash import LocalFlashService
        from romverse.guardian.local_transition import LocalDeviceTransitionService
        from romverse.rom.local_boot import LocalBootService
        from romverse.ui.local_flash import LocalFlashDialog

        if (
            self._experience_mode is not ExperienceMode.EXPERT
            or self._local_flash_dialog is not None
        ):
            self._expert_flash_pending = False
            return
        if self._resume_source_operation_before_new_device_work():
            self._expert_flash_pending = False
            return
        if self.scanning:
            if not self._expert_flash_pending:
                self._expert_flash_pending = True
                self.rom_studio.operation_status.setText(
                    "Waiting for the current phone scan to finish…"
                )
                QTimer.singleShot(200, self._continue_expert_flash_open)
            return
        self._expert_flash_pending = False
        if any(
            (
                self.rom_studio.worker,
                self.apk_installer.active_worker,
                self.backup_center.media_backup_worker,
                self.repair_center.host_repair_worker,
                self.terminal_center._worker,
            )
        ):
            QMessageBox.information(
                self,
                "Finish the current operation",
                "A device or project operation is running. Wait for its result before opening image flashing.",
            )
            return
        fastboot = self._device_fastboot_executable
        if fastboot is None:
            QMessageBox.information(
                self,
                "Fastboot is required",
                "Open Forge Arsenal to install or locate Android Platform Tools, then return to image flashing.",
            )
            self._navigate_route("forge_arsenal")
            return
        try:
            service = LocalFlashService(
                self._workspace, self._runtime_runner, fastboot, audit=self._audit_store
            )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Image flashing could not open", str(exc))
            return
        dialog = LocalFlashDialog(
            service,
            tuple(self._observed_devices),
            self,
            discover=self.engine.scan if self.engine is not None else None,
            transition_service=LocalDeviceTransitionService(service, self._device_adb_executable),
            boot_service=(
                LocalBootService(service, self._device_adb_executable)
                if self._device_adb_executable is not None
                else None
            ),
        )
        dialog.operation_finished.connect(self._record_local_flash_result)
        dialog.transition_finished.connect(self._record_local_transition_result)
        dialog.boot_finished.connect(self._record_local_boot_result)
        self._local_flash_dialog = dialog
        self._reconnect_timer.stop()
        try:
            dialog.exec()
        finally:
            self._local_flash_dialog = None
        self._finish_expert_dialog(dialog)
        if self.engine is not None:
            self.scan()
        else:
            self._finish_local_flash_recovery([])

    def _finish_expert_dialog(self, dialog) -> None:
        from romverse.guardian.source_installation import SourceInstallationResult
        from romverse.rom.source_installation_history import SourceInstallationOutcome

        result = dialog.result
        preparation = getattr(dialog, "preparation", None)
        failure_message = ""
        attempted = dialog.last_attempt_device
        trigger = RecoveryTrigger.FLASH_FAILURE
        if dialog.boot_report is not None and dialog.boot_report.status == "attention":
            failure_message = dialog.boot_report.summary
            attempted = dialog.boot_device
            trigger = (
                RecoveryTrigger.BOOTLOOP
                if dialog.boot_report.failure_kind == "reboot_loop"
                else RecoveryTrigger.BOOT_ATTENTION
            )
        elif dialog.boot_error:
            failure_message = "Boot could not be verified. " + dialog.boot_error
            attempted = dialog.boot_device
            trigger = RecoveryTrigger.BOOT_ATTENTION
        elif result is not None and result.phone_change_attempted and result.state != "completed":
            # An interrupted sequence can leave only some partitions written. Feed
            # the measured outcome into the existing recovery incident workflow.
            failure_message = result.summary
            attempted = dialog.last_flash_device or attempted
        elif dialog.execution_error:
            failure_message = (
                "The image-writing service did not return a complete result. Recheck the phone state. "
                + dialog.execution_error
            )
        elif dialog.transition_error:
            failure_message = (
                "The requested phone mode was not verified. " + dialog.transition_error
            )
            attempted = dialog.transition_attempt_device
            trigger = RecoveryTrigger.DEVICE_MODE
        elif (
            dialog.recovery_requested
            and isinstance(preparation, SourceInstallationOutcome)
            and (
                preparation.state in {"failed", "attention"}
                or (preparation.state == "cancelled" and preparation.completed_count > 0)
            )
        ):
            self._open_source_installation_recovery(
                preparation.project_id, preparation.source_sha256
            )
            return
        elif dialog.recovery_requested:
            self._navigate_route("recovery_bay")
        if failure_message and attempted is not None:
            self._pending_local_flash_recovery = (attempted, failure_message)
            self._pending_local_flash_recovery_trigger = trigger
            self._pending_local_flash_recovery_project = (
                (preparation.project_id, preparation.source_sha256)
                if preparation is not None
                else None
            )
            self._pending_local_flash_recovery_result = (
                result if isinstance(result, SourceInstallationResult) else None
            )
            self._selected_device_serial = attempted.serial
        elif failure_message and dialog.recovery_requested:
            # Historical failures without an exact connected phone still have a
            # useful destination; never attribute them to another selected device.
            self._navigate_route("recovery_bay")

    def _finish_local_flash_recovery(self, devices: list[AndroidDevice]) -> None:
        pending = self._pending_local_flash_recovery
        if pending is None:
            return
        self._pending_local_flash_recovery = None
        project_binding = getattr(self, "_pending_local_flash_recovery_project", None)
        self._pending_local_flash_recovery_project = None
        source_result = getattr(self, "_pending_local_flash_recovery_result", None)
        self._pending_local_flash_recovery_result = None
        trigger = getattr(
            self, "_pending_local_flash_recovery_trigger", RecoveryTrigger.FLASH_FAILURE
        )
        self._pending_local_flash_recovery_trigger = RecoveryTrigger.FLASH_FAILURE
        attempted, message = pending
        fresh = next((item for item in devices if item.serial == attempted.serial), None)
        target = fresh or AndroidDevice(
            attempted.serial,
            DeviceState.UNKNOWN,
            manufacturer=attempted.manufacturer,
            model=attempted.model,
            product=attempted.product,
            codename=attempted.codename,
            connection_note="Last selected operation target; current connection state is unknown.",
        )
        project_id = ""
        if project_binding is not None:
            with suppress(OSError, ProjectError):
                project = self.rom_studio.store.get(project_binding[0])
                if project.original is not None and project.original.sha256 == project_binding[1]:
                    # Historical operation attribution only, never a fresh artifact or
                    # installation claim. A changed source cannot inherit this incident.
                    project_id = project.project_id
        failure = None
        if project_id and source_result is not None:
            from romverse.guardian.source_installation import SourceInstallationResult
            from romverse.rom.source_installation_history import (
                SourceInstallationOutcome,
                load_latest_source_installation,
            )

            try:
                outcome = load_latest_source_installation(self.rom_studio.store, project_id)
            except (OSError, ProjectError, TypeError, ValueError):
                outcome = None
            if (
                isinstance(source_result, SourceInstallationResult)
                and isinstance(outcome, SourceInstallationOutcome)
                and outcome.matches_result(source_result)
                and outcome.action_evidence
            ):
                message = f"{message} {outcome.recovery_summary()}"
                failure = self._source_installation_knowledge_failure(outcome, trigger)
        self.repair_center.open_recovery_incident(
            trigger,
            project_id=project_id,
            message=message,
            failure=failure,
            target_device=target,
        )
        self._navigate_route("recovery_bay")

    def _continue_expert_flash_open(self) -> None:
        if not self._expert_flash_pending:
            return
        if self.scanning:
            QTimer.singleShot(200, self._continue_expert_flash_open)
        else:
            self._expert_flash_pending = False
            self._open_expert_flash()

    @Slot(object)
    def _record_source_installation_result(self, result: object) -> None:
        from romverse.guardian.source_installation import SourceInstallationResult

        if not isinstance(result, SourceInstallationResult):
            return
        self._record_activity(
            "rom-studio",
            "Declared installation actions completed · boot separate"
            if result.state == "completed"
            else "Source installation needs attention",
            result.summary,
            "attention",
            "ROM Studio",
        )
        self.rom_studio.operation_status.setText(result.summary)

    @Slot(object)
    def _record_local_flash_result(self, result: object) -> None:
        from romverse.guardian.local_flash import LocalFlashResult

        if not isinstance(result, LocalFlashResult):
            return
        title = (
            "Image writes completed · boot unverified"
            if result.state == "completed"
            else "Image writing stopped"
        )
        self._record_activity(
            "rom-studio",
            title,
            result.summary,
            "attention",
            "ROM Studio",
        )
        self.rom_studio.operation_status.setText(result.summary)

    @Slot(object)
    def _record_local_transition_result(self, result: object) -> None:
        from romverse.guardian.local_transition import LocalTransitionResult

        if not isinstance(result, LocalTransitionResult):
            return
        self._record_activity(
            "rom-studio",
            "Phone mode observed" if result.state == "completed" else "Phone mode needs attention",
            result.summary,
            "attention",
            "ROM Studio",
        )
        self.rom_studio.operation_status.setText(result.summary)

    @Slot(object)
    def _record_local_boot_result(self, result: object) -> None:
        from romverse.rom.local_boot import LocalBootReport

        if not isinstance(result, LocalBootReport):
            return
        stable = result.status == "stable" and result.boot_observed
        title = (
            "Android boot observed · subsystem tests pending"
            if stable
            else "Android boot check ended"
        )
        self._record_activity(
            "rom-studio",
            title,
            result.summary,
            "success" if stable else "attention",
            "ROM Studio",
        )
        self.rom_studio.operation_status.setText(result.summary)

    def _update_companion_ascension_status(self) -> None:
        project_id = (
            self.rom_studio.current_project.project_id
            if self.rom_studio.current_project is not None
            else ""
        )

        def verified_tool(name: str) -> Path | None:
            status = next(
                (
                    item
                    for item in self.rom_studio.tool_statuses
                    if item.name == name and item.available and item.path
                ),
                None,
            )
            if status is None:
                return None
            try:
                path = Path(status.path).expanduser().resolve(strict=True)
            except OSError:
                return None
            return path if path.is_file() else None

        release_service = OfficialRootReleaseService(
            self.rom_studio.store.workspace,
            aapt_executable=verified_tool("AAPT2"),
            apksigner_executable=verified_tool("APK Signer"),
            runner=self._runtime_runner,
        )
        status = AscensionCompanionStatusService(
            self.rom_studio.store,
            self.rom_studio.pack_registry,
            self.rom_studio.attestation_store,
            release_service,
        ).snapshot(
            project_id,
            next(iter(self.rom_studio.devices), None),
            self.rom_studio.companion_snapshot,
        )
        self.companion_center.set_ascension_status(status)

    def _record_activity(
        self,
        category: str,
        title: str,
        detail: str,
        outcome: str,
        source: str,
        *,
        source_route: str = "",
        context_type: str = "",
        context_id: str = "",
    ) -> None:
        with suppress(ActivityStoreError):
            self.activity_store.record(
                category,
                title,
                detail,
                outcome=outcome,
                source=source,
                source_route=source_route,
                context_type=context_type,
                context_id=context_id,
            )

    @Slot(object)
    def _tool_statuses_changed(self, statuses: object) -> None:
        if isinstance(statuses, tuple) and all(
            isinstance(status, ToolStatus) for status in statuses
        ):
            self.device_packs_center.set_tool_statuses(statuses)
            self.rom_studio.set_tool_statuses(statuses)
            self.apk_installer.set_tool_statuses(statuses)
            if hasattr(self, "about_page") and self.stack.currentWidget() is self.about_page:
                self._refresh_about_evidence()
            adb_executable = self._verified_runtime_executable(statuses, "ADB")
            fastboot_executable = self._verified_runtime_executable(statuses, "Fastboot")
            if adb_executable is None and fastboot_executable is None:
                self._disable_android_runtime(
                    "Verified Android Platform Tools are unavailable. Open Forge Arsenal to restore ADB and Fastboot monitoring."
                )
                return
            gateway = self._runtime_gateway
            if gateway is None:
                gateway = ExecutionGateway(
                    GuardianPolicy(self._workspace),
                    self._runtime_runner,
                    self._audit_store,
                )
                self._runtime_gateway = gateway
            runtime_changed = (
                self.engine is None
                or self._device_adb_executable != adb_executable
                or self._device_fastboot_executable != fastboot_executable
            )
            if runtime_changed:
                self._device_runtime_generation += 1
                self.scanning = False
                self.active_worker = None
                self.device_center.set_scanning(False)
                self.diagnostics_center.set_scanning(False)
                self.engine = DeviceEngine(
                    AdbClient(adb_executable, gateway) if adb_executable is not None else None,
                    FastbootClient(fastboot_executable, gateway)
                    if fastboot_executable is not None
                    else None,
                )
                self._device_adb_executable = adb_executable
                self._device_fastboot_executable = fastboot_executable
            self.rom_studio.set_android_runtime(
                gateway if adb_executable is not None else None,
                adb_executable,
                fastboot_executable,
            )
            self.rom_studio.device_scan_available = True
            if adb_executable is not None:
                self.apk_installer.set_install_service(
                    ApkInstallService(
                        adb_executable,
                        gateway,
                        ApprovalStore(self._workspace),
                    )
                )
                self.backup_center.set_media_backup_service(
                    PhoneMediaBackupService(
                        self._workspace,
                        adb_executable,
                        gateway,
                        ApprovalStore(self._workspace),
                    )
                )
                self.terminal_center.set_runtime(gateway, adb_executable)
                self.repair_center.set_host_repair_service(
                    AdbHostRepairService(
                        adb_executable,
                        gateway,
                        ApprovalStore(self._workspace),
                        AdbHostRepairReceiptStore(self._workspace),
                    )
                )
            else:
                self.apk_installer.set_install_service(None)
                self.backup_center.set_media_backup_service(None)
                self.terminal_center.set_runtime(None, None)
                self.repair_center.set_host_repair_service(None)
            self._reconnect_timer.stop()
            self._scan_failure_count = 0
            self.timer.setInterval(self.scan_interval_seconds * 1000)
            if not self.timer.isActive():
                self.timer.start()
            self.scan()

    @staticmethod
    def _verified_runtime_executable(
        statuses: tuple[ToolStatus, ...],
        name: str,
    ) -> Path | None:
        status = next(
            (item for item in statuses if item.name == name and item.available and item.path),
            None,
        )
        if status is None:
            return None
        executable = Path(status.path).expanduser().resolve()
        return executable if executable.is_file() else None

    def _disable_android_runtime(self, message: str) -> None:
        had_runtime = any(
            (
                self.engine is not None,
                self.rom_studio.adb_executable is not None,
                self.apk_installer.install_service is not None,
                self.backup_center.media_backup_service is not None,
                self.terminal_center.adb_executable is not None,
                self._device_fastboot_executable is not None,
            )
        )
        self._device_runtime_generation += 1
        self.engine = None
        self._device_adb_executable = None
        self._device_fastboot_executable = None
        self.scanning = False
        self.active_worker = None
        self.timer.stop()
        self._reconnect_timer.stop()
        self.rom_studio.set_android_runtime(None, None, None)
        self.rom_studio.device_scan_available = False
        self.apk_installer.set_install_service(None)
        self.backup_center.set_media_backup_service(None)
        self.terminal_center.set_runtime(None, None)
        self.repair_center.set_host_repair_service(None)
        if had_runtime:
            self._scan_failed(message)
            self.timer.stop()
            self._reconnect_timer.stop()

    def _current_studio_toolchain_context(
        self,
        project_id: str,
        context_digest: str = "",
    ) -> StudioProjectToolchainContext | None:
        """Re-derive exact project/source/tool evidence without trusting retained UI text."""

        current = self.rom_studio.current_project
        if current is None or current.project_id != project_id:
            return None
        try:
            project = self.rom_studio.store.get(project_id)
        except (OSError, ProjectError, TypeError, ValueError):
            return None
        if project.original is None:
            return None
        inspection = self.rom_studio.inspection.load_report(project.project_id)
        if inspection is not None and inspection.source_sha256 != project.original.sha256:
            inspection = None
        pack = next(
            (
                item
                for item in self.rom_studio.pack_registry.packs
                if item.pack_id == project.device_pack_id
            ),
            None,
        )
        contract = (
            pack.build_contract
            if pack is not None
            and pack.build_contract is not None
            and pack.build_contract.source.archive_sha256 == project.original.sha256
            else None
        )
        source_blueprint = FirmwareSourceIntelligenceService(
            self.rom_studio.store,
            self.rom_studio.tool_statuses,
            SubprocessRunner(),
        ).load(project.project_id)
        if (
            source_blueprint is not None
            and source_blueprint.source_archive_sha256 != project.original.sha256
        ):
            source_blueprint = None
        source_signals = (
            {
                "ota-payload": ("ota_payload",),
                "fastboot-super": ("super",),
                "partition-bundle": ("partition_bundle",),
            }.get(source_blueprint.source_kind, ())
            if source_blueprint is not None
            else ()
        )
        partition_signals = source_signals or (
            inspection.partition_signals if inspection is not None else ()
        )
        required_tools = required_tools_for_source(contract, partition_signals)
        payload = {
            "project_id": project.project_id,
            "project_name": project.name,
            "source_sha256": project.original.sha256,
            "device_pack_id": project.device_pack_id,
            "pack_sha256": pack.sha256 if pack is not None else "",
            "inspection_digest": inspection.record_digest if inspection is not None else "",
            "source_kind": source_blueprint.source_kind if source_blueprint is not None else "",
            "source_blueprint_digest": (
                source_blueprint.blueprint_digest if source_blueprint is not None else ""
            ),
            "source_plan_digest": (
                source_blueprint.plan_digest if source_blueprint is not None else ""
            ),
            "partition_signals": partition_signals,
            "required_tools": required_tools,
            "build_contract_bound": contract is not None,
        }
        actual_digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if context_digest and context_digest != actual_digest:
            return None
        return StudioProjectToolchainContext(
            context_digest=actual_digest,
            project_id=project.project_id,
            project_name=project.name,
            source_sha256=project.original.sha256,
            device_pack_id=project.device_pack_id,
            pack_sha256=pack.sha256 if pack is not None else "",
            inspection_digest=inspection.record_digest if inspection is not None else "",
            required_tools=required_tools,
            build_contract_bound=contract is not None,
            source_kind=source_blueprint.source_kind if source_blueprint is not None else "",
            source_blueprint_digest=(
                source_blueprint.blueprint_digest if source_blueprint is not None else ""
            ),
            source_plan_digest=(
                source_blueprint.plan_digest if source_blueprint is not None else ""
            ),
        )

    @Slot(str, str)
    def _open_toolchain(self, project_id: str, intent: str) -> None:
        if intent != "build-readiness":
            self.rom_studio.outbound_handoff_stopped(
                "Forge Arsenal",
                "The requested host-tool purpose is not approved",
            )
            return
        context = self._current_studio_toolchain_context(project_id)
        if context is None or not self.toolchain_center.open_studio_project_context(context):
            self.rom_studio.outbound_handoff_stopped(
                "Forge Arsenal",
                "The exact project, protected source, or derived tool evidence changed",
            )
            return
        self._navigate_route("forge_arsenal")

    @Slot(str, str)
    def _setup_studio_project_toolchain(
        self,
        project_id: str,
        context_digest: str,
    ) -> None:
        context = self._current_studio_toolchain_context(project_id, context_digest)
        if context is None or not self.toolchain_center.studio_project_context_matches(context):
            self.toolchain_center.studio_project_context_changed(
                "ROM Studio project, source, Device Pack, inspection, or required tools changed"
            )
            return
        self.toolchain_center.open_studio_project_setup(context)

    @Slot(str, str)
    def _return_forge_rom_studio(
        self,
        project_id: str,
        context_digest: str,
    ) -> None:
        context = self._current_studio_toolchain_context(project_id, context_digest)
        if context is None or not self.toolchain_center.studio_project_context_matches(context):
            self.toolchain_center.studio_project_context_changed(
                "ROM Studio project, source, Device Pack, inspection, or required tools changed"
            )
            return
        self.rom_studio.set_tool_statuses(self.toolchain_center.statuses)
        if not self.rom_studio.open_forge_toolchain_handoff(
            context.project_id,
            context.source_sha256,
            context.context_digest,
            context.required_tools,
            context.build_contract_bound,
        ):
            self.toolchain_center.studio_project_context_changed(
                "ROM Studio rejected the changed project/source/tool evidence"
            )
            return
        self._navigate_route("rom_studio")

    @Slot()
    def _resolve_apk_runtime(self) -> None:
        self.rom_studio._resolve_required_tools(
            ("ADB",),
            purpose=(
                "App Launchpad already verified the APK and target phone. It now needs only "
                "Android Platform Tools before Guardian can record the exact approval."
            ),
            title="ROMVERSE • Resolve App Launchpad connection",
            success_message="Android Platform Tools freshly verified for App Launchpad.",
            parent=self,
        )

    @Slot()
    def _resolve_backup_runtime(self) -> None:
        self.rom_studio._resolve_required_tools(
            ("ADB",),
            purpose=(
                "Time Machine needs verified Android Platform Tools to copy only the explicitly "
                "selected shared-storage folders into a local verified archive."
            ),
            title="ROMVERSE • Resolve local phone backup connection",
            success_message="Android Platform Tools freshly verified for local phone backup.",
            parent=self,
        )

    @Slot()
    def _resolve_device_runtime(self) -> None:
        self.rom_studio._resolve_required_tools(
            ("ADB",),
            purpose=(
                "Device Engine needs verified Android Platform Tools for automatic read-only "
                "device detection, identity evidence, and health telemetry."
            ),
            title="ROMVERSE • Start Device Engine",
            success_message="Android Platform Tools freshly verified. Device Engine is scanning now.",
            parent=self,
        )

    @Slot()
    def _resolve_apk_inspection_tools(self) -> None:
        self.rom_studio._resolve_required_tools(
            ("AAPT2", "APK Signer"),
            purpose=(
                "App Launchpad needs AAPT2 and cryptographic APK signature verification to "
                "decode the selected APK and verify its signer before review. The managed "
                "apksig route verifies only; it never creates or stores a signing key."
            ),
            title="ROMVERSE • Complete APK identity verification",
            success_message="AAPT2 and APK signature verification freshly verified for App Launchpad.",
            parent=self,
        )

    @Slot()
    def _resolve_terminal_runtime(self) -> None:
        self.rom_studio._resolve_required_tools(
            ("ADB",),
            purpose=(
                "Command Console needs verified Android Platform Tools for this approved "
                "read-only check. ROMVERSE will restore only the bounded ADB runtime."
            ),
            title="ROMVERSE • Resolve Command Console connection",
            success_message="Android Platform Tools freshly verified for Command Console.",
            parent=self,
        )

    @Slot()
    def _resolve_repair_runtime(self) -> None:
        self.rom_studio._resolve_required_tools(
            ("ADB",),
            purpose=(
                "Recovery Bay needs verified Android Platform Tools to restore Device Engine "
                "and collect a fresh read-only diagnostic snapshot."
            ),
            title="ROMVERSE • Restore Recovery Bay diagnostics",
            success_message=(
                "Android Platform Tools freshly verified. Device Engine is starting a new scan."
            ),
            parent=self,
        )

    @Slot(str, str, str, str)
    def _open_repair_solution_action(
        self,
        action_id: str,
        fingerprint_id: str,
        receipt_digest: str,
        source_id: str,
    ) -> None:
        """Revalidate and route a Smart Solution to its built-in review surface."""

        if not self.repair_center.validate_solution_handoff(
            action_id,
            fingerprint_id,
            receipt_digest,
            source_id,
        ):
            self.repair_center.solution_handoff_stopped(
                "The current saved research receipt no longer proves this exact lead action"
            )
            return
        receipt = self.repair_center.solution_handoff_receipt(
            action_id,
            fingerprint_id,
            receipt_digest,
            source_id,
        )
        if receipt is None:
            self.repair_center.solution_handoff_stopped(
                "The saved research receipt changed during final handoff validation"
            )
            return
        if action_id == "verify-platform-tools":
            context = RepairToolchainContext(
                action_id,
                fingerprint_id,
                receipt_digest,
                source_id,
                receipt,
            )
            if not self.toolchain_center.open_repair_solution_context(context):
                self.repair_center.solution_handoff_stopped(
                    "Forge Arsenal rejected the research-bound Platform Tools context"
                )
                return
            self._navigate_route("forge_arsenal")
            return
        if action_id in {
            "inspect-payload-source",
            "inspect-avb-topology",
            "classify-ota-source",
        }:
            if not self.rom_studio.open_repair_solution_handoff(
                action_id,
                fingerprint_id,
                receipt_digest,
                source_id,
                receipt,
            ):
                self.repair_center.solution_handoff_stopped(
                    "ROM Studio rejected the research-bound firmware inspection context"
                )
                return
            self._navigate_route("rom_studio")
            return
        self.repair_center.solution_handoff_stopped(
            "This typed action has no registered Desktop owner"
        )

    @Slot(str)
    def _open_time_machine(self, project_id: str) -> None:
        """Carry the exact selected Studio project into local recovery evidence."""

        current = self.rom_studio.current_project
        if (
            current is None
            or current.project_id != project_id
            or not self.backup_center.open_rom_studio_project(project_id)
        ):
            self.rom_studio.outbound_handoff_stopped(
                "Time Machine",
                "The requested project no longer matches the exact selected Studio project",
            )
            return
        self._navigate_route("time_machine")

    @Slot(str, str)
    def _open_device_center_from_studio(self, project_id: str, intent: str) -> None:
        """Carry one exact Studio project into Command Deck's read-only target evidence."""

        current = self.rom_studio.current_project
        if (
            current is None
            or current.project_id != project_id
            or current.original is None
            or intent not in {"build-readiness", "ascension-refresh"}
        ):
            self.rom_studio.outbound_handoff_stopped(
                "Command Deck",
                "The requested project or device-evidence purpose no longer matches Studio",
            )
            return
        profile = self.rom_studio.device_dna.profiles.load(project_id)
        model_fact = profile.fact("identity.model") if profile is not None else None
        codename_fact = profile.fact("identity.codename") if profile is not None else None
        context = RomStudioDeviceContext(
            project_id=current.project_id,
            project_name=current.name,
            source_sha256=current.original.sha256,
            device_pack_id=current.device_pack_id,
            expected_model=model_fact.value if model_fact is not None else "",
            expected_codename=codename_fact.value if codename_fact is not None else "",
            intent=intent,
        )
        if not self.device_center.open_rom_studio_context(context):
            self.rom_studio.outbound_handoff_stopped(
                "Command Deck",
                "Command Deck rejected incomplete exact project/device evidence",
            )
            return
        self._navigate_route("command_deck")
        if intent == "ascension-refresh":
            self.scan()

    @Slot(str, str, str)
    def _return_command_deck_rom_studio(
        self,
        project_id: str,
        source_sha256: str,
        intent: str,
    ) -> None:
        """Return Command Deck evidence to the exact source-bound Studio project."""

        if not self.rom_studio.open_command_deck_handoff(
            project_id,
            source_sha256,
            intent,
        ):
            self.device_center.studio_handoff_stopped(
                "The retained project, protected source, or handoff purpose is no longer current"
            )
            return
        self._navigate_route("rom_studio")

    @Slot(str)
    def _open_device_atlas_from_studio(self, project_id: str) -> None:
        """Carry one exact Studio project and source/Pack binding into Device Atlas."""

        current = self.rom_studio.current_project
        if current is None or current.project_id != project_id:
            self.rom_studio.outbound_handoff_stopped(
                "Device Atlas",
                "The requested project no longer matches the exact selected Studio project",
            )
            return
        source_sha256 = current.original.sha256 if current.original is not None else ""
        if not self.device_packs_center.open_rom_studio_project(
            current.project_id,
            current.name,
            current.device_pack_id,
            source_sha256,
        ):
            self.rom_studio.outbound_handoff_stopped(
                "Device Atlas",
                "Device Atlas rejected incomplete or changed project identity",
            )
            return
        self._navigate_route("device_atlas")

    @Slot(str)
    def _open_knowledge_route(self, route: str) -> None:
        aliases = {
            "device": "command_deck",
            "diagnostics": "quantum_optimizer",
            "history": "health_timeline",
            "guardian": "guardian_core",
            "recovery": "recovery_bay",
            "device_atlas": "device_atlas",
            "rom_studio": "rom_studio",
            "apk": "app_launchpad",
            "backup": "time_machine",
            "companion": "companion_link",
        }
        target = route if route in self.page_routes else aliases.get(route, "")
        recovery_identity = self.knowledge_center.recovery_review_identity
        if target == "recovery_bay" and recovery_identity is not None:
            self._return_archives_recovery(*recovery_identity)
            return
        self._navigate_route(target or f"knowledge:{route}")

    @Slot(str)
    def _open_knowledge_query(self, query: str) -> None:
        source_route = self._route_by_page_index.get(self.stack.currentIndex(), "")
        self._navigate_route("archives")
        self.knowledge_center.open_query(query, source_route=source_route)

    @Slot(str)
    def _open_knowledge_article(self, key: str) -> None:
        source_route = self._route_by_page_index.get(self.stack.currentIndex(), "")
        self._navigate_route("archives")
        self.knowledge_center.open_article(key, source_route=source_route)

    @Slot(object, object)
    def _handle_boot_observation(self, receipt: object, knowledge_report: object) -> None:
        """Route measured boot failure into Recovery Autopilot and close only on proof."""

        if not isinstance(receipt, BootObservationReceipt):
            return
        compatible_report = (
            knowledge_report
            if isinstance(knowledge_report, KnowledgeLookupReport)
            and knowledge_report.execution_authority == "none"
            else None
        )
        self.repair_center.update_recovery_boot_observation(receipt, compatible_report)
        if receipt.status is not BootObservationStatus.ATTENTION:
            return
        current_project = self.rom_studio.current_project
        device = self.rom_studio.devices[0] if len(self.rom_studio.devices) == 1 else None
        recovery_evidence = None
        if current_project is not None and current_project.project_id == receipt.project_id:
            with suppress(OSError, ProjectError):
                recovery_evidence = RecoveryEvidenceService(self.rom_studio.store).assess(
                    current_project.project_id,
                    device,
                )
        trigger = (
            RecoveryTrigger.BOOTLOOP
            if receipt.failure_kind is BootFailureKind.REBOOT_LOOP
            else RecoveryTrigger.BOOT_ATTENTION
        )
        created = self.repair_center.open_recovery_incident(
            trigger,
            project_id=receipt.project_id,
            message=receipt.diagnosis,
            boot_observation=receipt,
            knowledge_report=compatible_report,
            recovery_evidence=recovery_evidence,
        )
        if not created:
            return
        self._navigate_route("recovery_bay")
        self.notification_center.notify(
            f"recovery-autopilot.{receipt.project_id}.{receipt.failure_kind.value}",
            "Recovery Autopilot opened",
            "Measured boot evidence needs attention. ROMVERSE ranked evidence-backed routes and "
            "did not start a phone-changing action.",
            NotificationKind.ATTENTION,
        )

    @Slot(object, object)
    def _handle_first_light(self, report: object, knowledge_report: object) -> None:
        """Route measured subsystem failures to Recovery Autopilot without executing fixes."""

        if not isinstance(report, FirstLightReport) or not FirstLightService.needs_knowledge_lookup(
            report
        ):
            return
        compatible_report = (
            knowledge_report
            if isinstance(knowledge_report, KnowledgeLookupReport)
            and knowledge_report.execution_authority == "none"
            else None
        )
        project = self.rom_studio.current_project
        privacy = WorkspacePrivacy(self.rom_studio.store.workspace)
        device = next(
            (
                item
                for item in self.rom_studio.devices
                if privacy.pseudonym(item.serial) == report.device_key
            ),
            None,
        )
        recovery_evidence = None
        if project is not None and project.project_id == report.project_id:
            with suppress(OSError, ProjectError):
                recovery_evidence = RecoveryEvidenceService(self.rom_studio.store).assess(
                    report.project_id,
                    device,
                )
        created = self.repair_center.open_recovery_incident(
            RecoveryTrigger.MANUAL_DIAGNOSIS,
            project_id=report.project_id,
            message="; ".join(report.knowledge_queries),
            knowledge_report=compatible_report,
            recovery_evidence=recovery_evidence,
            target_device=device,
            # A First Light report is permanently bound to its pseudonymous phone.
            # If that phone is absent, keep the incident operationally targetless
            # instead of assigning it to a newly selected device.
            allow_current_device_fallback=False,
            expected_device_key=report.device_key,
        )
        if not created:
            return
        self._navigate_route("recovery_bay")
        self.notification_center.notify(
            f"recovery-autopilot.first-light.{report.report_id}",
            "First Light opened Recovery Autopilot",
            "Measured subsystem evidence needs attention. ROMVERSE ranked offline, "
            "evidence-backed routes and did not run a repair or phone-changing action.",
            NotificationKind.ATTENTION,
        )

    @Slot(str, str)
    def _open_autopilot_route(self, owner_route: str, route_id: str) -> None:
        """Open the typed route owner without turning a recommendation into execution."""

        archives_context = None
        if owner_route not in self.page_routes:
            self.notification_center.notify(
                f"recovery-autopilot.route.{route_id}",
                "Recovery route needs attention",
                "The route owner is unavailable. No scan, approval, repair, or phone action started.",
                NotificationKind.ATTENTION,
            )
            return
        if owner_route == "guardian_core":
            context = self.repair_center.recovery_route_context(route_id, owner_route)
            preparation = None
            recovery_live_target_service = None
            recovery_reviewed_device = None
            if context is not None and context[1].kind is RecoveryRouteKind.EXACT_STOCK_RESTORE:
                try:
                    preparation_service = GuardianRecoveryPreparationService(
                        self.rom_studio.store,
                        self.rom_studio.pack_registry,
                        self.repair_center.autopilot_service,
                    )
                    preparation = preparation_service.prepare(
                        context[0].incident_id,
                        context[1].route_id,
                        self.repair_center.devices,
                    )
                    recovery_reviewed_device = self._current_recovery_reviewed_device(
                        preparation.device_key
                    )
                    if recovery_reviewed_device is None:
                        raise GuardianRecoveryPreparationError(
                            "Reconnect the one exact phone involved in this Recovery incident"
                        )
                    if (
                        self._runtime_gateway is not None
                        and self._device_adb_executable is not None
                        and self._device_fastboot_executable is not None
                    ):
                        recovery_live_target_service = GuardianRecoveryLiveTargetReceiptService(
                            preparation_service,
                            AdbClient(self._device_adb_executable, self._runtime_gateway),
                            FastbootClient(self._device_fastboot_executable, self._runtime_gateway),
                        )
                except (
                    GuardianRecoveryPreparationError,
                    RecoveryAutopilotError,
                    ProjectError,
                    OSError,
                    TypeError,
                    ValueError,
                ) as exc:
                    self.notification_center.notify(
                        f"recovery-autopilot.route.{route_id}",
                        "Recovery preparation needs fresh evidence",
                        f"{exc}. The incident remains active and no phone action started.",
                        NotificationKind.ATTENTION,
                    )
                    return
            if context is None or not self.guardian_center.open_recovery_review(
                *context,
                preparation,
                recovery_live_target_service,
                recovery_reviewed_device,
            ):
                self.notification_center.notify(
                    f"recovery-autopilot.route.{route_id}",
                    "Recovery route context changed",
                    "Guardian did not accept stale, incomplete, or authority-bearing Recovery "
                    "context. The current Recovery incident remains active and no action started.",
                    NotificationKind.ATTENTION,
                )
                return
        elif owner_route == "time_machine":
            context = self.repair_center.recovery_route_context(route_id, owner_route)
            if context is None or not self.backup_center.open_recovery_review(*context):
                self.notification_center.notify(
                    f"recovery-autopilot.route.{route_id}",
                    "Recovery evidence context changed",
                    "Time Machine did not accept a missing, mismatched, or authority-bearing "
                    "Recovery prerequisite. The active incident remains unchanged.",
                    NotificationKind.ATTENTION,
                )
                return
        elif owner_route == "archives":
            archives_context = self.repair_center.recovery_route_context(route_id, owner_route)
            if archives_context is None:
                self.notification_center.notify(
                    f"recovery-autopilot.route.{route_id}",
                    "Recovery evidence context changed",
                    "Archives did not substitute a missing, changed, or unverified record. The "
                    "active Recovery incident remains unchanged and no action started.",
                    NotificationKind.ATTENTION,
                )
                return
        if not self._navigate_route(owner_route):
            return
        if archives_context is not None and not self.knowledge_center.open_recovery_review(
            *archives_context
        ):
            self._navigate_route("recovery_bay")
            self.notification_center.notify(
                f"recovery-autopilot.route.{route_id}",
                "Recovery evidence context changed",
                "Archives did not substitute a missing, changed, or unverified record. The "
                "active Recovery incident remains unchanged and no action started.",
                NotificationKind.ATTENTION,
            )
            return
        if owner_route == "guardian_core":
            self.guardian_center.request_refresh()
        self.notification_center.notify(
            f"recovery-autopilot.route.{route_id}",
            "Recovery route opened for review",
            "ROMVERSE opened the existing typed owner. The ranking granted no execution authority "
            "and started no phone command.",
            NotificationKind.INFORMATION,
        )

    def _current_recovery_reviewed_device(self, device_key: str) -> AndroidDevice | None:
        """Select one scan record by pseudonymous key; authority stays in Recovery services."""

        privacy = WorkspacePrivacy(self._workspace)
        scanned: dict[str, AndroidDevice] = {}
        for device in self.repair_center.devices:
            if device.serial:
                scanned.setdefault(device.serial, device)
        if len(scanned) != 1:
            return None
        device = next(iter(scanned.values()))
        return device if privacy.pseudonym(device.serial) == device_key else None

    @Slot()
    def _open_recovery_home(self) -> None:
        """Keep a stale Guardian handoff recoverable without reusing its old identity."""

        self._navigate_route("recovery_bay")

    @Slot()
    def _open_guardian_recovery_toolchain(self) -> None:
        """Route a missing read-only Recovery prerequisite to its real tool owner."""

        if not self._navigate_route("forge_arsenal"):
            return
        self.notification_center.notify(
            "recovery-autopilot.guardian-tools",
            "Recovery phone check needs Android Platform Tools",
            "Locate or repair verified ADB and Fastboot here, then return to the same active "
            "Recovery incident. No phone action started.",
            NotificationKind.ATTENTION,
        )

    @Slot(str, str)
    def _return_guardian_recovery(self, incident_id: str, route_id: str) -> None:
        """Return Guardian context to the same active incident and advisory route."""

        context = self.repair_center.recovery_route_context(route_id)
        if context is None or context[0].incident_id != incident_id:
            self.guardian_center.recovery_review_stopped(
                "The saved incident or route no longer matches current sealed Recovery evidence."
            )
            return
        preparation_digest = self.guardian_center.recovery_preparation_digest
        if preparation_digest:
            preparation = GuardianRecoveryPreparationService(
                self.rom_studio.store,
                self.rom_studio.pack_registry,
                self.repair_center.autopilot_service,
            ).load(incident_id, route_id, self.repair_center.devices)
            if preparation is None or preparation.preparation_digest != preparation_digest:
                self.guardian_center.recovery_review_stopped(
                    "The exact device, project, source, Device Pack, evidence, or prepared route changed."
                )
                return
        if not self._navigate_route(
            "recovery_bay"
        ) or not self.repair_center.restore_recovery_route(incident_id, route_id):
            self.guardian_center.recovery_review_stopped(
                "Recovery Bay could not restore the exact current incident and route."
            )

    @Slot(str, str)
    def _return_time_machine_recovery(self, incident_id: str, route_id: str) -> None:
        """Return exact Time Machine evidence to the same active Recovery route."""

        context = self.repair_center.recovery_route_context(route_id, "time_machine")
        assessment = self.backup_center.recovery_review_assessment(incident_id, route_id)
        if context is None or context[0].incident_id != incident_id or assessment is None:
            self.backup_center.recovery_review_stopped(
                "The project, incident, route, or Device Pack no longer matches the sealed handoff"
            )
            return
        if not self.repair_center.update_recovery_evidence(incident_id, assessment):
            self.backup_center.recovery_review_stopped(
                "Fresh local evidence could not be assigned to the exact active Recovery incident"
            )
            return
        refreshed = self.repair_center.recovery_route_context(route_id)
        if refreshed is None or refreshed[0].incident_id != incident_id:
            self.backup_center.recovery_review_stopped(
                "Recovery re-ranked the incident and the previous route is no longer current"
            )
            return
        if not self._navigate_route(
            "recovery_bay"
        ) or not self.repair_center.restore_recovery_route(incident_id, route_id):
            self.backup_center.recovery_review_stopped(
                "Recovery Bay could not restore the exact current incident and route"
            )
            return
        self.backup_center.clear_recovery_review()

    @Slot(str, str)
    def _return_archives_recovery(self, incident_id: str, route_id: str) -> None:
        """Return exact Archives evidence to its still-current Recovery route."""

        context = self.repair_center.recovery_route_context(route_id, "archives")
        if context is None or context[0].incident_id != incident_id:
            self.knowledge_center.recovery_review_stopped(
                "The saved incident, route, or exact Archives record set is no longer current."
            )
            return
        if not self._navigate_route(
            "recovery_bay"
        ) or not self.repair_center.restore_recovery_route(incident_id, route_id):
            self.knowledge_center.recovery_review_stopped(
                "Recovery Bay could not restore the exact current incident and evidence route."
            )
            return
        self.knowledge_center.clear_recovery_review()

    @Slot(str)
    def _open_repair_finding(self, finding_id: str) -> None:
        if self.repair_center.open_diagnostic_finding(finding_id):
            self.diagnostics_center.mark_repair_handoff(finding_id)
            self._navigate_route("recovery_bay")
            return
        self.diagnostics_center.show_repair_handoff_error(finding_id)
        self.notification_center.notify(
            f"repair.handoff.{finding_id[:60] or 'missing'}",
            "Repair handoff needs fresh evidence",
            "Recovery Bay could not match that finding to its current device report. "
            "Refresh Device Engine before opening a guided repair plan.",
            NotificationKind.ATTENTION,
        )

    @Slot(str)
    def _open_diagnostic_finding(self, finding_id: str) -> None:
        if self.diagnostics_center.open_finding(finding_id):
            self._navigate_route("quantum_optimizer")
            self.diagnostics_center.body.ensureWidgetVisible(
                self.diagnostics_center.finding_cards[finding_id.strip()[:120]], 0, 24
            )
            return
        self.repair_center.show_diagnostic_handoff_error(finding_id)
        self.notification_center.notify(
            f"diagnostics.handoff.{finding_id[:52] or 'missing'}",
            "Diagnostic source needs fresh evidence",
            "Quantum Optimizer could not match that Recovery Bay source to its current report. "
            "Refresh Device Engine before reviewing the finding.",
            NotificationKind.ATTENTION,
        )

    @Slot(object)
    def _diagnostic_report_changed(self, report: object) -> None:
        finding = actionable_repair_finding(
            report if isinstance(report, DiagnosticReport) else None
        )
        self.device_center.set_repair_context(
            finding.finding_id if finding is not None else "",
            finding.title if finding is not None else "",
        )

    @Slot(str)
    def _handle_dashboard_action(self, action: str) -> None:
        if action == "Continue Genesis":
            if self._navigate_route("rom_studio"):
                self.rom_studio.open_dashboard_intent("Build ROM")
            return
        if action in {"Build ROM", "Pre-Build Simulation", "Recipes"}:
            if self._navigate_route("rom_studio") and not self.rom_studio.open_dashboard_intent(
                action
            ):
                self.notification_center.notify(
                    f"command-deck.handoff.{action.casefold().replace(' ', '-')}",
                    "ROM Studio handoff needs attention",
                    "ROMVERSE opened ROM Studio but could not preserve the requested workflow. "
                    "No build or phone action started.",
                    NotificationKind.ATTENTION,
                )
            return
        owner_handoffs = {
            "Device DNA": ("device_atlas", self.device_packs_center),
            "Health Review": ("quantum_optimizer", self.diagnostics_center),
            "Rescue & Backup": ("time_machine", self.backup_center),
            "Guardian": ("guardian_core", self.guardian_center),
        }
        if action in owner_handoffs:
            route, owner = owner_handoffs[action]
            if self._navigate_route(route) and not owner.open_dashboard_intent(action):
                self.notification_center.notify(
                    f"command-deck.handoff.{action.casefold().replace(' ', '-')}",
                    "Command Deck handoff needs attention",
                    f"ROMVERSE opened {route.replace('_', ' ').title()} but could not preserve "
                    "the requested evidence view. No worker or phone action started.",
                    NotificationKind.ATTENTION,
                )
            return
        if action == "Theme":
            self._show_theme_menu()
            return
        if action == "Settings":
            self._open_settings()
            return
        if action == "Repair Phone":
            finding = actionable_repair_finding(self.diagnostics_center.current_report)
            if finding is not None and self.repair_center.open_diagnostic_finding(
                finding.finding_id
            ):
                self._navigate_route("recovery_bay")
                return
            self.repair_center.open_general_assessment(evidence_changed=finding is not None)
            self._navigate_route("recovery_bay")
            return
        targets = {
            "Timeline": "health_timeline",
            "Live Operations": "live_console",
            "Wireless Transfer": "companion_link",
            "ROMVERSE Lab": "nexus",
            "ROM Forge": "rom_studio",
            "Command Console": "command_console",
            "App Cleanse": "device_atlas",
            "Module Forge": "device_atlas",
            "Quantum Tune": "quantum_optimizer",
            "Optimize": "quantum_optimizer",
            "Install APK": "app_launchpad",
            "Time Snapshot": "time_machine",
            "Time Restore": "time_machine",
            "View Full Log": "activity_center",
            "View Activity Center": "activity_center",
        }
        target = targets.get(action)
        self._navigate_route(target or f"dashboard:{action}")

    @Slot()
    def _open_settings(self) -> None:
        dialog = SettingsDialog(
            self.device_center.workspace,
            self.app_settings,
            self,
            self.desktop_update_service,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        settings = dialog.values()
        self.app_settings = settings
        self.rom_studio.app_settings = settings
        self.repair_center.set_online_service(
            OnlineRemediationService.connected(
                self._workspace,
                include_community=settings.community_research_enabled,
            )
            if settings.online_intelligence_enabled
            else None
        )
        self.device_packs_center.online_catalog_enabled = settings.online_intelligence_enabled
        self.device_packs_center.set_catalog_status(self.device_catalog.status())
        self.online_status.set_monitoring_enabled(settings.online_intelligence_enabled)
        if not settings.online_intelligence_enabled and self.device_catalog_worker is not None:
            self.device_catalog_worker.cancel()
        if settings.online_intelligence_enabled and self.device_catalog.needs_refresh():
            self._catalog_auto_attempted = False
            QTimer.singleShot(0, self._maybe_refresh_device_catalog)
        self._apply_experience_mode(settings.experience_mode)
        self._apply_theme(settings.desktop_theme, persist=False)
        self.cosmic_background.set_reduced_motion(settings.reduced_motion)
        self._brand_logo.set_reduced_motion(settings.reduced_motion)
        self.about_page.logo.set_reduced_motion(settings.reduced_motion)
        self.about_page.set_privacy_settings(settings)
        self.notification_center.set_enabled(settings.desktop_notifications_enabled)
        self.notification_center.set_reduced_motion(settings.reduced_motion)
        self.diagnostics_center.set_reduced_motion(settings.reduced_motion)
        self.knowledge_center.set_reduced_motion(settings.reduced_motion)
        self.galaxy_center.set_reduced_motion(settings.reduced_motion)
        self.galaxy_center.set_contribution_opt_in(settings.synapse_contributions_enabled)
        self.backup_center.set_default_backup_directory(
            Path(settings.backup_directory) if settings.backup_directory else None
        )
        self.scan_interval_seconds = settings.scan_interval_seconds
        self.timer.setInterval(self.scan_interval_seconds * 1000)
        self.scan_interval_changed.emit(self.scan_interval_seconds)
        self.settings_changed.emit(settings)
        self.members_center.configure(settings.members_issuer, settings.members_client_id)
        self.galaxy_center.set_member_issuer(settings.members_issuer)
        self.device_center.device_note.setText(
            "Settings saved securely. Device timing, online research, verified tool acquisition, "
            "experience mode, Desktop theme, notifications, backup destination, accessibility, and Members "
            "configuration are active and persist after restart. Signed updates remain locked "
            "unless the packaged publisher identity verifies the selected release channel."
        )

    def _show_theme_menu(self) -> None:
        menu = QMenu(self)
        menu.setTitle("ROMVERSE Theme")
        for theme, (label, _override) in DESKTOP_THEMES.items():
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self.app_settings.desktop_theme is theme)
            action.triggered.connect(
                lambda _checked=False, selected=theme: self._apply_theme(selected)
            )
        button = self.device_center.export_button
        menu.popup(button.mapToGlobal(button.rect().bottomLeft()))

    def _apply_theme(self, theme: DesktopTheme, *, persist: bool = True) -> None:
        """Apply one validated presentation-only theme and persist explicit choices."""

        try:
            selected = DesktopTheme(theme)
        except ValueError:
            selected = DesktopTheme.NEBULA_FLOW
        label, override = DESKTOP_THEMES[selected]
        stylesheet = STYLESHEET + override
        app = QApplication.instance()
        if app is not None:
            apply_dark_palette(app)
            if app.styleSheet() != stylesheet:
                app.setStyleSheet(stylesheet)
        self.device_center.export_button.setText(f"Theme · {label}  ⌄")
        self.device_center.export_button.setToolTip(
            f"Current Desktop theme: {label}. Presentation only; Guardian and evidence are unchanged."
        )
        if persist and selected is not self.app_settings.desktop_theme:
            self.app_settings = replace(
                self.app_settings,
                schema_version=5,
                desktop_theme=selected,
            )
            self.rom_studio.app_settings = self.app_settings
            self.settings_changed.emit(self.app_settings)
            self.device_center.device_note.setText(
                f"{label} applied and saved. Projects, evidence, Guardian policy, and phone "
                "authority were unchanged."
            )
