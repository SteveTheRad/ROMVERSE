from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from romverse.device.models import AndroidDevice
from romverse.guardian.execution_gateway_contract import GuardianExecutionGatewayContract
from romverse.guardian.execution_plan import GuardianExecutionPlan
from romverse.guardian.execution_result_receipt import GuardianRuntimeTrust
from romverse.guardian.final_consent import (
    FinalConsentValidationError,
    GuardianFinalConsentGrant,
    GuardianFinalConsentReceiptService,
)
from romverse.guardian.live_target_receipt import GuardianLiveTargetReceipt
from romverse.guardian.runtime_session import (
    GuardianRuntimeSessionService,
    RuntimeSessionValidationError,
    VerifiedGuardianRuntimeSession,
)
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
class GuardianConsentCapabilityReservation:
    """Exclusive local reservation of exact consent; still not runtime consumption."""

    schema_version: int
    reservation_id: str
    reserved_at: str
    expires_at: str
    project_id: str
    gateway_contract_digest: str
    plan_digest: str
    live_target_receipt_digest: str
    device_key: str
    final_consent_id: str
    final_consent_receipt_digest: str
    ephemeral_grant_token_sha256: str
    ephemeral_grant_token_persisted: bool
    runtime_session_id: str
    runtime_session_attestation_digest: str
    runtime_session_envelope_sha256: str
    runtime_trust_digest: str
    runtime_signer_key_id: str
    runtime_adapter_id: str
    runtime_adapter_version: int
    runtime_adapter_sha256: str
    forward_scope_only: bool
    recovery_authority_granted: bool
    wipe_authority_granted: bool
    bootloader_relock_allowed: bool
    exclusive_reservation_recorded: bool
    runtime_consumption_completed: bool
    execution_grant_issued: bool
    execution_authority: str
    device_access_opened: bool
    runtime_invoked: bool
    phone_changed: bool
    reservation_digest: str


class ConsentCapabilityReservationError(ProjectError):
    """A final-consent capability reservation failed closed."""


class GuardianConsentCapabilityReservationService:
    """Reserve one exact grant for one verified runtime session.

    The reservation filename is derived from the random consent identity and created with
    an exclusive filesystem operation, so concurrent callers cannot both reserve the same
    grant. The raw token is never persisted. This stage deliberately does not consume the
    token inside a runtime, issue execution authority, open device access, or run a command.
    """

    FORMAT = "romverse.guardian-consent-capability-reservation"
    SCHEMA_VERSION = 1
    MAX_BYTES = 128 * 1024
    EXECUTION_AUTHORITY = "none"

    def __init__(
        self,
        store: RomProjectStore,
        final_consents: GuardianFinalConsentReceiptService,
        runtime_sessions: GuardianRuntimeSessionService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.final_consents = final_consents
        self.runtime_sessions = runtime_sessions
        self.clock = clock or (lambda: datetime.now(UTC))

    def reserve(
        self,
        grant: GuardianFinalConsentGrant,
        session: VerifiedGuardianRuntimeSession,
        gateway: GuardianExecutionGatewayContract,
        plan: GuardianExecutionPlan,
        live_target: GuardianLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        runtime_trust: GuardianRuntimeTrust,
        runtime_public_key: Ed25519PublicKey,
    ) -> GuardianConsentCapabilityReservation:
        """Atomically reserve one exact consent/session pair without invoking a runtime."""

        try:
            reserved = self._now()
            self._validate_context(
                grant,
                session,
                gateway,
                plan,
                live_target,
                reviewed_device,
                runtime_trust,
                runtime_public_key,
                now=reserved,
            )
            expires = min(
                _timestamp(grant.receipt.expires_at, "final-consent expiry"),
                _timestamp(session.attestation.expires_at, "runtime-session expiry"),
            )
            if reserved >= expires:
                raise ConsentCapabilityReservationError(
                    "The consent or runtime session expired before reservation"
                )
            attestation = session.attestation
            payload: dict[str, object] = {
                "schema_version": self.SCHEMA_VERSION,
                "reservation_id": uuid4().hex,
                "reserved_at": reserved.isoformat(),
                "expires_at": expires.isoformat(),
                "project_id": gateway.project_id,
                "gateway_contract_digest": gateway.contract_digest,
                "plan_digest": plan.plan_digest,
                "live_target_receipt_digest": live_target.receipt_digest,
                "device_key": gateway.device_key,
                "final_consent_id": grant.receipt.consent_id,
                "final_consent_receipt_digest": grant.receipt.receipt_digest,
                "ephemeral_grant_token_sha256": grant.receipt.ephemeral_grant_token_sha256,
                "ephemeral_grant_token_persisted": False,
                "runtime_session_id": attestation.session_id,
                "runtime_session_attestation_digest": attestation.attestation_digest,
                "runtime_session_envelope_sha256": session.signed_envelope_sha256,
                "runtime_trust_digest": grant.receipt.runtime_trust_digest,
                "runtime_signer_key_id": runtime_trust.key_id,
                "runtime_adapter_id": runtime_trust.adapter_id,
                "runtime_adapter_version": runtime_trust.adapter_version,
                "runtime_adapter_sha256": runtime_trust.adapter_sha256,
                "forward_scope_only": True,
                "recovery_authority_granted": False,
                "wipe_authority_granted": False,
                "bootloader_relock_allowed": False,
                "exclusive_reservation_recorded": True,
                "runtime_consumption_completed": False,
                "execution_grant_issued": False,
                "execution_authority": self.EXECUTION_AUTHORITY,
                "device_access_opened": False,
                "runtime_invoked": False,
                "phone_changed": False,
            }
            reservation = GuardianConsentCapabilityReservation(
                **payload,
                reservation_digest=_digest(payload),
            )
            self.validate(
                reservation,
                grant,
                session,
                gateway,
                plan,
                live_target,
                reviewed_device,
                runtime_trust,
                runtime_public_key,
                now=reserved,
            )
            path = self._path(gateway.project_id, grant.receipt.consent_id)
            ensure_private_directory(path.parent, boundary=self.store.workspace)
            exclusive_create_json(
                path,
                {"format": self.FORMAT, **asdict(reservation)},
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            return reservation
        except LocalStoreConflictError as exc:
            raise ConsentCapabilityReservationError(
                "This exact final-consent capability is already reserved"
            ) from exc
        except ConsentCapabilityReservationError:
            raise
        except (
            FinalConsentValidationError,
            RuntimeSessionValidationError,
            LocalStoreError,
            OSError,
            TypeError,
            ValueError,
            KeyError,
            ProjectError,
        ) as exc:
            raise ConsentCapabilityReservationError(
                "Consent capability reservation failed closed without opening device access"
            ) from exc

    def load(
        self,
        grant: GuardianFinalConsentGrant,
        session: VerifiedGuardianRuntimeSession,
        gateway: GuardianExecutionGatewayContract,
        plan: GuardianExecutionPlan,
        live_target: GuardianLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        runtime_trust: GuardianRuntimeTrust,
        runtime_public_key: Ed25519PublicKey,
        *,
        now: datetime | None = None,
    ) -> GuardianConsentCapabilityReservation | None:
        try:
            data = _read_exact_json(
                self._path(gateway.project_id, grant.receipt.consent_id),
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            expected = {
                "format",
                *(field.name for field in fields(GuardianConsentCapabilityReservation)),
            }
            if set(data) != expected or data.pop("format") != self.FORMAT:
                return None
            reservation = GuardianConsentCapabilityReservation(**data)
            self.validate(
                reservation,
                grant,
                session,
                gateway,
                plan,
                live_target,
                reviewed_device,
                runtime_trust,
                runtime_public_key,
                now=now or self._now(),
            )
            return reservation
        except (
            ConsentCapabilityReservationError,
            FinalConsentValidationError,
            RuntimeSessionValidationError,
            LocalStoreError,
            OSError,
            TypeError,
            ValueError,
            KeyError,
            ProjectError,
            json.JSONDecodeError,
        ):
            return None

    def validate(
        self,
        reservation: GuardianConsentCapabilityReservation,
        grant: GuardianFinalConsentGrant,
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
        checked_at = now or self._now()
        self._validate_context(
            grant,
            session,
            gateway,
            plan,
            live_target,
            reviewed_device,
            runtime_trust,
            runtime_public_key,
            now=checked_at,
        )
        payload = asdict(reservation)
        digest = str(payload.pop("reservation_digest", ""))
        reserved = _timestamp(reservation.reserved_at, "capability reservation")
        expires = _timestamp(reservation.expires_at, "capability reservation expiry")
        expected_expires = min(
            _timestamp(grant.receipt.expires_at, "final-consent expiry"),
            _timestamp(session.attestation.expires_at, "runtime-session expiry"),
        )
        attestation = session.attestation
        if (
            type(reservation.schema_version) is not int
            or reservation.schema_version != self.SCHEMA_VERSION
            or not _hex(reservation.reservation_id, 32)
            or not reserved <= checked_at <= expires
            or expires != expected_expires
            or reservation.project_id != gateway.project_id
            or reservation.gateway_contract_digest != gateway.contract_digest
            or reservation.plan_digest != plan.plan_digest
            or reservation.live_target_receipt_digest != live_target.receipt_digest
            or reservation.device_key != gateway.device_key
            or reservation.final_consent_id != grant.receipt.consent_id
            or reservation.final_consent_receipt_digest != grant.receipt.receipt_digest
            or reservation.ephemeral_grant_token_sha256
            != grant.receipt.ephemeral_grant_token_sha256
            or reservation.ephemeral_grant_token_persisted is not False
            or reservation.runtime_session_id != attestation.session_id
            or reservation.runtime_session_attestation_digest != attestation.attestation_digest
            or reservation.runtime_session_envelope_sha256 != session.signed_envelope_sha256
            or reservation.runtime_trust_digest != grant.receipt.runtime_trust_digest
            or reservation.runtime_signer_key_id != runtime_trust.key_id
            or reservation.runtime_adapter_id != runtime_trust.adapter_id
            or type(reservation.runtime_adapter_version) is not int
            or reservation.runtime_adapter_version != runtime_trust.adapter_version
            or reservation.runtime_adapter_sha256 != runtime_trust.adapter_sha256
            or reservation.forward_scope_only is not True
            or reservation.recovery_authority_granted is not False
            or reservation.wipe_authority_granted is not False
            or reservation.bootloader_relock_allowed is not False
            or reservation.exclusive_reservation_recorded is not True
            or reservation.runtime_consumption_completed is not False
            or reservation.execution_grant_issued is not False
            or reservation.execution_authority != self.EXECUTION_AUTHORITY
            or reservation.device_access_opened is not False
            or reservation.runtime_invoked is not False
            or reservation.phone_changed is not False
            or not _hex(digest, 64)
            or digest != _digest(payload)
        ):
            raise ConsentCapabilityReservationError(
                "Consent reservation failed exact integrity or safety validation"
            )

    def _validate_context(
        self,
        grant: GuardianFinalConsentGrant,
        session: VerifiedGuardianRuntimeSession,
        gateway: GuardianExecutionGatewayContract,
        plan: GuardianExecutionPlan,
        live_target: GuardianLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        runtime_trust: GuardianRuntimeTrust,
        runtime_public_key: Ed25519PublicKey,
        *,
        now: datetime,
    ) -> None:
        self.final_consents.validate_grant(
            grant,
            gateway,
            plan,
            live_target,
            reviewed_device,
            runtime_trust,
            runtime_public_key,
            now=now,
        )
        self.runtime_sessions.validate_session(
            session,
            gateway,
            live_target,
            reviewed_device,
            runtime_trust,
            runtime_public_key,
            now=now,
        )
        attestation = session.attestation
        if (
            grant.receipt.runtime_trust_digest != attestation.runtime_trust_digest
            or grant.receipt.runtime_signer_key_id != attestation.runtime_signer_key_id
            or grant.receipt.runtime_adapter_id != attestation.runtime_adapter_id
            or grant.receipt.runtime_adapter_version != attestation.runtime_adapter_version
            or grant.receipt.runtime_adapter_sha256 != attestation.runtime_adapter_sha256
            or grant.receipt.gateway_contract_digest != attestation.gateway_contract_digest
            or grant.receipt.live_target_receipt_digest != attestation.live_target_receipt_digest
            or grant.receipt.device_key != attestation.device_key
        ):
            raise ConsentCapabilityReservationError(
                "Consent and runtime session do not describe the same exact scope"
            )

    def _path(self, project_id: str, consent_id: str) -> Path:
        self.store.get(project_id)
        if not _hex(consent_id, 32):
            raise ConsentCapabilityReservationError("Final-consent identity is invalid")
        return (
            self.store.projects_root
            / project_id
            / "guardian"
            / f"consent-capability-reservation-{consent_id}.romverse"
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ConsentCapabilityReservationError(
                "Consent-reservation clock must be timezone-aware"
            )
        return value.astimezone(UTC)


def _read_exact_json(path: Path, *, boundary: Path, maximum_bytes: int) -> dict[str, Any]:
    encoded = read_regular_bytes(path, boundary=boundary, maximum_bytes=maximum_bytes)
    try:
        value = json.loads(encoded, object_pairs_hook=_strict_object)
    except ConsentCapabilityReservationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConsentCapabilityReservationError("Consent reservation is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ConsentCapabilityReservationError("Consent reservation must be one object")
    return value


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ConsentCapabilityReservationError(f"Duplicate consent-reservation field: {key}")
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
        raise ConsentCapabilityReservationError(
            "Consent reservation cannot be represented canonically"
        ) from exc


def _digest(payload: object) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not 20 <= len(value) <= 40:
        raise ConsentCapabilityReservationError(f"{label.capitalize()} timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConsentCapabilityReservationError(
            f"{label.capitalize()} timestamp is invalid"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConsentCapabilityReservationError(f"{label.capitalize()} timestamp requires a zone")
    return parsed.astimezone(UTC)


def _hex(value: object, length: int) -> bool:
    return bool(isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value))
