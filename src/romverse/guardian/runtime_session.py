from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from romverse.device.models import AndroidDevice
from romverse.guardian.execution_gateway_contract import (
    GuardianExecutionGatewayContract,
    GuardianExecutionGatewayContractService,
)
from romverse.guardian.execution_result_receipt import (
    ExecutionResultValidationError,
    GuardianRuntimeTrust,
    validate_guardian_runtime_trust,
)
from romverse.guardian.live_target_receipt import (
    GuardianLiveTargetReceipt,
    GuardianLiveTargetReceiptService,
)
from romverse.infrastructure.local_store import (
    LocalStoreConflictError,
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    exclusive_create_json,
    read_regular_bytes,
    remove_regular_file,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


@dataclass(frozen=True, slots=True)
class GuardianRuntimeHandshakeChallenge:
    """Short-lived Desktop challenge bound to one exact live Guardian context."""

    schema_version: int
    challenge_id: str
    issued_at: str
    expires_at: str
    project_id: str
    gateway_contract_digest: str
    live_target_receipt_digest: str
    device_key: str
    runtime_trust_digest: str
    runtime_signer_key_id: str
    runtime_public_key_sha256: str
    runtime_adapter_id: str
    runtime_adapter_version: int
    runtime_adapter_sha256: str
    result_receipt_schema_version: int
    runtime_protocol_version: int
    execution_authority: str
    runtime_invoked: bool
    phone_changed: bool
    challenge_digest: str


@dataclass(frozen=True, slots=True)
class GuardianRuntimeSessionAttestation:
    """Externally signed proof that one runtime instance accepted the exact scope."""

    schema_version: int
    session_id: str
    responded_at: str
    expires_at: str
    challenge_id: str
    challenge_digest: str
    project_id: str
    gateway_contract_digest: str
    live_target_receipt_digest: str
    device_key: str
    runtime_trust_digest: str
    runtime_signer_key_id: str
    runtime_public_key_sha256: str
    runtime_adapter_id: str
    runtime_adapter_version: int
    runtime_adapter_sha256: str
    runtime_platform: str
    runtime_architecture: str
    runtime_protocol_version: int
    result_receipt_schema_version: int
    runtime_instance_nonce_sha256: str
    accepts_exact_gateway: bool
    accepts_forward_scope_only: bool
    automatic_recovery_enabled: bool
    automatic_wipe_enabled: bool
    bootloader_relock_enabled: bool
    execution_authority: str
    device_access_opened: bool
    phone_changed: bool
    attestation_digest: str


@dataclass(frozen=True, slots=True)
class VerifiedGuardianRuntimeSession:
    attestation: GuardianRuntimeSessionAttestation
    signer_key_id: str
    signed_envelope_sha256: str
    challenge_claimed_once: bool


class RuntimeSessionValidationError(ProjectError):
    """A runtime challenge, signature, session, or exclusive claim failed closed."""


class GuardianRuntimeSessionService:
    """Verify a separate runtime instance without opening device access.

    This service creates a local nonce challenge, verifies a domain-separated Ed25519
    response from an externally enrolled runtime identity, and records one exclusive
    response claim. It contains no private key, process launcher, device runner, command,
    consent, or execution method. A verified session is therefore identity evidence,
    never phone authority.
    """

    CHALLENGE_FORMAT = "romverse.guardian-runtime-handshake-challenge"
    SESSION_FORMAT = "romverse.guardian-runtime-session-attestation"
    CLAIM_FORMAT = "romverse.guardian-runtime-handshake-claim"
    SCHEMA_VERSION = 1
    PROTOCOL_VERSION = 1
    ALGORITHM = "ed25519"
    DOMAIN = b"ROMVERSE-GUARDIAN-RUNTIME-SESSION-V1\0"
    CHALLENGE_NAME = "runtime-handshake-challenge.romverse"
    SESSION_NAME = "runtime-session-attestation.romverse"
    MAX_BYTES = 128 * 1024
    VALIDITY_SECONDS = 45
    EXECUTION_AUTHORITY = "none"
    ENVELOPE_FIELDS = {
        "format",
        "schema_version",
        "algorithm",
        "key_id",
        "attestation_sha256",
        "attestation",
        "signature",
    }
    ATTESTATION_FIELDS = {field.name for field in fields(GuardianRuntimeSessionAttestation)}

    def __init__(
        self,
        store: RomProjectStore,
        live_targets: GuardianLiveTargetReceiptService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.live_targets = live_targets
        self.clock = clock or (lambda: datetime.now(UTC))

    def issue_challenge(
        self,
        gateway: GuardianExecutionGatewayContract,
        live_target: GuardianLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        runtime_trust: GuardianRuntimeTrust,
        runtime_public_key: Ed25519PublicKey,
    ) -> GuardianRuntimeHandshakeChallenge:
        """Create a short-lived nonce after independently revalidating every binding."""

        try:
            issued = self._now()
            self._validate_context(
                gateway,
                live_target,
                reviewed_device,
                runtime_trust,
                runtime_public_key,
                now=issued,
            )
            live_expires = _timestamp(live_target.expires_at, "live-target expiry")
            expires = min(live_expires, issued + timedelta(seconds=self.VALIDITY_SECONDS))
            if issued >= expires:
                raise RuntimeSessionValidationError(
                    "The live-target receipt expires before a runtime can answer"
                )
            payload: dict[str, object] = {
                "schema_version": self.SCHEMA_VERSION,
                "challenge_id": uuid4().hex,
                "issued_at": issued.isoformat(),
                "expires_at": expires.isoformat(),
                "project_id": gateway.project_id,
                "gateway_contract_digest": gateway.contract_digest,
                "live_target_receipt_digest": live_target.receipt_digest,
                "device_key": gateway.device_key,
                "runtime_trust_digest": _digest(asdict(runtime_trust)),
                "runtime_signer_key_id": runtime_trust.key_id,
                "runtime_public_key_sha256": runtime_trust.public_key_sha256,
                "runtime_adapter_id": runtime_trust.adapter_id,
                "runtime_adapter_version": runtime_trust.adapter_version,
                "runtime_adapter_sha256": runtime_trust.adapter_sha256,
                "result_receipt_schema_version": gateway.result_receipt_schema_version,
                "runtime_protocol_version": self.PROTOCOL_VERSION,
                "execution_authority": self.EXECUTION_AUTHORITY,
                "runtime_invoked": False,
                "phone_changed": False,
            }
            challenge = GuardianRuntimeHandshakeChallenge(
                **payload,
                challenge_digest=_digest(payload),
            )
            self.validate_challenge(
                challenge,
                gateway,
                live_target,
                reviewed_device,
                runtime_trust,
                runtime_public_key,
                now=issued,
            )
            root = self._root(gateway.project_id)
            ensure_private_directory(root, boundary=self.store.workspace)
            remove_regular_file(
                root / self.SESSION_NAME,
                boundary=self.store.workspace,
                missing_ok=True,
            )
            atomic_write_json(
                root / self.CHALLENGE_NAME,
                {"format": self.CHALLENGE_FORMAT, **asdict(challenge)},
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            return challenge
        except RuntimeSessionValidationError:
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
            raise RuntimeSessionValidationError(
                "Runtime challenge failed closed without opening device access"
            ) from exc

    def accept(
        self,
        envelope: dict[str, Any],
        challenge: GuardianRuntimeHandshakeChallenge,
        gateway: GuardianExecutionGatewayContract,
        live_target: GuardianLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        runtime_trust: GuardianRuntimeTrust,
        runtime_public_key: Ed25519PublicKey,
    ) -> VerifiedGuardianRuntimeSession:
        """Verify and exclusively claim one signed answer to the current challenge."""

        try:
            now = self._now()
            current = self.load_challenge(
                gateway,
                live_target,
                reviewed_device,
                runtime_trust,
                runtime_public_key,
                now=now,
            )
            if current is None or current != challenge:
                raise RuntimeSessionValidationError("Runtime challenge is no longer current")
            verified = self._verify_envelope(
                envelope,
                challenge,
                gateway,
                runtime_trust,
                runtime_public_key,
                now=now,
            )
            claim_payload: dict[str, object] = {
                "schema_version": self.SCHEMA_VERSION,
                "challenge_id": challenge.challenge_id,
                "challenge_digest": challenge.challenge_digest,
                "session_id": verified.attestation.session_id,
                "attestation_digest": verified.attestation.attestation_digest,
                "signed_envelope_sha256": verified.signed_envelope_sha256,
                "claimed_at": now.isoformat(),
                "exclusive_claim_recorded": True,
                "execution_authority": self.EXECUTION_AUTHORITY,
                "runtime_invoked": False,
                "phone_changed": False,
            }
            claim = {**claim_payload, "claim_digest": _digest(claim_payload)}
            root = self._root(gateway.project_id)
            ensure_private_directory(root, boundary=self.store.workspace)
            exclusive_create_json(
                self._claim_path(gateway.project_id, challenge.challenge_id),
                {"format": self.CLAIM_FORMAT, **claim},
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            atomic_write_json(
                root / self.SESSION_NAME,
                envelope,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            return verified
        except LocalStoreConflictError as exc:
            raise RuntimeSessionValidationError(
                "This runtime challenge already has an accepted response"
            ) from exc
        except RuntimeSessionValidationError:
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
            raise RuntimeSessionValidationError(
                "Runtime session failed closed without opening device access"
            ) from exc

    def load_challenge(
        self,
        gateway: GuardianExecutionGatewayContract,
        live_target: GuardianLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        runtime_trust: GuardianRuntimeTrust,
        runtime_public_key: Ed25519PublicKey,
        *,
        now: datetime | None = None,
    ) -> GuardianRuntimeHandshakeChallenge | None:
        try:
            data = _read_exact_json(
                self._root(gateway.project_id) / self.CHALLENGE_NAME,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            expected = {
                "format",
                *(field.name for field in fields(GuardianRuntimeHandshakeChallenge)),
            }
            if set(data) != expected or data.pop("format") != self.CHALLENGE_FORMAT:
                return None
            challenge = GuardianRuntimeHandshakeChallenge(**data)
            self.validate_challenge(
                challenge,
                gateway,
                live_target,
                reviewed_device,
                runtime_trust,
                runtime_public_key,
                now=now or self._now(),
            )
            return challenge
        except (
            RuntimeSessionValidationError,
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

    def load(
        self,
        gateway: GuardianExecutionGatewayContract,
        live_target: GuardianLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        runtime_trust: GuardianRuntimeTrust,
        runtime_public_key: Ed25519PublicKey,
        *,
        now: datetime | None = None,
    ) -> VerifiedGuardianRuntimeSession | None:
        try:
            checked_at = now or self._now()
            challenge = self.load_challenge(
                gateway,
                live_target,
                reviewed_device,
                runtime_trust,
                runtime_public_key,
                now=checked_at,
            )
            if challenge is None:
                return None
            envelope = _read_exact_json(
                self._root(gateway.project_id) / self.SESSION_NAME,
                boundary=self.store.workspace,
                maximum_bytes=self.MAX_BYTES,
            )
            verified = self._verify_envelope(
                envelope,
                challenge,
                gateway,
                runtime_trust,
                runtime_public_key,
                now=checked_at,
            )
            self._validate_claim(verified, challenge, gateway.project_id, now=checked_at)
            return verified
        except (
            RuntimeSessionValidationError,
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

    def validate_session(
        self,
        session: VerifiedGuardianRuntimeSession,
        gateway: GuardianExecutionGatewayContract,
        live_target: GuardianLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        runtime_trust: GuardianRuntimeTrust,
        runtime_public_key: Ed25519PublicKey,
        *,
        now: datetime | None = None,
    ) -> None:
        current = self.load(
            gateway,
            live_target,
            reviewed_device,
            runtime_trust,
            runtime_public_key,
            now=now,
        )
        if not isinstance(session, VerifiedGuardianRuntimeSession) or current != session:
            raise RuntimeSessionValidationError("Runtime session is no longer current and exact")

    def validate_challenge(
        self,
        challenge: GuardianRuntimeHandshakeChallenge,
        gateway: GuardianExecutionGatewayContract,
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
            live_target,
            reviewed_device,
            runtime_trust,
            runtime_public_key,
            now=checked_at,
        )
        payload = asdict(challenge)
        challenge_digest = str(payload.pop("challenge_digest", ""))
        issued = _timestamp(challenge.issued_at, "runtime challenge issue")
        expires = _timestamp(challenge.expires_at, "runtime challenge expiry")
        live_expires = _timestamp(live_target.expires_at, "live-target expiry")
        if (
            type(challenge.schema_version) is not int
            or challenge.schema_version != self.SCHEMA_VERSION
            or not _hex(challenge.challenge_id, 32)
            or issued > checked_at
            or checked_at > expires
            or issued >= expires
            or (expires - issued).total_seconds() > self.VALIDITY_SECONDS
            or expires > live_expires
            or challenge.project_id != gateway.project_id
            or challenge.gateway_contract_digest != gateway.contract_digest
            or challenge.live_target_receipt_digest != live_target.receipt_digest
            or challenge.device_key != gateway.device_key
            or challenge.runtime_trust_digest != _digest(asdict(runtime_trust))
            or challenge.runtime_signer_key_id != runtime_trust.key_id
            or challenge.runtime_public_key_sha256 != runtime_trust.public_key_sha256
            or challenge.runtime_adapter_id != runtime_trust.adapter_id
            or type(challenge.runtime_adapter_version) is not int
            or challenge.runtime_adapter_version != runtime_trust.adapter_version
            or challenge.runtime_adapter_sha256 != runtime_trust.adapter_sha256
            or type(challenge.result_receipt_schema_version) is not int
            or challenge.result_receipt_schema_version != gateway.result_receipt_schema_version
            or type(challenge.runtime_protocol_version) is not int
            or challenge.runtime_protocol_version != self.PROTOCOL_VERSION
            or challenge.execution_authority != self.EXECUTION_AUTHORITY
            or challenge.runtime_invoked is not False
            or challenge.phone_changed is not False
            or not _hex(challenge_digest, 64)
            or challenge_digest != _digest(payload)
        ):
            raise RuntimeSessionValidationError(
                "Runtime challenge failed exact integrity or safety validation"
            )

    def _verify_envelope(
        self,
        envelope: dict[str, Any],
        challenge: GuardianRuntimeHandshakeChallenge,
        gateway: GuardianExecutionGatewayContract,
        runtime_trust: GuardianRuntimeTrust,
        runtime_public_key: Ed25519PublicKey,
        *,
        now: datetime,
    ) -> VerifiedGuardianRuntimeSession:
        if not isinstance(envelope, dict) or set(envelope) != self.ENVELOPE_FIELDS:
            raise RuntimeSessionValidationError("Runtime session envelope fields do not match")
        if (
            envelope["format"] != self.SESSION_FORMAT
            or type(envelope["schema_version"]) is not int
            or envelope["schema_version"] != self.SCHEMA_VERSION
            or envelope["algorithm"] != self.ALGORITHM
            or envelope["key_id"] != runtime_trust.key_id
        ):
            raise RuntimeSessionValidationError("Runtime session signer or schema is not trusted")
        raw = envelope["attestation"]
        if not isinstance(raw, dict) or set(raw) != self.ATTESTATION_FIELDS:
            raise RuntimeSessionValidationError("Runtime session attestation fields do not match")
        encoded = _canonical_bytes(raw)
        if len(encoded) > self.MAX_BYTES:
            raise RuntimeSessionValidationError("Runtime session attestation exceeds its boundary")
        signed_digest = hashlib.sha256(encoded).hexdigest()
        if envelope["attestation_sha256"] != signed_digest:
            raise RuntimeSessionValidationError("Runtime session signed digest does not match")
        try:
            runtime_public_key.verify(
                _signature(envelope["signature"]),
                self.DOMAIN + encoded,
            )
        except InvalidSignature as exc:
            raise RuntimeSessionValidationError(
                "Runtime session signature verification failed"
            ) from exc
        attestation = GuardianRuntimeSessionAttestation(**raw)
        self._validate_attestation(
            attestation,
            challenge,
            gateway,
            runtime_trust,
            now=now,
        )
        return VerifiedGuardianRuntimeSession(
            attestation=attestation,
            signer_key_id=runtime_trust.key_id,
            signed_envelope_sha256=_digest(envelope),
            challenge_claimed_once=True,
        )

    def _validate_attestation(
        self,
        attestation: GuardianRuntimeSessionAttestation,
        challenge: GuardianRuntimeHandshakeChallenge,
        gateway: GuardianExecutionGatewayContract,
        runtime_trust: GuardianRuntimeTrust,
        *,
        now: datetime,
    ) -> None:
        payload = asdict(attestation)
        digest = str(payload.pop("attestation_digest", ""))
        responded = _timestamp(attestation.responded_at, "runtime response")
        expires = _timestamp(attestation.expires_at, "runtime session expiry")
        issued = _timestamp(challenge.issued_at, "runtime challenge issue")
        if (
            type(attestation.schema_version) is not int
            or attestation.schema_version != self.SCHEMA_VERSION
            or not _hex(attestation.session_id, 32)
            or not issued <= responded <= now <= expires
            or expires != _timestamp(challenge.expires_at, "runtime challenge expiry")
            or attestation.challenge_id != challenge.challenge_id
            or attestation.challenge_digest != challenge.challenge_digest
            or attestation.project_id != gateway.project_id
            or attestation.gateway_contract_digest != gateway.contract_digest
            or attestation.live_target_receipt_digest != challenge.live_target_receipt_digest
            or attestation.device_key != gateway.device_key
            or attestation.runtime_trust_digest != _digest(asdict(runtime_trust))
            or attestation.runtime_signer_key_id != runtime_trust.key_id
            or attestation.runtime_public_key_sha256 != runtime_trust.public_key_sha256
            or attestation.runtime_adapter_id != runtime_trust.adapter_id
            or type(attestation.runtime_adapter_version) is not int
            or attestation.runtime_adapter_version != runtime_trust.adapter_version
            or attestation.runtime_adapter_sha256 != runtime_trust.adapter_sha256
            or attestation.runtime_platform not in {"linux", "windows", "macos"}
            or not _identifier(attestation.runtime_architecture)
            or type(attestation.runtime_protocol_version) is not int
            or attestation.runtime_protocol_version != self.PROTOCOL_VERSION
            or type(attestation.result_receipt_schema_version) is not int
            or attestation.result_receipt_schema_version != gateway.result_receipt_schema_version
            or not _hex(attestation.runtime_instance_nonce_sha256, 64)
            or attestation.accepts_exact_gateway is not True
            or attestation.accepts_forward_scope_only is not True
            or attestation.automatic_recovery_enabled is not False
            or attestation.automatic_wipe_enabled is not False
            or attestation.bootloader_relock_enabled is not False
            or attestation.execution_authority != self.EXECUTION_AUTHORITY
            or attestation.device_access_opened is not False
            or attestation.phone_changed is not False
            or not _hex(digest, 64)
            or digest != _digest(payload)
        ):
            raise RuntimeSessionValidationError(
                "Runtime session attestation failed exact integrity or safety validation"
            )

    def _validate_claim(
        self,
        verified: VerifiedGuardianRuntimeSession,
        challenge: GuardianRuntimeHandshakeChallenge,
        project_id: str,
        *,
        now: datetime,
    ) -> None:
        data = _read_exact_json(
            self._claim_path(project_id, challenge.challenge_id),
            boundary=self.store.workspace,
            maximum_bytes=self.MAX_BYTES,
        )
        expected = {
            "format",
            "schema_version",
            "challenge_id",
            "challenge_digest",
            "session_id",
            "attestation_digest",
            "signed_envelope_sha256",
            "claimed_at",
            "exclusive_claim_recorded",
            "execution_authority",
            "runtime_invoked",
            "phone_changed",
            "claim_digest",
        }
        if set(data) != expected or data.pop("format") != self.CLAIM_FORMAT:
            raise RuntimeSessionValidationError("Runtime handshake claim fields do not match")
        claim_digest = data.pop("claim_digest")
        claimed_at = _timestamp(data["claimed_at"], "runtime claim")
        attestation = verified.attestation
        if (
            data["schema_version"] != self.SCHEMA_VERSION
            or type(data["schema_version"]) is not int
            or data["challenge_id"] != challenge.challenge_id
            or data["challenge_digest"] != challenge.challenge_digest
            or data["session_id"] != attestation.session_id
            or data["attestation_digest"] != attestation.attestation_digest
            or data["signed_envelope_sha256"] != verified.signed_envelope_sha256
            or not _timestamp(attestation.responded_at, "runtime response") <= claimed_at <= now
            or data["exclusive_claim_recorded"] is not True
            or data["execution_authority"] != self.EXECUTION_AUTHORITY
            or data["runtime_invoked"] is not False
            or data["phone_changed"] is not False
            or not _hex(claim_digest, 64)
            or claim_digest != _digest(data)
        ):
            raise RuntimeSessionValidationError(
                "Runtime handshake claim failed exact integrity or safety validation"
            )

    def _validate_context(
        self,
        gateway: GuardianExecutionGatewayContract,
        live_target: GuardianLiveTargetReceipt,
        reviewed_device: AndroidDevice,
        runtime_trust: GuardianRuntimeTrust,
        runtime_public_key: Ed25519PublicKey,
        *,
        now: datetime,
    ) -> None:
        GuardianExecutionGatewayContractService.validate(gateway)
        current = self.live_targets.load(gateway, reviewed_device, now=now)
        if current is None or current != live_target:
            raise RuntimeSessionValidationError(
                "Runtime handshake requires the current exact live-target receipt"
            )
        validate_guardian_runtime_trust(runtime_trust, runtime_public_key, gateway)
        if (
            gateway.execution_authority != "none"
            or gateway.runtime_invoked
            or gateway.phone_changed
        ):
            raise RuntimeSessionValidationError(
                "Runtime handshake requires an inert exact Guardian gateway"
            )

    def _root(self, project_id: str) -> Path:
        self.store.get(project_id)
        return self.store.projects_root / project_id / "guardian"

    def _claim_path(self, project_id: str, challenge_id: str) -> Path:
        if not _hex(challenge_id, 32):
            raise RuntimeSessionValidationError("Runtime challenge identity is invalid")
        return self._root(project_id) / f"runtime-handshake-claim-{challenge_id}.romverse"

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeSessionValidationError("Runtime-session clock must be timezone-aware")
        return value.astimezone(UTC)


def _read_exact_json(path: Path, *, boundary: Path, maximum_bytes: int) -> dict[str, Any]:
    encoded = read_regular_bytes(path, boundary=boundary, maximum_bytes=maximum_bytes)
    try:
        value = json.loads(encoded, object_pairs_hook=_strict_object)
    except RuntimeSessionValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeSessionValidationError("Runtime-session evidence is not valid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeSessionValidationError("Runtime-session evidence must be one object")
    return value


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeSessionValidationError(f"Duplicate runtime-session field: {key}")
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
        raise RuntimeSessionValidationError(
            "Runtime-session evidence cannot be represented canonically"
        ) from exc


def _digest(payload: object) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _signature(value: object) -> bytes:
    if not isinstance(value, str) or len(value) > 128:
        raise RuntimeSessionValidationError("Runtime session signature is malformed")
    try:
        signature = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RuntimeSessionValidationError("Runtime session signature is malformed") from exc
    if len(signature) != 64:
        raise RuntimeSessionValidationError("Runtime session signature has invalid length")
    return signature


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not 20 <= len(value) <= 40:
        raise RuntimeSessionValidationError(f"{label.capitalize()} timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeSessionValidationError(f"{label.capitalize()} timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeSessionValidationError(f"{label.capitalize()} timestamp requires a zone")
    return parsed.astimezone(UTC)


def _identifier(value: object) -> bool:
    return bool(isinstance(value, str) and re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,95}", value))


def _hex(value: object, length: int) -> bool:
    return bool(isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value))
