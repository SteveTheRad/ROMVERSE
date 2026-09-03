from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

RELEASE_SCHEMA_VERSION = 1
RELEASE_PRODUCT = "ROMVERSE Desktop"
MAX_RELEASE_DOCUMENT_BYTES = 1_048_576
MAX_RELEASE_ARTIFACT_BYTES = 68_719_476_736
RELEASE_CHANNELS = frozenset({"development", "release-candidate", "stable"})
RELEASE_PLATFORMS = frozenset({"python-any", "linux-x86_64", "windows-x86_64"})
RELEASE_ARTIFACT_KINDS = frozenset({"wheel", "archive", "installer"})

_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?")
_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}")
_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,159}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class ReleaseValidationError(ValueError):
    """A desktop release document or artifact failed a trust boundary."""


@dataclass(frozen=True)
class DesktopReleaseArtifact:
    artifact_id: str
    platform: str
    kind: str
    file_name: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class DesktopRollbackPolicy:
    available: bool
    target_version: str
    artifact_id: str
    reason: str


@dataclass(frozen=True)
class DesktopReleaseManifest:
    version: str
    channel: str
    release_id: str
    published_at: str
    artifacts: tuple[DesktopReleaseArtifact, ...]
    rollback: DesktopRollbackPolicy


@dataclass(frozen=True)
class VerifiedDesktopRelease:
    manifest: DesktopReleaseManifest
    key_id: str
    manifest_sha256: str
    artifact_count: int
    artifact_bytes: int


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseValidationError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def load_release_json(path: Path) -> dict[str, Any]:
    resolved = path.expanduser()
    try:
        details = resolved.lstat()
    except OSError as exc:
        raise ReleaseValidationError("Release document is unavailable") from exc
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise ReleaseValidationError("Release document must be one regular file, not a link")
    if details.st_size < 2 or details.st_size > MAX_RELEASE_DOCUMENT_BYTES:
        raise ReleaseValidationError("Release document size is outside the safe limit")
    try:
        value = json.loads(resolved.read_bytes(), object_pairs_hook=_strict_object)
    except ReleaseValidationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseValidationError("Release document is not valid bounded JSON") from exc
    if not isinstance(value, dict):
        raise ReleaseValidationError("Release document must be one JSON object")
    return value


def canonical_release_bytes(manifest: dict[str, Any]) -> bytes:
    return json.dumps(
        manifest,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _require_exact_fields(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ReleaseValidationError(f"{label} fields do not match schema {RELEASE_SCHEMA_VERSION}")


def _bounded_string(value: Any, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ReleaseValidationError(f"{label} is invalid")
    return value


def _valid_timestamp(value: Any) -> str:
    timestamp = _bounded_string(value, "Release timestamp", 40)
    if not timestamp.endswith("Z"):
        raise ReleaseValidationError("Release timestamp must be UTC")
    try:
        parsed = datetime.fromisoformat(timestamp[:-1] + "+00:00")
    except ValueError as exc:
        raise ReleaseValidationError("Release timestamp is invalid") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ReleaseValidationError("Release timestamp must be UTC")
    return timestamp


def _valid_version(value: Any, label: str = "Release version") -> str:
    version = _bounded_string(value, label, 64)
    if _VERSION.fullmatch(version) is None:
        raise ReleaseValidationError(f"{label} is invalid")
    return version


def _version_order(version: str) -> tuple[int, int, int, int, str]:
    core, separator, prerelease = version.partition("-")
    major, minor, patch = (int(part) for part in core.split("."))
    return major, minor, patch, 0 if separator else 1, prerelease


def validate_release_manifest(value: dict[str, Any]) -> DesktopReleaseManifest:
    _require_exact_fields(
        value,
        {
            "schema_version",
            "product",
            "version",
            "channel",
            "release_id",
            "published_at",
            "artifacts",
            "update_policy",
            "rollback",
        },
        "Release manifest",
    )
    if value["schema_version"] != RELEASE_SCHEMA_VERSION or isinstance(
        value["schema_version"], bool
    ):
        raise ReleaseValidationError("Release manifest schema is unsupported")
    if value["product"] != RELEASE_PRODUCT:
        raise ReleaseValidationError("Release product identity is invalid")
    version = _valid_version(value["version"])
    channel = _bounded_string(value["channel"], "Release channel", 32)
    if channel not in RELEASE_CHANNELS:
        raise ReleaseValidationError("Release channel is unsupported")
    release_id = _bounded_string(value["release_id"], "Release identity", 96)
    if _IDENTIFIER.fullmatch(release_id) is None:
        raise ReleaseValidationError("Release identity is invalid")
    published_at = _valid_timestamp(value["published_at"])

    raw_artifacts = value["artifacts"]
    if not isinstance(raw_artifacts, list) or not 1 <= len(raw_artifacts) <= 16:
        raise ReleaseValidationError("Release must contain one to sixteen artifacts")
    artifacts: list[DesktopReleaseArtifact] = []
    seen_ids: set[str] = set()
    seen_files: set[str] = set()
    for raw in raw_artifacts:
        if not isinstance(raw, dict):
            raise ReleaseValidationError("Release artifact entry is invalid")
        _require_exact_fields(
            raw,
            {"artifact_id", "platform", "kind", "file_name", "sha256", "size_bytes"},
            "Release artifact",
        )
        artifact_id = _bounded_string(raw["artifact_id"], "Artifact identity", 96)
        platform = _bounded_string(raw["platform"], "Artifact platform", 32)
        kind = _bounded_string(raw["kind"], "Artifact kind", 24)
        file_name = _bounded_string(raw["file_name"], "Artifact filename", 160)
        digest = _bounded_string(raw["sha256"], "Artifact SHA-256", 64)
        size_bytes = raw["size_bytes"]
        if _IDENTIFIER.fullmatch(artifact_id) is None or artifact_id in seen_ids:
            raise ReleaseValidationError("Artifact identity is invalid or duplicated")
        if platform not in RELEASE_PLATFORMS:
            raise ReleaseValidationError("Artifact platform is unsupported")
        if kind not in RELEASE_ARTIFACT_KINDS:
            raise ReleaseValidationError("Artifact kind is unsupported")
        if (
            _FILENAME.fullmatch(file_name) is None
            or "/" in file_name
            or "\\" in file_name
            or file_name in {".", ".."}
            or file_name in seen_files
        ):
            raise ReleaseValidationError("Artifact filename is unsafe or duplicated")
        if _SHA256.fullmatch(digest) is None:
            raise ReleaseValidationError("Artifact SHA-256 is invalid")
        if (
            not isinstance(size_bytes, int)
            or isinstance(size_bytes, bool)
            or not 1 <= size_bytes <= MAX_RELEASE_ARTIFACT_BYTES
        ):
            raise ReleaseValidationError("Artifact size is invalid")
        seen_ids.add(artifact_id)
        seen_files.add(file_name)
        artifacts.append(
            DesktopReleaseArtifact(
                artifact_id,
                platform,
                kind,
                file_name,
                digest,
                size_bytes,
            )
        )

    update_policy = value["update_policy"]
    if not isinstance(update_policy, dict):
        raise ReleaseValidationError("Update policy is invalid")
    _require_exact_fields(
        update_policy,
        {
            "automatic_install",
            "requires_explicit_confirmation",
            "preserve_workspace",
            "execution_authority",
        },
        "Update policy",
    )
    if (
        update_policy["automatic_install"] is not False
        or update_policy["requires_explicit_confirmation"] is not True
        or update_policy["preserve_workspace"] is not True
        or update_policy["execution_authority"] != "none"
    ):
        raise ReleaseValidationError("Update policy violates the ROMVERSE safety boundary")

    raw_rollback = value["rollback"]
    if not isinstance(raw_rollback, dict):
        raise ReleaseValidationError("Rollback policy is invalid")
    _require_exact_fields(
        raw_rollback,
        {"available", "target_version", "artifact_id", "reason"},
        "Rollback policy",
    )
    available = raw_rollback["available"]
    target_version = raw_rollback["target_version"]
    rollback_artifact_id = raw_rollback["artifact_id"]
    reason = _bounded_string(raw_rollback["reason"], "Rollback reason", 500)
    if (
        not isinstance(available, bool)
        or not isinstance(target_version, str)
        or not isinstance(rollback_artifact_id, str)
    ):
        raise ReleaseValidationError("Rollback policy values are invalid")
    if available:
        target_version = _valid_version(target_version, "Rollback version")
        if (
            _version_order(target_version) >= _version_order(version)
            or rollback_artifact_id not in seen_ids
        ):
            raise ReleaseValidationError("Rollback target is not an eligible release artifact")
    elif target_version or rollback_artifact_id:
        raise ReleaseValidationError("Unavailable rollback cannot name a target")

    return DesktopReleaseManifest(
        version,
        channel,
        release_id,
        published_at,
        tuple(artifacts),
        DesktopRollbackPolicy(available, target_version, rollback_artifact_id, reason),
    )


def _hash_file(path: Path) -> tuple[str, int]:
    try:
        details = path.lstat()
    except OSError as exc:
        raise ReleaseValidationError(f"Release artifact is unavailable: {path.name}") from exc
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise ReleaseValidationError(f"Release artifact must be a regular file: {path.name}")
    if not 1 <= details.st_size <= MAX_RELEASE_ARTIFACT_BYTES:
        raise ReleaseValidationError(f"Release artifact size is invalid: {path.name}")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ReleaseValidationError(f"Release artifact cannot be read: {path.name}") from exc
    return digest.hexdigest(), details.st_size


def build_release_manifest(
    *,
    version: str,
    channel: str,
    release_id: str,
    published_at: str,
    artifacts: Iterable[tuple[str, str, str, Path]],
    rollback_version: str = "",
    rollback_artifact_id: str = "",
    rollback_reason: str = "No previously signed public ROMVERSE Desktop release is available.",
) -> dict[str, Any]:
    artifact_documents: list[dict[str, Any]] = []
    for artifact_id, platform, kind, supplied_path in artifacts:
        path = supplied_path.expanduser().resolve()
        digest, size_bytes = _hash_file(path)
        artifact_documents.append(
            {
                "artifact_id": artifact_id,
                "platform": platform,
                "kind": kind,
                "file_name": path.name,
                "sha256": digest,
                "size_bytes": size_bytes,
            }
        )
    rollback_available = bool(rollback_version or rollback_artifact_id)
    if rollback_available and not (rollback_version and rollback_artifact_id):
        raise ReleaseValidationError(
            "Rollback version and artifact identity must be supplied together"
        )
    manifest: dict[str, Any] = {
        "schema_version": RELEASE_SCHEMA_VERSION,
        "product": RELEASE_PRODUCT,
        "version": version,
        "channel": channel,
        "release_id": release_id,
        "published_at": published_at,
        "artifacts": artifact_documents,
        "update_policy": {
            "automatic_install": False,
            "requires_explicit_confirmation": True,
            "preserve_workspace": True,
            "execution_authority": "none",
        },
        "rollback": {
            "available": rollback_available,
            "target_version": rollback_version,
            "artifact_id": rollback_artifact_id,
            "reason": rollback_reason,
        },
    }
    validate_release_manifest(manifest)
    return manifest


def create_signed_release_envelope(
    manifest: dict[str, Any], private_key: Ed25519PrivateKey, key_id: str
) -> dict[str, Any]:
    validate_release_manifest(manifest)
    if _IDENTIFIER.fullmatch(key_id) is None:
        raise ReleaseValidationError("Release signing-key identity is invalid")
    encoded = canonical_release_bytes(manifest)
    return {
        "schema_version": RELEASE_SCHEMA_VERSION,
        "algorithm": "ed25519",
        "key_id": key_id,
        "manifest_sha256": hashlib.sha256(encoded).hexdigest(),
        "manifest": manifest,
        "signature": base64.b64encode(private_key.sign(encoded)).decode("ascii"),
    }


def verify_signed_release_envelope(
    envelope: dict[str, Any], public_key: Ed25519PublicKey, expected_key_id: str
) -> tuple[DesktopReleaseManifest, str]:
    _require_exact_fields(
        envelope,
        {"schema_version", "algorithm", "key_id", "manifest_sha256", "manifest", "signature"},
        "Signed release envelope",
    )
    if envelope["schema_version"] != RELEASE_SCHEMA_VERSION or isinstance(
        envelope["schema_version"], bool
    ):
        raise ReleaseValidationError("Signed release schema is unsupported")
    if envelope["algorithm"] != "ed25519" or envelope["key_id"] != expected_key_id:
        raise ReleaseValidationError("Release signing identity is not trusted")
    if _IDENTIFIER.fullmatch(expected_key_id) is None:
        raise ReleaseValidationError("Expected release signing-key identity is invalid")
    raw_manifest = envelope["manifest"]
    if not isinstance(raw_manifest, dict):
        raise ReleaseValidationError("Signed release manifest is invalid")
    manifest = validate_release_manifest(raw_manifest)
    encoded = canonical_release_bytes(raw_manifest)
    digest = hashlib.sha256(encoded).hexdigest()
    if envelope["manifest_sha256"] != digest:
        raise ReleaseValidationError("Signed release manifest digest does not match")
    signature_value = envelope["signature"]
    if not isinstance(signature_value, str) or len(signature_value) > 128:
        raise ReleaseValidationError("Release signature is malformed")
    try:
        signature = base64.b64decode(signature_value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ReleaseValidationError("Release signature is malformed") from exc
    if len(signature) != 64:
        raise ReleaseValidationError("Release signature has an invalid length")
    try:
        public_key.verify(signature, encoded)
    except InvalidSignature as exc:
        raise ReleaseValidationError("Release signature verification failed") from exc
    return manifest, digest


def verify_release_artifacts(
    manifest: DesktopReleaseManifest, artifact_directory: Path
) -> tuple[int, int]:
    root = artifact_directory.expanduser()
    try:
        root_details = root.lstat()
    except OSError as exc:
        raise ReleaseValidationError("Release artifact directory is unavailable") from exc
    if stat.S_ISLNK(root_details.st_mode) or not stat.S_ISDIR(root_details.st_mode):
        raise ReleaseValidationError("Release artifact directory must not be a link")
    total_bytes = 0
    for artifact in manifest.artifacts:
        digest, size_bytes = _hash_file(root / artifact.file_name)
        if digest != artifact.sha256 or size_bytes != artifact.size_bytes:
            raise ReleaseValidationError(
                f"Release artifact failed size or SHA-256 verification: {artifact.file_name}"
            )
        total_bytes += size_bytes
    return len(manifest.artifacts), total_bytes


def verify_release_bundle(
    *,
    envelope: dict[str, Any],
    public_key: Ed25519PublicKey,
    expected_key_id: str,
    artifact_directory: Path,
) -> VerifiedDesktopRelease:
    manifest, manifest_digest = verify_signed_release_envelope(
        envelope, public_key, expected_key_id
    )
    artifact_count, artifact_bytes = verify_release_artifacts(manifest, artifact_directory)
    return VerifiedDesktopRelease(
        manifest,
        expected_key_id,
        manifest_digest,
        artifact_count,
        artifact_bytes,
    )


def write_release_json(path: Path, value: dict[str, Any]) -> None:
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ReleaseValidationError("Release output must not replace a link")
    payload = json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True).encode("ascii") + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o644)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
