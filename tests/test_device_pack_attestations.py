from __future__ import annotations

import base64
import hashlib
import json
import shutil
import stat
import subprocess
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.attestations import (
    DevicePackAttestationStore,
    DevicePackAttestationVerifier,
    PublisherTrustKey,
    load_publisher_trust_keys,
)
from romverse.device_packs.models import (
    CapabilityStatus,
    DeviceBuildContract,
    DevicePack,
    DynamicPartitionGroup,
    FirmwareSourceContract,
    PackCapability,
    PartitionBuildRule,
)
from romverse.infrastructure.process import SubprocessRunner


def _pack() -> DevicePack:
    contract = DeviceBuildContract(
        "contract",
        1,
        FirmwareSourceContract("BUILD.EXACT", "b" * 64, "c" * 64),
        4096,
        512,
        2,
        False,
        (DynamicPartitionGroup("group", 4096),),
        (PartitionBuildRule("system", 512, 4096, "group", "opaque", "rebuild", "d" * 64),),
        ("system",),
        "e" * 64,
        "f" * 64,
        ("system.img", "vbmeta_system.img", "super.img"),
    )
    return DevicePack(
        "test.pack",
        "1.2.3",
        "Test Pack",
        10,
        ("test",),
        ("phone",),
        ("product",),
        (
            PackCapability(
                "firmware.operations",
                "Build",
                CapabilityStatus.SUPPORTED,
                "model_specific",
                "Exact",
            ),
        ),
        (),
        "a" * 64,
        contract,
    )


@pytest.fixture
def signed_attestation(tmp_path):
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.skip("OpenSSL is unavailable")
    private = tmp_path / "private.pem"
    public = tmp_path / "public.pem"
    subprocess.run(
        (openssl, "genpkey", "-algorithm", "ed25519", "-out", str(private)),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        (openssl, "pkey", "-in", str(private), "-pubout", "-out", str(public)),
        check=True,
        capture_output=True,
    )
    pack = _pack()
    issued = datetime(2026, 8, 29, tzinfo=UTC)
    payload = {
        "format": DevicePackAttestationVerifier.FORMAT,
        "schema_version": 1,
        "signature_algorithm": "ed25519",
        "signer_id": "radforge.release",
        "pack_id": pack.pack_id,
        "pack_version": pack.version,
        "pack_sha256": pack.sha256,
        "source_build_id": pack.build_contract.source.build_id,
        "model": "2509FPN0BC",
        "product": "popsicle",
        "scenarios": sorted(DevicePackAttestationVerifier.REQUIRED_SCENARIOS),
        "result": "pass",
        "report_sha256": "9" * 64,
        "issued_at": issued.isoformat(),
        "expires_at": (issued + timedelta(days=365)).isoformat(),
    }
    message = tmp_path / "message.json"
    signature = tmp_path / "signature.bin"
    message.write_bytes(DevicePackAttestationVerifier.canonical_bytes(payload))
    subprocess.run(
        (
            openssl,
            "pkeyutl",
            "-sign",
            "-inkey",
            str(private),
            "-rawin",
            "-in",
            str(message),
            "-out",
            str(signature),
        ),
        check=True,
        capture_output=True,
    )
    payload["signature"] = base64.b64encode(signature.read_bytes()).decode("ascii")
    envelope = tmp_path / "attestation.romverse"
    envelope.write_text(json.dumps(payload, indent=2) + "\n")
    key = PublisherTrustKey(
        "radforge.release",
        public,
        hashlib.sha256(public.read_bytes()).hexdigest(),
    )
    verifier = DevicePackAttestationVerifier(Path(openssl), SubprocessRunner(), (key,))
    return pack, issued, envelope, verifier, key


def test_exact_physical_recovery_attestation_verifies(signed_attestation):
    pack, issued, envelope, verifier, _key = signed_attestation

    report = verifier.verify(pack, envelope, issued + timedelta(days=1))

    assert report.verified
    assert report.pack_sha256 == pack.sha256
    assert set(report.scenarios) == verifier.REQUIRED_SCENARIOS
    assert report.report_sha256 == "9" * 64
    assert "signature verified" in report.reason


def test_tampered_or_expired_attestation_fails_closed(signed_attestation):
    pack, issued, envelope, verifier, _key = signed_attestation
    data = json.loads(envelope.read_text())
    data["model"] = "tampered"
    envelope.write_text(json.dumps(data))

    tampered = verifier.verify(pack, envelope, issued + timedelta(days=1))
    expired = verifier.verify(pack, envelope, issued + timedelta(days=366))

    assert not tampered.verified
    assert "signature verification failed" in tampered.reason
    assert not expired.verified
    assert "expired" in expired.reason


def test_revoked_key_and_wrong_pack_are_rejected(signed_attestation):
    pack, issued, envelope, verifier, key = signed_attestation
    revoked = DevicePackAttestationVerifier(
        verifier.openssl, verifier.runner, (replace(key, revoked=True),)
    )

    revoked_report = revoked.verify(pack, envelope, issued + timedelta(days=1))
    wrong_pack = verifier.verify(replace(pack, sha256="0" * 64), envelope, issued)

    assert not revoked_report.verified
    assert "revoked" in revoked_report.reason
    assert not wrong_pack.verified
    assert "exact current Pack" in wrong_pack.reason


def test_verified_attestation_is_stored_atomically_and_reverified(signed_attestation, tmp_path):
    pack, issued, envelope, verifier, _key = signed_attestation
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = DevicePackAttestationStore(workspace, verifier)
    device = AndroidDevice(
        "private-serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        product="popsicle",
        codename="popsicle",
    )

    imported = store.import_envelope(pack, envelope, now=issued + timedelta(days=1))
    loaded = store.load_exact(pack, device, now=issued + timedelta(days=2))

    assert imported.report.verified
    assert imported.stored_path.startswith("device_pack_attestations/test.pack/")
    assert loaded is not None and loaded.envelope_sha256 == imported.report.envelope_sha256
    assert (
        store.load_exact(
            pack,
            replace(device, model="Different model"),
            now=issued + timedelta(days=2),
        )
        is None
    )

    stored = workspace / imported.stored_path
    assert stat.S_IMODE((workspace / "device_pack_attestations").stat().st_mode) == 0o700
    assert stat.S_IMODE(stored.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(stored.stat().st_mode) == 0o600
    stored.write_text(stored.read_text().replace("2509FPN0BC", "tampered-model"))
    assert store.load_exact(pack, device, now=issued + timedelta(days=2)) is None


def test_untrusted_or_unsafe_attestation_is_never_persisted(signed_attestation, tmp_path):
    pack, issued, envelope, verifier, _key = signed_attestation
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = DevicePackAttestationStore(workspace, verifier)
    data = json.loads(envelope.read_text())
    data["report_sha256"] = "0" * 64
    envelope.write_text(json.dumps(data))

    rejected = store.import_envelope(pack, envelope, now=issued + timedelta(days=1))

    assert not rejected.report.verified
    assert rejected.stored_path == ""
    assert not list((workspace / "device_pack_attestations").rglob("*.romverse.json"))

    oversized = tmp_path / "oversized.romverse"
    oversized.write_bytes(b"x" * (store.MAX_ENVELOPE_BYTES + 1))
    too_large = store.import_envelope(pack, oversized, now=issued)
    assert not too_large.report.verified
    assert "size limit" in too_large.report.reason


def test_attestation_store_rejects_a_linked_storage_root(signed_attestation, tmp_path) -> None:
    pack, issued, envelope, verifier, _key = signed_attestation
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "device_pack_attestations").symlink_to(outside, target_is_directory=True)

    result = DevicePackAttestationStore(workspace, verifier).import_envelope(
        pack,
        envelope,
        now=issued + timedelta(days=1),
    )

    assert not result.report.verified
    assert result.stored_path == ""
    assert "unavailable or unsafe" in result.report.reason
    assert not tuple(outside.iterdir())


def test_release_trust_catalog_is_integrity_checked(signed_attestation, tmp_path):
    _pack_value, _issued, _envelope, _verifier, key = signed_attestation
    trust_root = tmp_path / "trust"
    trust_root.mkdir()
    trusted_public = trust_root / "radforge-release.pem"
    shutil.copyfile(key.public_key_path, trusted_public)
    digest = hashlib.sha256(trusted_public.read_bytes()).hexdigest()
    (trust_root / "index.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "keys": [
                    {
                        "signer_id": key.signer_id,
                        "file": trusted_public.name,
                        "sha256": digest,
                        "revoked": False,
                    }
                ],
            }
        )
    )

    loaded = load_publisher_trust_keys(trust_root)

    assert len(loaded) == 1
    assert loaded[0].signer_id == key.signer_id
    assert loaded[0].public_key_sha256 == digest

    (trust_root / "index.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "keys": [
                    {
                        "signer_id": key.signer_id,
                        "file": "../outside.pem",
                        "sha256": digest,
                    }
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="unsafe"):
        load_publisher_trust_keys(trust_root)


def test_bundled_release_trust_catalog_starts_fail_closed() -> None:
    from importlib.resources import as_file, files

    with as_file(files("romverse.assets").joinpath("device_pack_trust")) as root:
        assert load_publisher_trust_keys(root) == ()
