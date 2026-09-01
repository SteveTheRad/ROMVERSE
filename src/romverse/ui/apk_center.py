from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from romverse.applications.receipts import ApkReceiptStore
from romverse.core.activity import ActivityStore, ActivityStoreError
from romverse.core.privacy import WorkspacePrivacy
from romverse.device.apk_install import (
    ApkInspection,
    ApkInstallPlan,
    ApkInstallRequest,
    ApkInstallService,
    create_install_plan,
    inspect_apk,
    install_succeeded,
)
from romverse.device.models import AndroidDevice, DeviceState
from romverse.guardian.approval import ApprovalStore
from romverse.infrastructure.process import CommandResult, CommandRunner, SubprocessRunner
from romverse.infrastructure.tools import ToolStatus
from romverse.ui.background import ManagedRunnable, start_background
from romverse.ui.process_progress import ProcessProgressBar


class ApkWorkerSignals(QObject):
    complete = Signal(object)
    failed = Signal(str)
    progress = Signal(int)


class ApkPlanWorker(ManagedRunnable):
    def __init__(
        self,
        request: ApkInstallRequest,
        target_key: str,
        aapt_executable: Path | None,
        apksigner_executable: Path | None,
        runner: CommandRunner,
    ) -> None:
        super().__init__()
        self.request = request
        self.target_key = target_key
        self.aapt_executable = aapt_executable
        self.apksigner_executable = apksigner_executable
        self.runner = runner
        self.signals = ApkWorkerSignals()

    @Slot()
    def execute(self) -> None:
        try:
            self.signals.complete.emit(
                create_install_plan(
                    self.request,
                    self.target_key,
                    aapt_executable=self.aapt_executable,
                    apksigner_executable=self.apksigner_executable,
                    runner=self.runner,
                    progress=self.signals.progress.emit,
                )
            )
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class ApkInspectionWorker(ManagedRunnable):
    def __init__(
        self,
        path: Path,
        aapt_executable: Path | None,
        apksigner_executable: Path | None,
        runner: CommandRunner,
    ) -> None:
        super().__init__()
        self.path = path
        self.aapt_executable = aapt_executable
        self.apksigner_executable = apksigner_executable
        self.runner = runner
        self.signals = ApkWorkerSignals()

    @Slot()
    def execute(self) -> None:
        try:
            self.signals.complete.emit(
                inspect_apk(
                    self.path,
                    aapt_executable=self.aapt_executable,
                    apksigner_executable=self.apksigner_executable,
                    runner=self.runner,
                    progress=self.signals.progress.emit,
                )
            )
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class ApkInstallWorker(ManagedRunnable):
    def __init__(self, service: ApkInstallService, plan: ApkInstallPlan) -> None:
        super().__init__()
        self.service = service
        self.plan = plan
        self.signals = ApkWorkerSignals()

    @Slot()
    def execute(self) -> None:
        try:
            self.signals.complete.emit(self.service.install(self.plan))
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class ApkCenter(QWidget):
    """Hash-bound, Guardian-approved APK installation workflow."""

    runtime_tools_requested = Signal()
    inspection_tools_requested = Signal()

    def __init__(
        self,
        workspace: Path,
        install_service: ApkInstallService | None = None,
        activity_store: ActivityStore | None = None,
        tool_statuses: tuple[ToolStatus, ...] = (),
        runner: CommandRunner | None = None,
    ) -> None:
        super().__init__()
        self.workspace = workspace
        self.activity_store = activity_store
        self.install_service = install_service
        self.runner = runner or SubprocessRunner()
        self.aapt_executable: Path | None = None
        self.apksigner_executable: Path | None = None
        self.set_tool_statuses(tool_statuses)
        self.receipts = ApkReceiptStore(workspace)
        self.devices: list[AndroidDevice] = []
        self.current_inspection: ApkInspection | None = None
        self.selected_apk_path: Path | None = None
        self.current_plan: ApkInstallPlan | None = None
        self.active_worker: ManagedRunnable | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(12)
        eyebrow = QLabel("APP LAUNCHPAD  •  GUARDIAN CONTROLLED")
        eyebrow.setObjectName("Eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("App Launchpad")
        title.setObjectName("Title")
        layout.addWidget(title)
        intro = QLabel(
            "Choose an APK, let ROMVERSE inspect and fingerprint it, approve the exact plan, "
            "then install through Guardian. The APK and device are revalidated immediately "
            "before ADB is allowed to run."
        )
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.device_label = QLabel("No authorized device selected")
        self.device_label.setObjectName("Muted")
        layout.addWidget(self.device_label)

        details = QFrame()
        details.setObjectName("Card")
        details_layout = QVBoxLayout(details)
        self.file_label = QLabel("1  •  Choose an APK to begin")
        self.file_label.setObjectName("Value")
        self.file_label.setWordWrap(True)
        details_layout.addWidget(self.file_label)
        self.hash_label = QLabel("ROMVERSE will calculate SHA-256 and inspect the APK container.")
        self.hash_label.setObjectName("Muted")
        self.hash_label.setWordWrap(True)
        details_layout.addWidget(self.hash_label)
        self.command_label = QLabel(
            "Execution path: inspect → Guardian preflight → approval → install → receipt"
        )
        self.command_label.setObjectName("Muted")
        self.command_label.setWordWrap(True)
        details_layout.addWidget(self.command_label)
        layout.addWidget(details)

        self.progress = ProcessProgressBar()
        layout.addWidget(self.progress)

        self.choose = QPushButton("1  Choose APK and inspect")
        self.choose.setObjectName("Primary")
        self.choose.setToolTip(
            "Select an APK, calculate its SHA-256 identity, and inspect its bounded ZIP structure."
        )
        self.choose.clicked.connect(self._choose)
        layout.addWidget(self.choose)

        self.improve_inspection = QPushButton("Improve APK identity verification")
        self.improve_inspection.setToolTip(
            "Verify AAPT2 and APK Signer, then automatically repeat the local inspection of this exact APK."
        )
        self.improve_inspection.clicked.connect(self._resolve_inspection_tools)
        self.improve_inspection.setVisible(False)
        layout.addWidget(self.improve_inspection)

        self.approve = QPushButton("2  Review and approve exact plan")
        self.approve.setToolTip(
            "Bind your approval to this APK hash, safety evidence, and selected Android device."
        )
        self.approve.setEnabled(False)
        self.approve.clicked.connect(self._approve_or_resolve)
        layout.addWidget(self.approve)

        self.install_button = QPushButton("3  Install approved APK")
        self.install_button.setToolTip(
            "Revalidate the APK and device, pass the request through Guardian, and install with ADB."
        )
        self.install_button.setEnabled(False)
        self.install_button.clicked.connect(self._install)
        layout.addWidget(self.install_button)

        result = QFrame()
        result.setObjectName("Card")
        result_layout = QVBoxLayout(result)
        self.result_label = QLabel(
            "Choose an APK now. ROMVERSE can inspect it locally before a phone is connected."
        )
        self.result_label.setObjectName("Muted")
        self.result_label.setWordWrap(True)
        result_layout.addWidget(self.result_label)
        layout.addWidget(result)
        layout.addStretch(1)
        self._load_latest_review()

    def set_tool_statuses(self, statuses: tuple[ToolStatus, ...]) -> None:
        """Use only executables that Forge Arsenal has already verified."""
        self.aapt_executable = self._verified_tool(statuses, "AAPT2")
        self.apksigner_executable = self._verified_tool(statuses, "APK Signer")
        if hasattr(self, "improve_inspection"):
            self._sync_inspection_tool_action()

    @staticmethod
    def _verified_tool(statuses: tuple[ToolStatus, ...], name: str) -> Path | None:
        status = next(
            (item for item in statuses if item.name == name and item.available and item.path),
            None,
        )
        if status is None:
            return None
        path = Path(status.path).expanduser().resolve()
        return path if path.is_file() else None

    def set_install_service(self, service: ApkInstallService | None) -> None:
        """Activate a newly verified ADB runtime without trusting stale approval state."""
        self.install_service = service
        self.install_button.setEnabled(False)
        self._sync_approval_action()
        if service is not None and self.current_plan is not None and self.current_plan.safety_ready:
            self._set_result(
                "Verified Platform Tools are ready. Review and approve the exact device-bound "
                "APK plan to continue.",
                "Good",
            )

    def set_devices(self, devices: list[AndroidDevice]) -> None:
        previous = self._authorized_device()
        previous_serial = previous.serial if previous else ""
        self.devices = devices
        device = self._authorized_device()
        self.choose.setEnabled(self.active_worker is None)
        if device is None:
            self.device_label.setText("No authorized device selected")
            self.approve.setEnabled(False)
            self.approve.setText("2  Review and approve exact plan")
            self.install_button.setEnabled(False)
            if self.current_plan is not None:
                self.current_plan = None
                self._set_result(
                    "Phone disconnected. The local APK inspection is retained, but its "
                    "device-bound approval plan was safely cleared.",
                    "Warning",
                )
            elif self.current_inspection is not None and self.current_inspection.valid:
                self._set_result(
                    "Local inspection passed. Connect and authorize a phone; ROMVERSE will "
                    "automatically create a fresh device-bound safety plan.",
                    "Good",
                )
            return
        battery = f"{device.battery_percent}%" if device.battery_percent is not None else "unknown"
        self.device_label.setText(
            f"Target: {device.display_name}  •  {device.masked_serial()}  •  battery {battery}"
        )
        changed = (previous_serial and previous_serial != device.serial) or (
            self.current_plan and self.current_plan.request.device_serial != device.serial
        )
        evidence_refreshed = bool(
            self.current_plan
            and not self.current_plan.safety_ready
            and (
                self.current_plan.request.battery_percent != device.battery_percent
                or self.current_plan.request.device_free_bytes != device.storage.available_bytes
            )
        )
        if changed or evidence_refreshed:
            self._clear_plan(
                "ROMVERSE received newer device safety evidence. The old approval plan was "
                "cleared and the inspected APK is being checked again automatically."
                if evidence_refreshed
                else "Device changed. ROMVERSE cleared the old approval plan and is rebinding "
                "the inspected APK to the newly selected phone."
            )
        if (
            self.current_inspection is not None
            and self.current_inspection.valid
            and self.current_plan is None
            and self.active_worker is None
        ):
            self._bind_selected_to_device()
        elif self.current_plan is None and self.active_worker is None:
            self._set_result("Device ready. Choose an APK to begin Guardian inspection.", "Good")

    def _authorized_device(self) -> AndroidDevice | None:
        return next((item for item in self.devices if item.state is DeviceState.DEVICE), None)

    def _load_latest_review(self) -> None:
        loaded = self.receipts.load_latest_preflight()
        if not loaded.valid or loaded.data is None:
            if self.receipts.latest_preflight_path.exists():
                self._set_result(f"Previous APK review rejected: {loaded.reason}", "Danger")
            return
        data = loaded.data
        if not data.get("apk_name"):
            return
        self.file_label.setText(f"Last reviewed: {data['apk_name']}")
        digest = str(data.get("apk_sha256", ""))
        if digest:
            self.hash_label.setText(f"SHA-256: {digest}")
        integrity = "integrity verified" if loaded.integrity_verified else "legacy / unverified"
        self.result_label.setText(
            f"Previous review loaded for reference ({integrity}). Reselect the APK to create "
            "a fresh, device-bound install session."
        )

    def _choose(self) -> None:
        if self.active_worker is not None:
            return
        selected, _ = QFileDialog.getOpenFileName(
            self, "Choose APK", str(Path.home()), "Android APK (*.apk)"
        )
        if not selected:
            return
        self._start_inspection(Path(selected).expanduser().resolve())

    def _start_inspection(self, path: Path) -> None:
        self.current_plan = None
        self.current_inspection = None
        self.selected_apk_path = path
        self.approve.setEnabled(False)
        self.install_button.setEnabled(False)
        worker = ApkInspectionWorker(
            self.selected_apk_path,
            self.aapt_executable,
            self.apksigner_executable,
            self.runner,
        )
        worker.signals.complete.connect(self._inspection_ready)
        worker.signals.failed.connect(self._operation_failed)
        worker.signals.progress.connect(self.progress.report)
        self.active_worker = worker
        self._set_busy(
            "Inspecting APK locally and calculating SHA-256 with real byte progress…",
            determinate=True,
        )
        start_background(worker)

    def _sync_inspection_tool_action(self) -> None:
        inspection = self.current_inspection
        needs_tools = self.aapt_executable is None or self.apksigner_executable is None
        self.improve_inspection.setVisible(
            bool(
                inspection is not None
                and inspection.valid
                and needs_tools
                and self.active_worker is None
            )
        )

    def _resolve_inspection_tools(self) -> None:
        path = self.selected_apk_path
        if path is None or self.active_worker is not None:
            return
        self._set_result(
            "ROMVERSE is verifying AAPT2 and APK Signer for complete package identity and cryptographic signature evidence…",
            "Warning",
        )
        self.inspection_tools_requested.emit()
        if self.aapt_executable is None or self.apksigner_executable is None:
            self._set_result(
                "Complete APK identity tools remain unverified. The existing local inspection is retained and no phone action was started.",
                "Warning",
            )
            self._sync_inspection_tool_action()
            return
        self._start_inspection(path)

    @Slot(object)
    def _inspection_ready(self, inspection: ApkInspection) -> None:
        self.active_worker = None
        self.current_inspection = inspection
        self.selected_apk_path = Path(inspection.path)
        self.current_plan = None
        self._set_idle()
        self._show_inspection(inspection)
        self.approve.setEnabled(False)
        self.install_button.setEnabled(False)
        if not inspection.valid:
            self._set_result(
                "Local APK inspection failed. Guardian will not bind or install this file.",
                "Danger",
            )
            return
        if self._authorized_device() is None:
            self._set_result(
                "Local inspection passed. Connect and authorize a phone; ROMVERSE will "
                "automatically bind this exact APK hash to that device.",
                "Good",
            )
            return
        self._bind_selected_to_device()

    def _bind_selected_to_device(self) -> None:
        device = self._authorized_device()
        inspection = self.current_inspection
        if (
            device is None
            or inspection is None
            or not inspection.valid
            or self.active_worker is not None
        ):
            return
        request = ApkInstallRequest(
            inspection.path,
            device.serial,
            battery_percent=device.battery_percent,
            device_free_bytes=device.storage.available_bytes,
        )
        target_key = WorkspacePrivacy(self.workspace).pseudonym(device.serial)
        worker = ApkPlanWorker(
            request,
            target_key,
            self.aapt_executable,
            self.apksigner_executable,
            self.runner,
        )
        worker.signals.complete.connect(self._plan_ready)
        worker.signals.failed.connect(self._operation_failed)
        worker.signals.progress.connect(self.progress.report)
        self.active_worker = worker
        self._set_busy(
            f"Binding inspected APK to {device.display_name} and checking device safety evidence…",
            determinate=True,
        )
        start_background(worker)

    @Slot(object)
    def _plan_ready(self, plan: ApkInstallPlan) -> None:
        self.active_worker = None
        self.current_inspection = plan.inspection
        self.selected_apk_path = Path(plan.inspection.path)
        self._set_idle()
        device = self._authorized_device()
        if device is None or device.serial != plan.request.device_serial:
            self.current_plan = None
            self.approve.setEnabled(False)
            self.install_button.setEnabled(False)
            self._show_inspection(plan.inspection)
            self._set_result(
                "The target phone changed while ROMVERSE was checking it. The stale plan was "
                "discarded; a fresh device-bound check will run when the phone is ready.",
                "Warning",
            )
            if device is not None:
                self._bind_selected_to_device()
            return
        self.current_plan = plan
        inspection = plan.inspection
        self._show_inspection(inspection)
        self._sync_approval_action()
        self.install_button.setEnabled(False)
        if not inspection.valid:
            self._set_result("APK inspection failed. Guardian blocked this file.", "Danger")
        elif not plan.safety_ready:
            failed = [
                check.title
                for check in plan.manifest.preconditions
                if check.required and check.status.value != "pass"
            ]
            self._set_result(
                "Guardian needs more safety evidence before approval: " + ", ".join(failed),
                "Warning",
            )
        elif self.install_service is None:
            self._set_result(
                "APK passed inspection, but ADB execution is unavailable. Verify Platform Tools.",
                "Warning",
            )
        else:
            self._set_result(
                "APK and phone checks passed. Review the identity and approve this exact "
                "device-bound plan to continue.",
                "Good",
            )
        if not self._save_preflight(plan):
            self.approve.setEnabled(False)
            self.install_button.setEnabled(False)
            self._set_result(
                "APK inspection finished, but its tamper-evident preflight receipt could not "
                "be saved. Approval remains locked.",
                "Danger",
            )

    def _sync_approval_action(self) -> None:
        ready = bool(
            self.current_plan is not None
            and self.current_plan.safety_ready
            and self._authorized_device() is not None
            and self.active_worker is None
        )
        self.approve.setEnabled(ready)
        self.approve.setText(
            "2  Resolve Platform Tools"
            if ready and self.install_service is None
            else "2  Review and approve exact plan"
        )

    def _approve_or_resolve(self) -> None:
        if self.install_service is None:
            self.runtime_tools_requested.emit()
            if self.install_service is None:
                self._set_result(
                    "APK and phone checks passed, but Android Platform Tools remain unverified. "
                    "ROMVERSE kept approval locked and changed nothing on the phone.",
                    "Warning",
                )
            return
        self._approve()

    def _show_inspection(self, inspection: ApkInspection) -> None:
        identity = inspection.app_label or inspection.package_name or "Package identity unavailable"
        self.file_label.setText(
            f"Selected: {identity}  •  {Path(inspection.path).name}  •  "
            f"{inspection.file_size / 1024**2:.1f} MiB  •  "
            f"{inspection.entry_count:,} entries"
        )
        package_line = (
            f"Package: {inspection.package_name}  •  version "
            f"{inspection.version_name or 'unknown'} ({inspection.version_code or 'unknown'})"
            if inspection.package_name
            else "Package: not decoded — verify AAPT2 in Forge Arsenal for full identity"
        )
        sdk_line = (
            f"Android SDK: minimum {inspection.min_sdk or 'unknown'}  •  "
            f"target {inspection.target_sdk or 'unknown'}  •  "
            f"permissions declared {inspection.permission_count if inspection.permission_count is not None else 'unknown'}"
        )
        abi_line = (
            "Native ABI: " + ", ".join(inspection.native_abis)
            if inspection.native_abis
            else "Native ABI: none declared or not decoded"
        )
        signature_line = (
            f"Signature: VERIFIED  •  signer SHA-256 {inspection.signer_sha256}"
            if inspection.signature_verified is True
            else "Signature: FAILED verification"
            if inspection.signature_verified is False
            else "Signature: not cryptographically checked — verify APK Signer in Forge Arsenal"
        )
        self.hash_label.setText(
            f"SHA-256: {inspection.sha256}\n"
            f"{package_line}\n{sdk_line}\n{abi_line}\n{signature_line}\n"
            f"Manifest: {'found' if inspection.has_manifest else 'missing'}  •  "
            f"DEX files: {inspection.dex_count}  •  "
            f"signature metadata: {'found' if inspection.has_legacy_signature else 'not visible'}"
        )
        self.command_label.setText("\n".join(inspection.findings))
        self._sync_inspection_tool_action()

    def _approve(self) -> None:
        plan = self.current_plan
        device = self._authorized_device()
        if plan is None or device is None or not plan.safety_ready or self.install_service is None:
            return
        if device.serial != plan.request.device_serial:
            self._clear_plan("Selected device changed. Inspect the APK again.")
            return
        answer = QMessageBox.question(
            self,
            "Confirm Guardian approval",
            f"Approve this exact install?\n\n"
            f"APK: {Path(plan.inspection.path).name}\n"
            f"Package: {plan.inspection.package_name or 'not decoded'}\n"
            f"Version: {plan.inspection.version_name or 'unknown'} ({plan.inspection.version_code or 'unknown'})\n"
            f"Signer SHA-256: {plan.inspection.signer_sha256 or 'not cryptographically checked'}\n"
            f"SHA-256: {plan.inspection.sha256[:20]}…\n"
            f"Device: {device.display_name} ({device.masked_serial()})\n\n"
            "ROMVERSE will recheck the file and device before ADB runs.",
        )
        if answer is not QMessageBox.StandardButton.Yes:
            return
        record = ApprovalStore(self.workspace).issue(plan.digest, plan.target_key)
        self._set_result(
            f"Guardian approval recorded  •  {record.approval_id[:12]}…  •  ready to install.",
            "Good",
        )
        self.approve.setEnabled(False)
        self.install_button.setEnabled(True)
        self.install_button.setObjectName("Primary")
        self.install_button.style().unpolish(self.install_button)
        self.install_button.style().polish(self.install_button)

    def _install(self) -> None:
        plan = self.current_plan
        device = self._authorized_device()
        if (
            plan is None
            or device is None
            or self.install_service is None
            or self.active_worker is not None
        ):
            return
        if device.serial != plan.request.device_serial:
            self._clear_plan("Selected device changed. Guardian cancelled the install.")
            return
        answer = QMessageBox.warning(
            self,
            "Install APK on phone",
            f"Install {Path(plan.inspection.path).name} on {device.display_name}?\n\n"
            "This changes the phone's application state. Do not disconnect USB until ROMVERSE finishes.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            return
        worker = ApkInstallWorker(self.install_service, plan)
        worker.signals.complete.connect(self._install_complete)
        worker.signals.failed.connect(self._operation_failed)
        self.active_worker = worker
        self._set_busy("Installing through Guardian… Do not disconnect the phone.")
        start_background(worker)

    @Slot(object)
    def _install_complete(self, result: CommandResult) -> None:
        self.active_worker = None
        self._set_idle()
        success = install_succeeded(result)
        receipt_saved = self._save_install_receipt(result, success)
        self.install_button.setEnabled(not success)
        if success:
            if receipt_saved:
                self._set_result(
                    "Installation complete. ADB returned Success and Guardian recorded the operation.",
                    "Good",
                )
                QMessageBox.information(
                    self,
                    "APK installed",
                    "The approved APK was installed successfully. A privacy-safe, integrity-verified receipt was saved locally.",
                )
            else:
                self._set_result(
                    "ADB returned Success, but the local result receipt could not be saved. "
                    "Guardian's operation audit remains authoritative; review disk access before continuing.",
                    "Warning",
                )
                QMessageBox.warning(
                    self,
                    "APK installed — receipt attention required",
                    "Android reported a successful install, but ROMVERSE could not save the local result receipt.",
                )
            return
        detail = (result.stderr or result.stdout or "ADB did not return Success").strip()[-600:]
        self._set_result(f"Installation failed safely: {detail}", "Danger")
        QMessageBox.warning(self, "APK installation failed", detail)

    @Slot(str)
    def _operation_failed(self, message: str) -> None:
        self.active_worker = None
        self._set_idle()
        self.install_button.setEnabled(
            self.current_plan is not None
            and ApprovalStore(self.workspace).is_approved(
                self.current_plan.digest, self.current_plan.target_key
            )
        )
        self._set_result(f"Guardian stopped the operation: {message}", "Danger")

    def _set_busy(self, message: str, *, determinate: bool = False) -> None:
        self.progress.begin(determinate=determinate)
        self.choose.setEnabled(False)
        self.improve_inspection.setEnabled(False)
        self.approve.setEnabled(False)
        self.install_button.setEnabled(False)
        self._set_result(message, "Warning")

    def _set_idle(self) -> None:
        self.progress.stop()
        self.choose.setEnabled(True)
        self.improve_inspection.setEnabled(True)
        self._sync_inspection_tool_action()

    def _set_result(self, text: str, object_name: str) -> None:
        self.result_label.setText(text)
        self.result_label.setObjectName(object_name)
        self.result_label.style().unpolish(self.result_label)
        self.result_label.style().polish(self.result_label)

    def _clear_plan(self, message: str) -> None:
        self.current_plan = None
        self.approve.setEnabled(False)
        self.approve.setText("2  Review and approve exact plan")
        self.install_button.setEnabled(False)
        self._set_result(message, "Warning")

    def _save_preflight(self, plan: ApkInstallPlan) -> bool:
        try:
            self.receipts.write_preflight(plan)
        except OSError:
            return False
        return True

    def _save_install_receipt(self, result: CommandResult, success: bool) -> bool:
        if self.current_plan is None:
            return False
        try:
            self.receipts.write_install(self.current_plan, result, success)
        except OSError:
            return False
        if self.activity_store is not None:
            with suppress(ActivityStoreError):
                self.activity_store.record(
                    "applications",
                    "APK installation completed" if success else "APK installation failed safely",
                    f"{Path(self.current_plan.inspection.path).name} • Guardian receipt recorded",
                    outcome="success" if success else "attention",
                    source="App Launchpad",
                )
        return True
