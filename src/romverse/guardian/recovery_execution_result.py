from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from romverse.guardian.invariants import contains_bootloader_lock_action_id
from romverse.guardian.recovery_execution import (
    GuardianRecoveryExecutionClaim,
    GuardianRecoveryExecutionService,
    GuardianRecoveryStepIntent,
    RecoveryExecutionValidationError,
    RecoveryStepOutcome,
)
from romverse.guardian.recovery_preparation import GuardianRecoveryPreparation
from romverse.infrastructure.local_store import (
    LocalStoreConflictError,
    LocalStoreError,
    exclusive_create_json,
    read_regular_bytes,
)
from romverse.rom.models import ProjectError


class RecoveryExecutionResultValidationError(ProjectError):
    """An aggregate Recovery result could not be derived from exact evidence."""


class RecoveryExecutionResultState(StrEnum):
    SEQUENCE_COMPLETED_AWAITING_REASSESSMENT = "sequence_completed_awaiting_reassessment"
    FAILED_AWAITING_REASSESSMENT = "failed_awaiting_reassessment"
    UNKNOWN_AWAITING_RECONSTRUCTION = "unknown_awaiting_reconstruction"


@dataclass(frozen=True, slots=True)
class GuardianRecoveryExecutionJournalEntry:
    """One ordered intent/result binding used by the aggregate projection."""

    step_order: int
    adapter_action_id: str
    intent_digest: str
    result_digest: str
    outcome: RecoveryStepOutcome


@dataclass(frozen=True, slots=True)
class GuardianRecoveryExecutionResult:
    """Derived execution truth; intentionally not a repaired-device claim."""

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


@dataclass(frozen=True, slots=True)
class _Projection:
    claim: GuardianRecoveryExecutionClaim
    adapter: GuardianRecoveryStepIntent
    evidence_completed_at: str
    completed_step_count: int
    terminal_step_order: int
    journal_digest: str
    entries: tuple[GuardianRecoveryExecutionJournalEntry, ...]
    state: RecoveryExecutionResultState


class GuardianRecoveryExecutionResultService:
    """Persist one exclusive deterministic projection of a terminal step journal."""

    FORMAT = "romverse.guardian-recovery-execution-result"
    SCHEMA_VERSION = 1
    MAX_BYTES = 512 * 1024
    EXECUTION_AUTHORITY = "none"

    def __init__(self, executions: GuardianRecoveryExecutionService, *, clock=None) -> None:
        self.executions = executions
        self.store = executions.store
        self.clock = clock or (lambda: datetime.now(UTC))

    def record(
        self,
        preparation: GuardianRecoveryPreparation,
    ) -> GuardianRecoveryExecutionResult:
        """Derive state from the journal; callers cannot supply or override it."""

        try:
            if os.path.lexists(self.executions.aggregate_result_path(preparation)):
                raise RecoveryExecutionResultValidationError(
                    "This Recovery execution already has a durable aggregate result"
                )
            projection = self._derive(preparation)
            now = self._now()
            completed = (
                projection.state
                is RecoveryExecutionResultState.SEQUENCE_COMPLETED_AWAITING_REASSESSMENT
            )
            failed = projection.state is RecoveryExecutionResultState.FAILED_AWAITING_REASSESSMENT
            unknown = (
                projection.state is RecoveryExecutionResultState.UNKNOWN_AWAITING_RECONSTRUCTION
            )
            claim = projection.claim
            adapter = projection.adapter
            payload: dict[str, object] = {
                "schema_version": self.SCHEMA_VERSION,
                "record_id": _digest(
                    {
                        "claim_digest": claim.claim_digest,
                        "journal_digest": projection.journal_digest,
                    }
                )[:32],
                "recorded_at": now.isoformat(),
                "evidence_completed_at": projection.evidence_completed_at,
                "claim_id": claim.claim_id,
                "claim_digest": claim.claim_digest,
                "preparation_id": claim.preparation_id,
                "preparation_digest": claim.preparation_digest,
                "consent_id": claim.consent_id,
                "consent_receipt_digest": claim.consent_receipt_digest,
                "incident_id": claim.incident_id,
                "incident_record_digest": claim.incident_record_digest,
                "route_id": claim.route_id,
                "project_id": claim.project_id,
                "device_key": claim.device_key,
                "source_original_sha256": claim.source_original_sha256,
                "device_pack_id": claim.device_pack_id,
                "device_pack_version": claim.device_pack_version,
                "device_pack_sha256": claim.device_pack_sha256,
                "transition_contract_digest": claim.transition_contract_digest,
                "steps_digest": claim.steps_digest,
                "adapter_id": claim.recovery_adapter_id,
                "adapter_version": adapter.adapter_version,
                "adapter_package_id": adapter.adapter_package_id,
                "adapter_package_version": adapter.adapter_package_version,
                "adapter_package_sha256": adapter.adapter_package_sha256,
                "adapter_artifact_sha256": adapter.adapter_artifact_sha256,
                "adapter_release_key_id": adapter.adapter_release_key_id,
                "adapter_release_public_key_sha256": (adapter.adapter_release_public_key_sha256),
                "adapter_release_trust_scope": adapter.adapter_release_trust_scope,
                "adapter_protocol_version": adapter.adapter_protocol_version,
                "adapter_request_schema_version": adapter.adapter_request_schema_version,
                "adapter_result_schema_version": adapter.adapter_result_schema_version,
                "step_count": claim.step_count,
                "journal_entry_count": len(projection.entries),
                "completed_step_count": projection.completed_step_count,
                "terminal_step_order": projection.terminal_step_order,
                "journal_digest": projection.journal_digest,
                "journal_entries": [asdict(item) for item in projection.entries],
                "state": projection.state,
                "sequence_actions_completed": completed,
                "known_failure_recorded": failed,
                "unknown_outcome_recorded": unknown,
                "same_incident_preserved": True,
                "recovery_reassessment_required": True,
                "post_repair_verification_required": True,
                "recovery_verified": False,
                "device_repaired": False,
                "execution_authority": self.EXECUTION_AUTHORITY,
                "automatic_retry_allowed": False,
                "bootloader_relock_allowed": False,
            }
            result = GuardianRecoveryExecutionResult(
                **{
                    **payload,
                    "journal_entries": projection.entries,
                },
                result_digest=_digest(payload),
            )
            self._validate(result, preparation, projection)
            exclusive_create_json(
                self.executions.aggregate_result_path(preparation),
                {"format": self.FORMAT, **asdict(result)},
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            return result
        except LocalStoreConflictError as exc:
            raise RecoveryExecutionResultValidationError(
                "This Recovery execution already has a durable aggregate result"
            ) from exc
        except RecoveryExecutionResultValidationError:
            raise
        except (
            RecoveryExecutionValidationError,
            LocalStoreError,
            OSError,
            TypeError,
            ValueError,
            KeyError,
            ProjectError,
        ) as exc:
            raise RecoveryExecutionResultValidationError(
                "Recovery aggregate result failed closed without changing incident state"
            ) from exc

    def load(
        self,
        preparation: GuardianRecoveryPreparation,
    ) -> GuardianRecoveryExecutionResult | None:
        try:
            data = _read_exact_json(
                self.executions.aggregate_result_path(preparation),
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if set(data) != {
                "format",
                *(field.name for field in fields(GuardianRecoveryExecutionResult)),
            }:
                return None
            if data.pop("format") != self.FORMAT:
                return None
            entries = data["journal_entries"]
            if not isinstance(entries, list):
                return None
            parsed_entries = []
            expected_entry_fields = {
                field.name for field in fields(GuardianRecoveryExecutionJournalEntry)
            }
            for item in entries:
                if not isinstance(item, dict) or set(item) != expected_entry_fields:
                    return None
                parsed_entries.append(
                    GuardianRecoveryExecutionJournalEntry(
                        **{
                            **item,
                            "outcome": RecoveryStepOutcome(str(item["outcome"])),
                        }
                    )
                )
            data["journal_entries"] = tuple(parsed_entries)
            data["state"] = RecoveryExecutionResultState(str(data["state"]))
            result = GuardianRecoveryExecutionResult(**data)
            self._validate(result, preparation, self._derive(preparation))
            return result
        except (
            RecoveryExecutionResultValidationError,
            RecoveryExecutionValidationError,
            LocalStoreError,
            OSError,
            TypeError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ):
            return None

    def _derive(self, preparation: GuardianRecoveryPreparation) -> _Projection:
        claim = self.executions.load_claim(preparation)
        if claim is None:
            raise RecoveryExecutionResultValidationError(
                "Recovery execution claim is unavailable or changed"
            )
        entries: list[GuardianRecoveryExecutionJournalEntry] = []
        intents: list[GuardianRecoveryStepIntent] = []
        completed = 0
        terminal = 0
        evidence_completed_at = ""
        state: RecoveryExecutionResultState | None = None
        for step in preparation.steps:
            intent_path = self.executions._intent_path(preparation, step.order)
            intent = self.executions.load_step_intent(preparation, claim, step.order)
            if intent is None:
                if os.path.lexists(intent_path):
                    raise RecoveryExecutionResultValidationError(
                        "Recovery journal contains an unreadable step intent"
                    )
                break
            if intents and not _same_adapter(intents[0], intent):
                raise RecoveryExecutionResultValidationError(
                    "Recovery journal changed trusted adapter package identity"
                )
            intents.append(intent)
            result = self.executions.load_step_result(preparation, claim, step.order)
            if result is None:
                entries.append(
                    GuardianRecoveryExecutionJournalEntry(
                        step.order,
                        step.adapter_action_id,
                        intent.intent_digest,
                        "",
                        RecoveryStepOutcome.UNKNOWN,
                    )
                )
                terminal = step.order
                evidence_completed_at = intent.recorded_at
                state = RecoveryExecutionResultState.UNKNOWN_AWAITING_RECONSTRUCTION
                break
            entries.append(
                GuardianRecoveryExecutionJournalEntry(
                    step.order,
                    step.adapter_action_id,
                    intent.intent_digest,
                    result.result_digest,
                    result.outcome,
                )
            )
            terminal = step.order
            evidence_completed_at = result.recorded_at
            if result.outcome is RecoveryStepOutcome.SUCCEEDED:
                completed += 1
                continue
            state = (
                RecoveryExecutionResultState.FAILED_AWAITING_REASSESSMENT
                if result.outcome is RecoveryStepOutcome.FAILED
                else RecoveryExecutionResultState.UNKNOWN_AWAITING_RECONSTRUCTION
            )
            break
        if not entries or not intents:
            raise RecoveryExecutionResultValidationError(
                "Recovery execution has no started consequential step to summarize"
            )
        if state is None:
            if completed != preparation.step_count:
                raise RecoveryExecutionResultValidationError(
                    "Recovery execution is still waiting to start its next prepared step"
                )
            state = RecoveryExecutionResultState.SEQUENCE_COMPLETED_AWAITING_REASSESSMENT
        self._reject_later_or_unexpected_evidence(preparation, terminal)
        journal_digest = _digest({"entries": [asdict(item) for item in entries]})
        return _Projection(
            claim,
            intents[0],
            evidence_completed_at,
            completed,
            terminal,
            journal_digest,
            tuple(entries),
            state,
        )

    def _validate(
        self,
        result: GuardianRecoveryExecutionResult,
        preparation: GuardianRecoveryPreparation,
        projection: _Projection,
    ) -> None:
        payload = asdict(result)
        digest = str(payload.pop("result_digest", ""))
        recorded = _timestamp(result.recorded_at)
        evidence = _timestamp(result.evidence_completed_at)
        claim = projection.claim
        adapter = projection.adapter
        completed = (
            projection.state
            is RecoveryExecutionResultState.SEQUENCE_COMPLETED_AWAITING_REASSESSMENT
        )
        failed = projection.state is RecoveryExecutionResultState.FAILED_AWAITING_REASSESSMENT
        unknown = projection.state is RecoveryExecutionResultState.UNKNOWN_AWAITING_RECONSTRUCTION
        if (
            type(result.schema_version) is not int
            or result.schema_version != self.SCHEMA_VERSION
            or result.record_id
            != _digest(
                {
                    "claim_digest": claim.claim_digest,
                    "journal_digest": projection.journal_digest,
                }
            )[:32]
            or evidence > recorded
            or result.claim_id != claim.claim_id
            or result.claim_digest != claim.claim_digest
            or result.preparation_id != claim.preparation_id
            or result.preparation_digest != preparation.preparation_digest
            or result.consent_id != claim.consent_id
            or result.consent_receipt_digest != claim.consent_receipt_digest
            or result.incident_id != preparation.incident_id
            or result.incident_record_digest != preparation.incident_record_digest
            or result.route_id != preparation.route_id
            or result.project_id != preparation.project_id
            or result.device_key != preparation.device_key
            or result.source_original_sha256 != preparation.source_original_sha256
            or result.device_pack_id != preparation.device_pack_id
            or result.device_pack_version != preparation.device_pack_version
            or result.device_pack_sha256 != preparation.device_pack_sha256
            or result.transition_contract_digest != preparation.transition_contract_digest
            or result.steps_digest != preparation.steps_digest
            or result.adapter_id != preparation.recovery_adapter_id
            or result.adapter_version != adapter.adapter_version
            or result.adapter_package_id != adapter.adapter_package_id
            or result.adapter_package_version != adapter.adapter_package_version
            or result.adapter_package_sha256 != adapter.adapter_package_sha256
            or result.adapter_artifact_sha256 != adapter.adapter_artifact_sha256
            or result.adapter_release_key_id != adapter.adapter_release_key_id
            or result.adapter_release_public_key_sha256 != adapter.adapter_release_public_key_sha256
            or result.adapter_release_trust_scope != adapter.adapter_release_trust_scope
            or result.adapter_protocol_version != adapter.adapter_protocol_version
            or result.adapter_request_schema_version != adapter.adapter_request_schema_version
            or result.adapter_result_schema_version != adapter.adapter_result_schema_version
            or result.step_count != preparation.step_count
            or result.journal_entry_count != len(projection.entries)
            or result.completed_step_count != projection.completed_step_count
            or result.terminal_step_order != projection.terminal_step_order
            or result.journal_digest != projection.journal_digest
            or result.journal_entries != projection.entries
            or result.state is not projection.state
            or result.sequence_actions_completed is not completed
            or result.known_failure_recorded is not failed
            or result.unknown_outcome_recorded is not unknown
            or result.same_incident_preserved is not True
            or result.recovery_reassessment_required is not True
            or result.post_repair_verification_required is not True
            or result.recovery_verified is not False
            or result.device_repaired is not False
            or result.execution_authority != self.EXECUTION_AUTHORITY
            or result.automatic_retry_allowed is not False
            or result.bootloader_relock_allowed is not False
            or any(
                contains_bootloader_lock_action_id(item.adapter_action_id)
                for item in result.journal_entries
            )
            or not _hex(digest, 64)
            or not hmac.compare_digest(digest, _digest(payload))
        ):
            raise RecoveryExecutionResultValidationError(
                "Recovery aggregate result failed exact derived-state validation"
            )

    def _reject_later_or_unexpected_evidence(
        self,
        preparation: GuardianRecoveryPreparation,
        terminal_step_order: int,
    ) -> None:
        root = self.executions._root(preparation)
        allowed = {
            self.executions._claim_path(preparation).name,
            self.executions.AGGREGATE_RESULT_NAME,
        }
        for step in preparation.steps:
            intent_path = self.executions._intent_path(preparation, step.order)
            result_path = self.executions._result_path(preparation, step.order)
            allowed.update({intent_path.name, result_path.name})
            if step.order > terminal_step_order and (
                os.path.lexists(intent_path) or os.path.lexists(result_path)
            ):
                raise RecoveryExecutionResultValidationError(
                    "Recovery journal contains evidence after its terminal step"
                )
        try:
            unexpected = {item.name for item in root.iterdir()} - allowed
        except OSError as exc:
            raise RecoveryExecutionResultValidationError(
                "Recovery journal could not be inspected exactly"
            ) from exc
        if unexpected:
            raise RecoveryExecutionResultValidationError(
                "Recovery journal contains unexpected or hidden evidence"
            )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RecoveryExecutionResultValidationError(
                "Recovery aggregate result clock must be timezone-aware"
            )
        return value.astimezone(UTC)


def _same_adapter(
    first: GuardianRecoveryStepIntent,
    current: GuardianRecoveryStepIntent,
) -> bool:
    return bool(
        first.adapter_version == current.adapter_version
        and first.adapter_package_id == current.adapter_package_id
        and first.adapter_package_version == current.adapter_package_version
        and hmac.compare_digest(first.adapter_package_sha256, current.adapter_package_sha256)
        and hmac.compare_digest(first.adapter_artifact_sha256, current.adapter_artifact_sha256)
        and first.adapter_release_key_id == current.adapter_release_key_id
        and hmac.compare_digest(
            first.adapter_release_public_key_sha256,
            current.adapter_release_public_key_sha256,
        )
        and first.adapter_release_trust_scope == current.adapter_release_trust_scope
        and first.adapter_protocol_version == current.adapter_protocol_version
        and first.adapter_request_schema_version == current.adapter_request_schema_version
        and first.adapter_result_schema_version == current.adapter_result_schema_version
    )


def _read_exact_json(
    path: Path,
    *,
    boundary: Path,
    maximum_bytes: int,
) -> dict[str, object]:
    encoded = read_regular_bytes(path, boundary=boundary, maximum_bytes=maximum_bytes)

    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                raise RecoveryExecutionResultValidationError(
                    f"Duplicate Recovery aggregate result field: {key}"
                )
            result[key] = value
        return result

    payload = json.loads(encoded.decode("utf-8"), object_pairs_hook=pairs)
    if not isinstance(payload, dict):
        raise RecoveryExecutionResultValidationError("Recovery aggregate result must be one object")
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


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value))
