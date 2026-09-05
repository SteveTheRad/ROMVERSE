from __future__ import annotations

import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from romverse.guardian.recovery_adapter_package import (
    GuardianRecoveryAdapterReleaseTrustRoot,
    RecoveryAdapterTrustScope,
    build_guardian_recovery_adapter_manifest,
    create_signed_guardian_recovery_adapter_package,
    verify_guardian_recovery_adapter_package,
)

HOST_PLATFORM = "windows-x86_64" if os.name == "nt" else "linux-x86_64"
OTHER_PLATFORM = "linux-x86_64" if os.name == "nt" else "windows-x86_64"
ARTIFACT_NAME = "ROMVERSE-Recovery-Adapter.exe" if os.name == "nt" else "ROMVERSE-Recovery-Adapter"


def make_test_recovery_adapter_package(
    directory: Path,
    *,
    adapter_id: str,
    action_ids: tuple[str, ...],
    artifact_bytes: bytes = b"#!/bin/sh\nprintf 'fixture adapter\\n'\n",
):
    """Use ephemeral, explicitly test-only trust material; no private key is persisted."""

    directory.mkdir(parents=True, exist_ok=True)
    artifact = directory / ARTIFACT_NAME
    artifact.write_bytes(artifact_bytes)
    artifact.chmod(0o700)
    private_key = Ed25519PrivateKey.generate()
    trust = GuardianRecoveryAdapterReleaseTrustRoot.from_public_key(
        key_id="test.recovery-adapter-release",
        public_key=private_key.public_key(),
        scope=RecoveryAdapterTrustScope.TEST_ONLY,
    )
    manifest = build_guardian_recovery_adapter_manifest(
        package_id="romverse.recovery-adapter.test",
        package_version="0.1.0-test.1",
        created_at="2026-09-05T10:00:00Z",
        platform=HOST_PLATFORM,
        artifact_path=artifact,
        adapter_id=adapter_id,
        adapter_version=1,
        supported_action_ids=action_ids,
    )
    envelope = create_signed_guardian_recovery_adapter_package(
        manifest,
        private_key,
        trust.key_id,
    )
    verified = verify_guardian_recovery_adapter_package(
        envelope=envelope,
        trust_root=trust,
        package_directory=directory,
        expected_platform=HOST_PLATFORM,
    )
    return verified, artifact, private_key, trust, manifest, envelope
