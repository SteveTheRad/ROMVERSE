from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from uuid import uuid4

from romverse.device.models import AndroidDevice
from romverse.device_packs.models import DeviceRecoveryOperation
from romverse.guardian.recovery_live_target import (
    GuardianRecoveryLiveTargetReceipt,
    GuardianRecoveryLiveTargetReceiptService,
)
from romverse.guardian.recovery_preparation import (
    GuardianRecoveryPreparation,
    GuardianRecoveryPreparationService,
)
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_regular_bytes,
    remove_regular_file,
)
from romverse.rom.models import ProjectError


class RecoveryConsentValidationError(ProjectError):
    """One exact Recovery consent decision failed closed."""


@dataclass(frozen=True, slots=True)
class GuardianRecoveryConsentConsequence:
    """One sealed Recovery step presented in the meaningful consent decision."""

    order: int
    operation: DeviceRecoveryOperation
    adapter_action_id: str
    effect: str
    from_mode: str
    to_mode: str
    target_slot: str
    may_wipe_user_data: bool
    phone_changes_if_executed: bool


@dataclass(frozen=True, slots=True)
class GuardianRecoveryConsentReceipt:
    """Short-lived informed Recovery consent; never execution authority."""

    schema_version: int
    consent_id: str
    issued_at: str
    expires_at: str
    preparation_id: str
    preparation_digest: str
    live_target_receipt_digest: str
    incident_id: str
    incident_record_digest: str
    route_id: str
    project_id: str
    device_key: str
    device_name: str
    source_original_sha256: str
    device_pack_id: str
    device_pack_version: str
    device_pack_sha256: str
    transition_contract_digest: str
    recovery_evidence_digest: str
    expected_product: str
    observed_product: str
    expected_entry_mode: str
    observed_entry_mode: str
    recorded_prewrite_slot: str
    step_count: int
    steps_digest: str
    consequences: tuple[GuardianRecoveryConsentConsequence, ...]
    acknowledgements: tuple[str, ...]
    may_wipe_user_data: bool
    recovery_consent_recorded: bool
    wipe_risk_accepted: bool
    consent_scope_only: bool
    ephemeral_grant_token_sha256: str
    ephemeral_grant_token_persisted: bool
    execution_authority: str
    automatic_retry_allowed: bool
    bootloader_relock_allowed: bool
    runtime_invoked: bool
    phone_changed: bool
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class GuardianRecoveryConsentGrant:
    """Memory-only proof paired with the private consent receipt."""

    receipt: GuardianRecoveryConsentReceipt
    ephemeral_token: str


class GuardianRecoveryConsentReceiptService:
    """Record one current exact Recovery consent without exposing execution."""

    FORMAT = "romverse.guardian-recovery-consent-receipt"
    SCHEMA_VERSION = 1
    LATEST_NAME = "recovery-consent.romverse"
    MAX_BYTES = 256 * 1024
    EXECUTION_AUTHORITY = "none"
    BASE_ACKNOWLEDGEMENTS = frozenset(
        {
            "exact-recovery-plan-reviewed",
            "exact-live-phone-reviewed",
            "unknown-write-will-not-be-blindly-retried",
            "consent-does-not-start-recovery",
            "verification-still-required",
            "bootloader-relock-prohibited",
            "consent-is-short-lived",
        }
    )

    def __init__(
        self,
        live_targets: GuardianRecoveryLiveTargetReceiptService,
        *,
        clock=None,
    ) -> None:
        self.live_targets = live_targets
        self.preparations = live_targets.preparations
        self.store = self.preparations.store
        self.clock = clock or (lambda: datetime.now(UTC))

    @classmethod
    def required_acknowledgements(
        cls,
        preparation: GuardianRecoveryPreparation,
    ) -> tuple[str, ...]:
        required = set(cls.BASE_ACKNOWLEDGEMENTS)
        if preparation.may_wipe_user_data:
            required.add("user-data-may-be-erased")
        return tuple(sorted(required))

    def issue(
        self,
        preparation: GuardianRecoveryPreparation,
        live_target: GuardianRecoveryLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        *,
        confirmed: bool,
    ) -> GuardianRecoveryConsentGrant:
        """Record one explicit decision and return a non-persisted expiring token."""

        try:
            self._invalidate(preparation.incident_id)
            if confirmed is not True:
                raise RecoveryConsentValidationError(
                    "Recovery consent was declined; no consent receipt was recorded"
                )
            issued = self._now()
            self._validate_context(preparation, live_target, reviewed_device, now=issued)
            expires = _timestamp(live_target.expires_at)
            if issued >= expires:
                raise RecoveryConsentValidationError(
                    "The exact-phone check expired before Recovery consent was recorded"
                )
            consequences = self.consequences(preparation)
            token = secrets.token_hex(32)
            payload: dict[str, object] = {
                "schema_version": self.SCHEMA_VERSION,
                "consent_id": uuid4().hex,
                "issued_at": issued.isoformat(),
                "expires_at": expires.isoformat(),
                "preparation_id": preparation.preparation_id,
                "preparation_digest": preparation.preparation_digest,
                "live_target_receipt_digest": live_target.receipt_digest,
                "incident_id": preparation.incident_id,
                "incident_record_digest": preparation.incident_record_digest,
                "route_id": preparation.route_id,
                "project_id": preparation.project_id,
                "device_key": preparation.device_key,
                "device_name": preparation.device_name,
                "source_original_sha256": preparation.source_original_sha256,
                "device_pack_id": preparation.device_pack_id,
                "device_pack_version": preparation.device_pack_version,
                "device_pack_sha256": preparation.device_pack_sha256,
                "transition_contract_digest": preparation.transition_contract_digest,
                "recovery_evidence_digest": preparation.recovery_evidence_digest,
                "expected_product": preparation.expected_product,
                "observed_product": live_target.observed_product,
                "expected_entry_mode": preparation.expected_entry_mode,
                "observed_entry_mode": live_target.observed_entry_mode,
                "recorded_prewrite_slot": live_target.recorded_prewrite_slot,
                "step_count": len(consequences),
                "steps_digest": preparation.steps_digest,
                "consequences": [asdict(item) for item in consequences],
                "acknowledgements": self.required_acknowledgements(preparation),
                "may_wipe_user_data": preparation.may_wipe_user_data,
                "recovery_consent_recorded": True,
                "wipe_risk_accepted": preparation.may_wipe_user_data,
                "consent_scope_only": True,
                "ephemeral_grant_token_sha256": _text_digest(token),
                "ephemeral_grant_token_persisted": False,
                "execution_authority": self.EXECUTION_AUTHORITY,
                "automatic_retry_allowed": False,
                "bootloader_relock_allowed": False,
                "runtime_invoked": False,
                "phone_changed": False,
            }
            receipt = GuardianRecoveryConsentReceipt(
                **{
                    key: value
                    for key, value in payload.items()
                    if key not in {"consequences", "acknowledgements"}
                },
                consequences=consequences,
                acknowledgements=self.required_acknowledgements(preparation),
                receipt_digest=_digest(payload),
            )
            self.validate(receipt, preparation, live_target, reviewed_device, now=issued)
            self._write(receipt)
            return GuardianRecoveryConsentGrant(receipt, token)
        except RecoveryConsentValidationError:
            raise
        except (LocalStoreError, OSError, TypeError, ValueError, KeyError, ProjectError) as exc:
            raise RecoveryConsentValidationError(
                "Recovery consent failed closed without starting a phone operation"
            ) from exc

    def load(
        self,
        preparation: GuardianRecoveryPreparation,
        live_target: GuardianRecoveryLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        *,
        now: datetime | None = None,
    ) -> GuardianRecoveryConsentReceipt | None:
        try:
            data = _read_exact_json(
                self._path(preparation.incident_id),
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            expected = {
                "format",
                *(field.name for field in fields(GuardianRecoveryConsentReceipt)),
            }
            if set(data) != expected or data.pop("format") != self.FORMAT:
                return None
            raw_consequences = data.pop("consequences")
            raw_acknowledgements = data.pop("acknowledgements")
            consequence_fields = {
                field.name for field in fields(GuardianRecoveryConsentConsequence)
            }
            if (
                not isinstance(raw_consequences, list)
                or any(
                    not isinstance(item, dict) or set(item) != consequence_fields
                    for item in raw_consequences
                )
                or not isinstance(raw_acknowledgements, list)
                or any(type(item) is not str for item in raw_acknowledgements)
            ):
                return None
            receipt = GuardianRecoveryConsentReceipt(
                **data,
                consequences=tuple(
                    GuardianRecoveryConsentConsequence(
                        **{
                            **item,
                            "operation": DeviceRecoveryOperation(str(item["operation"])),
                        }
                    )
                    for item in raw_consequences
                ),
                acknowledgements=tuple(raw_acknowledgements),
            )
            self.validate(receipt, preparation, live_target, reviewed_device, now=now)
            return receipt
        except (
            RecoveryConsentValidationError,
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
        grant: GuardianRecoveryConsentGrant,
        preparation: GuardianRecoveryPreparation,
        live_target: GuardianRecoveryLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        *,
        now: datetime | None = None,
    ) -> None:
        if (
            not isinstance(grant, GuardianRecoveryConsentGrant)
            or not _hex(grant.ephemeral_token, 64)
            or _text_digest(grant.ephemeral_token) != grant.receipt.ephemeral_grant_token_sha256
        ):
            raise RecoveryConsentValidationError("Recovery consent token is invalid")
        current = self.load(
            preparation,
            live_target,
            reviewed_device,
            now=now,
        )
        if current is None or current != grant.receipt:
            raise RecoveryConsentValidationError("Recovery consent is no longer current and exact")

    def validate(
        self,
        receipt: GuardianRecoveryConsentReceipt,
        preparation: GuardianRecoveryPreparation,
        live_target: GuardianRecoveryLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        *,
        now: datetime | None = None,
    ) -> None:
        checked_at = now or self._now()
        self._validate_context(preparation, live_target, reviewed_device, now=checked_at)
        payload = asdict(receipt)
        receipt_digest = str(payload.pop("receipt_digest", ""))
        issued = _timestamp(receipt.issued_at)
        expires = _timestamp(receipt.expires_at)
        live_completed = _timestamp(live_target.completed_at)
        consequences = self.consequences(preparation)
        acknowledgements = self.required_acknowledgements(preparation)
        if (
            checked_at.tzinfo is None
            or checked_at.utcoffset() is None
            or issued < live_completed
            or issued > checked_at.astimezone(UTC)
            or checked_at.astimezone(UTC) > expires
            or expires != _timestamp(live_target.expires_at)
            or type(receipt.schema_version) is not int
            or receipt.schema_version != self.SCHEMA_VERSION
            or not _hex(receipt.consent_id, 32)
            or receipt.preparation_id != preparation.preparation_id
            or receipt.preparation_digest != preparation.preparation_digest
            or receipt.live_target_receipt_digest != live_target.receipt_digest
            or receipt.incident_id != preparation.incident_id
            or receipt.incident_record_digest != preparation.incident_record_digest
            or receipt.route_id != preparation.route_id
            or receipt.project_id != preparation.project_id
            or receipt.device_key != preparation.device_key
            or receipt.device_name != preparation.device_name
            or receipt.source_original_sha256 != preparation.source_original_sha256
            or receipt.device_pack_id != preparation.device_pack_id
            or receipt.device_pack_version != preparation.device_pack_version
            or receipt.device_pack_sha256 != preparation.device_pack_sha256
            or receipt.transition_contract_digest != preparation.transition_contract_digest
            or receipt.recovery_evidence_digest != preparation.recovery_evidence_digest
            or receipt.expected_product != preparation.expected_product
            or receipt.observed_product != live_target.observed_product
            or receipt.expected_entry_mode != preparation.expected_entry_mode
            or receipt.observed_entry_mode != live_target.observed_entry_mode
            or receipt.recorded_prewrite_slot != live_target.recorded_prewrite_slot
            or type(receipt.step_count) is not int
            or receipt.step_count != preparation.step_count
            or receipt.steps_digest != preparation.steps_digest
            or receipt.consequences != consequences
            or receipt.acknowledgements != acknowledgements
            or receipt.may_wipe_user_data is not preparation.may_wipe_user_data
            or receipt.recovery_consent_recorded is not True
            or receipt.wipe_risk_accepted is not preparation.may_wipe_user_data
            or receipt.consent_scope_only is not True
            or not _hex(receipt.ephemeral_grant_token_sha256, 64)
            or receipt.ephemeral_grant_token_persisted is not False
            or receipt.execution_authority != self.EXECUTION_AUTHORITY
            or receipt.automatic_retry_allowed is not False
            or receipt.bootloader_relock_allowed is not False
            or receipt.runtime_invoked is not False
            or receipt.phone_changed is not False
            or not _hex(receipt_digest, 64)
            or receipt_digest != _digest(payload)
        ):
            raise RecoveryConsentValidationError(
                "Recovery consent receipt failed exact integrity or safety validation"
            )

    @staticmethod
    def consequences(
        preparation: GuardianRecoveryPreparation,
    ) -> tuple[GuardianRecoveryConsentConsequence, ...]:
        effects = {
            DeviceRecoveryOperation.RESTORE_STOCK_PACKAGE: (
                "Restore the exact source-bound stock package declared by the Device Pack"
            ),
            DeviceRecoveryOperation.REBOOT_SYSTEM: "Reboot the phone into Android",
            DeviceRecoveryOperation.VERIFY_POST_BOOT: (
                "Observe the resulting boot and verify it against the sealed contract"
            ),
            DeviceRecoveryOperation.ACTIVATE_RECORDED_SLOT: (
                "Return to the slot recorded before the interrupted operation"
            ),
        }
        return tuple(
            GuardianRecoveryConsentConsequence(
                step.order,
                step.operation,
                step.adapter_action_id,
                effects.get(step.operation, step.operation.value.replace("_", " ").capitalize()),
                step.from_mode,
                step.to_mode,
                step.target_slot,
                step.may_wipe_user_data,
                step.operation is not DeviceRecoveryOperation.VERIFY_POST_BOOT,
            )
            for step in preparation.steps
        )

    def _validate_context(
        self,
        preparation: GuardianRecoveryPreparation,
        live_target: GuardianRecoveryLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        *,
        now: datetime,
    ) -> None:
        GuardianRecoveryPreparationService.validate(preparation)
        current_preparation = self.preparations.load(
            preparation.incident_id,
            preparation.route_id,
            [reviewed_device],
        )
        current_target = self.live_targets.load(
            preparation,
            reviewed_device,
            now=now,
        )
        if current_preparation != preparation or current_target != live_target:
            raise RecoveryConsentValidationError(
                "Recovery consent requires the current exact preparation and live-phone receipt"
            )

    def _write(self, receipt: GuardianRecoveryConsentReceipt) -> None:
        path = self._path(receipt.incident_id)
        ensure_private_directory(path.parent, boundary=self.store.workspace)
        atomic_write_json(
            path,
            {"format": self.FORMAT, **asdict(receipt)},
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_BYTES,
        )

    def _invalidate(self, incident_id: str) -> None:
        remove_regular_file(
            self._path(incident_id),
            boundary=self.store.workspace,
            missing_ok=True,
        )

    def _path(self, incident_id: str):
        if not _hex(incident_id, 32):
            raise RecoveryConsentValidationError("Recovery incident identifier is invalid")
        return (
            self.store.workspace
            / "diagnostics"
            / "recovery-preparations"
            / incident_id
            / self.LATEST_NAME
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RecoveryConsentValidationError("Recovery consent clock must be timezone-aware")
        return value.astimezone(UTC)


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


def _read_exact_json(path, *, boundary, maximum_bytes: int) -> dict[str, object]:
    encoded = read_regular_bytes(path, boundary=boundary, maximum_bytes=maximum_bytes)

    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    payload = json.loads(encoded.decode("utf-8"), object_pairs_hook=pairs)
    if not isinstance(payload, dict):
        raise ValueError("receipt must be a JSON object")
    return payload
