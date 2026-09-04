from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import stat
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from romverse.device.models import AndroidDevice
from romverse.device.parsers import parse_adb_devices, parse_fastboot_devices, parse_fastboot_getvar
from romverse.guardian.consent_capability import GuardianConsentCapabilityReservation
from romverse.guardian.execution_gateway_contract import (
    GatewayEvidenceKind,
    GatewayStepPhase,
    GuardianExecutionGatewayContract,
    GuardianExecutionGatewayContractService,
    GuardianGatewayStep,
)
from romverse.guardian.execution_plan import GuardianExecutionPlan
from romverse.guardian.execution_result_receipt import (
    ExecutionTerminalState,
    GatewayResultOutcome,
    GuardianExecutionPrerequisiteBindings,
    GuardianExecutionResultReceipt,
    GuardianExecutionResultVerifier,
    GuardianGatewayStepResult,
    GuardianRuntimeTrust,
    VerifiedGuardianExecutionResult,
    canonical_execution_result_bytes,
    execution_result_digest,
    validate_guardian_runtime_trust,
)
from romverse.guardian.final_consent import GuardianFinalConsentGrant
from romverse.guardian.invariants import contains_bootloader_relock
from romverse.guardian.live_target_receipt import GuardianLiveTargetReceipt
from romverse.guardian.models import OperationClass
from romverse.guardian.runtime_authorization import GuardianRuntimeForwardExecutionGrant
from romverse.guardian.runtime_execution_claim import (
    GuardianRuntimeDeviceOpenPermit,
    GuardianRuntimeExecutionClaimService,
    RuntimeExecutionClaimError,
)
from romverse.guardian.runtime_session import VerifiedGuardianRuntimeSession
from romverse.infrastructure.local_store import (
    LocalStoreConflictError,
    LocalStoreError,
    ensure_private_directory,
    exclusive_create_json,
)
from romverse.infrastructure.process import CommandResult, CommandRunner
from romverse.rom.models import ProjectError


class RuntimeForwardExecutionError(ProjectError):
    """The enrolled runtime failed closed before completing its exact forward contract."""


class GuardianRuntimeForwardExecutor:
    """Execute one already-authorized Guardian gateway and sign its bounded result.

    The shipping Desktop UI does not construct this class. A separately packaged runtime
    must supply its enrolled key, exact tool paths and complete live consent/session/permit
    chain. Recovery, wipe, unlock and relock are outside this forward-only surface.
    """

    OPEN_FORMAT = "romverse.guardian-runtime-device-open"
    OPEN_SCHEMA_VERSION = 1
    OPEN_DOMAIN = b"ROMVERSE-GUARDIAN-RUNTIME-DEVICE-OPEN-V1\0"
    MAX_OPEN_RECORD_BYTES = 128 * 1024
    MAX_RESULT_BYTES = GuardianExecutionResultVerifier.MAX_DOCUMENT_BYTES
    DEFAULT_COMMAND_TIMEOUT_SECONDS = 600
    PROBE_TIMEOUT_SECONDS = 4
    POLL_INTERVAL_SECONDS = 0.25

    def __init__(
        self,
        claims: GuardianRuntimeExecutionClaimService,
        runner: CommandRunner,
        *,
        fastboot_path: Path,
        adb_path: Path,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.claims = claims
        self.runner = runner
        self.fastboot_path = fastboot_path
        self.adb_path = adb_path
        self.clock = clock or (lambda: datetime.now(UTC))
        self.monotonic = monotonic or time.monotonic
        self.sleeper = sleeper or time.sleep

    def execute(
        self,
        permit: GuardianRuntimeDeviceOpenPermit,
        runtime_grant: GuardianRuntimeForwardExecutionGrant,
        grant: GuardianFinalConsentGrant,
        reservation: GuardianConsentCapabilityReservation,
        session: VerifiedGuardianRuntimeSession,
        gateway: GuardianExecutionGatewayContract,
        plan: GuardianExecutionPlan,
        live_target: GuardianLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        runtime_trust: GuardianRuntimeTrust,
        runtime_public_key: Ed25519PublicKey,
        runtime_private_key: Ed25519PrivateKey,
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> VerifiedGuardianExecutionResult:
        """Consume one permit, run only its ordered forward prefix and save a signed result."""

        cancel = should_cancel or (lambda: False)
        started_at = self._now()
        receipt_id = uuid4().hex
        try:
            GuardianExecutionGatewayContractService.validate(gateway)
            validate_guardian_runtime_trust(runtime_trust, runtime_public_key, gateway)
            self._validate_private_key(runtime_public_key, runtime_private_key)
            self.claims.validate_in_memory_permit(
                permit,
                runtime_grant,
                grant,
                reservation,
                session,
                gateway,
                plan,
                live_target,
                reviewed_device,
                runtime_trust,
                runtime_public_key,
                now=started_at,
            )
            fastboot = self._validated_tool(self.fastboot_path, "fastboot")
            adb = self._validated_tool(self.adb_path, "adb")
            self._validate_forward_scope(gateway)
            self._validate_all_artifacts(gateway)
            self._consume_open_permit(
                permit,
                gateway,
                runtime_trust,
                runtime_private_key,
                consumed_at=started_at,
            )
        except RuntimeForwardExecutionError:
            raise
        except LocalStoreConflictError as exc:
            raise RuntimeForwardExecutionError(
                "This runtime device-open permit has already been consumed"
            ) from exc
        except (
            RuntimeExecutionClaimError,
            LocalStoreError,
            OSError,
            TypeError,
            ValueError,
            KeyError,
            ProjectError,
        ) as exc:
            raise RuntimeForwardExecutionError(
                "Runtime execution failed closed before device access"
            ) from exc

        output_root = self._output_root(gateway.project_id, receipt_id)
        ensure_private_directory(output_root, boundary=self.claims.store.workspace)
        results: list[GuardianGatewayStepResult] = []
        if self._fresh_fastboot_target(fastboot, permit.target_serial):
            for step in gateway.steps:
                if cancel():
                    break
                result = self._execute_step(
                    step,
                    serial=permit.target_serial,
                    fastboot=fastboot,
                    adb=adb,
                    output_root=output_root,
                )
                results.append(result)
                if result.outcome is GatewayResultOutcome.FAILED:
                    break

        terminal_state = self._terminal_state(results, gateway)
        completed_at = self._now()
        prerequisites = GuardianExecutionPrerequisiteBindings(
            gateway_contract_digest=gateway.contract_digest,
            device_key=gateway.device_key,
            live_target_receipt_digest=live_target.receipt_digest,
            final_consent_receipt_digest=grant.receipt.receipt_digest,
            recorded_prewrite_slot=live_target.recorded_prewrite_slot,
        )
        envelope = self._signed_result(
            receipt_id=receipt_id,
            started_at=started_at,
            completed_at=completed_at,
            results=tuple(results),
            terminal_state=terminal_state,
            gateway=gateway,
            prerequisites=prerequisites,
            runtime_trust=runtime_trust,
            runtime_private_key=runtime_private_key,
        )
        verified = GuardianExecutionResultVerifier.verify(
            envelope,
            gateway=gateway,
            trust=runtime_trust,
            prerequisites=prerequisites,
            public_key=runtime_public_key,
        )
        try:
            exclusive_create_json(
                self._result_path(gateway.project_id, receipt_id),
                envelope,
                boundary=self.claims.store.workspace,
                maximum_bytes=self.MAX_RESULT_BYTES,
            )
        except (LocalStoreError, OSError, TypeError, ValueError) as exc:
            raise RuntimeForwardExecutionError(
                "Runtime result could not be preserved; phone state must be treated as uncertain"
            ) from exc
        return verified

    def _execute_step(
        self,
        step: GuardianGatewayStep,
        *,
        serial: str,
        fastboot: Path,
        adb: Path,
        output_root: Path,
    ) -> GuardianGatewayStepResult:
        started_at = self._now()
        observed_value = ""
        observed_size = 0
        observed_sha256 = ""
        error_code = ""
        command = self._resolved_command(
            step,
            serial=serial,
            fastboot=fastboot,
            adb=adb,
            output_root=output_root,
        )
        try:
            if step.phase is GatewayStepPhase.WRITE:
                self._validate_artifact(step)
            result = self._run(command, self._timeout(step))
            if result.ok and step.phase is GatewayStepPhase.TRANSITION:
                result, observed_value = self._observe_transition(
                    step,
                    serial=serial,
                    fastboot=fastboot,
                    adb=adb,
                )
            elif result.ok and step.evidence_kind is GatewayEvidenceKind.FASTBOOT_VARIABLE_EQUALS:
                observed_value = parse_fastboot_getvar(
                    result.stdout + "\n" + result.stderr,
                    step.arguments[-1],
                )
            elif result.ok and step.evidence_kind is GatewayEvidenceKind.FILE_SIZE_AND_SHA256:
                output = output_root / step.output_relative_path
                observed_size, observed_sha256 = self._measure_output(output, output_root)
            elif result.ok and step.evidence_kind is GatewayEvidenceKind.ANDROID_PROPERTY_EQUALS:
                observed_value = self._clean_observed(result.stdout)
        except RuntimeForwardExecutionError as exc:
            result = CommandResult(command, 126, "", "")
            error_code = self._error_code(exc)
        except (OSError, TypeError, ValueError) as exc:
            result = CommandResult(command, 127, "", "")
            error_code = self._error_code(exc)

        evidence_matches = self._evidence_matches(
            step,
            observed_value=observed_value,
            observed_size=observed_size,
            observed_sha256=observed_sha256,
        )
        if not error_code:
            if result.timed_out:
                error_code = "COMMAND_TIMEOUT"
            elif result.returncode != 0:
                error_code = "COMMAND_FAILED"
            elif not evidence_matches:
                error_code = "EVIDENCE_MISMATCH"
        outcome = GatewayResultOutcome.PASSED if not error_code else GatewayResultOutcome.FAILED
        completed_at = self._now()
        evidence = {
            "operation_id": step.operation_id,
            "command_sha256": execution_result_digest({"command": command}),
            "returncode": result.returncode,
            "timed_out": result.timed_out,
            "stdout_sha256": self._text_sha256(result.stdout),
            "stderr_sha256": self._text_sha256(result.stderr),
            "observed_value": observed_value,
            "observed_size_bytes": observed_size,
            "observed_sha256": observed_sha256,
            "error_code": error_code,
        }
        payload: dict[str, Any] = {
            "order": step.order,
            "operation_id": step.operation_id,
            "gateway_step_digest": execution_result_digest({"gateway_step": asdict(step)}),
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "outcome": outcome,
            "returncode": result.returncode,
            "timed_out": result.timed_out,
            "observed_value": observed_value,
            "observed_size_bytes": observed_size,
            "observed_sha256": observed_sha256,
            "evidence_sha256": execution_result_digest(evidence),
            "error_code": error_code,
        }
        return GuardianGatewayStepResult(
            **payload,
            result_digest=execution_result_digest(payload),
        )

    def _observe_transition(
        self,
        step: GuardianGatewayStep,
        *,
        serial: str,
        fastboot: Path,
        adb: Path,
    ) -> tuple[CommandResult, str]:
        deadline = self.monotonic() + max(step.timeout_seconds, self.PROBE_TIMEOUT_SECONDS)
        last = CommandResult((), 124, "", "", timed_out=True)
        while True:
            if step.evidence_kind is GatewayEvidenceKind.ACTIVE_SLOT_EQUALS:
                probe = (str(fastboot), "-s", serial, "getvar", "current-slot")
                last = self._run(probe, self.PROBE_TIMEOUT_SECONDS)
                observed = (
                    parse_fastboot_getvar(last.stdout + "\n" + last.stderr, "current-slot")
                    .casefold()
                    .removeprefix("_")
                )
                if last.ok and observed == step.expected_value:
                    return last, observed
            elif step.expected_value in {"android", "system"}:
                last = self._run((str(adb), "devices", "-l"), self.PROBE_TIMEOUT_SECONDS)
                devices = parse_adb_devices(last.stdout) if last.ok else []
                matching = [
                    item
                    for item in devices
                    if item.get("serial") == serial and item.get("state") == "device"
                ]
                if len(devices) == 1 and len(matching) == 1:
                    return last, step.expected_value
            else:
                last = self._run((str(fastboot), "devices", "-l"), self.PROBE_TIMEOUT_SECONDS)
                devices = (
                    parse_fastboot_devices(last.stdout + "\n" + last.stderr) if last.ok else []
                )
                if len(devices) == 1 and devices[0].get("serial") == serial:
                    probe = (str(fastboot), "-s", serial, "getvar", "is-userspace")
                    last = self._run(probe, self.PROBE_TIMEOUT_SECONDS)
                    value = parse_fastboot_getvar(last.stdout + "\n" + last.stderr, "is-userspace")
                    observed = (
                        "fastbootd" if value == "yes" else "bootloader" if value == "no" else ""
                    )
                    if last.ok and observed == step.expected_value:
                        return last, observed
            if self.monotonic() >= deadline:
                return CommandResult(last.args, 124, last.stdout, last.stderr, timed_out=True), ""
            self.sleeper(self.POLL_INTERVAL_SECONDS)

    def _resolved_command(
        self,
        step: GuardianGatewayStep,
        *,
        serial: str,
        fastboot: Path,
        adb: Path,
        output_root: Path,
    ) -> tuple[str, ...]:
        executable = fastboot if step.executable == "fastboot" else adb
        workspace = self.claims.store.workspace
        arguments: list[str] = []
        for token in step.arguments:
            if token in {
                GuardianExecutionGatewayContractService.TARGET_TOKEN,
                GuardianExecutionGatewayContractService.ADB_TARGET_TOKEN,
            }:
                arguments.append(serial)
            elif token.startswith(f"{GuardianExecutionGatewayContractService.WORKSPACE_TOKEN}/"):
                arguments.append(str(self._inside(workspace, token.split("/", 1)[1])))
            elif token.startswith(
                f"{GuardianExecutionGatewayContractService.PRIVATE_OUTPUT_TOKEN}/"
            ):
                relative = token.split("/", 1)[1]
                relative_path = Path(relative)
                if not relative or relative_path.is_absolute() or ".." in relative_path.parts:
                    raise RuntimeForwardExecutionError("Runtime path is outside its exact boundary")
                output = output_root.joinpath(*relative_path.parts)
                ensure_private_directory(output.parent, boundary=output_root)
                output = self._inside(output_root, relative)
                arguments.append(str(output))
            else:
                arguments.append(token)
        command = (str(executable), *arguments)
        if contains_bootloader_relock((command,)):
            raise RuntimeForwardExecutionError("Bootloader relock is prohibited")
        return command

    def _validate_artifact(self, step: GuardianGatewayStep) -> None:
        path = self._inside(self.claims.store.workspace, step.artifact_relative_path)
        details = self._regular_file(path, self.claims.store.workspace)
        if details.st_size != step.artifact_size_bytes:
            raise RuntimeForwardExecutionError("Artifact size changed after final consent")
        if not hmac.compare_digest(self._file_sha256(path), step.artifact_sha256):
            raise RuntimeForwardExecutionError("Artifact digest changed after final consent")

    def _validate_all_artifacts(self, gateway: GuardianExecutionGatewayContract) -> None:
        for step in gateway.steps:
            if step.phase is GatewayStepPhase.WRITE:
                self._validate_artifact(step)

    def _measure_output(self, path: Path, output_root: Path) -> tuple[int, str]:
        details = self._regular_file(path, output_root)
        return details.st_size, self._file_sha256(path)

    def _fresh_fastboot_target(self, fastboot: Path, serial: str) -> bool:
        result = self._run((str(fastboot), "devices", "-l"), self.PROBE_TIMEOUT_SECONDS)
        devices = parse_fastboot_devices(result.stdout + "\n" + result.stderr) if result.ok else []
        return bool(len(devices) == 1 and devices[0].get("serial") == serial)

    def _consume_open_permit(
        self,
        permit: GuardianRuntimeDeviceOpenPermit,
        gateway: GuardianExecutionGatewayContract,
        runtime_trust: GuardianRuntimeTrust,
        runtime_private_key: Ed25519PrivateKey,
        *,
        consumed_at: datetime,
    ) -> None:
        claim = permit.verified_claim.claim
        payload: dict[str, object] = {
            "schema_version": self.OPEN_SCHEMA_VERSION,
            "permit_id": claim.device_open_permit_id,
            "consumed_at": consumed_at.isoformat(),
            "project_id": gateway.project_id,
            "gateway_contract_digest": gateway.contract_digest,
            "execution_claim_digest": claim.claim_digest,
            "device_key": gateway.device_key,
            "runtime_signer_key_id": runtime_trust.key_id,
            "open_token_sha256": claim.device_open_permit_token_sha256,
            "forward_scope_only": True,
            "recovery_authority_granted": False,
            "wipe_authority_granted": False,
            "bootloader_relock_allowed": False,
            "phone_changed": False,
        }
        payload["record_digest"] = execution_result_digest(payload)
        encoded = canonical_execution_result_bytes(payload)
        envelope: dict[str, object] = {
            "format": self.OPEN_FORMAT,
            "schema_version": self.OPEN_SCHEMA_VERSION,
            "algorithm": GuardianExecutionResultVerifier.ALGORITHM,
            "key_id": runtime_trust.key_id,
            "record_sha256": hashlib.sha256(encoded).hexdigest(),
            "record": payload,
            "signature": base64.b64encode(
                runtime_private_key.sign(self.OPEN_DOMAIN + encoded)
            ).decode("ascii"),
        }
        exclusive_create_json(
            self._open_path(gateway.project_id, claim.device_open_permit_id),
            envelope,
            boundary=self.claims.store.workspace,
            maximum_bytes=self.MAX_OPEN_RECORD_BYTES,
        )

    def _signed_result(
        self,
        *,
        receipt_id: str,
        started_at: datetime,
        completed_at: datetime,
        results: tuple[GuardianGatewayStepResult, ...],
        terminal_state: ExecutionTerminalState,
        gateway: GuardianExecutionGatewayContract,
        prerequisites: GuardianExecutionPrerequisiteBindings,
        runtime_trust: GuardianRuntimeTrust,
        runtime_private_key: Ed25519PrivateKey,
    ) -> dict[str, object]:
        attempted_steps = gateway.steps[: len(results)]
        passed = tuple(item.outcome is GatewayResultOutcome.PASSED for item in results)
        phone_change_attempted = any(step.phone_changes for step in attempted_steps)
        phone_change_verified = any(
            step.phone_changes and valid
            for step, valid in zip(attempted_steps, passed, strict=True)
        )
        phone_state_uncertain = any(
            step.phone_changes and not valid
            for step, valid in zip(attempted_steps, passed, strict=True)
        )
        forward_payload = [asdict(item) for item in results]
        receipt = GuardianExecutionResultReceipt(
            schema_version=GuardianExecutionResultVerifier.SCHEMA_VERSION,
            receipt_id=receipt_id,
            created_at=self._now().isoformat(),
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            gateway_contract_digest=gateway.contract_digest,
            project_id=gateway.project_id,
            plan_digest=gateway.plan_digest,
            manifest_digest=gateway.manifest_digest,
            artifact_binding_digest=gateway.artifact_binding_digest,
            device_key=gateway.device_key,
            device_pack_id=gateway.device_pack_id,
            device_pack_version=gateway.device_pack_version,
            device_pack_sha256=gateway.device_pack_sha256,
            live_target_receipt_digest=prerequisites.live_target_receipt_digest,
            final_consent_receipt_digest=prerequisites.final_consent_receipt_digest,
            runtime_signer_key_id=runtime_trust.key_id,
            runtime_adapter_id=runtime_trust.adapter_id,
            runtime_adapter_version=runtime_trust.adapter_version,
            runtime_adapter_sha256=runtime_trust.adapter_sha256,
            recorded_prewrite_slot=prerequisites.recorded_prewrite_slot,
            forward_result_count=len(results),
            forward_results_digest=execution_result_digest({"forward_results": forward_payload}),
            forward_results=results,
            recovery_invoked=False,
            recovery_consent_receipt_digest="",
            wipe_consent_receipt_digest="",
            recovery_result_count=0,
            recovery_results_digest=execution_result_digest({"recovery_results": []}),
            recovery_results=(),
            terminal_state=terminal_state,
            phone_change_attempted=phone_change_attempted,
            phone_change_verified=phone_change_verified,
            phone_state_uncertain=phone_state_uncertain,
            postconditions_verified=terminal_state is ExecutionTerminalState.SUCCEEDED,
            receipt_digest="",
        )
        unsigned = asdict(receipt)
        unsigned.pop("receipt_digest")
        receipt = GuardianExecutionResultReceipt(
            **unsigned,
            receipt_digest=execution_result_digest(unsigned),
        )
        raw_receipt = json.loads(canonical_execution_result_bytes(asdict(receipt)))
        encoded = canonical_execution_result_bytes(raw_receipt)
        return {
            "format": GuardianExecutionResultVerifier.FORMAT,
            "schema_version": GuardianExecutionResultVerifier.SCHEMA_VERSION,
            "algorithm": GuardianExecutionResultVerifier.ALGORITHM,
            "key_id": runtime_trust.key_id,
            "receipt_sha256": hashlib.sha256(encoded).hexdigest(),
            "receipt": raw_receipt,
            "signature": base64.b64encode(
                runtime_private_key.sign(GuardianExecutionResultVerifier.DOMAIN + encoded)
            ).decode("ascii"),
        }

    @staticmethod
    def _terminal_state(
        results: Sequence[GuardianGatewayStepResult],
        gateway: GuardianExecutionGatewayContract,
    ) -> ExecutionTerminalState:
        if results and results[-1].outcome is GatewayResultOutcome.FAILED:
            return ExecutionTerminalState.FAILED
        if len(results) == gateway.step_count:
            return ExecutionTerminalState.SUCCEEDED
        return ExecutionTerminalState.ABORTED

    @staticmethod
    def _evidence_matches(
        step: GuardianGatewayStep,
        *,
        observed_value: str,
        observed_size: int,
        observed_sha256: str,
    ) -> bool:
        if step.evidence_kind is GatewayEvidenceKind.COMMAND_EXIT_ZERO:
            return not observed_value and observed_size == 0 and not observed_sha256
        if step.evidence_kind is GatewayEvidenceKind.FILE_SIZE_AND_SHA256:
            return bool(
                not observed_value
                and observed_size == step.expected_size_bytes
                and observed_sha256 == step.expected_sha256
            )
        return bool(
            observed_value == step.expected_value and observed_size == 0 and not observed_sha256
        )

    @staticmethod
    def _validate_forward_scope(gateway: GuardianExecutionGatewayContract) -> None:
        if not gateway.steps:
            raise RuntimeForwardExecutionError("Guardian gateway contains no forward step")
        first = gateway.steps[0]
        commands = tuple((step.executable, *step.arguments) for step in gateway.steps)
        prohibited = {"erase", "format", "wipe", "unlock", "lock", "relock"}
        if (
            first.phase is not GatewayStepPhase.PRECONDITION
            or first.category is not OperationClass.READ_ONLY
            or first.phone_changes
            or contains_bootloader_relock(commands)
            or any(token.casefold() in prohibited for command in commands for token in command)
        ):
            raise RuntimeForwardExecutionError(
                "Guardian runtime accepts only an exact read-only-first forward gateway"
            )

    @staticmethod
    def _validate_private_key(
        public_key: Ed25519PublicKey,
        private_key: Ed25519PrivateKey,
    ) -> None:
        if not isinstance(public_key, Ed25519PublicKey) or not isinstance(
            private_key, Ed25519PrivateKey
        ):
            raise RuntimeForwardExecutionError("Runtime signing key is not enrolled")
        enrolled = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        signing = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        if not hmac.compare_digest(enrolled, signing):
            raise RuntimeForwardExecutionError("Runtime private key does not match enrolled trust")

    @staticmethod
    def _validated_tool(path: Path, expected_name: str) -> Path:
        candidate = path.expanduser()
        try:
            details = candidate.lstat()
        except OSError as exc:
            raise RuntimeForwardExecutionError(
                f"Trusted {expected_name} executable is unavailable"
            ) from exc
        if (
            stat.S_ISLNK(details.st_mode)
            or not stat.S_ISREG(details.st_mode)
            or candidate.name.casefold() not in {expected_name, f"{expected_name}.exe"}
            or (os.name != "nt" and not os.access(candidate, os.X_OK))
        ):
            raise RuntimeForwardExecutionError(
                f"Trusted {expected_name} executable is not a regular executable"
            )
        return candidate.resolve(strict=True)

    @staticmethod
    def _regular_file(path: Path, boundary: Path) -> os.stat_result:
        candidate = path.expanduser()
        root = boundary.expanduser().resolve(strict=True)
        try:
            lexical = candidate.absolute().relative_to(root)
            current = root
            for part in lexical.parts[:-1]:
                current /= part
                parent_details = current.lstat()
                if stat.S_ISLNK(parent_details.st_mode) or not stat.S_ISDIR(parent_details.st_mode):
                    raise RuntimeForwardExecutionError(
                        "Runtime file evidence escaped its private boundary"
                    )
            resolved = candidate.resolve(strict=True)
            details = candidate.lstat()
        except OSError as exc:
            raise RuntimeForwardExecutionError("Runtime file evidence is unavailable") from exc
        if (
            not resolved.is_relative_to(root)
            or stat.S_ISLNK(details.st_mode)
            or not stat.S_ISREG(details.st_mode)
        ):
            raise RuntimeForwardExecutionError("Runtime file evidence escaped its private boundary")
        return details

    @staticmethod
    def _inside(boundary: Path, relative: str) -> Path:
        if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise RuntimeForwardExecutionError("Runtime path is outside its exact boundary")
        root = boundary.expanduser().resolve(strict=True)
        candidate = root.joinpath(*Path(relative).parts)
        if not candidate.parent.resolve(strict=True).is_relative_to(root):
            raise RuntimeForwardExecutionError("Runtime path is outside its exact boundary")
        return candidate

    def _output_root(self, project_id: str, receipt_id: str) -> Path:
        self.claims.store.get(project_id)
        return (
            self.claims.store.projects_root
            / project_id
            / "guardian"
            / "runtime-results"
            / receipt_id
        )

    def _open_path(self, project_id: str, permit_id: str) -> Path:
        self.claims.store.get(project_id)
        return (
            self.claims.store.projects_root
            / project_id
            / "guardian"
            / f"runtime-device-open-{permit_id}.romverse"
        )

    def _result_path(self, project_id: str, receipt_id: str) -> Path:
        self.claims.store.get(project_id)
        return (
            self.claims.store.projects_root
            / project_id
            / "guardian"
            / f"execution-result-{receipt_id}.romverse"
        )

    def _run(self, args: Sequence[str], timeout: float) -> CommandResult:
        safe = tuple(str(item) for item in args)
        try:
            result = self.runner.run(safe, timeout=timeout)
        except (OSError, TypeError, ValueError):
            return CommandResult(safe, 127, "", "")
        if result.args != safe:
            return CommandResult(safe, 126, "", "")
        return result

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeForwardExecutionError("Runtime clock must be timezone-aware")
        return value.astimezone(UTC)

    @classmethod
    def _timeout(cls, step: GuardianGatewayStep) -> float:
        return float(step.timeout_seconds or cls.DEFAULT_COMMAND_TIMEOUT_SECONDS)

    @staticmethod
    def _clean_observed(value: str) -> str:
        return " ".join(value.replace("\x00", " ").split())[:512]

    @staticmethod
    def _text_sha256(value: str) -> str:
        return hashlib.sha256(value[-2_000_000:].encode("utf-8", errors="replace")).hexdigest()

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _error_code(exc: Exception) -> str:
        text = str(exc).casefold()
        if "artifact" in text:
            return "ARTIFACT_CHANGED"
        if "boundary" in text or "file evidence" in text:
            return "OUTPUT_UNSAFE"
        return "RUNTIME_VALIDATION_FAILED"
