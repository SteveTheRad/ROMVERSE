from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import stat
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from romverse.guardian.execution_gateway_contract import (
    GuardianExecutionGatewayContract,
    GuardianExecutionGatewayContractService,
)
from romverse.guardian.execution_result_receipt import (
    GuardianRuntimeTrust,
    validate_guardian_runtime_trust,
)
from romverse.release import ReleaseValidationError, load_release_json, write_release_json
from romverse.rom.models import ProjectError

RUNTIME_PACKAGE_FORMAT = "romverse.guardian-runtime-package"
RUNTIME_PACKAGE_PRODUCT = "ROMVERSE Guardian Runtime"
RUNTIME_PACKAGE_SCHEMA_VERSION = 1
RUNTIME_PROTOCOL_VERSION = 1
RUNTIME_RESULT_RECEIPT_SCHEMA_VERSION = 2
RUNTIME_PACKAGE_DOMAIN = b"ROMVERSE-GUARDIAN-RUNTIME-PACKAGE-V1\0"
MAX_RUNTIME_ARTIFACT_BYTES = 2_147_483_648
RUNTIME_PLATFORMS = frozenset({"linux-x86_64", "windows-x86_64"})

_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?")
_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,159}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class RuntimePackageValidationError(ProjectError):
    """A Guardian runtime package failed its release or artifact trust boundary."""


@dataclass(frozen=True, slots=True)
class GuardianRuntimeArtifact:
    file_name: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class GuardianRuntimeSignerIdentity:
    key_id: str
    algorithm: str
    public_key_base64: str = field(repr=False)
    public_key_sha256: str


@dataclass(frozen=True, slots=True)
class GuardianRuntimeSafetyPolicy:
    accepts_forward_scope_only: bool
    automatic_recovery_enabled: bool
    automatic_wipe_enabled: bool
    bootloader_unlock_enabled: bool
    bootloader_relock_enabled: bool
    execution_authority: str
    device_access_opened: bool
    phone_changed: bool


@dataclass(frozen=True, slots=True)
class GuardianRuntimePackageManifest:
    runtime_id: str
    runtime_version: str
    created_at: str
    platform: str
    runtime_protocol_version: int
    result_receipt_schema_version: int
    adapter_id: str
    adapter_version: int
    artifact: GuardianRuntimeArtifact
    runtime_signer: GuardianRuntimeSignerIdentity
    safety_policy: GuardianRuntimeSafetyPolicy


@dataclass(frozen=True, slots=True)
class VerifiedGuardianRuntimePackage:
    """Release-signed runtime identity whose exact artifact has been rehashed locally."""

    manifest: GuardianRuntimePackageManifest
    release_key_id: str
    manifest_sha256: str
    artifact_path: Path
    _runtime_public_key: Ed25519PublicKey = field(repr=False, compare=False)

    @property
    def runtime_public_key(self) -> Ed25519PublicKey:
        return self._runtime_public_key

    def trust_for_gateway(
        self,
        gateway: GuardianExecutionGatewayContract,
    ) -> GuardianRuntimeTrust:
        """Bind this verified runtime identity to one exact inert Guardian gateway."""

        try:
            GuardianExecutionGatewayContractService.validate(gateway)
            if (
                self.manifest.runtime_protocol_version != RUNTIME_PROTOCOL_VERSION
                or self.manifest.result_receipt_schema_version
                != gateway.result_receipt_schema_version
            ):
                raise RuntimePackageValidationError(
                    "Runtime package protocol does not match the Guardian gateway"
                )
            trust = GuardianRuntimeTrust(
                key_id=self.manifest.runtime_signer.key_id,
                public_key_sha256=self.manifest.runtime_signer.public_key_sha256,
                adapter_id=self.manifest.adapter_id,
                adapter_version=self.manifest.adapter_version,
                adapter_sha256=self.manifest.artifact.sha256,
                device_pack_id=gateway.device_pack_id,
                device_pack_sha256=gateway.device_pack_sha256,
                write_contract_id=gateway.write_contract_id,
                write_contract_version=gateway.write_contract_version,
                write_attestation_sha256=gateway.write_attestation_sha256,
                transition_recovery_contract_digest=gateway.transition_recovery_contract_digest,
            )
            validate_guardian_runtime_trust(trust, self._runtime_public_key, gateway)
            return trust
        except RuntimePackageValidationError:
            raise
        except (AttributeError, TypeError, ValueError, ProjectError) as exc:
            raise RuntimePackageValidationError(
                "Runtime package could not bind to the exact Guardian gateway"
            ) from exc


def build_guardian_runtime_package_manifest(
    *,
    runtime_id: str,
    runtime_version: str,
    created_at: str,
    platform: str,
    artifact_path: Path,
    runtime_signer_key_id: str,
    runtime_public_key: Ed25519PublicKey,
    adapter_id: str,
    adapter_version: int,
) -> dict[str, Any]:
    """Build an unsigned manifest from one runtime artifact and public signing identity."""

    try:
        artifact_digest, artifact_size, artifact_mode = _hash_regular_artifact(
            artifact_path.expanduser()
        )
        if not isinstance(runtime_public_key, Ed25519PublicKey):
            raise RuntimePackageValidationError("Runtime signer public key must use Ed25519")
        raw_key = runtime_public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        manifest: dict[str, Any] = {
            "schema_version": RUNTIME_PACKAGE_SCHEMA_VERSION,
            "product": RUNTIME_PACKAGE_PRODUCT,
            "runtime_id": runtime_id,
            "runtime_version": runtime_version,
            "created_at": created_at,
            "platform": platform,
            "runtime_protocol_version": RUNTIME_PROTOCOL_VERSION,
            "result_receipt_schema_version": RUNTIME_RESULT_RECEIPT_SCHEMA_VERSION,
            "adapter_id": adapter_id,
            "adapter_version": adapter_version,
            "artifact": {
                "file_name": artifact_path.name,
                "size_bytes": artifact_size,
                "sha256": artifact_digest,
            },
            "runtime_signer": {
                "key_id": runtime_signer_key_id,
                "algorithm": "ed25519",
                "public_key_base64": base64.b64encode(raw_key).decode("ascii"),
                "public_key_sha256": hashlib.sha256(raw_key).hexdigest(),
            },
            "safety_policy": {
                "accepts_forward_scope_only": True,
                "automatic_recovery_enabled": False,
                "automatic_wipe_enabled": False,
                "bootloader_unlock_enabled": False,
                "bootloader_relock_enabled": False,
                "execution_authority": "none",
                "device_access_opened": False,
                "phone_changed": False,
            },
        }
        parsed = validate_guardian_runtime_package_manifest(manifest)
        _validate_platform_artifact(
            artifact_path.expanduser(),
            parsed.platform,
            artifact_mode=artifact_mode,
        )
        return manifest
    except RuntimePackageValidationError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise RuntimePackageValidationError(
            "Runtime package manifest could not be prepared"
        ) from exc


def validate_guardian_runtime_package_manifest(
    value: dict[str, Any],
) -> GuardianRuntimePackageManifest:
    if not isinstance(value, dict):
        raise RuntimePackageValidationError("Runtime package manifest must be one object")
    _exact_fields(
        value,
        {
            "schema_version",
            "product",
            "runtime_id",
            "runtime_version",
            "created_at",
            "platform",
            "runtime_protocol_version",
            "result_receipt_schema_version",
            "adapter_id",
            "adapter_version",
            "artifact",
            "runtime_signer",
            "safety_policy",
        },
        "Runtime package manifest",
    )
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != RUNTIME_PACKAGE_SCHEMA_VERSION
        or value["product"] != RUNTIME_PACKAGE_PRODUCT
    ):
        raise RuntimePackageValidationError("Runtime package schema or product is unsupported")
    runtime_id = _identifier(value["runtime_id"], "Runtime identity")
    runtime_version = _version(value["runtime_version"])
    created_at = _utc_timestamp(value["created_at"])
    platform = _text(value["platform"], "Runtime platform", 32)
    if platform not in RUNTIME_PLATFORMS:
        raise RuntimePackageValidationError("Runtime platform is unsupported")
    if (
        type(value["runtime_protocol_version"]) is not int
        or value["runtime_protocol_version"] != RUNTIME_PROTOCOL_VERSION
        or type(value["result_receipt_schema_version"]) is not int
        or value["result_receipt_schema_version"] != RUNTIME_RESULT_RECEIPT_SCHEMA_VERSION
    ):
        raise RuntimePackageValidationError("Runtime protocol or result schema is unsupported")
    adapter_id = _identifier(value["adapter_id"], "Runtime adapter identity")
    adapter_version = value["adapter_version"]
    if type(adapter_version) is not int or not 1 <= adapter_version <= 1_000_000:
        raise RuntimePackageValidationError("Runtime adapter version is invalid")

    raw_artifact = value["artifact"]
    if not isinstance(raw_artifact, dict):
        raise RuntimePackageValidationError("Runtime artifact is invalid")
    _exact_fields(raw_artifact, {"file_name", "size_bytes", "sha256"}, "Runtime artifact")
    file_name = _safe_filename(raw_artifact["file_name"])
    size_bytes = raw_artifact["size_bytes"]
    artifact_sha256 = _sha256(raw_artifact["sha256"], "Runtime artifact SHA-256")
    if type(size_bytes) is not int or not 1 <= size_bytes <= MAX_RUNTIME_ARTIFACT_BYTES:
        raise RuntimePackageValidationError("Runtime artifact size is invalid")

    raw_signer = value["runtime_signer"]
    if not isinstance(raw_signer, dict):
        raise RuntimePackageValidationError("Runtime signer identity is invalid")
    _exact_fields(
        raw_signer,
        {"key_id", "algorithm", "public_key_base64", "public_key_sha256"},
        "Runtime signer identity",
    )
    signer_key_id = _identifier(raw_signer["key_id"], "Runtime signer key identity")
    if raw_signer["algorithm"] != "ed25519":
        raise RuntimePackageValidationError("Runtime signer algorithm is unsupported")
    public_key_base64 = _text(raw_signer["public_key_base64"], "Runtime signer public key", 64)
    public_key_sha256 = _sha256(
        raw_signer["public_key_sha256"], "Runtime signer public-key SHA-256"
    )
    raw_public_key = _decode_runtime_public_key(public_key_base64)
    if hashlib.sha256(raw_public_key).hexdigest() != public_key_sha256:
        raise RuntimePackageValidationError("Runtime signer public-key digest does not match")

    raw_policy = value["safety_policy"]
    if not isinstance(raw_policy, dict):
        raise RuntimePackageValidationError("Runtime safety policy is invalid")
    _exact_fields(
        raw_policy,
        {
            "accepts_forward_scope_only",
            "automatic_recovery_enabled",
            "automatic_wipe_enabled",
            "bootloader_unlock_enabled",
            "bootloader_relock_enabled",
            "execution_authority",
            "device_access_opened",
            "phone_changed",
        },
        "Runtime safety policy",
    )
    if (
        raw_policy["accepts_forward_scope_only"] is not True
        or raw_policy["automatic_recovery_enabled"] is not False
        or raw_policy["automatic_wipe_enabled"] is not False
        or raw_policy["bootloader_unlock_enabled"] is not False
        or raw_policy["bootloader_relock_enabled"] is not False
        or raw_policy["execution_authority"] != "none"
        or raw_policy["device_access_opened"] is not False
        or raw_policy["phone_changed"] is not False
    ):
        raise RuntimePackageValidationError("Runtime package violates its safety boundary")

    return GuardianRuntimePackageManifest(
        runtime_id=runtime_id,
        runtime_version=runtime_version,
        created_at=created_at,
        platform=platform,
        runtime_protocol_version=value["runtime_protocol_version"],
        result_receipt_schema_version=value["result_receipt_schema_version"],
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        artifact=GuardianRuntimeArtifact(file_name, size_bytes, artifact_sha256),
        runtime_signer=GuardianRuntimeSignerIdentity(
            signer_key_id,
            "ed25519",
            public_key_base64,
            public_key_sha256,
        ),
        safety_policy=GuardianRuntimeSafetyPolicy(
            accepts_forward_scope_only=True,
            automatic_recovery_enabled=False,
            automatic_wipe_enabled=False,
            bootloader_unlock_enabled=False,
            bootloader_relock_enabled=False,
            execution_authority="none",
            device_access_opened=False,
            phone_changed=False,
        ),
    )


def create_signed_guardian_runtime_package(
    manifest: dict[str, Any],
    release_private_key: Ed25519PrivateKey,
    release_key_id: str,
) -> dict[str, Any]:
    validate_guardian_runtime_package_manifest(manifest)
    if not isinstance(release_private_key, Ed25519PrivateKey):
        raise RuntimePackageValidationError("Runtime package release key must use Ed25519")
    key_id = _identifier(release_key_id, "Runtime package release-key identity")
    encoded = _canonical_bytes(manifest)
    return {
        "format": RUNTIME_PACKAGE_FORMAT,
        "schema_version": RUNTIME_PACKAGE_SCHEMA_VERSION,
        "algorithm": "ed25519",
        "key_id": key_id,
        "manifest_sha256": hashlib.sha256(encoded).hexdigest(),
        "manifest": manifest,
        "signature": base64.b64encode(
            release_private_key.sign(RUNTIME_PACKAGE_DOMAIN + encoded)
        ).decode("ascii"),
    }


def verify_guardian_runtime_package(
    *,
    envelope: dict[str, Any],
    release_public_key: Ed25519PublicKey,
    expected_release_key_id: str,
    package_directory: Path,
    expected_platform: str,
) -> VerifiedGuardianRuntimePackage:
    """Verify release signature, runtime signing identity, and exact local runtime bytes."""

    try:
        if not isinstance(release_public_key, Ed25519PublicKey):
            raise RuntimePackageValidationError("Runtime package release key must use Ed25519")
        key_id = _identifier(
            expected_release_key_id, "Expected runtime package release-key identity"
        )
        platform = _text(expected_platform, "Expected runtime platform", 32)
        if platform not in RUNTIME_PLATFORMS:
            raise RuntimePackageValidationError("Expected runtime platform is unsupported")
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
            "Signed runtime package",
        )
        if (
            envelope["format"] != RUNTIME_PACKAGE_FORMAT
            or type(envelope["schema_version"]) is not int
            or envelope["schema_version"] != RUNTIME_PACKAGE_SCHEMA_VERSION
            or envelope["algorithm"] != "ed25519"
            or envelope["key_id"] != key_id
        ):
            raise RuntimePackageValidationError("Runtime package release identity is not trusted")
        raw_manifest = envelope["manifest"]
        manifest = validate_guardian_runtime_package_manifest(raw_manifest)
        if manifest.platform != platform:
            raise RuntimePackageValidationError("Runtime package platform does not match this host")
        encoded = _canonical_bytes(raw_manifest)
        manifest_sha256 = hashlib.sha256(encoded).hexdigest()
        if envelope["manifest_sha256"] != manifest_sha256:
            raise RuntimePackageValidationError("Runtime package manifest digest does not match")
        signature = _signature(envelope["signature"])
        try:
            release_public_key.verify(signature, RUNTIME_PACKAGE_DOMAIN + encoded)
        except InvalidSignature as exc:
            raise RuntimePackageValidationError(
                "Runtime package release signature verification failed"
            ) from exc

        root = package_directory.expanduser()
        try:
            root_details = root.lstat()
        except OSError as exc:
            raise RuntimePackageValidationError("Runtime package directory is unavailable") from exc
        if stat.S_ISLNK(root_details.st_mode) or not stat.S_ISDIR(root_details.st_mode):
            raise RuntimePackageValidationError(
                "Runtime package directory must be one real directory, not a link"
            )
        artifact_path = root / manifest.artifact.file_name
        artifact_digest, artifact_size, artifact_mode = _hash_regular_artifact(artifact_path)
        _validate_platform_artifact(
            artifact_path,
            manifest.platform,
            artifact_mode=artifact_mode,
        )
        if (
            artifact_digest != manifest.artifact.sha256
            or artifact_size != manifest.artifact.size_bytes
        ):
            raise RuntimePackageValidationError(
                "Runtime artifact failed exact size or SHA-256 verification"
            )
        raw_runtime_key = _decode_runtime_public_key(manifest.runtime_signer.public_key_base64)
        runtime_public_key = Ed25519PublicKey.from_public_bytes(raw_runtime_key)
        return VerifiedGuardianRuntimePackage(
            manifest=manifest,
            release_key_id=key_id,
            manifest_sha256=manifest_sha256,
            artifact_path=artifact_path.resolve(strict=True),
            _runtime_public_key=runtime_public_key,
        )
    except RuntimePackageValidationError:
        raise
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise RuntimePackageValidationError("Runtime package verification failed closed") from exc


def load_guardian_runtime_package(path: Path) -> dict[str, Any]:
    try:
        return load_release_json(path)
    except ReleaseValidationError as exc:
        raise RuntimePackageValidationError("Runtime package document is invalid") from exc


def write_guardian_runtime_package(path: Path, value: dict[str, Any]) -> None:
    try:
        write_release_json(path, value)
    except ReleaseValidationError as exc:
        raise RuntimePackageValidationError(
            "Runtime package document could not be written"
        ) from exc


def _hash_regular_artifact(path: Path) -> tuple[str, int, int]:
    try:
        before = path.lstat()
    except OSError as exc:
        raise RuntimePackageValidationError("Runtime artifact is unavailable") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RuntimePackageValidationError("Runtime artifact must be one regular file, not a link")
    if not 1 <= before.st_size <= MAX_RUNTIME_ARTIFACT_BYTES:
        raise RuntimePackageValidationError("Runtime artifact size is invalid")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
        try:
            with os.fdopen(descriptor, "rb", closefd=True) as stream:
                opened = os.fstat(stream.fileno())
                current = path.lstat()
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or not os.path.samestat(before, opened)
                    or not os.path.samestat(opened, current)
                    or opened.st_size != before.st_size
                ):
                    raise RuntimePackageValidationError(
                        "Runtime artifact changed while it was being opened"
                    )
                digest = hashlib.sha256()
                read_bytes = 0
                while chunk := stream.read(1024 * 1024):
                    read_bytes += len(chunk)
                    if read_bytes > MAX_RUNTIME_ARTIFACT_BYTES:
                        raise RuntimePackageValidationError(
                            "Runtime artifact exceeded its size boundary"
                        )
                    digest.update(chunk)
                final = os.fstat(stream.fileno())
                current = path.lstat()
                if (
                    read_bytes != opened.st_size
                    or final.st_size != opened.st_size
                    or final.st_mtime_ns != opened.st_mtime_ns
                    or not os.path.samestat(opened, final)
                    or not os.path.samestat(opened, current)
                ):
                    raise RuntimePackageValidationError(
                        "Runtime artifact changed while it was being verified"
                    )
        except Exception:
            with suppress(OSError):
                os.close(descriptor)
            raise
    except RuntimePackageValidationError:
        raise
    except OSError as exc:
        raise RuntimePackageValidationError("Runtime artifact could not be read safely") from exc
    return digest.hexdigest(), read_bytes, opened.st_mode


def _validate_platform_artifact(path: Path, platform: str, *, artifact_mode: int) -> None:
    if platform == "linux-x86_64" and not artifact_mode & stat.S_IXUSR:
        raise RuntimePackageValidationError("Linux runtime artifact is not owner-executable")
    if platform == "windows-x86_64" and path.suffix.casefold() != ".exe":
        raise RuntimePackageValidationError("Windows runtime artifact must be an EXE")


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise RuntimePackageValidationError(
            "Runtime package manifest is not canonical JSON"
        ) from exc


def _exact_fields(value: object, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise RuntimePackageValidationError(f"{label} fields do not match schema")


def _text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\x00" in value:
        raise RuntimePackageValidationError(f"{label} is invalid")
    return value


def _identifier(value: object, label: str) -> str:
    result = _text(value, label, 96)
    if _IDENTIFIER.fullmatch(result) is None:
        raise RuntimePackageValidationError(f"{label} is invalid")
    return result


def _version(value: object) -> str:
    result = _text(value, "Runtime version", 64)
    if _VERSION.fullmatch(result) is None:
        raise RuntimePackageValidationError("Runtime version is invalid")
    return result


def _utc_timestamp(value: object) -> str:
    result = _text(value, "Runtime package timestamp", 40)
    if not result.endswith("Z"):
        raise RuntimePackageValidationError("Runtime package timestamp must be UTC")
    try:
        parsed = datetime.fromisoformat(result[:-1] + "+00:00")
    except ValueError as exc:
        raise RuntimePackageValidationError("Runtime package timestamp is invalid") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise RuntimePackageValidationError("Runtime package timestamp must be UTC")
    return result


def _safe_filename(value: object) -> str:
    result = _text(value, "Runtime artifact filename", 160)
    if (
        _FILENAME.fullmatch(result) is None
        or "/" in result
        or "\\" in result
        or result in {".", ".."}
    ):
        raise RuntimePackageValidationError("Runtime artifact filename is unsafe")
    return result


def _sha256(value: object, label: str) -> str:
    result = _text(value, label, 64)
    if _SHA256.fullmatch(result) is None:
        raise RuntimePackageValidationError(f"{label} is invalid")
    return result


def _decode_runtime_public_key(value: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RuntimePackageValidationError("Runtime signer public key is malformed") from exc
    if len(decoded) != 32:
        raise RuntimePackageValidationError("Runtime signer public key has invalid length")
    return decoded


def _signature(value: object) -> bytes:
    if not isinstance(value, str) or len(value) > 128:
        raise RuntimePackageValidationError("Runtime package signature is malformed")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RuntimePackageValidationError("Runtime package signature is malformed") from exc
    if len(decoded) != 64:
        raise RuntimePackageValidationError("Runtime package signature has invalid length")
    return decoded
