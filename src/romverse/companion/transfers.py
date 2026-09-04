from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from time import time
from uuid import uuid4

from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    bounded_regular_files,
    ensure_private_directory,
    read_json_object,
    remove_regular_file,
    sha256_regular_file,
)


class CompanionTransferError(ValueError):
    """A Companion handoff failed its local evidence or storage contract."""


class CompanionTransferKind(StrEnum):
    APK = "apk"
    REPORT = "report"
    RECOVERY_CAPSULE = "recovery_capsule"
    APPROVED_PACKAGE = "approved_package"
    EMERGENCY_GUIDE = "emergency_guide"


_KIND_RULES: dict[CompanionTransferKind, tuple[tuple[str, ...], int, str]] = {
    CompanionTransferKind.APK: (
        (".apk",),
        512 * 1024 * 1024,
        "application/vnd.android.package-archive",
    ),
    CompanionTransferKind.REPORT: (
        (".json", ".txt", ".log", ".html", ".htm", ".pdf"),
        64 * 1024 * 1024,
        "application/octet-stream",
    ),
    CompanionTransferKind.RECOVERY_CAPSULE: (
        (".romverse-recovery", ".recovery.zip", ".zip"),
        4 * 1024 * 1024 * 1024,
        "application/vnd.romverse.recovery-capsule",
    ),
    CompanionTransferKind.APPROVED_PACKAGE: (
        (".romverse-package", ".romverse", ".zip", ".bin", ".img"),
        4 * 1024 * 1024 * 1024,
        "application/vnd.romverse.approved-package",
    ),
    CompanionTransferKind.EMERGENCY_GUIDE: (
        (".json", ".txt", ".html", ".htm", ".pdf"),
        4 * 1024 * 1024,
        "application/vnd.romverse.emergency-guide",
    ),
}


@dataclass(frozen=True)
class CompanionTransferPreview:
    source: Path
    kind: CompanionTransferKind
    display_name: str
    media_type: str
    size_bytes: int
    sha256: str
    source_mtime_ns: int
    source_device: int
    source_inode: int


@dataclass(frozen=True)
class CompanionTransferOffer:
    transfer_id: str
    kind: CompanionTransferKind
    display_name: str
    media_type: str
    size_bytes: int
    sha256: str
    created_at_epoch_ms: int
    expires_at_epoch_ms: int
    content_file: str
    content_mtime_ns: int

    def to_wire_mapping(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "transfer_id": self.transfer_id,
            "kind": self.kind.value,
            "display_name": self.display_name,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "created_at_epoch_ms": self.created_at_epoch_ms,
            "expires_at_epoch_ms": self.expires_at_epoch_ms,
            "requires_phone_confirmation": True,
            "install_authority": "none",
            "execution_authority": "none",
            "download_path": f"/companion/transfers/{self.transfer_id}/content",
        }


class CompanionTransferService:
    """Private, content-addressed offers for an authenticated Companion Link.

    Selecting a file and inspecting it does not retain it. ``stage`` performs a
    second stable read only after the user has approved the exact preview. Offers
    grant download authority only; installation, execution, flashing, and opening
    the payload always remain separate phone-side actions.
    """

    SCHEMA_VERSION = 1
    MAX_MANIFEST_BYTES = 8 * 1024
    MAX_OFFERS = 64
    DEFAULT_TTL_SECONDS = 24 * 60 * 60
    MAX_TTL_SECONDS = 7 * 24 * 60 * 60
    TRANSFER_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
    SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")

    def __init__(
        self,
        workspace: Path,
        *,
        clock: Callable[[], float] = time,
    ) -> None:
        unresolved_workspace = Path(os.path.abspath(workspace))
        try:
            unresolved_details = unresolved_workspace.lstat()
            self.workspace = unresolved_workspace.resolve(strict=True)
        except OSError as exc:
            raise CompanionTransferError("The ROMVERSE workspace is unavailable") from exc
        if (
            unresolved_workspace.is_symlink()
            or not stat.S_ISDIR(unresolved_details.st_mode)
            or not self.workspace.is_dir()
            or self.workspace.is_symlink()
        ):
            raise CompanionTransferError("The ROMVERSE workspace boundary is unsafe")
        self.root = self.workspace / "config" / "companion-link" / "transfers"
        self.content_root = self.root / "content"
        self.offer_root = self.root / "offers"
        self.clock = clock

    def inspect(
        self,
        source: Path,
        kind: CompanionTransferKind | str,
    ) -> CompanionTransferPreview:
        selected_kind = self._kind(kind)
        source = Path(source)
        display_name = self._display_name(source.name)
        _suffixes, maximum, media_type = _KIND_RULES[selected_kind]
        self._validate_extension(display_name, selected_kind)
        try:
            details = source.lstat()
            if source.is_symlink() or not stat.S_ISREG(details.st_mode):
                raise CompanionTransferError("Choose a regular file, not a link or folder")
            digest, size = sha256_regular_file(
                source,
                boundary=source.parent,
                maximum_bytes=maximum,
            )
            current = source.lstat()
        except CompanionTransferError:
            raise
        except (LocalStoreError, OSError, ValueError) as exc:
            raise CompanionTransferError(f"The selected file could not be verified: {exc}") from exc
        if not os.path.samestat(details, current) or current.st_mtime_ns != details.st_mtime_ns:
            raise CompanionTransferError("The selected file changed while it was being inspected")
        return CompanionTransferPreview(
            source=source,
            kind=selected_kind,
            display_name=display_name,
            media_type=media_type,
            size_bytes=size,
            sha256=digest,
            source_mtime_ns=current.st_mtime_ns,
            source_device=current.st_dev,
            source_inode=current.st_ino,
        )

    def stage(
        self,
        preview: CompanionTransferPreview,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> CompanionTransferOffer:
        if not isinstance(preview, CompanionTransferPreview):
            raise CompanionTransferError("The Companion transfer preview is invalid")
        self._validate_preview(preview)
        if type(ttl_seconds) is not int or not 60 <= ttl_seconds <= self.MAX_TTL_SECONDS:
            raise CompanionTransferError("The Companion transfer expiry is invalid")
        ensure_private_directory(self.content_root, boundary=self.workspace)
        ensure_private_directory(self.offer_root, boundary=self.workspace)
        self._ensure_offer_capacity()
        content_path = self._copy_exact_preview(preview)
        content_details = content_path.lstat()
        created = int(self.clock() * 1_000)
        transfer_id = uuid4().hex
        offer = CompanionTransferOffer(
            transfer_id=transfer_id,
            kind=preview.kind,
            display_name=preview.display_name,
            media_type=preview.media_type,
            size_bytes=preview.size_bytes,
            sha256=preview.sha256,
            created_at_epoch_ms=created,
            expires_at_epoch_ms=created + ttl_seconds * 1_000,
            content_file=content_path.name,
            content_mtime_ns=content_details.st_mtime_ns,
        )
        unsigned: dict[str, object] = {
            "format": "romverse.companion.transfer-offer",
            "schema_version": self.SCHEMA_VERSION,
            "transfer": self._stored_mapping(offer),
        }
        atomic_write_json(
            self.offer_root / f"{transfer_id}.json",
            {**unsigned, "record_digest": self._digest(unsigned)},
            boundary=self.workspace,
            maximum_bytes=self.MAX_MANIFEST_BYTES,
        )
        return offer

    def list_active(self) -> tuple[CompanionTransferOffer, ...]:
        if not self.offer_root.exists() and not self.offer_root.is_symlink():
            return ()
        try:
            manifests = bounded_regular_files(
                self.offer_root,
                ".json",
                boundary=self.workspace,
                maximum_entries=self.MAX_OFFERS + 1,
            )
            if len(manifests) > self.MAX_OFFERS:
                raise CompanionTransferError("Too many Companion transfer offers are staged")
            offers = tuple(self._load_manifest(path) for path in manifests)
        except CompanionTransferError:
            raise
        except (LocalStoreError, OSError, ValueError) as exc:
            raise CompanionTransferError(
                f"Companion transfer offers are unavailable: {exc}"
            ) from exc
        now = int(self.clock() * 1_000)
        return tuple(
            sorted(
                (offer for offer in offers if offer.expires_at_epoch_ms > now),
                key=lambda item: (item.created_at_epoch_ms, item.transfer_id),
                reverse=True,
            )
        )

    def get_active(self, transfer_id: str) -> CompanionTransferOffer:
        if self.TRANSFER_ID_PATTERN.fullmatch(transfer_id) is None:
            raise CompanionTransferError("The Companion transfer identifier is invalid")
        try:
            offer = self._load_manifest(self.offer_root / f"{transfer_id}.json")
        except (LocalStoreError, OSError, ValueError) as exc:
            raise CompanionTransferError(f"The Companion transfer is unavailable: {exc}") from exc
        if offer.expires_at_epoch_ms <= int(self.clock() * 1_000):
            raise CompanionTransferError("The Companion transfer offer has expired")
        return offer

    def verified_content_path(self, transfer_id: str) -> tuple[CompanionTransferOffer, Path]:
        offer = self.get_active(transfer_id)
        content = self.content_root / offer.content_file
        try:
            digest, size = sha256_regular_file(
                content,
                boundary=self.workspace,
                maximum_bytes=_KIND_RULES[offer.kind][1],
            )
        except (LocalStoreError, OSError, ValueError) as exc:
            raise CompanionTransferError(
                f"The staged Companion payload is unavailable: {exc}"
            ) from exc
        if digest != offer.sha256 or size != offer.size_bytes:
            raise CompanionTransferError(
                "The staged Companion payload failed integrity verification"
            )
        return offer, content

    def revoke_all(self) -> int:
        """Revoke manifests after the user resets Link; content remains inert and private."""

        if not self.offer_root.exists() and not self.offer_root.is_symlink():
            return 0
        try:
            manifests = bounded_regular_files(
                self.offer_root,
                ".json",
                boundary=self.workspace,
                maximum_entries=self.MAX_OFFERS + 1,
            )
            if len(manifests) > self.MAX_OFFERS:
                raise CompanionTransferError("Too many Companion transfer offers are staged")
            return sum(
                remove_regular_file(path, boundary=self.workspace, missing_ok=True)
                for path in manifests
            )
        except (LocalStoreError, OSError, ValueError) as exc:
            raise CompanionTransferError(f"Companion transfer revocation failed: {exc}") from exc

    def _copy_exact_preview(self, preview: CompanionTransferPreview) -> Path:
        maximum = _KIND_RULES[preview.kind][1]
        destination = self.content_root / f"{preview.sha256}.blob"
        temporary = self.content_root / f".{preview.sha256}.{uuid4().hex}.tmp"
        source_descriptor = -1
        output_descriptor = -1
        try:
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            source_descriptor = os.open(preview.source, flags)
            opened = os.fstat(source_descriptor)
            current = preview.source.lstat()
            if (
                not stat.S_ISREG(opened.st_mode)
                or not os.path.samestat(opened, current)
                or opened.st_size != preview.size_bytes
                or opened.st_mtime_ns != preview.source_mtime_ns
                or opened.st_dev != preview.source_device
                or opened.st_ino != preview.source_inode
                or preview.source.is_symlink()
            ):
                raise CompanionTransferError("The selected file changed after its review")
            output_descriptor = os.open(
                temporary,
                os.O_CREAT
                | os.O_EXCL
                | os.O_WRONLY
                | getattr(os, "O_BINARY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            digest = hashlib.sha256()
            copied = 0
            with os.fdopen(source_descriptor, "rb", closefd=True) as source_stream:
                source_descriptor = -1
                with os.fdopen(output_descriptor, "wb", closefd=True) as output_stream:
                    output_descriptor = -1
                    while chunk := source_stream.read(1024 * 1024):
                        copied += len(chunk)
                        if copied > maximum:
                            raise CompanionTransferError(
                                "The selected file exceeds its transfer limit"
                            )
                        digest.update(chunk)
                        output_stream.write(chunk)
                    output_stream.flush()
                    os.fsync(output_stream.fileno())
                final_source = os.fstat(source_stream.fileno())
            current = preview.source.lstat()
            if (
                copied != preview.size_bytes
                or digest.hexdigest() != preview.sha256
                or not os.path.samestat(opened, final_source)
                or not os.path.samestat(final_source, current)
                or final_source.st_size != opened.st_size
                or final_source.st_mtime_ns != opened.st_mtime_ns
            ):
                raise CompanionTransferError("The selected file changed while it was staged")
            if destination.exists() or destination.is_symlink():
                existing_digest, existing_size = sha256_regular_file(
                    destination,
                    boundary=self.workspace,
                    maximum_bytes=maximum,
                )
                if existing_digest != preview.sha256 or existing_size != preview.size_bytes:
                    raise CompanionTransferError("A staged payload conflicts with this fingerprint")
            else:
                os.replace(temporary, destination)
                with suppress(PermissionError):
                    destination.chmod(0o600)
            return destination
        except CompanionTransferError:
            raise
        except (LocalStoreError, OSError, ValueError) as exc:
            raise CompanionTransferError(
                f"The approved Companion transfer could not be staged: {exc}"
            ) from exc
        finally:
            if source_descriptor >= 0:
                with suppress(OSError):
                    os.close(source_descriptor)
            if output_descriptor >= 0:
                with suppress(OSError):
                    os.close(output_descriptor)
            with suppress(OSError):
                temporary.unlink(missing_ok=True)

    def _validate_preview(self, preview: CompanionTransferPreview) -> None:
        if not isinstance(preview.source, Path) or not isinstance(
            preview.kind, CompanionTransferKind
        ):
            raise CompanionTransferError("The Companion transfer preview is invalid")
        display_name = self._display_name(preview.display_name)
        self._validate_extension(display_name, preview.kind)
        _suffixes, maximum, media_type = _KIND_RULES[preview.kind]
        if (
            display_name != preview.source.name
            or preview.media_type != media_type
            or type(preview.size_bytes) is not int
            or not 0 < preview.size_bytes <= maximum
            or not isinstance(preview.sha256, str)
            or self.SHA256_PATTERN.fullmatch(preview.sha256) is None
            or type(preview.source_mtime_ns) is not int
            or preview.source_mtime_ns <= 0
            or type(preview.source_device) is not int
            or preview.source_device < 0
            or type(preview.source_inode) is not int
            or preview.source_inode < 0
        ):
            raise CompanionTransferError("The Companion transfer preview is invalid")

    def _ensure_offer_capacity(self) -> None:
        try:
            manifests = bounded_regular_files(
                self.offer_root,
                ".json",
                boundary=self.workspace,
                maximum_entries=self.MAX_OFFERS,
            )
        except (LocalStoreError, OSError, ValueError) as exc:
            raise CompanionTransferError(
                f"Companion transfer offers are unavailable: {exc}"
            ) from exc
        if len(manifests) >= self.MAX_OFFERS:
            raise CompanionTransferError(
                "The Companion transfer offer limit is reached; clear pending handoffs first"
            )

    def _load_manifest(self, path: Path) -> CompanionTransferOffer:
        payload = read_json_object(
            path,
            boundary=self.workspace,
            maximum_bytes=self.MAX_MANIFEST_BYTES,
        )
        if set(payload) != {"format", "schema_version", "transfer", "record_digest"}:
            raise CompanionTransferError("A Companion transfer manifest has an invalid shape")
        try:
            schema_version = self._strict_int(payload["schema_version"])
        except ValueError as exc:
            raise CompanionTransferError("A Companion transfer manifest is invalid") from exc
        if payload["format"] != "romverse.companion.transfer-offer" or (
            schema_version != self.SCHEMA_VERSION
        ):
            raise CompanionTransferError("A Companion transfer manifest is unsupported")
        unsigned = dict(payload)
        record_digest = unsigned.pop("record_digest")
        if not isinstance(record_digest, str) or record_digest != self._digest(unsigned):
            raise CompanionTransferError(
                "A Companion transfer manifest failed integrity verification"
            )
        raw = payload["transfer"]
        expected = {
            "transfer_id",
            "kind",
            "display_name",
            "media_type",
            "size_bytes",
            "sha256",
            "created_at_epoch_ms",
            "expires_at_epoch_ms",
            "content_file",
            "content_mtime_ns",
            "requires_phone_confirmation",
            "install_authority",
            "execution_authority",
        }
        if not isinstance(raw, dict) or set(raw) != expected:
            raise CompanionTransferError("A Companion transfer record has an invalid shape")
        try:
            kind = self._kind(raw["kind"])
            offer = CompanionTransferOffer(
                transfer_id=str(raw["transfer_id"]),
                kind=kind,
                display_name=self._display_name(raw["display_name"]),
                media_type=str(raw["media_type"]),
                size_bytes=self._strict_int(raw["size_bytes"]),
                sha256=str(raw["sha256"]),
                created_at_epoch_ms=self._strict_int(raw["created_at_epoch_ms"]),
                expires_at_epoch_ms=self._strict_int(raw["expires_at_epoch_ms"]),
                content_file=str(raw["content_file"]),
                content_mtime_ns=self._strict_int(raw["content_mtime_ns"]),
            )
        except (TypeError, ValueError) as exc:
            raise CompanionTransferError("A Companion transfer record is invalid") from exc
        _suffixes, maximum, expected_media = _KIND_RULES[kind]
        expected_content_file = f"{offer.sha256}.blob"
        if (
            self.TRANSFER_ID_PATTERN.fullmatch(offer.transfer_id) is None
            or path.name != f"{offer.transfer_id}.json"
            or self.SHA256_PATTERN.fullmatch(offer.sha256) is None
            or offer.content_file != expected_content_file
            or offer.media_type != expected_media
            or not 0 < offer.size_bytes <= maximum
            or offer.created_at_epoch_ms <= 0
            or not offer.created_at_epoch_ms < offer.expires_at_epoch_ms
            or offer.expires_at_epoch_ms - offer.created_at_epoch_ms > self.MAX_TTL_SECONDS * 1_000
            or offer.content_mtime_ns <= 0
            or raw["requires_phone_confirmation"] is not True
            or raw["install_authority"] != "none"
            or raw["execution_authority"] != "none"
        ):
            raise CompanionTransferError("A Companion transfer record violates its safety contract")
        self._validate_extension(offer.display_name, kind)
        content = self.content_root / offer.content_file
        try:
            details = content.lstat()
        except OSError as exc:
            raise CompanionTransferError("A staged Companion payload is unavailable") from exc
        if (
            content.is_symlink()
            or not stat.S_ISREG(details.st_mode)
            or details.st_size != offer.size_bytes
            or details.st_mtime_ns != offer.content_mtime_ns
        ):
            raise CompanionTransferError("A staged Companion payload changed after approval")
        return offer

    @staticmethod
    def _stored_mapping(offer: CompanionTransferOffer) -> dict[str, object]:
        return {
            "transfer_id": offer.transfer_id,
            "kind": offer.kind.value,
            "display_name": offer.display_name,
            "media_type": offer.media_type,
            "size_bytes": offer.size_bytes,
            "sha256": offer.sha256,
            "created_at_epoch_ms": offer.created_at_epoch_ms,
            "expires_at_epoch_ms": offer.expires_at_epoch_ms,
            "content_file": offer.content_file,
            "content_mtime_ns": offer.content_mtime_ns,
            "requires_phone_confirmation": True,
            "install_authority": "none",
            "execution_authority": "none",
        }

    @staticmethod
    def _strict_int(value: object) -> int:
        if type(value) is not int:
            raise ValueError("expected an integer")
        return value

    @staticmethod
    def _kind(value: object) -> CompanionTransferKind:
        try:
            return (
                value if isinstance(value, CompanionTransferKind) else CompanionTransferKind(value)
            )
        except (TypeError, ValueError) as exc:
            raise CompanionTransferError("The Companion transfer type is unsupported") from exc

    @staticmethod
    def _display_name(value: object) -> str:
        if not isinstance(value, str):
            raise CompanionTransferError("The Companion transfer filename is invalid")
        if (
            not 1 <= len(value) <= 160
            or value != Path(value).name
            or value in {".", ".."}
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise CompanionTransferError("The Companion transfer filename is invalid")
        return value

    @staticmethod
    def _validate_extension(display_name: str, kind: CompanionTransferKind) -> None:
        allowed = _KIND_RULES[kind][0]
        lowered = display_name.casefold()
        if not any(lowered.endswith(suffix) for suffix in allowed):
            choices = ", ".join(allowed)
            raise CompanionTransferError(
                f"{kind.value.replace('_', ' ').title()} files must end in {choices}"
            )

    @staticmethod
    def _digest(payload: object) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
