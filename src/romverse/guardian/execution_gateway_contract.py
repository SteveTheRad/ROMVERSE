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
    DeviceMode,
    DeviceModeTransitionRule,
    DevicePostWriteVerificationContract,
    DeviceRecoveryActionRule,
    DeviceRecoveryContract,
    DeviceRecoveryOperation,
    DeviceRecoveryStrategy,
    DeviceTransitionOperation,
    DeviceTransitionRecoveryContract,
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
    TRANSITION = "transition"
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
    DEVICE_MODE_EQUALS = "device_mode_equals"
    ACTIVE_SLOT_EQUALS = "active_slot_equals"


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
    transition_operation: DeviceTransitionOperation | None
    transition_order: int
    after_write_order: int
    from_mode: DeviceMode | None
    to_mode: DeviceMode | None
    timeout_seconds: int
    phone_changes: bool


@dataclass(frozen=True, slots=True)
class GuardianGatewayRecoveryStep:
    """One signed adapter action for contingency review, never a raw command."""

    order: int
    operation: DeviceRecoveryOperation
    adapter_action_id: str
    from_mode: DeviceMode
    to_mode: DeviceMode
    target_slot: str
    timeout_seconds: int
    may_wipe_user_data: bool
    phone_changes_if_executed: bool


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
    transition_recovery_contract_id: str
    transition_recovery_contract_version: int
    transition_recovery_contract_digest: str
    transition_source_build_id: str
    transition_attestation_sha256: str
    transition_entry_mode: str
    transition_final_mode: str
    transition_final_consent_required: bool
    transition_execution_authority: str
    transition_bootloader_relock_allowed: bool
    result_receipt_schema_version: int
    step_count: int
    write_count: int
    readback_count: int
    post_boot_property_count: int
    mode_transition_count: int
    steps_digest: str
    steps: tuple[GuardianGatewayStep, ...]
    recovery_action_count: int
    recovery_strategy: str
    recovery_adapter_id: str
    recovery_stock_package_sha256: str
    recovery_entry_mode: str
    recovery_require_external_backup: bool
    recovery_require_stock_recovery: bool
    recovery_require_prewrite_slot_capture: bool
    recovery_may_wipe_user_data: bool
    recovery_automatic_wipe_allowed: bool
    recovery_bootloader_relock_allowed: bool
    recovery_steps_digest: str
    recovery_steps: tuple[GuardianGatewayRecoveryStep, ...]
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

    try:
        if isinstance(contract, GuardianExecutionGatewayContract):
            GuardianExecutionGatewayContractService.validate(contract)
    except ProjectError:
        return False
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
        and contract.transition_recovery_contract_id == plan.transition_recovery_contract_id
        and contract.transition_recovery_contract_version
        == plan.transition_recovery_contract_version
        and contract.transition_recovery_contract_digest == plan.transition_recovery_contract_digest
        and contract.mode_transition_count == plan.mode_transition_count
        and contract.recovery_action_count == plan.recovery_action_count
        and contract.recovery_adapter_id == plan.recovery_adapter_id
        and contract.recovery_stock_package_sha256 == plan.recovery_stock_package_sha256
        and contract.recovery_may_wipe_user_data is plan.recovery_may_wipe_user_data
        and not contract.final_consent_available
        and contract.execution_authority == "none"
        and not contract.runtime_invoked
        and not contract.phone_changed
    )


class GuardianExecutionGatewayContractService:
    """Compile a typed gateway boundary without running or authorizing any command."""

    FORMAT = "romverse.guardian-execution-gateway-contract"
    SCHEMA_VERSION = 2
    RESULT_RECEIPT_SCHEMA_VERSION = 2
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
    ORCHESTRATED_STATUS = "blocked-missing-live-runtime-receipts-and-final-consent"
    ORCHESTRATED_BLOCKERS = (
        "This transition-aware gateway is an inert command, recovery, and result template; it ran no command, granted no execution authority, and is not an execution receipt.",
        "The signed Device Pack supplies exact mode changes and source-bound stock recovery. Live target re-identification, a governed runtime, immutable execution/postcondition receipts, separate final consent, and independent physical validation remain required.",
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
        plan, write_contract, verification, transition = self._current_context(
            project_id,
            report,
            device,
            progress,
        )
        steps = self._steps(plan, verification, transition)
        recovery_steps = self._recovery_steps(transition)
        steps_digest = _digest({"steps": [asdict(step) for step in steps]})
        recovery_steps_digest = _digest(
            {"recovery_steps": [asdict(step) for step in recovery_steps]}
        )
        transition_metadata = self._transition_metadata(transition)
        blockers, contract_status = self._boundary(write_contract.version)
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
            **transition_metadata,
            "result_receipt_schema_version": self.RESULT_RECEIPT_SCHEMA_VERSION,
            "step_count": len(steps),
            "write_count": sum(step.phase is GatewayStepPhase.WRITE for step in steps),
            "readback_count": sum(step.phase is GatewayStepPhase.READBACK for step in steps),
            "post_boot_property_count": sum(
                step.phase is GatewayStepPhase.POST_BOOT for step in steps
            ),
            "mode_transition_count": sum(
                step.phase is GatewayStepPhase.TRANSITION for step in steps
            ),
            "steps_digest": steps_digest,
            "steps": [asdict(step) for step in steps],
            "recovery_steps_digest": recovery_steps_digest,
            "recovery_steps": [asdict(step) for step in recovery_steps],
            "blockers": blockers,
            "contract_status": contract_status,
            "final_consent_available": False,
            "execution_authority": "none",
            "runtime_invoked": False,
            "phone_changed": False,
        }
        contract = GuardianExecutionGatewayContract(
            **{
                key: value
                for key, value in payload.items()
                if key not in {"steps", "recovery_steps"}
            },
            steps=steps,
            recovery_steps=recovery_steps,
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
            raw_recovery_steps = data.pop("recovery_steps")
            raw_blockers = data.get("blockers")
            step_fields = {field.name for field in fields(GuardianGatewayStep)}
            recovery_step_fields = {field.name for field in fields(GuardianGatewayRecoveryStep)}
            if (
                not isinstance(raw_steps, list)
                or not 1 <= len(raw_steps) <= self.MAX_STEPS
                or any(not isinstance(item, dict) or set(item) != step_fields for item in raw_steps)
                or not isinstance(raw_recovery_steps, list)
                or len(raw_recovery_steps) > 16
                or any(
                    not isinstance(item, dict) or set(item) != recovery_step_fields
                    for item in raw_recovery_steps
                )
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
                        "transition_operation": (
                            DeviceTransitionOperation(str(item["transition_operation"]))
                            if item["transition_operation"] is not None
                            else None
                        ),
                        "from_mode": (
                            DeviceMode(str(item["from_mode"]))
                            if item["from_mode"] is not None
                            else None
                        ),
                        "to_mode": (
                            DeviceMode(str(item["to_mode"]))
                            if item["to_mode"] is not None
                            else None
                        ),
                    }
                )
                for item in raw_steps
            )
            recovery_steps = tuple(
                GuardianGatewayRecoveryStep(
                    **{
                        **item,
                        "operation": DeviceRecoveryOperation(str(item["operation"])),
                        "from_mode": DeviceMode(str(item["from_mode"])),
                        "to_mode": DeviceMode(str(item["to_mode"])),
                    }
                )
                for item in raw_recovery_steps
            )
            data["blockers"] = tuple(raw_blockers)
            contract = GuardianExecutionGatewayContract(
                **data,
                steps=steps,
                recovery_steps=recovery_steps,
            )
            self.validate(contract)
            plan, _write_contract, verification, transition = self._current_context(
                project_id,
                report,
                device,
                progress,
            )
            if not self._matches(contract, plan, verification, transition):
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

    @classmethod
    def validate(cls, contract: GuardianExecutionGatewayContract) -> None:
        payload = asdict(contract)
        expected_contract_digest = str(payload.pop("contract_digest", ""))
        serialized_commands = tuple((step.executable, *step.arguments) for step in contract.steps)
        if (
            type(contract.schema_version) is not int
            or contract.schema_version != cls.SCHEMA_VERSION
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
            or contract.write_contract_version not in {2, 3}
            or not _hex(contract.write_attestation_sha256, 64)
            or not _clean(contract.post_write_verification_contract_id, 80)
            or type(contract.post_write_verification_contract_version) is not int
            or contract.post_write_verification_contract_version != 1
            or not _hex(contract.post_write_verification_contract_digest, 64)
            or not cls._valid_contract_boundary(contract)
            or type(contract.result_receipt_schema_version) is not int
            or contract.result_receipt_schema_version != cls.RESULT_RECEIPT_SCHEMA_VERSION
            or type(contract.step_count) is not int
            or contract.step_count != len(contract.steps)
            or not 1 <= contract.step_count <= cls.MAX_STEPS
            or tuple(step.order for step in contract.steps)
            != tuple(range(1, len(contract.steps) + 1))
            or any(not cls._valid_step(step) for step in contract.steps)
            or contains_bootloader_relock(serialized_commands)
            or cls._contains_uncontracted_mutation(contract.steps)
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
            or type(contract.mode_transition_count) is not int
            or contract.mode_transition_count
            != sum(step.phase is GatewayStepPhase.TRANSITION for step in contract.steps)
            or not cls._valid_step_sequence(contract)
            or contract.steps_digest
            != _digest({"steps": [asdict(step) for step in contract.steps]})
            or type(contract.recovery_action_count) is not int
            or contract.recovery_action_count != len(contract.recovery_steps)
            or tuple(step.order for step in contract.recovery_steps)
            != tuple(range(1, len(contract.recovery_steps) + 1))
            or any(
                not cls._valid_recovery_step(step, contract.recovery_adapter_id)
                for step in contract.recovery_steps
            )
            or not cls._valid_recovery_sequence(contract)
            or contract.recovery_steps_digest
            != _digest({"recovery_steps": [asdict(step) for step in contract.recovery_steps]})
            or (contract.blockers, contract.contract_status)
            != cls._boundary(contract.write_contract_version)
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

    @classmethod
    def _boundary(cls, write_contract_version: int) -> tuple[tuple[str, ...], str]:
        if write_contract_version == 3:
            return cls.ORCHESTRATED_BLOCKERS, cls.ORCHESTRATED_STATUS
        return cls.BLOCKERS, cls.STATUS

    @classmethod
    def _valid_contract_boundary(cls, contract: GuardianExecutionGatewayContract) -> bool:
        boolean_fields = (
            contract.transition_final_consent_required,
            contract.transition_bootloader_relock_allowed,
            contract.recovery_require_external_backup,
            contract.recovery_require_stock_recovery,
            contract.recovery_require_prewrite_slot_capture,
            contract.recovery_may_wipe_user_data,
            contract.recovery_automatic_wipe_allowed,
            contract.recovery_bootloader_relock_allowed,
        )
        if any(type(value) is not bool for value in boolean_fields):
            return False
        if contract.write_contract_version == 2:
            return bool(
                not contract.transition_recovery_contract_id
                and type(contract.transition_recovery_contract_version) is int
                and contract.transition_recovery_contract_version == 0
                and not contract.transition_recovery_contract_digest
                and not contract.transition_source_build_id
                and not contract.transition_attestation_sha256
                and not contract.transition_entry_mode
                and not contract.transition_final_mode
                and not contract.transition_execution_authority
                and contract.mode_transition_count == 0
                and contract.recovery_action_count == 0
                and not contract.recovery_strategy
                and not contract.recovery_adapter_id
                and not contract.recovery_stock_package_sha256
                and not contract.recovery_entry_mode
                and not any(boolean_fields)
                and not contract.recovery_steps
            )
        return bool(
            _clean(contract.transition_recovery_contract_id, 80)
            and type(contract.transition_recovery_contract_version) is int
            and contract.transition_recovery_contract_version == 1
            and _hex(contract.transition_recovery_contract_digest, 64)
            and _clean(contract.transition_source_build_id, 160)
            and contract.transition_attestation_sha256 == contract.write_attestation_sha256
            and contract.transition_entry_mode
            in {DeviceMode.BOOTLOADER.value, DeviceMode.FASTBOOTD.value}
            and contract.transition_final_mode == DeviceMode.ANDROID.value
            and contract.transition_final_consent_required
            and contract.transition_execution_authority == "none"
            and not contract.transition_bootloader_relock_allowed
            and 1 <= contract.mode_transition_count <= contract.write_count * 2 + 3
            and 2 <= contract.recovery_action_count <= 16
            and contract.recovery_strategy in {item.value for item in DeviceRecoveryStrategy}
            and _clean(contract.recovery_adapter_id, 80)
            and "relock" not in contract.recovery_adapter_id.casefold()
            and _hex(contract.recovery_stock_package_sha256, 64)
            and contract.recovery_entry_mode
            in {DeviceMode.BOOTLOADER.value, DeviceMode.FASTBOOTD.value}
            and contract.recovery_require_external_backup
            and contract.recovery_require_stock_recovery
            and not contract.recovery_automatic_wipe_allowed
            and not contract.recovery_bootloader_relock_allowed
            and cls._transition_digest_matches(contract)
        )

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
        DeviceTransitionRecoveryContract | None,
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
            if write_contract is not None and write_contract.version in {2, 3}
            else None
        )
        transition = (
            write_contract.transition_recovery_contract
            if write_contract is not None and write_contract.version == 3
            else None
        )
        expected_status = (
            GuardianExecutionPlanService.ORCHESTRATED_CONTRACT_STATUS
            if transition is not None
            else GuardianExecutionPlanService.VERIFIED_CONTRACT_STATUS
        )
        if (
            write_contract is None
            or verification is None
            or write_contract.version not in {2, 3}
            or plan.plan_status != expected_status
            or plan.write_contract_id != write_contract.contract_id
            or plan.write_contract_version != write_contract.version
            or plan.write_attestation_sha256 != write_contract.attestation_sha256
            or plan.post_write_verification_contract_id != verification.contract_id
            or plan.post_write_verification_contract_version != verification.version
            or plan.post_write_verification_contract_digest != _digest(asdict(verification))
            or (
                write_contract.version == 3
                and (
                    transition is None
                    or pack is None
                    or pack.build_contract is None
                    or not DevicePackRegistry.transition_recovery_contract_is_valid(
                        write_contract,
                        pack.build_contract.source,
                    )
                    or plan.transition_recovery_contract_id != transition.contract_id
                    or plan.transition_recovery_contract_version != transition.version
                    or plan.transition_recovery_contract_digest != _digest(asdict(transition))
                    or plan.mode_transition_count != len(transition.transitions)
                    or plan.recovery_action_count != len(transition.recovery.actions)
                    or plan.recovery_adapter_id != transition.recovery.adapter_id
                    or plan.recovery_stock_package_sha256
                    != transition.recovery.stock_package_sha256
                    or plan.recovery_may_wipe_user_data
                    is not transition.recovery.may_wipe_user_data
                )
            )
            or (
                write_contract.version == 2
                and write_contract.transition_recovery_contract is not None
            )
        ):
            raise ProjectError(
                "The signed schema-2/3 write, verification, and transition contract is not current and exact"
            )
        return plan, write_contract, verification, transition

    @classmethod
    def _matches(
        cls,
        contract: GuardianExecutionGatewayContract,
        plan: GuardianExecutionPlan,
        verification: DevicePostWriteVerificationContract,
        transition: DeviceTransitionRecoveryContract | None,
    ) -> bool:
        steps = cls._steps(plan, verification, transition)
        recovery_steps = cls._recovery_steps(transition)
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
            and contract.transition_recovery_contract_id == plan.transition_recovery_contract_id
            and contract.transition_recovery_contract_version
            == plan.transition_recovery_contract_version
            and contract.transition_recovery_contract_digest
            == plan.transition_recovery_contract_digest
            and contract.mode_transition_count == plan.mode_transition_count
            and contract.recovery_action_count == plan.recovery_action_count
            and contract.recovery_adapter_id == plan.recovery_adapter_id
            and contract.recovery_stock_package_sha256 == plan.recovery_stock_package_sha256
            and contract.recovery_may_wipe_user_data is plan.recovery_may_wipe_user_data
            and contract.steps == steps
            and contract.steps_digest == _digest({"steps": [asdict(step) for step in steps]})
            and contract.recovery_steps == recovery_steps
            and contract.recovery_steps_digest
            == _digest({"recovery_steps": [asdict(step) for step in recovery_steps]})
        )

    @classmethod
    def _transition_metadata(
        cls,
        transition: DeviceTransitionRecoveryContract | None,
    ) -> dict[str, object]:
        if transition is None:
            return {
                "transition_recovery_contract_id": "",
                "transition_recovery_contract_version": 0,
                "transition_recovery_contract_digest": "",
                "transition_source_build_id": "",
                "transition_attestation_sha256": "",
                "transition_entry_mode": "",
                "transition_final_mode": "",
                "transition_final_consent_required": False,
                "transition_execution_authority": "",
                "transition_bootloader_relock_allowed": False,
                "recovery_action_count": 0,
                "recovery_strategy": "",
                "recovery_adapter_id": "",
                "recovery_stock_package_sha256": "",
                "recovery_entry_mode": "",
                "recovery_require_external_backup": False,
                "recovery_require_stock_recovery": False,
                "recovery_require_prewrite_slot_capture": False,
                "recovery_may_wipe_user_data": False,
                "recovery_automatic_wipe_allowed": False,
                "recovery_bootloader_relock_allowed": False,
            }
        recovery = transition.recovery
        return {
            "transition_recovery_contract_id": transition.contract_id,
            "transition_recovery_contract_version": transition.version,
            "transition_recovery_contract_digest": _digest(asdict(transition)),
            "transition_source_build_id": transition.source_build_id,
            "transition_attestation_sha256": transition.attestation_sha256,
            "transition_entry_mode": transition.entry_mode.value,
            "transition_final_mode": transition.final_mode.value,
            "transition_final_consent_required": transition.final_consent_required,
            "transition_execution_authority": transition.execution_authority,
            "transition_bootloader_relock_allowed": transition.bootloader_relock_allowed,
            "recovery_action_count": len(recovery.actions),
            "recovery_strategy": recovery.strategy.value,
            "recovery_adapter_id": recovery.adapter_id,
            "recovery_stock_package_sha256": recovery.stock_package_sha256,
            "recovery_entry_mode": recovery.entry_mode.value,
            "recovery_require_external_backup": recovery.require_external_backup,
            "recovery_require_stock_recovery": recovery.require_stock_recovery,
            "recovery_require_prewrite_slot_capture": recovery.require_prewrite_slot_capture,
            "recovery_may_wipe_user_data": recovery.may_wipe_user_data,
            "recovery_automatic_wipe_allowed": recovery.automatic_wipe_allowed,
            "recovery_bootloader_relock_allowed": recovery.bootloader_relock_allowed,
        }

    @classmethod
    def _recovery_steps(
        cls,
        transition: DeviceTransitionRecoveryContract | None,
    ) -> tuple[GuardianGatewayRecoveryStep, ...]:
        if transition is None:
            return ()
        return tuple(
            GuardianGatewayRecoveryStep(
                order=rule.order,
                operation=rule.operation,
                adapter_action_id=rule.adapter_action_id,
                from_mode=rule.from_mode,
                to_mode=rule.to_mode,
                target_slot=rule.target_slot,
                timeout_seconds=rule.timeout_seconds,
                may_wipe_user_data=rule.may_wipe_user_data,
                phone_changes_if_executed=(
                    rule.operation is not DeviceRecoveryOperation.VERIFY_POST_BOOT
                ),
            )
            for rule in transition.recovery.actions
        )

    @classmethod
    def _steps(
        cls,
        plan: GuardianExecutionPlan,
        verification: DevicePostWriteVerificationContract,
        transition: DeviceTransitionRecoveryContract | None = None,
    ) -> tuple[GuardianGatewayStep, ...]:
        steps: list[GuardianGatewayStep] = []

        def append(**values: object) -> None:
            steps.append(GuardianGatewayStep(order=len(steps) + 1, **values))

        def append_precondition(command, *, entry: bool = False) -> None:
            if command.arguments[-2:] == ("getvar", "product"):
                expected = plan.codename
            elif command.arguments[-2:] == ("getvar", "unlocked"):
                expected = "yes"
            elif command.arguments[-2:] == ("getvar", "is-userspace"):
                expected = "yes" if command.transport is DeviceWriteTransport.FASTBOOTD else "no"
            else:
                expected = "yes"
            transport = GatewayTransport(command.transport.value)
            if entry and transition is not None:
                transport = cls._transport_for_mode(transition.entry_mode)
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
                transition_operation=None,
                transition_order=0,
                after_write_order=0,
                from_mode=None,
                to_mode=None,
                timeout_seconds=0,
                phone_changes=False,
            )

        transitions_by_boundary: dict[int, list[DeviceModeTransitionRule]] = {}
        if transition is not None:
            for rule in transition.transitions:
                transitions_by_boundary.setdefault(rule.after_write_order, []).append(rule)

        def append_transitions(boundary: int) -> None:
            for rule in transitions_by_boundary.get(boundary, ()):
                append(
                    operation_id=(
                        f"guardian.transition.{rule.order:02d}."
                        f"{rule.operation.value.replace('_', '-')}"
                    ),
                    phase=GatewayStepPhase.TRANSITION,
                    category=OperationClass.STATE_CHANGING,
                    transport=cls._transport_for_mode(rule.from_mode),
                    executable="fastboot",
                    arguments=cls._transition_arguments(rule),
                    partition="",
                    target_slot=rule.target_slot,
                    artifact_relative_path="",
                    artifact_sha256="",
                    artifact_size_bytes=0,
                    output_relative_path="",
                    property_name="",
                    evidence_kind=(
                        GatewayEvidenceKind.ACTIVE_SLOT_EQUALS
                        if rule.operation is DeviceTransitionOperation.SET_ACTIVE_SLOT
                        else GatewayEvidenceKind.DEVICE_MODE_EQUALS
                    ),
                    expected_value=(
                        rule.target_slot
                        if rule.operation is DeviceTransitionOperation.SET_ACTIVE_SLOT
                        else rule.to_mode.value
                    ),
                    expected_size_bytes=0,
                    expected_sha256="",
                    transition_operation=rule.operation,
                    transition_order=rule.order,
                    after_write_order=rule.after_write_order,
                    from_mode=rule.from_mode,
                    to_mode=rule.to_mode,
                    timeout_seconds=rule.timeout_seconds,
                    phone_changes=True,
                )

        global_ids = {"guardian.preflight.product", "guardian.preflight.unlocked"}
        pending_preconditions = []
        write_index = 0
        for command in plan.commands:
            if command.phase is ExecutionPlanPhase.PRECONDITION:
                if command.operation_id in global_ids:
                    append_precondition(command, entry=True)
                else:
                    pending_preconditions.append(command)
                continue
            append_transitions(write_index)
            for precondition in pending_preconditions:
                append_precondition(precondition)
            pending_preconditions.clear()
            transport = GatewayTransport(command.transport.value)
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
                transition_operation=None,
                transition_order=0,
                after_write_order=0,
                from_mode=None,
                to_mode=None,
                timeout_seconds=0,
                phone_changes=True,
            )
            write_index += 1
            rule = next(
                (
                    item
                    for item in verification.readbacks
                    if item.partition == command.partition
                    and item.transport is command.transport
                    and item.target_slot == command.target_slot
                ),
                None,
            )
            if rule is None:
                raise ProjectError(
                    f"Signed verification is missing the exact readback for {command.partition}"
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
                transition_operation=None,
                transition_order=0,
                after_write_order=0,
                from_mode=None,
                to_mode=None,
                timeout_seconds=0,
                phone_changes=False,
            )

        if pending_preconditions:
            raise ProjectError("Guardian plan contains preconditions without a following write")
        append_transitions(write_index)

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
                transition_operation=None,
                transition_order=0,
                after_write_order=0,
                from_mode=None,
                to_mode=None,
                timeout_seconds=0,
                phone_changes=False,
            )
        return tuple(steps)

    @classmethod
    def _transport_for_mode(cls, mode: DeviceMode) -> GatewayTransport:
        return (
            GatewayTransport.FASTBOOTD
            if mode is DeviceMode.FASTBOOTD
            else GatewayTransport.FASTBOOT
        )

    @classmethod
    def _transition_arguments(cls, rule: DeviceModeTransitionRule) -> tuple[str, ...]:
        suffix = {
            DeviceTransitionOperation.REBOOT_FASTBOOTD: ("reboot", "fastboot"),
            DeviceTransitionOperation.REBOOT_BOOTLOADER: ("reboot", "bootloader"),
            DeviceTransitionOperation.SET_ACTIVE_SLOT: ("set_active", rule.target_slot),
            DeviceTransitionOperation.REBOOT_SYSTEM: ("reboot",),
        }[rule.operation]
        return ("-s", cls.TARGET_TOKEN, *suffix)

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
            and 3 <= len(step.arguments) <= 9
            and all(_command_token(token) for token in step.arguments)
            and step.arguments[0] == "-s"
            and step.target_slot in {"a", "b", "none"}
            and type(step.artifact_size_bytes) is int
            and type(step.expected_size_bytes) is int
            and type(step.transition_order) is int
            and type(step.after_write_order) is int
            and type(step.timeout_seconds) is int
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
                and _empty_transition_fields(step)
                and not step.phone_changes
            )
        if step.phase is GatewayStepPhase.TRANSITION:
            if (
                not isinstance(step.transition_operation, DeviceTransitionOperation)
                or not isinstance(step.from_mode, DeviceMode)
                or not isinstance(step.to_mode, DeviceMode)
            ):
                return False
            rule = DeviceModeTransitionRule(
                order=step.transition_order,
                after_write_order=step.after_write_order,
                operation=step.transition_operation,
                from_mode=step.from_mode,
                to_mode=step.to_mode,
                target_slot=step.target_slot,
                timeout_seconds=step.timeout_seconds,
            )
            expected_evidence = (
                GatewayEvidenceKind.ACTIVE_SLOT_EQUALS
                if step.transition_operation is DeviceTransitionOperation.SET_ACTIVE_SLOT
                else GatewayEvidenceKind.DEVICE_MODE_EQUALS
            )
            expected_value = (
                step.target_slot
                if step.transition_operation is DeviceTransitionOperation.SET_ACTIVE_SLOT
                else step.to_mode.value
            )
            return bool(
                step.category is OperationClass.STATE_CHANGING
                and step.transport is cls._transport_for_mode(step.from_mode)
                and step.executable == "fastboot"
                and step.arguments == cls._transition_arguments(rule)
                and not step.partition
                and not step.artifact_relative_path
                and not step.artifact_sha256
                and step.artifact_size_bytes == 0
                and not step.output_relative_path
                and not step.property_name
                and step.evidence_kind is expected_evidence
                and step.expected_value == expected_value
                and step.expected_size_bytes == 0
                and not step.expected_sha256
                and 5 <= step.timeout_seconds <= 600
                and cls._valid_transition_shape(step)
                and step.phone_changes
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
                and _empty_transition_fields(step)
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
                and _empty_transition_fields(step)
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
            and _empty_transition_fields(step)
            and not step.phone_changes
        )

    @staticmethod
    def _valid_transition_shape(step: GuardianGatewayStep) -> bool:
        operation = step.transition_operation
        if operation is DeviceTransitionOperation.REBOOT_FASTBOOTD:
            return bool(
                step.from_mode is DeviceMode.BOOTLOADER
                and step.to_mode is DeviceMode.FASTBOOTD
                and step.target_slot == "none"
            )
        if operation is DeviceTransitionOperation.REBOOT_BOOTLOADER:
            return bool(
                step.from_mode is DeviceMode.FASTBOOTD
                and step.to_mode is DeviceMode.BOOTLOADER
                and step.target_slot == "none"
            )
        if operation is DeviceTransitionOperation.SET_ACTIVE_SLOT:
            return bool(
                step.from_mode in {DeviceMode.BOOTLOADER, DeviceMode.FASTBOOTD}
                and step.to_mode is step.from_mode
                and step.target_slot in {"a", "b"}
            )
        return bool(
            operation is DeviceTransitionOperation.REBOOT_SYSTEM
            and step.from_mode in {DeviceMode.BOOTLOADER, DeviceMode.FASTBOOTD}
            and step.to_mode is DeviceMode.ANDROID
            and step.target_slot == "none"
        )

    @classmethod
    def _valid_step_sequence(cls, contract: GuardianExecutionGatewayContract) -> bool:
        post_boot_started = False
        for index, step in enumerate(contract.steps):
            if step.phase is GatewayStepPhase.POST_BOOT:
                post_boot_started = True
            elif post_boot_started:
                return False
            if step.phase is GatewayStepPhase.WRITE:
                if index + 1 >= len(contract.steps):
                    return False
                readback = contract.steps[index + 1]
                if (
                    readback.phase is not GatewayStepPhase.READBACK
                    or readback.partition != step.partition
                    or readback.target_slot != step.target_slot
                    or readback.transport is not step.transport
                ):
                    return False
        transitions = tuple(
            step for step in contract.steps if step.phase is GatewayStepPhase.TRANSITION
        )
        if contract.write_contract_version == 2:
            return not transitions
        try:
            current_mode = DeviceMode(contract.transition_entry_mode)
            final_mode = DeviceMode(contract.transition_final_mode)
        except ValueError:
            return False
        transition_index = 0
        writes_seen = 0
        for step in contract.steps:
            if step.phase is GatewayStepPhase.TRANSITION:
                transition_index += 1
                expected_operation_id = (
                    f"guardian.transition.{transition_index:02d}."
                    f"{step.transition_operation.value.replace('_', '-')}"
                )
                if (
                    step.transition_order != transition_index
                    or step.after_write_order != writes_seen
                    or step.operation_id != expected_operation_id
                    or step.from_mode is not current_mode
                ):
                    return False
                current_mode = step.to_mode
            elif step.phase is GatewayStepPhase.WRITE:
                required_mode = (
                    DeviceMode.FASTBOOTD
                    if step.transport is GatewayTransport.FASTBOOTD
                    else DeviceMode.BOOTLOADER
                )
                if current_mode is not required_mode:
                    return False
                writes_seen += 1
        return bool(
            transitions
            and current_mode is final_mode is DeviceMode.ANDROID
            and transitions[-1].transition_operation is DeviceTransitionOperation.REBOOT_SYSTEM
            and sum(
                step.transition_operation is DeviceTransitionOperation.REBOOT_SYSTEM
                for step in transitions
            )
            == 1
        )

    @staticmethod
    def _valid_recovery_step(
        step: GuardianGatewayRecoveryStep,
        adapter_id: str,
    ) -> bool:
        common = bool(
            type(step.order) is int
            and 1 <= step.order <= 16
            and isinstance(step.operation, DeviceRecoveryOperation)
            and _clean(step.adapter_action_id, 96)
            and step.adapter_action_id.startswith(f"{adapter_id}.")
            and "relock" not in step.adapter_action_id.casefold()
            and isinstance(step.from_mode, DeviceMode)
            and isinstance(step.to_mode, DeviceMode)
            and step.target_slot in {"none", "recorded_prewrite"}
            and type(step.timeout_seconds) is int
            and 5 <= step.timeout_seconds <= 3600
            and type(step.may_wipe_user_data) is bool
            and type(step.phone_changes_if_executed) is bool
            and step.phone_changes_if_executed
            is (step.operation is not DeviceRecoveryOperation.VERIFY_POST_BOOT)
        )
        if not common:
            return False
        fastboot_modes = {DeviceMode.BOOTLOADER, DeviceMode.FASTBOOTD}
        if step.operation is DeviceRecoveryOperation.ACTIVATE_RECORDED_SLOT:
            return bool(
                step.from_mode in fastboot_modes
                and step.to_mode is step.from_mode
                and step.target_slot == "recorded_prewrite"
                and not step.may_wipe_user_data
            )
        if step.operation is DeviceRecoveryOperation.RESTORE_STOCK_PACKAGE:
            return bool(
                step.from_mode in fastboot_modes
                and step.to_mode in {*fastboot_modes, DeviceMode.ANDROID}
                and step.target_slot == "none"
            )
        if step.operation is DeviceRecoveryOperation.REBOOT_SYSTEM:
            return bool(
                step.from_mode in fastboot_modes
                and step.to_mode is DeviceMode.ANDROID
                and step.target_slot == "none"
                and not step.may_wipe_user_data
            )
        return bool(
            step.operation is DeviceRecoveryOperation.VERIFY_POST_BOOT
            and step.from_mode is DeviceMode.ANDROID
            and step.to_mode is DeviceMode.ANDROID
            and step.target_slot == "none"
            and not step.may_wipe_user_data
        )

    @staticmethod
    def _valid_recovery_sequence(contract: GuardianExecutionGatewayContract) -> bool:
        if contract.write_contract_version == 2:
            return not contract.recovery_steps
        try:
            current_mode = DeviceMode(contract.recovery_entry_mode)
            strategy = DeviceRecoveryStrategy(contract.recovery_strategy)
        except ValueError:
            return False
        for step in contract.recovery_steps:
            if step.from_mode is not current_mode:
                return False
            current_mode = step.to_mode
        restores = tuple(
            step
            for step in contract.recovery_steps
            if step.operation is DeviceRecoveryOperation.RESTORE_STOCK_PACKAGE
        )
        activations = tuple(
            step
            for step in contract.recovery_steps
            if step.operation is DeviceRecoveryOperation.ACTIVATE_RECORDED_SLOT
        )
        verifications = tuple(
            step
            for step in contract.recovery_steps
            if step.operation is DeviceRecoveryOperation.VERIFY_POST_BOOT
        )
        strategy_valid = (
            not activations and not contract.recovery_require_prewrite_slot_capture
            if strategy is DeviceRecoveryStrategy.STOCK_PACKAGE_RESTORE
            else len(activations) == 1
            and contract.recovery_steps[0] is activations[0]
            and contract.recovery_require_prewrite_slot_capture
        )
        return bool(
            current_mode is DeviceMode.ANDROID
            and len(restores) == 1
            and len(verifications) == 1
            and contract.recovery_steps[-1] is verifications[0]
            and contract.recovery_may_wipe_user_data
            is any(step.may_wipe_user_data for step in contract.recovery_steps)
            and strategy_valid
        )

    @staticmethod
    def _transition_digest_matches(contract: GuardianExecutionGatewayContract) -> bool:
        try:
            recovery = DeviceRecoveryContract(
                strategy=DeviceRecoveryStrategy(contract.recovery_strategy),
                adapter_id=contract.recovery_adapter_id,
                stock_package_sha256=contract.recovery_stock_package_sha256,
                entry_mode=DeviceMode(contract.recovery_entry_mode),
                actions=tuple(
                    DeviceRecoveryActionRule(
                        order=step.order,
                        operation=step.operation,
                        adapter_action_id=step.adapter_action_id,
                        from_mode=step.from_mode,
                        to_mode=step.to_mode,
                        target_slot=step.target_slot,
                        timeout_seconds=step.timeout_seconds,
                        may_wipe_user_data=step.may_wipe_user_data,
                    )
                    for step in contract.recovery_steps
                ),
                require_external_backup=contract.recovery_require_external_backup,
                require_stock_recovery=contract.recovery_require_stock_recovery,
                require_prewrite_slot_capture=contract.recovery_require_prewrite_slot_capture,
                may_wipe_user_data=contract.recovery_may_wipe_user_data,
                automatic_wipe_allowed=contract.recovery_automatic_wipe_allowed,
                bootloader_relock_allowed=contract.recovery_bootloader_relock_allowed,
            )
            transition = DeviceTransitionRecoveryContract(
                contract_id=contract.transition_recovery_contract_id,
                version=contract.transition_recovery_contract_version,
                source_build_id=contract.transition_source_build_id,
                attestation_sha256=contract.transition_attestation_sha256,
                entry_mode=DeviceMode(contract.transition_entry_mode),
                transitions=tuple(
                    DeviceModeTransitionRule(
                        order=step.transition_order,
                        after_write_order=step.after_write_order,
                        operation=step.transition_operation,
                        from_mode=step.from_mode,
                        to_mode=step.to_mode,
                        target_slot=step.target_slot,
                        timeout_seconds=step.timeout_seconds,
                    )
                    for step in contract.steps
                    if step.phase is GatewayStepPhase.TRANSITION
                ),
                final_mode=DeviceMode(contract.transition_final_mode),
                recovery=recovery,
                final_consent_required=contract.transition_final_consent_required,
                execution_authority=contract.transition_execution_authority,
                bootloader_relock_allowed=contract.transition_bootloader_relock_allowed,
            )
        except (TypeError, ValueError):
            return False
        return _digest(asdict(transition)) == contract.transition_recovery_contract_digest

    @staticmethod
    def _contains_uncontracted_mutation(
        steps: tuple[GuardianGatewayStep, ...],
    ) -> bool:
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
        return any(
            token.casefold() in forbidden
            for step in steps
            if step.phase is not GatewayStepPhase.TRANSITION
            for token in (step.executable, *step.arguments)
        )

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


def _empty_transition_fields(step: GuardianGatewayStep) -> bool:
    return bool(
        step.transition_operation is None
        and step.transition_order == 0
        and step.after_write_order == 0
        and step.from_mode is None
        and step.to_mode is None
        and step.timeout_seconds == 0
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
