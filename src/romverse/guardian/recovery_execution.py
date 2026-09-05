from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from romverse.device.models import AndroidDevice
from romverse.guardian.recovery_consent import (
    GuardianRecoveryConsentGrant,
    GuardianRecoveryConsentReceiptService,
    RecoveryConsentValidationError,
)
from romverse.guardian.recovery_live_target import (
    GuardianRecoveryExecutionTargetWitness,
    GuardianRecoveryLiveTargetReceipt,
    RecoveryLiveTargetValidationError,
)
from romverse.guardian.recovery_preparation import (
    GuardianPreparedRecoveryStep,
    GuardianRecoveryPreparation,
    GuardianRecoveryPreparationError,
    GuardianRecoveryPreparationService,
)
from romverse.infrastructure.local_store import (
    LocalStoreConflictError,
    LocalStoreError,
    ensure_private_directory,
    exclusive_create_json,
    read_regular_bytes,
)
from romverse.rom.models import ProjectError


class RecoveryExecutionValidationError(ProjectError):
    """Recovery execution admission or its durable step journal failed closed."""


class RecoveryStepOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class GuardianRecoveryExecutionClaim:
    """Exclusive authority snapshot for one exact Recovery preparation."""

    schema_version: int
    claim_id: str
    admitted_at: str
    expires_at: str
    preparation_id: str
    preparation_digest: str
    live_target_receipt_digest: str
    execution_target_witness_digest: str
    target_revalidated_at: str
    target_discovery_digest: str
    target_probe_results_digest: str
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
    recovery_evidence_digest: str
    recovery_adapter_id: str
    steps_digest: str
    step_count: int
    expected_entry_mode: str
    expected_product: str
    recorded_prewrite_slot: str
    execution_token_sha256: str
    execution_token_persisted: bool
    exact_sequence_authority: str
    exclusive_claim_recorded: bool
    consent_consumed_once: bool
    automatic_retry_allowed: bool
    bootloader_relock_allowed: bool
    first_step_started: bool
    phone_changed: bool
    claim_digest: str


@dataclass(frozen=True, slots=True)
class GuardianRecoveryExecutionGrant:
    """Memory-only executor capability; neither secret is persisted."""

    claim: GuardianRecoveryExecutionClaim
    target_serial: str = field(repr=False)
    ephemeral_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class GuardianRecoveryStepIntent:
    """Durable intent recorded before dispatch; absent result means UNKNOWN."""

    schema_version: int
    intent_id: str
    recorded_at: str
    claim_id: str
    claim_digest: str
    incident_id: str
    preparation_digest: str
    device_key: str
    steps_digest: str
    step_order: int
    operation: str
    adapter_action_id: str
    from_mode: str
    to_mode: str
    target_slot: str
    timeout_seconds: int
    may_wipe_user_data: bool
    outcome_at_record_time: str
    result_required_before_advance: bool
    automatic_retry_allowed: bool
    bootloader_relock_allowed: bool
    intent_digest: str


@dataclass(frozen=True, slots=True)
class GuardianRecoveryStepResult:
    """One immutable observed result; command output is represented only by a digest."""

    schema_version: int
    result_id: str
    recorded_at: str
    claim_id: str
    claim_digest: str
    intent_id: str
    intent_digest: str
    incident_id: str
    device_key: str
    step_order: int
    adapter_action_id: str
    outcome: RecoveryStepOutcome
    operation_dispatched: bool
    observed_result_sha256: str
    observed_next_mode: str
    next_step_allowed: bool
    recovery_reassessment_required: bool
    automatic_retry_allowed: bool
    bootloader_relock_allowed: bool
    result_digest: str


class GuardianRecoveryExecutionService:
    """Admit one exact Recovery sequence and journal its steps transactionally.

    This checkpoint intentionally owns no adapter dispatch.  A later adapter runner
    must use ``record_step_intent`` immediately before dispatch and
    ``record_step_result`` immediately after observing the outcome.  Losing the
    in-memory grant or finding an intent without a result leaves that step UNKNOWN.
    """

    FORMAT = "romverse.guardian-recovery-execution-claim"
    INTENT_FORMAT = "romverse.guardian-recovery-step-intent"
    RESULT_FORMAT = "romverse.guardian-recovery-step-result"
    SCHEMA_VERSION = 1
    MAX_BYTES = 256 * 1024
    EXACT_SEQUENCE_AUTHORITY = "exact-sealed-recovery-adapter-actions-only"
    MAX_CLAIM_SECONDS = 6 * 60 * 60

    def __init__(
        self,
        consents: GuardianRecoveryConsentReceiptService,
        *,
        clock=None,
    ) -> None:
        self.consents = consents
        self.live_targets = consents.live_targets
        self.preparations = consents.preparations
        self.store = consents.store
        self.clock = clock or (lambda: datetime.now(UTC))

    def admit(
        self,
        preparation: GuardianRecoveryPreparation,
        live_target: GuardianRecoveryLiveTargetReceipt,
        consent_grant: GuardianRecoveryConsentGrant,
        reviewed_device: AndroidDevice,
    ) -> GuardianRecoveryExecutionGrant:
        """Freshly revalidate and exclusively consume one exact consent grant."""

        try:
            admitted_at = self._now()
            self.consents.validate_grant(
                consent_grant,
                preparation,
                live_target,
                reviewed_device,
                now=admitted_at,
            )
            self._validate_actions(preparation)
            witness = self.live_targets.revalidate_for_execution(
                preparation,
                live_target,
                reviewed_device,
            )
            witness_time = _timestamp(witness.completed_at)
            self.consents.validate_grant(
                consent_grant,
                preparation,
                live_target,
                reviewed_device,
                now=witness_time,
            )
            current = self.preparations.load(
                preparation.incident_id,
                preparation.route_id,
                [reviewed_device],
            )
            if current != preparation:
                raise RecoveryExecutionValidationError(
                    "Recovery preparation changed during executor admission"
                )
            self.live_targets.validate_execution_witness(
                witness,
                preparation,
                live_target,
            )
            token = secrets.token_hex(32)
            duration = min(
                sum(step.timeout_seconds for step in preparation.steps) + 300,
                self.MAX_CLAIM_SECONDS,
            )
            payload: dict[str, object] = {
                "schema_version": self.SCHEMA_VERSION,
                "claim_id": uuid4().hex,
                "admitted_at": witness.completed_at,
                "expires_at": (witness_time + timedelta(seconds=duration)).isoformat(),
                "preparation_id": preparation.preparation_id,
                "preparation_digest": preparation.preparation_digest,
                "live_target_receipt_digest": live_target.receipt_digest,
                "execution_target_witness_digest": witness.witness_digest,
                "target_revalidated_at": witness.completed_at,
                "target_discovery_digest": _digest(witness.discovery_pass_digests),
                "target_probe_results_digest": witness.probe_results_digest,
                "consent_id": consent_grant.receipt.consent_id,
                "consent_receipt_digest": consent_grant.receipt.receipt_digest,
                "incident_id": preparation.incident_id,
                "incident_record_digest": preparation.incident_record_digest,
                "route_id": preparation.route_id,
                "project_id": preparation.project_id,
                "device_key": preparation.device_key,
                "source_original_sha256": preparation.source_original_sha256,
                "device_pack_id": preparation.device_pack_id,
                "device_pack_version": preparation.device_pack_version,
                "device_pack_sha256": preparation.device_pack_sha256,
                "transition_contract_digest": preparation.transition_contract_digest,
                "recovery_evidence_digest": preparation.recovery_evidence_digest,
                "recovery_adapter_id": preparation.recovery_adapter_id,
                "steps_digest": preparation.steps_digest,
                "step_count": preparation.step_count,
                "expected_entry_mode": preparation.expected_entry_mode,
                "expected_product": preparation.expected_product,
                "recorded_prewrite_slot": witness.recorded_prewrite_slot,
                "execution_token_sha256": _text_digest(token),
                "execution_token_persisted": False,
                "exact_sequence_authority": self.EXACT_SEQUENCE_AUTHORITY,
                "exclusive_claim_recorded": True,
                "consent_consumed_once": True,
                "automatic_retry_allowed": False,
                "bootloader_relock_allowed": False,
                "first_step_started": False,
                "phone_changed": False,
            }
            claim = GuardianRecoveryExecutionClaim(
                **payload,
                claim_digest=_digest(payload),
            )
            self._validate_claim(claim, preparation, witness)
            path = self._claim_path(preparation)
            ensure_private_directory(path.parent, boundary=self.store.workspace)
            exclusive_create_json(
                path,
                {"format": self.FORMAT, **asdict(claim)},
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            return GuardianRecoveryExecutionGrant(claim, reviewed_device.serial, token)
        except LocalStoreConflictError as exc:
            raise RecoveryExecutionValidationError(
                "This exact Recovery preparation already has an execution claim"
            ) from exc
        except RecoveryExecutionValidationError:
            raise
        except (
            RecoveryConsentValidationError,
            RecoveryLiveTargetValidationError,
            GuardianRecoveryPreparationError,
            LocalStoreError,
            OSError,
            TypeError,
            ValueError,
            KeyError,
            ProjectError,
        ) as exc:
            raise RecoveryExecutionValidationError(
                "Recovery executor admission failed closed before any phone-changing action"
            ) from exc

    def record_step_intent(
        self,
        grant: GuardianRecoveryExecutionGrant,
        preparation: GuardianRecoveryPreparation,
        step_order: int,
    ) -> GuardianRecoveryStepIntent:
        """Durably record the exact next action before an adapter may dispatch it."""

        try:
            now = self._now()
            claim = self._validate_grant(grant, preparation, now=now, require_unexpired=True)
            step = self._step(preparation, step_order)
            self._validate_actions(preparation)
            if step.order > 1:
                previous = self.load_step_result(preparation, claim, step.order - 1)
                if previous is None or previous.outcome is not RecoveryStepOutcome.SUCCEEDED:
                    raise RecoveryExecutionValidationError(
                        "Recovery cannot advance until the previous step has a durable success"
                    )
            payload: dict[str, object] = {
                "schema_version": self.SCHEMA_VERSION,
                "intent_id": uuid4().hex,
                "recorded_at": now.isoformat(),
                "claim_id": claim.claim_id,
                "claim_digest": claim.claim_digest,
                "incident_id": claim.incident_id,
                "preparation_digest": preparation.preparation_digest,
                "device_key": claim.device_key,
                "steps_digest": preparation.steps_digest,
                "step_order": step.order,
                "operation": step.operation.value,
                "adapter_action_id": step.adapter_action_id,
                "from_mode": step.from_mode,
                "to_mode": step.to_mode,
                "target_slot": step.target_slot,
                "timeout_seconds": step.timeout_seconds,
                "may_wipe_user_data": step.may_wipe_user_data,
                "outcome_at_record_time": RecoveryStepOutcome.UNKNOWN.value,
                "result_required_before_advance": True,
                "automatic_retry_allowed": False,
                "bootloader_relock_allowed": False,
            }
            intent = GuardianRecoveryStepIntent(
                **payload,
                intent_digest=_digest(payload),
            )
            self._validate_intent(intent, claim, step)
            exclusive_create_json(
                self._intent_path(preparation, step.order),
                {"format": self.INTENT_FORMAT, **asdict(intent)},
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            return intent
        except LocalStoreConflictError as exc:
            raise RecoveryExecutionValidationError(
                "This Recovery step already started; its outcome must not be retried or guessed"
            ) from exc
        except RecoveryExecutionValidationError:
            raise
        except (LocalStoreError, OSError, TypeError, ValueError, KeyError, ProjectError) as exc:
            raise RecoveryExecutionValidationError(
                "Recovery step intent failed closed before adapter dispatch"
            ) from exc

    def record_step_result(
        self,
        grant: GuardianRecoveryExecutionGrant,
        preparation: GuardianRecoveryPreparation,
        intent: GuardianRecoveryStepIntent,
        *,
        outcome: RecoveryStepOutcome,
        operation_dispatched: bool,
        observed_result_sha256: str,
        observed_next_mode: str,
    ) -> GuardianRecoveryStepResult:
        """Persist one observed result exactly once; UNKNOWN never permits advance."""

        try:
            now = self._now()
            claim = self._validate_grant(grant, preparation, now=now, require_unexpired=False)
            step = self._step(preparation, intent.step_order)
            current_intent = self.load_step_intent(preparation, claim, step.order)
            if current_intent != intent:
                raise RecoveryExecutionValidationError(
                    "Recovery result does not match the durable current step intent"
                )
            if (
                not isinstance(outcome, RecoveryStepOutcome)
                or type(operation_dispatched) is not bool
                or not _hex(observed_result_sha256, 64)
                or observed_next_mode not in {"android", "bootloader", "fastbootd", "unknown"}
                or (
                    outcome is RecoveryStepOutcome.SUCCEEDED
                    and (operation_dispatched is not True or observed_next_mode != step.to_mode)
                )
            ):
                raise RecoveryExecutionValidationError(
                    "Recovery step result is incomplete or conflicts with the sealed action"
                )
            next_allowed = outcome is RecoveryStepOutcome.SUCCEEDED
            payload: dict[str, object] = {
                "schema_version": self.SCHEMA_VERSION,
                "result_id": uuid4().hex,
                "recorded_at": now.isoformat(),
                "claim_id": claim.claim_id,
                "claim_digest": claim.claim_digest,
                "intent_id": intent.intent_id,
                "intent_digest": intent.intent_digest,
                "incident_id": claim.incident_id,
                "device_key": claim.device_key,
                "step_order": step.order,
                "adapter_action_id": step.adapter_action_id,
                "outcome": outcome,
                "operation_dispatched": operation_dispatched,
                "observed_result_sha256": observed_result_sha256,
                "observed_next_mode": observed_next_mode,
                "next_step_allowed": next_allowed,
                "recovery_reassessment_required": not next_allowed,
                "automatic_retry_allowed": False,
                "bootloader_relock_allowed": False,
            }
            result = GuardianRecoveryStepResult(
                **payload,
                result_digest=_digest(payload),
            )
            self._validate_result(result, claim, intent, step)
            exclusive_create_json(
                self._result_path(preparation, step.order),
                {"format": self.RESULT_FORMAT, **asdict(result)},
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            return result
        except LocalStoreConflictError as exc:
            raise RecoveryExecutionValidationError(
                "This Recovery step already has a durable result and cannot be replaced"
            ) from exc
        except RecoveryExecutionValidationError:
            raise
        except (LocalStoreError, OSError, TypeError, ValueError, KeyError, ProjectError) as exc:
            raise RecoveryExecutionValidationError(
                "Recovery step result failed closed and remains UNKNOWN"
            ) from exc

    def step_outcome(
        self,
        preparation: GuardianRecoveryPreparation,
        claim: GuardianRecoveryExecutionClaim,
        step_order: int,
    ) -> RecoveryStepOutcome | None:
        """Return None before intent, UNKNOWN after intent, or the durable result."""

        intent = self.load_step_intent(preparation, claim, step_order)
        if intent is None:
            return None
        result = self.load_step_result(preparation, claim, step_order)
        return RecoveryStepOutcome.UNKNOWN if result is None else result.outcome

    def load_claim(
        self,
        preparation: GuardianRecoveryPreparation,
    ) -> GuardianRecoveryExecutionClaim | None:
        try:
            data = _read_exact_json(
                self._claim_path(preparation),
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if set(data) != {
                "format",
                *(field.name for field in fields(GuardianRecoveryExecutionClaim)),
            }:
                return None
            if data.pop("format") != self.FORMAT:
                return None
            claim = GuardianRecoveryExecutionClaim(**data)
            self._validate_claim_static(claim, preparation)
            return claim
        except (
            RecoveryExecutionValidationError,
            LocalStoreError,
            OSError,
            TypeError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ):
            return None

    def load_step_intent(
        self,
        preparation: GuardianRecoveryPreparation,
        claim: GuardianRecoveryExecutionClaim,
        step_order: int,
    ) -> GuardianRecoveryStepIntent | None:
        try:
            step = self._step(preparation, step_order)
            data = _read_exact_json(
                self._intent_path(preparation, step_order),
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if set(data) != {
                "format",
                *(field.name for field in fields(GuardianRecoveryStepIntent)),
            }:
                return None
            if data.pop("format") != self.INTENT_FORMAT:
                return None
            intent = GuardianRecoveryStepIntent(**data)
            self._validate_intent(intent, claim, step)
            return intent
        except (
            RecoveryExecutionValidationError,
            LocalStoreError,
            OSError,
            TypeError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ):
            return None

    def load_step_result(
        self,
        preparation: GuardianRecoveryPreparation,
        claim: GuardianRecoveryExecutionClaim,
        step_order: int,
    ) -> GuardianRecoveryStepResult | None:
        try:
            step = self._step(preparation, step_order)
            intent = self.load_step_intent(preparation, claim, step_order)
            if intent is None:
                return None
            data = _read_exact_json(
                self._result_path(preparation, step_order),
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if set(data) != {
                "format",
                *(field.name for field in fields(GuardianRecoveryStepResult)),
            }:
                return None
            if data.pop("format") != self.RESULT_FORMAT:
                return None
            data["outcome"] = RecoveryStepOutcome(str(data["outcome"]))
            result = GuardianRecoveryStepResult(**data)
            self._validate_result(result, claim, intent, step)
            return result
        except (
            RecoveryExecutionValidationError,
            LocalStoreError,
            OSError,
            TypeError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ):
            return None

    def _validate_grant(
        self,
        grant: GuardianRecoveryExecutionGrant,
        preparation: GuardianRecoveryPreparation,
        *,
        now: datetime,
        require_unexpired: bool,
    ) -> GuardianRecoveryExecutionClaim:
        if (
            not isinstance(grant, GuardianRecoveryExecutionGrant)
            or not grant.target_serial
            or not _hex(grant.ephemeral_token, 64)
        ):
            raise RecoveryExecutionValidationError("Recovery execution grant is malformed")
        current = self.load_claim(preparation)
        if current is None or current != grant.claim:
            raise RecoveryExecutionValidationError("Recovery execution grant is no longer current")
        if not hmac.compare_digest(
            _text_digest(grant.ephemeral_token),
            current.execution_token_sha256,
        ):
            raise RecoveryExecutionValidationError("Recovery execution token does not match")
        if not hmac.compare_digest(
            self.preparations.privacy.pseudonym(grant.target_serial),
            current.device_key,
        ):
            raise RecoveryExecutionValidationError(
                "Recovery execution grant no longer identifies the exact target"
            )
        if require_unexpired and now > _timestamp(current.expires_at):
            raise RecoveryExecutionValidationError("Recovery execution grant expired")
        return current

    def _validate_claim(
        self,
        claim: GuardianRecoveryExecutionClaim,
        preparation: GuardianRecoveryPreparation,
        witness: GuardianRecoveryExecutionTargetWitness,
    ) -> None:
        self._validate_claim_static(claim, preparation)
        if (
            claim.execution_target_witness_digest != witness.witness_digest
            or claim.target_revalidated_at != witness.completed_at
            or claim.target_discovery_digest != _digest(witness.discovery_pass_digests)
            or claim.target_probe_results_digest != witness.probe_results_digest
            or claim.recorded_prewrite_slot != witness.recorded_prewrite_slot
        ):
            raise RecoveryExecutionValidationError(
                "Recovery execution claim does not bind the fresh exact-phone witness"
            )

    def _validate_claim_static(
        self,
        claim: GuardianRecoveryExecutionClaim,
        preparation: GuardianRecoveryPreparation,
    ) -> None:
        GuardianRecoveryPreparationService.validate(preparation)
        payload = asdict(claim)
        digest = str(payload.pop("claim_digest", ""))
        admitted = _timestamp(claim.admitted_at)
        expires = _timestamp(claim.expires_at)
        if (
            type(claim.schema_version) is not int
            or claim.schema_version != self.SCHEMA_VERSION
            or not _hex(claim.claim_id, 32)
            or expires <= admitted
            or (expires - admitted).total_seconds() > self.MAX_CLAIM_SECONDS
            or claim.preparation_id != preparation.preparation_id
            or claim.preparation_digest != preparation.preparation_digest
            or not _hex(claim.live_target_receipt_digest, 64)
            or not _hex(claim.execution_target_witness_digest, 64)
            or _timestamp(claim.target_revalidated_at) != admitted
            or not _hex(claim.target_discovery_digest, 64)
            or not _hex(claim.target_probe_results_digest, 64)
            or not _hex(claim.consent_id, 32)
            or not _hex(claim.consent_receipt_digest, 64)
            or claim.incident_id != preparation.incident_id
            or claim.incident_record_digest != preparation.incident_record_digest
            or claim.route_id != preparation.route_id
            or claim.project_id != preparation.project_id
            or claim.device_key != preparation.device_key
            or claim.source_original_sha256 != preparation.source_original_sha256
            or claim.device_pack_id != preparation.device_pack_id
            or claim.device_pack_version != preparation.device_pack_version
            or claim.device_pack_sha256 != preparation.device_pack_sha256
            or claim.transition_contract_digest != preparation.transition_contract_digest
            or claim.recovery_evidence_digest != preparation.recovery_evidence_digest
            or claim.recovery_adapter_id != preparation.recovery_adapter_id
            or claim.steps_digest != preparation.steps_digest
            or claim.step_count != preparation.step_count
            or claim.expected_entry_mode != preparation.expected_entry_mode
            or claim.expected_product != preparation.expected_product
            or not _hex(claim.execution_token_sha256, 64)
            or claim.execution_token_persisted is not False
            or claim.exact_sequence_authority != self.EXACT_SEQUENCE_AUTHORITY
            or claim.exclusive_claim_recorded is not True
            or claim.consent_consumed_once is not True
            or claim.automatic_retry_allowed is not False
            or claim.bootloader_relock_allowed is not False
            or claim.first_step_started is not False
            or claim.phone_changed is not False
            or not _hex(digest, 64)
            or digest != _digest(payload)
        ):
            raise RecoveryExecutionValidationError(
                "Recovery execution claim failed exact integrity or safety validation"
            )

    def _validate_intent(
        self,
        intent: GuardianRecoveryStepIntent,
        claim: GuardianRecoveryExecutionClaim,
        step: GuardianPreparedRecoveryStep,
    ) -> None:
        payload = asdict(intent)
        digest = str(payload.pop("intent_digest", ""))
        if (
            type(intent.schema_version) is not int
            or intent.schema_version != self.SCHEMA_VERSION
            or not _hex(intent.intent_id, 32)
            or not _timestamp(intent.recorded_at)
            or intent.claim_id != claim.claim_id
            or intent.claim_digest != claim.claim_digest
            or intent.incident_id != claim.incident_id
            or intent.preparation_digest != claim.preparation_digest
            or intent.device_key != claim.device_key
            or intent.steps_digest != claim.steps_digest
            or intent.step_order != step.order
            or intent.operation != step.operation.value
            or intent.adapter_action_id != step.adapter_action_id
            or intent.from_mode != step.from_mode
            or intent.to_mode != step.to_mode
            or intent.target_slot != step.target_slot
            or intent.timeout_seconds != step.timeout_seconds
            or intent.may_wipe_user_data is not step.may_wipe_user_data
            or intent.outcome_at_record_time != RecoveryStepOutcome.UNKNOWN.value
            or intent.result_required_before_advance is not True
            or intent.automatic_retry_allowed is not False
            or intent.bootloader_relock_allowed is not False
            or not _hex(digest, 64)
            or digest != _digest(payload)
        ):
            raise RecoveryExecutionValidationError(
                "Recovery step intent failed exact integrity or sequence validation"
            )

    def _validate_result(
        self,
        result: GuardianRecoveryStepResult,
        claim: GuardianRecoveryExecutionClaim,
        intent: GuardianRecoveryStepIntent,
        step: GuardianPreparedRecoveryStep,
    ) -> None:
        payload = asdict(result)
        digest = str(payload.pop("result_digest", ""))
        succeeded = result.outcome is RecoveryStepOutcome.SUCCEEDED
        if (
            type(result.schema_version) is not int
            or result.schema_version != self.SCHEMA_VERSION
            or not _hex(result.result_id, 32)
            or not _timestamp(result.recorded_at)
            or result.claim_id != claim.claim_id
            or result.claim_digest != claim.claim_digest
            or result.intent_id != intent.intent_id
            or result.intent_digest != intent.intent_digest
            or result.incident_id != claim.incident_id
            or result.device_key != claim.device_key
            or result.step_order != step.order
            or result.adapter_action_id != step.adapter_action_id
            or not isinstance(result.outcome, RecoveryStepOutcome)
            or type(result.operation_dispatched) is not bool
            or (succeeded and result.operation_dispatched is not True)
            or not _hex(result.observed_result_sha256, 64)
            or result.observed_next_mode not in {"android", "bootloader", "fastbootd", "unknown"}
            or (succeeded and result.observed_next_mode != step.to_mode)
            or result.next_step_allowed is not succeeded
            or result.recovery_reassessment_required is not (not succeeded)
            or result.automatic_retry_allowed is not False
            or result.bootloader_relock_allowed is not False
            or not _hex(digest, 64)
            or digest != _digest(payload)
        ):
            raise RecoveryExecutionValidationError(
                "Recovery step result failed exact integrity or safety validation"
            )

    @staticmethod
    def _validate_actions(preparation: GuardianRecoveryPreparation) -> None:
        for step in preparation.steps:
            normalized = re.sub(r"[^a-z0-9]+", " ", step.adapter_action_id.casefold()).strip()
            if (
                not step.adapter_action_id.startswith(f"{preparation.recovery_adapter_id}.")
                or "relock" in normalized.split()
                or ("lock" in normalized.split() and "bootloader" in normalized.split())
            ):
                raise RecoveryExecutionValidationError(
                    "Recovery sequence contains an untrusted or bootloader-locking action"
                )

    @staticmethod
    def _step(
        preparation: GuardianRecoveryPreparation,
        step_order: int,
    ) -> GuardianPreparedRecoveryStep:
        if type(step_order) is not int:
            raise RecoveryExecutionValidationError("Recovery step order is invalid")
        try:
            return next(step for step in preparation.steps if step.order == step_order)
        except StopIteration as exc:
            raise RecoveryExecutionValidationError(
                "Recovery step is not part of the exact sealed sequence"
            ) from exc

    def _claim_path(self, preparation: GuardianRecoveryPreparation) -> Path:
        return self._root(preparation) / f"claim-{preparation.preparation_id}.romverse"

    def _intent_path(self, preparation: GuardianRecoveryPreparation, step_order: int) -> Path:
        return self._root(preparation) / f"step-{step_order:02d}-intent.romverse"

    def _result_path(self, preparation: GuardianRecoveryPreparation, step_order: int) -> Path:
        return self._root(preparation) / f"step-{step_order:02d}-result.romverse"

    def _root(self, preparation: GuardianRecoveryPreparation) -> Path:
        GuardianRecoveryPreparationService.validate(preparation)
        return (
            self.store.workspace
            / "diagnostics"
            / "recovery-preparations"
            / preparation.incident_id
            / "execution"
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RecoveryExecutionValidationError(
                "Recovery execution clock must be timezone-aware"
            )
        return value.astimezone(UTC)


def _read_exact_json(path: Path, *, boundary: Path, maximum_bytes: int) -> dict[str, object]:
    encoded = read_regular_bytes(path, boundary=boundary, maximum_bytes=maximum_bytes)

    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                raise RecoveryExecutionValidationError(f"Duplicate Recovery execution field: {key}")
            result[key] = value
        return result

    payload = json.loads(encoded.decode("utf-8"), object_pairs_hook=pairs)
    if not isinstance(payload, dict):
        raise RecoveryExecutionValidationError("Recovery execution record must be one object")
    return payload


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


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value))
