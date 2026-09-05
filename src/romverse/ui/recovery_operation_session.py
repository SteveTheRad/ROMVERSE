"""Application-owned continuation for one governed Recovery execution result.

The session owns no adapter or device-command surface. It only carries an already
durable exact result through reassessment, read-only boot observation, and the
independent same-incident verification boundary.
"""

from __future__ import annotations

import hmac
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from PySide6.QtCore import QObject, Signal

from romverse.device.models import AndroidDevice, DeviceState
from romverse.guardian.recovery_execution_result import (
    GuardianRecoveryExecutionResult,
    GuardianRecoveryExecutionResultService,
    RecoveryExecutionResultState,
)
from romverse.guardian.recovery_preparation import GuardianRecoveryPreparation
from romverse.repair.autopilot import (
    RecoveryAutopilotError,
    RecoveryAutopilotService,
    RecoveryIncident,
    RecoveryIncidentState,
)
from romverse.rom.boot_observation import (
    BootObservationReceipt,
    BootObservationService,
    BootObservationStatus,
)
from romverse.rom.models import ProjectError


class RecoveryOperationSessionError(RuntimeError):
    """The app could not preserve the exact governed Recovery continuation."""


class RecoveryOperationPhase(StrEnum):
    WAITING_FOR_ANDROID = "waiting-for-android"
    OBSERVING_BOOT = "observing-boot"
    VERIFIED = "verified"
    STOPPED_FAILED = "stopped-failed"
    STOPPED_UNKNOWN = "stopped-unknown"
    ATTENTION = "attention"


@dataclass(frozen=True, slots=True)
class RecoveryOperationSnapshot:
    revision: int
    phase: RecoveryOperationPhase
    status: str
    details: str
    incident_id: str
    project_id: str
    device_key: str
    result_digest: str
    result_state: RecoveryExecutionResultState
    incident_state: RecoveryIncidentState
    boot_observation_digest: str
    boot_status: str
    waiting_for_exact_device: bool
    can_observe: bool
    recovered: bool
    terminal: bool
    execution_authority: str
    automatic_retry_allowed: bool
    bootloader_relock_allowed: bool


class RecoveryOperationSession(QObject):
    """Retain one exact Recovery continuation independently of its presentation."""

    changed = Signal(object)
    MAX_SCAN_DEVICES = 64

    def __init__(
        self,
        preparation: GuardianRecoveryPreparation,
        execution_results: GuardianRecoveryExecutionResultService,
        autopilot: RecoveryAutopilotService,
        boot_observations: BootObservationService,
        *,
        clock: Callable[[], datetime] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if (
            not isinstance(preparation, GuardianRecoveryPreparation)
            or not isinstance(execution_results, GuardianRecoveryExecutionResultService)
            or not isinstance(autopilot, RecoveryAutopilotService)
            or not isinstance(boot_observations, BootObservationService)
            or execution_results.store.workspace.resolve() != autopilot.workspace.resolve()
            or boot_observations.store.workspace.resolve() != autopilot.workspace.resolve()
            or boot_observations.registry is not autopilot.registry
        ):
            raise RecoveryOperationSessionError(
                "Recovery continuation requires one exact local evidence context"
            )
        result = execution_results.load(preparation)
        if result is None:
            raise RecoveryOperationSessionError(
                "Recovery continuation requires the exact durable execution result"
            )
        try:
            incident = autopilot.reassess_execution(preparation, execution_results)
        except (OSError, ProjectError, RecoveryAutopilotError) as exc:
            raise RecoveryOperationSessionError(
                "Recovery continuation could not validate the same incident reassessment"
            ) from exc
        if (
            incident.incident_id != result.incident_id
            or incident.project_id != result.project_id
            or not hmac.compare_digest(incident.device_key, result.device_key)
            or incident.pack_id != result.device_pack_id
            or not hmac.compare_digest(incident.pack_sha256, result.device_pack_sha256)
            or incident.phone_changed
            or incident.routes
            or result.execution_authority != "none"
            or result.automatic_retry_allowed is not False
            or result.bootloader_relock_allowed is not False
        ):
            raise RecoveryOperationSessionError(
                "Recovery continuation no longer matches its exact sealed result"
            )
        self.preparation = preparation
        self.execution_results = execution_results
        self.autopilot = autopilot
        self.boot_observations = boot_observations
        self.result: GuardianRecoveryExecutionResult = result
        self.incident: RecoveryIncident = incident
        self.boot_receipt: BootObservationReceipt | None = None
        self.clock = clock or (lambda: datetime.now(UTC))
        self.revision = 1
        self.details = incident.diagnosis
        self._last_observed_at: datetime | None = None
        if result.state is RecoveryExecutionResultState.SEQUENCE_COMPLETED_AWAITING_REASSESSMENT:
            if incident.state is not RecoveryIncidentState.VERIFYING:
                raise RecoveryOperationSessionError(
                    "Completed Recovery result is not waiting at the verification boundary"
                )
            self.phase = RecoveryOperationPhase.WAITING_FOR_ANDROID
            self.status = (
                "Recovery actions are recorded. ROMVERSE is waiting for the phone involved in "
                "this incident to return to Android, then boot checks continue automatically."
            )
        elif result.state is RecoveryExecutionResultState.FAILED_AWAITING_REASSESSMENT:
            self.phase = RecoveryOperationPhase.STOPPED_FAILED
            self.status = (
                "Recovery recorded a known failure. The same incident is stopped for diagnosis; "
                "no action will be retried automatically."
            )
        elif result.state is RecoveryExecutionResultState.UNKNOWN_AWAITING_RECONSTRUCTION:
            self.phase = RecoveryOperationPhase.STOPPED_UNKNOWN
            self.status = (
                "Recovery could not prove the last action's result. The same incident is stopped "
                "for state reconstruction and ROMVERSE will not blindly retry it."
            )
        else:  # pragma: no cover - the exact result service owns the closed enum.
            raise RecoveryOperationSessionError("Recovery result state is unsupported")

    @property
    def identity(self) -> tuple[str, str, str]:
        return (
            self.preparation.preparation_digest,
            self.result.result_digest,
            self.incident.incident_id,
        )

    @property
    def can_observe(self) -> bool:
        return self.phase in {
            RecoveryOperationPhase.WAITING_FOR_ANDROID,
            RecoveryOperationPhase.OBSERVING_BOOT,
        }

    @property
    def terminal(self) -> bool:
        return self.phase in {
            RecoveryOperationPhase.VERIFIED,
            RecoveryOperationPhase.STOPPED_FAILED,
            RecoveryOperationPhase.STOPPED_UNKNOWN,
            RecoveryOperationPhase.ATTENTION,
        }

    def matches(self, other: RecoveryOperationSession) -> bool:
        return isinstance(other, RecoveryOperationSession) and self.identity == other.identity

    def snapshot(self) -> RecoveryOperationSnapshot:
        receipt = self.boot_receipt
        return RecoveryOperationSnapshot(
            revision=self.revision,
            phase=self.phase,
            status=self.status,
            details=self.details,
            incident_id=self.incident.incident_id,
            project_id=self.result.project_id,
            device_key=self.result.device_key,
            result_digest=self.result.result_digest,
            result_state=self.result.state,
            incident_state=self.incident.state,
            boot_observation_digest=receipt.receipt_digest if receipt is not None else "",
            boot_status=receipt.status.value if receipt is not None else "",
            waiting_for_exact_device=self.phase is RecoveryOperationPhase.WAITING_FOR_ANDROID,
            can_observe=self.can_observe,
            recovered=self.phase is RecoveryOperationPhase.VERIFIED,
            terminal=self.terminal,
            execution_authority="none",
            automatic_retry_allowed=False,
            bootloader_relock_allowed=False,
        )

    def accept_scan(self, devices: Iterable[AndroidDevice]) -> RecoveryOperationSnapshot:
        """Consume one fresh app scan without selecting or acting on another phone."""

        if not self.can_observe:
            return self.snapshot()
        try:
            scanned = tuple(devices)
        except TypeError as exc:
            raise RecoveryOperationSessionError("Recovery scan evidence must be iterable") from exc
        if len(scanned) > self.MAX_SCAN_DEVICES or any(
            not isinstance(device, AndroidDevice) for device in scanned
        ):
            raise RecoveryOperationSessionError("Recovery scan evidence has an invalid shape")
        exact: dict[str, AndroidDevice] = {}
        conflicting_duplicate = False
        for device in scanned:
            if not device.serial or not hmac.compare_digest(
                self.autopilot.privacy.pseudonym(device.serial),
                self.result.device_key,
            ):
                continue
            previous = exact.get(device.serial)
            if previous is not None and previous != device:
                conflicting_duplicate = True
            exact[device.serial] = device
        if conflicting_duplicate or len(exact) != 1:
            return self._update(
                RecoveryOperationPhase.WAITING_FOR_ANDROID,
                "ROMVERSE is waiting for the phone involved in this Recovery incident. Boot "
                "diagnosis continues automatically after that exact phone is freshly recognized.",
                "No current scan was assigned to the sealed incident and no action was retried.",
            )
        device = next(iter(exact.values()))
        if device.state is not DeviceState.DEVICE:
            return self._update(
                RecoveryOperationPhase.WAITING_FOR_ANDROID,
                "The exact Recovery phone is recognized, but Android is not available yet. "
                "ROMVERSE will continue after a fresh authorized Android scan.",
                f"Observed mode: {device.state.value}. No boot evidence or phone command was accepted.",
            )
        try:
            now = self._now()
            if self._last_observed_at is not None and now < self._last_observed_at:
                raise RecoveryOperationSessionError(
                    "The observation clock moved backwards; current boot continuity is unproven"
                )
            receipt = self.boot_observations.observe_recovery(
                self.result.project_id,
                device,
                self.preparation,
                self.execution_results,
                now,
            )
            self._last_observed_at = now
        except (OSError, ProjectError, RecoveryOperationSessionError) as exc:
            return self._update(
                RecoveryOperationPhase.ATTENTION,
                "ROMVERSE could not accept the current boot evidence. The same Recovery incident "
                "is preserved and no action will be retried.",
                self._safe_detail(exc),
            )
        self.boot_receipt = receipt
        if receipt.status is BootObservationStatus.ATTENTION:
            return self._update(
                RecoveryOperationPhase.ATTENTION,
                "Android boot evidence needs diagnosis. The same Recovery incident remains open "
                "and no Recovery action will be retried automatically.",
                receipt.diagnosis,
            )
        if receipt.status is not BootObservationStatus.STABLE:
            return self._update(
                RecoveryOperationPhase.OBSERVING_BOOT,
                "The exact phone is back in Android. ROMVERSE is measuring a continuous stable "
                "boot window automatically.",
                receipt.diagnosis,
            )
        try:
            verified = self.autopilot.verify_execution_recovery(
                self.preparation,
                self.execution_results,
                self.boot_observations,
                device,
            )
        except (OSError, ProjectError, RecoveryAutopilotError) as exc:
            return self._update(
                RecoveryOperationPhase.ATTENTION,
                "Stable boot evidence could not verify the Recovery result. The same incident is "
                "preserved and ROMVERSE will not infer success or retry an action.",
                self._safe_detail(exc),
            )
        self.incident = verified
        return self._update(
            RecoveryOperationPhase.VERIFIED,
            "Recovery verified. Fresh evidence proved that the exact phone remained booted on the "
            "same Android build and slot across the required stability window.",
            verified.diagnosis,
        )

    def note_scan_unavailable(self, reason: str = "") -> RecoveryOperationSnapshot:
        """Preserve a live continuation when the app cannot obtain a fresh scan."""

        if not self.can_observe:
            return self.snapshot()
        detail = self._safe_detail(reason) if reason else "Fresh device evidence is unavailable."
        return self._update(
            RecoveryOperationPhase.WAITING_FOR_ANDROID,
            "ROMVERSE cannot read the Recovery phone yet. It will continue after a fresh exact-phone "
            "scan; no action has been retried.",
            detail,
        )

    def _update(
        self,
        phase: RecoveryOperationPhase,
        status: str,
        details: str,
    ) -> RecoveryOperationSnapshot:
        changed = (phase, status, details) != (self.phase, self.status, self.details)
        self.phase = phase
        self.status = status
        self.details = details
        if changed:
            self.revision += 1
            snapshot = self.snapshot()
            self.changed.emit(snapshot)
            return snapshot
        return self.snapshot()

    def _now(self) -> datetime:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise RecoveryOperationSessionError(
                "Recovery boot observation requires a timezone-aware application clock"
            )
        return value.astimezone(UTC)

    @staticmethod
    def _safe_detail(value: object) -> str:
        return " ".join(str(value).replace("\x00", " ").split())[:500]


__all__ = [
    "RecoveryOperationPhase",
    "RecoveryOperationSession",
    "RecoveryOperationSessionError",
    "RecoveryOperationSnapshot",
]
