from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from romverse.ascension import (
    AscensionAssessmentService,
    AscensionConsentReview,
    AscensionConsentReviewService,
    AscensionFinalHandoff,
    AscensionFinalHandoffService,
    AscensionGuardianManifest,
    AscensionGuardianManifestService,
    AscensionMethod,
    AscensionRecommendation,
    AscensionRootPlanService,
    AscensionRouteRecord,
    AscensionRouteRecordService,
    GateState,
    KernelSuSupportEvidenceService,
    ManifestState,
    OfficialRootReleaseService,
    PatchedImageReceipt,
    PatchedOutputDiscovery,
    PatchedOutputPlan,
    RootManagerLaunchPlan,
    RootManagerLaunchReceipt,
    RootManagerLaunchService,
    RootManagerPathPlan,
    RootPatchCapsule,
    RootPatchedOutputService,
    RootPatchHandoffPlan,
    RootPatchHandoffReceipt,
    RootPatchHandoffService,
    RootPatchPreparationService,
    RootRomBuildHandoffReceipt,
    RootRomBuildHandoffService,
    RootRomIntegrationReceipt,
    RootRomIntegrationService,
    build_journey_brief,
    build_journey_checkpoints,
    build_resolution_plan,
    load_root_patch_handoff,
)
from romverse.ascension.models import OfficialRootRelease
from romverse.ascension.releases import OfficialRootAcquisition, OfficialRootConnectivityError
from romverse.core.privacy import WorkspacePrivacy
from romverse.device.apk_install import (
    ApkInstallPlan,
    ApkInstallRequest,
    ApkInstallService,
    create_install_plan,
    install_succeeded,
)
from romverse.guardian.approval import ApprovalStore
from romverse.guardian.models import GuardianDeniedError
from romverse.infrastructure.process import CommandResult, CommandRunner, SubprocessRunner
from romverse.infrastructure.tools import ToolVerifier
from romverse.nexus.events import (
    LiveConsoleEventStore,
    LiveConsoleStoreError,
    MissionConfidence,
    MissionState,
)
from romverse.platform.host import current_host
from romverse.rom.inspection import ContainerKind, FindingSeverity
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.ui.background import (
    CoalescedProgress,
    ManagedRunnable,
    measured_percent,
    start_background,
)
from romverse.ui.guided_mission import GuidedBuildMission
from romverse.ui.process_progress import ProcessProgressBar


class AscensionReleaseSignals(QObject):
    complete = Signal(object)
    failed = Signal(str)
    connectivity_failed = Signal(str)
    progress = Signal(int)


class AscensionReleaseWorker(ManagedRunnable):
    def __init__(
        self,
        workspace: Path,
        method: AscensionMethod,
        aapt_executable: Path | None = None,
        apksigner_executable: Path | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        super().__init__()
        self.workspace = workspace
        self.method = method
        self.aapt_executable = aapt_executable
        self.apksigner_executable = apksigner_executable
        self.runner = runner or SubprocessRunner()
        self.signals = AscensionReleaseSignals()

    @Slot()
    def execute(self) -> None:
        publish_progress = CoalescedProgress(self.signals.progress.emit)
        try:
            service = OfficialRootReleaseService(
                self.workspace,
                aapt_executable=self.aapt_executable,
                apksigner_executable=self.apksigner_executable,
                runner=self.runner,
            )

            def report(done: int, total: int) -> None:
                with suppress(RuntimeError):
                    percent = measured_percent(done, total)
                    if percent is not None:
                        publish_progress(percent)

            result = service.acquire_latest_or_verified(self.method, report)
            with suppress(RuntimeError):
                self.signals.complete.emit(result)
        except OfficialRootConnectivityError as exc:
            with suppress(RuntimeError):
                self.signals.connectivity_failed.emit(str(exc))
        except (OSError, ProjectError) as exc:
            with suppress(RuntimeError):
                self.signals.failed.emit(str(exc))


class AscensionPreparationSignals(QObject):
    complete = Signal(object)
    failed = Signal(str)
    progress = Signal(int)


@dataclass(frozen=True, slots=True)
class AscensionManagerInstallPreparation:
    plan: ApkInstallPlan
    release: OfficialRootRelease
    manager_path: Path


@dataclass(frozen=True, slots=True)
class AscensionManagerInstallCompletion:
    """Exact, privacy-safe terminal evidence emitted after a successful Manager install."""

    plan_digest: str
    target_key: str
    apk_sha256: str
    package_name: str
    result: CommandResult


@dataclass(frozen=True, slots=True)
class AscensionOutputDiscoveryCompletion:
    """Bind filename results to the strict persisted discovery receipt that proves them."""

    names: tuple[str, ...]
    receipt: PatchedOutputDiscovery


class AscensionManagerPlanWorker(ManagedRunnable):
    """Inspect and bind a Manager APK without blocking the Ascension window."""

    def __init__(
        self,
        request: ApkInstallRequest,
        target_key: str,
        *,
        method: AscensionMethod,
        expected_release: OfficialRootRelease,
        expected_manager_path: Path,
        release_service: OfficialRootReleaseService,
        aapt_executable: Path | None = None,
        apksigner_executable: Path | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        super().__init__()
        self.request = request
        self.target_key = target_key
        self.method = method
        self.expected_release = expected_release
        self.expected_manager_path = expected_manager_path
        self.release_service = release_service
        self.aapt_executable = aapt_executable
        self.apksigner_executable = apksigner_executable
        self.runner = runner or SubprocessRunner()
        self.signals = AscensionPreparationSignals()

    @Slot()
    def execute(self) -> None:
        publish_progress = CoalescedProgress(self.signals.progress.emit)
        try:
            verified = self.release_service.load_verified(self.method)
            if verified is None:
                raise ProjectError("The official KernelSU Manager vault no longer verifies")
            release, manager_path = verified
            try:
                expected_path = self.expected_manager_path.expanduser().resolve(strict=True)
                current_path = manager_path.expanduser().resolve(strict=True)
            except OSError as exc:
                raise ProjectError("The official KernelSU Manager is unavailable") from exc
            if (
                current_path != expected_path
                or release.provider is not self.method
                or release.tag != self.expected_release.tag
                or release.asset.sha256 != self.expected_release.asset.sha256
                or release.asset.size_bytes != self.expected_release.asset.size_bytes
            ):
                raise ProjectError("The official KernelSU Manager changed before install planning")
            request = ApkInstallRequest(
                str(current_path),
                self.request.device_serial,
                allow_downgrade=self.request.allow_downgrade,
                execution_locked=self.request.execution_locked,
                battery_percent=self.request.battery_percent,
                device_free_bytes=self.request.device_free_bytes,
            )
            plan = create_install_plan(
                request,
                self.target_key,
                aapt_executable=self.aapt_executable,
                apksigner_executable=self.apksigner_executable,
                runner=self.runner,
                progress=publish_progress,
            )
            if (
                plan.inspection.sha256 != release.asset.sha256
                or plan.inspection.file_size != release.asset.size_bytes
            ):
                raise ProjectError("The official KernelSU Manager changed during install planning")
            with suppress(RuntimeError):
                self.signals.complete.emit(
                    AscensionManagerInstallPreparation(plan, release, current_path)
                )
        except (OSError, ProjectError) as exc:
            with suppress(RuntimeError):
                self.signals.failed.emit(str(exc))


class AscensionPreparationWorker(ManagedRunnable):
    def __init__(
        self,
        store: RomProjectStore,
        project_id: str,
        method: AscensionMethod,
        *,
        release: OfficialRootRelease | None = None,
        manager_path: Path | None = None,
        patched_path: Path | None = None,
        release_service: OfficialRootReleaseService | None = None,
    ) -> None:
        super().__init__()
        self.store = store
        self.project_id = project_id
        self.method = method
        self.release = release
        self.manager_path = manager_path
        self.patched_path = patched_path
        self.release_service = release_service
        self.signals = AscensionPreparationSignals()

    @Slot()
    def execute(self) -> None:
        service = RootPatchPreparationService(self.store, self.release_service)
        publish_progress = CoalescedProgress(self.signals.progress.emit)
        try:
            if self.patched_path is not None:
                result = service.import_patched(
                    self.project_id,
                    self.method,
                    self.patched_path,
                    publish_progress,
                )
            else:
                if self.release is None or self.manager_path is None:
                    raise ProjectError("The verified official manager is unavailable")
                result = service.prepare(
                    self.project_id,
                    self.method,
                    self.release,
                    self.manager_path,
                    publish_progress,
                )
            with suppress(RuntimeError):
                self.signals.complete.emit(result)
        except (OSError, ProjectError) as exc:
            with suppress(RuntimeError):
                self.signals.failed.emit(str(exc))


class AscensionIntegrationWorker(ManagedRunnable):
    def __init__(
        self,
        store: RomProjectStore,
        project_id: str,
        method: AscensionMethod,
    ) -> None:
        super().__init__()
        self.store = store
        self.project_id = project_id
        self.method = method
        self.signals = AscensionPreparationSignals()

    @Slot()
    def execute(self) -> None:
        publish_progress = CoalescedProgress(self.signals.progress.emit)
        try:
            receipt = RootRomIntegrationService(self.store).integrate(
                self.project_id,
                self.method,
                publish_progress,
            )
            with suppress(RuntimeError):
                self.signals.complete.emit(receipt)
        except (OSError, ProjectError) as exc:
            with suppress(RuntimeError):
                self.signals.failed.emit(str(exc))


class AscensionBuildSealWorker(ManagedRunnable):
    def __init__(
        self,
        store: RomProjectStore,
        project_id: str,
        method: AscensionMethod,
    ) -> None:
        super().__init__()
        self.store = store
        self.project_id = project_id
        self.method = method
        self.signals = AscensionPreparationSignals()

    @Slot()
    def execute(self) -> None:
        publish_progress = CoalescedProgress(self.signals.progress.emit)
        try:
            receipt = RootRomBuildHandoffService(self.store).seal(
                self.project_id,
                self.method,
                publish_progress,
            )
            with suppress(RuntimeError):
                self.signals.complete.emit(receipt)
        except (OSError, ProjectError) as exc:
            with suppress(RuntimeError):
                self.signals.failed.emit(str(exc))


class AscensionHandoffWorker(ManagedRunnable):
    def __init__(
        self,
        service: RootPatchHandoffService,
        plan: RootPatchHandoffPlan,
    ) -> None:
        super().__init__()
        self.service = service
        self.plan = plan
        self.signals = AscensionPreparationSignals()

    @Slot()
    def execute(self) -> None:
        publish_progress = CoalescedProgress(self.signals.progress.emit)
        try:
            result = self.service.execute(self.plan, publish_progress)
            with suppress(RuntimeError):
                self.signals.complete.emit(result)
        except (OSError, ProjectError, GuardianDeniedError) as exc:
            with suppress(RuntimeError):
                self.signals.failed.emit(str(exc))


class AscensionManagerLaunchWorker(ManagedRunnable):
    def __init__(
        self,
        service: RootManagerLaunchService,
        *,
        path_plan: RootManagerPathPlan | None = None,
        launch_plan: RootManagerLaunchPlan | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.path_plan = path_plan
        self.launch_plan = launch_plan
        self.signals = AscensionPreparationSignals()

    @Slot()
    def execute(self) -> None:
        publish_progress = CoalescedProgress(self.signals.progress.emit)
        try:
            if self.path_plan is not None and self.launch_plan is None:
                result = self.service.resolve_path(self.path_plan)
            elif self.launch_plan is not None and self.path_plan is None:
                result = self.service.execute(
                    self.launch_plan,
                    publish_progress,
                )
            else:
                raise ProjectError("The verified Manager open plan is incomplete")
            with suppress(RuntimeError):
                self.signals.complete.emit(result)
        except (OSError, ProjectError, GuardianDeniedError) as exc:
            with suppress(RuntimeError):
                self.signals.failed.emit(str(exc))


class AscensionPhoneOutputWorker(ManagedRunnable):
    def __init__(
        self,
        service: RootPatchedOutputService,
        *,
        project_id: str = "",
        method: AscensionMethod | None = None,
        serial: str = "",
        plan: PatchedOutputPlan | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.project_id = project_id
        self.method = method
        self.serial = serial
        self.plan = plan
        self.signals = AscensionPreparationSignals()

    @Slot()
    def execute(self) -> None:
        publish_progress = CoalescedProgress(self.signals.progress.emit)
        try:
            if self.plan is not None:
                result = self.service.retrieve_and_import(self.plan, publish_progress)
            elif self.project_id and self.method is not None and self.serial:
                names = self.service.find(self.project_id, self.method, self.serial)
                receipt = self.service.load_discovery(
                    self.project_id,
                    self.method,
                    self.serial,
                )
                if receipt is None:
                    raise ProjectError(
                        "Patched-output search finished without a verified discovery receipt"
                    )
                result = AscensionOutputDiscoveryCompletion(names, receipt)
            else:
                raise ProjectError("The patched-output search plan is incomplete")
            with suppress(RuntimeError):
                self.signals.complete.emit(result)
        except (OSError, ProjectError, GuardianDeniedError) as exc:
            with suppress(RuntimeError):
                self.signals.failed.emit(str(exc))


class AscensionManagerInstallWorker(ManagedRunnable):
    def __init__(self, service: ApkInstallService, plan: ApkInstallPlan) -> None:
        super().__init__()
        self.service = service
        self.plan = plan
        self.signals = AscensionPreparationSignals()

    @Slot()
    def execute(self) -> None:
        try:
            result = self.service.install(self.plan)
            if not install_succeeded(result):
                detail = (result.stderr or result.stdout).strip().replace("\n", " ")[:300]
                raise ProjectError(
                    f"Official KernelSU Manager installation failed: {detail or result.returncode}"
                )
            with suppress(RuntimeError):
                self.signals.complete.emit(
                    AscensionManagerInstallCompletion(
                        plan_digest=self.plan.digest,
                        target_key=self.plan.target_key,
                        apk_sha256=self.plan.inspection.sha256,
                        package_name=self.plan.inspection.package_name,
                        result=result,
                    )
                )
        except (OSError, ProjectError, GuardianDeniedError) as exc:
            with suppress(RuntimeError):
                self.signals.failed.emit(str(exc))


class AscensionManifestDialog(QDialog):
    """Plain-language inspection of a non-executable Guardian root manifest."""

    def __init__(
        self,
        manifest: AscensionGuardianManifest,
        parent: QWidget | None = None,
        resolver: Callable[[str], None] | None = None,
        final_handoff: AscensionFinalHandoff | None = None,
    ) -> None:
        super().__init__(parent)
        self.manifest = manifest
        self.setWindowTitle("ROMVERSE • Ascension Guardian Manifest")
        self.setMinimumSize(780, 620)
        self.resize(920, 740)
        self.setStyleSheet(GuidedBuildMission._stylesheet() + AscensionProtocolDialog._stylesheet())
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("MissionHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(26, 20, 26, 20)
        eyebrow = QLabel("ASCENSION PROTOCOL  /  GUARDIAN WRITE MANIFEST")
        eyebrow.setObjectName("MissionEyebrow")
        title = QLabel(
            "Final Guardian handoff packet is ready"
            if final_handoff is not None
            else (
                "Manifest ready for review"
                if manifest.review_ready
                else f"Guardian found {len(manifest.blockers)} safety gate(s) to resolve"
            )
        )
        title.setObjectName("MissionTitle")
        intro = QLabel(
            "This document explains exactly what a future approved root handoff would change. "
            "It contains no executable command and has not modified the phone. If its saved "
            "source, device, artifact, or storage evidence changes, ROMVERSE discards it and "
            "returns to the first affected step instead of preserving a stale approval."
        )
        intro.setObjectName("MissionMuted")
        intro.setWordWrap(True)
        header_layout.addWidget(eyebrow)
        header_layout.addWidget(title)
        header_layout.addWidget(intro)
        root.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        content = QVBoxLayout(host)
        content.setContentsMargins(26, 20, 26, 20)
        content.setSpacing(11)

        exact = QFrame()
        exact.setObjectName("AscensionOverview")
        exact_layout = QVBoxLayout(exact)
        exact_heading = QLabel("EXACT BINDING  •  WHAT ROMVERSE PROVED")
        exact_heading.setObjectName("CardHeading")
        exact_copy = QLabel(
            f"Phone  •  {manifest.device_name} ({manifest.device_codename})\n"
            f"Method  •  {manifest.method.display_name}\n"
            f"Target  •  {manifest.target_partition}  •  slot {manifest.target_slot or 'not yet proven'}\n"
            f"Patched image  •  {manifest.patched_image_sha256}\n"
            f"Pristine rollback  •  {manifest.pristine_image_sha256}\n"
            f"Required final transport  •  {manifest.required_transport}"
        )
        exact_copy.setObjectName("GateCopy")
        exact_copy.setWordWrap(True)
        exact_layout.addWidget(exact_heading)
        exact_layout.addWidget(exact_copy)
        content.addWidget(exact)

        if final_handoff is not None:
            backup_summary = (
                "hash-verified local-drive backup"
                if final_handoff.backup_evidence_kind == "verified-local-file"
                else "exact project/device-bound user-confirmed cloud backup (private contents not inspected)"
            )
            ready = QFrame()
            ready.setProperty("gateStatus", "pass")
            ready_layout = QVBoxLayout(ready)
            ready_heading = QLabel("FINAL HANDOFF PACKET  •  EXACT EVIDENCE SEALED")
            ready_heading.setObjectName("CardHeading")
            ready_copy = QLabel(
                f"ROMVERSE revalidated the exact USB phone, unlocked-bootloader signal, "
                f"slot {final_handoff.observed_slot}, {final_handoff.battery_percent}% battery, "
                f"{backup_summary}, Device Pack, pristine rollback image, patched image, and manager.\n"
                f"Packet digest  •  {final_handoff.handoff_digest}\n"
                "Evidence storage  •  PRIVATE • BOUNDED • LINK-SAFE\n"
                "Execution authority  •  NONE. A separate plain-language consent ceremony and "
                "fresh fastboot identity check are still required before any device write."
            )
            ready_copy.setObjectName("GateCopy")
            ready_copy.setWordWrap(True)
            ready_layout.addWidget(ready_heading)
            ready_layout.addWidget(ready_copy)
            content.addWidget(ready)

        for check in manifest.checks:
            row = QFrame()
            row.setProperty("gateStatus", check.state.value)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(15, 11, 15, 11)
            icon = QLabel(
                {
                    ManifestState.PASS: "✓",
                    ManifestState.ATTENTION: "!",
                    ManifestState.BLOCKED: "×",
                }[check.state]
            )
            icon.setObjectName("GateSymbol")
            icon.setFixedWidth(28)
            copy = QLabel(
                f"{check.label}\n{check.evidence}"
                + (f"\nNext: {check.resolution}" if check.state is not ManifestState.PASS else "")
            )
            copy.setObjectName("GateCopy")
            copy.setWordWrap(True)
            badge = QLabel(check.state.value.upper())
            badge.setObjectName("GateBadge")
            row_layout.addWidget(icon)
            row_layout.addWidget(copy, 1)
            if (
                check.state is not ManifestState.PASS
                and resolver is not None
                and check.action_id != "none"
            ):
                resolve = QPushButton(check.action_label)
                resolve.setObjectName("GateResolve")
                resolve.setToolTip(check.resolution)
                resolve.clicked.connect(
                    lambda _checked=False, action=check.action_id: self._resolve(action, resolver)
                )
                row_layout.addWidget(resolve)
            row_layout.addWidget(badge)
            row.setToolTip(check.resolution)
            content.addWidget(row)

        future = QFrame()
        future.setObjectName("AscensionHandoff")
        future_layout = QVBoxLayout(future)
        future_heading = QLabel("FINAL HANDOFF PLAN  •  EXPLANATION ONLY")
        future_heading.setObjectName("CardHeading")
        future_copy = QLabel(
            "\n".join(f"{index}. {step}" for index, step in enumerate(manifest.semantic_steps, 1))
        )
        future_copy.setObjectName("GateCopy")
        future_copy.setWordWrap(True)
        future_layout.addWidget(future_heading)
        future_layout.addWidget(future_copy)
        content.addWidget(future)

        prohibited = QFrame()
        prohibited.setProperty("gateStatus", "blocked")
        prohibited_layout = QVBoxLayout(prohibited)
        prohibited_heading = QLabel("PERMANENTLY PROHIBITED")
        prohibited_heading.setObjectName("CardHeading")
        prohibited_copy = QLabel("\n".join(f"×  {item}" for item in manifest.prohibited_actions))
        prohibited_copy.setObjectName("GateCopy")
        prohibited_copy.setWordWrap(True)
        prohibited_layout.addWidget(prohibited_heading)
        prohibited_layout.addWidget(prohibited_copy)
        content.addWidget(prohibited)
        content.addStretch()
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

        footer = QFrame()
        footer.setObjectName("MissionFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 13, 24, 13)
        status = QLabel(
            "Review artifact only  •  commands: NONE  •  root applied: NO  •  phone changed: NO"
        )
        status.setObjectName("MissionMuted")
        status.setWordWrap(True)
        footer_layout.addWidget(status, 1)
        if final_handoff is not None and resolver is not None:
            consent = QPushButton("Begin final consent review")
            consent.setObjectName("GateResolve")
            consent.setToolTip(
                "Record a short-lived plain-language review. This still creates no command or device-write authority."
            )
            consent.clicked.connect(
                lambda _checked=False: self._resolve("record-final-consent", resolver)
            )
            footer_layout.addWidget(consent)
        close = QPushButton("Close review")
        close.setObjectName("MissionNext")
        close.clicked.connect(self.accept)
        footer_layout.addWidget(close)
        root.addWidget(footer)

    def _resolve(self, action_id: str, resolver: Callable[[str], None]) -> None:
        self.accept()
        resolver(action_id)


class AscensionConsentReviewDialog(QDialog):
    """Explicit consequence review that cannot authorize or execute a device write."""

    ITEMS = (
        (
            "exact-device-reviewed",
            "I verified the exact phone, codename, target partition, and active slot shown below.",
        ),
        (
            "backup-and-rollback-reviewed",
            "I reviewed the independent backup and the pristine rollback image.",
        ),
        (
            "patched-image-reviewed",
            "I understand only the displayed SHA-256-bound patched image may be considered.",
        ),
        (
            "boot-risk-understood",
            "I understand a root image can fail to boot and may require the verified rollback route.",
        ),
        (
            "keep-data-no-wipe",
            "Keep data is the only reviewed action; this review does not authorize a data wipe.",
        ),
        (
            "bootloader-relock-prohibited",
            "I understand ROMVERSE will never relock the bootloader.",
        ),
        (
            "separate-device-write-approval-required",
            "I understand this review creates no command and a separate Guardian approval is still required.",
        ),
    )

    def __init__(self, handoff: AscensionFinalHandoff, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.handoff = handoff
        self.accepted_acknowledgements: tuple[str, ...] = ()
        self.setWindowTitle("ROMVERSE • Guardian Ascension Consent Review")
        self.setMinimumSize(760, 650)
        self.resize(880, 760)
        self.setStyleSheet(GuidedBuildMission._stylesheet() + AscensionProtocolDialog._stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(12)
        eyebrow = QLabel("ASCENSION PROTOCOL  /  FINAL CONSEQUENCE REVIEW")
        eyebrow.setObjectName("MissionEyebrow")
        title = QLabel("Review what a later Guardian-controlled write would mean")
        title.setObjectName("MissionTitle")
        intro = QLabel(
            "This ten-minute review record is bound to the exact evidence below. It does not "
            "create a fastboot command, approve a device write, root the phone, or change any data. "
            "ROMVERSE stores it privately and rejects corrupt, oversized, linked, redirected, or "
            "stale evidence automatically."
        )
        intro.setObjectName("MissionMuted")
        intro.setWordWrap(True)
        root.addWidget(eyebrow)
        root.addWidget(title)
        root.addWidget(intro)

        exact = QFrame()
        exact.setObjectName("AscensionOverview")
        exact_layout = QVBoxLayout(exact)
        exact_copy = QLabel(
            f"PHONE  •  {handoff.device_name} ({handoff.device_codename})\n"
            f"METHOD  •  {handoff.method.display_name}\n"
            f"TARGET  •  {handoff.target_partition}  •  slot {handoff.target_slot}\n"
            f"PATCHED IMAGE  •  {handoff.patched_image_sha256}\n"
            "DATA ACTION  •  KEEP DATA / NO WIPE\n"
            "BOOTLOADER RELOCK  •  PERMANENTLY PROHIBITED"
        )
        exact_copy.setObjectName("GateCopy")
        exact_copy.setWordWrap(True)
        exact_layout.addWidget(exact_copy)
        root.addWidget(exact)

        self.checkboxes: list[tuple[str, QCheckBox]] = []
        for acknowledgement, copy in self.ITEMS:
            checkbox = QCheckBox(copy)
            checkbox.setObjectName("ConsentCheck")
            checkbox.setProperty("acknowledgement", acknowledgement)
            checkbox.setToolTip(copy)
            checkbox.stateChanged.connect(self._update_ready)
            checkbox.setMinimumHeight(34)
            self.checkboxes.append((acknowledgement, checkbox))
            root.addWidget(checkbox)

        phrase_label = QLabel("Type ASCEND to confirm you read every item")
        phrase_label.setObjectName("CardHeading")
        self.phrase = QLineEdit()
        self.phrase.setPlaceholderText("ASCEND")
        self.phrase.setMaxLength(12)
        self.phrase.textChanged.connect(self._update_ready)
        root.addWidget(phrase_label)
        root.addWidget(self.phrase)
        root.addStretch()

        footer = QHBoxLayout()
        self.boundary = QLabel("Execution authority: NONE  •  commands: NONE  •  phone changed: NO")
        self.boundary.setObjectName("MissionMuted")
        self.boundary.setWordWrap(True)
        footer.addWidget(self.boundary, 1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.record_button = QPushButton("Save review — no device write")
        self.record_button.setObjectName("MissionNext")
        self.record_button.setEnabled(False)
        self.record_button.clicked.connect(self._accept_review)
        footer.addWidget(cancel)
        footer.addWidget(self.record_button)
        root.addLayout(footer)

    def _update_ready(self, *_args) -> None:
        ready = all(checkbox.isChecked() for _key, checkbox in self.checkboxes) and (
            self.phrase.text().strip() == "ASCEND"
        )
        self.record_button.setEnabled(ready)
        self.boundary.setText(
            "Ready to save a review record only  •  execution authority remains NONE"
            if ready
            else "Execution authority: NONE  •  commands: NONE  •  phone changed: NO"
        )

    def _accept_review(self) -> None:
        if not self.record_button.isEnabled():
            return
        self.accepted_acknowledgements = tuple(key for key, _checkbox in self.checkboxes)
        self.accept()


class AscensionProtocolDialog(QDialog):
    MANAGER_VERIFICATION_TOOLS = ("AAPT2", "APK Signer")
    PAYLOAD_EXTRACTION_TOOLS = ("Python", "Payload Dumper")
    """Device-aware root preparation; execution remains Guardian-locked."""

    OUTPUT_WATCH_SECONDS = 9 * 60
    OUTPUT_SCAN_INTERVAL_SECONDS = 12
    MANAGER_CONNECTIVITY_RETRY_DELAYS_MS = (1_500, 4_000)

    def __init__(self, studio, parent: QWidget | None = None) -> None:
        super().__init__(parent or studio)
        self.studio = studio
        self.project = studio.current_project
        if self.project is None:
            raise RuntimeError("Select a ROM project before opening Ascension Protocol")
        self.worker: ManagedRunnable | None = None
        self.automatic_attempted: set[AscensionMethod] = set()
        self.current_report = None
        self.current_brief = None
        self.route_record: AscensionRouteRecord | None = None
        self.verified_release: OfficialRootRelease | None = None
        self.manager_path: Path | None = None
        self.manager_install_plan: ApkInstallPlan | None = None
        self.manager_verification_note = ""
        self.manager_acquisition_mode = ""
        self.patch_capsule = None
        self.patched_receipt = None
        self.integration_receipt = None
        self.build_seal_receipt = None
        self.handoff_receipt = None
        self.manager_launch_receipt: RootManagerLaunchReceipt | None = None
        self.output_discovery: PatchedOutputDiscovery | None = None
        self.root_plan = None
        self.guardian_manifest = None
        self.final_handoff = None
        self._automatic_start_pending = False
        self.consent_review: AscensionConsentReview | None = None
        self.prerequisite_operation = ""
        self.context_refresh_pending = False
        self.live_mission_id = ""
        self.live_mission_method: AscensionMethod | None = None
        self.live_mission_progress = 0
        self.tool_runner = SubprocessRunner()
        self.output_watch_active = False
        self.output_watch_started_at = 0.0
        self.output_watch_last_scan_at = 0.0
        self.output_watch_scan_count = 0
        self.output_watch_timer = QTimer(self)
        self.output_watch_timer.setInterval(1_000)
        self.output_watch_timer.timeout.connect(self._watch_phone_output_tick)
        self.manager_retry_attempts: dict[AscensionMethod, int] = {}
        self.manager_retry_method: AscensionMethod | None = None
        self.manager_retry_timer = QTimer(self)
        self.manager_retry_timer.setSingleShot(True)
        self.manager_retry_timer.timeout.connect(self._retry_official_manager)
        self.setWindowTitle("ROMVERSE • Ascension Protocol")
        self.setMinimumSize(900, 680)
        self.resize(1120, 780)
        self.setStyleSheet(GuidedBuildMission._stylesheet() + self._stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QFrame()
        header.setObjectName("MissionHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(28, 20, 28, 20)
        copy = QVBoxLayout()
        eyebrow = QLabel("ROM STUDIO  /  ASCENSION PROTOCOL")
        eyebrow.setObjectName("MissionEyebrow")
        title = QLabel("Root preparation with proof at every gate")
        title.setObjectName("MissionTitle")
        intro = QLabel(
            "ROMVERSE identifies the exact source and phone, chooses a compatible path, verifies official tools, and prepares the handoff. No unlock, wipe, patch, root, or flash runs silently."
        )
        intro.setObjectName("MissionMuted")
        intro.setWordWrap(True)
        copy.addWidget(eyebrow)
        copy.addWidget(title)
        copy.addWidget(intro)
        header_layout.addLayout(copy, 1)
        self.method = QComboBox()
        self.method.addItem("Magisk  •  official image patch workflow", AscensionMethod.MAGISK)
        self.method.addItem(
            "KernelSU LKM  •  kernel/KMI support required", AscensionMethod.KERNELSU_LKM
        )
        self.method.setVisible(False)
        self.route_toggle = QPushButton("Change route  •  advanced")
        self.route_toggle.setCheckable(True)
        self.route_toggle.setToolTip(
            "ROMVERSE selects the safest supported route automatically. Open this only when you understand why a different root method is required."
        )
        self.route_toggle.toggled.connect(self.method.setVisible)
        self.recommendation_badge = QLabel()
        self.recommendation_badge.setObjectName("GuardianBadge")
        self.recommendation_badge.setWordWrap(True)
        selector = QVBoxLayout()
        selector.setSpacing(6)
        selector.addWidget(self.recommendation_badge)
        selector.addWidget(self.route_toggle)
        selector.addWidget(self.method)
        recommendation = self._root_recommendation()
        recommended_index = self.method.findData(recommendation.method)
        if recommended_index >= 0:
            self.method.setCurrentIndex(recommended_index)
        self._render_recommendation(recommendation)
        self.method.currentIndexChanged.connect(self._method_changed)
        header_layout.addLayout(selector)
        root.addWidget(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.host = QWidget()
        self.content = QVBoxLayout(self.host)
        self.content.setContentsMargins(28, 22, 28, 22)
        self.content.setSpacing(12)
        self.scroll.setWidget(self.host)
        root.addWidget(self.scroll, 1)

        footer = QFrame()
        footer.setObjectName("MissionFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 14, 24, 14)
        self.status = QLabel("Assessment is local and read-only.")
        self.status.setObjectName("MissionMuted")
        self.status.setWordWrap(True)
        footer_layout.addWidget(self.status, 1)
        self.progress = ProcessProgressBar()
        self.progress.setFixedWidth(190)
        footer_layout.addWidget(self.progress)
        self.learn_button = QPushButton("Learn this stage")
        self.learn_button.setToolTip(
            "Pause Ascension safely and open the verified beginner guide for the current stage in ROMVERSE Archives."
        )
        self.learn_button.clicked.connect(self._open_stage_learning)
        footer_layout.addWidget(self.learn_button)
        self.acquire_button = QPushButton("Acquire verified official manager")
        self.acquire_button.setObjectName("MissionNext")
        self.acquire_button.setToolTip(
            "Download the current stable manager APK from its official GitHub repository, require the published SHA-256, and place it in the content-addressed Ascension vault. It is not installed on the phone."
        )
        self.acquire_button.clicked.connect(self._primary_action)
        footer_layout.addWidget(self.acquire_button)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        footer_layout.addWidget(close)
        root.addWidget(footer)
        self.refresh()
        self.studio.operation_progress.connect(self._prerequisite_progress)
        self.studio.operation_completed.connect(self._prerequisite_complete)
        self.studio.operation_failed.connect(self._prerequisite_failed)
        self.studio.device_context_changed.connect(self._device_context_changed)

    def _open_stage_learning(self) -> None:
        brief = self.current_brief
        if brief is None:
            self.status.setText("ROMVERSE is still determining the current Ascension stage.")
            return
        if self.worker is not None or self.prerequisite_operation:
            self.status.setText(
                "Finish the current safe Ascension step before opening its learning guide."
            )
            return
        query = f"Ascension stage {brief.stage_number}"
        self.accept()
        self.studio.knowledge_requested.emit(query)

    def _method_changed(self) -> None:
        self._cancel_manager_retry(clear_budget=True)
        self._stop_output_watch()
        self._finish_ascension_live(
            MissionState.ATTENTION,
            "Ascension route changed after review.",
            "ROMVERSE closed the previous preparation timeline instead of combining evidence from two root methods.",
            "The selected route will start a new source-bound preparation timeline.",
            MissionConfidence.HIGH,
        )
        self.verified_release = None
        self.manager_path = None
        self.manager_install_plan = None
        self.manager_verification_note = ""
        self.manager_acquisition_mode = ""
        self.patch_capsule = None
        self.patched_receipt = None
        self.integration_receipt = None
        self.build_seal_receipt = None
        self.handoff_receipt = None
        self.manager_launch_receipt = None
        self.output_discovery = None
        self.root_plan = None
        self.guardian_manifest = None
        self.final_handoff = None
        self._render_recommendation(self._root_recommendation())
        self.refresh()

    def _root_recommendation(self) -> AscensionRecommendation:
        assessment = AscensionAssessmentService(
            self.studio.store,
            self.studio.pack_registry,
            self._release_service(),
        )
        device = next(iter(self.studio.devices), None)
        companion = getattr(self.studio, "companion_snapshot", None)
        try:
            self.route_record = AscensionRouteRecordService(
                self.studio.store,
                self.studio.pack_registry,
                assessment,
            ).resolve(self.project.project_id, device, companion)
        except ProjectError:
            self.route_record = None
            return assessment.recommend(self.project.project_id, device, companion)
        return AscensionRecommendation(
            self.route_record.candidate_method,
            self.route_record.title,
            self.route_record.reason,
            self.route_record.evidence,
            self.route_record.ready_for_local_preparation,
        )

    def _render_recommendation(self, recommendation: AscensionRecommendation) -> None:
        self.recommendation_badge.setText(f"◆  AUTO ROUTE  •  {recommendation.title}")
        evidence = "\n".join(f"• {item}" for item in recommendation.evidence)
        record = (
            f"\n\nRoute record: {self.route_record.record_digest[:16]}…"
            f"\nState: {self.route_record.state}"
            "\nExecution authority: NONE"
            if self.route_record is not None
            else ""
        )
        self.recommendation_badge.setToolTip(
            recommendation.reason + record + (f"\n\nEvidence:\n{evidence}" if evidence else "")
        )

    def _live_console_store(self) -> LiveConsoleEventStore | None:
        store = getattr(self.studio, "live_console_store", None)
        return store if isinstance(store, LiveConsoleEventStore) else None

    def _finish_ascension_live(
        self,
        state: MissionState,
        summary: str,
        explanation: str,
        next_action: str,
        confidence: MissionConfidence,
        evidence_refs: tuple[str, ...] = (),
    ) -> None:
        mission_id = self.live_mission_id
        self.live_mission_id = ""
        self.live_mission_method = None
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
                evidence_refs=evidence_refs,
            )

    def _sync_ascension_live(self, method: AscensionMethod, report, brief) -> None:
        store = self._live_console_store()
        if store is None:
            return
        project_ref = f"projects/{self.project.project_id}/ascension"
        if self.final_handoff is not None:
            refs = (
                f"{project_ref}/guardian/final-handoff.romverse",
                f"projects/{self.project.project_id}/device-dna.romverse",
                f"{project_ref}/route/route-record.romverse",
            )
            if self.live_mission_id:
                self._finish_ascension_live(
                    MissionState.SUCCEEDED,
                    "Ascension root preparation is sealed for Guardian review.",
                    "The exact source, Device DNA, official manager, patched ROM input, rollback evidence, backup, and phone binding were verified. Root has not been applied.",
                    "Continue the ROM build; a later Guardian flash review requires separate informed consent.",
                    MissionConfidence.VERIFIED,
                    refs,
                )
            else:
                with suppress(LiveConsoleStoreError):
                    store.note(
                        source="Ascension Protocol",
                        stage="root-preparation-sealed",
                        title=f"{method.display_name} preparation sealed",
                        summary="Verified root preparation is already complete; root applied: NO.",
                        explanation="ROMVERSE revalidated the sealed Guardian handoff without running a device write.",
                        next_action="Continue the rooted ROM build and review Guardian before any flash.",
                        state=MissionState.INFORMATION,
                        progress_percent=100,
                        confidence=MissionConfidence.VERIFIED,
                        guardian_protected=True,
                        project_id=self.project.project_id,
                        evidence_refs=refs,
                        dedupe_key=f"ascension-sealed-{self.final_handoff.handoff_digest}",
                    )
            return
        if self.live_mission_id and self.live_mission_method is not method:
            self._finish_ascension_live(
                MissionState.ATTENTION,
                "Ascension route changed.",
                "The previous method timeline was closed so its evidence cannot be mixed with the new route.",
                "Follow the new route shown by ROMVERSE.",
                MissionConfidence.HIGH,
            )
        if self.live_mission_id and brief.progress_percent < self.live_mission_progress:
            self._finish_ascension_live(
                MissionState.ATTENTION,
                "Ascension evidence changed and the route was safely recalculated.",
                "A completed stage no longer had matching source-bound evidence, so ROMVERSE did not preserve stale progress.",
                "Review the newly highlighted prerequisite.",
                MissionConfidence.HIGH,
            )
        if not self.live_mission_id:
            try:
                event = store.start(
                    source="Ascension Protocol",
                    stage="root-preparation",
                    title=f"Prepare {method.display_name} rooted ROM input",
                    summary="ROMVERSE started source-bound root preparation.",
                    explanation="Ascension prepares a rooted ROM input while Guardian keeps root, flash, unlock, wipe, and relock unavailable.",
                    next_action=brief.user_action,
                    project_id=self.project.project_id,
                    confidence=MissionConfidence.UNCONFIRMED,
                    guardian_protected=True,
                    evidence_refs=(
                        f"projects/{self.project.project_id}/device-dna.romverse",
                        f"{project_ref}/route/route-record.romverse",
                    ),
                )
            except LiveConsoleStoreError:
                return
            self.live_mission_id = event.mission_id
            self.live_mission_method = method
            self.live_mission_progress = 0
        try:
            store.progress(
                self.live_mission_id,
                brief.progress_percent,
                summary=f"Stage {brief.stage_number} of 9 — {brief.title}.",
                explanation=(
                    f"{brief.romverse_action} This preparation stage cannot root, flash, "
                    "unlock, wipe, or relock the phone."
                ),
                next_action=brief.user_action,
            )
            self.live_mission_progress = brief.progress_percent
        except LiveConsoleStoreError:
            self.live_mission_id = ""
            self.live_mission_method = None
            self.live_mission_progress = 0

    @Slot()
    def _device_context_changed(self) -> None:
        """Reassess automatically when fresh phone, Companion, or ADB evidence arrives."""

        self._cancel_manager_retry(clear_budget=True)
        if self.output_watch_active and self.worker is None:
            self._stop_output_watch()
        if self.worker is not None or self.prerequisite_operation:
            self.context_refresh_pending = True
            self.status.setText(
                "New phone evidence received  •  ROMVERSE will re-check it as soon as the current safe step finishes."
            )
            return
        recommendation = self._root_recommendation()
        current = AscensionMethod(self.method.currentData())
        if (
            recommendation.ready
            and recommendation.method is not current
            and self.patch_capsule is None
            and self.handoff_receipt is None
            and self.patched_receipt is None
        ):
            index = self.method.findData(recommendation.method)
            if index >= 0:
                self.method.setCurrentIndex(index)
                return
        self.status.setText(
            "New phone or tool evidence received  •  ROMVERSE is re-checking every Ascension gate automatically …"
        )
        self.refresh()
        QTimer.singleShot(0, self._ensure_patch_capsule)

    def reject(self) -> None:
        if self.worker is not None:
            self.status.setText("Official artifact verification is still running.")
            return
        self._cancel_manager_retry(clear_budget=False)
        self._stop_output_watch()
        self._finish_ascension_live(
            MissionState.ATTENTION,
            "Ascension preparation was paused.",
            "The dialog closed before root preparation was sealed. Verified local evidence remains preserved.",
            "Reopen Ascension Protocol to continue from the last verified stage.",
            MissionConfidence.HIGH,
        )
        super().reject()

    def accept(self) -> None:
        if self.worker is not None:
            self.status.setText("Finish the current verified Ascension step before closing.")
            return
        self._cancel_manager_retry(clear_budget=False)
        self._stop_output_watch()
        self._finish_ascension_live(
            MissionState.ATTENTION,
            "Ascension preparation was paused.",
            "The dialog closed before root preparation was sealed. Verified local evidence remains preserved.",
            "Reopen Ascension Protocol to continue from the last verified stage.",
            MissionConfidence.HIGH,
        )
        super().accept()

    def refresh(self) -> None:
        while self.content.count():
            item = self.content.takeAt(0)
            if (widget := item.widget()) is not None:
                widget.deleteLater()
        self._render_recommendation(self._root_recommendation())
        method = AscensionMethod(self.method.currentData())
        device = next(iter(self.studio.devices), None)
        report = AscensionAssessmentService(
            self.studio.store,
            self.studio.pack_registry,
            self._release_service(),
        ).assess(
            self.project.project_id,
            method,
            device,
            getattr(self.studio, "companion_snapshot", None),
        )
        self.current_report = report
        preparation = RootPatchPreparationService(self.studio.store)
        self.patch_capsule = preparation.load(self.project.project_id, method)
        self.patched_receipt = preparation.load_patched(self.project.project_id, method)
        self.integration_receipt = RootRomIntegrationService(self.studio.store).load(
            self.project.project_id, method
        )
        self.build_seal_receipt = RootRomBuildHandoffService(self.studio.store).load(
            self.project.project_id, method
        )
        handoff = self._handoff_service()
        self.handoff_receipt = (
            handoff.load(self.project.project_id, method) if handoff is not None else None
        )
        manager_launch = self._manager_launch_service()
        self.manager_launch_receipt = (
            manager_launch.load(self.project.project_id, method)
            if manager_launch is not None and self.handoff_receipt is not None
            else None
        )
        output_service = self._patched_output_service()
        self.output_discovery = (
            output_service.load_discovery(self.project.project_id, method, device.serial)
            if output_service is not None
            and self.handoff_receipt is not None
            and device is not None
            and getattr(device.state, "value", "") == "device"
            else None
        )
        self.root_plan = AscensionRootPlanService(self.studio.store).load(
            self.project.project_id, method
        )
        manifest_service = AscensionGuardianManifestService(
            self.studio.store,
            self.studio.pack_registry,
            getattr(self.studio, "attestation_store", None),
        )
        self.guardian_manifest = manifest_service.load(self.project.project_id, method)
        exact_device = None
        if self.root_plan is not None and self.patched_receipt is not None:
            exact_device = next(
                (
                    item
                    for item in self.studio.devices
                    if item.state is not None
                    and AscensionRootPlanService(self.studio.store).matches_device(
                        self.root_plan, item
                    )
                ),
                None,
            )
            if exact_device is not None and self.guardian_manifest is None:
                with suppress(ProjectError):
                    self.guardian_manifest = manifest_service.prepare(
                        self.project.project_id, method, exact_device
                    )
        final_service = AscensionFinalHandoffService(self.studio.store, manifest_service)
        self.final_handoff = (
            final_service.load(
                self.project.project_id,
                method,
                exact_device,
            )
            if exact_device is not None
            else None
        )
        if (
            self.final_handoff is None
            and exact_device is not None
            and self.guardian_manifest is not None
            and self.guardian_manifest.review_ready
        ):
            with suppress(ProjectError):
                self.final_handoff = final_service.prepare(
                    self.project.project_id,
                    method,
                    exact_device,
                )
        self.consent_review = (
            AscensionConsentReviewService(self.studio.store, final_service).load(
                self.project.project_id,
                method,
                exact_device,
            )
            if self.final_handoff is not None and exact_device is not None
            else None
        )

        overview = QFrame()
        overview.setObjectName("AscensionOverview")
        overview_layout = QVBoxLayout(overview)
        source = QLabel(f"DETECTED SOURCE  •  {report.source_summary}")
        source.setObjectName("CardHeading")
        target = QLabel(
            f"PATCH TARGET  •  {report.patch_target or 'Not yet available'}\n"
            "EXECUTION  •  GUARDIAN LOCKED — preparation cannot modify the phone\n"
            "EVIDENCE RECOVERY  •  If rollback, patch, integration, build, phone-handoff, "
            "Manager-open, or output-scan evidence is corrupt, oversized, linked, redirected, "
            "or stale, ROMVERSE discards it and returns to the first safe stage that can rebuild it."
        )
        target.setObjectName("GateCopy")
        target.setWordWrap(True)
        overview_layout.addWidget(source)
        overview_layout.addWidget(target)
        self.content.addWidget(overview)

        if self.route_record is not None:
            route = QFrame()
            route.setProperty(
                "gateStatus",
                "pass"
                if self.route_record.state == "ready-local-only"
                else "blocked"
                if self.route_record.state == "blocked"
                else "attention",
            )
            route_layout = QVBoxLayout(route)
            route_layout.setContentsMargins(16, 13, 16, 13)
            selected = (
                self.route_record.recommended_method.display_name
                if self.route_record.recommended_method is not None
                else "No route authorized yet"
            )
            route_title = QLabel(
                f"AUTOMATIC ROUTE RECORD  •  {selected.upper()}  •  "
                f"{self.route_record.confidence.upper()}"
            )
            route_title.setObjectName("CardHeading")
            route_copy = QLabel(
                f"{self.route_record.reason}\n\n"
                f"Source authority: {self.route_record.source_authority}; "
                f"Device DNA identity: {self.route_record.device_dna_identity_state}; "
                f"blocking gates: {self.route_record.blocker_count}.\n"
                f"Evidence record: {self.route_record.record_digest[:20]}…  •  "
                "private bounded storage: VERIFIED  •  "
                "execution authority: NONE  •  phone changed: NO  •  "
                "bootloader relock: NEVER"
            )
            route_copy.setObjectName("GateCopy")
            route_copy.setWordWrap(True)
            route_layout.addWidget(route_title)
            route_layout.addWidget(route_copy)
            route.setToolTip(
                "ROMVERSE automatically replaces this record when the protected source, "
                "Device DNA, phone identity, kernel evidence, or route readiness changes. "
                "Malformed, oversized, linked, or redirected evidence is rejected instead of "
                "being used to select a root method."
            )
            self.content.addWidget(route)

        resolution_plan = build_resolution_plan(report)
        if resolution_plan.steps:
            resolution = QFrame()
            resolution.setProperty(
                "gateStatus",
                "blocked" if resolution_plan.state == "safety-stop" else "attention",
            )
            resolution_layout = QVBoxLayout(resolution)
            resolution_layout.setContentsMargins(16, 13, 16, 13)
            resolution_title = QLabel(
                "AUTOMATIC RESOLUTION PLAN  •  "
                f"{resolution_plan.automatic_step_count} ROMVERSE STEP(S)  •  "
                f"{resolution_plan.user_step_count} USER STEP(S)"
            )
            resolution_title.setObjectName("CardHeading")
            resolution_copy = QLabel(
                "\n\n".join(
                    f"{index}. {step.title}\n"
                    f"ROMVERSE: {step.romverse_action}\n"
                    f"You: {step.user_action}"
                    for index, step in enumerate(resolution_plan.steps, 1)
                )
                + "\n\nEvery completed step is reassessed from evidence. No root, flash, wipe, "
                "unlock, or bootloader relock is authorized."
            )
            resolution_copy.setObjectName("GateCopy")
            resolution_copy.setWordWrap(True)
            resolution_layout.addWidget(resolution_title)
            resolution_layout.addWidget(resolution_copy)
            self.content.addWidget(resolution)

        brief = build_journey_brief(
            method,
            blocked=report.blocked,
            manager_verified=self.verified_release is not None,
            capsule_ready=self.patch_capsule is not None,
            handoff_ready=self.handoff_receipt is not None,
            patched_ready=self.patched_receipt is not None,
            integration_ready=self.integration_receipt is not None,
            build_handoff_ready=self.build_seal_receipt is not None,
            plan_ready=self.root_plan is not None,
            manifest_ready=self.guardian_manifest is not None,
            review_ready=bool(self.guardian_manifest and self.guardian_manifest.review_ready),
            manager_opened=self.manager_launch_receipt is not None,
        )
        self.current_brief = brief
        self._sync_ascension_live(method, report, brief)
        guide = QFrame()
        guide.setObjectName("AscensionGuide")
        guide_layout = QVBoxLayout(guide)
        guide_layout.setContentsMargins(18, 14, 18, 14)
        guide_layout.setSpacing(6)
        guide_title = QLabel(
            f"NEXT SAFE ACTION  •  STAGE {brief.stage_number} OF 9  •  {brief.title.upper()}"
        )
        guide_title.setObjectName("CardHeading")
        journey_progress = QProgressBar()
        journey_progress.setObjectName("AscensionJourneyProgress")
        journey_progress.setRange(0, 100)
        journey_progress.setValue(brief.progress_percent)
        journey_progress.setFormat(
            f"{brief.verified_checkpoints} of 9 evidence checkpoints verified  •  %p%"
        )
        journey_progress.setAccessibleName(
            f"Ascension progress: {brief.verified_checkpoints} of 9 evidence checkpoints verified"
        )
        journey_progress.setTextVisible(True)
        journey_progress.setToolTip(
            "Overall Ascension progress advances only when a source-bound checkpoint reloads from verified evidence. The current stage number is not treated as completed progress."
        )
        guide_copy = QLabel(
            f"ROMVERSE WILL DO\n{brief.romverse_action}\n\nYOUR PART\n{brief.user_action}\n\n"
            f"WHY THIS MATTERS\n{brief.why}\n\n"
            "GUARDIAN BOUNDARY  •  no root, flash, wipe, unlock, or bootloader relock occurs in preparation."
        )
        guide_copy.setObjectName("GateCopy")
        guide_copy.setWordWrap(True)
        guide_layout.addWidget(guide_title)
        guide_layout.addWidget(journey_progress)
        guide_layout.addWidget(guide_copy)
        self.content.addWidget(guide)

        workflow = QFrame()
        workflow.setObjectName("AscensionWorkflow")
        workflow_layout = QHBoxLayout(workflow)
        workflow_layout.setContentsMargins(12, 10, 12, 10)
        workflow_layout.setSpacing(8)
        blocked = sum(gate.state is GateState.BLOCKED for gate in report.gates)
        stages = build_journey_checkpoints(
            blocked=report.blocked,
            manager_verified=self.verified_release is not None,
            capsule_ready=self.patch_capsule is not None,
            handoff_ready=self.handoff_receipt is not None,
            patched_ready=self.patched_receipt is not None,
            integration_ready=self.integration_receipt is not None,
            build_handoff_ready=self.build_seal_receipt is not None,
            plan_ready=self.root_plan is not None,
            manifest_ready=self.guardian_manifest is not None,
            final_handoff_ready=self.final_handoff is not None,
        )
        first_pending = next(
            (index for index, checkpoint in enumerate(stages) if not checkpoint.complete),
            -1,
        )
        for index, checkpoint in enumerate(stages):
            stage = QLabel(
                f"{'✓' if checkpoint.complete else checkpoint.stage_number}\n{checkpoint.title}"
            )
            stage.setProperty(
                "stageState",
                "complete"
                if checkpoint.complete
                else "active"
                if index == first_pending
                else "pending",
            )
            stage.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stage.setWordWrap(True)
            stage.setToolTip(
                f"Stage {checkpoint.stage_number} of 9 — {checkpoint.title}.\n"
                + (
                    "Completed and revalidated by ROMVERSE evidence."
                    if checkpoint.complete
                    else "Not complete. ROMVERSE will resolve this stage only when its exact evidence exists; device-changing work still requires Guardian approval."
                )
            )
            workflow_layout.addWidget(stage, 1)
        self.content.addWidget(workflow)

        if self.verified_release is not None and self.manager_path is not None:
            manager_card = QFrame()
            cached_fallback = self.manager_acquisition_mode == "verified-cache"
            manager_card.setProperty("gateStatus", "attention" if cached_fallback else "pass")
            manager_layout = QHBoxLayout(manager_card)
            manager_layout.setContentsMargins(16, 12, 16, 12)
            manager_heading = (
                "OFFICIAL ROOT MANAGER  •  REVALIDATED CACHE  •  ONLINE FRESHNESS PENDING\n"
                if cached_fallback
                else "OFFICIAL ROOT MANAGER  •  CURRENT RELEASE PROVENANCE VERIFIED\n"
            )
            manager_copy = QLabel(
                manager_heading
                + f"{self.verified_release.repository}  •  {self.verified_release.tag}  •  "
                f"SHA-256 {self.verified_release.asset.sha256[:20]}…\n"
                f"{self.manager_verification_note}  •  installed on phone: NO"
            )
            manager_copy.setObjectName("GateCopy")
            manager_copy.setWordWrap(True)
            manager_layout.addWidget(manager_copy, 1)
            self.content.addWidget(manager_card)

        for gate in report.gates:
            card = QFrame()
            card.setProperty("gateStatus", gate.state.value)
            layout = QHBoxLayout(card)
            layout.setContentsMargins(16, 12, 16, 12)
            icon = QLabel(
                {GateState.PASS: "✓", GateState.ATTENTION: "!", GateState.BLOCKED: "×"}[gate.state]
            )
            icon.setObjectName("GateSymbol")
            icon.setFixedWidth(28)
            copy = QLabel(
                f"{gate.title}\n{gate.detail}"
                + (f"\nNext: {gate.resolution}" if gate.resolution else "")
            )
            copy.setObjectName("GateCopy")
            copy.setWordWrap(True)
            badge = QLabel(gate.state.value.upper())
            badge.setObjectName("GateBadge")
            layout.addWidget(icon)
            layout.addWidget(copy, 1)
            layout.addWidget(badge)
            card.setToolTip(gate.resolution or gate.detail)
            self.content.addWidget(card)
        if self.guardian_manifest is not None:
            manifest_card = QFrame()
            manifest_card.setObjectName("AscensionHandoff")
            manifest_layout = QHBoxLayout(manifest_card)
            manifest_layout.setContentsMargins(16, 13, 16, 13)
            manifest_copy = QLabel(
                "ASCENSION GUARDIAN MANIFEST\n"
                + (
                    "All manifest evidence is review-ready; separate final consent is still required."
                    if self.guardian_manifest.review_ready
                    else f"ROMVERSE compiled the exact intent and found {len(self.guardian_manifest.blockers)} unresolved safety gate(s)."
                )
                + "\nNo flash command exists. Bootloader relock is permanently prohibited."
            )
            manifest_copy.setObjectName("GateCopy")
            manifest_copy.setWordWrap(True)
            review = QPushButton("Review exact manifest")
            review.setObjectName("GateResolve")
            review.clicked.connect(self._review_guardian_manifest)
            manifest_layout.addWidget(manifest_copy, 1)
            manifest_layout.addWidget(review)
            self.content.addWidget(manifest_card)
        if self.final_handoff is not None:
            final_card = QFrame()
            final_card.setProperty("gateStatus", "pass")
            final_layout = QHBoxLayout(final_card)
            final_layout.setContentsMargins(16, 13, 16, 13)
            final_copy = QLabel(
                "FINAL GUARDIAN HANDOFF  •  EVIDENCE SEALED\n"
                f"Exact USB phone, slot {self.final_handoff.observed_slot}, "
                f"{self.final_handoff.battery_percent}% battery, backup, Device Pack, and both "
                "image hashes were revalidated. Commands: NONE. Root applied: NO."
            )
            final_copy.setObjectName("GateCopy")
            final_copy.setWordWrap(True)
            review_final = QPushButton("Review sealed handoff")
            review_final.setObjectName("GateResolve")
            review_final.clicked.connect(self._review_guardian_manifest)
            final_layout.addWidget(final_copy, 1)
            final_layout.addWidget(review_final)
            self.content.addWidget(final_card)
        if self.consent_review is not None:
            consent_card = QFrame()
            consent_card.setProperty("gateStatus", "attention")
            consent_layout = QVBoxLayout(consent_card)
            consent_layout.setContentsMargins(16, 13, 16, 13)
            consent_heading = QLabel("GUARDIAN CONSEQUENCE REVIEW  •  ACTIVE FOR TEN MINUTES")
            consent_heading.setObjectName("CardHeading")
            consent_copy = QLabel(
                f"Exact target  •  {self.consent_review.target_partition}  •  "
                f"slot {self.consent_review.target_slot}\n"
                "Keep data / no wipe  •  bootloader relock permanently prohibited\n"
                "Execution authority  •  NONE  •  commands  •  NONE  •  phone changed  •  NO"
            )
            consent_copy.setObjectName("GateCopy")
            consent_copy.setWordWrap(True)
            consent_layout.addWidget(consent_heading)
            consent_layout.addWidget(consent_copy)
            self.content.addWidget(consent_card)
        if self.integration_receipt is not None:
            integration_card = QFrame()
            integration_card.setProperty("gateStatus", "pass")
            integration_layout = QHBoxLayout(integration_card)
            integration_layout.setContentsMargins(16, 13, 16, 13)
            integration_copy = QLabel(
                "ROOTED ROM INPUT  •  INTEGRATED AND ROLLBACK-PROTECTED\n"
                f"{method.display_name} output replaced only the isolated "
                f"{self.integration_receipt.target_relative_path} build input. "
                "Protected source: unchanged. Phone changed: NO. "
                + (
                    "Content-addressed build seal: verified."
                    if self.build_seal_receipt is not None
                    else "Next: seal the content-addressed build handoff."
                )
            )
            integration_copy.setObjectName("GateCopy")
            integration_copy.setWordWrap(True)
            integration_layout.addWidget(integration_copy, 1)
            self.content.addWidget(integration_card)
        if self.build_seal_receipt is not None:
            seal_card = QFrame()
            seal_card.setProperty("gateStatus", "pass")
            seal_layout = QHBoxLayout(seal_card)
            seal_layout.setContentsMargins(16, 13, 16, 13)
            seal_copy = QLabel(
                "ASCENSION BUILD SEAL  •  CONTENT VERIFIED\n"
                f"{self.build_seal_receipt.target_partition} • "
                f"{self.build_seal_receipt.packaging_route} • "
                f"SHA-256 {self.build_seal_receipt.artifact_sha256[:20]}… • "
                "flash authority: NONE • phone changed: NO"
            )
            seal_copy.setObjectName("GateCopy")
            seal_copy.setWordWrap(True)
            seal_layout.addWidget(seal_copy, 1)
            self.content.addWidget(seal_card)
        if self.handoff_receipt is not None and self.patched_receipt is None:
            handoff_card = QFrame()
            handoff_card.setObjectName("AscensionHandoff")
            handoff_layout = QVBoxLayout(handoff_card)
            handoff_title = QLabel("PHONE PATCH HANDOFF  •  READY FOR YOUR ON-PHONE STEP")
            handoff_title.setObjectName("CardHeading")
            phone_steps = (
                "Open Magisk → Install → Select and Patch a File → choose the ROMVERSE image. Magisk creates a magisk_patched image in Downloads."
                if method is AscensionMethod.MAGISK
                else "Open KernelSU Manager → Install → Select a file → choose the ROMVERSE image. Continue only because the device support gate passed; KernelSU creates a patched or restore image in Downloads."
            )
            handoff_copy = QLabel(
                f"ROMVERSE installed the verified official manager and copied the pristine source-bound image to:\n{self.handoff_receipt.remote_input_path}\n\n"
                f"On the phone: {phone_steps}\n\nReturn here and choose Find patched image on phone. ROMVERSE will retrieve only the selected output, hash it, inspect it, and bind it to this exact source before Guardian review. Nothing has been rooted or flashed yet."
                + (
                    "\n\nLAST SAVED OUTPUT SCAN  •  "
                    + (
                        f"{self.output_discovery.candidate_count} matching filename(s) found"
                        if self.output_discovery.state == "found"
                        else "no matching filename found yet"
                    )
                    + "  •  raw filenames were not stored  •  diagnostic only; retrieval requires a fresh exact approval"
                    if self.output_discovery is not None
                    else ""
                )
            )
            handoff_copy.setObjectName("GateCopy")
            handoff_copy.setWordWrap(True)
            handoff_layout.addWidget(handoff_title)
            handoff_layout.addWidget(handoff_copy)
            open_manager = QPushButton(
                f"Open verified {method.display_name} again"
                if self.manager_launch_receipt is not None
                else f"Open verified {method.display_name} on phone"
            )
            open_manager.setObjectName("GateResolve")
            open_manager.setToolTip(
                "ROMVERSE first copies only the installed Manager APK into temporary verification storage, rechecks its complete hash and pinned signing certificate, deletes the temporary copy, and then opens that exact allowlisted package. It cannot patch or flash the phone."
            )
            open_manager.setEnabled(self._manager_launch_service() is not None)
            open_manager.clicked.connect(self._open_verified_manager)
            handoff_layout.addWidget(open_manager)
            if self.manager_launch_receipt is not None:
                opened_copy = QLabel(
                    "VERIFIED MANAGER OPENED  •  installed APK hash and signing certificate matched  •  temporary verification copy removed  •  root applied: NO  •  flashed: NO"
                )
                opened_copy.setObjectName("GateCopy")
                opened_copy.setWordWrap(True)
                handoff_layout.addWidget(opened_copy)
            self.content.addWidget(handoff_card)
        if self.patched_receipt is not None:
            lineage_card = QFrame()
            lineage_card.setProperty(
                "gateStatus",
                "pass" if self.patched_receipt.lineage_confidence == "high" else "attention",
            )
            lineage_layout = QVBoxLayout(lineage_card)
            lineage_layout.setContentsMargins(16, 13, 16, 13)
            lineage_title = QLabel(
                "PATCHED-IMAGE LINEAGE  •  "
                + (
                    "HIGH CONFIDENCE"
                    if self.patched_receipt.lineage_confidence == "high"
                    else "CAUTION"
                    if self.patched_receipt.lineage_confidence == "caution"
                    else "LIMITED BY KERNEL-LESS IMAGE"
                )
            )
            lineage_title.setObjectName("CardHeading")
            lineage_copy = QLabel(
                (
                    "ROMVERSE proved the normalized Android header and unchanged kernel against the pristine capsule input."
                    if self.patched_receipt.lineage_confidence == "high"
                    else "The normalized header matches, but Magisk changed kernel bytes. This can be legitimate on specific legacy or Samsung routes and remains visible for Guardian review."
                    if self.patched_receipt.lineage_confidence == "caution"
                    else "The normalized header matches. This init_boot-style image has no kernel section to compare, so ROMVERSE keeps exact-source certainty limited and relies on the protected same-phone handoff plus rollback evidence."
                )
                + "\nNo flash authority was granted. Bootloader relock remains prohibited."
            )
            lineage_copy.setObjectName("GateCopy")
            lineage_copy.setWordWrap(True)
            lineage_layout.addWidget(lineage_title)
            lineage_layout.addWidget(lineage_copy)
            self.content.addWidget(lineage_card)
        self.content.addStretch()
        self._update_primary_action(report)
        self.status.setText(
            f"{method.display_name} final handoff evidence sealed  •  commands: NONE  •  phone changed: NO"
            if self.final_handoff is not None
            else f"{method.display_name} assessment complete  •  {blocked} blocking gate(s)  •  phone changed: NO"
        )
        self.studio.ascension_status_changed.emit()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt virtual method name
        super().showEvent(event)
        if not self._automatic_start_pending and self.worker is None:
            self._automatic_start_pending = True
            QTimer.singleShot(0, self._start_automatic_when_visible)

    def _start_automatic_when_visible(self) -> None:
        self._automatic_start_pending = False
        if self.isVisible() and self.worker is None:
            self._ensure_official_manager()

    def _update_primary_action(self, report) -> None:
        """Expose one plain-language action instead of an internal workflow command."""

        action = self._primary_action_key(report)
        if action == "busy":
            return
        labels = {
            "integrate": "Integrate verified root image into ROM",
            "seal": "Seal rooted ROM build input",
            "review": (
                "Review sealed Guardian handoff"
                if self.final_handoff is not None
                else "Review final Guardian safety gates"
            ),
            "open-manager": (
                f"Open verified {AscensionMethod(self.method.currentData()).display_name} on phone"
            ),
            "find-phone": "Find and verify patched image",
            "import": "Choose patched image from this PC…",
            "review-handoff": "Review guided phone preparation",
            "resolve": self._blocked_action_label(report),
            "prepare": "Continue automatic preparation",
            "acquire": "Start automatic Ascension setup",
        }
        self.acquire_button.setText(labels[action])

    def _primary_action_key(self, report) -> str:
        """Return the single action used by both button copy and click dispatch."""

        if self.worker is not None:
            return "busy"
        if report is not None and any(
            gate.gate_id == "root-state" and gate.state is GateState.BLOCKED
            for gate in report.gates
        ):
            # An observed existing root is a route-level safety stop. It must outrank
            # every saved preparation receipt so ROMVERSE never layers another method.
            return "resolve"
        if self.patched_receipt is not None and self.integration_receipt is None:
            return "integrate"
        if self.integration_receipt is not None and self.build_seal_receipt is None:
            return "seal"
        if self.patched_receipt is not None:
            return "review"
        if report is not None and report.blocked:
            # Before a patched output exists, every remaining action depends on the
            # current source/device route. Newly blocking live evidence must outrank a
            # historical handoff receipt; the execution service also revalidates it.
            return "resolve"
        if (
            self.patch_capsule is not None
            and self.handoff_receipt is not None
            and self.manager_launch_receipt is None
        ):
            return "open-manager"
        if self.patch_capsule is not None and self.handoff_receipt is not None:
            return "find-phone" if self._patched_output_service() is not None else "import"
        if self.patch_capsule is not None:
            return "review-handoff" if self._handoff_service() is not None else "import"
        if self.verified_release is not None:
            return "prepare"
        return "acquire"

    def _ensure_official_manager(self) -> None:
        if self.worker is not None:
            return
        if self.current_report is not None and any(
            gate.gate_id == "root-state" and gate.state is GateState.BLOCKED
            for gate in self.current_report.gates
        ):
            self._update_primary_action(self.current_report)
            return
        if self.verified_release is not None and self.manager_path is not None:
            QTimer.singleShot(0, self._ensure_patch_capsule)
            return
        method = AscensionMethod(self.method.currentData())
        settings = getattr(self.studio, "app_settings", None)
        if settings is not None and not settings.auto_download_verified_tools:
            self.status.setText(
                "Automatic verified-tool acquisition is disabled in ROMVERSE Settings. "
                f"Choose Acquire official {method.display_name} when you are ready."
            )
            self._update_primary_action(self.current_report)
            return
        if method in self.automatic_attempted:
            return
        self.automatic_attempted.add(method)
        self.status.setText(
            f"Automatic resolver  •  locating and verifying the latest official {method.display_name} manager …"
        )
        self._acquire(automatic=True)

    def _revalidate_official_manager(self, method: AscensionMethod) -> bool:
        """Rebind the UI only to the currently rehashed official vault artifact."""

        if self.verified_release is None or self.manager_path is None:
            return False
        loaded = self._release_service().load_verified(method)
        if loaded is None:
            return False
        release, path = loaded
        try:
            same_path = path.resolve(strict=True) == self.manager_path.resolve(strict=True)
        except OSError:
            return False
        if (
            not same_path
            or release.tag != self.verified_release.tag
            or release.asset.sha256 != self.verified_release.asset.sha256
            or release.asset.size_bytes != self.verified_release.asset.size_bytes
        ):
            return False
        self.verified_release = release
        self.manager_path = path
        return True

    def _reacquire_changed_manager(
        self,
        method: AscensionMethod,
        *,
        reason: str = "",
    ) -> None:
        self.verified_release = None
        self.manager_path = None
        self.manager_verification_note = ""
        self.manager_acquisition_mode = ""
        self.automatic_attempted.discard(method)
        self.manager_retry_attempts.pop(method, None)
        self._cancel_manager_retry(clear_budget=False)
        detail = " ".join(reason.split())[:300]
        self.status.setText(
            "The vaulted official Manager changed or failed revalidation. ROMVERSE discarded "
            "the stale trust state and is retrieving a fresh official copy; nothing was installed."
            + (f" Why: {detail}" if detail else "")
        )
        QTimer.singleShot(0, self._ensure_official_manager)

    def _manager_verified(
        self,
        release: OfficialRootRelease,
        path: Path,
        explanation: str,
        mode: str = "official-latest",
    ) -> None:
        self.manager_retry_attempts.pop(release.provider, None)
        self._cancel_manager_retry(clear_budget=False)
        self.verified_release = release
        self.manager_path = path
        self.manager_verification_note = explanation
        self.manager_acquisition_mode = mode
        self.acquire_button.setToolTip(
            f"ROMVERSE verified {release.tag}, its published SHA-256, and the vaulted copy at {path}. {explanation} It has not been installed on the phone."
        )
        if self.context_refresh_pending:
            self.context_refresh_pending = False
            self.refresh()
            return
        self._ensure_patch_capsule()

    def _ensure_patch_capsule(self) -> None:
        if self.worker is not None or self.verified_release is None or self.manager_path is None:
            return
        method = AscensionMethod(self.method.currentData())
        if not self._revalidate_official_manager(method):
            self._reacquire_changed_manager(method)
            return
        service = RootPatchPreparationService(self.studio.store)
        loaded = service.load(self.project.project_id, method)
        if loaded is not None and not service.matches_release(
            loaded,
            self.verified_release,
        ):
            loaded = None
            self.status.setText(
                "A newer official root Manager is verified. ROMVERSE is rebuilding the "
                "source-bound patch capsule; older dependent receipts will be revalidated."
            )
        if loaded is not None:
            self.patch_capsule = loaded
            self.patched_receipt = service.load_patched(self.project.project_id, method)
            self.integration_receipt = RootRomIntegrationService(self.studio.store).load(
                self.project.project_id, method
            )
            self.build_seal_receipt = RootRomBuildHandoffService(self.studio.store).load(
                self.project.project_id, method
            )
            handoff = self._handoff_service()
            self.handoff_receipt = (
                handoff.load(self.project.project_id, method) if handoff is not None else None
            )
            if self.patched_receipt is not None:
                if self.integration_receipt is None:
                    self.acquire_button.setText("Integrate verified root image into ROM")
                    self.status.setText(
                        "Patched output verified • next ROMVERSE will integrate it into the isolated ROM • phone changed: NO"
                    )
                elif self.build_seal_receipt is None:
                    self.acquire_button.setText("Seal rooted ROM build input")
                    self.status.setText(
                        "Root image integrated • next ROMVERSE will create and verify the content-addressed build seal • phone changed: NO"
                    )
                else:
                    self.root_plan = self._ensure_root_plan(method)
                    self.guardian_manifest = self._ensure_guardian_manifest(method)
                    self.acquire_button.setText(
                        "Review Guardian root manifest"
                        if self.guardian_manifest is not None
                        else "Connect exact phone to finish root plan"
                    )
                    if self.guardian_manifest is not None:
                        self.status.setText(
                            f"Guardian manifest compiled  •  {len(self.guardian_manifest.blockers)} unresolved safety gate(s)  •  commands: NONE  •  phone changed: NO"
                        )
            elif self.handoff_receipt is not None:
                self.acquire_button.setText(
                    "Find patched image on phone"
                    if self._patched_output_service() is not None
                    else "Import patched image…"
                )
                self.status.setText(
                    "Stage 4 of 9 complete  •  finish stage 5 in the official manager, then ROMVERSE can find, retrieve, verify, and integrate the output  •  root applied: NO  •  flashed: NO"
                )
            elif handoff is not None:
                self.acquire_button.setText("Continue to guided phone patch")
                self.status.setText(
                    "Stage 3 of 9 complete  •  patch capsule verified  •  stage 4 requires explicit approval for manager installation and file transfer"
                )
            else:
                self.acquire_button.setText("Import patched image…")
                self.status.setText(
                    "Stage 3 of 9 complete  •  patch capsule verified; automatic stage 4 phone handoff is unavailable on this launch"
                )
            self.acquire_button.setEnabled(True)
            return
        report = self.current_report
        if report is None or report.blocked:
            blocked_ids = (
                {gate.gate_id for gate in report.gates if gate.state is GateState.BLOCKED}
                if report is not None
                else set()
            )
            if "patch-target" in blocked_ids and self._try_automatic_patch_target():
                self.status.setText(
                    "Automatic resolver  •  one contained payload identified  •  "
                    "ROMVERSE is resolving the required boot images without a technical prompt."
                )
                return
            blocked = sum(g.state is GateState.BLOCKED for g in report.gates) if report else 1
            self.acquire_button.setText(self._blocked_action_label(report))
            self.status.setText(
                f"Automatic preparation paused at {blocked} safety gate(s). Select the highlighted action and ROMVERSE will resolve every safe prerequisite it can, then explain any required phone or user step."
            )
            self.acquire_button.setEnabled(True)
            return
        worker = AscensionPreparationWorker(
            self.studio.store,
            self.project.project_id,
            method,
            release=self.verified_release,
            manager_path=self.manager_path,
            release_service=self._release_service(),
        )
        worker.signals.progress.connect(self.progress.report)
        worker.signals.complete.connect(self._capsule_ready)
        worker.signals.failed.connect(self._failed)
        self.worker = worker
        self.method.setEnabled(False)
        self.acquire_button.setEnabled(False)
        self.acquire_button.setText("Preparing verified patch capsule …")
        self.progress.begin(determinate=False)
        self.status.setText(
            "Automatic resolver  •  revalidating trust evidence, then copying and independently hashing the pristine patch target and official Manager with measured byte progress …"
        )
        start_background(worker)

    def _ensure_root_plan(self, method: AscensionMethod):
        service = AscensionRootPlanService(self.studio.store)
        device = next(
            (item for item in self.studio.devices if getattr(item.state, "value", "") == "device"),
            None,
        )
        loaded = service.load(self.project.project_id, method)
        if loaded is not None and device is not None and service.matches_device(loaded, device):
            return loaded
        if device is None:
            self.status.setText(
                "Patched image verified. Reconnect the exact authorized phone so ROMVERSE can bind the final Ascension root plan."
            )
            return None
        try:
            return service.create(self.project.project_id, method, device)
        except ProjectError as exc:
            self.status.setText(f"Ascension root plan stopped safely. Why: {exc}")
            return None

    def _ensure_guardian_manifest(self, method: AscensionMethod):
        if self.root_plan is None:
            return None
        service = AscensionGuardianManifestService(
            self.studio.store,
            self.studio.pack_registry,
            getattr(self.studio, "attestation_store", None),
        )
        device = next(
            (
                item
                for item in self.studio.devices
                if AscensionRootPlanService(self.studio.store).matches_device(self.root_plan, item)
            ),
            None,
        )
        loaded = service.load(self.project.project_id, method)
        if loaded is not None and device is not None and service.matches_device(loaded, device):
            return loaded
        if device is None:
            return None
        try:
            return service.prepare(self.project.project_id, method, device)
        except ProjectError as exc:
            self.status.setText(f"Guardian manifest stopped safely. Why: {exc}")
            return None

    def _review_guardian_manifest(self) -> None:
        if self.guardian_manifest is None:
            method = AscensionMethod(self.method.currentData())
            self.root_plan = self._ensure_root_plan(method)
            self.guardian_manifest = self._ensure_guardian_manifest(method)
        if self.guardian_manifest is None:
            self.status.setText(
                "Reconnect the exact authorized phone so ROMVERSE can compile the Guardian manifest."
            )
            return
        AscensionManifestDialog(
            self.guardian_manifest,
            self,
            self._resolve_manifest_action,
            self.final_handoff,
        ).exec()

    def _resolve_manifest_action(self, action_id: str) -> None:
        if action_id == "record-final-consent":
            self._record_final_consent_review()
            return
        if action_id == "refresh-ascension":
            self.root_plan = None
            self.guardian_manifest = None
            self.refresh()
            self.status.setText(
                "Ascension evidence refreshed. ROMVERSE rechecked every safe local prerequisite."
            )
            return
        if action_id == "open-backup-guide":
            from romverse.ui.build_control import BuildControlCenter

            control = BuildControlCenter(self.studio, self, auto_start=False)
            QTimer.singleShot(0, control.start_guided_backup)
            control.exec()
            self.root_plan = None
            self.guardian_manifest = None
            self.refresh()
            return
        if action_id == "open-device-atlas":
            self._leave_for_navigation()
            self.studio.device_packs_requested.emit()
            return
        if action_id == "refresh-device":
            QMessageBox.information(
                self,
                "Safe phone re-scan",
                "Keep the phone connected by USB with Android debugging authorized. "
                "ROMVERSE will return to Command Deck, refresh the read-only device evidence, "
                "and never unlock, relock, reboot, wipe, root, or flash during this scan.",
            )
            self._leave_for_navigation()
            self.studio.device_center_requested.emit()
            return
        self.status.setText("That Guardian resolution is not available on this launch.")

    def _record_final_consent_review(self) -> None:
        method = AscensionMethod(self.method.currentData())
        manifest_service = AscensionGuardianManifestService(
            self.studio.store,
            self.studio.pack_registry,
            getattr(self.studio, "attestation_store", None),
        )
        handoff_service = AscensionFinalHandoffService(self.studio.store, manifest_service)
        device = next(
            (
                item
                for item in self.studio.devices
                if self.root_plan is not None
                and AscensionRootPlanService(self.studio.store).matches_device(self.root_plan, item)
            ),
            None,
        )
        current = (
            handoff_service.load(self.project.project_id, method, device)
            if device is not None
            else None
        )
        if current is None:
            self.consent_review = None
            self.status.setText(
                "Final consent review paused. Reconnect the exact USB phone and refresh Guardian evidence; no device action was run."
            )
            return
        dialog = AscensionConsentReviewDialog(current, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.status.setText(
                "Final consequence review cancelled. No approval, command, or phone change was created."
            )
            return
        try:
            self.consent_review = AscensionConsentReviewService(
                self.studio.store,
                handoff_service,
            ).record(current, device, dialog.accepted_acknowledgements)
        except ProjectError as exc:
            self.consent_review = None
            self.status.setText(f"Consent review stopped safely. Why: {exc}")
            return
        console = self._live_console_store()
        if console is not None:
            with suppress(LiveConsoleStoreError):
                console.note(
                    source="Ascension Protocol",
                    stage="final-consent-review",
                    title="Guardian consequence review recorded",
                    summary="The exact-device review is preserved for ten minutes; execution authority remains NONE.",
                    explanation="The user reviewed the target, patched digest, rollback, keep-data route, boot risk, and permanent bootloader-relock prohibition. No command was created.",
                    next_action="A later device-write workflow must revalidate every live signal and request separate Guardian approval.",
                    state=MissionState.INFORMATION,
                    progress_percent=100,
                    confidence=MissionConfidence.VERIFIED,
                    guardian_protected=True,
                    project_id=self.project.project_id,
                    evidence_refs=(
                        f"projects/{self.project.project_id}/ascension/guardian/final-consent-review.romverse",
                    ),
                    dedupe_key=f"ascension-consent-{self.consent_review.review_digest}",
                )
        self.refresh()
        self.status.setText(
            "Guardian consequence review saved for ten minutes  •  execution authority: NONE  •  commands: NONE  •  bootloader relock: PROHIBITED"
        )

    def _leave_for_navigation(self) -> None:
        parent = self.parentWidget()
        self.accept()
        if isinstance(parent, QDialog) and parent is not self.studio:
            parent.accept()

    def _primary_action(self) -> None:
        action = self._primary_action_key(self.current_report)
        if action == "busy":
            self.status.setText("The current verified Ascension step is still running.")
            return
        if action == "integrate":
            self._integrate_root_rom()
            return
        if action == "seal":
            self._seal_root_build()
            return
        if action == "review":
            self._review_guardian_manifest()
            return
        if action == "open-manager":
            self._open_verified_manager()
            return
        if action == "find-phone":
            self._find_patched_on_phone()
            return
        if action == "import":
            self._import_patched()
            return
        if action == "review-handoff":
            self._review_handoff()
            return
        if action == "resolve":
            self._resolve_blocked_preparation()
            return
        if action == "prepare":
            self._ensure_patch_capsule()
            return
        method = AscensionMethod(self.method.currentData())
        self.manager_retry_attempts.pop(method, None)
        self._acquire()

    def _integrate_root_rom(self) -> None:
        if self.worker is not None or self.patched_receipt is None:
            return
        method = AscensionMethod(self.method.currentData())
        worker = AscensionIntegrationWorker(
            self.studio.store,
            self.project.project_id,
            method,
        )
        worker.signals.progress.connect(self.progress.report)
        worker.signals.complete.connect(self._root_rom_integrated)
        worker.signals.failed.connect(self._failed)
        self.worker = worker
        self.method.setEnabled(False)
        self.acquire_button.setEnabled(False)
        self.acquire_button.setText("Integrating verified root image …")
        self.progress.begin(determinate=False)
        self.status.setText(
            "Ascension is revalidating the integration evidence, then measured byte progress will cover the rollback snapshot, rooted-image replacement, and every independent hash • phone changed: NO"
        )
        start_background(worker)

    @Slot(object)
    def _root_rom_integrated(self, value: object) -> None:
        self.worker = None
        self.progress.finish()
        self.method.setEnabled(True)
        self.acquire_button.setEnabled(True)
        if not isinstance(value, RootRomIntegrationReceipt):
            self._failed("Root integration returned an unexpected result")
            return
        self.integration_receipt = value
        self.refresh()
        self.status.setText(
            "Rooted ROM input verified • automatic rollback available • Ascension is sealing the build handoff next • protected source unchanged • phone changed: NO"
        )
        QTimer.singleShot(0, self._seal_root_build)

    def _seal_root_build(self) -> None:
        if self.worker is not None or self.integration_receipt is None:
            return
        method = AscensionMethod(self.method.currentData())
        worker = AscensionBuildSealWorker(
            self.studio.store,
            self.project.project_id,
            method,
        )
        worker.signals.progress.connect(self.progress.report)
        worker.signals.complete.connect(self._root_build_sealed)
        worker.signals.failed.connect(self._failed)
        self.worker = worker
        self.method.setEnabled(False)
        self.acquire_button.setEnabled(False)
        self.acquire_button.setText("Sealing rooted ROM build input …")
        self.progress.begin(determinate=False)
        self.status.setText(
            "Ascension is creating the content-addressed rooted artifact and freezing the complete build tree. The combined tree verification has no trustworthy total, so this remains animated • phone changed: NO"
        )
        start_background(worker)

    @Slot(object)
    def _root_build_sealed(self, value: object) -> None:
        self.worker = None
        self.progress.finish()
        self.method.setEnabled(True)
        self.acquire_button.setEnabled(True)
        if not isinstance(value, RootRomBuildHandoffReceipt):
            self._failed("Ascension Build Seal returned an unexpected result")
            return
        self.build_seal_receipt = value
        method = AscensionMethod(self.method.currentData())
        self.root_plan = self._ensure_root_plan(method)
        self.guardian_manifest = self._ensure_guardian_manifest(method)
        self.final_handoff = None
        self.refresh()
        self.status.setText(
            (
                "Ascension Build Seal and exact-device Guardian review compiled automatically"
                if self.guardian_manifest is not None
                else "Ascension Build Seal verified • reconnect the exact authorized phone to compile Guardian review"
            )
            + " • flash authority: NONE • phone changed: NO"
        )

    @staticmethod
    def _blocked_action_label(report) -> str:
        primary = build_resolution_plan(report).primary
        return primary.button_label if primary is not None else "Auto-resolve project prerequisites"

    def _resolve_blocked_preparation(self) -> None:
        report = self.current_report
        if report is None:
            self.refresh()
            return
        blocked = {gate.gate_id: gate for gate in report.gates if gate.state is GateState.BLOCKED}
        if "root-state" in blocked:
            gate = blocked["root-state"]
            QMessageBox.information(
                self,
                "Existing root needs review",
                "ROMVERSE stopped automatic root preparation because it detected an existing root identity.\n\n"
                f"What was found:\n{gate.detail}\n\n"
                f"Safe next step:\n{gate.resolution}\n\n"
                "No manager was installed, no image was patched, and no phone partition was changed.",
            )
            self.status.setText(
                "Ascension paused safely  •  existing root must be reviewed before a new root route can be prepared"
            )
            return
        if "patch-target" in blocked and self._resolve_patch_target():
            return
        if "kernel" in blocked:
            self._review_kernelsu_support()
            return
        human_gate = next(
            (
                blocked[gate_id]
                for gate_id in ("live-device", "device-match", "bootloader")
                if gate_id in blocked
            ),
            None,
        )
        if human_gate is not None:
            QMessageBox.information(
                self,
                f"Ascension needs: {human_gate.title}",
                f"ROMVERSE completed every safe local step it can.\n\n"
                f"What was found:\n{human_gate.detail}\n\n"
                f"What to do:\n{human_gate.resolution}\n\n"
                "After that, return here and ROMVERSE will scan again automatically. "
                "It will never unlock the bootloader, wipe data, or guess across device models.",
            )
            self.refresh()
            return

        details = "\n".join(
            f"• {gate.title}: {gate.resolution or gate.detail}" for gate in blocked.values()
        )
        answer = QMessageBox.question(
            self,
            "Prepare Ascension prerequisites",
            "Ascension needs earlier project evidence before it can prepare a root patch. "
            "ROMVERSE can open Genesis Sequence and automatically complete all safe local stages.\n\n"
            f"{details}\n\nContinue with automatic project preparation?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            self.status.setText(
                "Automatic prerequisite preparation cancelled. No files or phone state changed."
            )
            return
        mission = GuidedBuildMission(self.studio)
        QTimer.singleShot(0, mission._start_autopilot)
        mission.exec()
        self.refresh()

    def _resolve_patch_target(self) -> bool:
        if self._try_automatic_patch_target():
            return True

        answer = QMessageBox.question(
            self,
            "Prepare the firmware workspace",
            "The protected firmware has not yet produced a verified init_boot.img, boot.img, or recovery.img. "
            "ROMVERSE can run Genesis Sequence to verify and safely extract the source now.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer is QMessageBox.StandardButton.Yes:
            mission = GuidedBuildMission(self.studio)
            QTimer.singleShot(0, mission._start_autopilot)
            mission.exec()
            self.refresh()
        else:
            self.status.setText(
                "Firmware preparation cancelled. The protected source was not changed."
            )
        return True

    def _try_automatic_patch_target(self) -> bool:
        """Prepare a safe source tree and resolve one unambiguous payload automatically."""

        service = getattr(self.studio, "payload_service", None)
        project_id = self.project.project_id
        tree = self.studio.store.working_root / project_id / "tree"
        if not tree.exists() and not tree.is_symlink():
            report = self.studio.inspection.load_report(project_id)
            signals = set(report.partition_signals) if report is not None else set()
            target_signals = {"init_boot", "boot", "recovery"}
            supported_source = bool(
                report is not None
                and report.complete
                and not any(
                    finding.severity is FindingSeverity.CRITICAL for finding in report.findings
                )
                and (
                    (
                        report.container in {ContainerKind.ZIP, ContainerKind.TAR}
                        and bool(signals & (target_signals | {"ota_payload"}))
                    )
                    or (
                        report.container is ContainerKind.ANDROID_BOOT
                        and len(signals & target_signals) == 1
                    )
                    or report.container is ContainerKind.ANDROID_PAYLOAD
                )
            )
            if supported_source:
                try:
                    budget = self.studio.inspection.extraction_budget(project_id, report)
                except ProjectError as exc:
                    self.status.setText(
                        f"Ascension could not verify a safe extraction budget: {exc}. No source file was changed."
                    )
                    return False
                if not budget.safe:
                    self.status.setText(
                        f"Ascension paused before source extraction: {budget.reason}. No source file was changed."
                    )
                    return False
                return self._start_prerequisite_operation(
                    "extract",
                    "Preparing the verified firmware package in an isolated tree so Ascension can identify the exact boot image …",
                )
        payloads = (
            tuple(
                path
                for path in tree.rglob("*")
                if path.name.casefold() == "payload.bin"
                and path.is_file()
                and not path.is_symlink()
                and path.resolve().is_relative_to(tree.resolve())
            )
            if tree.is_dir() and not tree.is_symlink()
            else ()
        )
        if len(payloads) == 1 and service is None:
            settings = getattr(self.studio, "app_settings", None)
            automatic = settings is None or settings.auto_download_verified_tools
            if not automatic or not self._resolve_required_tools(
                self.PAYLOAD_EXTRACTION_TOOLS,
                purpose=(
                    "Ascension found one contained payload.bin and needs only Payload "
                    "Dumper to identify and extract its boot images."
                ),
                automatic=True,
            ):
                return False
            service = getattr(self.studio, "payload_service", None)
        if len(payloads) == 1 and service is not None:
            manifest = service.load(project_id)
            if manifest is None:
                return self._start_prerequisite_operation(
                    "scan-payload",
                    "Scanning payload.bin and identifying the exact boot partitions …",
                )
            selected = tuple(
                name
                for name in ("init_boot", "boot", "recovery")
                if any(
                    item.name == name and not item.extracted_path for item in manifest.partitions
                )
            )
            if selected:
                return self._start_prerequisite_operation(
                    "extract-payload",
                    "Extracting and hashing only the boot and recovery images Ascension needs …",
                    selected,
                )
            self.refresh()
            patch_still_blocked = bool(
                self.current_report
                and any(
                    gate.gate_id == "patch-target" and gate.state is GateState.BLOCKED
                    for gate in self.current_report.gates
                )
            )
            if not patch_still_blocked and self.current_report and not self.current_report.blocked:
                QTimer.singleShot(0, self._ensure_patch_capsule)
            return not patch_still_blocked
        return False

    def _resolve_required_tools(
        self,
        required: tuple[str, ...],
        *,
        purpose: str,
        automatic: bool,
    ) -> bool:
        """Resolve and reverify only the local tools needed by this Ascension step."""

        required = tuple(dict.fromkeys(required))
        status_by_name = {item.name: item for item in self.studio.tool_statuses}
        missing = tuple(
            name
            for name in required
            if name not in status_by_name or not status_by_name[name].available
        )
        if not missing:
            return True

        from romverse.ui.toolchain_center import (
            ToolchainSetupDialog,
            activate_verified_managed_tools,
        )

        host = current_host()
        dialog = ToolchainSetupDialog(
            host,
            self.studio.tool_statuses,
            self.studio.store.workspace,
            self,
            required_names=required,
            auto_start=automatic,
            auto_close=automatic,
        )
        dialog.setWindowTitle("ROMVERSE • Ascension tool resolver")
        dialog.status.setText(purpose)
        dialog.exec()
        activate_verified_managed_tools(self.studio.store.workspace)
        self.studio.set_tool_statuses(ToolVerifier(host, SubprocessRunner()).verify_extended())
        refreshed = {item.name: item for item in self.studio.tool_statuses}
        remaining = tuple(
            name for name in required if name not in refreshed or not refreshed[name].available
        )
        if remaining:
            detail = dialog.last_message.strip()
            self.status.setText(
                "Ascension paused safely because its exact verification tools are not ready. "
                + (f"Why: {detail}. " if detail else "")
                + f"Still required: {', '.join(remaining)}. No manager was trusted, no image was patched, and no phone state changed."
            )
            return False
        self.status.setText(
            f"Forge Arsenal verified {', '.join(required)}. Ascension is resuming the same safe step automatically …"
        )
        return True

    def _review_kernelsu_support(self) -> None:
        method = AscensionMethod(self.method.currentData())
        if method is not AscensionMethod.KERNELSU_LKM:
            self.status.setText("KernelSU support checking is available only on its route.")
            return
        device = next(
            (item for item in self.studio.devices if getattr(item.state, "value", "") == "device"),
            None,
        )
        existing = KernelSuSupportEvidenceService(
            self.studio.store,
            self._release_service(),
        ).load(self.project.project_id, device)
        if existing is not None:
            if existing.status == "supported":
                self.status.setText(
                    "Existing exact-device KernelSU support evidence revalidated. ROMVERSE is continuing without reinstalling the Manager."
                )
                self.refresh()
                QTimer.singleShot(0, self._ensure_patch_capsule)
            else:
                magisk_index = self.method.findData(AscensionMethod.MAGISK)
                self.method.setCurrentIndex(magisk_index)
                self.status.setText(
                    "The exact observed kernel was already recorded as KernelSU Unsupported. ROMVERSE switched to the Magisk fallback without reinstalling anything."
                )
            return
        if self.verified_release is None or self.manager_path is None:
            self.status.setText(
                "ROMVERSE is still acquiring and verifying the official KernelSU Manager."
            )
            self._ensure_official_manager()
            return
        gateway = getattr(self.studio, "gateway", None)
        adb = getattr(self.studio, "adb_executable", None)
        if device is None or gateway is None or adb is None:
            self.status.setText(
                "Connect and authorize the exact phone and verify ADB in Forge Arsenal, then retry the KernelSU support check."
            )
            return
        device_key = WorkspacePrivacy(self.studio.store.workspace).pseudonym(device.serial)
        worker = AscensionManagerPlanWorker(
            ApkInstallRequest(
                str(self.manager_path),
                device.serial,
                battery_percent=device.battery_percent,
                device_free_bytes=device.storage.available_bytes,
            ),
            device_key,
            method=method,
            expected_release=self.verified_release,
            expected_manager_path=self.manager_path,
            release_service=self._release_service(),
            aapt_executable=self._verified_tool("AAPT2"),
            apksigner_executable=self._verified_tool("APK Signer"),
            runner=self.tool_runner,
        )
        worker.signals.progress.connect(self.progress.report)
        worker.signals.complete.connect(self._kernelsu_manager_plan_ready)
        worker.signals.failed.connect(self._kernelsu_manager_plan_failed)
        self.worker = worker
        self.method.setEnabled(False)
        self.acquire_button.setEnabled(False)
        self.acquire_button.setText("Verifying Manager install plan …")
        self.progress.begin(determinate=False)
        self.status.setText(
            "Revalidating the private official-Manager vault, then hashing and inspecting the KernelSU APK with measured progress before binding its app-only plan to the exact authorized phone …"
        )
        start_background(worker)

    @Slot(object)
    def _kernelsu_manager_plan_ready(self, value: object) -> None:
        self.worker = None
        self.progress.finish()
        self.method.setEnabled(True)
        self.acquire_button.setEnabled(True)
        if not isinstance(value, AscensionManagerInstallPreparation):
            self._failed("KernelSU Manager planning returned an unexpected result")
            return
        plan = value.plan
        method = AscensionMethod(self.method.currentData())
        if method is not AscensionMethod.KERNELSU_LKM:
            self.status.setText(
                "KernelSU Manager planning finished after the root route changed. ROMVERSE discarded the stale app-only plan; nothing was installed."
            )
            return
        device = next(
            (
                item
                for item in self.studio.devices
                if getattr(item.state, "value", "") == "device"
                and item.serial == plan.request.device_serial
            ),
            None,
        )
        gateway = getattr(self.studio, "gateway", None)
        adb = getattr(self.studio, "adb_executable", None)
        if device is None or gateway is None or adb is None:
            self.status.setText(
                "The exact phone disconnected while ROMVERSE verified the KernelSU Manager plan. Reconnect it and retry; nothing was installed."
            )
            return
        try:
            planned_path = Path(plan.request.apk_path).expanduser().resolve(strict=True)
            current_path = self.manager_path.resolve(strict=True) if self.manager_path else None
        except OSError:
            planned_path = None
            current_path = None
        if (
            planned_path is None
            or current_path is None
            or planned_path != current_path
            or planned_path != value.manager_path
            or self.verified_release is None
            or self.verified_release.tag != value.release.tag
            or self.verified_release.asset.sha256 != value.release.asset.sha256
            or self.verified_release.asset.size_bytes != value.release.asset.size_bytes
            or plan.inspection.sha256 != value.release.asset.sha256
            or plan.inspection.file_size != value.release.asset.size_bytes
            or plan.target_key
            != WorkspacePrivacy(self.studio.store.workspace).pseudonym(device.serial)
        ):
            self._reacquire_changed_manager(method)
            return
        self.verified_release = value.release
        self.manager_path = value.manager_path
        if not plan.safety_ready:
            reasons = "; ".join(plan.assessment.reasons)
            self.status.setText(f"KernelSU Manager installation needs more evidence: {reasons}")
            return
        answer = QMessageBox.question(
            self,
            "Install verified KernelSU Manager",
            f"ROMVERSE verified the official {self.verified_release.tag} Manager APK.\n"
            f"SHA-256: {plan.inspection.sha256[:24]}…\n"
            f"Phone: {device.display_name} ({device.codename})\n\n"
            "Installing the Manager changes only application state. It does not root, patch, reboot, unlock, wipe, or flash the phone. After installation, open it and report the compatibility result. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            self.status.setText(
                "KernelSU Manager installation cancelled. Root state was not changed."
            )
            return
        approvals = ApprovalStore(self.studio.store.workspace)
        approvals.issue(plan.digest, plan.target_key)
        self.manager_install_plan = plan
        worker = AscensionManagerInstallWorker(
            ApkInstallService(Path(adb), gateway, approvals), plan
        )
        worker.signals.complete.connect(self._kernelsu_manager_installed)
        worker.signals.failed.connect(self._failed)
        self.worker = worker
        self.method.setEnabled(False)
        self.acquire_button.setEnabled(False)
        self.acquire_button.setText("Installing verified Manager …")
        self.progress.begin(determinate=False)
        self.status.setText(
            "Installing only the verified official KernelSU Manager so the phone can report real kernel support … Android does not expose a trustworthy install percentage, so this phase remains indeterminate."
        )
        start_background(worker)

    @Slot(str)
    def _kernelsu_manager_plan_failed(self, message: str) -> None:
        self.worker = None
        self.manager_install_plan = None
        self.progress.stop()
        self.method.setEnabled(True)
        self.acquire_button.setEnabled(True)
        self._reacquire_changed_manager(
            AscensionMethod.KERNELSU_LKM,
            reason=f"KernelSU Manager preflight could not be trusted: {message}",
        )

    @Slot(object)
    def _kernelsu_manager_installed(self, value: object) -> None:
        self.worker = None
        self.progress.finish()
        self.method.setEnabled(True)
        self.acquire_button.setEnabled(True)
        plan = self.manager_install_plan
        self.manager_install_plan = None
        if (
            not isinstance(value, AscensionManagerInstallCompletion)
            or plan is None
            or not install_succeeded(value.result)
            or value.plan_digest != plan.digest
            or value.target_key != plan.target_key
            or value.apk_sha256 != plan.inspection.sha256
            or value.package_name != plan.inspection.package_name
        ):
            self._failed("KernelSU Manager install returned unexpected terminal evidence")
            return
        device = next(
            (
                item
                for item in self.studio.devices
                if getattr(item.state, "value", "") == "device"
                and item.serial == plan.request.device_serial
                and WorkspacePrivacy(self.studio.store.workspace).pseudonym(item.serial)
                == value.target_key
            ),
            None,
        )
        verified = self._release_service().load_verified(AscensionMethod.KERNELSU_LKM)
        if (
            device is None
            or self.verified_release is None
            or verified is None
            or self.verified_release.provider is not AscensionMethod.KERNELSU_LKM
            or verified[0] != self.verified_release
            or value.apk_sha256 != verified[0].asset.sha256
        ):
            self.status.setText(
                "The Manager install finished, but the exact phone or official release evidence changed. ROMVERSE will revalidate before recording KernelSU support."
            )
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("KernelSU compatibility result")
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setText("What does the official KernelSU Manager show?")
        dialog.setInformativeText(
            "Open KernelSU Manager on the phone and read the main status. Choose the exact result—ROMVERSE will not guess.\n\n"
            "Not installed means this kernel is supported and the source image can be patched. Unsupported means ROMVERSE should use the recommended Magisk route instead."
        )
        supported = dialog.addButton("Shows Not installed", QMessageBox.ButtonRole.AcceptRole)
        unsupported = dialog.addButton("Shows Unsupported", QMessageBox.ButtonRole.DestructiveRole)
        dialog.addButton("I have not checked", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        if dialog.clickedButton() not in {supported, unsupported}:
            self.status.setText(
                "Manager installed; support is still unconfirmed. Open it on the phone, then retry this check."
            )
            return
        status = "supported" if dialog.clickedButton() is supported else "unsupported"
        try:
            KernelSuSupportEvidenceService(
                self.studio.store,
                self._release_service(),
            ).record(
                self.project.project_id,
                device,
                self.verified_release.tag,
                self.verified_release.asset.sha256,
                status,
            )
        except ProjectError as exc:
            self.status.setText(
                f"KernelSU result was not trusted because Manager provenance changed: {exc}. "
                "ROMVERSE will reacquire the official Manager before retrying; root was not applied."
            )
            self._reacquire_changed_manager(AscensionMethod.KERNELSU_LKM)
            return
        if status == "unsupported":
            magisk_index = self.method.findData(AscensionMethod.MAGISK)
            self.method.setCurrentIndex(magisk_index)
            self.status.setText(
                "KernelSU Manager reported Unsupported. ROMVERSE recorded the result and safely switched to the recommended Magisk image-patch route."
            )
            return
        self.refresh()
        self.status.setText(
            "KernelSU support confirmed by the verified official Manager. ROMVERSE can now prepare the exact LKM patch capsule."
        )
        QTimer.singleShot(0, self._ensure_patch_capsule)

    def _start_prerequisite_operation(
        self,
        operation: str,
        message: str,
        partitions: tuple[str, ...] = (),
    ) -> bool:
        if self.worker is not None or self.studio.worker is not None:
            return False
        self.prerequisite_operation = operation
        self.method.setEnabled(False)
        self.acquire_button.setEnabled(False)
        self.acquire_button.setText("ROMVERSE is resolving …")
        self.progress.begin(determinate=True)
        self.status.setText(message)
        self.studio._start_worker(operation, partitions=partitions)
        if self.studio.worker is None:
            self.prerequisite_operation = ""
            self.progress.stop()
            self.method.setEnabled(True)
            self.acquire_button.setEnabled(True)
            self.status.setText(
                "Automatic extraction could not start. Open Forge Arsenal to verify Payload Dumper, then retry."
            )
            return False
        return True

    @Slot(str, int)
    def _prerequisite_progress(self, operation: str, value: int) -> None:
        if operation == self.prerequisite_operation:
            self.progress.report(value)
            self.status.setText(
                f"Automatic resolver  •  {operation.replace('-', ' ')}  •  {value}%"
            )

    @Slot(str, object)
    def _prerequisite_complete(self, operation: str, result: object) -> None:
        if operation != self.prerequisite_operation:
            return
        self.prerequisite_operation = ""
        self.progress.finish()
        self.method.setEnabled(True)
        self.acquire_button.setEnabled(True)
        self.context_refresh_pending = False
        self.refresh()
        # RomStudio clears its worker before emitting operation_completed, so the
        # next Ascension-only step can start deterministically here. A zero-delay
        # timer could be lost when this dialog is driven without a continuously
        # running event loop, leaving the beginner journey visibly stalled after
        # successful payload extraction.
        self._ensure_patch_capsule()

    @Slot(str, str)
    def _prerequisite_failed(self, operation: str, message: str) -> None:
        if operation != self.prerequisite_operation:
            return
        self.prerequisite_operation = ""
        self.progress.stop()
        self.method.setEnabled(True)
        self.acquire_button.setEnabled(True)
        pending = self.context_refresh_pending
        self.context_refresh_pending = False
        self.status.setText(
            f"Automatic resolver stopped safely. Why: {message}  •  No phone write occurred."
        )
        self._finish_ascension_live(
            MissionState.ATTENTION,
            f"Ascension prerequisite {operation.replace('-', ' ')} stopped safely.",
            "ROMVERSE preserved the project and kept the detailed failure inside the local Ascension status instead of publishing device or workspace details.",
            "Resolve the described evidence or tool issue, then retry the highlighted step.",
            MissionConfidence.UNCONFIRMED,
        )
        if pending:
            QTimer.singleShot(0, self._device_context_changed)

    def _handoff_service(self) -> RootPatchHandoffService | None:
        gateway = getattr(self.studio, "gateway", None)
        adb = getattr(self.studio, "adb_executable", None)
        if gateway is None or adb is None:
            return None
        return RootPatchHandoffService(
            self.studio.store,
            Path(adb),
            gateway,
            ApprovalStore(self.studio.store.workspace),
            self.studio.pack_registry,
            self._release_service(),
        )

    def _patched_output_service(self) -> RootPatchedOutputService | None:
        gateway = getattr(self.studio, "gateway", None)
        adb = getattr(self.studio, "adb_executable", None)
        if gateway is None or adb is None:
            return None
        return RootPatchedOutputService(
            self.studio.store,
            Path(adb),
            gateway,
            ApprovalStore(self.studio.store.workspace),
        )

    def _manager_launch_service(self) -> RootManagerLaunchService | None:
        gateway = getattr(self.studio, "gateway", None)
        adb = getattr(self.studio, "adb_executable", None)
        if gateway is None or adb is None:
            return None
        return RootManagerLaunchService(
            self.studio.store,
            Path(adb),
            gateway,
            ApprovalStore(self.studio.store.workspace),
            self.studio.pack_registry,
            self._release_service(),
        )

    def _open_verified_manager(self) -> None:
        service = self._manager_launch_service()
        method = AscensionMethod(self.method.currentData())
        device = next(
            (item for item in self.studio.devices if getattr(item.state, "value", "") == "device"),
            None,
        )
        if service is None or device is None:
            self.status.setText(
                "Reconnect and authorize the exact phone before opening the verified Manager."
            )
            return
        try:
            plan = service.plan_path(self.project.project_id, method, device)
        except ProjectError as exc:
            self.status.setText(f"Verified Manager handoff stopped safely. Why: {exc}")
            return
        answer = QMessageBox.question(
            self,
            f"Open verified {method.display_name}",
            f"ROMVERSE will first ask Android for the installed path of the allowlisted package:\n\n"
            f"{plan.package_name}\n\n"
            "This lookup reads no personal files and does not patch, root, reboot, flash, wipe, unlock, or relock the phone. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            self.status.setText("Verified Manager opening cancelled. Nothing was changed.")
            return
        ApprovalStore(self.studio.store.workspace).issue(
            plan.approval_digest,
            plan.device_key,
        )
        worker = AscensionManagerLaunchWorker(service, path_plan=plan)
        worker.signals.complete.connect(self._manager_path_ready)
        worker.signals.failed.connect(self._failed)
        self.worker = worker
        self.method.setEnabled(False)
        self.acquire_button.setEnabled(False)
        self.acquire_button.setText("Checking installed Manager …")
        self.progress.begin(determinate=False)
        self.status.setText(
            f"Resolving the installed {method.display_name} package through the exact authorized ADB connection …"
        )
        start_background(worker)

    @Slot(object)
    def _manager_path_ready(self, value: object) -> None:
        self.worker = None
        self.progress.finish()
        self.method.setEnabled(True)
        self.acquire_button.setEnabled(True)
        if not isinstance(value, RootManagerLaunchPlan):
            self._failed("Installed Manager lookup returned an unexpected result")
            return
        method = value.method
        answer = QMessageBox.question(
            self,
            f"Verify and open {method.display_name}",
            f"Android reported the installed {method.display_name} base package. ROMVERSE will now:\n\n"
            "1. Copy only that installed APK into isolated temporary PC storage\n"
            f"2. Require full SHA-256 {value.manager_sha256[:24]}… and the pinned official signing certificate\n"
            "3. Delete the temporary copy\n"
            f"4. Open only {value.package_name}\n\n"
            "The Manager will still require you to select the ROMVERSE image. No root or flash is performed by this action. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            self.status.setText(
                "Installed Manager verification cancelled. No APK was copied and nothing was opened."
            )
            self.refresh()
            return
        service = self._manager_launch_service()
        if service is None:
            self.status.setText("The authorized ADB connection became unavailable.")
            return
        ApprovalStore(self.studio.store.workspace).issue(
            value.approval_digest,
            value.device_key,
        )
        worker = AscensionManagerLaunchWorker(service, launch_plan=value)
        worker.signals.progress.connect(self.progress.report)
        worker.signals.complete.connect(self._manager_opened)
        worker.signals.failed.connect(self._failed)
        self.worker = worker
        self.method.setEnabled(False)
        self.acquire_button.setEnabled(False)
        self.acquire_button.setText("Verifying and opening Manager …")
        self.progress.begin(determinate=False)
        self.status.setText(
            f"Copying, verifying, and opening the installed {method.display_name}. ADB does not expose a trustworthy completion percentage, so this remains animated until every check returns …"
        )
        start_background(worker)

    @Slot(object)
    def _manager_opened(self, value: object) -> None:
        self.worker = None
        self.progress.finish()
        self.method.setEnabled(True)
        self.acquire_button.setEnabled(True)
        if not isinstance(value, RootManagerLaunchReceipt):
            self._failed("Verified Manager launch returned an unexpected result")
            return
        self.manager_launch_receipt = value
        self._record_manager_opened_note(value)
        self.refresh()
        self.status.setText(
            f"Verified {value.method.display_name} opened on the exact phone  •  temporary verification copy removed  •  now select the ROMVERSE image in the Manager  •  root applied: NO  •  flashed: NO"
        )
        QTimer.singleShot(0, self._offer_output_watch)

    def _record_manager_opened_note(self, receipt: RootManagerLaunchReceipt) -> None:
        store = self._live_console_store()
        if store is None:
            return
        with suppress(LiveConsoleStoreError):
            store.note(
                source="Ascension Protocol",
                stage="verified-manager-open",
                title=f"Verified {receipt.method.display_name} opened",
                summary="The installed Manager APK matched the official hash and pinned signer before ROMVERSE opened it.",
                explanation="ROMVERSE copied only the installed base APK into isolated temporary storage, revalidated it, removed the copy, and launched one allowlisted package. No image was patched or flashed.",
                next_action="In the opened Manager, select the transferred ROMVERSE image and complete its standard file-patch step.",
                state=MissionState.INFORMATION,
                progress_percent=100,
                confidence=MissionConfidence.VERIFIED,
                guardian_protected=True,
                project_id=self.project.project_id,
                evidence_refs=(
                    f"projects/{self.project.project_id}/ascension/manager-launch/{RootManagerLaunchService.RECEIPT_NAME}",
                ),
                dedupe_key=f"ascension-manager-open-{receipt.receipt_digest}",
            )

    def _offer_output_watch(self) -> None:
        if self.output_watch_active or self.worker is not None:
            return
        service = self._patched_output_service()
        method = AscensionMethod(self.method.currentData())
        device = next(
            (item for item in self.studio.devices if getattr(item.state, "value", "") == "device"),
            None,
        )
        if service is None or device is None or self.handoff_receipt is None:
            self.status.setText(
                f"Verified {method.display_name} opened. Return here after patching and choose Find patched image."
            )
            return
        answer = QMessageBox.question(
            self,
            "Watch for the patched image automatically",
            f"While you finish the patch in {method.display_name}, ROMVERSE can watch only filenames in Downloads for up to nine minutes. It checks every {self.OUTPUT_SCAN_INTERVAL_SECONDS} seconds, ignores files from another root manager, reads no file contents until you approve one exact result, and stops immediately if you close Ascension.\n\nStart the filename-only watch?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            self.status.setText(
                f"Automatic watch was not started. Finish the patch in {method.display_name}, then choose Find patched image."
            )
            return
        try:
            ApprovalStore(self.studio.store.workspace).issue(
                service.list_digest(device.serial),
                self.handoff_receipt.device_key,
            )
        except ProjectError as exc:
            self.status.setText(f"Automatic output watch stopped safely. Why: {exc}")
            return
        now = monotonic()
        self.output_watch_active = True
        self.output_watch_started_at = now
        self.output_watch_last_scan_at = 0.0
        self.output_watch_scan_count = 0
        self.method.setEnabled(False)
        self.acquire_button.setEnabled(False)
        self.acquire_button.setText("Watching for patched image …")
        self.progress.begin(determinate=True)
        self.progress.report(0)
        self.status.setText(
            f"Automatic watch active  •  finish the patch in {method.display_name}  •  filenames only  •  9:00 remaining  •  phone changed: NO"
        )
        self.output_watch_timer.start()
        QTimer.singleShot(0, self._watch_phone_output_tick)

    def _watch_phone_output_tick(self) -> None:
        if not self.output_watch_active:
            return
        now = monotonic()
        elapsed = max(0.0, now - self.output_watch_started_at)
        if elapsed >= self.OUTPUT_WATCH_SECONDS:
            if self.worker is not None:
                self.progress.report(99)
                return
            self._record_output_discovery_note(AscensionMethod(self.method.currentData()))
            self._stop_output_watch(completed=True)
            self.status.setText(
                "Automatic filename watch finished after nine minutes without a matching output. The Manager may still be working; choose Find patched image when it finishes. Nothing was copied or changed."
            )
            return
        self.progress.report(min(99, int(elapsed * 100 / self.OUTPUT_WATCH_SECONDS)))
        if self.worker is not None:
            return
        if now - self.output_watch_last_scan_at < self.OUTPUT_SCAN_INTERVAL_SECONDS:
            return
        service = self._patched_output_service()
        method = AscensionMethod(self.method.currentData())
        device = next(
            (item for item in self.studio.devices if getattr(item.state, "value", "") == "device"),
            None,
        )
        if service is None or device is None or self.handoff_receipt is None:
            self._stop_output_watch()
            self.status.setText(
                "Automatic watch stopped because the exact authorized phone is unavailable. Reconnect it and choose Find patched image; no file was copied."
            )
            return
        self.output_watch_last_scan_at = now
        self.output_watch_scan_count += 1
        remaining = max(0, int(self.OUTPUT_WATCH_SECONDS - elapsed))
        worker = AscensionPhoneOutputWorker(
            service,
            project_id=self.project.project_id,
            method=method,
            serial=device.serial,
        )
        worker.signals.complete.connect(self._phone_outputs_found)
        worker.signals.failed.connect(self._output_watch_failed)
        self.worker = worker
        self.status.setText(
            f"Automatic filename scan {self.output_watch_scan_count}  •  checking for {method.display_name} output  •  {remaining // 60}:{remaining % 60:02d} remaining  •  phone changed: NO"
        )
        start_background(worker)

    @Slot(str)
    def _output_watch_failed(self, message: str) -> None:
        self._stop_output_watch()
        self._failed(message)

    def _stop_output_watch(self, *, completed: bool = False) -> None:
        if not self.output_watch_active and not self.output_watch_timer.isActive():
            return
        self.output_watch_active = False
        self.output_watch_timer.stop()
        self.output_watch_started_at = 0.0
        self.output_watch_last_scan_at = 0.0
        self.output_watch_scan_count = 0
        if self.worker is None:
            self.method.setEnabled(True)
            self.acquire_button.setEnabled(True)
            if completed:
                self.progress.finish()
            else:
                self.progress.stop()
            self._update_primary_action(self.current_report)

    def _find_patched_on_phone(self) -> None:
        if self.output_watch_active:
            self.status.setText("ROMVERSE is already watching Downloads for the patched image.")
            return
        service = self._patched_output_service()
        method = AscensionMethod(self.method.currentData())
        device = next(
            (item for item in self.studio.devices if getattr(item.state, "value", "") == "device"),
            None,
        )
        if service is None or device is None:
            self.status.setText(
                "Reconnect and authorize the exact phone, or choose the patched image manually."
            )
            self._import_patched()
            return
        if self.handoff_receipt is None:
            self.status.setText(
                "The verified phone handoff is no longer available. Review guided phone preparation again before scanning Downloads."
            )
            self.refresh()
            return
        answer = QMessageBox.question(
            self,
            "Find the patched image on your phone",
            f"ROMVERSE will read filenames only in the phone's Downloads folder and look for the image created by {method.display_name}. Outputs from other root managers will be ignored. It will not read other folders, patch the phone, or flash anything.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            self.status.setText(
                "Phone search cancelled. You can retry or import a local patched image."
            )
            return
        device_key = self.handoff_receipt.device_key
        approvals = ApprovalStore(self.studio.store.workspace)
        approvals.issue(service.list_digest(device.serial), device_key)
        worker = AscensionPhoneOutputWorker(
            service,
            project_id=self.project.project_id,
            method=method,
            serial=device.serial,
        )
        worker.signals.complete.connect(self._phone_outputs_found)
        worker.signals.failed.connect(self._failed)
        self.worker = worker
        self.method.setEnabled(False)
        self.acquire_button.setEnabled(False)
        self.acquire_button.setText("Searching phone Downloads …")
        self.progress.begin(determinate=False)
        self.status.setText(
            f"Reading Downloads filenames through the exact authorized ADB connection and ranking matching {method.display_name} outputs newest first …"
        )
        start_background(worker)

    @Slot(object)
    def _phone_outputs_found(self, value: object) -> None:
        watching = self.output_watch_active
        self.worker = None
        if watching and self.context_refresh_pending:
            self.context_refresh_pending = False
            self._stop_output_watch()
            self.status.setText(
                "Automatic watch stopped because the connected-device evidence changed. ROMVERSE will revalidate the phone before another scan."
            )
            QTimer.singleShot(0, self._device_context_changed)
            return
        if not watching:
            self.progress.finish()
            self.method.setEnabled(True)
            self.acquire_button.setEnabled(True)
        if not isinstance(value, AscensionOutputDiscoveryCompletion) or any(
            not isinstance(item, str) for item in getattr(value, "names", ())
        ):
            self._stop_output_watch()
            self._failed("Patched-output scan returned unexpected terminal evidence")
            return
        names = value.names
        method = AscensionMethod(self.method.currentData())
        service = self._patched_output_service()
        device = next(
            (item for item in self.studio.devices if getattr(item.state, "value", "") == "device"),
            None,
        )
        persisted = (
            service.load_discovery(self.project.project_id, method, device.serial)
            if service is not None and device is not None
            else None
        )
        receipt = value.receipt
        expected_refs = tuple(sha256(name.encode("utf-8")).hexdigest() for name in names)
        expected_state = "found" if names else "none"
        if (
            persisted is None
            or persisted != receipt
            or receipt.project_id != self.project.project_id
            or receipt.method is not method
            or receipt.state != expected_state
            or receipt.candidate_count != len(names)
            or receipt.candidate_refs != expected_refs
            or receipt.recommended_name_ref != (expected_refs[0] if expected_refs else "")
            or receipt.data_scope != "filenames-only"
            or receipt.source_directory != "/sdcard/Download"
            or receipt.ordering != "modified-descending"
            or receipt.phone_changed
            or receipt.execution_authority != "none"
        ):
            self._stop_output_watch()
            self._failed("Patched-output scan evidence changed before it could be displayed")
            return
        self.output_discovery = receipt
        if not names:
            if watching:
                elapsed = max(0.0, monotonic() - self.output_watch_started_at)
                remaining = max(0, int(self.OUTPUT_WATCH_SECONDS - elapsed))
                self.status.setText(
                    f"No matching {method.display_name} image yet  •  automatic watch continues  •  {remaining // 60}:{remaining % 60:02d} remaining  •  filenames only  •  phone changed: NO"
                )
                return
            self._record_output_discovery_note(method)
            answer = QMessageBox.question(
                self,
                f"{method.display_name} image not found yet",
                f"ROMVERSE did not find an image created by {method.display_name} in Downloads. Finish the patch in the verified official manager first. Files from a different root manager are deliberately ignored so the wrong image cannot enter this route. You can also choose an image you already copied to this PC.\n\nChoose a local image now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer is QMessageBox.StandardButton.Yes:
                self._import_patched()
            else:
                self.status.setText(
                    f"Waiting for {method.display_name} to create its patched image. Select Find patched image on phone when it is ready."
                )
            return
        if watching:
            self._stop_output_watch(completed=True)
        self._record_output_discovery_note(method)
        selected = names[0]
        if len(names) > 1:
            selected, accepted = QInputDialog.getItem(
                self,
                "Confirm the recommended patched image",
                "Matching images, newest first (recommended image preselected)",
                names,
                0,
                False,
            )
            if not accepted:
                self.status.setText("Patched-image selection cancelled. Nothing was copied.")
                return
        self._retrieve_phone_output(selected)

    def _record_output_discovery_note(self, method: AscensionMethod) -> None:
        receipt = self.output_discovery
        store = self._live_console_store()
        if receipt is None or store is None:
            return
        found = receipt.state == "found"
        with suppress(LiveConsoleStoreError):
            store.note(
                source="Ascension Protocol",
                stage="patched-output-discovery",
                title=f"{method.display_name} patched-output scan complete",
                summary=(
                    f"ROMVERSE found {receipt.candidate_count} matching manager output filename(s)."
                    if found
                    else "ROMVERSE found no matching manager output filename yet."
                ),
                explanation=(
                    "The approved scan read filenames only, ranked matches newest first, stored only SHA-256 references, and did not copy a file or modify the phone."
                ),
                next_action=(
                    "Review the recommended exact filename and approve its read-only retrieval."
                    if found
                    else f"Finish patching the ROMVERSE image in {method.display_name}, then run the filename-only scan again."
                ),
                state=MissionState.INFORMATION if found else MissionState.ATTENTION,
                progress_percent=100,
                confidence=MissionConfidence.VERIFIED,
                guardian_protected=True,
                project_id=self.project.project_id,
                evidence_refs=(
                    f"projects/{self.project.project_id}/ascension/phone-output/{method.value}/{RootPatchedOutputService.DISCOVERY_NAME}",
                ),
                dedupe_key=f"ascension-output-discovery-{receipt.receipt_digest}",
            )

    def _retrieve_phone_output(self, name: str) -> None:
        service = self._patched_output_service()
        device = next(
            (item for item in self.studio.devices if getattr(item.state, "value", "") == "device"),
            None,
        )
        if service is None or device is None:
            self.status.setText("The authorized phone disconnected before retrieval.")
            return
        method = AscensionMethod(self.method.currentData())
        try:
            plan = service.plan(self.project.project_id, method, device.serial, name)
        except ProjectError as exc:
            self.status.setText(f"Patched-image retrieval stopped safely. Why: {exc}")
            return
        answer = QMessageBox.question(
            self,
            "Retrieve and verify patched image",
            f"ROMVERSE found:\n{plan.remote_path}\n\n"
            "It will copy this one file into temporary local verification storage, prove its Android boot header and source capsule, then remove the temporary copy. No phone partition will be changed. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            self.status.setText("Patched-image retrieval cancelled. No file was copied.")
            return
        ApprovalStore(self.studio.store.workspace).issue(plan.approval_digest, plan.device_key)
        worker = AscensionPhoneOutputWorker(service, plan=plan)
        worker.signals.progress.connect(self.progress.report)
        worker.signals.complete.connect(self._patched_ready)
        worker.signals.failed.connect(self._failed)
        self.worker = worker
        self.method.setEnabled(False)
        self.acquire_button.setEnabled(False)
        self.acquire_button.setText("Retrieving and verifying …")
        self.progress.begin(determinate=False)
        self.status.setText(
            "Copying the selected patched image from Android without inventing an ADB percentage; measured local vault-copy and rehash progress will appear automatically afterward …"
        )
        start_background(worker)

    def _review_handoff(self) -> None:
        service = self._handoff_service()
        device = next(
            (item for item in self.studio.devices if getattr(item.state, "value", "") == "device"),
            None,
        )
        if service is None or device is None:
            self.status.setText(
                "Connect and authorize the exact phone, then retry the guided patch handoff."
            )
            return
        method = AscensionMethod(self.method.currentData())
        try:
            plan = service.plan(self.project.project_id, method, device)
        except (OSError, ProjectError) as exc:
            self.status.setText(f"Automatic handoff stopped safely. Why: {exc}")
            return
        if not plan.safety_ready:
            reasons = "; ".join(
                (*plan.apk_plan.assessment.reasons, *plan.transfer_assessment.reasons)
            )
            self.status.setText(f"Phone handoff needs more safety evidence: {reasons}")
            return
        answer = QMessageBox.question(
            self,
            "Approve Ascension phone patch handoff",
            f"ROMVERSE is ready to perform exactly two reversible preparation actions:\n\n"
            f"1. Install the verified official {method.display_name} manager\n"
            f"   SHA-256: {plan.apk_plan.inspection.sha256[:24]}…\n"
            f"2. Copy the pristine source-bound image to:\n"
            f"   {plan.remote_input_path}\n\n"
            f"Target: {device.display_name} ({device.codename})\n\n"
            "This does NOT patch, root, reboot, unlock, wipe, or flash the phone. Approve these exact actions?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            self.status.setText("Phone handoff cancelled. No device action was run.")
            return
        approvals = ApprovalStore(self.studio.store.workspace)
        approvals.issue(plan.apk_plan.digest, plan.device_key)
        approvals.issue(plan.transfer_digest, plan.device_key)
        worker = AscensionHandoffWorker(service, plan)
        worker.signals.progress.connect(self.progress.report)
        worker.signals.complete.connect(self._handoff_ready)
        worker.signals.failed.connect(self._failed)
        self.worker = worker
        self.method.setEnabled(False)
        self.acquire_button.setEnabled(False)
        self.acquire_button.setText("Installing and transferring …")
        self.progress.begin(determinate=False)
        self.status.setText(
            "Guardian approved  •  installing the exact verified manager, then transferring only the pristine patch input  •  ADB does not expose a trustworthy completion percentage …"
        )
        start_background(worker)

    @Slot(object)
    def _handoff_ready(self, receipt: object) -> None:
        self.worker = None
        self.progress.finish()
        self.method.setEnabled(True)
        self.acquire_button.setEnabled(True)
        method = AscensionMethod(self.method.currentData())
        persisted = load_root_patch_handoff(
            self.studio.store,
            self.project.project_id,
            method,
        )
        if (
            not isinstance(receipt, RootPatchHandoffReceipt)
            or persisted is None
            or persisted != receipt
        ):
            self._failed("Phone patch handoff returned unexpected or unverified terminal evidence")
            return
        self.handoff_receipt = receipt
        self.refresh()
        self.status.setText(
            "Phone patch handoff complete  •  manager installed  •  pristine image transferred  •  root applied: NO  •  flashed: NO"
        )
        QTimer.singleShot(0, self._open_verified_manager)

    def _cancel_manager_retry(self, *, clear_budget: bool) -> None:
        was_pending = self.manager_retry_timer.isActive()
        self.manager_retry_timer.stop()
        self.manager_retry_method = None
        if was_pending and self.worker is None:
            self.acquire_button.setEnabled(True)
            self.method.setEnabled(True)
        if clear_budget:
            self.manager_retry_attempts.clear()

    @Slot()
    def _retry_official_manager(self) -> None:
        method = self.manager_retry_method
        self.manager_retry_method = None
        if method is None or self.worker is not None:
            return
        if not self.isVisible() or AscensionMethod(self.method.currentData()) is not method:
            self.acquire_button.setEnabled(True)
            self.method.setEnabled(True)
            return
        attempt = self.manager_retry_attempts.get(method, 0)
        self.status.setText(
            f"Automatic network recovery {attempt} of "
            f"{len(self.MANAGER_CONNECTIVITY_RETRY_DELAYS_MS)}  •  reconnecting to the "
            f"official {method.display_name} release service …"
        )
        self._acquire()

    @Slot(str)
    def _manager_connectivity_failed(self, message: str) -> None:
        """Retry only a typed official-provider outage, never a trust rejection."""

        self.worker = None
        self.progress.stop()
        self.method.setEnabled(True)
        method = AscensionMethod(self.method.currentData())
        retry_index = self.manager_retry_attempts.get(method, 0)
        delays = self.MANAGER_CONNECTIVITY_RETRY_DELAYS_MS
        if self.isVisible() and retry_index < len(delays):
            delay_ms = delays[retry_index]
            attempt = retry_index + 1
            self.manager_retry_attempts[method] = attempt
            self.manager_retry_method = method
            self.acquire_button.setEnabled(False)
            self.acquire_button.setText(f"Network retry {attempt} of {len(delays)} …")
            seconds = max(1, round(delay_ms / 1_000))
            self.status.setText(
                "The official provider connection was interrupted. "
                f"ROMVERSE will retry automatically in {seconds} second(s) "
                f"({attempt} of {len(delays)}). Rejected hashes, signatures, packages, or "
                "metadata are never retried. Phone changed: NO."
            )
            self._record_manager_connectivity_retry(method, message, attempt, seconds)
            self.manager_retry_timer.start(delay_ms)
            return
        exhausted = (
            f" after {len(delays)} bounded automatic retries" if retry_index >= len(delays) else ""
        )
        self._failed(f"Official provider connectivity remained unavailable{exhausted}. {message}")

    def _record_manager_connectivity_retry(
        self,
        method: AscensionMethod,
        _message: str,
        attempt: int,
        seconds: int,
    ) -> None:
        store = self._live_console_store()
        if store is None:
            return
        with suppress(LiveConsoleStoreError):
            store.note(
                source="Ascension Protocol",
                stage="official-manager-connectivity",
                title=f"Official {method.display_name} connection retry {attempt}",
                summary=f"A verified-provider connection failed; retrying in {seconds} second(s).",
                explanation=(
                    "ROMVERSE kept the detailed provider error inside the local Ascension status and classified only the connection as retryable. "
                    "Artifact identity, hash, package, signer, and metadata failures still fail closed."
                ),
                next_action="No action is needed during the bounded retry; keep Ascension visible.",
                state=MissionState.ATTENTION,
                progress_percent=0,
                confidence=MissionConfidence.HIGH,
                guardian_protected=True,
                project_id=self.project.project_id,
                evidence_refs=(
                    f"projects/{self.project.project_id}/ascension/route/route-record.romverse",
                ),
                dedupe_key=f"ascension-manager-connectivity-{method.value}-{attempt}",
            )

    def _acquire(self, *, automatic: bool = False) -> None:
        if self.worker is not None:
            return
        if not self._resolve_required_tools(
            self.MANAGER_VERIFICATION_TOOLS,
            purpose=(
                "Ascension needs Android package identity and signer verification before "
                "it may trust an official root manager."
            ),
            automatic=automatic,
        ):
            return
        self._cancel_manager_retry(clear_budget=False)
        method = AscensionMethod(self.method.currentData())
        self.worker = AscensionReleaseWorker(
            self.studio.store.workspace,
            method,
            self._verified_tool("AAPT2"),
            self._verified_tool("APK Signer"),
            self.tool_runner,
        )
        self.worker.signals.progress.connect(self.progress.report)
        self.worker.signals.complete.connect(self._acquired)
        self.worker.signals.connectivity_failed.connect(self._manager_connectivity_failed)
        self.worker.signals.failed.connect(self._failed)
        self.acquire_button.setEnabled(False)
        self.acquire_button.setText("Verifying official release …")
        self.method.setEnabled(False)
        self.progress.begin(determinate=False)
        self.status.setText(
            f"Resolving stable {method.display_name} release from its official repository …"
        )
        start_background(self.worker)

    def _release_service(self) -> OfficialRootReleaseService:
        return OfficialRootReleaseService(
            self.studio.store.workspace,
            aapt_executable=self._verified_tool("AAPT2"),
            apksigner_executable=self._verified_tool("APK Signer"),
            runner=self.tool_runner,
        )

    def _verified_tool(self, name: str) -> Path | None:
        status = next(
            (
                item
                for item in getattr(self.studio, "tool_statuses", ())
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

    @Slot(object)
    def _acquired(self, result: object) -> None:
        self.worker = None
        self.progress.finish()
        self.method.setEnabled(True)
        self.acquire_button.setEnabled(True)
        if not isinstance(result, OfficialRootAcquisition):
            self._failed("Official manager acquisition returned an unexpected result")
            return
        release = result.release
        tag = release.tag
        digest = release.asset.sha256
        self.status.setText(
            f"{tag} verified  •  SHA-256 {digest[:16]}…  •  {result.mode.replace('-', ' ')}  •  installed: NO"
        )
        self._manager_verified(release, result.path, result.explanation, result.mode)

    @Slot(object)
    def _capsule_ready(self, capsule: object) -> None:
        self.worker = None
        self.progress.finish()
        self.method.setEnabled(True)
        self.acquire_button.setEnabled(True)
        method = AscensionMethod(self.method.currentData())
        persisted = RootPatchPreparationService(self.studio.store).load(
            self.project.project_id,
            method,
        )
        if not isinstance(capsule, RootPatchCapsule) or persisted is None or persisted != capsule:
            self._failed("Patch capsule returned unexpected or unverified terminal evidence")
            return
        self.patch_capsule = capsule
        self.refresh()
        self.status.setText(
            "Automatic patch capsule complete  •  every input is source-bound and SHA-256 verified  •  phone changed: NO"
        )

    def _import_patched(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose the patched boot image produced from this capsule",
            str(Path.home() / "Downloads"),
            "Android boot image (*.img)",
        )
        if not selected:
            return
        method = AscensionMethod(self.method.currentData())
        worker = AscensionPreparationWorker(
            self.studio.store,
            self.project.project_id,
            method,
            patched_path=Path(selected),
        )
        worker.signals.progress.connect(self.progress.report)
        worker.signals.complete.connect(self._patched_ready)
        worker.signals.failed.connect(self._failed)
        self.worker = worker
        self.method.setEnabled(False)
        self.acquire_button.setEnabled(False)
        self.acquire_button.setText("Verifying patched image …")
        self.progress.begin(determinate=False)
        self.status.setText(
            "Proving the candidate Android boot header, ramdisk, source capsule, and bounded size; measured vault-copy and independent rehash progress will appear automatically …"
        )
        start_background(worker)

    @Slot(object)
    def _patched_ready(self, receipt: object) -> None:
        self.worker = None
        self.progress.finish()
        self.method.setEnabled(True)
        self.acquire_button.setEnabled(True)
        if not isinstance(receipt, PatchedImageReceipt):
            self._failed("Patched-image verification returned an unexpected result")
            return
        self.patched_receipt = receipt
        self.refresh()
        self.status.setText(
            f"Patched image verified with {receipt.lineage_confidence} immutable-lineage confidence  •  ROMVERSE is continuing automatically "
            "with rollback-protected integration and Build Seal  •  phone changed: NO"
        )
        QTimer.singleShot(0, self._continue_after_patched)

    def _continue_after_patched(self) -> None:
        """Continue only the reversible local half of Ascension automatically."""

        if self.worker is not None or self.patched_receipt is None:
            return
        if self.integration_receipt is None:
            self._integrate_root_rom()
            return
        if self.build_seal_receipt is None:
            self._seal_root_build()

    @Slot(str)
    def _failed(self, message: str) -> None:
        self.worker = None
        self.manager_install_plan = None
        self._stop_output_watch()
        self.progress.stop()
        self.acquire_button.setEnabled(True)
        self.method.setEnabled(True)
        pending = self.context_refresh_pending
        self.context_refresh_pending = False
        self.acquire_button.setText("Retry the safe step")
        self.status.setText(
            "Automatic Ascension step stopped safely. "
            f"Why: {message}  •  How: check the connection or evidence described above, then select Retry the safe step. No phone partition was changed."
        )
        self._finish_ascension_live(
            MissionState.ATTENTION,
            "An Ascension preparation step stopped safely.",
            "ROMVERSE preserved verified evidence, made no partition change, and kept detailed device or workspace diagnostics inside the local Ascension status.",
            "Check the connection or evidence shown in Ascension, then retry the safe step.",
            MissionConfidence.UNCONFIRMED,
        )
        if pending:
            QTimer.singleShot(0, self._device_context_changed)

    @staticmethod
    def _stylesheet() -> str:
        return """
            QScrollArea, QWidget { background: #02050A; border: none; }
            QFrame#AscensionOverview { background: #071422; border: 1px solid #24BFD2; border-radius: 12px; }
            QFrame#AscensionGuide { background: rgba(12, 20, 42, 226); border: 1px solid #8E54F4; border-radius: 12px; }
            QProgressBar#AscensionJourneyProgress { min-height: 20px; color: #F5F8FF; font-size: 10px; font-weight: 800; text-align: center; background: #070D1B; border: 1px solid #354A78; border-radius: 6px; }
            QProgressBar#AscensionJourneyProgress::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #8F48EE,stop:0.56 #5573FF,stop:1 #2ADDEB); border-radius: 5px; }
            QFrame#AscensionWorkflow { background: #050B15; border: 1px solid #28466D; border-radius: 11px; }
            QFrame#AscensionHandoff { background: #091124; border: 1px solid #A354EF; border-radius: 11px; padding: 4px; }
            QLabel[stageState="complete"] { color: #58EDB1; background: #082018; border: 1px solid #227A58; border-radius: 8px; padding: 9px; font-weight: 800; }
            QLabel[stageState="active"] { color: #FFFFFF; background: #39205E; border: 1px solid #BA5DFF; border-radius: 8px; padding: 9px; font-weight: 900; }
            QLabel[stageState="pending"] { color: #687896; background: #090F1C; border: 1px solid #23334F; border-radius: 8px; padding: 9px; font-weight: 700; }
            QFrame[gateStatus="pass"] { background: #061710; border: 1px solid #176845; border-radius: 9px; }
            QFrame[gateStatus="attention"] { background: #181405; border: 1px solid #826A1D; border-radius: 9px; }
            QFrame[gateStatus="blocked"] { background: #1B080F; border: 1px solid #7C2742; border-radius: 9px; }
            QLabel#GateCopy { color: #DCE8FA; font-size: 13px; background: transparent; }
            QLabel#GateSymbol { color: #5CEBB0; font-size: 20px; font-weight: 900; background: transparent; }
            QLabel#GateBadge { color: #9EDFF5; font-weight: 900; font-size: 11px; background: transparent; }
            QCheckBox#ConsentCheck { color: #EDF4FF; spacing: 12px; padding: 5px 8px; background: transparent; }
            QCheckBox#ConsentCheck::indicator { width: 20px; height: 20px; border: 2px solid #52DFF0; border-radius: 5px; background: #07111C; }
            QCheckBox#ConsentCheck::indicator:hover { border-color: #C171FF; background: #111A2D; }
            QCheckBox#ConsentCheck::indicator:checked { border-color: #70F3C4; background: #2ED59A; }
            QComboBox { min-width: 300px; padding: 10px 14px; }
        """
