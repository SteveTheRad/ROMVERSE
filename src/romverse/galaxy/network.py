"""Authenticated, signed and bounded transport for optional Galaxy intelligence sharing."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import ipaddress
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from romverse import __version__
from romverse.galaxy.intelligence import (
    GalaxyContribution,
    GalaxyEvidenceClass,
    GalaxyIntelligenceError,
    GalaxyIntelligenceService,
    GalaxyModerationKey,
)
from romverse.infrastructure.local_store import (
    LocalStoreConflictError,
    LocalStoreError,
    atomic_write_bytes,
    ensure_private_directory,
    exclusive_create_json,
    read_json_object,
    read_regular_bytes,
)
from romverse.knowledge.updates import (
    KnowledgePublisherKey,
    KnowledgeUpdatePreview,
    KnowledgeUpdateService,
)
from romverse.members.client import MemberSession


class GalaxyNetworkError(RuntimeError):
    """An optional Galaxy network operation failed its privacy or trust contract."""


@dataclass(frozen=True, slots=True)
class GalaxyReceiptKey:
    key_id: str
    public_key_base64: str
    revoked: bool = False

    def public_key(self) -> Ed25519PublicKey:
        if self.revoked:
            raise GalaxyNetworkError("Galaxy receipt key is revoked")
        try:
            raw = base64.b64decode(self.public_key_base64, validate=True)
            if len(raw) != 32:
                raise ValueError("wrong key length")
            return Ed25519PublicKey.from_public_bytes(raw)
        except (ValueError, binascii.Error) as exc:
            raise GalaxyNetworkError("Galaxy receipt public key is invalid") from exc


@dataclass(frozen=True, slots=True)
class GalaxyServiceTrust:
    configured: bool
    reason: str
    service_url: str
    members_issuer: str
    receipt_keys: tuple[GalaxyReceiptKey, ...]
    moderation_keys: tuple[GalaxyModerationKey, ...]
    knowledge_keys: tuple[KnowledgePublisherKey, ...]


@dataclass(frozen=True, slots=True)
class GalaxyHttpResponse:
    status: int
    final_url: str
    body: bytes
    content_type: str = "application/json"


class GalaxyHttpTransport(Protocol):
    def request(
        self,
        url: str,
        *,
        method: str,
        body: bytes | None,
        headers: dict[str, str],
        maximum_bytes: int,
    ) -> GalaxyHttpResponse: ...


class UrllibGalaxyTransport:
    """Strict HTTPS JSON transport that never logs or persists bearer credentials."""

    def request(
        self,
        url: str,
        *,
        method: str,
        body: bytes | None,
        headers: dict[str, str],
        maximum_bytes: int,
    ) -> GalaxyHttpResponse:
        trusted_url = _public_https_url(url, "Galaxy endpoint")
        request = urllib.request.Request(
            trusted_url,
            data=body,
            headers={"User-Agent": f"ROMVERSE/{__version__} Galaxy", **headers},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
                final_url = _public_https_url(response.geturl(), "Galaxy response")
                if final_url != trusted_url:
                    raise GalaxyNetworkError("Galaxy service redirected unexpectedly")
                length = response.headers.get("Content-Length")
                if length and int(length) > maximum_bytes:
                    raise GalaxyNetworkError("Galaxy response exceeds its size boundary")
                payload = response.read(maximum_bytes + 1)
                status = int(getattr(response, "status", 200))
                content_type = str(response.headers.get("Content-Type", ""))[:160]
        except GalaxyNetworkError:
            raise
        except urllib.error.HTTPError as exc:
            raise GalaxyNetworkError(
                f"Galaxy service rejected the request with HTTP {exc.code}"
            ) from exc
        except (OSError, TimeoutError, ValueError, urllib.error.URLError) as exc:
            raise GalaxyNetworkError("Galaxy service could not be reached securely") from exc
        if not 0 < len(payload) <= maximum_bytes:
            raise GalaxyNetworkError("Galaxy response exceeds its size boundary")
        if status < 200 or status >= 300:
            raise GalaxyNetworkError(f"Galaxy service returned HTTP {status}")
        return GalaxyHttpResponse(status, final_url, payload, content_type)


@dataclass(frozen=True, slots=True)
class GalaxySubmissionPreview:
    contribution_id: str
    contribution_digest: str
    endpoint: str
    payload_json: str
    payload_sha256: str
    excluded_private_fields: tuple[str, ...]
    requires_member_session: bool = True
    requires_explicit_confirmation: bool = True
    network_authority: str = "single-reviewed-submission"
    execution_authority: str = "none"
    phone_changed: bool = False


@dataclass(frozen=True, slots=True)
class GalaxySubmissionReceipt:
    receipt_id: str
    contribution_id: str
    contribution_digest: str
    received_at: str
    state: str
    signer_id: str
    request_sha256: str
    response_sha256: str
    receipt_path: Path
    execution_authority: str = "none"
    phone_changed: bool = False


class GalaxyNetworkService:
    """Optional authenticated Galaxy client with signed server receipts.

    Network access exists only when immutable packaged trust is configured, the
    matching Members issuer created an active in-memory session, sharing is opted
    in, and the user accepts the exact privacy-reviewed payload digest.
    """

    SUBMISSION_FORMAT = "romverse.galaxy.reviewed-submission"
    RECEIPT_FORMAT = "romverse.galaxy.submission-receipt"
    SCHEMA_VERSION = 1
    RECEIPT_DOMAIN = b"ROMVERSE-GALAXY-SUBMISSION-RECEIPT-V1\x00"
    MAX_SUBMISSION_BYTES = 2 * 1024 * 1024
    MAX_RECEIPT_BYTES = 256 * 1024
    MAX_TRUST_BYTES = 256 * 1024
    _RECEIPT_FIELDS = {
        "format",
        "schema_version",
        "receipt_id",
        "contribution_id",
        "contribution_digest",
        "received_at",
        "state",
        "signer_id",
        "signature_algorithm",
        "signature",
    }

    def __init__(
        self,
        workspace: Path,
        intelligence: GalaxyIntelligenceService,
        trust: GalaxyServiceTrust,
        *,
        member_issuer: str = "",
        update_service: KnowledgeUpdateService | None = None,
        transport: GalaxyHttpTransport | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.intelligence = intelligence
        self.trust = trust
        self.member_issuer = member_issuer.strip().rstrip("/")
        self.update_service = update_service
        self.transport = transport or UrllibGalaxyTransport()
        self.clock = clock
        self.receipt_root = self.workspace / "galaxy" / "submission-receipts"
        self.download_root = self.workspace / "galaxy" / "signed-updates"
        self._receipt_keys = {_identifier(item.key_id): item for item in trust.receipt_keys}
        if len(self._receipt_keys) != len(trust.receipt_keys):
            raise GalaxyNetworkError("Galaxy receipt key identities are duplicated")
        for item in trust.receipt_keys:
            item.public_key()
        self._validate_trust()

    @property
    def configured(self) -> bool:
        return bool(
            self.trust.configured
            and self.member_issuer
            and self.member_issuer == self.trust.members_issuer.rstrip("/")
            and any(not item.revoked for item in self._receipt_keys.values())
        )

    @property
    def status_reason(self) -> str:
        if not self.trust.configured:
            return self.trust.reason
        if not self.member_issuer:
            return "Configure the official ROMVERSE Members issuer before Galaxy networking."
        if self.member_issuer != self.trust.members_issuer.rstrip("/"):
            return "The configured Members issuer does not match packaged Galaxy trust."
        if not any(not item.revoked for item in self._receipt_keys.values()):
            return "No active Galaxy server receipt key is trusted."
        return "Ready for an explicit authenticated Galaxy request."

    def set_member_issuer(self, value: str) -> None:
        self.member_issuer = value.strip().rstrip("/")

    def preview_submission(self, contribution: GalaxyContribution) -> GalaxySubmissionPreview:
        self._require_configured()
        if not self.intelligence.sharing_enabled:
            raise GalaxyNetworkError("Galaxy contribution sharing is opted out")
        current = self._current_contribution(contribution)
        if current.evidence_class in {
            GalaxyEvidenceClass.REJECTED,
            GalaxyEvidenceClass.OFFICIAL,
        }:
            raise GalaxyNetworkError("This contribution is not eligible for community review")
        if not current.queued_for_review:
            raise GalaxyNetworkError("This contribution is not in the local review queue")
        if self.receipt_for(current) is not None:
            raise GalaxyNetworkError("This contribution already has a verified Galaxy receipt")
        encoded = self._submission_bytes(current)
        if len(encoded) > self.MAX_SUBMISSION_BYTES:
            raise GalaxyNetworkError("Galaxy submission exceeds its size boundary")
        if current.device_pattern.pattern_digest not in encoded.decode("utf-8"):
            raise GalaxyNetworkError("Galaxy submission lost its reviewed Device DNA binding")
        return GalaxySubmissionPreview(
            current.contribution_id,
            self.intelligence.contribution_digest(current),
            self._endpoint("contributions"),
            encoded.decode("utf-8"),
            hashlib.sha256(encoded).hexdigest(),
            self.intelligence.EXCLUDED_PRIVATE_FIELDS,
        )

    def submit(
        self,
        preview: GalaxySubmissionPreview,
        accepted_payload_sha256: str,
        session: MemberSession,
    ) -> GalaxySubmissionReceipt:
        self._require_configured()
        if not isinstance(preview, GalaxySubmissionPreview):
            raise GalaxyNetworkError("Galaxy submission preview is invalid")
        if not hmac.compare_digest(preview.payload_sha256, accepted_payload_sha256):
            raise GalaxyNetworkError("The exact Galaxy network preview was not accepted")
        current = next(
            (
                item
                for item in self.intelligence.load()
                if item.contribution_id == preview.contribution_id
            ),
            None,
        )
        if current is None:
            raise GalaxyNetworkError("Galaxy contribution is no longer available")
        fresh = self.preview_submission(current)
        if fresh != preview:
            raise GalaxyNetworkError(
                "Galaxy contribution or network destination changed after preview"
            )
        token = self._active_token(session)
        response = self.transport.request(
            preview.endpoint,
            method="POST",
            body=preview.payload_json.encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Idempotency-Key": preview.contribution_digest,
            },
            maximum_bytes=self.MAX_RECEIPT_BYTES,
        )
        if response.final_url != preview.endpoint:
            raise GalaxyNetworkError("Galaxy submission response came from the wrong endpoint")
        receipt = self._verified_receipt(response.body, preview)
        saved = self._save_receipt(receipt, preview.payload_sha256, response.body)
        return saved

    def download_signed_update(
        self,
        session: MemberSession,
        *,
        channel: str = "stable",
    ) -> KnowledgeUpdatePreview:
        self._require_configured()
        if channel not in {"stable", "preview"}:
            raise GalaxyNetworkError("Galaxy knowledge update channel is unsupported")
        service = self.update_service
        if service is None or not service.configured:
            raise GalaxyNetworkError(
                "No production Synapse publisher key is enrolled for downloaded updates"
            )
        token = self._active_token(session)
        endpoint = self._endpoint(f"knowledge/{channel}/latest")
        response = self.transport.request(
            endpoint,
            method="GET",
            body=None,
            headers={
                "Accept": "application/vnd.romverse.knowledge-update+json",
                "Authorization": f"Bearer {token}",
            },
            maximum_bytes=service.MAX_ENVELOPE_BYTES,
        )
        if response.final_url != endpoint:
            raise GalaxyNetworkError("Galaxy update response came from the wrong endpoint")
        digest = hashlib.sha256(response.body).hexdigest()
        target = self.download_root / f"{digest}.romverse"
        try:
            ensure_private_directory(self.download_root, boundary=self.workspace)
            if target.exists() or target.is_symlink():
                existing = read_regular_bytes(
                    target,
                    boundary=self.workspace,
                    maximum_bytes=service.MAX_ENVELOPE_BYTES,
                )
                if not hmac.compare_digest(
                    hashlib.sha256(existing).hexdigest(),
                    digest,
                ):
                    raise GalaxyNetworkError("Staged Galaxy update content conflicts by digest")
            else:
                atomic_write_bytes(
                    target,
                    response.body,
                    boundary=self.workspace,
                    maximum_bytes=service.MAX_ENVELOPE_BYTES,
                )
            return service.inspect(target)
        except GalaxyNetworkError:
            raise
        except (LocalStoreError, OSError, ValueError) as exc:
            raise GalaxyNetworkError(f"Downloaded Galaxy update was rejected: {exc}") from exc

    def receipt_for(
        self,
        contribution: GalaxyContribution,
    ) -> GalaxySubmissionReceipt | None:
        if not isinstance(contribution, GalaxyContribution):
            raise GalaxyNetworkError("Galaxy contribution is invalid")
        current = self._current_contribution_id(contribution.contribution_id)
        if self.intelligence.contribution_digest(current) != (
            self.intelligence.contribution_digest(contribution)
        ):
            raise GalaxyNetworkError("Galaxy contribution changed before receipt verification")
        target = self.receipt_root / f"{current.contribution_id}.json"
        if not target.exists() and not target.is_symlink():
            return None
        try:
            payload = read_json_object(
                target,
                boundary=self.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
            expected = {
                "format",
                "schema_version",
                "receipt",
                "request_sha256",
                "response_sha256",
                "local_digest",
                "execution_authority",
                "phone_changed",
            }
            if (
                set(payload) != expected
                or payload["format"] != "romverse.galaxy.local-submission-receipt"
                or payload["schema_version"] != self.SCHEMA_VERSION
            ):
                raise ValueError("local Galaxy receipt fields are invalid")
            unsigned = dict(payload)
            digest = unsigned.pop("local_digest")
            if not _sha256(digest) or not hmac.compare_digest(str(digest), _digest(unsigned)):
                raise ValueError("local Galaxy receipt digest does not match")
            raw_receipt = payload["receipt"]
            if not isinstance(raw_receipt, dict):
                raise ValueError("signed Galaxy receipt is invalid")
            receipt = self._verify_receipt_document(raw_receipt)
            request_digest = str(payload["request_sha256"])
            response_digest = str(payload["response_sha256"])
            if (
                receipt.contribution_id != current.contribution_id
                or receipt.contribution_digest != self.intelligence.contribution_digest(current)
                or not _sha256(request_digest)
                or not hmac.compare_digest(
                    request_digest,
                    hashlib.sha256(self._submission_bytes(current)).hexdigest(),
                )
                or not _sha256(response_digest)
                or not hmac.compare_digest(
                    response_digest,
                    hashlib.sha256(_canonical(raw_receipt)).hexdigest(),
                )
                or payload["execution_authority"] != "none"
                or payload["phone_changed"] is not False
            ):
                raise ValueError("local Galaxy receipt contribution binding is invalid")
            return GalaxySubmissionReceipt(
                receipt.receipt_id,
                receipt.contribution_id,
                receipt.contribution_digest,
                receipt.received_at,
                receipt.state,
                receipt.signer_id,
                request_digest,
                response_digest,
                target,
            )
        except (LocalStoreError, OSError, TypeError, ValueError) as exc:
            raise GalaxyNetworkError(f"Galaxy submission receipt is unreadable: {exc}") from exc

    def _verified_receipt(
        self,
        payload: bytes,
        preview: GalaxySubmissionPreview,
    ) -> GalaxySubmissionReceipt:
        try:
            raw = json.loads(payload.decode("utf-8"), object_pairs_hook=_strict_object)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GalaxyNetworkError("Galaxy submission receipt is not valid JSON") from exc
        if not isinstance(raw, dict) or set(raw) != self._RECEIPT_FIELDS:
            raise GalaxyNetworkError("Galaxy submission receipt fields do not match schema 1")
        receipt = self._verify_receipt_document(raw, require_fresh=True)
        if (
            receipt.contribution_id != preview.contribution_id
            or receipt.contribution_digest != preview.contribution_digest
        ):
            raise GalaxyNetworkError("Galaxy receipt does not match the reviewed contribution")
        return receipt

    def _verify_receipt_document(
        self,
        raw: dict[str, object],
        *,
        require_fresh: bool = False,
    ) -> GalaxySubmissionReceipt:
        receipt = self._receipt_values(raw)
        if require_fresh:
            received = _timestamp(receipt.received_at)
            current_time = datetime.fromtimestamp(float(self.clock()), UTC)
            if received < current_time - timedelta(minutes=10):
                raise GalaxyNetworkError("Galaxy submission receipt is not fresh")
        signer = self._receipt_keys.get(receipt.signer_id)
        if signer is None:
            raise GalaxyNetworkError("Galaxy receipt signer is not trusted")
        signature_text = raw["signature"]
        try:
            signature = base64.b64decode(str(signature_text), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise GalaxyNetworkError("Galaxy receipt signature is malformed") from exc
        unsigned = dict(raw)
        unsigned.pop("signature")
        try:
            signer.public_key().verify(signature, self.RECEIPT_DOMAIN + _canonical(unsigned))
        except InvalidSignature as exc:
            raise GalaxyNetworkError("Galaxy receipt signature verification failed") from exc
        return receipt

    def _receipt_values(self, raw: dict[str, object]) -> GalaxySubmissionReceipt:
        if (
            set(raw) != self._RECEIPT_FIELDS
            or raw["format"] != self.RECEIPT_FORMAT
            or raw["schema_version"] != self.SCHEMA_VERSION
            or raw["signature_algorithm"] != "ed25519"
        ):
            raise GalaxyNetworkError("Galaxy submission receipt format is invalid")
        receipt_id = _identifier(raw["receipt_id"])
        contribution_id = str(raw["contribution_id"])
        contribution_digest = str(raw["contribution_digest"])
        signer_id = _identifier(raw["signer_id"])
        state = str(raw["state"])
        received = _timestamp(raw["received_at"])
        current_time = datetime.fromtimestamp(float(self.clock()), UTC)
        if (
            not re.fullmatch(r"[0-9a-f]{32}", contribution_id)
            or not _sha256(contribution_digest)
            or state not in {"pending-review", "duplicate"}
            or received > current_time + timedelta(minutes=5)
        ):
            raise GalaxyNetworkError("Galaxy submission receipt values are invalid")
        return GalaxySubmissionReceipt(
            receipt_id,
            contribution_id,
            contribution_digest,
            received.isoformat(),
            state,
            signer_id,
            "",
            "",
            Path(),
        )

    def _save_receipt(
        self,
        receipt: GalaxySubmissionReceipt,
        request_sha256: str,
        response: bytes,
    ) -> GalaxySubmissionReceipt:
        try:
            signed_receipt = json.loads(response.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GalaxyNetworkError("Verified Galaxy receipt could not be preserved") from exc
        payload: dict[str, object] = {
            "format": "romverse.galaxy.local-submission-receipt",
            "schema_version": 1,
            "receipt": signed_receipt,
            "request_sha256": request_sha256,
            "response_sha256": hashlib.sha256(_canonical(signed_receipt)).hexdigest(),
            "execution_authority": "none",
            "phone_changed": False,
        }
        payload["local_digest"] = _digest(payload)
        target = self.receipt_root / f"{receipt.contribution_id}.json"
        try:
            ensure_private_directory(self.receipt_root, boundary=self.workspace)
            exclusive_create_json(
                target,
                payload,
                boundary=self.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
        except LocalStoreConflictError:
            existing = self.receipt_for(self._current_contribution_id(receipt.contribution_id))
            if (
                existing is None
                or existing.receipt_id != receipt.receipt_id
                or existing.response_sha256 != payload["response_sha256"]
            ):
                raise GalaxyNetworkError("A different Galaxy receipt already exists") from None
            return existing
        except (LocalStoreError, OSError) as exc:
            raise GalaxyNetworkError("Galaxy receipt could not be saved privately") from exc
        stored = self.receipt_for(self._current_contribution_id(receipt.contribution_id))
        if stored is None:
            raise GalaxyNetworkError("Galaxy receipt failed post-write verification")
        return stored

    def _current_contribution(self, contribution: GalaxyContribution) -> GalaxyContribution:
        if not isinstance(contribution, GalaxyContribution):
            raise GalaxyNetworkError("Galaxy contribution is invalid")
        current = self._current_contribution_id(contribution.contribution_id)
        if current.record_digest != contribution.record_digest:
            raise GalaxyNetworkError("Galaxy contribution changed before network review")
        return current

    def _submission_bytes(self, contribution: GalaxyContribution) -> bytes:
        document: dict[str, object] = {
            "format": self.SUBMISSION_FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "privacy": "serial-imei-account-free",
            "submission": {
                "schema_version": contribution.schema_version,
                "contribution_id": contribution.contribution_id,
                "created_at": contribution.created_at,
                "kind": contribution.kind.value,
                "outcome": contribution.outcome.value,
                "title": contribution.title,
                "summary": contribution.summary,
                "symptoms": contribution.symptoms,
                "solution_steps": contribution.solution_steps,
                "evidence_refs": contribution.evidence_refs,
                "contributor_key": contribution.contributor_key,
                "device_pattern": asdict(contribution.device_pattern),
                "conflict_ids": contribution.conflict_ids,
                "submitted_evidence_class": (
                    GalaxyEvidenceClass.DISPUTED.value
                    if contribution.conflict_ids
                    else GalaxyEvidenceClass.EXPERIMENTAL.value
                ),
            },
            "contribution_digest": self.intelligence.contribution_digest(contribution),
            "upload_authority": "single-reviewed-submission",
            "execution_authority": "none",
            "phone_changed": False,
        }
        return _canonical(document)

    def _current_contribution_id(self, contribution_id: str) -> GalaxyContribution:
        try:
            current = next(
                item for item in self.intelligence.load() if item.contribution_id == contribution_id
            )
        except (StopIteration, GalaxyIntelligenceError) as exc:
            raise GalaxyNetworkError("Galaxy contribution is no longer available") from exc
        return current

    def _active_token(self, session: MemberSession) -> str:
        if (
            not isinstance(session, MemberSession)
            or session.token_type.casefold() != "bearer"
            or not session.profile.access_active
            or session.expires_at_epoch <= int(self.clock())
            or not 16 <= len(session.access_token) <= 16_384
        ):
            raise GalaxyNetworkError("An active ROMVERSE Members session is required")
        return session.access_token

    def _endpoint(self, suffix: str) -> str:
        base = self.trust.service_url.rstrip("/")
        endpoint = _public_https_url(f"{base}/{suffix}", "Galaxy endpoint")
        if not endpoint.startswith(base + "/"):
            raise GalaxyNetworkError("Galaxy endpoint escaped its packaged service root")
        return endpoint

    def _require_configured(self) -> None:
        if not self.configured:
            raise GalaxyNetworkError(self.status_reason)

    def _validate_trust(self) -> None:
        reason = self.trust.reason.strip()
        if not 1 <= len(reason) <= 500:
            raise GalaxyNetworkError("Galaxy service trust reason is invalid")
        if self.trust.configured:
            service = _public_https_url(self.trust.service_url, "Galaxy service URL").rstrip("/")
            issuer = _public_https_url(self.trust.members_issuer, "Galaxy Members issuer").rstrip(
                "/"
            )
            if service != self.trust.service_url.rstrip("/") or issuer != (
                self.trust.members_issuer.rstrip("/")
            ):
                raise GalaxyNetworkError("Galaxy service trust URLs are not canonical")
            key_groups = (
                ("receipt", self.trust.receipt_keys),
                ("moderation", self.trust.moderation_keys),
                ("knowledge", self.trust.knowledge_keys),
            )
            for label, keys in key_groups:
                identities = tuple(_identifier(item.key_id) for item in keys)
                if len(identities) != len(set(identities)):
                    raise GalaxyNetworkError(f"Galaxy {label} trust keys are duplicated")
                active = tuple(item for item in keys if not item.revoked)
                if not active:
                    raise GalaxyNetworkError(
                        f"Configured Galaxy service has no active {label} trust key"
                    )
                for item in active:
                    item.public_key()
        elif any(
            (
                self.trust.service_url,
                self.trust.members_issuer,
                self.trust.receipt_keys,
                self.trust.moderation_keys,
                self.trust.knowledge_keys,
            )
        ):
            raise GalaxyNetworkError("Unconfigured Galaxy trust cannot carry partial authority")


def load_galaxy_service_trust(path: Path) -> GalaxyServiceTrust:
    try:
        if path.is_symlink():
            raise GalaxyNetworkError("Galaxy service trust cannot be a symbolic link")
        payload = read_regular_bytes(
            path,
            boundary=path.parent.resolve(strict=True),
            maximum_bytes=GalaxyNetworkService.MAX_TRUST_BYTES,
        )
        raw = json.loads(payload.decode("utf-8"), object_pairs_hook=_strict_object)
    except GalaxyNetworkError:
        raise
    except (LocalStoreError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GalaxyNetworkError("Galaxy service trust is unreadable") from exc
    if not isinstance(raw, dict) or set(raw) != {
        "schema_version",
        "configured",
        "reason",
        "service_url",
        "members_issuer",
        "receipt_keys",
        "moderation_keys",
        "knowledge_keys",
    }:
        raise GalaxyNetworkError("Galaxy service trust fields do not match schema 1")
    if raw["schema_version"] != 1 or type(raw["configured"]) is not bool:
        raise GalaxyNetworkError("Galaxy service trust schema is unsupported")
    receipt_keys = tuple(_receipt_key(item) for item in _objects(raw["receipt_keys"], 16))
    moderation_keys = tuple(
        GalaxyModerationKey(item.key_id, item.public_key_base64, item.revoked)
        for item in (_receipt_key(value) for value in _objects(raw["moderation_keys"], 16))
    )
    knowledge_keys = tuple(
        KnowledgePublisherKey(item.key_id, item.public_key_base64, item.revoked)
        for item in (_receipt_key(value) for value in _objects(raw["knowledge_keys"], 16))
    )
    trust = GalaxyServiceTrust(
        raw["configured"],
        _text(raw["reason"], "Galaxy service trust reason", 500),
        _optional_text(raw["service_url"], "Galaxy service URL", 2048),
        _optional_text(raw["members_issuer"], "Galaxy Members issuer", 2048),
        receipt_keys,
        moderation_keys,
        knowledge_keys,
    )
    # Construction runs the same semantic validation as the live client.
    GalaxyNetworkService(Path.cwd(), GalaxyIntelligenceService(Path.cwd()), trust)
    return trust


def galaxy_submission_receipt_document(
    *,
    receipt_id: str,
    contribution_id: str,
    contribution_digest: str,
    received_at: str,
    state: str,
    signer_id: str,
) -> dict[str, object]:
    if state not in {"pending-review", "duplicate"}:
        raise GalaxyNetworkError("Galaxy receipt state is invalid")
    if not re.fullmatch(r"[0-9a-f]{32}", contribution_id) or not _sha256(contribution_digest):
        raise GalaxyNetworkError("Galaxy receipt contribution binding is invalid")
    return {
        "format": GalaxyNetworkService.RECEIPT_FORMAT,
        "schema_version": GalaxyNetworkService.SCHEMA_VERSION,
        "receipt_id": _identifier(receipt_id),
        "contribution_id": contribution_id,
        "contribution_digest": contribution_digest,
        "received_at": _timestamp(received_at).isoformat(),
        "state": state,
        "signer_id": _identifier(signer_id),
        "signature_algorithm": "ed25519",
    }


def _receipt_key(value: dict[str, object]) -> GalaxyReceiptKey:
    if set(value) != {"key_id", "public_key_base64", "revoked"}:
        raise GalaxyNetworkError("Galaxy trust key fields are invalid")
    if type(value["revoked"]) is not bool:
        raise GalaxyNetworkError("Galaxy trust key revocation state is invalid")
    key = GalaxyReceiptKey(
        _identifier(value["key_id"]),
        _text(value["public_key_base64"], "Galaxy public key", 128),
        value["revoked"],
    )
    if not key.revoked:
        key.public_key()
    return key


def _objects(value: object, maximum: int) -> tuple[dict[str, object], ...]:
    if (
        not isinstance(value, list)
        or len(value) > maximum
        or any(not isinstance(item, dict) for item in value)
    ):
        raise GalaxyNetworkError("Galaxy trust key collection is invalid")
    return tuple(value)  # type: ignore[return-value]


def _public_https_url(value: object, label: str) -> str:
    text = _text(value, label, 4096)
    parsed = urllib.parse.urlsplit(text)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise GalaxyNetworkError(f"{label} must be a clean public HTTPS URL")
    hostname = parsed.hostname.casefold().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise GalaxyNetworkError(f"{label} cannot use a local address")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise GalaxyNetworkError(f"{label} cannot use a private address")
    return urllib.parse.urlunsplit(("https", parsed.netloc.casefold(), parsed.path or "/", "", ""))


def _timestamp(value: object) -> datetime:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise GalaxyNetworkError("Galaxy timestamp is invalid") from exc
    if result.tzinfo is None:
        raise GalaxyNetworkError("Galaxy timestamp requires a timezone")
    return result.astimezone(UTC)


def _identifier(value: object) -> str:
    result = str(value).strip().casefold()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,95}", result):
        raise GalaxyNetworkError("Galaxy identifier is invalid")
    return result


def _text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise GalaxyNetworkError(f"{label} is invalid")
    result = value.strip()
    if not result or len(result) > maximum or "\x00" in result:
        raise GalaxyNetworkError(f"{label} is invalid")
    return result


def _optional_text(value: object, label: str, maximum: int) -> str:
    if value == "":
        return ""
    return _text(value, label, maximum)


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise GalaxyNetworkError(f"Duplicate Galaxy field: {key}")
        result[key] = value
    return result


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha256(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))
