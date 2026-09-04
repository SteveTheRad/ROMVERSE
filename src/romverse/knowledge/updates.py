"""Detached Ed25519 verification for explicit, offline Synapse archive updates."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_regular_bytes,
)
from romverse.knowledge.models import KnowledgeArchive, KnowledgeImportResult
from romverse.knowledge.store import (
    MAX_ARCHIVE_BYTES,
    KnowledgeArchiveError,
    KnowledgeArchiveStore,
    load_packaged_archive,
    merge_archives,
    parse_archive,
    reconcile_packaged_archive,
)


class KnowledgeUpdateError(ValueError):
    """A signed knowledge update failed its trust or integrity boundary."""


@dataclass(frozen=True, slots=True)
class KnowledgePublisherKey:
    key_id: str
    public_key_base64: str
    revoked: bool = False

    def public_key(self) -> Ed25519PublicKey:
        if self.revoked:
            raise KnowledgeUpdateError("Knowledge publisher key is revoked")
        try:
            raw = base64.b64decode(self.public_key_base64, validate=True)
            if len(raw) != 32:
                raise ValueError("wrong key length")
            return Ed25519PublicKey.from_public_bytes(raw)
        except (ValueError, binascii.Error) as exc:
            raise KnowledgeUpdateError("Knowledge publisher public key is invalid") from exc


@dataclass(frozen=True, slots=True)
class KnowledgeUpdatePreview:
    source_path: Path
    update_id: str
    signer_id: str
    issued_at: str
    expires_at: str
    envelope_sha256: str
    incoming_archive_digest: str
    current_archive_digest: str
    result: KnowledgeImportResult
    incoming_archive: KnowledgeArchive
    execution_authority: str = "none"
    phone_action_allowed: bool = False


@dataclass(frozen=True, slots=True)
class KnowledgeUpdateReceipt:
    update_id: str
    signer_id: str
    applied_at: str
    envelope_sha256: str
    incoming_archive_digest: str
    previous_archive_digest: str
    installed_archive_digest: str
    added: int
    updated: int
    unchanged: int
    record_count: int
    receipt_path: Path
    execution_authority: str = "none"
    phone_changed: bool = False


class KnowledgeUpdateService:
    """Preview and explicitly merge signed local updates; never downloads or executes them."""

    FORMAT = "romverse.synapse.signed-update"
    SCHEMA_VERSION = 1
    DOMAIN = b"ROMVERSE-SYNAPSE-KNOWLEDGE-UPDATE-V1\x00"
    MAX_ENVELOPE_BYTES = MAX_ARCHIVE_BYTES + 256 * 1024
    MAX_RECEIPT_BYTES = 128 * 1024
    _FIELDS = {
        "format",
        "schema_version",
        "update_id",
        "signer_id",
        "signature_algorithm",
        "issued_at",
        "expires_at",
        "archive",
        "signature",
    }

    def __init__(
        self,
        workspace: Path,
        trust_keys: tuple[KnowledgePublisherKey, ...],
        *,
        unavailable_reason: str = "No trusted ROMVERSE knowledge publisher key is configured.",
    ) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.store = KnowledgeArchiveStore(self.workspace)
        self.trust_keys = {self._identifier(key.key_id): key for key in trust_keys}
        if len(self.trust_keys) != len(trust_keys):
            raise KnowledgeUpdateError("Knowledge publisher key identities are duplicated")
        for key in trust_keys:
            key.public_key()
        self.unavailable_reason = unavailable_reason.strip()[:500] or (
            "No trusted ROMVERSE knowledge publisher key is configured."
        )
        self.receipt_root = self.workspace / "knowledge" / "update-receipts"

    @property
    def configured(self) -> bool:
        return any(not key.revoked for key in self.trust_keys.values())

    def inspect(
        self,
        source: Path,
        *,
        now: datetime | None = None,
    ) -> KnowledgeUpdatePreview:
        if not self.configured:
            raise KnowledgeUpdateError(self.unavailable_reason)
        resolved, payload = self._read(source)
        envelope = self._document(payload)
        timestamp = (now or datetime.now(UTC)).astimezone(UTC)
        issued = self._timestamp(envelope["issued_at"])
        expires = self._timestamp(envelope["expires_at"])
        if issued > timestamp + timedelta(minutes=5):
            raise KnowledgeUpdateError("Knowledge update issue time is in the future")
        if expires <= timestamp or expires <= issued:
            raise KnowledgeUpdateError("Knowledge update is expired or has an invalid window")
        signer_id = self._identifier(envelope["signer_id"])
        trust = self.trust_keys.get(signer_id)
        if trust is None:
            raise KnowledgeUpdateError("Knowledge update publisher is not trusted")
        if trust.revoked:
            raise KnowledgeUpdateError("Knowledge update publisher key is revoked")
        try:
            signature = base64.b64decode(str(envelope["signature"]), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise KnowledgeUpdateError("Knowledge update signature is malformed") from exc
        if len(signature) != 64:
            raise KnowledgeUpdateError("Knowledge update signature has an invalid length")
        unsigned = dict(envelope)
        unsigned.pop("signature")
        try:
            trust.public_key().verify(signature, self.DOMAIN + self.canonical_bytes(unsigned))
        except InvalidSignature as exc:
            raise KnowledgeUpdateError("Knowledge update signature verification failed") from exc
        archive_raw = envelope["archive"]
        if not isinstance(archive_raw, dict):
            raise KnowledgeUpdateError("Knowledge update archive must be an object")
        try:
            incoming = parse_archive(archive_raw)
            current = self._current_archive_readonly()
            _merged, result = merge_archives(current, incoming)
        except KnowledgeArchiveError as exc:
            raise KnowledgeUpdateError(f"Knowledge update content was rejected: {exc}") from exc
        return KnowledgeUpdatePreview(
            resolved,
            self._identifier(envelope["update_id"]),
            signer_id,
            issued.isoformat(),
            expires.isoformat(),
            hashlib.sha256(payload).hexdigest(),
            incoming.bundle_digest,
            current.bundle_digest,
            result,
            incoming,
        )

    def apply(self, preview: KnowledgeUpdatePreview) -> KnowledgeUpdateReceipt:
        if not isinstance(preview, KnowledgeUpdatePreview):
            raise KnowledgeUpdateError("Knowledge update preview is invalid")
        try:
            fresh = self.inspect(preview.source_path)
        except KnowledgeUpdateError as exc:
            raise KnowledgeUpdateError(
                "Knowledge update changed after the reviewed preview"
            ) from exc
        if (
            fresh.update_id != preview.update_id
            or fresh.signer_id != preview.signer_id
            or not hmac.compare_digest(fresh.envelope_sha256, preview.envelope_sha256)
            or not hmac.compare_digest(
                fresh.incoming_archive_digest, preview.incoming_archive_digest
            )
            or not hmac.compare_digest(
                fresh.current_archive_digest, preview.current_archive_digest
            )
            or fresh.result != preview.result
        ):
            raise KnowledgeUpdateError(
                "Knowledge update or local Archive changed after the reviewed preview"
            )
        current = self.store.ensure_seeded()
        merged, result = merge_archives(current, fresh.incoming_archive)
        saved = self.store.save(merged)
        applied_at = datetime.now(UTC).isoformat()
        receipt_data = {
            "format": "romverse.synapse.knowledge-update-receipt",
            "schema_version": 1,
            "update_id": fresh.update_id,
            "signer_id": fresh.signer_id,
            "applied_at": applied_at,
            "envelope_sha256": fresh.envelope_sha256,
            "incoming_archive_digest": fresh.incoming_archive_digest,
            "previous_archive_digest": current.bundle_digest,
            "installed_archive_digest": saved.bundle_digest,
            "added": result.added,
            "updated": result.updated,
            "unchanged": result.unchanged,
            "record_count": result.record_count,
            "execution_authority": "none",
            "phone_changed": False,
        }
        receipt_data["receipt_digest"] = hashlib.sha256(
            self.canonical_bytes(receipt_data)
        ).hexdigest()
        receipt_path = self.receipt_root / f"{fresh.update_id}.json"
        try:
            ensure_private_directory(self.receipt_root, boundary=self.workspace)
            atomic_write_json(
                receipt_path,
                receipt_data,
                boundary=self.workspace,
                maximum_bytes=self.MAX_RECEIPT_BYTES,
            )
        except LocalStoreError as exc:
            raise KnowledgeUpdateError(
                "Knowledge updated, but its local audit receipt could not be preserved"
            ) from exc
        return KnowledgeUpdateReceipt(
            fresh.update_id,
            fresh.signer_id,
            applied_at,
            fresh.envelope_sha256,
            fresh.incoming_archive_digest,
            current.bundle_digest,
            saved.bundle_digest,
            result.added,
            result.updated,
            result.unchanged,
            result.record_count,
            receipt_path,
        )

    @classmethod
    def canonical_bytes(cls, value: object) -> bytes:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")

    def _read(self, source: Path) -> tuple[Path, bytes]:
        unresolved = source.expanduser()
        if unresolved.is_symlink():
            raise KnowledgeUpdateError("Knowledge update cannot be a symbolic link")
        try:
            resolved = unresolved.resolve(strict=True)
            payload = read_regular_bytes(
                resolved,
                boundary=resolved.parent,
                maximum_bytes=self.MAX_ENVELOPE_BYTES,
            )
        except (LocalStoreError, OSError) as exc:
            raise KnowledgeUpdateError("Knowledge update file is unavailable") from exc
        return resolved, payload

    def _current_archive_readonly(self) -> KnowledgeArchive:
        if not self.store.path.exists() and not self.store.path.is_symlink():
            return load_packaged_archive()
        current = self.store.load()
        return reconcile_packaged_archive(current, load_packaged_archive())

    def _document(self, payload: bytes) -> dict[str, object]:
        try:
            value = json.loads(payload.decode("utf-8"), object_pairs_hook=self._strict_object)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise KnowledgeUpdateError("Knowledge update is not valid JSON") from exc
        if not isinstance(value, dict) or set(value) != self._FIELDS:
            raise KnowledgeUpdateError("Knowledge update fields do not match schema 1")
        if (
            value["format"] != self.FORMAT
            or value["schema_version"] != self.SCHEMA_VERSION
            or isinstance(value["schema_version"], bool)
            or value["signature_algorithm"] != "ed25519"
        ):
            raise KnowledgeUpdateError("Knowledge update format or signature scheme is unsupported")
        return value

    @staticmethod
    def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise KnowledgeUpdateError(f"Duplicate knowledge update field: {key}")
            value[key] = item
        return value

    @staticmethod
    def _identifier(value: object) -> str:
        text = str(value or "").strip().casefold()
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,95}", text):
            raise KnowledgeUpdateError("Knowledge update identifier is invalid")
        return text

    @staticmethod
    def _timestamp(value: object) -> datetime:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise KnowledgeUpdateError("Knowledge update timestamp is invalid") from exc
        if parsed.tzinfo is None:
            raise KnowledgeUpdateError("Knowledge update timestamp needs a timezone")
        return parsed.astimezone(UTC)


def signed_update_document(
    archive: KnowledgeArchive,
    *,
    update_id: str,
    signer_id: str,
    issued_at: str,
    expires_at: str,
) -> dict[str, object]:
    """Build the exact unsigned document a separate offline signer must sign."""

    return {
        "format": KnowledgeUpdateService.FORMAT,
        "schema_version": KnowledgeUpdateService.SCHEMA_VERSION,
        "update_id": KnowledgeUpdateService._identifier(update_id),
        "signer_id": KnowledgeUpdateService._identifier(signer_id),
        "signature_algorithm": "ed25519",
        "issued_at": KnowledgeUpdateService._timestamp(issued_at).isoformat(),
        "expires_at": KnowledgeUpdateService._timestamp(expires_at).isoformat(),
        "archive": {
            "format": "romverse.offline-knowledge-archive",
            **asdict(archive),
        },
    }
