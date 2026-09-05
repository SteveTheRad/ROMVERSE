"""Neutral, non-authoritative contracts for Recovery evidence exchange.

These immutable records and nominal reader boundaries let Guardian policy,
Recovery orchestration, persistence, and boot observation exchange evidence
without importing one another's concrete services.  They deliberately contain
no command surface, migration hook, retry operation, or execution authority.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from romverse.device_packs.models import DeviceRecoveryOperation

if TYPE_CHECKING:
    from romverse.device.models import AndroidDevice


RECOVERY_BOOT_OBSERVATION_SCHEMA_VERSION = 3


class RecoveryContractError(RuntimeError):
    """A neutral Recovery evidence boundary rejected its input."""


class RecoveryAutopilotError(RecoveryContractError):
    """Recovery orchestration rejected an evidence transition."""


class RecoveryTargetMismatchError(RecoveryAutopilotError):
    """Fresh device evidence cannot be assigned to the sealed incident."""


class RecoveryTrigger(StrEnum):
    FLASH_FAILURE = "flash_failure"
    BOOTLOOP = "bootloop"
    BOOT_ATTENTION = "boot_attention"
    DEVICE_DISCONNECTED = "device_disconnected"
    DEVICE_MODE = "device_mode"
    MANUAL_DIAGNOSIS = "manual_diagnosis"


class RecoveryIncidentState(StrEnum):
    MONITORING = "monitoring"
    EMERGENCY = "emergency"
    STABILIZING = "stabilizing"
    VERIFYING = "verifying"
    RECOVERED = "recovered"
    SERVICE_REQUIRED = "service_required"


class RecoveryRouteRisk(StrEnum):
    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    DESTRUCTIVE = "destructive"


class RecoveryRouteKind(StrEnum):
    REFRESH_SCAN = "refresh_scan"
    AUTHORIZE_ADB = "authorize_adb"
    RECONNECT_USB = "reconnect_usb"
    OBSERVE_BOOT = "observe_boot"
    HOST_ADB_REPAIR = "host_adb_repair"
    PHYSICAL_CHECK = "physical_check"
    RECOVERY_LOG_REVIEW = "recovery_log_review"
    CACHE_GUIDANCE = "cache_guidance"
    SLOT_REVIEW = "slot_review"
    IMAGE_RESTORE_REVIEW = "image_restore_review"
    EXACT_STOCK_RESTORE = "exact_stock_restore"
    DATA_RESET_GUIDANCE = "data_reset_guidance"
    ARCHIVES_REVIEW = "archives_review"
    AUTHORIZED_SERVICE = "authorized_service"


@dataclass(frozen=True, slots=True)
class RecoveryRoute:
    route_id: str
    kind: RecoveryRouteKind
    title: str
    summary: str
    confidence: int
    risk: RecoveryRouteRisk
    rank: int
    changes_device: bool
    confirmation_required: bool
    execution_authority: str
    owner_route: str
    requirements: tuple[str, ...]
    evidence: tuple[str, ...]
    knowledge_record_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RecoveryIncidentEvent:
    sequence: int
    observed_at: str
    event_type: str
    state: RecoveryIncidentState
    mode: str
    title: str
    detail: str
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class RecoveryIncident:
    schema_version: int
    incident_id: str
    created_at: str
    updated_at: str
    project_id: str
    trigger: RecoveryTrigger
    device_key: str
    device_name: str
    pack_id: str
    pack_sha256: str
    mode: str
    state: RecoveryIncidentState
    diagnosis: str
    before_evidence_digest: str
    after_evidence_digest: str
    boot_observation_digest: str
    knowledge_archive_digest: str
    recovery_evidence_ready: bool
    routes: tuple[RecoveryRoute, ...]
    events: tuple[RecoveryIncidentEvent, ...]
    repaired: bool
    verified_reboot: bool
    phone_changed: bool
    record_digest: str

    @property
    def integrity_verified(self) -> bool:
        return bool(self.record_digest)


@dataclass(frozen=True, slots=True)
class GuardianPreparedRecoveryStep:
    order: int
    operation: DeviceRecoveryOperation
    adapter_action_id: str
    from_mode: str
    to_mode: str
    target_slot: str
    timeout_seconds: int
    may_wipe_user_data: bool


@dataclass(frozen=True, slots=True)
class GuardianRecoveryPreparation:
    """Sealed Recovery intent; this evidence never authorizes execution."""

    schema_version: int
    preparation_id: str
    created_at: str
    incident_id: str
    incident_record_digest: str
    route_id: str
    route_kind: RecoveryRouteKind
    project_id: str
    device_key: str
    device_name: str
    expected_product: str
    expected_entry_mode: str
    source_original_sha256: str
    device_pack_id: str
    device_pack_version: str
    device_pack_sha256: str
    transition_contract_id: str
    transition_contract_digest: str
    recovery_strategy: str
    recovery_adapter_id: str
    stock_package_sha256: str
    recovery_evidence_digest: str
    focused_operation: DeviceRecoveryOperation
    step_count: int
    steps_digest: str
    steps: tuple[GuardianPreparedRecoveryStep, ...]
    may_wipe_user_data: bool
    recorded_prewrite_slot_required: bool
    guardian_validation_required: bool
    user_confirmation_required: bool
    execution_authority: str
    runtime_invoked: bool
    phone_changed: bool
    bootloader_relock_allowed: bool
    preparation_status: str
    preparation_digest: str


class RecoveryStepOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class RecoveryExecutionResultState(StrEnum):
    SEQUENCE_COMPLETED_AWAITING_REASSESSMENT = "sequence_completed_awaiting_reassessment"
    FAILED_AWAITING_REASSESSMENT = "failed_awaiting_reassessment"
    UNKNOWN_AWAITING_RECONSTRUCTION = "unknown_awaiting_reconstruction"


@dataclass(frozen=True, slots=True)
class GuardianRecoveryExecutionJournalEntry:
    step_order: int
    adapter_action_id: str
    intent_digest: str
    result_digest: str
    outcome: RecoveryStepOutcome


@dataclass(frozen=True, slots=True)
class GuardianRecoveryExecutionResult:
    """Aggregate execution evidence; explicitly not a repaired-device claim."""

    schema_version: int
    record_id: str
    recorded_at: str
    evidence_completed_at: str
    claim_id: str
    claim_digest: str
    preparation_id: str
    preparation_digest: str
    consent_id: str
    consent_receipt_digest: str
    incident_id: str
    incident_record_digest: str
    route_id: str
    project_id: str
    device_key: str
    source_original_sha256: str
    device_pack_id: str
    device_pack_version: str
    device_pack_sha256: str
    transition_contract_digest: str
    steps_digest: str
    adapter_id: str
    adapter_version: int
    adapter_package_id: str
    adapter_package_version: str
    adapter_package_sha256: str
    adapter_artifact_sha256: str
    adapter_release_key_id: str
    adapter_release_public_key_sha256: str
    adapter_release_trust_scope: str
    adapter_protocol_version: int
    adapter_request_schema_version: int
    adapter_result_schema_version: int
    step_count: int
    journal_entry_count: int
    completed_step_count: int
    terminal_step_order: int
    journal_digest: str
    journal_entries: tuple[GuardianRecoveryExecutionJournalEntry, ...]
    state: RecoveryExecutionResultState
    sequence_actions_completed: bool
    known_failure_recorded: bool
    unknown_outcome_recorded: bool
    same_incident_preserved: bool
    recovery_reassessment_required: bool
    post_repair_verification_required: bool
    recovery_verified: bool
    device_repaired: bool
    execution_authority: str
    automatic_retry_allowed: bool
    bootloader_relock_allowed: bool
    result_digest: str


class BootObservationStatus(StrEnum):
    WAITING = "waiting"
    SETTLING = "settling"
    STABLE = "stable"
    ATTENTION = "attention"


class BootFailureKind(StrEnum):
    NONE = "none"
    DEVICE_MODE = "device_mode"
    IDENTITY_CHANGED = "identity_changed"
    REBOOT_LOOP = "reboot_loop"
    BOOT_TIMEOUT = "boot_timeout"
    PROBE_INCOMPLETE = "probe_incomplete"


@dataclass(frozen=True, slots=True)
class BootSample:
    observed_at: str
    device_pseudonym: str
    state: str
    boot_completed: bool | None
    uptime_seconds: int | None
    slot_suffix: str
    build_id: str
    build_fingerprint: str
    battery_percent: int | None
    probe_errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BootObservationReceipt:
    schema_version: int
    project_id: str
    pack_id: str
    contract_id: str
    source_original_sha256: str
    samples: tuple[BootSample, ...]
    status: BootObservationStatus
    stable: bool
    reboot_detected: bool
    flash_linked: bool
    guardian_execution_receipt_digest: str
    verified_first_boot: bool
    diagnosis: str
    phone_changed: bool
    failure_kind: BootFailureKind
    knowledge_queries: tuple[str, ...]
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class RecoveryProjectEvidence:
    """Minimal project identity exposed to independent Recovery verification."""

    project_id: str
    device_pack_id: str
    source_original_sha256: str


class RecoveryIncidentEvidenceStore(ABC):
    """Nominal incident evidence boundary implemented by Recovery orchestration."""

    workspace: Path

    @abstractmethod
    def load(self, incident_id: str) -> RecoveryIncident:
        raise NotImplementedError

    @abstractmethod
    def validate_route_handoff(
        self,
        incident_id: str,
        route_id: str,
        *,
        owner_route: str = "",
        device: AndroidDevice | None = None,
        require_exact_device: bool = False,
    ) -> tuple[RecoveryIncident, RecoveryRoute]:
        raise NotImplementedError


class RecoveryExecutionResultEvidenceStore(ABC):
    """Nominal reader for exact, durable Guardian execution results."""

    workspace: Path

    @abstractmethod
    def load(
        self,
        preparation: GuardianRecoveryPreparation,
    ) -> GuardianRecoveryExecutionResult | None:
        raise NotImplementedError


class RecoveryBootEvidenceStore(ABC):
    """Nominal read-only boot evidence boundary used by independent verification."""

    workspace: Path
    registry: object

    @abstractmethod
    def load_recovery(
        self,
        project_id: str,
        device: AndroidDevice,
        preparation: GuardianRecoveryPreparation,
        execution_results: RecoveryExecutionResultEvidenceStore,
    ) -> BootObservationReceipt | None:
        raise NotImplementedError

    @abstractmethod
    def project_evidence(self, project_id: str) -> RecoveryProjectEvidence:
        raise NotImplementedError


def validate_recovery_preparation_evidence(
    preparation: GuardianRecoveryPreparation,
) -> None:
    """Fail closed unless a preparation remains internally sealed and non-authoritative."""

    try:
        payload = asdict(preparation)
        digest = payload.pop("preparation_digest")
        steps = preparation.steps
        valid = bool(
            type(preparation) is GuardianRecoveryPreparation
            and preparation.schema_version == 1
            and _hex(preparation.preparation_id, 32)
            and _aware_timestamp(preparation.created_at)
            and _hex(preparation.incident_id, 32)
            and _hex(preparation.incident_record_digest, 64)
            and _clean(preparation.route_id, 80)
            and _clean(preparation.project_id, 100)
            and _hex(preparation.device_key, 20)
            and _clean(preparation.device_name, 120)
            and _clean(preparation.expected_product, 120)
            and preparation.expected_entry_mode in {"bootloader", "fastbootd"}
            and _hex(preparation.source_original_sha256, 64)
            and _clean(preparation.device_pack_id, 128)
            and _clean(preparation.device_pack_version, 80)
            and _hex(preparation.device_pack_sha256, 64)
            and _clean(preparation.transition_contract_id, 80)
            and _hex(preparation.transition_contract_digest, 64)
            and _clean(preparation.recovery_strategy, 80)
            and _clean(preparation.recovery_adapter_id, 80)
            and not _bootloader_lock_action(preparation.recovery_adapter_id)
            and _hex(preparation.stock_package_sha256, 64)
            and hmac.compare_digest(
                preparation.source_original_sha256,
                preparation.stock_package_sha256,
            )
            and _hex(preparation.recovery_evidence_digest, 64)
            and preparation.route_kind is RecoveryRouteKind.EXACT_STOCK_RESTORE
            and preparation.focused_operation is DeviceRecoveryOperation.RESTORE_STOCK_PACKAGE
            and type(preparation.step_count) is int
            and 1 <= preparation.step_count <= 16
            and preparation.step_count == len(steps)
            and tuple(step.order for step in steps) == tuple(range(1, len(steps) + 1))
            and steps[0].operation is preparation.focused_operation
            and all(_valid_prepared_step(step, preparation.recovery_adapter_id) for step in steps)
            and hmac.compare_digest(
                preparation.steps_digest,
                _digest({"steps": [asdict(step) for step in steps]}),
            )
            and type(preparation.may_wipe_user_data) is bool
            and preparation.may_wipe_user_data is any(step.may_wipe_user_data for step in steps)
            and type(preparation.recorded_prewrite_slot_required) is bool
            and preparation.recorded_prewrite_slot_required
            is any(step.target_slot == "recorded_prewrite" for step in steps)
            and preparation.guardian_validation_required is True
            and preparation.user_confirmation_required is True
            and preparation.execution_authority == "none"
            and preparation.runtime_invoked is False
            and preparation.phone_changed is False
            and preparation.bootloader_relock_allowed is False
            and preparation.preparation_status
            == "prepared-awaiting-guardian-live-target-and-consent"
            and _hex(digest, 64)
            and hmac.compare_digest(digest, _digest(payload))
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise RecoveryContractError("Recovery preparation evidence failed closed")


def validate_recovery_execution_result_evidence(
    preparation: GuardianRecoveryPreparation,
    result: GuardianRecoveryExecutionResult,
) -> None:
    """Independently validate aggregate truth before orchestration consumes it."""

    validate_recovery_preparation_evidence(preparation)
    try:
        payload = asdict(result)
        digest = payload.pop("result_digest")
        entries = result.journal_entries
        completed = (
            result.state is RecoveryExecutionResultState.SEQUENCE_COMPLETED_AWAITING_REASSESSMENT
        )
        failed = result.state is RecoveryExecutionResultState.FAILED_AWAITING_REASSESSMENT
        unknown = result.state is RecoveryExecutionResultState.UNKNOWN_AWAITING_RECONSTRUCTION
        valid = bool(
            type(result) is GuardianRecoveryExecutionResult
            and result.schema_version == 1
            and _hex(result.record_id, 32)
            and _aware_timestamp(result.recorded_at)
            and _aware_timestamp(result.evidence_completed_at)
            and datetime.fromisoformat(result.evidence_completed_at)
            <= datetime.fromisoformat(result.recorded_at)
            and _hex(result.claim_id, 32)
            and _hex(result.claim_digest, 64)
            and result.preparation_id == preparation.preparation_id
            and hmac.compare_digest(result.preparation_digest, preparation.preparation_digest)
            and _hex(result.consent_id, 32)
            and _hex(result.consent_receipt_digest, 64)
            and result.incident_id == preparation.incident_id
            and hmac.compare_digest(
                result.incident_record_digest,
                preparation.incident_record_digest,
            )
            and result.route_id == preparation.route_id
            and result.project_id == preparation.project_id
            and hmac.compare_digest(result.device_key, preparation.device_key)
            and hmac.compare_digest(
                result.source_original_sha256,
                preparation.source_original_sha256,
            )
            and result.device_pack_id == preparation.device_pack_id
            and result.device_pack_version == preparation.device_pack_version
            and hmac.compare_digest(result.device_pack_sha256, preparation.device_pack_sha256)
            and hmac.compare_digest(
                result.transition_contract_digest,
                preparation.transition_contract_digest,
            )
            and hmac.compare_digest(result.steps_digest, preparation.steps_digest)
            and result.adapter_id == preparation.recovery_adapter_id
            and type(result.adapter_version) is int
            and result.adapter_version > 0
            and _clean(result.adapter_package_id, 96)
            and _clean(result.adapter_package_version, 48)
            and _hex(result.adapter_package_sha256, 64)
            and _hex(result.adapter_artifact_sha256, 64)
            and _clean(result.adapter_release_key_id, 96)
            and _hex(result.adapter_release_public_key_sha256, 64)
            and _clean(result.adapter_release_trust_scope, 32)
            and type(result.adapter_protocol_version) is int
            and result.adapter_protocol_version > 0
            and type(result.adapter_request_schema_version) is int
            and result.adapter_request_schema_version > 0
            and type(result.adapter_result_schema_version) is int
            and result.adapter_result_schema_version > 0
            and type(result.step_count) is int
            and result.step_count == preparation.step_count
            and type(result.journal_entry_count) is int
            and result.journal_entry_count == len(entries)
            and 1 <= result.journal_entry_count <= result.step_count
            and type(result.completed_step_count) is int
            and 0 <= result.completed_step_count <= result.step_count
            and type(result.terminal_step_order) is int
            and tuple(entry.step_order for entry in entries) == tuple(range(1, len(entries) + 1))
            and result.terminal_step_order == entries[-1].step_order
            and tuple(entry.adapter_action_id for entry in entries)
            == tuple(step.adapter_action_id for step in preparation.steps[: len(entries)])
            and all(
                type(entry) is GuardianRecoveryExecutionJournalEntry
                and isinstance(entry.outcome, RecoveryStepOutcome)
                and not _bootloader_lock_action(entry.adapter_action_id)
                and _hex(entry.intent_digest, 64)
                and (not entry.result_digest or _hex(entry.result_digest, 64))
                for entry in entries
            )
            and hmac.compare_digest(
                result.journal_digest,
                _digest({"entries": [asdict(entry) for entry in entries]}),
            )
            and isinstance(result.state, RecoveryExecutionResultState)
            and sum((completed, failed, unknown)) == 1
            and result.sequence_actions_completed is completed
            and result.known_failure_recorded is failed
            and result.unknown_outcome_recorded is unknown
            and result.same_incident_preserved is True
            and result.recovery_reassessment_required is True
            and result.post_repair_verification_required is True
            and result.recovery_verified is False
            and result.device_repaired is False
            and result.execution_authority == "none"
            and result.automatic_retry_allowed is False
            and result.bootloader_relock_allowed is False
            and (
                not completed
                or (
                    result.completed_step_count == result.step_count
                    and result.terminal_step_order == result.step_count
                    and all(entry.outcome is RecoveryStepOutcome.SUCCEEDED for entry in entries)
                )
            )
            and (
                not failed
                or (
                    entries[-1].outcome is RecoveryStepOutcome.FAILED
                    and bool(entries[-1].result_digest)
                    and result.completed_step_count == result.terminal_step_order - 1
                    and all(
                        entry.outcome is RecoveryStepOutcome.SUCCEEDED for entry in entries[:-1]
                    )
                )
            )
            and (
                not unknown
                or (
                    entries[-1].outcome is RecoveryStepOutcome.UNKNOWN
                    and result.completed_step_count == result.terminal_step_order - 1
                    and all(
                        entry.outcome is RecoveryStepOutcome.SUCCEEDED for entry in entries[:-1]
                    )
                )
            )
            and _hex(digest, 64)
            and hmac.compare_digest(digest, _digest(payload))
        )
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise RecoveryContractError("Recovery execution result evidence failed closed")


def validate_recovery_boot_evidence(receipt: BootObservationReceipt) -> None:
    """Validate a boot receipt's sealed evidence shape before independent use."""

    try:
        payload = asdict(receipt)
        digest = payload.pop("receipt_digest")
        samples = receipt.samples
        valid = bool(
            type(receipt) is BootObservationReceipt
            and receipt.schema_version == RECOVERY_BOOT_OBSERVATION_SCHEMA_VERSION
            and isinstance(receipt.status, BootObservationStatus)
            and isinstance(receipt.failure_kind, BootFailureKind)
            and _clean(receipt.project_id, 100)
            and _clean(receipt.pack_id, 128)
            and _clean(receipt.contract_id, 96)
            and _hex(receipt.source_original_sha256, 64)
            and 1 <= len(samples) <= 30
            and all(type(sample) is BootSample and _valid_boot_sample(sample) for sample in samples)
            and tuple(datetime.fromisoformat(sample.observed_at) for sample in samples)
            == tuple(sorted(datetime.fromisoformat(sample.observed_at) for sample in samples))
            and receipt.phone_changed is False
            and receipt.stable is (receipt.status is BootObservationStatus.STABLE)
            and (receipt.failure_kind is BootFailureKind.NONE if receipt.stable else True)
            and receipt.verified_first_boot is (receipt.stable and receipt.flash_linked)
            and (
                _hex(receipt.guardian_execution_receipt_digest, 64)
                if receipt.flash_linked
                else receipt.guardian_execution_receipt_digest == ""
            )
            and (not receipt.reboot_detected or receipt.stable is False)
            and _hex(digest, 64)
            and hmac.compare_digest(digest, _digest(payload))
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise RecoveryContractError("Recovery boot evidence failed closed")


def _valid_prepared_step(step: GuardianPreparedRecoveryStep, adapter_id: str) -> bool:
    return bool(
        type(step) is GuardianPreparedRecoveryStep
        and type(step.order) is int
        and 1 <= step.order <= 16
        and isinstance(step.operation, DeviceRecoveryOperation)
        and _clean(step.adapter_action_id, 96)
        and step.adapter_action_id.startswith(f"{adapter_id}.")
        and not _bootloader_lock_action(step.adapter_action_id)
        and step.from_mode in {"android", "bootloader", "fastbootd"}
        and step.to_mode in {"android", "bootloader", "fastbootd"}
        and step.target_slot in {"none", "recorded_prewrite"}
        and type(step.timeout_seconds) is int
        and 5 <= step.timeout_seconds <= 3600
        and type(step.may_wipe_user_data) is bool
    )


def _valid_boot_sample(sample: BootSample) -> bool:
    observed_at = datetime.fromisoformat(sample.observed_at)
    return bool(
        observed_at.tzinfo is not None
        and observed_at.astimezone(UTC) <= datetime.now(UTC) + timedelta(minutes=5)
        and _hex(sample.device_pseudonym, 20)
        and sample.state
        in {
            "device",
            "unauthorized",
            "offline",
            "recovery",
            "sideload",
            "fastboot",
            "bootloader",
            "fastbootd",
            "unknown",
        }
        and (sample.boot_completed is None or type(sample.boot_completed) is bool)
        and (
            sample.uptime_seconds is None
            or (type(sample.uptime_seconds) is int and 0 <= sample.uptime_seconds <= 10**9)
        )
        and (
            sample.battery_percent is None
            or (type(sample.battery_percent) is int and 0 <= sample.battery_percent <= 100)
        )
    )


def _bootloader_lock_action(value: object) -> bool:
    if not isinstance(value, str):
        return True
    tokens = re.sub(r"[^a-z0-9]+", " ", value.casefold()).split()
    compact = "".join(tokens)
    return bool(
        any(token == "relock" or token.startswith("relock") for token in tokens)
        or "relockbootloader" in compact
        or any(
            phrase in compact
            for phrase in (
                "bootloaderlock",
                "lockbootloader",
                "flashinglock",
                "lockflashing",
                "oemlock",
                "lockoem",
                "criticallock",
                "lockcritical",
            )
        )
    )


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value))


def _clean(value: object, maximum: int) -> bool:
    return bool(
        type(value) is str
        and 1 <= len(value) <= maximum
        and value == value.strip()
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def _aware_timestamp(value: object) -> bool:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return False
    return bool(
        parsed.tzinfo is not None
        and parsed.utcoffset() is not None
        and parsed.astimezone(UTC) <= datetime.now(UTC) + timedelta(minutes=5)
    )
