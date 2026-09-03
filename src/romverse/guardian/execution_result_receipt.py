from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import stat
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from romverse.device_packs.models import DeviceRecoveryOperation
from romverse.guardian.execution_gateway_contract import (
    GatewayEvidenceKind,
    GuardianExecutionGatewayContract,
    GuardianExecutionGatewayContractService,
    GuardianGatewayRecoveryStep,
    GuardianGatewayStep,
)
from romverse.rom.models import ProjectError


class GatewayResultOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class ExecutionTerminalState(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABORTED = "aborted"
    RECOVERED = "recovered"
    RECOVERY_FAILED = "recovery_failed"


@dataclass(frozen=True, slots=True)
class GuardianRuntimeTrust:
    """One externally trusted runtime identity; this module never creates its key."""

    key_id: str
    public_key_sha256: str
    adapter_id: str
    adapter_version: int
    adapter_sha256: str
    device_pack_id: str
    device_pack_sha256: str
    write_contract_id: str
    write_contract_version: int
    write_attestation_sha256: str
    transition_recovery_contract_digest: str


@dataclass(frozen=True, slots=True)
class GuardianExecutionPrerequisiteBindings:
    """Digests independently verified before a runtime result may be accepted."""

    gateway_contract_digest: str
    device_key: str
    live_target_receipt_digest: str
    final_consent_receipt_digest: str
    recovery_consent_receipt_digest: str = ""
    wipe_consent_receipt_digest: str = ""
    recorded_prewrite_slot: str = ""


@dataclass(frozen=True, slots=True)
class GuardianGatewayStepResult:
    """Privacy-bounded evidence for one attempted forward gateway step."""

    order: int
    operation_id: str
    gateway_step_digest: str
    started_at: str
    completed_at: str
    outcome: GatewayResultOutcome
    returncode: int
    timed_out: bool
    observed_value: str
    observed_size_bytes: int
    observed_sha256: str
    evidence_sha256: str
    error_code: str
    result_digest: str


@dataclass(frozen=True, slots=True)
class GuardianGatewayRecoveryResult:
    """Privacy-bounded evidence for one separately consented recovery action."""

    order: int
    operation: DeviceRecoveryOperation
    adapter_action_id: str
    recovery_step_digest: str
    started_at: str
    completed_at: str
    outcome: GatewayResultOutcome
    resulting_mode: str
    resulting_slot: str
    wiped_user_data: bool
    evidence_sha256: str
    error_code: str
    result_digest: str


@dataclass(frozen=True, slots=True)
class GuardianExecutionResultReceipt:
    """Signed runtime claim bound to one exact inert Guardian gateway contract."""

    schema_version: int
    receipt_id: str
    created_at: str
    started_at: str
    completed_at: str
    gateway_contract_digest: str
    project_id: str
    plan_digest: str
    manifest_digest: str
    artifact_binding_digest: str
    device_key: str
    device_pack_id: str
    device_pack_version: str
    device_pack_sha256: str
    live_target_receipt_digest: str
    final_consent_receipt_digest: str
    runtime_signer_key_id: str
    runtime_adapter_id: str
    runtime_adapter_version: int
    runtime_adapter_sha256: str
    recorded_prewrite_slot: str
    forward_result_count: int
    forward_results_digest: str
    forward_results: tuple[GuardianGatewayStepResult, ...]
    recovery_invoked: bool
    recovery_consent_receipt_digest: str
    wipe_consent_receipt_digest: str
    recovery_result_count: int
    recovery_results_digest: str
    recovery_results: tuple[GuardianGatewayRecoveryResult, ...]
    terminal_state: ExecutionTerminalState
    phone_change_attempted: bool
    phone_change_verified: bool
    phone_state_uncertain: bool
    postconditions_verified: bool
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class VerifiedGuardianExecutionResult:
    receipt: GuardianExecutionResultReceipt
    signer_key_id: str
    signed_receipt_sha256: str


class ExecutionResultValidationError(ProjectError):
    """A signed execution result failed its trust, binding, or evidence contract."""


class GuardianExecutionResultVerifier:
    """Verify runtime-signed results without providing a runner or signing authority."""

    FORMAT = "romverse.guardian-execution-result"
    SCHEMA_VERSION = 2
    ALGORITHM = "ed25519"
    DOMAIN = b"ROMVERSE-GUARDIAN-EXECUTION-RESULT-V2\0"
    MAX_DOCUMENT_BYTES = 1024 * 1024
    MAX_DURATION_SECONDS = 24 * 60 * 60

    ENVELOPE_FIELDS = {
        "format",
        "schema_version",
        "algorithm",
        "key_id",
        "receipt_sha256",
        "receipt",
        "signature",
    }
    RECEIPT_FIELDS = {field.name for field in fields(GuardianExecutionResultReceipt)}
    STEP_RESULT_FIELDS = {field.name for field in fields(GuardianGatewayStepResult)}
    RECOVERY_RESULT_FIELDS = {field.name for field in fields(GuardianGatewayRecoveryResult)}

    @classmethod
    def verify(
        cls,
        envelope: dict[str, Any],
        *,
        gateway: GuardianExecutionGatewayContract,
        trust: GuardianRuntimeTrust,
        prerequisites: GuardianExecutionPrerequisiteBindings,
        public_key: Ed25519PublicKey,
    ) -> VerifiedGuardianExecutionResult:
        try:
            GuardianExecutionGatewayContractService.validate(gateway)
            cls._validate_trust(trust, public_key, gateway)
            _exact_fields(envelope, cls.ENVELOPE_FIELDS, "execution result envelope")
            if (
                envelope["format"] != cls.FORMAT
                or type(envelope["schema_version"]) is not int
                or envelope["schema_version"] != cls.SCHEMA_VERSION
                or envelope["algorithm"] != cls.ALGORITHM
                or envelope["key_id"] != trust.key_id
            ):
                raise ExecutionResultValidationError(
                    "Execution result signer or envelope schema is not trusted"
                )
            raw_receipt = envelope["receipt"]
            if not isinstance(raw_receipt, dict):
                raise ExecutionResultValidationError("Execution result receipt is not an object")
            encoded = canonical_execution_result_bytes(raw_receipt)
            if len(encoded) > cls.MAX_DOCUMENT_BYTES:
                raise ExecutionResultValidationError("Execution result exceeds its size boundary")
            signed_digest = hashlib.sha256(encoded).hexdigest()
            if envelope["receipt_sha256"] != signed_digest:
                raise ExecutionResultValidationError(
                    "Execution result signed digest does not match"
                )
            signature = cls._signature(envelope["signature"])
            try:
                public_key.verify(signature, cls.DOMAIN + encoded)
            except InvalidSignature as exc:
                raise ExecutionResultValidationError(
                    "Execution result signature verification failed"
                ) from exc
            receipt = cls._parse_receipt(raw_receipt)
            cls._validate_receipt(receipt, gateway, trust, prerequisites)
            return VerifiedGuardianExecutionResult(receipt, trust.key_id, signed_digest)
        except ExecutionResultValidationError:
            raise
        except (KeyError, TypeError, ValueError, ProjectError) as exc:
            raise ExecutionResultValidationError(
                "Execution result failed strict safety validation"
            ) from exc

    @classmethod
    def _parse_receipt(cls, raw: dict[str, Any]) -> GuardianExecutionResultReceipt:
        _exact_fields(raw, cls.RECEIPT_FIELDS, "execution result receipt")
        raw_forward = raw["forward_results"]
        raw_recovery = raw["recovery_results"]
        if not isinstance(raw_forward, list) or not isinstance(raw_recovery, list):
            raise ExecutionResultValidationError("Execution results must be ordered lists")
        forward: list[GuardianGatewayStepResult] = []
        for value in raw_forward:
            if not isinstance(value, dict):
                raise ExecutionResultValidationError("Gateway step result is not an object")
            _exact_fields(value, cls.STEP_RESULT_FIELDS, "gateway step result")
            forward.append(
                GuardianGatewayStepResult(
                    **{
                        **value,
                        "outcome": GatewayResultOutcome(value["outcome"]),
                    }
                )
            )
        recovery: list[GuardianGatewayRecoveryResult] = []
        for value in raw_recovery:
            if not isinstance(value, dict):
                raise ExecutionResultValidationError("Recovery result is not an object")
            _exact_fields(value, cls.RECOVERY_RESULT_FIELDS, "recovery result")
            recovery.append(
                GuardianGatewayRecoveryResult(
                    **{
                        **value,
                        "operation": DeviceRecoveryOperation(value["operation"]),
                        "outcome": GatewayResultOutcome(value["outcome"]),
                    }
                )
            )
        return GuardianExecutionResultReceipt(
            **{
                **raw,
                "forward_results": tuple(forward),
                "recovery_results": tuple(recovery),
                "terminal_state": ExecutionTerminalState(raw["terminal_state"]),
            }
        )

    @classmethod
    def _validate_receipt(
        cls,
        receipt: GuardianExecutionResultReceipt,
        gateway: GuardianExecutionGatewayContract,
        trust: GuardianRuntimeTrust,
        prerequisites: GuardianExecutionPrerequisiteBindings,
    ) -> None:
        unsigned = asdict(receipt)
        receipt_digest = unsigned.pop("receipt_digest", "")
        start = _timestamp(receipt.started_at, "execution start")
        completed = _timestamp(receipt.completed_at, "execution completion")
        created = _timestamp(receipt.created_at, "receipt creation")
        if (
            type(receipt.schema_version) is not int
            or receipt.schema_version != gateway.result_receipt_schema_version
            or receipt.schema_version != cls.SCHEMA_VERSION
            or not _hex(receipt.receipt_id, 32)
            or not start <= completed <= created
            or (completed - start).total_seconds() > cls.MAX_DURATION_SECONDS
            or receipt.gateway_contract_digest != gateway.contract_digest
            or receipt.project_id != gateway.project_id
            or receipt.plan_digest != gateway.plan_digest
            or receipt.manifest_digest != gateway.manifest_digest
            or receipt.artifact_binding_digest != gateway.artifact_binding_digest
            or receipt.device_key != gateway.device_key
            or receipt.device_pack_id != gateway.device_pack_id
            or receipt.device_pack_version != gateway.device_pack_version
            or receipt.device_pack_sha256 != gateway.device_pack_sha256
            or not cls._valid_prerequisites(prerequisites, gateway)
            or receipt.live_target_receipt_digest != prerequisites.live_target_receipt_digest
            or receipt.final_consent_receipt_digest != prerequisites.final_consent_receipt_digest
            or receipt.runtime_signer_key_id != trust.key_id
            or receipt.runtime_adapter_id != trust.adapter_id
            or receipt.runtime_adapter_version != trust.adapter_version
            or receipt.runtime_adapter_sha256 != trust.adapter_sha256
            or receipt.recorded_prewrite_slot != prerequisites.recorded_prewrite_slot
            or type(receipt.forward_result_count) is not int
            or receipt.forward_result_count != len(receipt.forward_results)
            or receipt.forward_result_count > gateway.step_count
            or receipt.forward_results_digest
            != execution_result_digest(
                {"forward_results": [asdict(item) for item in receipt.forward_results]}
            )
            or type(receipt.recovery_invoked) is not bool
            or type(receipt.recovery_result_count) is not int
            or receipt.recovery_result_count != len(receipt.recovery_results)
            or receipt.recovery_result_count > gateway.recovery_action_count
            or receipt.recovery_results_digest
            != execution_result_digest(
                {"recovery_results": [asdict(item) for item in receipt.recovery_results]}
            )
            or any(
                type(value) is not bool
                for value in (
                    receipt.phone_change_attempted,
                    receipt.phone_change_verified,
                    receipt.phone_state_uncertain,
                    receipt.postconditions_verified,
                )
            )
            or not _hex(receipt_digest, 64)
            or receipt_digest != execution_result_digest(unsigned)
        ):
            raise ExecutionResultValidationError(
                "Execution result does not match the exact Guardian gateway and runtime trust"
            )

        forward_validity = tuple(
            cls._validate_forward_result(result, step)
            for result, step in zip(
                receipt.forward_results,
                gateway.steps[: receipt.forward_result_count],
                strict=True,
            )
        )
        recovery_validity = tuple(
            cls._validate_recovery_result(result, step, receipt.recorded_prewrite_slot)
            for result, step in zip(
                receipt.recovery_results,
                gateway.recovery_steps[: receipt.recovery_result_count],
                strict=True,
            )
        )
        if not cls._valid_recovery_consent(receipt, prerequisites):
            raise ExecutionResultValidationError("Execution recovery consent binding is invalid")
        if not cls._valid_timeline(receipt, gateway):
            raise ExecutionResultValidationError("Execution result timeline is invalid")

        attempted = any(
            step.phone_changes for step in gateway.steps[: receipt.forward_result_count]
        ) or any(
            step.phone_changes_if_executed
            for step in gateway.recovery_steps[: receipt.recovery_result_count]
        )
        verified = any(
            step.phone_changes and valid
            for step, valid in zip(
                gateway.steps[: receipt.forward_result_count],
                forward_validity,
                strict=True,
            )
        ) or any(
            step.phone_changes_if_executed and valid
            for step, valid in zip(
                gateway.recovery_steps[: receipt.recovery_result_count],
                recovery_validity,
                strict=True,
            )
        )
        uncertain = any(
            step.phone_changes and not valid
            for step, valid in zip(
                gateway.steps[: receipt.forward_result_count],
                forward_validity,
                strict=True,
            )
        ) or any(
            step.phone_changes_if_executed and not valid
            for step, valid in zip(
                gateway.recovery_steps[: receipt.recovery_result_count],
                recovery_validity,
                strict=True,
            )
        )
        if (
            receipt.phone_change_attempted is not attempted
            or receipt.phone_change_verified is not verified
            or receipt.phone_state_uncertain is not uncertain
            or not cls._valid_terminal_state(
                receipt,
                gateway,
                forward_validity,
                recovery_validity,
            )
        ):
            raise ExecutionResultValidationError(
                "Execution result terminal state or derived phone-state claim is invalid"
            )

    @staticmethod
    def _validate_trust(
        trust: GuardianRuntimeTrust,
        public_key: Ed25519PublicKey,
        gateway: GuardianExecutionGatewayContract,
    ) -> None:
        if not isinstance(public_key, Ed25519PublicKey):
            raise ExecutionResultValidationError("Runtime public key type is not trusted")
        raw_key = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        if (
            not _identifier(trust.key_id)
            or not _hex(trust.public_key_sha256, 64)
            or hashlib.sha256(raw_key).hexdigest() != trust.public_key_sha256
            or not _identifier(trust.adapter_id)
            or type(trust.adapter_version) is not int
            or not 1 <= trust.adapter_version <= 1_000_000
            or not _hex(trust.adapter_sha256, 64)
            or trust.device_pack_id != gateway.device_pack_id
            or trust.device_pack_sha256 != gateway.device_pack_sha256
            or trust.write_contract_id != gateway.write_contract_id
            or trust.write_contract_version != gateway.write_contract_version
            or trust.write_attestation_sha256 != gateway.write_attestation_sha256
            or trust.transition_recovery_contract_digest
            != gateway.transition_recovery_contract_digest
        ):
            raise ExecutionResultValidationError("Runtime trust record is invalid")

    @classmethod
    def _validate_forward_result(
        cls,
        result: GuardianGatewayStepResult,
        step: GuardianGatewayStep,
    ) -> bool:
        unsigned = asdict(result)
        result_digest = unsigned.pop("result_digest", "")
        start = _timestamp(result.started_at, "gateway step start")
        completed = _timestamp(result.completed_at, "gateway step completion")
        if (
            type(result.order) is not int
            or result.order != step.order
            or result.operation_id != step.operation_id
            or result.gateway_step_digest != execution_result_digest({"gateway_step": asdict(step)})
            or start > completed
            or type(result.returncode) is not int
            or isinstance(result.returncode, bool)
            or not -255 <= result.returncode <= 65535
            or type(result.timed_out) is not bool
            or not _optional_text(result.observed_value, 512)
            or type(result.observed_size_bytes) is not int
            or isinstance(result.observed_size_bytes, bool)
            or not 0 <= result.observed_size_bytes <= 2**50
            or not _optional_hex(result.observed_sha256, 64)
            or not _hex(result.evidence_sha256, 64)
            or not _error_code(result.error_code)
            or not _hex(result_digest, 64)
            or result_digest != execution_result_digest(unsigned)
        ):
            raise ExecutionResultValidationError(
                f"Gateway result {step.order} failed structural validation"
            )
        evidence_matches = cls._evidence_matches(result, step)
        passed = (
            result.returncode == 0
            and not result.timed_out
            and evidence_matches
            and not result.error_code
        )
        if result.outcome is GatewayResultOutcome.PASSED and not passed:
            raise ExecutionResultValidationError(
                f"Gateway result {step.order} claims success without exact evidence"
            )
        if result.outcome is GatewayResultOutcome.FAILED and (passed or not result.error_code):
            raise ExecutionResultValidationError(
                f"Gateway result {step.order} has an invalid failure claim"
            )
        return passed

    @staticmethod
    def _evidence_matches(
        result: GuardianGatewayStepResult,
        step: GuardianGatewayStep,
    ) -> bool:
        if step.evidence_kind is GatewayEvidenceKind.COMMAND_EXIT_ZERO:
            return (
                not result.observed_value
                and result.observed_size_bytes == 0
                and not result.observed_sha256
            )
        if step.evidence_kind is GatewayEvidenceKind.FILE_SIZE_AND_SHA256:
            return bool(
                not result.observed_value
                and result.observed_size_bytes == step.expected_size_bytes
                and result.observed_sha256 == step.expected_sha256
            )
        return bool(
            result.observed_value == step.expected_value
            and result.observed_size_bytes == 0
            and not result.observed_sha256
        )

    @staticmethod
    def _validate_recovery_result(
        result: GuardianGatewayRecoveryResult,
        step: GuardianGatewayRecoveryStep,
        recorded_slot: str,
    ) -> bool:
        unsigned = asdict(result)
        result_digest = unsigned.pop("result_digest", "")
        start = _timestamp(result.started_at, "recovery step start")
        completed = _timestamp(result.completed_at, "recovery step completion")
        expected_slot = (
            recorded_slot if step.target_slot == "recorded_prewrite" else step.target_slot
        )
        if expected_slot == "none":
            expected_slot = ""
        if (
            type(result.order) is not int
            or result.order != step.order
            or result.operation is not step.operation
            or result.adapter_action_id != step.adapter_action_id
            or result.recovery_step_digest
            != execution_result_digest({"recovery_step": asdict(step)})
            or start > completed
            or not _optional_text(result.resulting_mode, 32)
            or result.resulting_slot not in {"", "a", "b"}
            or type(result.wiped_user_data) is not bool
            or (result.wiped_user_data and not step.may_wipe_user_data)
            or not _hex(result.evidence_sha256, 64)
            or not _error_code(result.error_code)
            or not _hex(result_digest, 64)
            or result_digest != execution_result_digest(unsigned)
        ):
            raise ExecutionResultValidationError(
                f"Recovery result {step.order} failed structural validation"
            )
        passed = bool(
            result.resulting_mode == step.to_mode.value
            and result.resulting_slot == expected_slot
            and not result.error_code
        )
        if result.outcome is GatewayResultOutcome.PASSED and not passed:
            raise ExecutionResultValidationError(
                f"Recovery result {step.order} claims success without exact evidence"
            )
        if result.outcome is GatewayResultOutcome.FAILED and (passed or not result.error_code):
            raise ExecutionResultValidationError(
                f"Recovery result {step.order} has an invalid failure claim"
            )
        return passed

    @staticmethod
    def _valid_prerequisites(
        prerequisites: GuardianExecutionPrerequisiteBindings,
        gateway: GuardianExecutionGatewayContract,
    ) -> bool:
        if (
            not isinstance(prerequisites, GuardianExecutionPrerequisiteBindings)
            or prerequisites.gateway_contract_digest != gateway.contract_digest
            or prerequisites.device_key != gateway.device_key
            or not _hex(prerequisites.live_target_receipt_digest, 64)
            or not _hex(prerequisites.final_consent_receipt_digest, 64)
            or not _optional_hex(prerequisites.recovery_consent_receipt_digest, 64)
            or not _optional_hex(prerequisites.wipe_consent_receipt_digest, 64)
        ):
            return False
        if gateway.recovery_require_prewrite_slot_capture:
            return prerequisites.recorded_prewrite_slot in {"a", "b"}
        return prerequisites.recorded_prewrite_slot == ""

    @staticmethod
    def _valid_recovery_consent(
        receipt: GuardianExecutionResultReceipt,
        prerequisites: GuardianExecutionPrerequisiteBindings,
    ) -> bool:
        wiped = any(item.wiped_user_data for item in receipt.recovery_results)
        if receipt.recovery_invoked:
            return bool(
                receipt.recovery_results
                and _hex(receipt.recovery_consent_receipt_digest, 64)
                and receipt.recovery_consent_receipt_digest
                == prerequisites.recovery_consent_receipt_digest
                and (
                    receipt.wipe_consent_receipt_digest == prerequisites.wipe_consent_receipt_digest
                    and _hex(receipt.wipe_consent_receipt_digest, 64)
                    if wiped
                    else not receipt.wipe_consent_receipt_digest
                    and not prerequisites.wipe_consent_receipt_digest
                )
            )
        return bool(
            not receipt.recovery_results
            and not receipt.recovery_consent_receipt_digest
            and not receipt.wipe_consent_receipt_digest
            and not prerequisites.recovery_consent_receipt_digest
            and not prerequisites.wipe_consent_receipt_digest
        )

    @classmethod
    def _valid_timeline(
        cls,
        receipt: GuardianExecutionResultReceipt,
        gateway: GuardianExecutionGatewayContract,
    ) -> bool:
        execution_start = _timestamp(receipt.started_at, "execution start")
        execution_end = _timestamp(receipt.completed_at, "execution completion")
        previous = execution_start
        for result, step in zip(
            receipt.forward_results,
            gateway.steps[: receipt.forward_result_count],
            strict=True,
        ):
            started = _timestamp(result.started_at, "gateway step start")
            completed = _timestamp(result.completed_at, "gateway step completion")
            if started < previous or completed > execution_end:
                return False
            if (
                step.timeout_seconds
                and (completed - started).total_seconds() > step.timeout_seconds
            ):
                return False
            previous = completed
        for result, step in zip(
            receipt.recovery_results,
            gateway.recovery_steps[: receipt.recovery_result_count],
            strict=True,
        ):
            started = _timestamp(result.started_at, "recovery step start")
            completed = _timestamp(result.completed_at, "recovery step completion")
            if started < previous or completed > execution_end:
                return False
            if (completed - started).total_seconds() > step.timeout_seconds:
                return False
            previous = completed
        return True

    @staticmethod
    def _valid_terminal_state(
        receipt: GuardianExecutionResultReceipt,
        gateway: GuardianExecutionGatewayContract,
        forward: tuple[bool, ...],
        recovery: tuple[bool, ...],
    ) -> bool:
        all_forward = len(forward) == gateway.step_count and all(forward)
        forward_failed = bool(forward) and not forward[-1] and all(forward[:-1])
        forward_aborted = len(forward) < gateway.step_count and all(forward)
        all_recovery = (
            len(recovery) == gateway.recovery_action_count
            and bool(recovery)
            and all(recovery)
            and gateway.recovery_steps[-1].operation is DeviceRecoveryOperation.VERIFY_POST_BOOT
        )
        recovery_failed = bool(recovery) and not recovery[-1] and all(recovery[:-1])
        state = receipt.terminal_state
        if state is ExecutionTerminalState.SUCCEEDED:
            expected = all_forward and not receipt.recovery_invoked
            return expected and receipt.postconditions_verified
        if state is ExecutionTerminalState.FAILED:
            return bool(
                forward_failed
                and not receipt.recovery_invoked
                and not receipt.postconditions_verified
            )
        if state is ExecutionTerminalState.ABORTED:
            return bool(
                forward_aborted
                and not receipt.recovery_invoked
                and not receipt.postconditions_verified
            )
        if state is ExecutionTerminalState.RECOVERED:
            return bool(
                forward_failed
                and receipt.recovery_invoked
                and all_recovery
                and receipt.postconditions_verified
            )
        if state is ExecutionTerminalState.RECOVERY_FAILED:
            return bool(
                forward_failed
                and receipt.recovery_invoked
                and recovery_failed
                and not receipt.postconditions_verified
            )
        return False

    @staticmethod
    def _signature(value: object) -> bytes:
        if not isinstance(value, str) or len(value) > 128:
            raise ExecutionResultValidationError("Execution result signature is malformed")
        try:
            signature = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ExecutionResultValidationError("Execution result signature is malformed") from exc
        if len(signature) != 64:
            raise ExecutionResultValidationError("Execution result signature has invalid length")
        return signature


def load_signed_execution_result(path: Path) -> dict[str, Any]:
    """Load one bounded regular JSON result without following a link or duplicate keys."""

    resolved = path.expanduser()
    try:
        details = resolved.lstat()
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
            raise ExecutionResultValidationError(
                "Execution result must be one regular file, not a link"
            )
        if not 2 <= details.st_size <= GuardianExecutionResultVerifier.MAX_DOCUMENT_BYTES:
            raise ExecutionResultValidationError("Execution result size is outside its boundary")
        payload = resolved.read_bytes()
    except ExecutionResultValidationError:
        raise
    except OSError as exc:
        raise ExecutionResultValidationError("Execution result is unavailable") from exc
    return parse_signed_execution_result_bytes(payload)


def parse_signed_execution_result_bytes(payload: bytes) -> dict[str, Any]:
    if (
        not isinstance(payload, bytes)
        or not 2 <= len(payload) <= GuardianExecutionResultVerifier.MAX_DOCUMENT_BYTES
    ):
        raise ExecutionResultValidationError("Execution result size is outside its boundary")
    try:
        value = json.loads(payload, object_pairs_hook=_strict_object)
    except ExecutionResultValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExecutionResultValidationError("Execution result is not valid bounded JSON") from exc
    if not isinstance(value, dict):
        raise ExecutionResultValidationError("Execution result must be one JSON object")
    return value


def canonical_execution_result_bytes(payload: dict[str, Any]) -> bytes:
    try:
        return json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ExecutionResultValidationError(
            "Execution result cannot be represented as canonical JSON"
        ) from exc


def execution_result_digest(payload: object) -> str:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ExecutionResultValidationError("Execution result digest payload is invalid") from exc
    return hashlib.sha256(encoded).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExecutionResultValidationError(f"Duplicate execution result field: {key}")
        result[key] = value
    return result


def _exact_fields(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ExecutionResultValidationError(f"{label.capitalize()} fields do not match schema")


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not 20 <= len(value) <= 40:
        raise ExecutionResultValidationError(f"{label.capitalize()} timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExecutionResultValidationError(f"{label.capitalize()} timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise ExecutionResultValidationError(f"{label.capitalize()} timestamp requires a zone")
    return parsed.astimezone(UTC)


def _identifier(value: object) -> bool:
    return bool(isinstance(value, str) and re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,95}", value))


def _hex(value: object, length: int) -> bool:
    return bool(isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value))


def _optional_hex(value: object, length: int) -> bool:
    return value == "" or _hex(value, length)


def _optional_text(value: object, maximum: int) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) <= maximum
        and all(ord(character) >= 32 for character in value)
    )


def _error_code(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and (not value or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}", value))
    )
