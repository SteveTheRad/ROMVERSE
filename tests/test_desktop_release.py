from __future__ import annotations

import base64
import json
import os
from copy import deepcopy
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from romverse.release import (
    ReleaseValidationError,
    build_release_manifest,
    create_signed_release_envelope,
    load_release_json,
    release_version_order,
    validate_release_manifest,
    verify_release_artifacts,
    verify_release_bundle,
    verify_signed_release_envelope,
    write_release_json,
)


def test_release_version_order_accepts_pep_440_alpha_identity() -> None:
    alpha = release_version_order("0.2.0a1")

    assert alpha > release_version_order("0.1.0")
    assert alpha < release_version_order("0.2.0a2")
    assert release_version_order("0.2.0a10") < release_version_order("0.2.0b1")
    assert release_version_order("0.2.0b1") < release_version_order("0.2.0rc1")
    assert alpha < release_version_order("0.2.0")


def _manifest(tmp_path: Path) -> tuple[dict[str, object], Path]:
    artifact = tmp_path / "romverse-0.1.0-py3-none-any.whl"
    artifact.write_bytes(b"exact desktop candidate bytes")
    return (
        build_release_manifest(
            version="0.1.0",
            channel="release-candidate",
            release_id="romverse-desktop-0.1.0-rc.1",
            published_at="2026-09-03T06:30:00Z",
            artifacts=(("current-python-wheel", "python-any", "wheel", artifact),),
        ),
        artifact,
    )


def test_signed_desktop_release_verifies_exact_artifact(tmp_path: Path) -> None:
    manifest, artifact = _manifest(tmp_path)
    private_key = Ed25519PrivateKey.generate()
    envelope = create_signed_release_envelope(manifest, private_key, "romverse-release-2026")

    result = verify_release_bundle(
        envelope=envelope,
        public_key=private_key.public_key(),
        expected_key_id="romverse-release-2026",
        artifact_directory=tmp_path,
    )

    assert result.manifest.version == "0.1.0"
    assert result.artifact_count == 1
    assert result.artifact_bytes == artifact.stat().st_size
    assert result.manifest.rollback.available is False


def test_signed_release_rejects_manifest_changed_after_signing(tmp_path: Path) -> None:
    manifest, _artifact = _manifest(tmp_path)
    private_key = Ed25519PrivateKey.generate()
    envelope = create_signed_release_envelope(manifest, private_key, "romverse-release-2026")
    envelope["manifest"]["release_id"] = "romverse-desktop-0.1.0-rc.2"

    with pytest.raises(ReleaseValidationError, match="digest does not match"):
        verify_signed_release_envelope(envelope, private_key.public_key(), "romverse-release-2026")


def test_signed_release_rejects_wrong_key_and_key_identity(tmp_path: Path) -> None:
    manifest, _artifact = _manifest(tmp_path)
    private_key = Ed25519PrivateKey.generate()
    envelope = create_signed_release_envelope(manifest, private_key, "romverse-release-2026")

    with pytest.raises(ReleaseValidationError, match="not trusted"):
        verify_signed_release_envelope(envelope, private_key.public_key(), "different-key")
    with pytest.raises(ReleaseValidationError, match="verification failed"):
        verify_signed_release_envelope(
            envelope, Ed25519PrivateKey.generate().public_key(), "romverse-release-2026"
        )


def test_release_rejects_artifact_changed_after_signing(tmp_path: Path) -> None:
    manifest, artifact = _manifest(tmp_path)
    parsed = validate_release_manifest(manifest)
    artifact.write_bytes(b"tampered candidate bytes")

    with pytest.raises(ReleaseValidationError, match="size or SHA-256"):
        verify_release_artifacts(parsed, tmp_path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda manifest: manifest.update({"authority": "install"}), "fields do not match"),
        (
            lambda manifest: manifest["update_policy"].update({"automatic_install": True}),
            "safety boundary",
        ),
        (
            lambda manifest: manifest["artifacts"][0].update({"file_name": "../candidate.whl"}),
            "filename is unsafe",
        ),
        (
            lambda manifest: manifest["artifacts"][0].update({"size_bytes": True}),
            "size is invalid",
        ),
    ),
)
def test_release_manifest_rejects_unsafe_contracts(tmp_path: Path, mutation, message: str) -> None:
    manifest, _artifact = _manifest(tmp_path)
    changed = deepcopy(manifest)
    mutation(changed)

    with pytest.raises(ReleaseValidationError, match=message):
        validate_release_manifest(changed)


def test_release_rollback_requires_exact_included_artifact(tmp_path: Path) -> None:
    manifest, _artifact = _manifest(tmp_path)
    changed = deepcopy(manifest)
    changed["rollback"] = {
        "available": True,
        "target_version": "0.0.9",
        "artifact_id": "missing-rollback",
        "reason": "Operator-selected recovery build.",
    }

    with pytest.raises(ReleaseValidationError, match="eligible release artifact"):
        validate_release_manifest(changed)


def test_release_rollback_requires_older_version_and_included_artifact(tmp_path: Path) -> None:
    current = tmp_path / "romverse-current.whl"
    current.write_bytes(b"current")
    previous = tmp_path / "romverse-previous.whl"
    previous.write_bytes(b"previous")

    manifest = build_release_manifest(
        version="0.1.0",
        channel="release-candidate",
        release_id="romverse-desktop-0.1.0-rc.1",
        published_at="2026-09-03T06:30:00Z",
        artifacts=(
            ("current-python-wheel", "python-any", "wheel", current),
            ("previous-python-wheel", "python-any", "wheel", previous),
        ),
        rollback_version="0.0.9",
        rollback_artifact_id="previous-python-wheel",
        rollback_reason="Last independently verified signed release.",
    )

    assert validate_release_manifest(manifest).rollback.available is True
    manifest["rollback"]["target_version"] = "0.2.0"
    with pytest.raises(ReleaseValidationError, match="eligible release artifact"):
        validate_release_manifest(manifest)


def test_release_json_rejects_duplicate_fields_and_links(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    linked = tmp_path / "linked.json"
    linked.symlink_to(duplicate.name)

    with pytest.raises(ReleaseValidationError, match="Duplicate JSON field"):
        load_release_json(duplicate)
    with pytest.raises(ReleaseValidationError, match="not a link"):
        load_release_json(linked)


def test_release_rejects_malformed_signature(tmp_path: Path) -> None:
    manifest, _artifact = _manifest(tmp_path)
    private_key = Ed25519PrivateKey.generate()
    envelope = create_signed_release_envelope(manifest, private_key, "romverse-release-2026")
    envelope["signature"] = base64.b64encode(b"short").decode("ascii")

    with pytest.raises(ReleaseValidationError, match="invalid length"):
        verify_signed_release_envelope(envelope, private_key.public_key(), "romverse-release-2026")


def test_release_json_writer_round_trips_valid_manifest(tmp_path: Path) -> None:
    manifest, _artifact = _manifest(tmp_path)
    output = tmp_path / "release-manifest.json"

    write_release_json(output, manifest)

    assert load_release_json(output) == json.loads(output.read_text(encoding="ascii"))
    if os.name != "nt":
        assert output.stat().st_mode & 0o777 == 0o644
