from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from romverse.guardian.runtime_package import (
    RUNTIME_PACKAGE_DOMAIN,
    RuntimePackageValidationError,
    build_guardian_runtime_package_manifest,
    create_signed_guardian_runtime_package,
    load_guardian_runtime_package,
    verify_guardian_runtime_package,
    write_guardian_runtime_package,
)

pytest_plugins = ("tests.test_guardian_runtime_session",)

_HOST_PLATFORM = "windows-x86_64" if os.name == "nt" else "linux-x86_64"
_OTHER_PLATFORM = "linux-x86_64" if os.name == "nt" else "windows-x86_64"
_ARTIFACT_NAME = "ROMVERSE-Guardian-Runtime.exe" if os.name == "nt" else "ROMVERSE-Guardian-Runtime"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _package(tmp_path: Path):
    artifact = tmp_path / _ARTIFACT_NAME
    artifact.write_bytes(b"separately packaged forward-only runtime fixture\n")
    artifact.chmod(0o700)
    runtime_private_key = Ed25519PrivateKey.generate()
    release_private_key = Ed25519PrivateKey.generate()
    manifest = build_guardian_runtime_package_manifest(
        runtime_id="romverse.guardian-runtime",
        runtime_version="0.1.0-rc.1",
        created_at="2026-09-04T08:30:00Z",
        platform=_HOST_PLATFORM,
        artifact_path=artifact,
        runtime_signer_key_id="guardian-runtime-2026",
        runtime_public_key=runtime_private_key.public_key(),
        adapter_id="romverse.fastboot.forward",
        adapter_version=1,
    )
    envelope = create_signed_guardian_runtime_package(
        manifest,
        release_private_key,
        "romverse-runtime-release-2026",
    )
    return artifact, runtime_private_key, release_private_key, manifest, envelope


def _resign(envelope, release_private_key):
    changed = deepcopy(envelope)
    encoded = _canonical(changed["manifest"])
    changed["manifest_sha256"] = hashlib.sha256(encoded).hexdigest()
    changed["signature"] = base64.b64encode(
        release_private_key.sign(RUNTIME_PACKAGE_DOMAIN + encoded)
    ).decode("ascii")
    return changed


def test_release_signed_runtime_package_rehashes_artifact_and_binds_exact_gateway(
    tmp_path,
    runtime_context,
) -> None:
    artifact, runtime_key, release_key, manifest, envelope = _package(tmp_path)

    verified = verify_guardian_runtime_package(
        envelope=envelope,
        release_public_key=release_key.public_key(),
        expected_release_key_id="romverse-runtime-release-2026",
        package_directory=tmp_path,
        expected_platform=_HOST_PLATFORM,
    )
    trust = verified.trust_for_gateway(runtime_context["gateway"])
    raw_runtime_key = runtime_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    assert verified.artifact_path == artifact.resolve()
    assert verified.manifest.runtime_id == "romverse.guardian-runtime"
    assert verified.manifest.safety_policy.accepts_forward_scope_only
    assert verified.manifest.safety_policy.execution_authority == "none"
    assert not verified.manifest.safety_policy.device_access_opened
    assert not verified.manifest.safety_policy.phone_changed
    assert (
        verified.runtime_public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        == raw_runtime_key
    )
    assert trust.key_id == "guardian-runtime-2026"
    assert trust.adapter_id == "romverse.fastboot.forward"
    assert trust.adapter_sha256 == manifest["artifact"]["sha256"]
    assert trust.device_pack_id == runtime_context["gateway"].device_pack_id
    assert trust.write_contract_id == runtime_context["gateway"].write_contract_id
    assert "public_key_base64" not in repr(verified)


def test_runtime_package_rejects_changed_or_linked_artifact(tmp_path) -> None:
    artifact, _runtime_key, release_key, _manifest, envelope = _package(tmp_path)
    artifact.write_bytes(b"changed after release signing\n")

    with pytest.raises(RuntimePackageValidationError, match="size or SHA-256"):
        verify_guardian_runtime_package(
            envelope=envelope,
            release_public_key=release_key.public_key(),
            expected_release_key_id="romverse-runtime-release-2026",
            package_directory=tmp_path,
            expected_platform=_HOST_PLATFORM,
        )

    if os.name == "nt":
        pytest.skip("Windows test accounts may not have symbolic-link permission")
    artifact.unlink()
    outside = tmp_path.parent / "outside-runtime"
    outside.write_bytes(b"separately packaged forward-only runtime fixture\n")
    artifact.symlink_to(outside)
    with pytest.raises(RuntimePackageValidationError, match="regular file, not a link"):
        verify_guardian_runtime_package(
            envelope=envelope,
            release_public_key=release_key.public_key(),
            expected_release_key_id="romverse-runtime-release-2026",
            package_directory=tmp_path,
            expected_platform=_HOST_PLATFORM,
        )


def test_runtime_package_rejects_wrong_release_identity_key_or_platform(tmp_path) -> None:
    _artifact, _runtime_key, release_key, _manifest, envelope = _package(tmp_path)

    with pytest.raises(RuntimePackageValidationError, match="identity is not trusted"):
        verify_guardian_runtime_package(
            envelope=envelope,
            release_public_key=release_key.public_key(),
            expected_release_key_id="different-release-key",
            package_directory=tmp_path,
            expected_platform=_HOST_PLATFORM,
        )
    with pytest.raises(RuntimePackageValidationError, match="signature verification failed"):
        verify_guardian_runtime_package(
            envelope=envelope,
            release_public_key=Ed25519PrivateKey.generate().public_key(),
            expected_release_key_id="romverse-runtime-release-2026",
            package_directory=tmp_path,
            expected_platform=_HOST_PLATFORM,
        )
    with pytest.raises(RuntimePackageValidationError, match="platform does not match"):
        verify_guardian_runtime_package(
            envelope=envelope,
            release_public_key=release_key.public_key(),
            expected_release_key_id="romverse-runtime-release-2026",
            package_directory=tmp_path,
            expected_platform=_OTHER_PLATFORM,
        )


def test_linux_runtime_package_rejects_artifact_without_owner_execute_bit(tmp_path) -> None:
    if os.name == "nt":
        pytest.skip("Windows runtime packages use executable-file identity instead of mode bits")
    artifact, _runtime_key, release_key, _manifest, envelope = _package(tmp_path)
    artifact.chmod(0o600)

    with pytest.raises(RuntimePackageValidationError, match="not owner-executable"):
        verify_guardian_runtime_package(
            envelope=envelope,
            release_public_key=release_key.public_key(),
            expected_release_key_id="romverse-runtime-release-2026",
            package_directory=tmp_path,
            expected_platform=_HOST_PLATFORM,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda manifest: manifest["safety_policy"].update({"bootloader_relock_enabled": True}),
            "safety boundary",
        ),
        (
            lambda manifest: manifest["safety_policy"].update({"automatic_wipe_enabled": True}),
            "safety boundary",
        ),
        (
            lambda manifest: manifest["artifact"].update({"file_name": "../runtime"}),
            "filename is unsafe",
        ),
        (
            lambda manifest: manifest["runtime_signer"].update({"public_key_sha256": "0" * 64}),
            "public-key digest does not match",
        ),
        (lambda manifest: manifest.update({"execution_authority": "flash"}), "fields"),
    ),
)
def test_runtime_package_rejects_release_signed_unsafe_or_ambiguous_manifest(
    tmp_path,
    mutation,
    message,
) -> None:
    _artifact, _runtime_key, release_key, _manifest, envelope = _package(tmp_path)
    changed = deepcopy(envelope)
    mutation(changed["manifest"])
    changed = _resign(changed, release_key)

    with pytest.raises(RuntimePackageValidationError, match=message):
        verify_guardian_runtime_package(
            envelope=changed,
            release_public_key=release_key.public_key(),
            expected_release_key_id="romverse-runtime-release-2026",
            package_directory=tmp_path,
            expected_platform=_HOST_PLATFORM,
        )


def test_runtime_package_document_round_trips_and_rejects_duplicate_or_linked_json(
    tmp_path,
) -> None:
    _artifact, _runtime_key, _release_key, _manifest, envelope = _package(tmp_path)
    document = tmp_path / "guardian-runtime-package.json"
    write_guardian_runtime_package(document, envelope)

    assert load_guardian_runtime_package(document) == envelope

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(RuntimePackageValidationError, match="document is invalid"):
        load_guardian_runtime_package(duplicate)

    linked = tmp_path / "linked.json"
    linked.symlink_to(document.name)
    with pytest.raises(RuntimePackageValidationError, match="document is invalid"):
        load_guardian_runtime_package(linked)


def test_runtime_package_rejects_linked_package_directory(tmp_path) -> None:
    if os.name == "nt":
        pytest.skip("Windows test accounts may not have symbolic-link permission")
    package = tmp_path / "package"
    package.mkdir()
    _artifact, _runtime_key, release_key, _manifest, envelope = _package(package)
    linked = tmp_path / "linked-package"
    linked.symlink_to(package, target_is_directory=True)

    with pytest.raises(RuntimePackageValidationError, match="real directory, not a link"):
        verify_guardian_runtime_package(
            envelope=envelope,
            release_public_key=release_key.public_key(),
            expected_release_key_id="romverse-runtime-release-2026",
            package_directory=linked,
            expected_platform=_HOST_PLATFORM,
        )


def test_runtime_package_cli_prepares_signs_and_verifies_without_executing_artifact(
    tmp_path,
) -> None:
    repository = Path(__file__).resolve().parents[1]
    marker = tmp_path / "runtime-was-executed"
    artifact = tmp_path / _ARTIFACT_NAME
    artifact.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    artifact.chmod(0o700)
    runtime_key = Ed25519PrivateKey.generate()
    release_key = Ed25519PrivateKey.generate()
    runtime_public_path = tmp_path / "runtime-public.pem"
    release_private_path = tmp_path / "release-private.pem"
    release_public_path = tmp_path / "release-public.pem"
    runtime_public_path.write_bytes(
        runtime_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    release_private_path.write_bytes(
        release_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    release_private_path.chmod(0o600)
    release_public_path.write_bytes(
        release_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    unsigned = tmp_path / "guardian-runtime-unsigned.json"
    signed = tmp_path / "guardian-runtime-signed.json"

    prepared = subprocess.run(
        (
            sys.executable,
            str(repository / "scripts" / "prepare_guardian_runtime_package.py"),
            "--runtime-version",
            "0.1.0-rc.1",
            "--created-at",
            "2026-09-04T08:30:00Z",
            "--platform",
            _HOST_PLATFORM,
            "--artifact",
            str(artifact),
            "--runtime-signer-key-id",
            "guardian-runtime-2026",
            "--runtime-public-key",
            str(runtime_public_path),
            "--adapter-id",
            "romverse.fastboot.forward",
            "--adapter-version",
            "1",
            "--output",
            str(unsigned),
        ),
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    assert prepared.returncode == 0, prepared.stderr
    assert "UNSIGNED" in prepared.stdout
    assert "execution authority" in prepared.stdout

    signed_result = subprocess.run(
        (
            sys.executable,
            str(repository / "scripts" / "sign_guardian_runtime_package.py"),
            str(unsigned),
            "--private-key",
            str(release_private_path),
            "--key-id",
            "romverse-runtime-release-2026",
            "--output",
            str(signed),
        ),
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    assert signed_result.returncode == 0, signed_result.stderr
    assert "does not enroll" in signed_result.stdout
    assert b"PRIVATE KEY" not in signed.read_bytes()

    verified = subprocess.run(
        (
            sys.executable,
            str(repository / "scripts" / "verify_guardian_runtime_package.py"),
            str(signed),
            "--release-public-key",
            str(release_public_path),
            "--release-key-id",
            "romverse-runtime-release-2026",
            "--package-directory",
            str(tmp_path),
            "--platform",
            _HOST_PLATFORM,
        ),
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    assert verified.returncode == 0, verified.stderr
    assert "execution authority none" in verified.stdout
    assert not marker.exists()

    artifact.write_text("changed after verification\n", encoding="utf-8")
    rejected = subprocess.run(
        (
            sys.executable,
            str(repository / "scripts" / "verify_guardian_runtime_package.py"),
            str(signed),
            "--release-public-key",
            str(release_public_path),
            "--release-key-id",
            "romverse-runtime-release-2026",
            "--package-directory",
            str(tmp_path),
            "--platform",
            _HOST_PLATFORM,
        ),
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rejected.returncode != 0
    assert "size or SHA-256" in rejected.stderr
    assert not marker.exists()
