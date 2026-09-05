from __future__ import annotations

import hashlib
import hmac
import os
import re
import stat
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from romverse.device_packs.models import DeviceRecoveryOperation
from romverse.guardian.invariants import contains_bootloader_lock_action_id
from romverse.guardian.recovery_adapter_package import (
    RecoveryAdapterTrustScope,
    VerifiedGuardianRecoveryAdapterPackage,
    revalidate_verified_guardian_recovery_adapter_package,
)
from romverse.guardian.recovery_execution import (
    GuardianRecoveryExecutionGrant,
    GuardianRecoveryExecutionService,
    GuardianRecoveryStepIntent,
    GuardianRecoveryStepResult,
    RecoveryExecutionValidationError,
    RecoveryStepOutcome,
)
from romverse.guardian.recovery_preparation import (
    GuardianPreparedRecoveryStep,
    GuardianRecoveryPreparation,
)
from romverse.guardian.recovery_step_target import (
    GuardianRecoveryStepTargetService,
    RecoveryStepTargetPhase,
    RecoveryStepTargetValidationError,
)
from romverse.rom.models import ProjectError


class RecoveryAdapterRunnerError(ProjectError):
    """The bounded Recovery adapter runner failed closed."""


class RecoveryAdapterRunState(StrEnum):
    STEP_SUCCEEDED = "step_succeeded"
    STEP_FAILED = "step_failed"
    STEP_UNKNOWN = "step_unknown"
    SEQUENCE_COMPLETE_AWAITING_DURABLE_RESULT = "sequence_complete_awaiting_durable_result"


@dataclass(frozen=True, slots=True)
class GuardianRecoveryAdapterRequest:
    """Exact adapter-scoped action request; no arbitrary command surface exists."""

    claim_id: str
    incident_id: str
    preparation_digest: str
    device_key: str
    adapter_id: str
    adapter_action_id: str
    operation: DeviceRecoveryOperation
    step_order: int
    expected_from_mode: str
    expected_to_mode: str
    target_slot: str
    stock_package_path: Path = field(repr=False)
    stock_package_sha256: str = ""
    timeout_seconds: int = 0
    may_wipe_user_data: bool = False
    target_serial: str = field(default="", repr=False)


@dataclass(frozen=True, slots=True)
class GuardianRecoveryAdapterObservation:
    """Privacy-bounded observable result returned by one adapter dispatch."""

    adapter_id: str
    adapter_action_id: str
    step_order: int
    outcome: RecoveryStepOutcome
    dispatch_started: bool
    timed_out: bool
    evidence_sha256: str


class GuardianRecoveryActionAdapter(Protocol):
    verified_package: VerifiedGuardianRecoveryAdapterPackage
    adapter_id: str
    adapter_version: int
    package_sha256: str
    protocol_version: int
    action_ids: tuple[str, ...]
    bootloader_relock_allowed: bool
    automatic_retry_allowed: bool

    def invoke(
        self,
        request: GuardianRecoveryAdapterRequest,
    ) -> GuardianRecoveryAdapterObservation: ...


@dataclass(frozen=True, slots=True)
class GuardianRecoveryAdapterRun:
    """One-step runner result; sequence completion is explicitly not Recovery proof."""

    state: RecoveryAdapterRunState
    incident_id: str
    step_order: int
    durable_outcome: RecoveryStepOutcome | None
    next_step_order: int | None
    intent: GuardianRecoveryStepIntent | None
    result: GuardianRecoveryStepResult | None
    same_incident_preserved: bool
    recovery_verified: bool
    automatic_retry_allowed: bool
    bootloader_relock_allowed: bool


class GuardianRecoveryAdapterRunner:
    """Dispatch exactly one prepared Recovery action behind durable step evidence."""

    POST_TARGET_POLL_SECONDS = 0.25

    def __init__(
        self,
        executions: GuardianRecoveryExecutionService,
        targets: GuardianRecoveryStepTargetService | None = None,
        *,
        monotonic=None,
        sleeper=None,
        allow_test_adapter_trust: bool = False,
    ) -> None:
        self.executions = executions
        self.targets = targets or GuardianRecoveryStepTargetService(executions)
        self.monotonic = monotonic or time.monotonic
        self.sleeper = sleeper or time.sleep
        self.allow_test_adapter_trust = allow_test_adapter_trust is True

    def execute_next(
        self,
        grant: GuardianRecoveryExecutionGrant,
        preparation: GuardianRecoveryPreparation,
        adapter: GuardianRecoveryActionAdapter,
    ) -> GuardianRecoveryAdapterRun:
        """Execute at most one step; never retries an existing or uncertain intent."""

        try:
            claim = self.executions.validate_grant(grant, preparation)
            self._validate_adapter(adapter, preparation, claim)
            pending = self._next_step(preparation, claim)
            if isinstance(pending, GuardianRecoveryAdapterRun):
                return pending
            step = pending
            pre_target = self.targets.observe(
                grant,
                preparation,
                step.order,
                RecoveryStepTargetPhase.PRE_DISPATCH,
            )
            source = self._validated_source(preparation)
            intent = self.executions.record_step_intent(
                grant,
                preparation,
                step.order,
                pre_target,
                adapter.verified_package,
            )
            request = GuardianRecoveryAdapterRequest(
                claim_id=claim.claim_id,
                incident_id=claim.incident_id,
                preparation_digest=preparation.preparation_digest,
                device_key=claim.device_key,
                adapter_id=preparation.recovery_adapter_id,
                adapter_action_id=step.adapter_action_id,
                operation=step.operation,
                step_order=step.order,
                expected_from_mode=step.from_mode,
                expected_to_mode=step.to_mode,
                target_slot=(
                    claim.recorded_prewrite_slot if step.target_slot == "recorded_prewrite" else ""
                ),
                stock_package_path=source,
                stock_package_sha256=preparation.stock_package_sha256,
                timeout_seconds=step.timeout_seconds,
                may_wipe_user_data=step.may_wipe_user_data,
                target_serial=grant.target_serial,
            )
            self._validate_request(request, preparation, step, grant.target_serial)
            try:
                observation = adapter.invoke(request)
            except Exception as exc:
                return self._record_unknown(
                    grant,
                    preparation,
                    intent,
                    evidence_sha256=_text_digest(type(exc).__name__),
                )
            try:
                self._validate_observation(observation, preparation, step)
            except RecoveryAdapterRunnerError:
                return self._record_unknown(
                    grant,
                    preparation,
                    intent,
                    evidence_sha256=_text_digest("untrusted-adapter-observation"),
                )
            if observation.timed_out or observation.outcome is RecoveryStepOutcome.UNKNOWN:
                return self._record_unknown(
                    grant,
                    preparation,
                    intent,
                    evidence_sha256=observation.evidence_sha256,
                    operation_dispatched=observation.dispatch_started,
                )
            if observation.dispatch_started:
                try:
                    phase = (
                        RecoveryStepTargetPhase.POST_DISPATCH
                        if observation.outcome is RecoveryStepOutcome.SUCCEEDED
                        else RecoveryStepTargetPhase.PRE_DISPATCH
                    )
                    post_target = (
                        self._observe_post_target(grant, preparation, step)
                        if phase is RecoveryStepTargetPhase.POST_DISPATCH
                        else self.targets.observe(
                            grant,
                            preparation,
                            step.order,
                            phase,
                        )
                    )
                except RecoveryStepTargetValidationError:
                    return self._record_unknown(
                        grant,
                        preparation,
                        intent,
                        evidence_sha256=observation.evidence_sha256,
                    )
            else:
                post_target = None
            outcome = observation.outcome
            result = self.executions.record_step_result(
                grant,
                preparation,
                intent,
                outcome=outcome,
                operation_dispatched=observation.dispatch_started,
                observed_result_sha256=observation.evidence_sha256,
                observed_next_mode=(
                    post_target.observed_mode if post_target is not None else step.from_mode
                ),
                post_target_witness=(post_target if post_target is not None else None),
            )
            return self._run_result(preparation, step, intent, result)
        except RecoveryAdapterRunnerError:
            raise
        except (
            RecoveryExecutionValidationError,
            RecoveryStepTargetValidationError,
            OSError,
            TypeError,
            ValueError,
            KeyError,
            ProjectError,
        ) as exc:
            raise RecoveryAdapterRunnerError(
                "Recovery adapter runner failed closed without dispatching another action"
            ) from exc

    def _next_step(self, preparation, claim):
        for step in preparation.steps:
            outcome = self.executions.step_outcome(preparation, claim, step.order)
            if outcome is None:
                return step
            if outcome is RecoveryStepOutcome.UNKNOWN:
                return GuardianRecoveryAdapterRun(
                    RecoveryAdapterRunState.STEP_UNKNOWN,
                    preparation.incident_id,
                    step.order,
                    outcome,
                    None,
                    self.executions.load_step_intent(preparation, claim, step.order),
                    self.executions.load_step_result(preparation, claim, step.order),
                    True,
                    False,
                    False,
                    False,
                )
            if outcome is RecoveryStepOutcome.FAILED:
                return GuardianRecoveryAdapterRun(
                    RecoveryAdapterRunState.STEP_FAILED,
                    preparation.incident_id,
                    step.order,
                    outcome,
                    None,
                    self.executions.load_step_intent(preparation, claim, step.order),
                    self.executions.load_step_result(preparation, claim, step.order),
                    True,
                    False,
                    False,
                    False,
                )
        return GuardianRecoveryAdapterRun(
            RecoveryAdapterRunState.SEQUENCE_COMPLETE_AWAITING_DURABLE_RESULT,
            preparation.incident_id,
            preparation.step_count,
            RecoveryStepOutcome.SUCCEEDED,
            None,
            None,
            None,
            True,
            False,
            False,
            False,
        )

    def _record_unknown(
        self,
        grant: GuardianRecoveryExecutionGrant,
        preparation: GuardianRecoveryPreparation,
        intent: GuardianRecoveryStepIntent,
        *,
        evidence_sha256: str,
        operation_dispatched: bool = True,
    ) -> GuardianRecoveryAdapterRun:
        result = self.executions.record_step_result(
            grant,
            preparation,
            intent,
            outcome=RecoveryStepOutcome.UNKNOWN,
            operation_dispatched=operation_dispatched,
            observed_result_sha256=evidence_sha256,
            observed_next_mode="unknown",
        )
        return GuardianRecoveryAdapterRun(
            RecoveryAdapterRunState.STEP_UNKNOWN,
            preparation.incident_id,
            intent.step_order,
            RecoveryStepOutcome.UNKNOWN,
            None,
            intent,
            result,
            True,
            False,
            False,
            False,
        )

    def _observe_post_target(
        self,
        grant: GuardianRecoveryExecutionGrant,
        preparation: GuardianRecoveryPreparation,
        step: GuardianPreparedRecoveryStep,
    ):
        """Wait within the sealed step timeout for the exact expected post-state."""

        deadline = self.monotonic() + step.timeout_seconds
        while True:
            try:
                return self.targets.observe(
                    grant,
                    preparation,
                    step.order,
                    RecoveryStepTargetPhase.POST_DISPATCH,
                )
            except RecoveryStepTargetValidationError:
                if self.monotonic() >= deadline:
                    raise
                self.sleeper(self.POST_TARGET_POLL_SECONDS)

    @staticmethod
    def _run_result(
        preparation: GuardianRecoveryPreparation,
        step: GuardianPreparedRecoveryStep,
        intent: GuardianRecoveryStepIntent,
        result: GuardianRecoveryStepResult,
    ) -> GuardianRecoveryAdapterRun:
        succeeded = result.outcome is RecoveryStepOutcome.SUCCEEDED
        state = (
            RecoveryAdapterRunState.STEP_SUCCEEDED
            if succeeded
            else RecoveryAdapterRunState.STEP_FAILED
        )
        next_order = step.order + 1 if succeeded and step.order < preparation.step_count else None
        return GuardianRecoveryAdapterRun(
            state,
            preparation.incident_id,
            step.order,
            result.outcome,
            next_order,
            intent,
            result,
            True,
            False,
            False,
            False,
        )

    def _validate_adapter(
        self,
        adapter: GuardianRecoveryActionAdapter,
        preparation: GuardianRecoveryPreparation,
        claim,
    ) -> None:
        from romverse.guardian.recovery_runtime_adapter import (
            GuardianTrustedRecoveryProcessAdapter,
        )

        expected = tuple(step.adapter_action_id for step in preparation.steps)
        try:
            verified = revalidate_verified_guardian_recovery_adapter_package(
                adapter.verified_package
            )
            adapter_id = adapter.adapter_id
            adapter_version = adapter.adapter_version
            package_sha256 = adapter.package_sha256
            protocol_version = adapter.protocol_version
            action_ids = adapter.action_ids
            relock = adapter.bootloader_relock_allowed
            retry = adapter.automatic_retry_allowed
            invoke = adapter.invoke
        except AttributeError as exc:
            raise RecoveryAdapterRunnerError("Recovery adapter contract is incomplete") from exc
        if (
            not isinstance(adapter, GuardianTrustedRecoveryProcessAdapter)
            or adapter_id != preparation.recovery_adapter_id
            or adapter_version != verified.manifest.adapter_version
            or package_sha256 != verified.package_sha256
            or protocol_version != verified.manifest.protocol_version
            or (
                verified.release_trust_scope is RecoveryAdapterTrustScope.TEST_ONLY
                and not self.allow_test_adapter_trust
            )
            or (
                verified.release_trust_scope is RecoveryAdapterTrustScope.RADFORGE_PRODUCTION
                and type(adapter) is not GuardianTrustedRecoveryProcessAdapter
            )
            or type(action_ids) is not tuple
            or action_ids != expected
            or action_ids != verified.manifest.supported_action_ids
            or relock is not False
            or retry is not False
            or not callable(invoke)
            or any(contains_bootloader_lock_action_id(item) for item in action_ids)
        ):
            raise RecoveryAdapterRunnerError(
                "Recovery adapter is not the exact sealed allowlisted action implementation"
            )
        first_intent = self.executions.load_step_intent(preparation, claim, 1)
        if first_intent is not None and (
            first_intent.adapter_version != verified.manifest.adapter_version
            or first_intent.adapter_package_id != verified.manifest.package_id
            or first_intent.adapter_package_version != verified.manifest.package_version
            or first_intent.adapter_package_sha256 != verified.package_sha256
            or first_intent.adapter_artifact_sha256 != verified.manifest.artifact.sha256
            or first_intent.adapter_release_key_id != verified.release_key_id
            or first_intent.adapter_release_public_key_sha256 != verified.release_public_key_sha256
            or first_intent.adapter_release_trust_scope != verified.release_trust_scope.value
            or first_intent.adapter_protocol_version != verified.manifest.protocol_version
            or first_intent.adapter_request_schema_version
            != verified.manifest.request_schema_version
            or first_intent.adapter_result_schema_version != verified.manifest.result_schema_version
        ):
            raise RecoveryAdapterRunnerError(
                "Recovery adapter package changed after the exact sequence began"
            )

    @staticmethod
    def _validate_request(
        request: GuardianRecoveryAdapterRequest,
        preparation: GuardianRecoveryPreparation,
        step: GuardianPreparedRecoveryStep,
        serial: str,
    ) -> None:
        expected_slot = request.target_slot
        if (
            request.incident_id != preparation.incident_id
            or request.preparation_digest != preparation.preparation_digest
            or request.device_key != preparation.device_key
            or request.adapter_id != preparation.recovery_adapter_id
            or request.adapter_action_id != step.adapter_action_id
            or request.operation is not step.operation
            or request.step_order != step.order
            or request.expected_from_mode != step.from_mode
            or request.expected_to_mode != step.to_mode
            or expected_slot not in {"", "a", "b"}
            or request.stock_package_sha256 != preparation.stock_package_sha256
            or request.timeout_seconds != step.timeout_seconds
            or request.may_wipe_user_data is not step.may_wipe_user_data
            or request.target_serial != serial
            or contains_bootloader_lock_action_id(request.adapter_action_id)
        ):
            raise RecoveryAdapterRunnerError(
                "Recovery adapter request does not match the exact prepared action"
            )

    @staticmethod
    def _validate_observation(
        observation: GuardianRecoveryAdapterObservation,
        preparation: GuardianRecoveryPreparation,
        step: GuardianPreparedRecoveryStep,
    ) -> None:
        if (
            not isinstance(observation, GuardianRecoveryAdapterObservation)
            or observation.adapter_id != preparation.recovery_adapter_id
            or observation.adapter_action_id != step.adapter_action_id
            or observation.step_order != step.order
            or not isinstance(observation.outcome, RecoveryStepOutcome)
            or type(observation.dispatch_started) is not bool
            or type(observation.timed_out) is not bool
            or not _hex(observation.evidence_sha256, 64)
            or (
                observation.outcome is RecoveryStepOutcome.SUCCEEDED
                and observation.dispatch_started is not True
            )
            or (observation.timed_out and observation.dispatch_started is not True)
            or (observation.timed_out and observation.outcome is not RecoveryStepOutcome.UNKNOWN)
        ):
            raise RecoveryAdapterRunnerError(
                "Recovery adapter returned an untrusted or contradictory observation"
            )

    def _validated_source(self, preparation: GuardianRecoveryPreparation) -> Path:
        project = self.executions.store.get(preparation.project_id)
        if project.original is None:
            raise RecoveryAdapterRunnerError("Recovery stock package is unavailable")
        root = self.executions.store.workspace.expanduser().resolve(strict=True)
        recorded = Path(project.original.workspace_path).expanduser()
        candidate = recorded if recorded.is_absolute() else root / recorded
        try:
            resolved = candidate.resolve(strict=True)
            details = candidate.lstat()
        except OSError as exc:
            raise RecoveryAdapterRunnerError("Recovery stock package is unavailable") from exc
        if (
            not resolved.is_relative_to(root)
            or stat.S_ISLNK(details.st_mode)
            or not stat.S_ISREG(details.st_mode)
            or details.st_size != project.original.size_bytes
            or not hmac.compare_digest(_file_sha256(resolved), preparation.stock_package_sha256)
        ):
            raise RecoveryAdapterRunnerError("Recovery stock package changed after preparation")
        return resolved


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value))
