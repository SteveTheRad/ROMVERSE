from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Callable, Collection
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from romverse.device.models import AndroidDevice
from romverse.device_packs.models import DeviceRecoveryOperation
from romverse.guardian.execution_gateway_contract import (
    GatewayStepPhase,
    GatewayTransport,
    GuardianExecutionGatewayContract,
    GuardianExecutionGatewayContractService,
    gateway_contract_matches_plan,
)
from romverse.guardian.execution_plan import (
    GuardianExecutionPlan,
    GuardianExecutionPlanService,
)
from romverse.guardian.execution_result_receipt import (
    ExecutionResultValidationError,
    GuardianRuntimeTrust,
    validate_guardian_runtime_trust,
)
from romverse.guardian.flash_handoff import FlashMode
from romverse.guardian.live_target_receipt import (
    GuardianLiveTargetReceipt,
    GuardianLiveTargetReceiptService,
)
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_regular_bytes,
    remove_regular_file,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


class ConsentDataAction(StrEnum):
    KEEP_USER_DATA = "keep-user-data"
    ERASE_USER_DATA = "erase-user-data"


@dataclass(frozen=True, slots=True)
class GuardianForwardConsequence:
    """One exact forward gateway step rendered for informed human review."""

    order: int
    operation_id: str
    phase: GatewayStepPhase
    transport: GatewayTransport
    effect: str
    partition: str
    target_slot: str
    artifact_sha256: str
    command_sha256: str
    phone_changes: bool


@dataclass(frozen=True, slots=True)
class GuardianRecoveryConsequence:
    """One signed contingency step that needs a later, separate consent."""

    order: int
    operation: DeviceRecoveryOperation
    adapter_action_id: str
    effect: str
    from_mode: str
    to_mode: str
    target_slot: str
    may_wipe_user_data: bool
    phone_changes_if_executed: bool
    separately_consented: bool


@dataclass(frozen=True, slots=True)
class GuardianFinalConsentReceipt:
    """Short-lived exact user consent; never standalone execution authority."""

    schema_version: int
    consent_id: str
    issued_at: str
    expires_at: str
    project_id: str
    gateway_contract_digest: str
    plan_digest: str
    manifest_digest: str
    artifact_binding_digest: str
    live_target_receipt_digest: str
    device_key: str
    device_name: str
    device_codename: str
    observed_product: str
    observed_entry_mode: str
    recorded_prewrite_slot: str
    device_pack_id: str
    device_pack_version: str
    device_pack_sha256: str
    data_action: ConsentDataAction
    runtime_trust_digest: str
    runtime_signer_key_id: str
    runtime_public_key_sha256: str
    runtime_adapter_id: str
    runtime_adapter_version: int
    runtime_adapter_sha256: str
    confirmation_phrase_sha256: str
    acknowledgements: tuple[str, ...]
    forward_step_count: int
    forward_phone_change_count: int
    forward_steps_digest: str
    forward_consequences: tuple[GuardianForwardConsequence, ...]
    recovery_step_count: int
    recovery_steps_digest: str
    recovery_consequences: tuple[GuardianRecoveryConsequence, ...]
    final_consent_recorded: bool
    forward_scope_only: bool
    separate_recovery_consent_required: bool
    separate_wipe_consent_required: bool
    recovery_consent_recorded: bool
    wipe_consent_recorded: bool
    runtime_trust_bound: bool
    ephemeral_grant_token_sha256: str
    ephemeral_grant_token_persisted: bool
    bootloader_relock_allowed: bool
    automatic_recovery_allowed: bool
    automatic_wipe_allowed: bool
    execution_authority: str
    runtime_invoked: bool
    phone_changed: bool
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class GuardianFinalConsentGrant:
    """Memory-only ephemeral token paired with a persisted consent receipt."""

    receipt: GuardianFinalConsentReceipt
    ephemeral_token: str


class FinalConsentValidationError(ProjectError):
    """The exact Guardian final-consent boundary failed closed."""


class GuardianFinalConsentReceiptService:
    """Capture exact informed consent without exposing a device runner.

    The raw ephemeral token exists only in the returned in-memory grant. The private
    receipt stores its SHA-256 and expires at the same instant as the live-target
    observation. A future governed runtime must atomically consume this capability
    exactly once before doing anything; this verification-only service deliberately
    does not claim that runtime boundary yet. A receipt without the token, exact
    runtime trust, current target, exact gateway, and that later governed runtime
    cannot start an operation.
    """

    FORMAT = "romverse.guardian-final-consent-receipt"
    SCHEMA_VERSION = 1
    LATEST_NAME = "final-consent-receipt.romverse"
    MAX_BYTES = 512 * 1024
    MAX_TEXT = 4096
    EXECUTION_AUTHORITY = "none"
    BASE_ACKNOWLEDGEMENTS = frozenset(
        {
            "exact-live-target-reviewed",
            "exact-gateway-reviewed",
            "all-forward-consequences-reviewed",
            "verification-and-uncertain-state-understood",
            "separate-recovery-consent-understood",
            "bootloader-relock-prohibited",
            "ephemeral-expiring-consent-understood",
        }
    )

    def __init__(
        self,
        store: RomProjectStore,
        plan_service: GuardianExecutionPlanService,
        live_targets: GuardianLiveTargetReceiptService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.plan_service = plan_service
        self.live_targets = live_targets
        self.clock = clock or (lambda: datetime.now(UTC))

    @classmethod
    def required_acknowledgements(
        cls,
        plan: GuardianExecutionPlan,
        gateway: GuardianExecutionGatewayContract,
    ) -> frozenset[str]:
        required = set(cls.BASE_ACKNOWLEDGEMENTS)
        required.add(
            "keep-data-risk-understood"
            if plan.mode is FlashMode.DIRTY_KEEP_DATA
            else "erase-data-requires-separate-wipe-consent"
        )
        if gateway.recovery_may_wipe_user_data:
            required.add("recovery-wipe-requires-separate-consent")
        return frozenset(required)

    @staticmethod
    def confirmation_phrase(
        plan: GuardianExecutionPlan,
        live_target: GuardianLiveTargetReceipt,
    ) -> str:
        action = "KEEP DATA" if plan.mode is FlashMode.DIRTY_KEEP_DATA else "ERASE DATA"
        return (
            f"FLASH {live_target.observed_product.upper()} {plan.plan_digest[-8:].upper()} {action}"
        )

    def issue(
        self,
        gateway: GuardianExecutionGatewayContract,
        plan: GuardianExecutionPlan,
        live_target: GuardianLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        runtime_trust: GuardianRuntimeTrust,
        runtime_public_key: Ed25519PublicKey,
        acknowledgements: Collection[str],
        confirmation_phrase: str,
    ) -> GuardianFinalConsentGrant:
        """Record exact forward consent and return its non-persisted ephemeral token."""

        try:
            self._invalidate(gateway.project_id)
            issued = self._now()
            self._validate_context(
                gateway,
                plan,
                live_target,
                reviewed_device,
                runtime_trust,
                runtime_public_key,
                now=issued,
            )
            normalized = tuple(sorted(set(acknowledgements)))
            required = self.required_acknowledgements(plan, gateway)
            if (
                set(normalized) != required
                or len(normalized) != len(required)
                or any(not _clean(item, 96) for item in normalized)
            ):
                raise FinalConsentValidationError(
                    "Review every required consequence before final consent"
                )
            expected_phrase = self.confirmation_phrase(plan, live_target)
            if confirmation_phrase.strip() != expected_phrase:
                raise FinalConsentValidationError(
                    "The typed final-consent phrase does not match this exact target and plan"
                )
            expires = _timestamp(live_target.expires_at)
            if issued >= expires:
                raise FinalConsentValidationError(
                    "The live-target check expired before final consent was recorded"
                )

            forward = self._forward_consequences(gateway)
            recovery = self._recovery_consequences(gateway)
            ephemeral_token = secrets.token_hex(32)
            payload: dict[str, object] = {
                "schema_version": self.SCHEMA_VERSION,
                "consent_id": uuid4().hex,
                "issued_at": issued.isoformat(),
                "expires_at": expires.isoformat(),
                "project_id": gateway.project_id,
                "gateway_contract_digest": gateway.contract_digest,
                "plan_digest": plan.plan_digest,
                "manifest_digest": gateway.manifest_digest,
                "artifact_binding_digest": gateway.artifact_binding_digest,
                "live_target_receipt_digest": live_target.receipt_digest,
                "device_key": gateway.device_key,
                "device_name": plan.device_name,
                "device_codename": plan.codename,
                "observed_product": live_target.observed_product,
                "observed_entry_mode": live_target.observed_entry_mode,
                "recorded_prewrite_slot": live_target.recorded_prewrite_slot,
                "device_pack_id": gateway.device_pack_id,
                "device_pack_version": gateway.device_pack_version,
                "device_pack_sha256": gateway.device_pack_sha256,
                "data_action": self._data_action(plan.mode),
                "runtime_trust_digest": _digest(asdict(runtime_trust)),
                "runtime_signer_key_id": runtime_trust.key_id,
                "runtime_public_key_sha256": runtime_trust.public_key_sha256,
                "runtime_adapter_id": runtime_trust.adapter_id,
                "runtime_adapter_version": runtime_trust.adapter_version,
                "runtime_adapter_sha256": runtime_trust.adapter_sha256,
                "confirmation_phrase_sha256": _text_digest(expected_phrase),
                "acknowledgements": normalized,
                "forward_step_count": len(forward),
                "forward_phone_change_count": sum(item.phone_changes for item in forward),
                "forward_steps_digest": gateway.steps_digest,
                "forward_consequences": [asdict(item) for item in forward],
                "recovery_step_count": len(recovery),
                "recovery_steps_digest": gateway.recovery_steps_digest,
                "recovery_consequences": [asdict(item) for item in recovery],
                "final_consent_recorded": True,
                "forward_scope_only": True,
                "separate_recovery_consent_required": bool(recovery),
                "separate_wipe_consent_required": bool(
                    plan.mode is FlashMode.CLEAN_WIPE_DATA or gateway.recovery_may_wipe_user_data
                ),
                "recovery_consent_recorded": False,
                "wipe_consent_recorded": False,
                "runtime_trust_bound": True,
                "ephemeral_grant_token_sha256": _text_digest(ephemeral_token),
                "ephemeral_grant_token_persisted": False,
                "bootloader_relock_allowed": False,
                "automatic_recovery_allowed": False,
                "automatic_wipe_allowed": False,
                "execution_authority": self.EXECUTION_AUTHORITY,
                "runtime_invoked": False,
                "phone_changed": False,
            }
            receipt = GuardianFinalConsentReceipt(
                **{
                    key: value
                    for key, value in payload.items()
                    if key
                    not in {
                        "forward_consequences",
                        "recovery_consequences",
                    }
                },
                forward_consequences=forward,
                recovery_consequences=recovery,
                receipt_digest=_digest(payload),
            )
            self.validate(
                receipt,
                gateway,
                plan,
                live_target,
                reviewed_device,
                runtime_trust,
                runtime_public_key,
                now=issued,
            )
            self._write(receipt)
            return GuardianFinalConsentGrant(receipt, ephemeral_token)
        except FinalConsentValidationError:
            raise
        except (
            ExecutionResultValidationError,
            LocalStoreError,
            OSError,
            TypeError,
            ValueError,
            KeyError,
            ProjectError,
        ) as exc:
            raise FinalConsentValidationError(
                "Final consent failed closed without starting a phone operation"
            ) from exc

    def load(
        self,
        gateway: GuardianExecutionGatewayContract,
        plan: GuardianExecutionPlan,
        live_target: GuardianLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        runtime_trust: GuardianRuntimeTrust,
        runtime_public_key: Ed25519PublicKey,
        *,
        now: datetime | None = None,
    ) -> GuardianFinalConsentReceipt | None:
        try:
            data = _read_exact_json(
                self._path(gateway.project_id),
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            expected_fields = {
                "format",
                *(field.name for field in fields(GuardianFinalConsentReceipt)),
            }
            if set(data) != expected_fields or data.pop("format") != self.FORMAT:
                return None
            raw_acknowledgements = data.pop("acknowledgements")
            raw_forward = data.pop("forward_consequences")
            raw_recovery = data.pop("recovery_consequences")
            forward_fields = {field.name for field in fields(GuardianForwardConsequence)}
            recovery_fields = {field.name for field in fields(GuardianRecoveryConsequence)}
            if (
                not isinstance(raw_acknowledgements, list)
                or any(type(item) is not str for item in raw_acknowledgements)
                or not isinstance(raw_forward, list)
                or any(
                    not isinstance(item, dict) or set(item) != forward_fields
                    for item in raw_forward
                )
                or not isinstance(raw_recovery, list)
                or any(
                    not isinstance(item, dict) or set(item) != recovery_fields
                    for item in raw_recovery
                )
            ):
                return None
            data["data_action"] = ConsentDataAction(str(data["data_action"]))
            receipt = GuardianFinalConsentReceipt(
                **data,
                acknowledgements=tuple(raw_acknowledgements),
                forward_consequences=tuple(
                    GuardianForwardConsequence(
                        **{
                            **item,
                            "phase": GatewayStepPhase(str(item["phase"])),
                            "transport": GatewayTransport(str(item["transport"])),
                        }
                    )
                    for item in raw_forward
                ),
                recovery_consequences=tuple(
                    GuardianRecoveryConsequence(
                        **{
                            **item,
                            "operation": DeviceRecoveryOperation(str(item["operation"])),
                        }
                    )
                    for item in raw_recovery
                ),
            )
            self.validate(
                receipt,
                gateway,
                plan,
                live_target,
                reviewed_device,
                runtime_trust,
                runtime_public_key,
                now=now or self._now(),
            )
            return receipt
        except (
            FinalConsentValidationError,
            ExecutionResultValidationError,
            LocalStoreError,
            OSError,
            TypeError,
            ValueError,
            KeyError,
            ProjectError,
            json.JSONDecodeError,
        ):
            return None

    def validate_grant(
        self,
        grant: GuardianFinalConsentGrant,
        gateway: GuardianExecutionGatewayContract,
        plan: GuardianExecutionPlan,
        live_target: GuardianLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        runtime_trust: GuardianRuntimeTrust,
        runtime_public_key: Ed25519PublicKey,
        *,
        now: datetime | None = None,
    ) -> None:
        if (
            not isinstance(grant, GuardianFinalConsentGrant)
            or not _hex(grant.ephemeral_token, 64)
            or _text_digest(grant.ephemeral_token) != grant.receipt.ephemeral_grant_token_sha256
        ):
            raise FinalConsentValidationError("Final consent ephemeral token is invalid")
        current = self.load(
            gateway,
            plan,
            live_target,
            reviewed_device,
            runtime_trust,
            runtime_public_key,
            now=now,
        )
        if current is None or current != grant.receipt:
            raise FinalConsentValidationError("Final consent is no longer current and exact")

    def validate(
        self,
        receipt: GuardianFinalConsentReceipt,
        gateway: GuardianExecutionGatewayContract,
        plan: GuardianExecutionPlan,
        live_target: GuardianLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        runtime_trust: GuardianRuntimeTrust,
        runtime_public_key: Ed25519PublicKey,
        *,
        now: datetime | None = None,
    ) -> None:
        checked_at = now or self._now()
        self._validate_context(
            gateway,
            plan,
            live_target,
            reviewed_device,
            runtime_trust,
            runtime_public_key,
            now=checked_at,
        )
        payload = asdict(receipt)
        receipt_digest = str(payload.pop("receipt_digest", ""))
        issued = _timestamp(receipt.issued_at)
        expires = _timestamp(receipt.expires_at)
        live_completed = _timestamp(live_target.completed_at)
        expected_forward = self._forward_consequences(gateway)
        expected_recovery = self._recovery_consequences(gateway)
        expected_acknowledgements = self.required_acknowledgements(plan, gateway)
        expected_phrase = self.confirmation_phrase(plan, live_target)
        if (
            not _valid_receipt_shape(receipt, self.MAX_TEXT)
            or receipt.schema_version != self.SCHEMA_VERSION
            or not _hex(receipt.consent_id, 32)
            or issued < live_completed
            or issued > checked_at
            or checked_at > expires
            or expires != _timestamp(live_target.expires_at)
            or receipt.project_id != gateway.project_id
            or receipt.gateway_contract_digest != gateway.contract_digest
            or receipt.plan_digest != plan.plan_digest
            or receipt.manifest_digest != gateway.manifest_digest
            or receipt.artifact_binding_digest != gateway.artifact_binding_digest
            or receipt.live_target_receipt_digest != live_target.receipt_digest
            or receipt.device_key != gateway.device_key
            or receipt.device_name != plan.device_name
            or receipt.device_codename != plan.codename
            or receipt.observed_product != live_target.observed_product
            or receipt.observed_entry_mode != live_target.observed_entry_mode
            or receipt.recorded_prewrite_slot != live_target.recorded_prewrite_slot
            or receipt.device_pack_id != gateway.device_pack_id
            or receipt.device_pack_version != gateway.device_pack_version
            or receipt.device_pack_sha256 != gateway.device_pack_sha256
            or receipt.data_action is not self._data_action(plan.mode)
            or receipt.runtime_trust_digest != _digest(asdict(runtime_trust))
            or receipt.runtime_signer_key_id != runtime_trust.key_id
            or receipt.runtime_public_key_sha256 != runtime_trust.public_key_sha256
            or receipt.runtime_adapter_id != runtime_trust.adapter_id
            or receipt.runtime_adapter_version != runtime_trust.adapter_version
            or receipt.runtime_adapter_sha256 != runtime_trust.adapter_sha256
            or receipt.confirmation_phrase_sha256 != _text_digest(expected_phrase)
            or set(receipt.acknowledgements) != expected_acknowledgements
            or len(receipt.acknowledgements) != len(expected_acknowledgements)
            or receipt.forward_step_count != len(expected_forward)
            or receipt.forward_phone_change_count
            != sum(item.phone_changes for item in expected_forward)
            or receipt.forward_steps_digest != gateway.steps_digest
            or receipt.forward_consequences != expected_forward
            or receipt.recovery_step_count != len(expected_recovery)
            or receipt.recovery_steps_digest != gateway.recovery_steps_digest
            or receipt.recovery_consequences != expected_recovery
            or receipt.final_consent_recorded is not True
            or receipt.forward_scope_only is not True
            or receipt.separate_recovery_consent_required is not bool(expected_recovery)
            or receipt.separate_wipe_consent_required
            is not bool(
                plan.mode is FlashMode.CLEAN_WIPE_DATA or gateway.recovery_may_wipe_user_data
            )
            or receipt.recovery_consent_recorded is not False
            or receipt.wipe_consent_recorded is not False
            or receipt.runtime_trust_bound is not True
            or not _hex(receipt.ephemeral_grant_token_sha256, 64)
            or receipt.ephemeral_grant_token_persisted is not False
            or receipt.bootloader_relock_allowed is not False
            or receipt.automatic_recovery_allowed is not False
            or receipt.automatic_wipe_allowed is not False
            or receipt.execution_authority != self.EXECUTION_AUTHORITY
            or receipt.runtime_invoked is not False
            or receipt.phone_changed is not False
            or not _hex(receipt_digest, 64)
            or receipt_digest != _digest(payload)
        ):
            raise FinalConsentValidationError(
                "Final consent receipt failed exact integrity or safety validation"
            )

    def _validate_context(
        self,
        gateway: GuardianExecutionGatewayContract,
        plan: GuardianExecutionPlan,
        live_target: GuardianLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        runtime_trust: GuardianRuntimeTrust,
        runtime_public_key: Ed25519PublicKey,
        *,
        now: datetime,
    ) -> None:
        GuardianExecutionGatewayContractService.validate(gateway)
        self.plan_service.validate(plan)
        if (
            not gateway_contract_matches_plan(gateway, plan)
            or gateway.write_contract_version != 3
            or plan.plan_status != GuardianExecutionPlanService.ORCHESTRATED_CONTRACT_STATUS
            or gateway.contract_status
            != GuardianExecutionGatewayContractService.ORCHESTRATED_STATUS
            or not gateway.transition_final_consent_required
            or not gateway.recovery_steps
            or gateway.transition_execution_authority != "none"
            or gateway.execution_authority != "none"
            or gateway.runtime_invoked
            or gateway.phone_changed
        ):
            raise FinalConsentValidationError(
                "Final consent requires the exact signed transition and recovery gateway"
            )
        current_live = self.live_targets.load(
            gateway,
            reviewed_device,
            now=now,
        )
        if current_live is None or current_live != live_target:
            raise FinalConsentValidationError(
                "Final consent requires the current exact live-target receipt"
            )
        if (
            reviewed_device.display_name.casefold() != plan.device_name.casefold()
            or reviewed_device.codename.casefold() != plan.codename.casefold()
        ):
            raise FinalConsentValidationError(
                "Final consent device identity does not match the reviewed plan"
            )
        validate_guardian_runtime_trust(runtime_trust, runtime_public_key, gateway)

    @staticmethod
    def _data_action(mode: FlashMode) -> ConsentDataAction:
        return (
            ConsentDataAction.KEEP_USER_DATA
            if mode is FlashMode.DIRTY_KEEP_DATA
            else ConsentDataAction.ERASE_USER_DATA
        )

    @classmethod
    def _forward_consequences(
        cls,
        gateway: GuardianExecutionGatewayContract,
    ) -> tuple[GuardianForwardConsequence, ...]:
        return tuple(
            GuardianForwardConsequence(
                order=step.order,
                operation_id=step.operation_id,
                phase=step.phase,
                transport=step.transport,
                effect=cls._forward_effect(step),
                partition=step.partition,
                target_slot=step.target_slot,
                artifact_sha256=step.artifact_sha256,
                command_sha256=_digest(
                    {"executable": step.executable, "arguments": step.arguments}
                ),
                phone_changes=step.phone_changes,
            )
            for step in gateway.steps
        )

    @staticmethod
    def _forward_effect(step) -> str:
        slot = "" if step.target_slot == "none" else f" in slot {step.target_slot}"
        if step.phase is GatewayStepPhase.WRITE:
            return f"Write the exact hash-bound image to {step.partition}{slot}."
        if step.phase is GatewayStepPhase.TRANSITION:
            operation = step.transition_operation.value.replace("_", " ")
            return f"{operation.capitalize()} from {step.from_mode.value} to {step.to_mode.value}."
        if step.phase is GatewayStepPhase.READBACK:
            return f"Read back {step.partition}{slot} and require the signed full-image size and SHA-256."
        if step.phase is GatewayStepPhase.POST_BOOT:
            return f"Verify Android reports {step.property_name} = {step.expected_value}."
        return f"Verify the exact {step.arguments[-1]} precondition before any write."

    @classmethod
    def _recovery_consequences(
        cls,
        gateway: GuardianExecutionGatewayContract,
    ) -> tuple[GuardianRecoveryConsequence, ...]:
        return tuple(
            GuardianRecoveryConsequence(
                order=step.order,
                operation=step.operation,
                adapter_action_id=step.adapter_action_id,
                effect=cls._recovery_effect(step),
                from_mode=step.from_mode.value,
                to_mode=step.to_mode.value,
                target_slot=step.target_slot,
                may_wipe_user_data=step.may_wipe_user_data,
                phone_changes_if_executed=step.phone_changes_if_executed,
                separately_consented=False,
            )
            for step in gateway.recovery_steps
        )

    @staticmethod
    def _recovery_effect(step) -> str:
        action = step.operation.value.replace("_", " ").capitalize()
        wipe = " It may erase user data." if step.may_wipe_user_data else ""
        return f"{action} through the signed recovery adapter.{wipe}"

    def _write(self, receipt: GuardianFinalConsentReceipt) -> None:
        path = self._path(receipt.project_id)
        ensure_private_directory(path.parent, boundary=self.store.workspace)
        atomic_write_json(
            path,
            {"format": self.FORMAT, **asdict(receipt)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_BYTES,
        )

    def _invalidate(self, project_id: str) -> None:
        remove_regular_file(
            self._path(project_id),
            boundary=self.store.workspace,
            missing_ok=True,
        )

    def _path(self, project_id: str) -> Path:
        self.store.get(project_id)
        return self.store.projects_root / project_id / "guardian" / self.LATEST_NAME

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise FinalConsentValidationError("Final-consent clock must be timezone-aware")
        return value.astimezone(UTC)


def _valid_receipt_shape(receipt: GuardianFinalConsentReceipt, maximum: int) -> bool:
    booleans = (
        receipt.final_consent_recorded,
        receipt.forward_scope_only,
        receipt.separate_recovery_consent_required,
        receipt.separate_wipe_consent_required,
        receipt.recovery_consent_recorded,
        receipt.wipe_consent_recorded,
        receipt.runtime_trust_bound,
        receipt.ephemeral_grant_token_persisted,
        receipt.bootloader_relock_allowed,
        receipt.automatic_recovery_allowed,
        receipt.automatic_wipe_allowed,
        receipt.runtime_invoked,
        receipt.phone_changed,
    )
    integers = (
        receipt.schema_version,
        receipt.runtime_adapter_version,
        receipt.forward_step_count,
        receipt.forward_phone_change_count,
        receipt.recovery_step_count,
    )
    texts = (
        receipt.consent_id,
        receipt.issued_at,
        receipt.expires_at,
        receipt.project_id,
        receipt.device_name,
        receipt.device_codename,
        receipt.observed_product,
        receipt.observed_entry_mode,
        receipt.device_pack_id,
        receipt.device_pack_version,
        receipt.runtime_signer_key_id,
        receipt.runtime_adapter_id,
        receipt.execution_authority,
    )
    hashes = (
        receipt.gateway_contract_digest,
        receipt.plan_digest,
        receipt.manifest_digest,
        receipt.artifact_binding_digest,
        receipt.live_target_receipt_digest,
        receipt.device_pack_sha256,
        receipt.runtime_trust_digest,
        receipt.runtime_public_key_sha256,
        receipt.runtime_adapter_sha256,
        receipt.confirmation_phrase_sha256,
        receipt.forward_steps_digest,
        receipt.recovery_steps_digest,
        receipt.ephemeral_grant_token_sha256,
        receipt.receipt_digest,
    )
    return bool(
        all(type(item) is bool for item in booleans)
        and all(type(item) is int and not isinstance(item, bool) for item in integers)
        and all(_clean(item, maximum) for item in texts)
        and all(_hex(item, 64) for item in hashes)
        and _hex(receipt.device_key, 20)
        and isinstance(receipt.data_action, ConsentDataAction)
        and receipt.recorded_prewrite_slot in {"", "a", "b"}
        and type(receipt.acknowledgements) is tuple
        and len(set(receipt.acknowledgements)) == len(receipt.acknowledgements)
        and all(_clean(item, 96) for item in receipt.acknowledgements)
        and type(receipt.forward_consequences) is tuple
        and all(_valid_forward_consequence(item) for item in receipt.forward_consequences)
        and type(receipt.recovery_consequences) is tuple
        and all(_valid_recovery_consequence(item) for item in receipt.recovery_consequences)
    )


def _valid_forward_consequence(value: object) -> bool:
    return bool(
        isinstance(value, GuardianForwardConsequence)
        and type(value.order) is int
        and not isinstance(value.order, bool)
        and isinstance(value.phase, GatewayStepPhase)
        and isinstance(value.transport, GatewayTransport)
        and _clean(value.operation_id, 160)
        and _clean(value.effect, 512)
        and _optional_clean(value.partition, 160)
        and _clean(value.target_slot, 80)
        and _optional_hex(value.artifact_sha256, 64)
        and _hex(value.command_sha256, 64)
        and type(value.phone_changes) is bool
    )


def _valid_recovery_consequence(value: object) -> bool:
    return bool(
        isinstance(value, GuardianRecoveryConsequence)
        and type(value.order) is int
        and not isinstance(value.order, bool)
        and isinstance(value.operation, DeviceRecoveryOperation)
        and _clean(value.adapter_action_id, 160)
        and _clean(value.effect, 512)
        and _clean(value.from_mode, 80)
        and _clean(value.to_mode, 80)
        and _clean(value.target_slot, 80)
        and type(value.may_wipe_user_data) is bool
        and type(value.phone_changes_if_executed) is bool
        and type(value.separately_consented) is bool
    )


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(f"[0-9a-f]{{{length}}}", value))


def _optional_hex(value: object, length: int) -> bool:
    return value == "" or _hex(value, length)


def _clean(value: object, maximum: int) -> bool:
    return bool(
        isinstance(value, str)
        and 1 <= len(value) <= maximum
        and all(ord(character) >= 32 and character != "\x7f" for character in value)
    )


def _optional_clean(value: object, maximum: int) -> bool:
    return value == "" or _clean(value, maximum)


def _read_exact_json(path: Path, *, boundary: Path, maximum_bytes: int) -> dict[str, Any]:
    encoded = read_regular_bytes(path, boundary=boundary, maximum_bytes=maximum_bytes)

    def exact_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate final-consent field")
            result[key] = value
        return result

    value = json.loads(encoded.decode("utf-8"), object_pairs_hook=exact_pairs)
    if not isinstance(value, dict):
        raise ValueError("final-consent evidence must be an object")
    return value
