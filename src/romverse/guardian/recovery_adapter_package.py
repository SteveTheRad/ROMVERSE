from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import platform as host_platform
import re
import stat
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from romverse.guardian.invariants import contains_bootloader_lock_action_id
from romverse.release import ReleaseValidationError, load_release_json, write_release_json
from romverse.rom.models import ProjectError

RECOVERY_ADAPTER_PACKAGE_FORMAT = "romverse.guardian-recovery-adapter-package"
RECOVERY_ADAPTER_PACKAGE_PRODUCT = "ROMVERSE Guardian Recovery Adapter"
RECOVERY_ADAPTER_PACKAGE_SCHEMA_VERSION = 1
RECOVERY_ADAPTER_PROTOCOL_VERSION = 1
RECOVERY_ADAPTER_REQUEST_SCHEMA_VERSION = 1
RECOVERY_ADAPTER_RESULT_SCHEMA_VERSION = 1
RECOVERY_ADAPTER_PACKAGE_DOMAIN = b"ROMVERSE-GUARDIAN-RECOVERY-ADAPTER-PACKAGE-V1\0"
MAX_RECOVERY_ADAPTER_BYTES = 512 * 1024 * 1024
RECOVERY_ADAPTER_PLATFORMS = frozenset({"linux-x86_64", "windows-x86_64"})

_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?")
_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,159}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class RecoveryAdapterPackageValidationError(ProjectError):
    """A Recovery adapter package failed its release trust boundary."""


class RecoveryAdapterTrustScope(StrEnum):
    RADFORGE_PRODUCTION = "radforge-production"
    TEST_ONLY = "test-only"


@dataclass(frozen=True, slots=True)
class GuardianRecoveryAdapterReleaseTrustRoot:
    """Pinned public release identity; private signing material never belongs here."""

    key_id: str
    public_key_sha256: str
    scope: RecoveryAdapterTrustScope
    _public_key: Ed25519PublicKey = field(repr=False, compare=False)

    @classmethod
    def from_public_key(
        cls,
        *,
        key_id: str,
        public_key: Ed25519PublicKey,
        scope: RecoveryAdapterTrustScope,
    ) -> GuardianRecoveryAdapterReleaseTrustRoot:
        if not isinstance(public_key, Ed25519PublicKey):
            raise RecoveryAdapterPackageValidationError(
                "Recovery adapter release trust must use an Ed25519 public key"
            )
        key_id = _identifier(key_id, "Recovery adapter release key identity")
        if not isinstance(scope, RecoveryAdapterTrustScope):
            raise RecoveryAdapterPackageValidationError(
                "Recovery adapter release trust scope is invalid"
            )
        if scope is RecoveryAdapterTrustScope.RADFORGE_PRODUCTION:
            if not key_id.startswith("radforge."):
                raise RecoveryAdapterPackageValidationError(
                    "Production Recovery adapter trust must use a RadForge release identity"
                )
        elif not key_id.startswith("test."):
            raise RecoveryAdapterPackageValidationError(
                "Recovery adapter test trust must remain explicitly test-only"
            )
        raw = public_key.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        return cls(key_id, hashlib.sha256(raw).hexdigest(), scope, public_key)

    @property
    def public_key(self) -> Ed25519PublicKey:
        return self._public_key


@dataclass(frozen=True, slots=True)
class GuardianRecoveryAdapterArtifact:
    file_name: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class GuardianRecoveryAdapterSafetyPolicy:
    exact_target_required: bool
    one_action_per_invocation: bool
    confirmed_recovery_only: bool
    request_digest_required: bool
    source_digest_required: bool
    structured_result_required: bool
    raw_output_success_allowed: bool
    arbitrary_command_allowed: bool
    environment_overrides_allowed: bool
    automatic_retry_allowed: bool
    bootloader_unlock_allowed: bool
    bootloader_relock_allowed: bool
    execution_authority: str


@dataclass(frozen=True, slots=True)
class GuardianRecoveryAdapterPackageManifest:
    package_id: str
    package_version: str
    created_at: str
    platform: str
    protocol_version: int
    request_schema_version: int
    result_schema_version: int
    adapter_id: str
    adapter_version: int
    supported_action_ids: tuple[str, ...]
    artifact: GuardianRecoveryAdapterArtifact
    safety_policy: GuardianRecoveryAdapterSafetyPolicy


@dataclass(frozen=True, slots=True)
class VerifiedGuardianRecoveryAdapterPackage:
    """Release-authenticated identity whose exact executable is rehashed locally."""

    manifest: GuardianRecoveryAdapterPackageManifest
    release_key_id: str
    release_public_key_sha256: str
    release_trust_scope: RecoveryAdapterTrustScope
    manifest_sha256: str
    package_sha256: str
    artifact_path: Path
    _trust_root: GuardianRecoveryAdapterReleaseTrustRoot = field(
        repr=False,
        compare=False,
    )
    _envelope: dict[str, Any] = field(repr=False, compare=False)


def current_recovery_adapter_platform() -> str:
    machine = host_platform.machine().casefold().replace("-", "_")
    if machine not in {"x86_64", "amd64"}:
        raise RecoveryAdapterPackageValidationError(
            "This host architecture has no Recovery adapter package target"
        )
    return "windows-x86_64" if os.name == "nt" else "linux-x86_64"


def build_guardian_recovery_adapter_manifest(
    *,
    package_id: str,
    package_version: str,
    created_at: str,
    platform: str,
    artifact_path: Path,
    adapter_id: str,
    adapter_version: int,
    supported_action_ids: tuple[str, ...],
) -> dict[str, Any]:
    """Build the canonical unsigned manifest; this grants no runtime authority."""

    digest, size, mode = _hash_regular_artifact(artifact_path)
    manifest: dict[str, Any] = {
        "schema_version": RECOVERY_ADAPTER_PACKAGE_SCHEMA_VERSION,
        "product": RECOVERY_ADAPTER_PACKAGE_PRODUCT,
        "package_id": package_id,
        "package_version": package_version,
        "created_at": created_at,
        "platform": platform,
        "protocol_version": RECOVERY_ADAPTER_PROTOCOL_VERSION,
        "request_schema_version": RECOVERY_ADAPTER_REQUEST_SCHEMA_VERSION,
        "result_schema_version": RECOVERY_ADAPTER_RESULT_SCHEMA_VERSION,
        "adapter_id": adapter_id,
        "adapter_version": adapter_version,
        "supported_action_ids": list(supported_action_ids),
        "artifact": {
            "file_name": artifact_path.name,
            "size_bytes": size,
            "sha256": digest,
        },
        "safety_policy": {
            "exact_target_required": True,
            "one_action_per_invocation": True,
            "confirmed_recovery_only": True,
            "request_digest_required": True,
            "source_digest_required": True,
            "structured_result_required": True,
            "raw_output_success_allowed": False,
            "arbitrary_command_allowed": False,
            "environment_overrides_allowed": False,
            "automatic_retry_allowed": False,
            "bootloader_unlock_allowed": False,
            "bootloader_relock_allowed": False,
            "execution_authority": "sealed-recovery-action-only",
        },
    }
    parsed = validate_guardian_recovery_adapter_manifest(manifest)
    _validate_platform_artifact(artifact_path, parsed.platform, mode)
    return manifest


def validate_guardian_recovery_adapter_manifest(
    value: dict[str, Any],
) -> GuardianRecoveryAdapterPackageManifest:
    if not isinstance(value, dict):
        raise RecoveryAdapterPackageValidationError("Recovery adapter manifest must be one object")
    _exact_fields(
        value,
        {
            "schema_version",
            "product",
            "package_id",
            "package_version",
            "created_at",
            "platform",
            "protocol_version",
            "request_schema_version",
            "result_schema_version",
            "adapter_id",
            "adapter_version",
            "supported_action_ids",
            "artifact",
            "safety_policy",
        },
        "Recovery adapter manifest",
    )
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != RECOVERY_ADAPTER_PACKAGE_SCHEMA_VERSION
        or value["product"] != RECOVERY_ADAPTER_PACKAGE_PRODUCT
    ):
        raise RecoveryAdapterPackageValidationError(
            "Recovery adapter package schema or product is unsupported"
        )
    package_id = _identifier(value["package_id"], "Recovery adapter package identity")
    package_version = _version(value["package_version"])
    created_at = _utc_timestamp(value["created_at"])
    platform = _text(value["platform"], "Recovery adapter platform", 32)
    if platform not in RECOVERY_ADAPTER_PLATFORMS:
        raise RecoveryAdapterPackageValidationError("Recovery adapter platform is unsupported")
    if (
        type(value["protocol_version"]) is not int
        or value["protocol_version"] != RECOVERY_ADAPTER_PROTOCOL_VERSION
        or type(value["request_schema_version"]) is not int
        or value["request_schema_version"] != RECOVERY_ADAPTER_REQUEST_SCHEMA_VERSION
        or type(value["result_schema_version"]) is not int
        or value["result_schema_version"] != RECOVERY_ADAPTER_RESULT_SCHEMA_VERSION
    ):
        raise RecoveryAdapterPackageValidationError(
            "Recovery adapter protocol or schema is unsupported"
        )
    adapter_id = _identifier(value["adapter_id"], "Recovery adapter identity")
    adapter_version = value["adapter_version"]
    if type(adapter_version) is not int or not 1 <= adapter_version <= 1_000_000:
        raise RecoveryAdapterPackageValidationError("Recovery adapter version is invalid")
    actions = value["supported_action_ids"]
    if (
        not isinstance(actions, list)
        or not 1 <= len(actions) <= 64
        or any(not isinstance(item, str) for item in actions)
    ):
        raise RecoveryAdapterPackageValidationError("Recovery adapter action allowlist is invalid")
    action_ids = tuple(_identifier(item, "Recovery adapter action identity") for item in actions)
    if (
        len(set(action_ids)) != len(action_ids)
        or any(not item.startswith(f"{adapter_id}.") for item in action_ids)
        or any(contains_bootloader_lock_action_id(item) for item in action_ids)
    ):
        raise RecoveryAdapterPackageValidationError(
            "Recovery adapter action allowlist contains an unexpected or locking action"
        )

    artifact = value["artifact"]
    if not isinstance(artifact, dict):
        raise RecoveryAdapterPackageValidationError("Recovery adapter artifact is invalid")
    _exact_fields(artifact, {"file_name", "size_bytes", "sha256"}, "Recovery adapter artifact")
    file_name = _safe_filename(artifact["file_name"])
    size_bytes = artifact["size_bytes"]
    artifact_sha256 = _sha256(artifact["sha256"], "Recovery adapter artifact SHA-256")
    if type(size_bytes) is not int or not 1 <= size_bytes <= MAX_RECOVERY_ADAPTER_BYTES:
        raise RecoveryAdapterPackageValidationError("Recovery adapter artifact size is invalid")

    policy = value["safety_policy"]
    if not isinstance(policy, dict):
        raise RecoveryAdapterPackageValidationError("Recovery adapter safety policy is invalid")
    _exact_fields(
        policy,
        {
            "exact_target_required",
            "one_action_per_invocation",
            "confirmed_recovery_only",
            "request_digest_required",
            "source_digest_required",
            "structured_result_required",
            "raw_output_success_allowed",
            "arbitrary_command_allowed",
            "environment_overrides_allowed",
            "automatic_retry_allowed",
            "bootloader_unlock_allowed",
            "bootloader_relock_allowed",
            "execution_authority",
        },
        "Recovery adapter safety policy",
    )
    if (
        policy["exact_target_required"] is not True
        or policy["one_action_per_invocation"] is not True
        or policy["confirmed_recovery_only"] is not True
        or policy["request_digest_required"] is not True
        or policy["source_digest_required"] is not True
        or policy["structured_result_required"] is not True
        or policy["raw_output_success_allowed"] is not False
        or policy["arbitrary_command_allowed"] is not False
        or policy["environment_overrides_allowed"] is not False
        or policy["automatic_retry_allowed"] is not False
        or policy["bootloader_unlock_allowed"] is not False
        or policy["bootloader_relock_allowed"] is not False
        or policy["execution_authority"] != "sealed-recovery-action-only"
    ):
        raise RecoveryAdapterPackageValidationError(
            "Recovery adapter package violates its safety boundary"
        )
    return GuardianRecoveryAdapterPackageManifest(
        package_id,
        package_version,
        created_at,
        platform,
        value["protocol_version"],
        value["request_schema_version"],
        value["result_schema_version"],
        adapter_id,
        adapter_version,
        action_ids,
        GuardianRecoveryAdapterArtifact(file_name, size_bytes, artifact_sha256),
        GuardianRecoveryAdapterSafetyPolicy(
            True,
            True,
            True,
            True,
            True,
            True,
            False,
            False,
            False,
            False,
            False,
            False,
            "sealed-recovery-action-only",
        ),
    )


def create_signed_guardian_recovery_adapter_package(
    manifest: dict[str, Any],
    release_private_key: Ed25519PrivateKey,
    release_key_id: str,
) -> dict[str, Any]:
    validate_guardian_recovery_adapter_manifest(manifest)
    if not isinstance(release_private_key, Ed25519PrivateKey):
        raise RecoveryAdapterPackageValidationError(
            "Recovery adapter package release key must use Ed25519"
        )
    key_id = _identifier(release_key_id, "Recovery adapter release key identity")
    encoded = _canonical_bytes(manifest)
    return {
        "format": RECOVERY_ADAPTER_PACKAGE_FORMAT,
        "schema_version": RECOVERY_ADAPTER_PACKAGE_SCHEMA_VERSION,
        "algorithm": "ed25519",
        "key_id": key_id,
        "manifest_sha256": hashlib.sha256(encoded).hexdigest(),
        "manifest": manifest,
        "signature": base64.b64encode(
            release_private_key.sign(RECOVERY_ADAPTER_PACKAGE_DOMAIN + encoded)
        ).decode("ascii"),
    }


def verify_guardian_recovery_adapter_package(
    *,
    envelope: dict[str, Any],
    trust_root: GuardianRecoveryAdapterReleaseTrustRoot,
    package_directory: Path,
    expected_platform: str,
) -> VerifiedGuardianRecoveryAdapterPackage:
    """Verify release signature, exact identity, platform and local executable bytes."""

    try:
        _validate_trust_root(trust_root)
        _exact_fields(
            envelope,
            {
                "format",
                "schema_version",
                "algorithm",
                "key_id",
                "manifest_sha256",
                "manifest",
                "signature",
            },
            "Signed Recovery adapter package",
        )
        if (
            envelope["format"] != RECOVERY_ADAPTER_PACKAGE_FORMAT
            or type(envelope["schema_version"]) is not int
            or envelope["schema_version"] != RECOVERY_ADAPTER_PACKAGE_SCHEMA_VERSION
            or envelope["algorithm"] != "ed25519"
            or envelope["key_id"] != trust_root.key_id
        ):
            raise RecoveryAdapterPackageValidationError(
                "Recovery adapter package release identity is not trusted"
            )
        manifest = validate_guardian_recovery_adapter_manifest(envelope["manifest"])
        if manifest.platform != expected_platform:
            raise RecoveryAdapterPackageValidationError(
                "Recovery adapter package platform does not match this host"
            )
        encoded = _canonical_bytes(envelope["manifest"])
        manifest_sha256 = hashlib.sha256(encoded).hexdigest()
        if envelope["manifest_sha256"] != manifest_sha256:
            raise RecoveryAdapterPackageValidationError(
                "Recovery adapter manifest digest does not match"
            )
        try:
            trust_root.public_key.verify(
                _signature(envelope["signature"]),
                RECOVERY_ADAPTER_PACKAGE_DOMAIN + encoded,
            )
        except InvalidSignature as exc:
            raise RecoveryAdapterPackageValidationError(
                "Recovery adapter package release signature verification failed"
            ) from exc

        root = package_directory.expanduser()
        details = root.lstat()
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
            raise RecoveryAdapterPackageValidationError(
                "Recovery adapter package directory must be one real directory"
            )
        artifact_path = root / manifest.artifact.file_name
        digest, size, mode = _hash_regular_artifact(artifact_path)
        _validate_platform_artifact(artifact_path, manifest.platform, mode)
        if digest != manifest.artifact.sha256 or size != manifest.artifact.size_bytes:
            raise RecoveryAdapterPackageValidationError(
                "Recovery adapter executable failed exact size or SHA-256 verification"
            )
        return VerifiedGuardianRecoveryAdapterPackage(
            manifest,
            trust_root.key_id,
            trust_root.public_key_sha256,
            trust_root.scope,
            manifest_sha256,
            hashlib.sha256(_canonical_bytes(envelope)).hexdigest(),
            artifact_path.resolve(strict=True),
            trust_root,
            json.loads(json.dumps(envelope)),
        )
    except RecoveryAdapterPackageValidationError:
        raise
    except (AttributeError, OSError, TypeError, ValueError, KeyError) as exc:
        raise RecoveryAdapterPackageValidationError(
            "Recovery adapter package verification failed closed"
        ) from exc


def resolve_radforge_production_recovery_adapter_package(
    *,
    envelope: dict[str, Any],
    trust_root: GuardianRecoveryAdapterReleaseTrustRoot,
    package_directory: Path,
    expected_platform: str,
) -> VerifiedGuardianRecoveryAdapterPackage:
    """Production resolver that can never accept development or test release trust."""

    _validate_trust_root(trust_root)
    if trust_root.scope is not RecoveryAdapterTrustScope.RADFORGE_PRODUCTION:
        raise RecoveryAdapterPackageValidationError(
            "Production Recovery adapter resolution requires RadForge release trust"
        )
    return verify_guardian_recovery_adapter_package(
        envelope=envelope,
        trust_root=trust_root,
        package_directory=package_directory,
        expected_platform=expected_platform,
    )


def revalidate_verified_guardian_recovery_adapter_package(
    package: VerifiedGuardianRecoveryAdapterPackage,
) -> VerifiedGuardianRecoveryAdapterPackage:
    """Recheck signature and bytes; the launcher additionally pins the bytes it executes."""

    if not isinstance(package, VerifiedGuardianRecoveryAdapterPackage):
        raise RecoveryAdapterPackageValidationError(
            "Recovery adapter package has not crossed the trusted verifier boundary"
        )
    current = verify_guardian_recovery_adapter_package(
        envelope=package._envelope,
        trust_root=package._trust_root,
        package_directory=package.artifact_path.parent,
        expected_platform=package.manifest.platform,
    )
    if (
        current.manifest != package.manifest
        or current.release_key_id != package.release_key_id
        or current.release_public_key_sha256 != package.release_public_key_sha256
        or current.release_trust_scope is not package.release_trust_scope
        or current.manifest_sha256 != package.manifest_sha256
        or current.package_sha256 != package.package_sha256
        or current.artifact_path != package.artifact_path
    ):
        raise RecoveryAdapterPackageValidationError(
            "Recovery adapter verified identity changed before use"
        )
    return current


def load_guardian_recovery_adapter_package(path: Path) -> dict[str, Any]:
    try:
        return load_release_json(path)
    except ReleaseValidationError as exc:
        raise RecoveryAdapterPackageValidationError(
            "Recovery adapter package document is invalid"
        ) from exc


def write_guardian_recovery_adapter_package(path: Path, value: dict[str, Any]) -> None:
    try:
        write_release_json(path, value)
    except ReleaseValidationError as exc:
        raise RecoveryAdapterPackageValidationError(
            "Recovery adapter package document could not be written"
        ) from exc


def _validate_trust_root(root: GuardianRecoveryAdapterReleaseTrustRoot) -> None:
    if not isinstance(root, GuardianRecoveryAdapterReleaseTrustRoot):
        raise RecoveryAdapterPackageValidationError(
            "Recovery adapter release trust root is missing"
        )
    expected = GuardianRecoveryAdapterReleaseTrustRoot.from_public_key(
        key_id=root.key_id,
        public_key=root.public_key,
        scope=root.scope,
    )
    if expected.public_key_sha256 != root.public_key_sha256:
        raise RecoveryAdapterPackageValidationError(
            "Recovery adapter release trust root digest changed"
        )


def _hash_regular_artifact(path: Path) -> tuple[str, int, int]:
    candidate = path.expanduser()
    details = candidate.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise RecoveryAdapterPackageValidationError(
            "Recovery adapter executable must be one regular file, not a link"
        )
    descriptor = os.open(candidate, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            details.st_dev,
            details.st_ino,
        ):
            raise RecoveryAdapterPackageValidationError(
                "Recovery adapter executable changed while it was inspected"
            )
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                size += len(block)
                if size > MAX_RECOVERY_ADAPTER_BYTES:
                    raise RecoveryAdapterPackageValidationError(
                        "Recovery adapter executable exceeds its size boundary"
                    )
                digest.update(block)
        final = os.fstat(descriptor)
        if (final.st_size, final.st_mtime_ns) != (opened.st_size, opened.st_mtime_ns):
            raise RecoveryAdapterPackageValidationError(
                "Recovery adapter executable changed while it was hashed"
            )
        return digest.hexdigest(), size, opened.st_mode
    finally:
        os.close(descriptor)


def _validate_platform_artifact(path: Path, platform: str, mode: int) -> None:
    if mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
        raise RecoveryAdapterPackageValidationError(
            "Recovery adapter executable has unsafe special permissions"
        )
    if platform == "linux-x86_64":
        if path.suffix.casefold() == ".exe" or not mode & stat.S_IXUSR:
            raise RecoveryAdapterPackageValidationError(
                "Linux Recovery adapter executable is not owner-executable"
            )
    elif path.suffix.casefold() != ".exe":
        raise RecoveryAdapterPackageValidationError(
            "Windows Recovery adapter executable must use an .exe identity"
        )


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _exact_fields(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise RecoveryAdapterPackageValidationError(f"{label} fields are not exact")


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise RecoveryAdapterPackageValidationError(f"{label} is invalid")
    return value


def _version(value: object) -> str:
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise RecoveryAdapterPackageValidationError("Recovery adapter package version is invalid")
    return value


def _utc_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise RecoveryAdapterPackageValidationError(
            "Recovery adapter package timestamp must be canonical UTC"
        )
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise RecoveryAdapterPackageValidationError(
            "Recovery adapter package timestamp must be UTC"
        )
    return value


def _text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise RecoveryAdapterPackageValidationError(f"{label} is invalid")
    return value


def _safe_filename(value: object) -> str:
    if not isinstance(value, str) or not _FILENAME.fullmatch(value):
        raise RecoveryAdapterPackageValidationError(
            "Recovery adapter executable filename is unsafe"
        )
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise RecoveryAdapterPackageValidationError(f"{label} is invalid")
    return value


def _signature(value: object) -> bytes:
    if not isinstance(value, str) or len(value) > 128:
        raise RecoveryAdapterPackageValidationError("Recovery adapter package signature is invalid")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RecoveryAdapterPackageValidationError(
            "Recovery adapter package signature is invalid"
        ) from exc
    if len(decoded) != 64:
        raise RecoveryAdapterPackageValidationError("Recovery adapter package signature is invalid")
    return decoded
