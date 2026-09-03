from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from romverse.device.models import AndroidDevice
from romverse.guardian.consent_capability import GuardianConsentCapabilityReservation
from romverse.guardian.execution_gateway_contract import (
    GatewayStepPhase,
    GuardianExecutionGatewayContract,
    GuardianExecutionGatewayContractService,
)
from romverse.guardian.execution_plan import GuardianExecutionPlan
from romverse.guardian.execution_result_receipt import GuardianRuntimeTrust
from romverse.guardian.final_consent import GuardianFinalConsentGrant
from romverse.guardian.live_target_receipt import GuardianLiveTargetReceipt
from romverse.guardian.models import OperationClass
from romverse.guardian.runtime_authorization import (
    GuardianRuntimeAuthorizationService,
    GuardianRuntimeForwardExecutionGrant,
    RuntimeAuthorizationError,
)
from romverse.guardian.runtime_session import VerifiedGuardianRuntimeSession
from romverse.infrastructure.local_store import (
    LocalStoreConflictError,
    LocalStoreError,
    ensure_private_directory,
    exclusive_create_json,
    read_regular_bytes,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


@dataclass(frozen=True, slots=True)
class GuardianRuntimeExecutionClaim:
    """Runtime-signed proof that one forward grant was claimed exactly once."""

    schema_version: int
    claim_id: str
    claimed_at: str
    expires_at: str
    project_id: str
    gateway_contract_digest: str
    plan_digest: str
    manifest_digest: str
    artifact_binding_digest: str
    live_target_receipt_digest: str
    device_key: str
    device_pack_id: str
    device_pack_version: str
    device_pack_sha256: str
    final_consent_receipt_digest: str
    reservation_digest: str
    runtime_session_attestation_digest: str
    runtime_consumption_id: str
    runtime_consumption_digest: str
    runtime_consumption_envelope_sha256: str
    execution_grant_id: str
    execution_grant_token_sha256: str
    execution_grant_token_persisted: bool
    runtime_signer_key_id: str
    runtime_public_key_sha256: str
    runtime_adapter_id: str
    runtime_adapter_version: int
    runtime_adapter_sha256: str
    expected_entry_mode: str
    expected_product: str
    expected_unlocked: bool
    recorded_prewrite_slot: str
    forward_step_count: int
    forward_steps_digest: str
    first_step_order: int
    first_step_operation_id: str
    first_step_digest: str
    first_step_transport: str
    forward_scope_only: bool
    recovery_authority_granted: bool
    wipe_authority_granted: bool
    automatic_recovery_enabled: bool
    automatic_wipe_enabled: bool
    bootloader_relock_allowed: bool
    exclusive_execution_claim_recorded: bool
    execution_grant_claimed_once: bool
    device_open_permit_id: str
    device_open_permit_token_sha256: str
    device_open_permit_token_persisted: bool
    device_open_authority: str
    device_access_opened: bool
    first_forward_step_started: bool
    phone_changed: bool
    claim_digest: str


@dataclass(frozen=True, slots=True)
class VerifiedGuardianRuntimeExecutionClaim:
    claim: GuardianRuntimeExecutionClaim
    signer_key_id: str
    signed_envelope_sha256: str


@dataclass(frozen=True, slots=True)
class GuardianRuntimeDeviceOpenPermit:
    """Memory-only permit for one later exact-target claim-and-open operation."""

    verified_claim: VerifiedGuardianRuntimeExecutionClaim
    target_serial: str = field(repr=False)
    ephemeral_open_token: str = field(repr=False)


class RuntimeExecutionClaimError(ProjectError):
    """A one-use execution-grant claim failed closed before device access."""


class GuardianRuntimeExecutionClaimService:
    """Claim one runtime forward grant without opening or commanding a device.

    The separately packaged runtime must call this immediately before its future
    claim-and-open adapter. One exclusive signed record converts the memory-only
    forward grant into one new memory-only exact-target permit. A persisted record
    can be audited but cannot recreate either token or the raw phone serial.
    """

    FORMAT = "romverse.guardian-runtime-execution-claim"
    SCHEMA_VERSION = 1
    ALGORITHM = "ed25519"
    DOMAIN = b"ROMVERSE-GUARDIAN-RUNTIME-EXECUTION-CLAIM-V1\0"
    MAX_BYTES = 256 * 1024
    DEVICE_OPEN_AUTHORITY = "exact-reviewed-target-open-once"
    ENVELOPE_FIELDS = {
        "format",
        "schema_version",
        "algorithm",
        "key_id",
        "claim_sha256",
        "claim",
        "signature",
    }
    CLAIM_FIELDS = {field.name for field in fields(GuardianRuntimeExecutionClaim)}

    def __init__(
        self,
        store: RomProjectStore,
        authorizations: GuardianRuntimeAuthorizationService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.authorizations = authorizations
        self.clock = clock or (lambda: datetime.now(UTC))

    def claim(
        self,
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
    ) -> GuardianRuntimeDeviceOpenPermit:
        """Consume one in-memory forward grant without opening device access."""

        try:
            claimed_at = self._now()
            self.authorizations.validate_in_memory_grant(
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
                now=claimed_at,
            )
            self._validate_private_key(runtime_public_key, runtime_private_key)
            GuardianExecutionGatewayContractService.validate(gateway)
            if not gateway.steps:
                raise RuntimeExecutionClaimError("Guardian gateway contains no forward step")

            consumption = runtime_grant.verified_consumption.consumption
            expires_at = _timestamp(consumption.expires_at, "runtime execution-claim expiry")
            if claimed_at >= expires_at:
                raise RuntimeExecutionClaimError(
                    "Runtime forward grant expired before its execution claim"
                )
            first_step = gateway.steps[0]
            if (
                first_step.phase is not GatewayStepPhase.PRECONDITION
                or first_step.category is not OperationClass.READ_ONLY
                or first_step.phone_changes
            ):
                raise RuntimeExecutionClaimError(
                    "Runtime device opening must begin with an exact read-only precondition"
                )
            open_token = secrets.token_hex(32)
            payload: dict[str, object] = {
                "schema_version": self.SCHEMA_VERSION,
                "claim_id": uuid4().hex,
                "claimed_at": claimed_at.isoformat(),
                "expires_at": expires_at.isoformat(),
                "project_id": gateway.project_id,
                "gateway_contract_digest": gateway.contract_digest,
                "plan_digest": plan.plan_digest,
                "manifest_digest": gateway.manifest_digest,
                "artifact_binding_digest": gateway.artifact_binding_digest,
                "live_target_receipt_digest": live_target.receipt_digest,
                "device_key": gateway.device_key,
                "device_pack_id": gateway.device_pack_id,
                "device_pack_version": gateway.device_pack_version,
                "device_pack_sha256": gateway.device_pack_sha256,
                "final_consent_receipt_digest": grant.receipt.receipt_digest,
                "reservation_digest": reservation.reservation_digest,
                "runtime_session_attestation_digest": session.attestation.attestation_digest,
                "runtime_consumption_id": consumption.consumption_id,
                "runtime_consumption_digest": consumption.consumption_digest,
                "runtime_consumption_envelope_sha256": (
                    runtime_grant.verified_consumption.signed_envelope_sha256
                ),
                "execution_grant_id": consumption.execution_grant_id,
                "execution_grant_token_sha256": consumption.execution_grant_token_sha256,
                "execution_grant_token_persisted": False,
                "runtime_signer_key_id": runtime_trust.key_id,
                "runtime_public_key_sha256": runtime_trust.public_key_sha256,
                "runtime_adapter_id": runtime_trust.adapter_id,
                "runtime_adapter_version": runtime_trust.adapter_version,
                "runtime_adapter_sha256": runtime_trust.adapter_sha256,
                "expected_entry_mode": live_target.expected_entry_mode,
                "expected_product": live_target.observed_product,
                "expected_unlocked": True,
                "recorded_prewrite_slot": live_target.recorded_prewrite_slot,
                "forward_step_count": gateway.step_count,
                "forward_steps_digest": gateway.steps_digest,
                "first_step_order": first_step.order,
                "first_step_operation_id": first_step.operation_id,
                "first_step_digest": _digest({"gateway_step": asdict(first_step)}),
                "first_step_transport": first_step.transport.value,
                "forward_scope_only": True,
                "recovery_authority_granted": False,
                "wipe_authority_granted": False,
                "automatic_recovery_enabled": False,
                "automatic_wipe_enabled": False,
                "bootloader_relock_allowed": False,
                "exclusive_execution_claim_recorded": True,
                "execution_grant_claimed_once": True,
                "device_open_permit_id": uuid4().hex,
                "device_open_permit_token_sha256": _text_digest(open_token),
                "device_open_permit_token_persisted": False,
                "device_open_authority": self.DEVICE_OPEN_AUTHORITY,
                "device_access_opened": False,
                "first_forward_step_started": False,
                "phone_changed": False,
            }
            claim = GuardianRuntimeExecutionClaim(
                **payload,
                claim_digest=_digest(payload),
            )
            encoded = _canonical_bytes(asdict(claim))
            envelope: dict[str, object] = {
                "format": self.FORMAT,
                "schema_version": self.SCHEMA_VERSION,
                "algorithm": self.ALGORITHM,
                "key_id": runtime_trust.key_id,
                "claim_sha256": hashlib.sha256(encoded).hexdigest(),
                "claim": asdict(claim),
                "signature": base64.b64encode(
                    runtime_private_key.sign(self.DOMAIN + encoded)
                ).decode("ascii"),
            }
            verified = self._verify_envelope(
                envelope,
                runtime_grant,
                grant,
                reservation,
                session,
                gateway,
                plan,
                live_target,
                runtime_trust,
                runtime_public_key,
                now=claimed_at,
            )
            path = self._path(gateway.project_id, consumption.execution_grant_id)
            ensure_private_directory(path.parent, boundary=self.store.workspace)
            exclusive_create_json(
                path,
                envelope,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            return GuardianRuntimeDeviceOpenPermit(
                verified,
                reviewed_device.serial,
                open_token,
            )
        except LocalStoreConflictError as exc:
            raise RuntimeExecutionClaimError(
                "This runtime forward grant has already been claimed"
            ) from exc
        except RuntimeExecutionClaimError:
            raise
        except (
            RuntimeAuthorizationError,
            LocalStoreError,
            OSError,
            TypeError,
            ValueError,
            KeyError,
            ProjectError,
        ) as exc:
            raise RuntimeExecutionClaimError(
                "Runtime execution claim failed closed before device access"
            ) from exc

    def load(
        self,
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
        *,
        now: datetime | None = None,
    ) -> VerifiedGuardianRuntimeExecutionClaim | None:
        """Reload signed audit proof without recreating the device-open permit."""

        try:
            checked_at = now or self._now()
            self.authorizations.validate_in_memory_grant(
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
                now=checked_at,
            )
            consumption = runtime_grant.verified_consumption.consumption
            envelope = _read_exact_json(
                self._path(gateway.project_id, consumption.execution_grant_id),
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            return self._verify_envelope(
                envelope,
                runtime_grant,
                grant,
                reservation,
                session,
                gateway,
                plan,
                live_target,
                runtime_trust,
                runtime_public_key,
                now=checked_at,
            )
        except (
            RuntimeExecutionClaimError,
            RuntimeAuthorizationError,
            LocalStoreError,
            OSError,
            TypeError,
            ValueError,
            KeyError,
            ProjectError,
            json.JSONDecodeError,
        ):
            return None

    def validate_in_memory_permit(
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
        *,
        now: datetime | None = None,
    ) -> None:
        """Revalidate one memory-only permit without opening the target."""

        if (
            not isinstance(permit, GuardianRuntimeDeviceOpenPermit)
            or not _hex(permit.ephemeral_open_token, 64)
            or not permit.target_serial
            or permit.target_serial != reviewed_device.serial
        ):
            raise RuntimeExecutionClaimError("Runtime device-open permit is malformed")
        current = self.load(
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
            now=now,
        )
        if current is None or current != permit.verified_claim:
            raise RuntimeExecutionClaimError("Runtime device-open permit is no longer current")
        if not hmac.compare_digest(
            _text_digest(permit.ephemeral_open_token),
            current.claim.device_open_permit_token_sha256,
        ):
            raise RuntimeExecutionClaimError("Runtime device-open token does not match")

    def _verify_envelope(
        self,
        envelope: dict[str, Any],
        runtime_grant: GuardianRuntimeForwardExecutionGrant,
        grant: GuardianFinalConsentGrant,
        reservation: GuardianConsentCapabilityReservation,
        session: VerifiedGuardianRuntimeSession,
        gateway: GuardianExecutionGatewayContract,
        plan: GuardianExecutionPlan,
        live_target: GuardianLiveTargetReceipt,
        runtime_trust: GuardianRuntimeTrust,
        runtime_public_key: Ed25519PublicKey,
        *,
        now: datetime,
    ) -> VerifiedGuardianRuntimeExecutionClaim:
        if not isinstance(envelope, dict) or set(envelope) != self.ENVELOPE_FIELDS:
            raise RuntimeExecutionClaimError("Runtime execution-claim envelope fields do not match")
        if (
            envelope["format"] != self.FORMAT
            or type(envelope["schema_version"]) is not int
            or envelope["schema_version"] != self.SCHEMA_VERSION
            or envelope["algorithm"] != self.ALGORITHM
            or envelope["key_id"] != runtime_trust.key_id
        ):
            raise RuntimeExecutionClaimError(
                "Runtime execution-claim signer or schema is not trusted"
            )
        raw = envelope["claim"]
        if not isinstance(raw, dict) or set(raw) != self.CLAIM_FIELDS:
            raise RuntimeExecutionClaimError("Runtime execution-claim payload fields do not match")
        encoded = _canonical_bytes(raw)
        if len(encoded) > self.MAX_BYTES:
            raise RuntimeExecutionClaimError("Runtime execution claim exceeds its size boundary")
        signed_digest = hashlib.sha256(encoded).hexdigest()
        if envelope["claim_sha256"] != signed_digest:
            raise RuntimeExecutionClaimError("Runtime execution-claim signed digest does not match")
        try:
            runtime_public_key.verify(_signature(envelope["signature"]), self.DOMAIN + encoded)
        except InvalidSignature as exc:
            raise RuntimeExecutionClaimError(
                "Runtime execution-claim signature verification failed"
            ) from exc
        claim = GuardianRuntimeExecutionClaim(**raw)
        self._validate_claim(
            claim,
            runtime_grant,
            grant,
            reservation,
            session,
            gateway,
            plan,
            live_target,
            runtime_trust,
            now=now,
        )
        return VerifiedGuardianRuntimeExecutionClaim(
            claim,
            runtime_trust.key_id,
            _digest(envelope),
        )

    def _validate_claim(
        self,
        claim: GuardianRuntimeExecutionClaim,
        runtime_grant: GuardianRuntimeForwardExecutionGrant,
        grant: GuardianFinalConsentGrant,
        reservation: GuardianConsentCapabilityReservation,
        session: VerifiedGuardianRuntimeSession,
        gateway: GuardianExecutionGatewayContract,
        plan: GuardianExecutionPlan,
        live_target: GuardianLiveTargetReceipt,
        runtime_trust: GuardianRuntimeTrust,
        *,
        now: datetime,
    ) -> None:
        payload = asdict(claim)
        digest = str(payload.pop("claim_digest", ""))
        claimed = _timestamp(claim.claimed_at, "runtime execution claim")
        expires = _timestamp(claim.expires_at, "runtime execution-claim expiry")
        consumption = runtime_grant.verified_consumption.consumption
        first_step = gateway.steps[0]
        if (
            type(claim.schema_version) is not int
            or claim.schema_version != self.SCHEMA_VERSION
            or not _hex(claim.claim_id, 32)
            or not claimed <= now <= expires
            or claimed >= expires
            or expires != _timestamp(consumption.expires_at, "runtime authorization expiry")
            or claim.project_id != gateway.project_id
            or claim.gateway_contract_digest != gateway.contract_digest
            or claim.plan_digest != plan.plan_digest
            or claim.manifest_digest != gateway.manifest_digest
            or claim.artifact_binding_digest != gateway.artifact_binding_digest
            or claim.live_target_receipt_digest != live_target.receipt_digest
            or claim.device_key != gateway.device_key
            or claim.device_pack_id != gateway.device_pack_id
            or claim.device_pack_version != gateway.device_pack_version
            or claim.device_pack_sha256 != gateway.device_pack_sha256
            or claim.final_consent_receipt_digest != grant.receipt.receipt_digest
            or claim.reservation_digest != reservation.reservation_digest
            or claim.runtime_session_attestation_digest != session.attestation.attestation_digest
            or claim.runtime_consumption_id != consumption.consumption_id
            or claim.runtime_consumption_digest != consumption.consumption_digest
            or claim.runtime_consumption_envelope_sha256
            != runtime_grant.verified_consumption.signed_envelope_sha256
            or claim.execution_grant_id != consumption.execution_grant_id
            or claim.execution_grant_token_sha256 != consumption.execution_grant_token_sha256
            or claim.execution_grant_token_persisted is not False
            or claim.runtime_signer_key_id != runtime_trust.key_id
            or claim.runtime_public_key_sha256 != runtime_trust.public_key_sha256
            or claim.runtime_adapter_id != runtime_trust.adapter_id
            or type(claim.runtime_adapter_version) is not int
            or claim.runtime_adapter_version != runtime_trust.adapter_version
            or claim.runtime_adapter_sha256 != runtime_trust.adapter_sha256
            or claim.expected_entry_mode != live_target.expected_entry_mode
            or claim.expected_entry_mode != live_target.observed_entry_mode
            or claim.expected_product != live_target.observed_product
            or claim.expected_unlocked is not True
            or claim.recorded_prewrite_slot != live_target.recorded_prewrite_slot
            or type(claim.forward_step_count) is not int
            or claim.forward_step_count != gateway.step_count
            or claim.forward_steps_digest != gateway.steps_digest
            or type(claim.first_step_order) is not int
            or claim.first_step_order != first_step.order
            or claim.first_step_order != 1
            or claim.first_step_operation_id != first_step.operation_id
            or claim.first_step_digest != _digest({"gateway_step": asdict(first_step)})
            or claim.first_step_transport != first_step.transport.value
            or first_step.phase is not GatewayStepPhase.PRECONDITION
            or first_step.category is not OperationClass.READ_ONLY
            or first_step.phone_changes
            or claim.forward_scope_only is not True
            or claim.recovery_authority_granted is not False
            or claim.wipe_authority_granted is not False
            or claim.automatic_recovery_enabled is not False
            or claim.automatic_wipe_enabled is not False
            or claim.bootloader_relock_allowed is not False
            or claim.exclusive_execution_claim_recorded is not True
            or claim.execution_grant_claimed_once is not True
            or not _hex(claim.device_open_permit_id, 32)
            or not _hex(claim.device_open_permit_token_sha256, 64)
            or claim.device_open_permit_token_persisted is not False
            or claim.device_open_authority != self.DEVICE_OPEN_AUTHORITY
            or claim.device_access_opened is not False
            or claim.first_forward_step_started is not False
            or claim.phone_changed is not False
            or not _hex(digest, 64)
            or digest != _digest(payload)
        ):
            raise RuntimeExecutionClaimError(
                "Runtime execution claim failed exact integrity or safety validation"
            )

    def _path(self, project_id: str, execution_grant_id: str) -> Path:
        self.store.get(project_id)
        if not _hex(execution_grant_id, 32):
            raise RuntimeExecutionClaimError("Runtime execution-grant identity is invalid")
        return (
            self.store.projects_root
            / project_id
            / "guardian"
            / f"runtime-execution-claim-{execution_grant_id}.romverse"
        )

    @staticmethod
    def _validate_private_key(
        runtime_public_key: Ed25519PublicKey,
        runtime_private_key: Ed25519PrivateKey,
    ) -> None:
        if not isinstance(runtime_public_key, Ed25519PublicKey) or not isinstance(
            runtime_private_key, Ed25519PrivateKey
        ):
            raise RuntimeExecutionClaimError("Runtime execution-claim signing key is not trusted")
        enrolled = runtime_public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        signing = runtime_private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        if not hmac.compare_digest(enrolled, signing):
            raise RuntimeExecutionClaimError(
                "Runtime execution-claim key does not match the enrolled runtime"
            )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeExecutionClaimError("Runtime execution-claim clock must be timezone-aware")
        return value.astimezone(UTC)


def _read_exact_json(path: Path, *, boundary: Path, maximum_bytes: int) -> dict[str, Any]:
    encoded = read_regular_bytes(path, boundary=boundary, maximum_bytes=maximum_bytes)
    try:
        value = json.loads(encoded, object_pairs_hook=_strict_object)
    except RuntimeExecutionClaimError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeExecutionClaimError("Runtime execution claim is not valid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeExecutionClaimError("Runtime execution claim must be one object")
    return value


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeExecutionClaimError(f"Duplicate runtime execution-claim field: {key}")
        result[key] = value
    return result


def _canonical_bytes(payload: object) -> bytes:
    try:
        return json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise RuntimeExecutionClaimError(
            "Runtime execution claim cannot be represented canonically"
        ) from exc


def _digest(payload: object) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not 20 <= len(value) <= 40:
        raise RuntimeExecutionClaimError(f"{label.capitalize()} timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeExecutionClaimError(f"{label.capitalize()} timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeExecutionClaimError(f"{label.capitalize()} timestamp requires a zone")
    return parsed.astimezone(UTC)


def _hex(value: object, length: int) -> bool:
    return bool(isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value))


def _signature(value: object) -> bytes:
    if not isinstance(value, str) or len(value) > 128:
        raise RuntimeExecutionClaimError("Runtime execution-claim signature is malformed")
    try:
        signature = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RuntimeExecutionClaimError("Runtime execution-claim signature is malformed") from exc
    if len(signature) != 64:
        raise RuntimeExecutionClaimError("Runtime execution-claim signature has invalid length")
    return signature
