from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import stat
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from romverse import __version__
from romverse.infrastructure.local_store import (
    LocalStoreError,
    atomic_write_json,
    ensure_private_directory,
    read_regular_bytes,
    remove_regular_file,
    sha256_regular_file,
)
from romverse.release import (
    MAX_RELEASE_ARTIFACT_BYTES,
    MAX_RELEASE_DOCUMENT_BYTES,
    RELEASE_PRODUCT,
    DesktopReleaseArtifact,
    DesktopReleaseManifest,
    ReleaseValidationError,
    parse_release_json_bytes,
    release_version_order,
    verify_signed_release_envelope,
)

UPDATE_TRUST_SCHEMA_VERSION = 1
MAX_UPDATE_TRUST_BYTES = 64 * 1024
MAX_UPDATE_RECEIPT_BYTES = 64 * 1024
UPDATE_CHANNELS = frozenset({"stable", "preview"})
CHANNEL_RELEASE_KINDS: Mapping[str, frozenset[str]] = {
    "stable": frozenset({"stable"}),
    "preview": frozenset({"stable", "release-candidate"}),
}
HOST_PLATFORMS = frozenset({"linux-x86_64", "windows-x86_64"})

DownloadProgress = Callable[[int, int], None]


class DesktopUpdateError(ValueError):
    """A desktop update failed its network, signature, or local-storage boundary."""


class DesktopUpdateCancelled(DesktopUpdateError):
    """The user withdrew a signed-update download before it was committed."""


@dataclass(frozen=True, slots=True)
class DesktopUpdateTrust:
    configured: bool
    reason: str
    key_id: str
    public_key_base64: str
    stable_url: str
    preview_url: str

    def manifest_url(self, channel: str) -> str:
        if channel not in UPDATE_CHANNELS:
            raise DesktopUpdateError("Desktop update channel is unsupported")
        if not self.configured:
            raise DesktopUpdateError(self.reason)
        return self.stable_url if channel == "stable" else self.preview_url

    def public_key(self) -> Ed25519PublicKey:
        if not self.configured:
            raise DesktopUpdateError(self.reason)
        try:
            raw = base64.b64decode(self.public_key_base64, validate=True)
            if len(raw) != 32:
                raise ValueError("wrong key length")
            return Ed25519PublicKey.from_public_bytes(raw)
        except (ValueError, binascii.Error) as exc:
            raise DesktopUpdateError("Pinned desktop update public key is invalid") from exc


@dataclass(frozen=True, slots=True)
class DesktopUpdateCandidate:
    current_version: str
    available: bool
    manifest: DesktopReleaseManifest
    manifest_sha256: str
    manifest_url: str
    artifact: DesktopReleaseArtifact | None
    artifact_url: str
    checked_at: str
    execution_authority: str = "none"
    automatic_install: bool = False
    requires_explicit_confirmation: bool = True


@dataclass(frozen=True, slots=True)
class StagedDesktopUpdate:
    release_id: str
    version: str
    channel: str
    platform: str
    artifact_path: Path
    receipt_path: Path
    sha256: str
    size_bytes: int
    execution_authority: str = "none"
    automatic_install: bool = False


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DesktopUpdateError(f"Duplicate update trust field: {key}")
        result[key] = value
    return result


def load_desktop_update_trust(path: Path) -> DesktopUpdateTrust:
    """Load the immutable publisher configuration packaged with the application."""

    try:
        details = path.lstat()
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
            raise DesktopUpdateError("Desktop update trust must be a regular packaged file")
        if not 2 <= details.st_size <= MAX_UPDATE_TRUST_BYTES:
            raise DesktopUpdateError("Desktop update trust exceeds its size boundary")
        value = json.loads(path.read_bytes(), object_pairs_hook=_strict_object)
    except DesktopUpdateError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DesktopUpdateError("Desktop update trust is unreadable") from exc
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "configured",
        "product",
        "reason",
        "key_id",
        "public_key_base64",
        "channels",
    }:
        raise DesktopUpdateError("Desktop update trust fields do not match schema 1")
    if value["schema_version"] != UPDATE_TRUST_SCHEMA_VERSION or isinstance(
        value["schema_version"], bool
    ):
        raise DesktopUpdateError("Desktop update trust schema is unsupported")
    if value["product"] != RELEASE_PRODUCT or not isinstance(value["configured"], bool):
        raise DesktopUpdateError("Desktop update trust product or state is invalid")
    reason = value["reason"]
    key_id = value["key_id"]
    public_key = value["public_key_base64"]
    channels = value["channels"]
    if (
        not isinstance(reason, str)
        or not 1 <= len(reason) <= 500
        or not isinstance(key_id, str)
        or len(key_id) > 96
        or not isinstance(public_key, str)
        or len(public_key) > 128
        or not isinstance(channels, dict)
        or set(channels) != UPDATE_CHANNELS
        or not all(isinstance(item, str) and len(item) <= 2048 for item in channels.values())
    ):
        raise DesktopUpdateError("Desktop update trust values are invalid")
    trust = DesktopUpdateTrust(
        value["configured"],
        reason,
        key_id,
        public_key,
        channels["stable"],
        channels["preview"],
    )
    if trust.configured:
        if not key_id:
            raise DesktopUpdateError("Desktop update signing identity is missing")
        trust.public_key()
        _validate_https_url(trust.stable_url)
        _validate_https_url(trust.preview_url)
    elif key_id or public_key or trust.stable_url or trust.preview_url:
        raise DesktopUpdateError("Unconfigured desktop update trust cannot carry partial authority")
    return trust


class DesktopUpdateService:
    """Check and stage signed releases without installing or changing the workspace."""

    def __init__(
        self,
        trust: DesktopUpdateTrust,
        *,
        current_version: str,
        platform: str,
        opener=None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        release_version_order(current_version)
        if platform not in HOST_PLATFORMS:
            raise DesktopUpdateError("Desktop update platform is unsupported")
        self.trust = trust
        self.current_version = current_version
        self.platform = platform
        self._opener = opener or urllib.request.urlopen
        self._now = now or (lambda: datetime.now(UTC))
        self._accepted_candidate: DesktopUpdateCandidate | None = None

    def check(self, channel: str) -> DesktopUpdateCandidate:
        manifest_url = self.trust.manifest_url(channel)
        encoded = self._read_metadata(manifest_url)
        try:
            envelope = parse_release_json_bytes(encoded)
            manifest, digest = verify_signed_release_envelope(
                envelope,
                self.trust.public_key(),
                self.trust.key_id,
            )
        except ReleaseValidationError as exc:
            raise DesktopUpdateError(f"Signed desktop update was rejected: {exc}") from exc
        if manifest.channel not in CHANNEL_RELEASE_KINDS[channel]:
            raise DesktopUpdateError(
                "Signed release does not belong to the selected update channel"
            )
        published = datetime.fromisoformat(manifest.published_at[:-1] + "+00:00")
        if published > self._now() + timedelta(minutes=5):
            raise DesktopUpdateError("Signed release timestamp is unexpectedly in the future")

        available = release_version_order(manifest.version) > release_version_order(
            self.current_version
        )
        artifact: DesktopReleaseArtifact | None = None
        artifact_url = ""
        if available:
            eligible = tuple(
                item
                for item in manifest.artifacts
                if item.platform == self.platform and item.kind in {"installer", "archive"}
            )
            if len(eligible) != 1:
                raise DesktopUpdateError(
                    "Signed release must contain exactly one installable artifact for this platform"
                )
            artifact = eligible[0]
            artifact_url = _sibling_url(manifest_url, artifact.file_name)
        candidate = DesktopUpdateCandidate(
            self.current_version,
            available,
            manifest,
            digest,
            manifest_url,
            artifact,
            artifact_url,
            self._now().isoformat(),
        )
        self._accepted_candidate = candidate
        return candidate

    def stage(
        self,
        candidate: DesktopUpdateCandidate,
        destination: Path,
        *,
        progress: DownloadProgress | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> StagedDesktopUpdate:
        self._validate_candidate(candidate)
        _raise_if_update_cancelled(should_cancel)
        artifact = candidate.artifact
        if artifact is None:
            raise DesktopUpdateError("No newer desktop update is available to download")
        root = Path(os.path.abspath(destination))
        boundary = root.parent
        release_directory = root / candidate.manifest.release_id
        target = release_directory / artifact.file_name
        receipt = release_directory / "staged-update.romverse"
        temporary = release_directory / f".{artifact.file_name}.{uuid4().hex}.part"
        published_new_target = False
        wrote_receipt = False
        try:
            ensure_private_directory(root, boundary=boundary)
            ensure_private_directory(release_directory, boundary=boundary)
            _raise_if_update_cancelled(should_cancel)
            if target.exists() or target.is_symlink():
                _verify_regular_artifact(target, artifact, boundary=boundary)
            else:
                self._download_artifact(
                    candidate.artifact_url,
                    temporary,
                    artifact,
                    progress,
                    should_cancel,
                )
                _raise_if_update_cancelled(should_cancel)
                if target.exists() or target.is_symlink():
                    raise DesktopUpdateError("Desktop update target changed during staging")
                os.replace(temporary, target)
                published_new_target = True
                with suppress(PermissionError):
                    target.chmod(0o600)
            _raise_if_update_cancelled(should_cancel)
            receipt_payload: dict[str, object] = {
                "format": "romverse.desktop-update-stage",
                "schema_version": 1,
                "release_id": candidate.manifest.release_id,
                "version": candidate.manifest.version,
                "channel": candidate.manifest.channel,
                "platform": artifact.platform,
                "artifact_file": artifact.file_name,
                "artifact_sha256": artifact.sha256,
                "artifact_size_bytes": artifact.size_bytes,
                "manifest_sha256": candidate.manifest_sha256,
                "key_id": self.trust.key_id,
                "staged_at": self._now().isoformat(),
                "workspace_preserved": True,
                "requires_explicit_confirmation": True,
                "automatic_install": False,
                "execution_authority": "none",
            }
            receipt_payload["receipt_sha256"] = _payload_digest(receipt_payload)
            atomic_write_json(
                receipt,
                receipt_payload,
                boundary=boundary,
                maximum_bytes=MAX_UPDATE_RECEIPT_BYTES,
            )
            wrote_receipt = True
            return self.verify_staged(candidate, root)
        except (OSError, urllib.error.URLError, LocalStoreError, DesktopUpdateError) as exc:
            if wrote_receipt:
                with suppress(LocalStoreError):
                    remove_regular_file(receipt, boundary=boundary)
            if published_new_target:
                with suppress(LocalStoreError):
                    remove_regular_file(target, boundary=boundary)
            if isinstance(exc, DesktopUpdateError):
                raise
            raise DesktopUpdateError(f"Desktop update staging failed: {exc}") from exc
        finally:
            with suppress(LocalStoreError):
                remove_regular_file(temporary, boundary=boundary)

    def verify_staged(
        self,
        candidate: DesktopUpdateCandidate,
        destination: Path,
    ) -> StagedDesktopUpdate:
        """Reload and independently verify one staged artifact and its private receipt."""

        self._validate_candidate(candidate)
        artifact = candidate.artifact
        if artifact is None:
            raise DesktopUpdateError("No newer desktop update is available to verify")
        root = Path(os.path.abspath(destination))
        boundary = root.parent
        release_directory = root / candidate.manifest.release_id
        target = release_directory / artifact.file_name
        receipt = release_directory / "staged-update.romverse"
        try:
            encoded = read_regular_bytes(
                receipt,
                boundary=boundary,
                maximum_bytes=MAX_UPDATE_RECEIPT_BYTES,
            )
            payload = json.loads(encoded, object_pairs_hook=_strict_object)
            if not isinstance(payload, dict):
                raise DesktopUpdateError("Desktop update receipt must be one JSON object")
            _validate_staged_receipt(payload, candidate, artifact, self.trust.key_id)
            _verify_regular_artifact(target, artifact, boundary=boundary)
        except DesktopUpdateError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, LocalStoreError) as exc:
            raise DesktopUpdateError("Desktop update stage evidence is unreadable") from exc
        return StagedDesktopUpdate(
            candidate.manifest.release_id,
            candidate.manifest.version,
            candidate.manifest.channel,
            artifact.platform,
            target,
            receipt,
            artifact.sha256,
            artifact.size_bytes,
        )

    def _read_metadata(self, url: str) -> bytes:
        _validate_https_url(url)
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": f"ROMVERSE/{__version__}"},
        )
        try:
            with self._opener(request, timeout=15) as response:
                if response.geturl() != url:
                    raise DesktopUpdateError("Desktop update metadata redirected unexpectedly")
                _validate_content_length(response.headers, MAX_RELEASE_DOCUMENT_BYTES)
                encoded = response.read(MAX_RELEASE_DOCUMENT_BYTES + 1)
        except DesktopUpdateError:
            raise
        except (OSError, urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise DesktopUpdateError("Desktop update metadata is unavailable") from exc
        if not 2 <= len(encoded) <= MAX_RELEASE_DOCUMENT_BYTES:
            raise DesktopUpdateError("Desktop update metadata exceeds its size boundary")
        return encoded

    def _download_artifact(
        self,
        url: str,
        temporary: Path,
        artifact: DesktopReleaseArtifact,
        progress: DownloadProgress | None,
        should_cancel: Callable[[], bool] | None,
    ) -> None:
        _raise_if_update_cancelled(should_cancel)
        _validate_https_url(url)
        request = urllib.request.Request(url, headers={"User-Agent": f"ROMVERSE/{__version__}"})
        digest = hashlib.sha256()
        written = 0
        try:
            with self._opener(request, timeout=90) as response:
                if response.geturl() != url:
                    raise DesktopUpdateError("Desktop update artifact redirected unexpectedly")
                declared = _validate_content_length(response.headers, artifact.size_bytes)
                if declared not in {0, artifact.size_bytes}:
                    raise DesktopUpdateError(
                        "Desktop update server reported the wrong artifact size"
                    )
                flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(temporary, flags, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    if progress is not None:
                        progress(0, artifact.size_bytes)
                    while chunk := response.read(1024 * 1024):
                        _raise_if_update_cancelled(should_cancel)
                        written += len(chunk)
                        if written > artifact.size_bytes or written > MAX_RELEASE_ARTIFACT_BYTES:
                            raise DesktopUpdateError(
                                "Desktop update artifact exceeds its signed size"
                            )
                        digest.update(chunk)
                        stream.write(chunk)
                        if progress is not None:
                            progress(written, artifact.size_bytes)
                    _raise_if_update_cancelled(should_cancel)
                    stream.flush()
                    os.fsync(stream.fileno())
        except DesktopUpdateError:
            raise
        except (OSError, urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise DesktopUpdateError("Desktop update artifact download failed") from exc
        finally:
            if progress is not None:
                progress(0, 0)
        if written != artifact.size_bytes or digest.hexdigest() != artifact.sha256:
            raise DesktopUpdateError("Desktop update artifact failed signed size or SHA-256 checks")

    def _validate_candidate(self, candidate: DesktopUpdateCandidate) -> None:
        if (
            candidate != self._accepted_candidate
            or type(candidate.available) is not bool
            or not candidate.available
            or candidate.current_version != self.current_version
            or candidate.execution_authority != "none"
            or candidate.automatic_install is not False
            or candidate.requires_explicit_confirmation is not True
            or candidate.manifest.channel not in {"stable", "release-candidate"}
            or candidate.artifact is None
            or candidate.artifact.platform != self.platform
            or candidate.artifact not in candidate.manifest.artifacts
            or candidate.artifact_url
            != _sibling_url(candidate.manifest_url, candidate.artifact.file_name)
            or release_version_order(candidate.manifest.version)
            <= release_version_order(self.current_version)
        ):
            raise DesktopUpdateError("Desktop update candidate is stale or invalid")


def _validate_staged_receipt(
    payload: dict[str, Any],
    candidate: DesktopUpdateCandidate,
    artifact: DesktopReleaseArtifact,
    key_id: str,
) -> None:
    expected: dict[str, object] = {
        "format": "romverse.desktop-update-stage",
        "schema_version": 1,
        "release_id": candidate.manifest.release_id,
        "version": candidate.manifest.version,
        "channel": candidate.manifest.channel,
        "platform": artifact.platform,
        "artifact_file": artifact.file_name,
        "artifact_sha256": artifact.sha256,
        "artifact_size_bytes": artifact.size_bytes,
        "manifest_sha256": candidate.manifest_sha256,
        "key_id": key_id,
        "workspace_preserved": True,
        "requires_explicit_confirmation": True,
        "automatic_install": False,
        "execution_authority": "none",
    }
    if set(payload) != set(expected) | {"staged_at", "receipt_sha256"}:
        raise DesktopUpdateError("Desktop update receipt fields do not match schema 1")
    for field, expected_value in expected.items():
        value = payload[field]
        if type(value) is not type(expected_value) or value != expected_value:
            raise DesktopUpdateError(f"Desktop update receipt {field} is invalid")
    staged_at = payload["staged_at"]
    receipt_digest = payload["receipt_sha256"]
    if (
        not isinstance(staged_at, str)
        or not 1 <= len(staged_at) <= 64
        or not isinstance(receipt_digest, str)
        or len(receipt_digest) != 64
        or any(character not in "0123456789abcdef" for character in receipt_digest)
    ):
        raise DesktopUpdateError("Desktop update receipt timestamp or digest is invalid")
    try:
        parsed = datetime.fromisoformat(staged_at)
    except ValueError as exc:
        raise DesktopUpdateError("Desktop update receipt timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DesktopUpdateError("Desktop update receipt timestamp must include its timezone")
    digest_payload = dict(payload)
    del digest_payload["receipt_sha256"]
    if receipt_digest != _payload_digest(digest_payload):
        raise DesktopUpdateError("Desktop update receipt digest does not match")


def _raise_if_update_cancelled(should_cancel: Callable[[], bool] | None) -> None:
    if should_cancel is not None and should_cancel():
        raise DesktopUpdateCancelled("Desktop update download was cancelled")


def _validate_https_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise DesktopUpdateError("Desktop update URL is invalid") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or port not in {None, 443}
        or parsed.fragment
        or not parsed.path
    ):
        raise DesktopUpdateError("Desktop update URL must use a direct trusted HTTPS endpoint")
    return url


def _sibling_url(manifest_url: str, file_name: str) -> str:
    parsed = urllib.parse.urlsplit(_validate_https_url(manifest_url))
    directory = parsed.path.rsplit("/", 1)[0]
    encoded_name = urllib.parse.quote(file_name, safe=".+-")
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, f"{directory}/{encoded_name}", "", "")
    )


def _validate_content_length(headers: object, maximum: int) -> int:
    raw = headers.get("Content-Length", "") if hasattr(headers, "get") else ""
    if not raw:
        return 0
    try:
        length = int(raw)
    except (TypeError, ValueError) as exc:
        raise DesktopUpdateError("Desktop update Content-Length is invalid") from exc
    if length < 1 or length > maximum:
        raise DesktopUpdateError("Desktop update Content-Length exceeds its boundary")
    return length


def _verify_regular_artifact(
    path: Path,
    artifact: DesktopReleaseArtifact,
    *,
    boundary: Path,
) -> None:
    digest, size_bytes = sha256_regular_file(
        path,
        boundary=boundary,
        maximum_bytes=MAX_RELEASE_ARTIFACT_BYTES,
    )
    if size_bytes != artifact.size_bytes or digest != artifact.sha256:
        raise DesktopUpdateError("Existing staged update failed signed size or SHA-256 checks")


def _payload_digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
