from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path, PurePosixPath
from uuid import uuid4

from romverse.device.models import AndroidDevice
from romverse.device_packs.models import (
    DevicePostWriteVerificationContract,
    DeviceWriteContract,
    DeviceWriteTransport,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.artifact_binding import GuardianArtifactBindingService
from romverse.guardian.execution_plan import (
    ExecutionPlanPhase,
    GuardianExecutionPlan,
    GuardianExecutionPlanService,
)
from romverse.guardian.invariants import contains_bootloader_relock
from romverse.guardian.manifest_review import GuardianManifestReview
from romverse.guardian.models import OperationClass
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_json_object,
)
from romverse.infrastructure.process import CommandRunner, SubprocessRunner
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.readiness import BuildReadinessReport


class GatewayStepPhase(StrEnum):
    PRECONDITION = "precondition"
    WRITE = "write"
    READBACK = "readback"
    POST_BOOT = "post_boot"


class GatewayTransport(StrEnum):
    FASTBOOT = "fastboot"
    FASTBOOTD = "fastbootd"
    ADB = "adb"


class GatewayEvidenceKind(StrEnum):
    FASTBOOT_VARIABLE_EQUALS = "fastboot_variable_equals"
    COMMAND_EXIT_ZERO = "command_exit_zero"
    FILE_SIZE_AND_SHA256 = "file_size_and_sha256"
    ANDROID_PROPERTY_EQUALS = "android_property_equals"


@dataclass(frozen=True, slots=True)
class GuardianGatewayStep:
    """One exact but inert gateway operation and its required result evidence."""

    order: int
    operation_id: str
    phase: GatewayStepPhase
    category: OperationClass
    transport: GatewayTransport
    executable: str
    arguments: tuple[str, ...]
    partition: str
    target_slot: str
    artifact_relative_path: str
    artifact_sha256: str
    artifact_size_bytes: int
    output_relative_path: str
    property_name: str
    evidence_kind: GatewayEvidenceKind
    expected_value: str
    expected_size_bytes: int
    expected_sha256: str
    phone_changes: bool


@dataclass(frozen=True, slots=True)
class GuardianExecutionGatewayContract:
    """Tamper-evident execution/result template with zero runtime authority."""

    schema_version: int
    contract_id: str
    created_at: str
    project_id: str
    plan_id: str
    plan_digest: str
    manifest_digest: str
    artifact_binding_digest: str
    device_key: str
    device_pack_id: str
    device_pack_version: str
    device_pack_sha256: str
    write_contract_id: str
    write_contract_version: int
    write_attestation_sha256: str
    post_write_verification_contract_id: str
    post_write_verification_contract_version: int
    post_write_verification_contract_digest: str
    result_receipt_schema_version: int
    step_count: int
    write_count: int
    readback_count: int
    post_boot_property_count: int
    steps_digest: str
    steps: tuple[GuardianGatewayStep, ...]
    blockers: tuple[str, ...]
    contract_status: str
    final_consent_available: bool
    execution_authority: str
    runtime_invoked: bool
    phone_changed: bool
    contract_digest: str


def execution_plan_matches_manifest(
    plan: GuardianExecutionPlan | None,
    manifest: GuardianManifestReview,
) -> bool:
    """Match a validated inert plan to the exact command-free review it extends."""

    return bool(
        isinstance(plan, GuardianExecutionPlan)
        and plan.project_id == manifest.project_id
        and plan.handoff_digest == manifest.handoff_digest
        and plan.readiness_evidence_digest == manifest.readiness_evidence_digest
        and plan.manifest_digest == manifest.manifest_digest
        and plan.artifact_binding_digest == manifest.artifact_binding_digest
        and plan.source_sha256 == manifest.source_sha256
        and plan.device_key == manifest.device_key
        and plan.device_name == manifest.device_name
        and plan.codename == manifest.codename
        and plan.mode is manifest.mode
        and plan.device_pack_id == manifest.device_pack_id
        and plan.device_pack_version == manifest.device_pack_version
        and plan.device_pack_sha256 == manifest.device_pack_sha256
        and not plan.final_consent_available
        and plan.execution_authority == "none"
        and not plan.phone_changed
        and not plan.bootloader_relock_allowed
    )


def gateway_contract_matches_plan(
    contract: GuardianExecutionGatewayContract | None,
    plan: GuardianExecutionPlan | None,
) -> bool:
    """Match a validated inert gateway contract to its exact plan."""

    return bool(
        isinstance(contract, GuardianExecutionGatewayContract)
        and isinstance(plan, GuardianExecutionPlan)
        and contract.project_id == plan.project_id
        and contract.plan_id == plan.plan_id
        and contract.plan_digest == plan.plan_digest
        and contract.manifest_digest == plan.manifest_digest
        and contract.artifact_binding_digest == plan.artifact_binding_digest
        and contract.device_key == plan.device_key
        and contract.device_pack_id == plan.device_pack_id
        and contract.device_pack_version == plan.device_pack_version
        and contract.device_pack_sha256 == plan.device_pack_sha256
        and contract.write_contract_id == plan.write_contract_id
        and contract.write_contract_version == plan.write_contract_version
        and contract.write_attestation_sha256 == plan.write_attestation_sha256
        and contract.post_write_verification_contract_digest
        == plan.post_write_verification_contract_digest
        and not contract.final_consent_available
        and contract.execution_authority == "none"
        and not contract.runtime_invoked
        and not contract.phone_changed
    )


class GuardianExecutionGatewayContractService:
    """Compile a typed gateway boundary without running or authorizing any command."""

    FORMAT = "romverse.guardian-execution-gateway-contract"
    SCHEMA_VERSION = 1
    RESULT_RECEIPT_SCHEMA_VERSION = 1
    LATEST_NAME = "execution-gateway-contract.romverse"
    MAX_BYTES = 512 * 1024
    TARGET_TOKEN = GuardianExecutionPlanService.TARGET_TOKEN
    ADB_TARGET_TOKEN = "{CURRENT_EXACT_ADB_TARGET}"
    WORKSPACE_TOKEN = GuardianExecutionPlanService.WORKSPACE_TOKEN
    PRIVATE_OUTPUT_TOKEN = "{PRIVATE_VERIFICATION_OUTPUT}"
    STATUS = "blocked-missing-signed-transition-recovery-and-final-consent"
    BLOCKERS = (
        "This typed gateway contract is an inert command-and-result template; it ran no command, granted no execution authority, and is not an execution receipt.",
        "Exact signed mode transitions, slot activation, reboot, rollback and recovery orchestration, live target re-identification, final consent, and independent physical validation remain required.",
    )
    MAX_STEPS = GuardianArtifactBindingService.MAX_WRITES * 3 + 32

    def __init__(
        self,
        store: RomProjectStore,
        registry: DevicePackRegistry,
        tool_statuses: tuple[ToolStatus, ...] = (),
        avbtool: Path | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        self.store = store
        self.registry = registry
        self.tool_statuses = tool_statuses
        self.avbtool = avbtool
        self.runner = runner or SubprocessRunner()

    def compile(
        self,
        project_id: str,
        report: BuildReadinessReport,
        device: AndroidDevice,
        progress: Callable[[int], None] | None = None,
    ) -> GuardianExecutionGatewayContract:
        plan, write_contract, verification = self._current_context(
            project_id,
            report,
            device,
            progress,
        )
        steps = self._steps(plan, verification)
        steps_digest = _digest({"steps": [asdict(step) for step in steps]})
        payload: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "contract_id": uuid4().hex,
            "created_at": datetime.now(UTC).isoformat(),
            "project_id": plan.project_id,
            "plan_id": plan.plan_id,
            "plan_digest": plan.plan_digest,
            "manifest_digest": plan.manifest_digest,
            "artifact_binding_digest": plan.artifact_binding_digest,
            "device_key": plan.device_key,
            "device_pack_id": plan.device_pack_id,
            "device_pack_version": plan.device_pack_version,
            "device_pack_sha256": plan.device_pack_sha256,
            "write_contract_id": write_contract.contract_id,
            "write_contract_version": write_contract.version,
            "write_attestation_sha256": write_contract.attestation_sha256,
            "post_write_verification_contract_id": verification.contract_id,
            "post_write_verification_contract_version": verification.version,
            "post_write_verification_contract_digest": plan.post_write_verification_contract_digest,
            "result_receipt_schema_version": self.RESULT_RECEIPT_SCHEMA_VERSION,
            "step_count": len(steps),
            "write_count": sum(step.phase is GatewayStepPhase.WRITE for step in steps),
            "readback_count": sum(step.phase is GatewayStepPhase.READBACK for step in steps),
            "post_boot_property_count": sum(
                step.phase is GatewayStepPhase.POST_BOOT for step in steps
            ),
            "steps_digest": steps_digest,
            "steps": [asdict(step) for step in steps],
            "blockers": self.BLOCKERS,
            "contract_status": self.STATUS,
            "final_consent_available": False,
            "execution_authority": "none",
            "runtime_invoked": False,
            "phone_changed": False,
        }
        contract = GuardianExecutionGatewayContract(
            **{key: value for key, value in payload.items() if key != "steps"},
            steps=steps,
            contract_digest=_digest(payload),
        )
        self.validate(contract)
        self._write(contract)
        return contract

    def load(
        self,
        project_id: str,
        report: BuildReadinessReport,
        device: AndroidDevice,
        progress: Callable[[int], None] | None = None,
    ) -> GuardianExecutionGatewayContract | None:
        try:
            data = read_json_object(
                self._root(project_id) / self.LATEST_NAME,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            if (
                set(data)
                != {"format", *(field.name for field in fields(GuardianExecutionGatewayContract))}
                or data.pop("format") != self.FORMAT
            ):
                return None
            raw_steps = data.pop("steps")
            raw_blockers = data.get("blockers")
            step_fields = {field.name for field in fields(GuardianGatewayStep)}
            if (
                not isinstance(raw_steps, list)
                or not 1 <= len(raw_steps) <= self.MAX_STEPS
                or any(not isinstance(item, dict) or set(item) != step_fields for item in raw_steps)
                or not isinstance(raw_blockers, list)
                or any(type(item) is not str for item in raw_blockers)
            ):
                return None
            steps = tuple(
                GuardianGatewayStep(
                    **{
                        **item,
                        "phase": GatewayStepPhase(str(item["phase"])),
                        "category": OperationClass(str(item["category"])),
                        "transport": GatewayTransport(str(item["transport"])),
                        "evidence_kind": GatewayEvidenceKind(str(item["evidence_kind"])),
                        "arguments": tuple(item["arguments"]),
                    }
                )
                for item in raw_steps
            )
            data["blockers"] = tuple(raw_blockers)
            contract = GuardianExecutionGatewayContract(**data, steps=steps)
            self.validate(contract)
            plan, _write_contract, verification = self._current_context(
                project_id,
                report,
                device,
                progress,
            )
            if not self._matches(contract, plan, verification):
                return None
            return contract
        except (
            LocalStoreError,
            OSError,
            TypeError,
            ValueError,
            KeyError,
            ProjectError,
            json.JSONDecodeError,
        ):
            return None

    def validate(self, contract: GuardianExecutionGatewayContract) -> None:
        payload = asdict(contract)
        expected_contract_digest = str(payload.pop("contract_digest", ""))
        serialized_commands = tuple((step.executable, *step.arguments) for step in contract.steps)
        if (
            type(contract.schema_version) is not int
            or contract.schema_version != self.SCHEMA_VERSION
            or not _hex(contract.contract_id, 32)
            or not _aware_timestamp(contract.created_at)
            or not _clean(contract.project_id, 128)
            or not _hex(contract.plan_id, 32)
            or not _hex(contract.plan_digest, 64)
            or not _hex(contract.manifest_digest, 64)
            or not _hex(contract.artifact_binding_digest, 64)
            or not _hex(contract.device_key, 20)
            or not _clean(contract.device_pack_id, 128)
            or not _clean(contract.device_pack_version, 80)
            or not _hex(contract.device_pack_sha256, 64)
            or not _clean(contract.write_contract_id, 80)
            or type(contract.write_contract_version) is not int
            or contract.write_contract_version != 2
            or not _hex(contract.write_attestation_sha256, 64)
            or not _clean(contract.post_write_verification_contract_id, 80)
            or type(contract.post_write_verification_contract_version) is not int
            or contract.post_write_verification_contract_version != 1
            or not _hex(contract.post_write_verification_contract_digest, 64)
            or type(contract.result_receipt_schema_version) is not int
            or contract.result_receipt_schema_version != self.RESULT_RECEIPT_SCHEMA_VERSION
            or type(contract.step_count) is not int
            or contract.step_count != len(contract.steps)
            or not 1 <= contract.step_count <= self.MAX_STEPS
            or tuple(step.order for step in contract.steps)
            != tuple(range(1, len(contract.steps) + 1))
            or any(not self._valid_step(step) for step in contract.steps)
            or contains_bootloader_relock(serialized_commands)
            or self._contains_uncontracted_mutation(serialized_commands)
            or type(contract.write_count) is not int
            or contract.write_count
            != sum(step.phase is GatewayStepPhase.WRITE for step in contract.steps)
            or type(contract.readback_count) is not int
            or contract.readback_count
            != sum(step.phase is GatewayStepPhase.READBACK for step in contract.steps)
            or contract.readback_count != contract.write_count
            or type(contract.post_boot_property_count) is not int
            or contract.post_boot_property_count
            != sum(step.phase is GatewayStepPhase.POST_BOOT for step in contract.steps)
            or not 7 <= contract.post_boot_property_count <= 16
            or contract.steps_digest
            != _digest({"steps": [asdict(step) for step in contract.steps]})
            or contract.blockers != self.BLOCKERS
            or contract.contract_status != self.STATUS
            or type(contract.final_consent_available) is not bool
            or contract.final_consent_available
            or contract.execution_authority != "none"
            or type(contract.runtime_invoked) is not bool
            or contract.runtime_invoked
            or type(contract.phone_changed) is not bool
            or contract.phone_changed
            or not _hex(expected_contract_digest, 64)
            or expected_contract_digest != _digest(payload)
        ):
            raise ProjectError("Guardian execution gateway contract failed safety validation")

    def _current_context(
        self,
        project_id: str,
        report: BuildReadinessReport,
        device: AndroidDevice,
        progress: Callable[[int], None] | None = None,
    ) -> tuple[
        GuardianExecutionPlan,
        DeviceWriteContract,
        DevicePostWriteVerificationContract,
    ]:
        plan = GuardianExecutionPlanService(
            self.store,
            self.registry,
            self.tool_statuses,
            self.avbtool,
            self.runner,
        ).load(project_id, report, device, progress)
        if plan is None:
            raise ProjectError(
                "A current, exact Guardian execution plan is required before preparing the gateway contract"
            )
        pack = next(
            (item for item in self.registry.packs if item.pack_id == plan.device_pack_id),
            None,
        )
        write_contract = (
            pack.build_contract.partition_write_contract
            if pack is not None and pack.build_contract is not None
            else None
        )
        verification = (
            write_contract.post_write_verification_contract
            if write_contract is not None and write_contract.version == 2
            else None
        )
        if (
            write_contract is None
            or verification is None
            or plan.plan_status != GuardianExecutionPlanService.VERIFIED_CONTRACT_STATUS
            or plan.write_contract_id != write_contract.contract_id
            or plan.write_contract_version != write_contract.version
            or plan.write_attestation_sha256 != write_contract.attestation_sha256
            or plan.post_write_verification_contract_id != verification.contract_id
            or plan.post_write_verification_contract_version != verification.version
            or plan.post_write_verification_contract_digest != _digest(asdict(verification))
        ):
            raise ProjectError(
                "The signed schema-2 write and verification contract is not current and exact"
            )
        return plan, write_contract, verification

    @classmethod
    def _matches(
        cls,
        contract: GuardianExecutionGatewayContract,
        plan: GuardianExecutionPlan,
        verification: DevicePostWriteVerificationContract,
    ) -> bool:
        steps = cls._steps(plan, verification)
        return bool(
            contract.project_id == plan.project_id
            and contract.plan_id == plan.plan_id
            and contract.plan_digest == plan.plan_digest
            and contract.manifest_digest == plan.manifest_digest
            and contract.artifact_binding_digest == plan.artifact_binding_digest
            and contract.device_key == plan.device_key
            and contract.device_pack_id == plan.device_pack_id
            and contract.device_pack_version == plan.device_pack_version
            and contract.device_pack_sha256 == plan.device_pack_sha256
            and contract.write_contract_id == plan.write_contract_id
            and contract.write_contract_version == plan.write_contract_version
            and contract.write_attestation_sha256 == plan.write_attestation_sha256
            and contract.post_write_verification_contract_id
            == plan.post_write_verification_contract_id
            and contract.post_write_verification_contract_version
            == plan.post_write_verification_contract_version
            and contract.post_write_verification_contract_digest
            == plan.post_write_verification_contract_digest
            and contract.steps == steps
            and contract.steps_digest == _digest({"steps": [asdict(step) for step in steps]})
        )

    @classmethod
    def _steps(
        cls,
        plan: GuardianExecutionPlan,
        verification: DevicePostWriteVerificationContract,
    ) -> tuple[GuardianGatewayStep, ...]:
        steps: list[GuardianGatewayStep] = []

        def append(**values: object) -> None:
            steps.append(GuardianGatewayStep(order=len(steps) + 1, **values))

        write_index = 0
        for command in plan.commands:
            transport = GatewayTransport(command.transport.value)
            if command.phase is ExecutionPlanPhase.PRECONDITION:
                if command.arguments[-2:] == ("getvar", "product"):
                    expected = plan.codename
                elif command.arguments[-2:] == ("getvar", "unlocked"):
                    expected = "yes"
                elif command.arguments[-2:] == ("getvar", "is-userspace"):
                    expected = (
                        "yes" if command.transport is DeviceWriteTransport.FASTBOOTD else "no"
                    )
                else:
                    expected = "yes"
                append(
                    operation_id=command.operation_id,
                    phase=GatewayStepPhase.PRECONDITION,
                    category=OperationClass.READ_ONLY,
                    transport=transport,
                    executable=command.executable,
                    arguments=command.arguments,
                    partition=command.partition,
                    target_slot=command.target_slot,
                    artifact_relative_path="",
                    artifact_sha256="",
                    artifact_size_bytes=0,
                    output_relative_path="",
                    property_name="",
                    evidence_kind=GatewayEvidenceKind.FASTBOOT_VARIABLE_EQUALS,
                    expected_value=expected,
                    expected_size_bytes=0,
                    expected_sha256="",
                    phone_changes=False,
                )
                continue
            append(
                operation_id=command.operation_id,
                phase=GatewayStepPhase.WRITE,
                category=OperationClass.STATE_CHANGING,
                transport=transport,
                executable=command.executable,
                arguments=command.arguments,
                partition=command.partition,
                target_slot=command.target_slot,
                artifact_relative_path=command.artifact_relative_path,
                artifact_sha256=command.artifact_sha256,
                artifact_size_bytes=command.artifact_size_bytes,
                output_relative_path="",
                property_name="",
                evidence_kind=GatewayEvidenceKind.COMMAND_EXIT_ZERO,
                expected_value="0",
                expected_size_bytes=0,
                expected_sha256="",
                phone_changes=True,
            )
            write_index += 1
            rule = next(
                item
                for item in verification.readbacks
                if item.partition == command.partition
                and item.transport is command.transport
                and item.target_slot == command.target_slot
            )
            output_path = (
                f"readbacks/{write_index:02d}-{command.partition}-{command.target_slot}.img"
            )
            slot_arguments = ("--slot", rule.target_slot) if rule.target_slot != "none" else ()
            append(
                operation_id=f"guardian.verify.readback.{write_index:02d}.{command.partition}",
                phase=GatewayStepPhase.READBACK,
                category=OperationClass.READ_ONLY,
                transport=GatewayTransport(rule.transport.value),
                executable="fastboot",
                arguments=(
                    "-s",
                    cls.TARGET_TOKEN,
                    *slot_arguments,
                    "fetch",
                    rule.partition,
                    f"{cls.PRIVATE_OUTPUT_TOKEN}/{output_path}",
                ),
                partition=rule.partition,
                target_slot=rule.target_slot,
                artifact_relative_path="",
                artifact_sha256="",
                artifact_size_bytes=0,
                output_relative_path=output_path,
                property_name="",
                evidence_kind=GatewayEvidenceKind.FILE_SIZE_AND_SHA256,
                expected_value="",
                expected_size_bytes=rule.expected_size_bytes,
                expected_sha256=rule.expected_sha256,
                phone_changes=False,
            )

        for property_index, rule in enumerate(verification.post_boot_properties, 1):
            append(
                operation_id=f"guardian.verify.property.{property_index:02d}",
                phase=GatewayStepPhase.POST_BOOT,
                category=OperationClass.READ_ONLY,
                transport=GatewayTransport.ADB,
                executable="adb",
                arguments=(
                    "-s",
                    cls.ADB_TARGET_TOKEN,
                    "shell",
                    "getprop",
                    rule.property_name,
                ),
                partition="",
                target_slot="none",
                artifact_relative_path="",
                artifact_sha256="",
                artifact_size_bytes=0,
                output_relative_path="",
                property_name=rule.property_name,
                evidence_kind=GatewayEvidenceKind.ANDROID_PROPERTY_EQUALS,
                expected_value=rule.expected_value,
                expected_size_bytes=0,
                expected_sha256="",
                phone_changes=False,
            )
        return tuple(steps)

    @classmethod
    def _valid_step(cls, step: GuardianGatewayStep) -> bool:
        common = bool(
            type(step.order) is int
            and 1 <= step.order <= cls.MAX_STEPS
            and isinstance(step.operation_id, str)
            and re.fullmatch(r"[a-z0-9.-]{4,96}", step.operation_id)
            and isinstance(step.phase, GatewayStepPhase)
            and isinstance(step.category, OperationClass)
            and isinstance(step.transport, GatewayTransport)
            and step.executable in {"adb", "fastboot"}
            and 4 <= len(step.arguments) <= 9
            and all(_command_token(token) for token in step.arguments)
            and step.arguments[0] == "-s"
            and step.target_slot in {"a", "b", "none"}
            and type(step.artifact_size_bytes) is int
            and type(step.expected_size_bytes) is int
            and isinstance(step.evidence_kind, GatewayEvidenceKind)
            and type(step.phone_changes) is bool
        )
        if not common:
            return False
        if step.phase is GatewayStepPhase.PRECONDITION:
            product = step.arguments == ("-s", cls.TARGET_TOKEN, "getvar", "product")
            unlocked = step.arguments == ("-s", cls.TARGET_TOKEN, "getvar", "unlocked")
            userspace = step.arguments == (
                "-s",
                cls.TARGET_TOKEN,
                "getvar",
                "is-userspace",
            )
            has_slot = bool(
                _partition(step.partition)
                and step.target_slot in {"a", "b"}
                and step.arguments
                == (
                    "-s",
                    cls.TARGET_TOKEN,
                    "getvar",
                    f"has-slot:{step.partition}",
                )
            )
            expected_matches = bool(
                (product and _clean(step.expected_value, 80))
                or (unlocked and step.expected_value == "yes")
                or (userspace and step.expected_value in {"yes", "no"})
                or (has_slot and step.expected_value == "yes")
            )
            return bool(
                step.category is OperationClass.READ_ONLY
                and step.transport in {GatewayTransport.FASTBOOT, GatewayTransport.FASTBOOTD}
                and step.executable == "fastboot"
                and step.arguments[1] == cls.TARGET_TOKEN
                and expected_matches
                and step.evidence_kind is GatewayEvidenceKind.FASTBOOT_VARIABLE_EQUALS
                and _empty_payload_fields(step)
                and ((not step.partition and step.target_slot == "none") or has_slot)
                and not step.phone_changes
            )
        if step.phase is GatewayStepPhase.WRITE:
            artifact_token = f"{cls.WORKSPACE_TOKEN}/{step.artifact_relative_path}"
            expected_arguments = (
                "-s",
                cls.TARGET_TOKEN,
                *(("--slot", step.target_slot) if step.target_slot != "none" else ()),
                "flash",
                step.partition,
                artifact_token,
            )
            return bool(
                step.category is OperationClass.STATE_CHANGING
                and step.transport in {GatewayTransport.FASTBOOT, GatewayTransport.FASTBOOTD}
                and step.executable == "fastboot"
                and _partition(step.partition)
                and _safe_relative(step.artifact_relative_path)
                and _hex(step.artifact_sha256, 64)
                and 0
                < step.artifact_size_bytes
                <= GuardianArtifactBindingService.MAX_ARTIFACT_BYTES
                and step.arguments == expected_arguments
                and not step.output_relative_path
                and not step.property_name
                and step.evidence_kind is GatewayEvidenceKind.COMMAND_EXIT_ZERO
                and step.expected_value == "0"
                and step.expected_size_bytes == 0
                and not step.expected_sha256
                and step.phone_changes
            )
        if step.phase is GatewayStepPhase.READBACK:
            output_token = f"{cls.PRIVATE_OUTPUT_TOKEN}/{step.output_relative_path}"
            expected_arguments = (
                "-s",
                cls.TARGET_TOKEN,
                *(("--slot", step.target_slot) if step.target_slot != "none" else ()),
                "fetch",
                step.partition,
                output_token,
            )
            return bool(
                step.category is OperationClass.READ_ONLY
                and step.transport in {GatewayTransport.FASTBOOT, GatewayTransport.FASTBOOTD}
                and step.executable == "fastboot"
                and _partition(step.partition)
                and _safe_relative(step.output_relative_path)
                and step.arguments == expected_arguments
                and not step.artifact_relative_path
                and not step.artifact_sha256
                and step.artifact_size_bytes == 0
                and not step.property_name
                and step.evidence_kind is GatewayEvidenceKind.FILE_SIZE_AND_SHA256
                and not step.expected_value
                and 0 < step.expected_size_bytes <= 128 * 1024**3
                and step.expected_size_bytes % 512 == 0
                and _hex(step.expected_sha256, 64)
                and not step.phone_changes
            )
        return bool(
            step.phase is GatewayStepPhase.POST_BOOT
            and step.category is OperationClass.READ_ONLY
            and step.transport is GatewayTransport.ADB
            and step.executable == "adb"
            and step.arguments
            == (
                "-s",
                cls.ADB_TARGET_TOKEN,
                "shell",
                "getprop",
                step.property_name,
            )
            and not step.partition
            and step.target_slot == "none"
            and not step.artifact_relative_path
            and not step.artifact_sha256
            and step.artifact_size_bytes == 0
            and not step.output_relative_path
            and bool(re.fullmatch(r"[a-z0-9._-]{3,96}", step.property_name))
            and step.evidence_kind is GatewayEvidenceKind.ANDROID_PROPERTY_EQUALS
            and _clean(step.expected_value, 512)
            and step.expected_size_bytes == 0
            and not step.expected_sha256
            and not step.phone_changes
        )

    @staticmethod
    def _contains_uncontracted_mutation(commands: tuple[tuple[str, ...], ...]) -> bool:
        forbidden = {
            "delete-logical-partition",
            "erase",
            "flashing",
            "format",
            "oem",
            "reboot",
            "set_active",
            "set-active",
            "update",
            "wipe-super",
        }
        return any(token.casefold() in forbidden for command in commands for token in command)

    def _write(self, contract: GuardianExecutionGatewayContract) -> None:
        root = self._root(contract.project_id)
        ensure_private_directory(root, boundary=self.store.workspace)
        atomic_write_json(
            root / self.LATEST_NAME,
            {"format": self.FORMAT, **asdict(contract)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_BYTES,
        )

    def _root(self, project_id: str) -> Path:
        self.store.get(project_id)
        return self.store.projects_root / project_id / "guardian"


def _empty_payload_fields(step: GuardianGatewayStep) -> bool:
    return bool(
        not step.artifact_relative_path
        and not step.artifact_sha256
        and step.artifact_size_bytes == 0
        and not step.output_relative_path
        and not step.property_name
        and step.expected_size_bytes == 0
        and not step.expected_sha256
    )


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value))


def _clean(value: object, maximum: int) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= maximum and "\x00" not in value


def _command_token(value: object) -> bool:
    return bool(_clean(value, 512) and all(32 <= ord(character) < 127 for character in str(value)))


def _partition(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", value))


def _safe_relative(value: object) -> bool:
    if not _clean(value, 512) or "\\" in str(value):
        return False
    path = PurePosixPath(str(value))
    return bool(
        not path.is_absolute()
        and path.parts
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _aware_timestamp(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 80:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed <= datetime.now(UTC) + timedelta(minutes=5)


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
