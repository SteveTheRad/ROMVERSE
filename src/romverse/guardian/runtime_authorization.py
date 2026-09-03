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
from romverse.guardian.consent_capability import (
    ConsentCapabilityReservationError,
    GuardianConsentCapabilityReservation,
    GuardianConsentCapabilityReservationService,
)
from romverse.guardian.execution_gateway_contract import GuardianExecutionGatewayContract
from romverse.guardian.execution_plan import GuardianExecutionPlan
from romverse.guardian.execution_result_receipt import (
    ExecutionResultValidationError,
    GuardianRuntimeTrust,
    validate_guardian_runtime_trust,
)
from romverse.guardian.final_consent import GuardianFinalConsentGrant
from romverse.guardian.live_target_receipt import GuardianLiveTargetReceipt
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
class GuardianRuntimeConsentConsumption:
    """Runtime-signed proof that one exact consent capability was consumed once."""

    schema_version: int
    consumption_id: str
    consumed_at: str
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
    final_consent_id: str
    final_consent_receipt_digest: str
    ephemeral_grant_token_sha256: str
    ephemeral_grant_token_persisted: bool
    reservation_id: str
    reservation_digest: str
    runtime_session_id: str
    runtime_session_attestation_digest: str
    runtime_session_envelope_sha256: str
    runtime_instance_nonce_sha256: str
    runtime_trust_digest: str
    runtime_signer_key_id: str
    runtime_public_key_sha256: str
    runtime_adapter_id: str
    runtime_adapter_version: int
    runtime_adapter_sha256: str
    result_receipt_schema_version: int
    forward_step_count: int
    forward_steps_digest: str
    data_action: str
    forward_scope_only: bool
    recovery_authority_granted: bool
    wipe_authority_granted: bool
    automatic_recovery_enabled: bool
    automatic_wipe_enabled: bool
    bootloader_relock_allowed: bool
    runtime_consumption_completed: bool
    execution_grant_id: str
    execution_grant_token_sha256: str
    execution_grant_token_persisted: bool
    execution_grant_issued: bool
    execution_authority: str
    device_access_opened: bool
    runtime_invoked: bool
    phone_changed: bool
    consumption_digest: str


@dataclass(frozen=True, slots=True)
class VerifiedGuardianRuntimeConsentConsumption:
    consumption: GuardianRuntimeConsentConsumption
    signer_key_id: str
    signed_envelope_sha256: str


@dataclass(frozen=True, slots=True)
class GuardianRuntimeForwardExecutionGrant:
    """Memory-only exact forward grant; a later executor must claim it once."""

    verified_consumption: VerifiedGuardianRuntimeConsentConsumption
    ephemeral_execution_token: str = field(repr=False)


class RuntimeAuthorizationError(ProjectError):
    """One-use runtime consumption or exact forward authorization failed closed."""


class GuardianRuntimeAuthorizationService:
    """Consume final consent once and issue a runtime-signed memory-only grant.

    This service is intended for the separately packaged Guardian runtime. It requires
    that runtime's externally enrolled private key, revalidates the entire current
    Desktop reservation/session/consent context, and creates one exclusive signed
    consumption record before returning an in-memory forward grant. The raw consent and
    execution tokens are never written. There is deliberately no device runner or
    command method here: the next runtime stage must atomically claim this exact grant
    immediately before opening the selected device.
    """

    FORMAT = "romverse.guardian-runtime-consent-consumption"
    SCHEMA_VERSION = 1
    ALGORITHM = "ed25519"
    DOMAIN = b"ROMVERSE-GUARDIAN-RUNTIME-CONSENT-CONSUMPTION-V1\0"
    MAX_BYTES = 256 * 1024
    EXECUTION_AUTHORITY = "exact-forward-gateway-once"
    ENVELOPE_FIELDS = {
        "format",
        "schema_version",
        "algorithm",
        "key_id",
        "consumption_sha256",
        "consumption",
        "signature",
    }
    CONSUMPTION_FIELDS = {field.name for field in fields(GuardianRuntimeConsentConsumption)}

    def __init__(
        self,
        store: RomProjectStore,
        reservations: GuardianConsentCapabilityReservationService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.reservations = reservations
        self.clock = clock or (lambda: datetime.now(UTC))

    def consume(
        self,
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
    ) -> GuardianRuntimeForwardExecutionGrant:
        """Atomically consume one exact grant without opening device access."""

        try:
            consumed_at = self._now()
            self._validate_context(
                grant,
                reservation,
                session,
                gateway,
                plan,
                live_target,
                reviewed_device,
                runtime_trust,
                runtime_public_key,
                runtime_private_key,
                now=consumed_at,
            )
            expires_at = _timestamp(reservation.expires_at, "runtime authorization expiry")
            if consumed_at >= expires_at:
                raise RuntimeAuthorizationError(
                    "Consent expired before the runtime could consume it"
                )
            execution_token = secrets.token_hex(32)
            attestation = session.attestation
            receipt = grant.receipt
            payload: dict[str, object] = {
                "schema_version": self.SCHEMA_VERSION,
                "consumption_id": uuid4().hex,
                "consumed_at": consumed_at.isoformat(),
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
                "final_consent_id": receipt.consent_id,
                "final_consent_receipt_digest": receipt.receipt_digest,
                "ephemeral_grant_token_sha256": receipt.ephemeral_grant_token_sha256,
                "ephemeral_grant_token_persisted": False,
                "reservation_id": reservation.reservation_id,
                "reservation_digest": reservation.reservation_digest,
                "runtime_session_id": attestation.session_id,
                "runtime_session_attestation_digest": attestation.attestation_digest,
                "runtime_session_envelope_sha256": session.signed_envelope_sha256,
                "runtime_instance_nonce_sha256": attestation.runtime_instance_nonce_sha256,
                "runtime_trust_digest": _digest(asdict(runtime_trust)),
                "runtime_signer_key_id": runtime_trust.key_id,
                "runtime_public_key_sha256": runtime_trust.public_key_sha256,
                "runtime_adapter_id": runtime_trust.adapter_id,
                "runtime_adapter_version": runtime_trust.adapter_version,
                "runtime_adapter_sha256": runtime_trust.adapter_sha256,
                "result_receipt_schema_version": gateway.result_receipt_schema_version,
                "forward_step_count": gateway.step_count,
                "forward_steps_digest": gateway.steps_digest,
                "data_action": receipt.data_action.value,
                "forward_scope_only": True,
                "recovery_authority_granted": False,
                "wipe_authority_granted": False,
                "automatic_recovery_enabled": False,
                "automatic_wipe_enabled": False,
                "bootloader_relock_allowed": False,
                "runtime_consumption_completed": True,
                "execution_grant_id": uuid4().hex,
                "execution_grant_token_sha256": _text_digest(execution_token),
                "execution_grant_token_persisted": False,
                "execution_grant_issued": True,
                "execution_authority": self.EXECUTION_AUTHORITY,
                "device_access_opened": False,
                "runtime_invoked": True,
                "phone_changed": False,
            }
            consumption = GuardianRuntimeConsentConsumption(
                **payload,
                consumption_digest=_digest(payload),
            )
            encoded = _canonical_bytes(asdict(consumption))
            envelope: dict[str, object] = {
                "format": self.FORMAT,
                "schema_version": self.SCHEMA_VERSION,
                "algorithm": self.ALGORITHM,
                "key_id": runtime_trust.key_id,
                "consumption_sha256": hashlib.sha256(encoded).hexdigest(),
                "consumption": asdict(consumption),
                "signature": base64.b64encode(
                    runtime_private_key.sign(self.DOMAIN + encoded)
                ).decode("ascii"),
            }
            verified = self._verify_envelope(
                envelope,
                reservation,
                session,
                gateway,
                plan,
                live_target,
                grant,
                runtime_trust,
                runtime_public_key,
                now=consumed_at,
            )
            path = self._path(gateway.project_id, receipt.consent_id)
            ensure_private_directory(path.parent, boundary=self.store.workspace)
            exclusive_create_json(
                path,
                envelope,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            return GuardianRuntimeForwardExecutionGrant(verified, execution_token)
        except LocalStoreConflictError as exc:
            raise RuntimeAuthorizationError(
                "This final-consent capability has already been consumed"
            ) from exc
        except RuntimeAuthorizationError:
            raise
        except (
            ConsentCapabilityReservationError,
            ExecutionResultValidationError,
            LocalStoreError,
            OSError,
            TypeError,
            ValueError,
            KeyError,
            ProjectError,
        ) as exc:
            raise RuntimeAuthorizationError(
                "Runtime authorization failed closed without opening device access"
            ) from exc

    def load(
        self,
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
    ) -> VerifiedGuardianRuntimeConsentConsumption | None:
        """Reload only signed audit proof; the memory-only execution token is unrecoverable."""

        try:
            checked_at = now or self._now()
            self._validate_context(
                grant,
                reservation,
                session,
                gateway,
                plan,
                live_target,
                reviewed_device,
                runtime_trust,
                runtime_public_key,
                None,
                now=checked_at,
            )
            envelope = _read_exact_json(
                self._path(gateway.project_id, grant.receipt.consent_id),
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            return self._verify_envelope(
                envelope,
                reservation,
                session,
                gateway,
                plan,
                live_target,
                grant,
                runtime_trust,
                runtime_public_key,
                now=checked_at,
            )
        except (
            RuntimeAuthorizationError,
            ConsentCapabilityReservationError,
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

    def validate_in_memory_grant(
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
    ) -> None:
        """Revalidate the non-persisted forward capability without using it."""

        if not isinstance(runtime_grant, GuardianRuntimeForwardExecutionGrant) or not _hex(
            runtime_grant.ephemeral_execution_token, 64
        ):
            raise RuntimeAuthorizationError("Runtime execution grant is malformed")
        current = self.load(
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
        if current is None or current != runtime_grant.verified_consumption:
            raise RuntimeAuthorizationError("Runtime execution grant is no longer current")
        if not hmac.compare_digest(
            _text_digest(runtime_grant.ephemeral_execution_token),
            current.consumption.execution_grant_token_sha256,
        ):
            raise RuntimeAuthorizationError("Runtime execution token does not match")

    def _validate_context(
        self,
        grant: GuardianFinalConsentGrant,
        reservation: GuardianConsentCapabilityReservation,
        session: VerifiedGuardianRuntimeSession,
        gateway: GuardianExecutionGatewayContract,
        plan: GuardianExecutionPlan,
        live_target: GuardianLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        runtime_trust: GuardianRuntimeTrust,
        runtime_public_key: Ed25519PublicKey,
        runtime_private_key: Ed25519PrivateKey | None,
        *,
        now: datetime,
    ) -> None:
        current = self.reservations.load(
            grant,
            session,
            gateway,
            plan,
            live_target,
            reviewed_device,
            runtime_trust,
            runtime_public_key,
            now=now,
        )
        if current is None or current != reservation:
            raise RuntimeAuthorizationError(
                "Runtime consumption requires the current exact consent reservation"
            )
        validate_guardian_runtime_trust(runtime_trust, runtime_public_key, gateway)
        if runtime_private_key is not None:
            if not isinstance(runtime_private_key, Ed25519PrivateKey):
                raise RuntimeAuthorizationError("Runtime signing key type is not trusted")
            enrolled = runtime_public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            signing = runtime_private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            if not hmac.compare_digest(enrolled, signing):
                raise RuntimeAuthorizationError(
                    "Runtime signing key does not match the enrolled runtime"
                )

    def _verify_envelope(
        self,
        envelope: dict[str, Any],
        reservation: GuardianConsentCapabilityReservation,
        session: VerifiedGuardianRuntimeSession,
        gateway: GuardianExecutionGatewayContract,
        plan: GuardianExecutionPlan,
        live_target: GuardianLiveTargetReceipt,
        grant: GuardianFinalConsentGrant,
        runtime_trust: GuardianRuntimeTrust,
        runtime_public_key: Ed25519PublicKey,
        *,
        now: datetime,
    ) -> VerifiedGuardianRuntimeConsentConsumption:
        if not isinstance(envelope, dict) or set(envelope) != self.ENVELOPE_FIELDS:
            raise RuntimeAuthorizationError("Runtime authorization envelope fields do not match")
        if (
            envelope["format"] != self.FORMAT
            or type(envelope["schema_version"]) is not int
            or envelope["schema_version"] != self.SCHEMA_VERSION
            or envelope["algorithm"] != self.ALGORITHM
            or envelope["key_id"] != runtime_trust.key_id
        ):
            raise RuntimeAuthorizationError("Runtime authorization signer or schema is not trusted")
        raw = envelope["consumption"]
        if not isinstance(raw, dict) or set(raw) != self.CONSUMPTION_FIELDS:
            raise RuntimeAuthorizationError("Runtime authorization payload fields do not match")
        encoded = _canonical_bytes(raw)
        if len(encoded) > self.MAX_BYTES:
            raise RuntimeAuthorizationError("Runtime authorization exceeds its size boundary")
        signed_digest = hashlib.sha256(encoded).hexdigest()
        if envelope["consumption_sha256"] != signed_digest:
            raise RuntimeAuthorizationError("Runtime authorization signed digest does not match")
        try:
            runtime_public_key.verify(
                _signature(envelope["signature"]),
                self.DOMAIN + encoded,
            )
        except InvalidSignature as exc:
            raise RuntimeAuthorizationError(
                "Runtime authorization signature verification failed"
            ) from exc
        consumption = GuardianRuntimeConsentConsumption(**raw)
        self._validate_consumption(
            consumption,
            reservation,
            session,
            gateway,
            plan,
            live_target,
            grant,
            runtime_trust,
            now=now,
        )
        return VerifiedGuardianRuntimeConsentConsumption(
            consumption,
            runtime_trust.key_id,
            _digest(envelope),
        )

    def _validate_consumption(
        self,
        consumption: GuardianRuntimeConsentConsumption,
        reservation: GuardianConsentCapabilityReservation,
        session: VerifiedGuardianRuntimeSession,
        gateway: GuardianExecutionGatewayContract,
        plan: GuardianExecutionPlan,
        live_target: GuardianLiveTargetReceipt,
        grant: GuardianFinalConsentGrant,
        runtime_trust: GuardianRuntimeTrust,
        *,
        now: datetime,
    ) -> None:
        payload = asdict(consumption)
        digest = str(payload.pop("consumption_digest", ""))
        consumed = _timestamp(consumption.consumed_at, "runtime consumption")
        expires = _timestamp(consumption.expires_at, "runtime authorization expiry")
        attestation = session.attestation
        receipt = grant.receipt
        if (
            type(consumption.schema_version) is not int
            or consumption.schema_version != self.SCHEMA_VERSION
            or not _hex(consumption.consumption_id, 32)
            or not consumed <= now <= expires
            or consumed >= expires
            or expires != _timestamp(reservation.expires_at, "reservation expiry")
            or consumption.project_id != gateway.project_id
            or consumption.gateway_contract_digest != gateway.contract_digest
            or consumption.plan_digest != plan.plan_digest
            or consumption.manifest_digest != gateway.manifest_digest
            or consumption.artifact_binding_digest != gateway.artifact_binding_digest
            or consumption.live_target_receipt_digest != live_target.receipt_digest
            or consumption.device_key != gateway.device_key
            or consumption.device_pack_id != gateway.device_pack_id
            or consumption.device_pack_version != gateway.device_pack_version
            or consumption.device_pack_sha256 != gateway.device_pack_sha256
            or consumption.final_consent_id != receipt.consent_id
            or consumption.final_consent_receipt_digest != receipt.receipt_digest
            or consumption.ephemeral_grant_token_sha256 != receipt.ephemeral_grant_token_sha256
            or consumption.ephemeral_grant_token_persisted is not False
            or consumption.reservation_id != reservation.reservation_id
            or consumption.reservation_digest != reservation.reservation_digest
            or consumption.runtime_session_id != attestation.session_id
            or consumption.runtime_session_attestation_digest != attestation.attestation_digest
            or consumption.runtime_session_envelope_sha256 != session.signed_envelope_sha256
            or consumption.runtime_instance_nonce_sha256
            != attestation.runtime_instance_nonce_sha256
            or consumption.runtime_trust_digest != _digest(asdict(runtime_trust))
            or consumption.runtime_signer_key_id != runtime_trust.key_id
            or consumption.runtime_public_key_sha256 != runtime_trust.public_key_sha256
            or consumption.runtime_adapter_id != runtime_trust.adapter_id
            or type(consumption.runtime_adapter_version) is not int
            or consumption.runtime_adapter_version != runtime_trust.adapter_version
            or consumption.runtime_adapter_sha256 != runtime_trust.adapter_sha256
            or type(consumption.result_receipt_schema_version) is not int
            or consumption.result_receipt_schema_version != gateway.result_receipt_schema_version
            or type(consumption.forward_step_count) is not int
            or consumption.forward_step_count != gateway.step_count
            or consumption.forward_steps_digest != gateway.steps_digest
            or consumption.data_action != receipt.data_action.value
            or consumption.forward_scope_only is not True
            or consumption.recovery_authority_granted is not False
            or consumption.wipe_authority_granted is not False
            or consumption.automatic_recovery_enabled is not False
            or consumption.automatic_wipe_enabled is not False
            or consumption.bootloader_relock_allowed is not False
            or consumption.runtime_consumption_completed is not True
            or not _hex(consumption.execution_grant_id, 32)
            or not _hex(consumption.execution_grant_token_sha256, 64)
            or consumption.execution_grant_token_persisted is not False
            or consumption.execution_grant_issued is not True
            or consumption.execution_authority != self.EXECUTION_AUTHORITY
            or consumption.device_access_opened is not False
            or consumption.runtime_invoked is not True
            or consumption.phone_changed is not False
            or not _hex(digest, 64)
            or digest != _digest(payload)
        ):
            raise RuntimeAuthorizationError(
                "Runtime authorization failed exact integrity or safety validation"
            )

    def _path(self, project_id: str, consent_id: str) -> Path:
        self.store.get(project_id)
        if not _hex(consent_id, 32):
            raise RuntimeAuthorizationError("Final-consent identity is invalid")
        return (
            self.store.projects_root
            / project_id
            / "guardian"
            / f"runtime-consent-consumption-{consent_id}.romverse"
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeAuthorizationError("Runtime-authorization clock must be timezone-aware")
        return value.astimezone(UTC)


def _read_exact_json(path: Path, *, boundary: Path, maximum_bytes: int) -> dict[str, Any]:
    encoded = read_regular_bytes(path, boundary=boundary, maximum_bytes=maximum_bytes)
    try:
        value = json.loads(encoded, object_pairs_hook=_strict_object)
    except RuntimeAuthorizationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeAuthorizationError("Runtime authorization is not valid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeAuthorizationError("Runtime authorization must be one object")
    return value


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeAuthorizationError(f"Duplicate runtime-authorization field: {key}")
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
        raise RuntimeAuthorizationError(
            "Runtime authorization cannot be represented canonically"
        ) from exc


def _digest(payload: object) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not 20 <= len(value) <= 40:
        raise RuntimeAuthorizationError(f"{label.capitalize()} timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeAuthorizationError(f"{label.capitalize()} timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeAuthorizationError(f"{label.capitalize()} timestamp requires a zone")
    return parsed.astimezone(UTC)


def _hex(value: object, length: int) -> bool:
    return bool(isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value))


def _signature(value: object) -> bytes:
    if not isinstance(value, str) or len(value) > 128:
        raise RuntimeAuthorizationError("Runtime authorization signature is malformed")
    try:
        signature = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RuntimeAuthorizationError("Runtime authorization signature is malformed") from exc
    if len(signature) != 64:
        raise RuntimeAuthorizationError("Runtime authorization signature has invalid length")
    return signature
