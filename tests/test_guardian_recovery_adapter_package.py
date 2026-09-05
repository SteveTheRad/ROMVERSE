from __future__ import annotations

import base64
import hashlib
import json
import os
from copy import deepcopy

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from romverse.guardian.recovery_adapter_package import (
    RECOVERY_ADAPTER_PACKAGE_DOMAIN,
    GuardianRecoveryAdapterReleaseTrustRoot,
    RecoveryAdapterPackageValidationError,
    RecoveryAdapterTrustScope,
    create_signed_guardian_recovery_adapter_package,
    current_recovery_adapter_platform,
    load_guardian_recovery_adapter_package,
    resolve_radforge_production_recovery_adapter_package,
    revalidate_verified_guardian_recovery_adapter_package,
    verify_guardian_recovery_adapter_package,
    write_guardian_recovery_adapter_package,
)
from tests._recovery_adapter_trust import (
    HOST_PLATFORM,
    OTHER_PLATFORM,
    make_test_recovery_adapter_package,
)

ADAPTER_ID = "romverse.fixture.recovery"
ACTIONS = (
    f"{ADAPTER_ID}.restore-stock",
    f"{ADAPTER_ID}.reboot-system",
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _resign(envelope, private_key):
    changed = deepcopy(envelope)
    encoded = _canonical(changed["manifest"])
    changed["manifest_sha256"] = hashlib.sha256(encoded).hexdigest()
    changed["signature"] = base64.b64encode(
        private_key.sign(RECOVERY_ADAPTER_PACKAGE_DOMAIN + encoded)
    ).decode("ascii")
    return changed


def test_release_signed_package_exposes_exact_trust_and_action_identity(tmp_path) -> None:
    package, artifact, _private, trust, manifest, envelope = make_test_recovery_adapter_package(
        tmp_path,
        adapter_id=ADAPTER_ID,
        action_ids=ACTIONS,
    )

    assert package.artifact_path == artifact.resolve()
    assert package.manifest.adapter_id == ADAPTER_ID
    assert package.manifest.adapter_version == 1
    assert package.manifest.supported_action_ids == ACTIONS
    assert package.manifest.artifact.sha256 == manifest["artifact"]["sha256"]
    assert package.release_key_id == trust.key_id
    assert package.release_public_key_sha256 == trust.public_key_sha256
    assert package.release_trust_scope is RecoveryAdapterTrustScope.TEST_ONLY
    with pytest.raises(RecoveryAdapterPackageValidationError, match="RadForge release trust"):
        resolve_radforge_production_recovery_adapter_package(
            envelope=envelope,
            trust_root=trust,
            package_directory=tmp_path,
            expected_platform=HOST_PLATFORM,
        )
    assert len(package.manifest_sha256) == 64
    assert len(package.package_sha256) == 64
    assert "private" not in repr(package).casefold()
    assert revalidate_verified_guardian_recovery_adapter_package(package).package_sha256 == (
        package.package_sha256
    )
    assert current_recovery_adapter_platform() == HOST_PLATFORM


def test_test_and_radforge_production_trust_roots_are_explicitly_separate(tmp_path) -> None:
    package, _artifact, _private, _trust, _manifest, envelope = make_test_recovery_adapter_package(
        tmp_path,
        adapter_id=ADAPTER_ID,
        action_ids=ACTIONS,
    )
    wrong_key = Ed25519PrivateKey.generate()
    production = GuardianRecoveryAdapterReleaseTrustRoot.from_public_key(
        key_id="radforge.recovery-adapter.release-2026",
        public_key=wrong_key.public_key(),
        scope=RecoveryAdapterTrustScope.RADFORGE_PRODUCTION,
    )

    with pytest.raises(RecoveryAdapterPackageValidationError, match="identity is not trusted"):
        verify_guardian_recovery_adapter_package(
            envelope=envelope,
            trust_root=production,
            package_directory=tmp_path,
            expected_platform=HOST_PLATFORM,
        )
    with pytest.raises(RecoveryAdapterPackageValidationError, match="RadForge"):
        GuardianRecoveryAdapterReleaseTrustRoot.from_public_key(
            key_id="test.looks-production",
            public_key=wrong_key.public_key(),
            scope=RecoveryAdapterTrustScope.RADFORGE_PRODUCTION,
        )
    with pytest.raises(RecoveryAdapterPackageValidationError, match="test-only"):
        GuardianRecoveryAdapterReleaseTrustRoot.from_public_key(
            key_id="radforge.looks-test",
            public_key=wrong_key.public_key(),
            scope=RecoveryAdapterTrustScope.TEST_ONLY,
        )
    assert package.release_trust_scope is RecoveryAdapterTrustScope.TEST_ONLY


def test_radforge_production_resolver_accepts_only_explicit_production_public_trust(
    tmp_path,
) -> None:
    _package, _artifact, _private, _test_trust, manifest, _envelope = (
        make_test_recovery_adapter_package(
            tmp_path,
            adapter_id=ADAPTER_ID,
            action_ids=ACTIONS,
        )
    )
    production_private = Ed25519PrivateKey.generate()
    production_trust = GuardianRecoveryAdapterReleaseTrustRoot.from_public_key(
        key_id="radforge.recovery-adapter.release-2026",
        public_key=production_private.public_key(),
        scope=RecoveryAdapterTrustScope.RADFORGE_PRODUCTION,
    )
    production_envelope = create_signed_guardian_recovery_adapter_package(
        manifest,
        production_private,
        production_trust.key_id,
    )

    resolved = resolve_radforge_production_recovery_adapter_package(
        envelope=production_envelope,
        trust_root=production_trust,
        package_directory=tmp_path,
        expected_platform=HOST_PLATFORM,
    )

    assert resolved.release_trust_scope is RecoveryAdapterTrustScope.RADFORGE_PRODUCTION
    assert resolved.release_key_id == "radforge.recovery-adapter.release-2026"


def test_unsigned_wrong_signer_platform_and_tampered_executable_fail_closed(tmp_path) -> None:
    package, artifact, _private, trust, _manifest, envelope = make_test_recovery_adapter_package(
        tmp_path,
        adapter_id=ADAPTER_ID,
        action_ids=ACTIONS,
    )
    unsigned = deepcopy(envelope)
    unsigned["signature"] = ""
    with pytest.raises(RecoveryAdapterPackageValidationError, match="signature"):
        verify_guardian_recovery_adapter_package(
            envelope=unsigned,
            trust_root=trust,
            package_directory=tmp_path,
            expected_platform=HOST_PLATFORM,
        )

    wrong = GuardianRecoveryAdapterReleaseTrustRoot.from_public_key(
        key_id=trust.key_id,
        public_key=Ed25519PrivateKey.generate().public_key(),
        scope=RecoveryAdapterTrustScope.TEST_ONLY,
    )
    with pytest.raises(RecoveryAdapterPackageValidationError, match="signature verification"):
        verify_guardian_recovery_adapter_package(
            envelope=envelope,
            trust_root=wrong,
            package_directory=tmp_path,
            expected_platform=HOST_PLATFORM,
        )
    with pytest.raises(RecoveryAdapterPackageValidationError, match="platform"):
        verify_guardian_recovery_adapter_package(
            envelope=envelope,
            trust_root=trust,
            package_directory=tmp_path,
            expected_platform=OTHER_PLATFORM,
        )

    artifact.write_bytes(b"substituted executable\n")
    artifact.chmod(0o700)
    with pytest.raises(RecoveryAdapterPackageValidationError, match="size or SHA-256"):
        revalidate_verified_guardian_recovery_adapter_package(package)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda manifest: manifest.update({"protocol_version": 2}), "protocol or schema"),
        (
            lambda manifest: manifest.update({"request_schema_version": 2}),
            "protocol or schema",
        ),
        (
            lambda manifest: manifest["supported_action_ids"].append("untrusted.hidden-command"),
            "action allowlist",
        ),
        (
            lambda manifest: manifest.update({"extraArgs": ["--unlock"]}),
            "fields are not exact",
        ),
        (
            lambda manifest: manifest["safety_policy"].update(
                {"environment_overrides_allowed": True}
            ),
            "safety boundary",
        ),
        (
            lambda manifest: manifest["safety_policy"].update({"raw_output_success_allowed": True}),
            "safety boundary",
        ),
        (
            lambda manifest: manifest["supported_action_ids"].append(
                f"{ADAPTER_ID}.bootloader-lock"
            ),
            "locking action",
        ),
        (
            lambda manifest: manifest["supported_action_ids"].append(f"{ADAPTER_ID}.relock"),
            "locking action",
        ),
        (
            lambda manifest: manifest["supported_action_ids"].append(
                f"{ADAPTER_ID}.bootloaderlock"
            ),
            "locking action",
        ),
        (
            lambda manifest: manifest["supported_action_ids"].append(
                f"{ADAPTER_ID}.relockbootloader"
            ),
            "locking action",
        ),
    ),
)
def test_even_release_signed_hidden_unsafe_or_unsupported_manifests_are_rejected(
    tmp_path,
    mutation,
    message,
) -> None:
    _package, _artifact, private, trust, _manifest, envelope = make_test_recovery_adapter_package(
        tmp_path,
        adapter_id=ADAPTER_ID,
        action_ids=ACTIONS,
    )
    changed = deepcopy(envelope)
    mutation(changed["manifest"])
    changed = _resign(changed, private)

    with pytest.raises(RecoveryAdapterPackageValidationError, match=message):
        verify_guardian_recovery_adapter_package(
            envelope=changed,
            trust_root=trust,
            package_directory=tmp_path,
            expected_platform=HOST_PLATFORM,
        )


def test_package_document_rejects_duplicate_fields_and_link_substitution(tmp_path) -> None:
    _package, artifact, _private, _trust, _manifest, envelope = make_test_recovery_adapter_package(
        tmp_path,
        adapter_id=ADAPTER_ID,
        action_ids=ACTIONS,
    )
    document = tmp_path / "recovery-adapter-package.json"
    write_guardian_recovery_adapter_package(document, envelope)
    assert load_guardian_recovery_adapter_package(document) == envelope

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(RecoveryAdapterPackageValidationError, match="document is invalid"):
        load_guardian_recovery_adapter_package(duplicate)

    if os.name != "nt":
        linked = tmp_path / "linked-adapter"
        linked.symlink_to(artifact.name)
        changed = deepcopy(envelope)
        changed["manifest"]["artifact"]["file_name"] = linked.name
        changed = _resign(changed, _private)
        with pytest.raises(RecoveryAdapterPackageValidationError, match="regular file"):
            verify_guardian_recovery_adapter_package(
                envelope=changed,
                trust_root=_trust,
                package_directory=tmp_path,
                expected_platform=HOST_PLATFORM,
            )
