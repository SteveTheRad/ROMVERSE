from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from romverse.device_packs.models import (
    AvbExecutionPolicy,
    AvbPolicyAuthority,
    AvbPolicyMode,
    DeviceBuildContract,
    DevicePack,
    FirmwareSourceContract,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.local_store import LocalStoreError
from romverse.infrastructure.process import CommandResult
from romverse.rom.build_execution import LocalDeviceBuildExecutor
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.signing_ceremony import OfflineSigningCeremonyService

SIGNED_INFO = """Minimum libavb version:   1.0
Algorithm:                SHA256_RSA4096
Public key (sha1):        8256e695b81d1eb6dd0b1ce5d08b9c73cbb5e5b6
Rollback Index:           42
Flags:                    0
Rollback Index Location:  2
Descriptors:
    Hashtree descriptor:
      Partition Name:        product
    Hashtree descriptor:
      Partition Name:        system
"""


class SignedRunner:
    def run(self, args, timeout=10, cwd=None):
        return CommandResult(tuple(str(value) for value in args), 0, SIGNED_INFO, "")


def _service(tmp_path: Path, monkeypatch, *, authorized: bool = True):
    workspace = tmp_path / "workspace"
    store = RomProjectStore(workspace)
    project = store.create("Signing", "test.signing")
    source = tmp_path / "source.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"exact source")
    imported = store.import_original(project.project_id, source)
    assert imported.original is not None
    policy = AvbExecutionPolicy(
        AvbPolicyMode.SIGNED_CUSTOM_RECHAIN,
        AvbPolicyAuthority.FLASH_VALIDATED,
        "TEST.BUILD",
        "preserve_exact_source",
        "vbmeta_system",
        "SHA256_RSA4096",
        42,
        2,
        0,
        False,
        False,
        True,
        "a",
        "b",
        "a" * 64,
        "8256e695b81d1eb6dd0b1ce5d08b9c73cbb5e5b6",
    )
    if not authorized:
        policy = replace(
            policy,
            mode=AvbPolicyMode.UNLOCKED_UNSIGNED_CHILD,
            authority=AvbPolicyAuthority.REFERENCE_ONLY,
            candidate_algorithm="NONE",
            signing_public_key_sha1="",
        )
    contract = DeviceBuildContract(
        "contract",
        1,
        FirmwareSourceContract("TEST.BUILD", imported.original.sha256, "b" * 64),
        4096,
        65536,
        2,
        False,
        (),
        (),
        ("product", "system"),
        "c" * 64,
        "d" * 64,
        ("product.img", "vbmeta_system.img"),
        avb_execution_policy=policy,
    )
    pack = DevicePack(
        "test.signing",
        "1",
        "Signing Pack",
        1,
        ("test",),
        (),
        (),
        (),
        (),
        "e" * 64,
        contract,
    )
    output_dir = workspace / "working_roms" / project.project_id / "build-candidates" / "one"
    output_dir.mkdir(parents=True)
    output_records = []
    for name, payload in (("product.img", b"p" * 64), ("vbmeta_system.img", b"v" * 64)):
        path = output_dir / name
        path.write_bytes(payload)
        stat = path.stat()
        output_records.append(
            SimpleNamespace(
                name=name,
                path=path.relative_to(workspace).as_posix(),
                size_bytes=stat.st_size,
                modified_ns=stat.st_mtime_ns,
                sha256=hashlib.sha256(payload).hexdigest(),
            )
        )
    build = SimpleNamespace(receipt_digest="f" * 64, outputs=tuple(output_records))
    monkeypatch.setattr(LocalDeviceBuildExecutor, "load_receipt", lambda self, _id: build)
    avbtool = tmp_path / "avbtool"
    avbtool.write_text("tool", encoding="utf-8")
    service = OfflineSigningCeremonyService(
        store, DevicePackRegistry((pack,)), (), avbtool, SignedRunner()
    )
    return service, project.project_id


def test_signing_ceremony_exports_no_private_key_and_verifies_import(tmp_path, monkeypatch):
    service, project_id = _service(tmp_path, monkeypatch)
    export_parent = tmp_path / "external"
    export_parent.mkdir()

    request = service.export_request(project_id, export_parent)

    manifest = json.loads((Path(request.output_path) / service.MANIFEST_NAME).read_text())
    request_path = service.store.projects_root / project_id / service.REQUEST_NAME
    assert stat.S_IMODE(request_path.stat().st_mode) == 0o600
    assert stat.S_IMODE((Path(request.output_path) / service.MANIFEST_NAME).stat().st_mode) == 0o600
    assert manifest["private_key_included"] is False
    assert (
        manifest["expected_public_key_sha1"]
        == SIGNED_INFO.split("Public key (sha1):")[1].split()[0]
    )
    assert {item["name"] for item in manifest["artifacts"]} == set(service.SIGNED_NAMES)

    receipt = service.import_signed_bundle(project_id, Path(request.output_path))

    assert receipt.verified
    assert not receipt.private_key_stored
    assert not receipt.phone_changed
    assert service.load_receipt(project_id) == receipt
    receipt_path = service.store.projects_root / project_id / service.RECEIPT_NAME
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600
    for artifact in receipt.artifacts:
        assert stat.S_IMODE((service.store.workspace / artifact.path).stat().st_mode) == 0o600


def test_signing_receipt_fails_closed_after_artifact_tampering(tmp_path, monkeypatch):
    service, project_id = _service(tmp_path, monkeypatch)
    export_parent = tmp_path / "external"
    export_parent.mkdir()
    request = service.export_request(project_id, export_parent)
    receipt = service.import_signed_bundle(project_id, Path(request.output_path))
    artifact = service.store.workspace / receipt.artifacts[0].path
    artifact.write_bytes(b"x" * artifact.stat().st_size)

    assert service.load_receipt(project_id) is None


def test_signing_receipt_rejects_symlinked_workspace_evidence(tmp_path, monkeypatch):
    service, project_id = _service(tmp_path, monkeypatch)
    export_parent = tmp_path / "external"
    export_parent.mkdir()
    request = service.export_request(project_id, export_parent)
    receipt = service.import_signed_bundle(project_id, Path(request.output_path))
    artifact = service.store.workspace / receipt.artifacts[0].path
    alternate = artifact.with_name("alternate.img")
    alternate.write_bytes(artifact.read_bytes())
    artifact.unlink()
    artifact.symlink_to(alternate.name)

    assert service.load_receipt(project_id) is None


def test_reference_only_policy_cannot_export_signing_request(tmp_path, monkeypatch):
    service, project_id = _service(tmp_path, monkeypatch, authorized=False)
    output = tmp_path / "external"
    output.mkdir()

    eligible, reason = service.eligibility(project_id)
    assert not eligible
    assert "does not authorize" in reason

    with pytest.raises(ProjectError, match="does not authorize"):
        service.export_request(project_id, output)


def test_signing_request_requires_exact_bounded_regular_evidence(tmp_path, monkeypatch):
    service, project_id = _service(tmp_path, monkeypatch)
    export_parent = tmp_path / "external"
    export_parent.mkdir()
    request = service.export_request(project_id, export_parent)
    bundle = Path(request.output_path)
    request_path = service.store.projects_root / project_id / service.REQUEST_NAME
    original = request_path.read_bytes()

    payload = json.loads(original)
    payload["unexpected"] = True
    request_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ProjectError, match="fresh signing request"):
        service.import_signed_bundle(project_id, bundle)

    request_path.write_bytes(b"{" + b" " * service.MAX_REQUEST_BYTES + b"}")
    with pytest.raises(ProjectError, match="fresh signing request"):
        service.import_signed_bundle(project_id, bundle)

    outside = tmp_path / "outside-request.json"
    outside.write_bytes(original)
    request_path.unlink()
    request_path.symlink_to(outside)
    with pytest.raises(ProjectError, match="fresh signing request"):
        service.import_signed_bundle(project_id, bundle)


def test_signing_bundle_requires_bound_manifest_and_regular_images(tmp_path, monkeypatch):
    service, project_id = _service(tmp_path, monkeypatch)
    export_parent = tmp_path / "external"
    export_parent.mkdir()
    request = service.export_request(project_id, export_parent)
    bundle = Path(request.output_path)
    manifest_path = bundle / service.MANIFEST_NAME
    original_manifest = manifest_path.read_bytes()

    manifest = json.loads(original_manifest)
    manifest["unexpected"] = "detached"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ProjectError, match="exact ROMVERSE request manifest"):
        service.import_signed_bundle(project_id, bundle)

    manifest_path.write_bytes(original_manifest)
    outside_manifest = tmp_path / "outside-manifest.json"
    outside_manifest.write_bytes(original_manifest)
    manifest_path.unlink()
    manifest_path.symlink_to(outside_manifest)
    with pytest.raises(ProjectError, match="exact ROMVERSE request manifest"):
        service.import_signed_bundle(project_id, bundle)

    manifest_path.unlink()
    manifest_path.write_bytes(original_manifest)
    image = bundle / "product.img"
    original_image = image.read_bytes()
    target = bundle / "alternate-product.img"
    target.write_bytes(original_image)
    image.unlink()
    image.symlink_to(target.name)
    with pytest.raises(ProjectError, match="cannot be a symbolic link"):
        service.import_signed_bundle(project_id, bundle)


def test_signing_import_rejects_redirected_workspace_evidence_directory(tmp_path, monkeypatch):
    service, project_id = _service(tmp_path, monkeypatch)
    export_parent = tmp_path / "external"
    export_parent.mkdir()
    request = service.export_request(project_id, export_parent)
    outside = tmp_path / "outside-evidence"
    outside.mkdir()
    evidence_parent = service.store.projects_root / project_id / "signing-evidence"
    evidence_parent.symlink_to(outside, target_is_directory=True)

    with pytest.raises(LocalStoreError, match="unsafe or unavailable"):
        service.import_signed_bundle(project_id, Path(request.output_path))

    assert tuple(outside.iterdir()) == ()


def test_signing_receipt_rejects_hostile_records_and_migrates_schema_one(tmp_path, monkeypatch):
    service, project_id = _service(tmp_path, monkeypatch)
    export_parent = tmp_path / "external"
    export_parent.mkdir()
    request = service.export_request(project_id, export_parent)
    receipt = service.import_signed_bundle(project_id, Path(request.output_path))
    receipt_path = service.store.projects_root / project_id / service.RECEIPT_NAME
    original = receipt_path.read_bytes()

    payload = json.loads(original)
    payload["unexpected"] = True
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load_receipt(project_id) is None

    receipt_path.write_bytes(b"{" + b" " * service.MAX_RECEIPT_BYTES + b"}")
    assert service.load_receipt(project_id) is None

    outside = tmp_path / "outside-receipt.json"
    outside.write_bytes(original)
    receipt_path.unlink()
    receipt_path.symlink_to(outside)
    assert service.load_receipt(project_id) is None

    receipt_path.unlink()
    legacy = json.loads(original)
    legacy["schema_version"] = 1
    digest_payload = {
        key: value for key, value in legacy.items() if key not in {"format", "receipt_digest"}
    }
    legacy["receipt_digest"] = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    legacy_digest = legacy["receipt_digest"]
    receipt_path.write_text(json.dumps(legacy), encoding="utf-8")

    migrated = service.load_receipt(project_id)

    assert migrated is not None
    assert migrated.schema_version == 2
    assert migrated.receipt_digest == receipt.receipt_digest
    assert migrated.receipt_digest != legacy_digest
    assert json.loads(receipt_path.read_text())["schema_version"] == 2
