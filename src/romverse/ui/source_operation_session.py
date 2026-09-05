"""Application-owned lifecycle for one exact source or rebuilt-ROM installation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from threading import Event

from PySide6.QtCore import QObject, QTimer, Signal, Slot

import romverse.ui.local_flash as local_flash_ui
from romverse.device.models import AndroidDevice
from romverse.guardian.local_transition import (
    LocalTransitionPlan,
    LocalTransitionResult,
    LocalTransitionTarget,
)
from romverse.guardian.source_installation import (
    SourceInstallationPlan,
    SourceInstallationResult,
)
from romverse.rom.candidate_installation import CandidateInstallationRecipe
from romverse.rom.local_boot import LocalBootReport, LocalBootSession
from romverse.ui.background import ManagedRunnable
from romverse.ui.local_flash import (
    LocalBootWorker,
    LocalFlashDiscoveryWorker,
    LocalFlashSignals,
    LocalTransitionWorker,
)


class SourceOperationPhase(StrEnum):
    READY = "ready"
    REFRESHING = "refreshing"
    REVIEWING = "reviewing"
    REVIEW_READY = "review-ready"
    INSTALLING = "installing"
    TRANSITION_REVIEWING = "transition-reviewing"
    TRANSITION_READY = "transition-ready"
    TRANSITIONING = "transitioning"
    BOOT_CHECKING = "boot-checking"
    COMPLETED = "completed"
    ATTENTION = "attention"


@dataclass(frozen=True, slots=True)
class SourceOperationSnapshot:
    revision: int
    phase: SourceOperationPhase
    status: str
    details: str
    progress_value: int
    progress_total: int
    progress_indeterminate: bool
    progress_format: str
    selected_serial: str
    busy: bool
    writing: bool
    monitoring: bool
    stop_requested: bool
    plan_digest: str
    can_review: bool
    can_install: bool
    can_refresh: bool
    can_change_mode: bool
    can_check_boot: bool
    recovery_available: bool


@dataclass(frozen=True, slots=True)
class SourceTransitionReview:
    revision: int
    plan: LocalTransitionPlan
    device: AndroidDevice
    target: LocalTransitionTarget


class SourceInstallationWorker(ManagedRunnable):
    def __init__(self, service, device, recipe, *, plan=None):
        super().__init__()
        self.service = service
        self.device = device
        self.recipe = recipe
        self.plan = plan
        self.cancel_requested = Event()
        self.signals = LocalFlashSignals()

    def execute(self):
        try:
            value = (
                self.service.inspect(self.device, self.recipe)
                if self.plan is None
                else self.service.execute(
                    self.plan,
                    accepted_digest=self.plan.plan_digest,
                    risk_accepted=True,
                    should_cancel=self.cancel_requested.is_set,
                    progress=self.signals.progress.emit,
                )
            )
            self.signals.complete.emit(value)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class SourceOperationSession(QObject):
    """Own workers and evidence independently of any Guided or Expert view."""

    changed = Signal(object)
    transition_review_ready = Signal(object)
    operation_finished = Signal(object)
    transition_finished = Signal(object)
    boot_finished = Signal(object)
    recovery_required = Signal()
    quiescent = Signal()

    def __init__(
        self,
        service,
        devices,
        *,
        recipe,
        discover=None,
        transition_service=None,
        boot_service=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.devices = tuple(devices)
        self.recipe = recipe
        self.preparation = recipe
        self.discover = discover
        self.transition_service = transition_service
        self.boot_service = boot_service
        self.selected_serial = self.devices[0].serial if self.devices else ""
        self.revision = 0
        self.phase = SourceOperationPhase.READY
        self.status = self._ready_status()
        self.details = ""
        self.progress_value = 0
        self.progress_total = 100
        self.progress_indeterminate = False
        self.progress_format = "%p%"
        self.plan: SourceInstallationPlan | None = None
        self.result: SourceInstallationResult | None = None
        self.worker: (
            SourceInstallationWorker
            | LocalFlashDiscoveryWorker
            | LocalTransitionWorker
            | LocalBootWorker
            | None
        ) = None
        self.execution_error = ""
        self.last_attempt_device: AndroidDevice | None = None
        self.last_flash_device: AndroidDevice | None = None
        self.transition_result: LocalTransitionResult | None = None
        self.transition_error = ""
        self.transition_attempt_device: AndroidDevice | None = None
        self.transition_review: SourceTransitionReview | None = None
        self.boot_session: LocalBootSession | None = None
        self.boot_report: LocalBootReport | None = None
        self.boot_device: AndroidDevice | None = None
        self.boot_error = ""
        self.monitoring = False
        self._boot_stop_requested = False
        self.recovery_requested = False
        self.boot_timer = QTimer(self)
        self.boot_timer.setSingleShot(True)
        self.boot_timer.setInterval(5000)
        self.boot_timer.timeout.connect(self._poll_boot)

    @property
    def busy(self) -> bool:
        return self.worker is not None or self.monitoring

    @property
    def writing(self) -> bool:
        return isinstance(self.worker, SourceInstallationWorker) and self.worker.plan is not None

    @property
    def stop_requested(self) -> bool:
        return self._boot_stop_requested or bool(
            self.worker is not None
            and hasattr(self.worker, "cancel_requested")
            and self.worker.cancel_requested.is_set()
        )

    @property
    def identity(self) -> tuple[str, str, str]:
        return (
            self.recipe.project_id,
            self.recipe.source_sha256,
            self.recipe.script_sha256,
        )

    def matches(self, project_id: str, source_sha256: str) -> bool:
        return self.identity[:2] == (project_id, source_sha256)

    def snapshot(self) -> SourceOperationSnapshot:
        selected = self.selected_device()
        plan_digest = self.plan.plan_digest if self.plan is not None else ""
        recoverable = bool(
            self.execution_error
            or self.transition_error
            or self.boot_error
            or (self.boot_report is not None and self.boot_report.status == "attention")
            or (
                self.result is not None
                and self.result.phone_change_attempted
                and self.result.state != "completed"
            )
        )
        can_retry_read_only_review = (
            self.phase is SourceOperationPhase.ATTENTION and not recoverable
        )
        preparation_open = self.phase in {
            SourceOperationPhase.READY,
            SourceOperationPhase.REVIEW_READY,
        } or can_retry_read_only_review
        needs_android_return = bool(
            self.phase is SourceOperationPhase.COMPLETED
            and self.result is not None
            and self.result.state == "completed"
            and not self.result.reboot_requested
            and self.boot_report is None
        )
        return SourceOperationSnapshot(
            revision=self.revision,
            phase=self.phase,
            status=self.status,
            details=self.details,
            progress_value=self.progress_value,
            progress_total=self.progress_total,
            progress_indeterminate=self.progress_indeterminate,
            progress_format=self.progress_format,
            selected_serial=self.selected_serial,
            busy=self.busy,
            writing=self.writing,
            monitoring=self.monitoring,
            stop_requested=self.stop_requested,
            plan_digest=plan_digest,
            can_review=(
                not self.busy
                and selected is not None
                and self.plan is None
                and (
                    self.phase is SourceOperationPhase.READY
                    or can_retry_read_only_review
                )
            ),
            can_install=not self.busy and self.plan is not None,
            can_refresh=(
                not self.busy and self.discover is not None and preparation_open
            ),
            can_change_mode=(
                not self.busy
                and selected is not None
                and self.transition_service is not None
                and (preparation_open or needs_android_return)
            ),
            can_check_boot=(
                not self.busy and selected is not None and self.boot_service is not None
            ),
            recovery_available=not self.busy and recoverable,
        )

    def selected_device(self) -> AndroidDevice | None:
        return next(
            (item for item in self.devices if item.serial == self.selected_serial),
            None,
        )

    def select_device(self, serial: str) -> bool:
        if self.busy or serial == self.selected_serial:
            return False
        if serial and not any(item.serial == serial for item in self.devices):
            return False
        self.selected_serial = serial
        self._invalidate_review("Review this phone before installation.")
        return True

    def review_installation(self) -> bool:
        device = self.selected_device()
        if self.busy or device is None:
            return False
        self._invalidate_review("Verifying the package, exact phone and every declared write…")
        self.phase = SourceOperationPhase.REVIEWING
        self.progress_indeterminate = True
        return self._start(SourceInstallationWorker(self.service, device, self.recipe))

    def accept_installation(self, revision: int, plan_digest: str) -> bool:
        plan = self.plan
        device = self.selected_device()
        if self.busy:
            return False
        if (
            plan is None
            or device is None
            or revision != self.revision
            or plan_digest != plan.plan_digest
        ):
            self.status = "The target or plan changed. Review again before confirming."
            self._emit_changed()
            return False
        self.result = None
        self.execution_error = ""
        self.last_attempt_device = device
        self.last_flash_device = device
        self.boot_report = None
        self.boot_error = ""
        self.phase = SourceOperationPhase.INSTALLING
        self.status = "Preserving the reviewed images, then running the exact confirmed sequence…"
        self.progress_indeterminate = False
        self.progress_value = 0
        self.progress_total = max(1, len(self.recipe.steps))
        self.progress_format = "%v / %m declared actions completed"
        return self._start(SourceInstallationWorker(self.service, device, self.recipe, plan=plan))

    def refresh_devices(self) -> bool:
        if self.busy or self.discover is None:
            return False
        self._invalidate_review("Checking connected phones…")
        self.phase = SourceOperationPhase.REFRESHING
        self.progress_indeterminate = True
        return self._start(LocalFlashDiscoveryWorker(self.discover))

    def review_transition(self, target: LocalTransitionTarget) -> bool:
        device = self.selected_device()
        if self.busy or device is None or self.transition_service is None:
            return False
        identity = device.codename or device.product
        if identity.casefold() != self.recipe.expected_product.casefold():
            self.status = "Identify the exact intended device before preparing a mode change."
            self._emit_changed()
            return False
        self._invalidate_review(
            "Checking the selected phone before preparing a mode change…"
        )
        self.phase = SourceOperationPhase.TRANSITION_REVIEWING
        self.progress_indeterminate = True
        return self._start(LocalTransitionWorker(self.transition_service, device, target))

    def accept_transition(self, review: SourceTransitionReview) -> bool:
        selected = self.selected_device()
        current = self.transition_review
        if self.busy:
            return False
        if (
            current is None
            or review != current
            or review.revision != self.revision
            or selected is None
            or selected.serial != review.device.serial
        ):
            self.status = "The target or requested mode changed. Prepare the mode change again."
            self._emit_changed()
            return False
        self.transition_error = ""
        self.transition_result = None
        self.transition_attempt_device = selected
        self.last_attempt_device = selected
        self.boot_report = None
        self.boot_error = ""
        self.transition_review = None
        self.phase = SourceOperationPhase.TRANSITIONING
        self.status = "Rechecking the exact phone, then waiting for its requested mode…"
        self.progress_indeterminate = True
        return self._start(
            LocalTransitionWorker(
                self.transition_service,
                selected,
                review.target,
                plan=review.plan,
            )
        )

    def check_boot(self) -> bool:
        device = self.selected_device()
        return self._start_boot(device) if device is not None else False

    def request_stop(self) -> bool:
        worker = self.worker
        if self.monitoring:
            self.boot_timer.stop()
            self._boot_stop_requested = True
            self.status = "Stopping boot monitoring after the current read-only check…"
            if worker is None:
                self._poll_boot()
            self._emit_changed()
            return True
        if isinstance(worker, SourceInstallationWorker) and worker.plan is not None:
            worker.cancel_requested.set()
            self.status = (
                "Stop requested. The current action will finish; completed changes cannot be undone "
                "automatically."
            )
            self._emit_changed()
            return True
        if isinstance(worker, LocalTransitionWorker) and worker.plan is not None:
            worker.cancel_requested.set()
            self.status = (
                "Stop requested. A reboot already sent cannot be undone; ROMVERSE will recheck the "
                "phone afterward."
            )
            self._emit_changed()
            return True
        return False

    def request_recovery(self) -> bool:
        if self.busy or not self.snapshot().recovery_available:
            return False
        self.recovery_requested = True
        self.recovery_required.emit()
        self._emit_changed()
        return True

    def dispose(self) -> None:
        """Release an idle historical session; never stop live work implicitly."""
        if self.busy:
            raise RuntimeError("A live installation session cannot be discarded")
        self.boot_timer.stop()

    def _ready_status(self) -> str:
        return (
            f"{len(self.recipe.steps)} declared actions · target slot "
            f"{self.recipe.target_slot.upper()}. Review performs only read-only checks."
        )

    def _invalidate_review(self, status: str) -> None:
        self.revision += 1
        self.plan = None
        self.transition_review = None
        self.details = ""
        self.status = status
        self.progress_value = 0
        self.progress_total = 100
        self.progress_indeterminate = False
        self.progress_format = "%p%"
        self.phase = SourceOperationPhase.READY
        self._emit_changed()

    def _start(self, worker) -> bool:
        if self.worker is not None:
            return False
        self.worker = worker
        worker.signals.complete.connect(self._receive_complete)
        worker.signals.failed.connect(self._receive_failed)
        worker.signals.progress.connect(self._receive_progress)
        self._emit_changed()
        try:
            local_flash_ui.start_background(worker)
        except RuntimeError as exc:
            self._failed(str(exc))
            return False
        return True

    @Slot(object)
    def _receive_complete(self, value: object) -> None:
        if self.worker is not None and self.sender() is self.worker.signals:
            self._complete(value)

    @Slot(str)
    def _receive_failed(self, message: str) -> None:
        if self.worker is not None and self.sender() is self.worker.signals:
            self._failed(message)

    @Slot(int, int, str)
    def _receive_progress(self, done: int, total: int, message: str) -> None:
        if self.worker is None or self.sender() is not self.worker.signals:
            return
        self.progress_indeterminate = False
        self.progress_total = max(1, total)
        self.progress_value = done
        self.status = message
        self._emit_changed()

    def _complete(self, value: object) -> None:
        finished = self.worker
        if finished is None:
            return
        stop_requested = bool(
            hasattr(finished, "cancel_requested")
            and finished.cancel_requested.is_set()
        )
        self.worker = None
        if isinstance(finished, LocalBootWorker):
            if isinstance(value, LocalBootReport):
                self.boot_session = finished.session
                self._complete_boot(value)
            else:
                self.worker = finished
                self._failed(
                    "The boot observer returned an unsupported result. No boot success was accepted."
                )
            return
        if isinstance(value, SourceInstallationPlan) and isinstance(
            finished, SourceInstallationWorker
        ):
            self.plan = value
            self.phase = SourceOperationPhase.REVIEW_READY
            self.details = self._installation_review(value)
            self.status = "Ready to install. Review the meaningful risks, then confirm once."
            self.progress_indeterminate = False
            self.progress_value = 100
            self.progress_total = 100
            self.progress_format = "Preparation verified"
            self._emit_changed()
            return
        if isinstance(value, SourceInstallationResult) and isinstance(
            finished, SourceInstallationWorker
        ):
            self.plan = None
            self.result = value
            self.details = self._installation_result(value)
            self.status = value.summary
            self.progress_indeterminate = False
            self.progress_total = max(1, len(self.recipe.steps))
            self.progress_value = value.completed_count
            self.progress_format = "%v / %m declared actions completed · boot separate"
            self.operation_finished.emit(value)
            if value.observed_device is not None:
                self._adopt_device(value.observed_device)
            if (
                value.state == "completed"
                and value.reboot_requested
                and self.boot_service is not None
                and not stop_requested
            ):
                self._start_boot(value.observed_device or self.last_flash_device)
                return
            self.phase = (
                SourceOperationPhase.COMPLETED
                if value.state == "completed"
                else SourceOperationPhase.ATTENTION
            )
            if stop_requested and value.state == "completed":
                self.status = (
                    value.summary
                    + " Boot monitoring was not started because you requested Stop. Choose Check "
                    "Android boot when ready."
                )
            if value.phone_change_attempted and value.state != "completed":
                self.recovery_requested = True
                self.recovery_required.emit()
            self._finish_quiescent()
            return
        if isinstance(value, LocalTransitionPlan) and isinstance(
            finished, LocalTransitionWorker
        ):
            self.phase = SourceOperationPhase.TRANSITION_READY
            self.progress_indeterminate = False
            self.progress_value = 0
            self.transition_review = SourceTransitionReview(
                self.revision,
                value,
                finished.device,
                finished.target,
            )
            self.status = "Mode change is ready for one confirmation."
            self._emit_changed()
            self.transition_review_ready.emit(self.transition_review)
            return
        if isinstance(value, LocalTransitionResult) and isinstance(
            finished, LocalTransitionWorker
        ):
            self.transition_result = value
            self.transition_finished.emit(value)
            self.status = value.summary
            self.details = self._append_detail(
                f"MODE CHANGE  {value.summary}\nReceipt: {value.receipt_path}"
            )
            if value.observed_device is not None:
                self._adopt_device(value.observed_device)
            if value.state != "completed" and value.phone_change_attempted:
                self.transition_error = value.summary
                self.recovery_requested = True
            if (
                (value.state == "completed" or value.command_completed)
                and value.state != "cancelled"
                and finished.target is LocalTransitionTarget.ANDROID
                and self.boot_service is not None
            ):
                self._start_boot(value.observed_device or finished.device)
                return
            if value.state == "completed" and finished.target is not LocalTransitionTarget.ANDROID:
                self.phase = SourceOperationPhase.READY
                self.status = value.summary + " Continue with installation preparation."
            else:
                self.phase = (
                    SourceOperationPhase.COMPLETED
                    if value.state == "completed"
                    else SourceOperationPhase.ATTENTION
                )
            if self.recovery_requested:
                self.recovery_required.emit()
            self._finish_quiescent()
            return
        if isinstance(value, tuple) and all(isinstance(item, AndroidDevice) for item in value):
            previous = self.selected_serial
            self.devices = value
            self.selected_serial = (
                previous
                if any(item.serial == previous for item in value)
                else value[0].serial
                if value
                else ""
            )
            self.status = (
                "Choose the intended phone, then review the installation."
                if value
                else "No phone detected. Connect it in Android, Fastboot or fastbootd and refresh."
            )
            self.phase = SourceOperationPhase.READY
            self.progress_indeterminate = False
            self._emit_changed()
            return
        self.worker = finished
        self._failed("The operation returned an unsupported result. Recheck the phone state.")

    def _failed(self, message: str) -> None:
        worker = self.worker
        changing = False
        if isinstance(worker, SourceInstallationWorker) and worker.plan is not None:
            self.result = None
            self.execution_error = message
            changing = True
        elif isinstance(worker, LocalTransitionWorker) and worker.plan is not None:
            self.transition_error = message
            changing = True
        elif isinstance(worker, LocalBootWorker):
            self.boot_error = message
            self.monitoring = False
            self.boot_timer.stop()
            changing = True
        self.worker = None
        self.plan = None
        self.phase = SourceOperationPhase.ATTENTION
        self.progress_indeterminate = False
        self.progress_value = 0
        self.progress_total = 100
        self.status = message
        self.details = self._append_detail(f"Operation stopped: {message}")
        if changing:
            self.recovery_requested = True
            self.recovery_required.emit()
        self._finish_quiescent()

    def _start_boot(self, device: AndroidDevice | None) -> bool:
        if (
            device is None
            or self.boot_service is None
            or self.worker is not None
            or self.monitoring
        ):
            return False
        self.revision += 1
        self.plan = None
        self.transition_review = None
        self.monitoring = True
        self._boot_stop_requested = False
        self.boot_session = None
        self.boot_report = None
        self.boot_error = ""
        linked = (
            self.result
            if (
                self.result is not None
                and self.result.state == "completed"
                and self.last_flash_device is not None
                and self.last_flash_device.serial == device.serial
            )
            else None
        )
        baseline = self.last_flash_device if linked is not None else device
        self.boot_device = baseline
        self.phase = SourceOperationPhase.BOOT_CHECKING
        self.status = "Starting Android and measuring a stable boot interval…"
        self.progress_indeterminate = True
        return self._start(LocalBootWorker(self.boot_service, baseline, flash_result=linked))

    @Slot()
    def _poll_boot(self) -> None:
        if not self.monitoring or self.worker is not None or self.boot_session is None:
            return
        self._start(
            LocalBootWorker(
                self.boot_service,
                self.boot_device,
                session=self.boot_session,
                stop=self._boot_stop_requested,
            )
        )

    def _complete_boot(self, report: LocalBootReport) -> None:
        if (
            report.latest_device is not None
            and self.boot_device is not None
            and report.latest_device.serial != self.boot_device.serial
        ):
            self.boot_error = (
                "The boot check returned another phone's observations. No boot success was accepted."
            )
            self.monitoring = False
            self.boot_timer.stop()
            self._failed(self.boot_error)
            return
        self.boot_report = report
        self.status = report.summary
        if report.latest_device is not None:
            self._adopt_device(report.latest_device)
        self.details = self._boot_details(report)
        if not report.terminal:
            self.progress_indeterminate = True
            if self._boot_stop_requested:
                self._poll_boot()
            else:
                self.boot_timer.start()
                self._emit_changed()
            return
        self.monitoring = False
        self.boot_timer.stop()
        stable = report.status == "stable" and report.boot_observed
        self.progress_indeterminate = False
        self.progress_value = 100 if stable else 0
        self.progress_total = 100
        self.progress_format = "Observed boot window complete" if stable else "Boot check ended"
        if (
            stable
            and self.transition_attempt_device is not None
            and self.boot_device is not None
            and self.transition_attempt_device.serial == self.boot_device.serial
        ):
            self.transition_error = ""
        self.phase = SourceOperationPhase.COMPLETED if stable else SourceOperationPhase.ATTENTION
        self.boot_finished.emit(report)
        if report.status == "attention":
            self.recovery_requested = True
            self.recovery_required.emit()
        self._finish_quiescent()

    def _adopt_device(self, observed: AndroidDevice) -> None:
        index = next(
            (i for i, item in enumerate(self.devices) if item.serial == observed.serial),
            None,
        )
        if index is None:
            return
        devices = list(self.devices)
        devices[index] = observed
        self.devices = tuple(devices)

    def _finish_quiescent(self) -> None:
        self._emit_changed()
        self.quiescent.emit()

    def _emit_changed(self) -> None:
        self.changed.emit(self.snapshot())

    def _append_detail(self, text: str) -> str:
        return f"{self.details}\n\n{text}".strip()

    def _installation_review(self, value: SourceInstallationPlan) -> str:
        lines = [
            f"TARGET  {value.device_name} · {value.masked_serial}",
            f"PRODUCT  {value.product} · CURRENT SLOT  {value.current_slot}",
            f"PROJECT  {value.recipe.project_id}",
            f"SOURCE SHA-256  {value.recipe.source_sha256}",
            f"DECLARATION SHA-256  {value.recipe.script_sha256}",
            f"PLAN  {value.plan_digest}",
            "",
            "DATA  "
            + (
                "ERASE metadata and userdata"
                if value.recipe.wipe
                else "No data erase requested · data preservation and compatibility unproven"
            ),
            "FINISH  "
            + (
                "Restart Android and measure boot"
                if value.recipe.reboot
                else "Stay in bootloader"
            ),
            "",
        ]
        if isinstance(value.recipe, CandidateInstallationRecipe):
            lines.extend(
                (
                    f"BASE PACKAGE SHA-256  {value.recipe.procedure_source_sha256}",
                    f"BUILD RECEIPT  {value.recipe.build_receipt_digest}",
                    f"COMPOSITION  {value.recipe.composition_digest}",
                    "SCOPE  2 rebuilt images + 48 exact-base images; local unlocked experimental, not OEM-trusted.",
                    "",
                )
            )
        images = {item.member: item for item in value.recipe.images}
        for index, step in enumerate(value.recipe.steps, 1):
            lines.append(f"{index}. {step.action} {step.partition or step.slot or 'Android'}")
            if step.action == "flash":
                image = images[step.image_member]
                lines.extend((f"   {image.member}", f"   SHA-256: {image.sha256}"))
                if step.chunk_size:
                    lines.append(f"   Transfer chunk limit: {step.chunk_size}")
        lines.extend(("", "WARNINGS", *value.warnings))
        return "\n".join(lines)

    def _installation_result(self, value: SourceInstallationResult) -> str:
        lines = [
            f"RESULT  {value.state}",
            value.summary,
            f"Receipt: {value.receipt_path}",
        ]
        for step in value.results:
            lines.extend(
                ("", f"{step.action} {step.partition} · exit {step.returncode}", step.output)
            )
        return "\n".join(lines)

    def _boot_details(self, report: LocalBootReport) -> str:
        lines = [
            f"ANDROID BOOT CHECK  ·  {report.status}",
            report.summary,
            "",
            f"Samples: {report.sample_count} · Elapsed: {report.elapsed_seconds:.0f} seconds",
            "This read-only observation is not image readback, a full subsystem test, or a public release certification.",
            "",
            f"Receipt: {report.receipt_path}",
        ]
        if report.latest_device is not None:
            observed = report.latest_device
            lines.extend(
                (
                    "",
                    "MEASURED PHONE",
                    f"Product: {observed.product} · Device: {observed.codename}",
                    f"Android: {observed.android_version or 'Not reported'} · Build: {observed.build_id or 'Not reported'}",
                    f"Slot: {observed.slot_suffix or 'Not reported'} · Uptime: {observed.uptime_seconds} seconds",
                    f"Build fingerprint: {observed.build_fingerprint or 'Not reported'}",
                )
            )
        return "\n".join(lines)


__all__ = [
    "SourceInstallationWorker",
    "SourceOperationPhase",
    "SourceOperationSession",
    "SourceOperationSnapshot",
    "SourceTransitionReview",
]
