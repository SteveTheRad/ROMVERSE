from __future__ import annotations

import base64
import hashlib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import romverse.rom.release_forge as release_forge_module
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.process import CommandResult
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.build_contracts import DeviceBuildContractService
from romverse.rom.build_execution import BuildOutputReceipt, LocalDeviceBuildExecutor
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.recovery_evidence import (
    RecoveryEvidenceAssessment,
    RecoveryEvidenceService,
)
from romverse.rom.release_forge import (
    ReleaseForgeService,
    ReleasePackageKind,
    ReleaseTier,
    _canonical,
    _digest,
)
from romverse.rom.simulation import RomSimulationService


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fixture(tmp_path: Path, monkeypatch, *, artifact_name: str = "super.img"):
    workspace = tmp_path / "workspace"
    store = RomProjectStore(workspace)
    source = tmp_path / "firmware.zip"
    source.write_bytes(b"exact protected source")
    project = store.create("Release Forge", "test.release")
    project = store.import_original(project.project_id, source)
    assert project.original is not None
    pack = SimpleNamespace(
        pack_id="test.release",
        sha256="a" * 64,
        build_contract=SimpleNamespace(
            source=SimpleNamespace(archive_sha256=project.original.sha256)
        ),
    )
    registry = DevicePackRegistry((pack,))
    output_path = (
        workspace / "working_roms" / project.project_id / "build-candidates" / "one" / artifact_name
    )
    output_path.parent.mkdir(parents=True)
    output_path.write_bytes(b"verified release artifact")
    output = BuildOutputReceipt(
        artifact_name,
        output_path.relative_to(workspace).as_posix(),
        output_path.stat().st_size,
        output_path.stat().st_mtime_ns,
        _sha(output_path.read_bytes()),
    )
    state = {
        "build": SimpleNamespace(receipt_digest="b" * 64, outputs=(output,)),
    }
    simulation = SimpleNamespace(
        successful=True,
        expert_edits=(),
        receipt_digest="c" * 64,
    )
    mission = SimpleNamespace(mission_digest="d" * 64)
    monkeypatch.setattr(
        LocalDeviceBuildExecutor,
        "load_receipt",
        lambda self, _project_id: state["build"],
    )
    monkeypatch.setattr(
        RomSimulationService,
        "load",
        lambda self, _project_id: simulation,
    )
    monkeypatch.setattr(
        RomSimulationService,
        "load_mission",
        lambda self, _project_id: mission,
    )
    monkeypatch.setattr(
        RecoveryEvidenceService,
        "assess",
        lambda self, _project_id: RecoveryEvidenceAssessment(
            True,
            True,
            True,
            ("Exact stock recovery package verified.",),
        ),
    )
    service = ReleaseForgeService(store, registry)
    return service, project.project_id, output_path, state


def test_development_release_is_deterministic_local_and_tamper_evident(
    tmp_path,
    monkeypatch,
):
    service, project_id, _artifact, _state = _fixture(tmp_path, monkeypatch)

    assessment = service.assess(
        project_id,
        ReleaseTier.DEVELOPMENT,
        ReleasePackageKind.FULL,
    )
    plan = service.prepare_plan(
        project_id,
        "1.2.3-dev.1",
        ReleaseTier.DEVELOPMENT,
        ReleasePackageKind.FULL,
        ("First development capsule", "Digital Twin rehearsal passed"),
    )
    receipt = service.create_bundle(plan)

    assert assessment.ready
    assert not plan.phone_changed
    assert plan.publishing_authority == "none"
    assert not receipt.published
    assert not receipt.phone_changed
    assert service.verify_bundle(receipt) is None
    archive_path = service.store.workspace / receipt.archive_path
    with zipfile.ZipFile(archive_path) as archive:
        assert set(archive.namelist()) == {
            service.MANIFEST_MEMBER,
            service.PLAN_MEMBER,
            service.CERTIFICATE_MEMBER,
            service.CHECKSUM_MEMBER,
            service.CHANGELOG_MEMBER,
            service.INSTALL_MEMBER,
            "artifacts/super.img",
        }
        manifest = json.loads(archive.read(service.MANIFEST_MEMBER))
        assert manifest["safety"]["publishing_authority"] == "none"
        assert manifest["safety"]["phone_changed"] is False

    archive_path.write_bytes(archive_path.read_bytes() + b"tampered")
    assert "hash or size changed" in service.verify_bundle(receipt)


def test_public_certificate_is_signed_externally_and_reverified(
    tmp_path,
    monkeypatch,
):
    service, project_id, artifact, _state = _fixture(
        tmp_path,
        monkeypatch,
        artifact_name="product.img",
    )
    signed = SimpleNamespace(
        name="product.img",
        path=artifact.relative_to(service.store.workspace).as_posix(),
        size_bytes=artifact.stat().st_size,
        sha256=_sha(artifact.read_bytes()),
    )
    signing = SimpleNamespace(
        receipt_digest="e" * 64,
        verified=True,
        artifacts=(signed,),
    )
    monkeypatch.setattr(service, "_load_signing", lambda _project_id: signing)
    monkeypatch.setattr(service, "_first_light_passed", lambda _project_id: True)
    plan = service.prepare_plan(
        project_id,
        "2.0.0",
        ReleaseTier.PUBLIC,
        ReleasePackageKind.FULL,
        ("Verified public candidate",),
    )
    private = Ed25519PrivateKey.generate()
    public_path = tmp_path / "release-public.pem"
    public_path.write_bytes(
        private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    signature = private.sign(
        service.CERTIFICATE_DOMAIN + _canonical(service._certificate_payload_from_plan(plan))
    )
    envelope = tmp_path / "signed-certificate.json"
    envelope.write_text(
        json.dumps(
            {
                "format": service.SIGNATURE_FORMAT,
                "schema_version": 1,
                "release_id": plan.release_id,
                "key_id": "release-key-01",
                "certificate_payload_digest": plan.certificate_payload_digest,
                "signature_base64": base64.b64encode(signature).decode("ascii"),
            }
        ),
        encoding="utf-8",
    )

    imported = service.import_certificate_signature(
        plan,
        envelope,
        public_path,
        "release-key-01",
    )
    receipt = service.create_bundle(plan)

    assert imported.verified
    assert not imported.private_key_stored
    assert receipt.signed_certificate
    assert service.verify_bundle(receipt) is None

    stored_path = service.store.projects_root / project_id / service.SIGNATURE_NAME
    stored = json.loads(stored_path.read_text(encoding="utf-8"))
    stored["signature_base64"] = base64.b64encode(bytes(64)).decode("ascii")
    unsigned = {key: value for key, value in stored.items() if key != "format"}
    unsigned.pop("receipt_digest")
    stored["receipt_digest"] = _digest(unsigned)
    stored_path.write_text(json.dumps(stored), encoding="utf-8")
    assert service.load_certificate_signature(plan) is None


def test_release_plan_rejects_artifact_change_and_secret_leak(tmp_path, monkeypatch):
    service, project_id, artifact, _state = _fixture(tmp_path, monkeypatch)
    secret = service.store.working_root / project_id / "tree" / ".env"
    secret.parent.mkdir(parents=True)
    secret.write_text("TOKEN=not-for-release", encoding="utf-8")

    assessment = service.assess(
        project_id,
        ReleaseTier.DEVELOPMENT,
        ReleasePackageKind.FULL,
    )

    assert any(gate.gate_id == "security" and gate.state == "blocked" for gate in assessment.gates)
    with pytest.raises(ProjectError, match="Accidental-secret"):
        service.prepare_plan(
            project_id,
            "1.0.0",
            ReleaseTier.DEVELOPMENT,
            ReleasePackageKind.FULL,
            ("Blocked secret test",),
        )

    secret.unlink()
    plan = service.prepare_plan(
        project_id,
        "1.0.0",
        ReleaseTier.DEVELOPMENT,
        ReleasePackageKind.FULL,
        ("Clean plan",),
    )
    artifact.write_bytes(b"changed but same role")
    with pytest.raises(ProjectError, match="evidence changed|artifact changed"):
        service.create_bundle(plan)


def test_incremental_package_contains_only_changed_artifacts(tmp_path, monkeypatch):
    service, project_id, artifact, state = _fixture(
        tmp_path,
        monkeypatch,
        artifact_name="product.img",
    )
    extra = artifact.with_name("boot.img")
    extra.write_bytes(b"unchanged boot")
    boot = BuildOutputReceipt(
        "boot.img",
        extra.relative_to(service.store.workspace).as_posix(),
        extra.stat().st_size,
        extra.stat().st_mtime_ns,
        _sha(extra.read_bytes()),
    )
    state["build"] = SimpleNamespace(
        receipt_digest=state["build"].receipt_digest,
        outputs=(state["build"].outputs[0], boot),
    )
    base = service.prepare_plan(
        project_id,
        "1.0.0",
        ReleaseTier.DEVELOPMENT,
        ReleasePackageKind.FULL,
        ("Base",),
    )
    service.create_bundle(base)
    artifact.write_bytes(b"changed product")
    changed = BuildOutputReceipt(
        "product.img",
        artifact.relative_to(service.store.workspace).as_posix(),
        artifact.stat().st_size,
        artifact.stat().st_mtime_ns,
        _sha(artifact.read_bytes()),
    )
    state["build"] = SimpleNamespace(
        receipt_digest="f" * 64,
        outputs=(changed, boot),
    )

    incremental = service.prepare_plan(
        project_id,
        "1.0.1",
        ReleaseTier.DEVELOPMENT,
        ReleasePackageKind.INCREMENTAL,
        ("Changed product",),
        base_plan=base,
    )

    assert [item.name for item in incremental.artifacts] == ["product.img"]
    assert incremental.unchanged_artifacts == (("boot.img", boot.sha256),)


def test_signed_super_is_reassembled_unpacked_and_bound_to_current_signing(
    tmp_path,
    monkeypatch,
):
    service, project_id, product, state = _fixture(
        tmp_path,
        monkeypatch,
        artifact_name="product.img",
    )
    original_super = product.with_name("super.img")
    original_super.write_bytes(b"pre-signing super")
    super_output = BuildOutputReceipt(
        "super.img",
        original_super.relative_to(service.store.workspace).as_posix(),
        original_super.stat().st_size,
        original_super.stat().st_mtime_ns,
        _sha(original_super.read_bytes()),
    )
    state["build"] = SimpleNamespace(
        receipt_digest="b" * 64,
        outputs=(state["build"].outputs[0], super_output),
    )
    signed = SimpleNamespace(
        name="product.img",
        path=product.relative_to(service.store.workspace).as_posix(),
        size_bytes=product.stat().st_size,
        sha256=_sha(product.read_bytes()),
    )
    signing = SimpleNamespace(
        receipt_digest="e" * 64,
        verified=True,
        artifacts=(signed,),
    )
    monkeypatch.setattr(service, "_load_signing", lambda _project_id: signing)
    step = SimpleNamespace(
        step_id="assemble-super",
        arguments=(
            "--metadata-size",
            "65536",
            "--device",
            "super:4096",
            "--image",
            f"product_a={product.relative_to(service.store.workspace).as_posix()}",
            "--sparse",
            "--output",
            original_super.relative_to(service.store.workspace).as_posix(),
        ),
        outputs=(original_super.relative_to(service.store.workspace).as_posix(),),
    )
    monkeypatch.setattr(
        DeviceBuildContractService,
        "load",
        lambda self, _project_id: SimpleNamespace(steps=(step,)),
    )
    tools = []
    for name, filename in (
        ("LP Make", "lpmake"),
        ("LP Unpack", "lpunpack"),
        ("LP Dump", "lpdump"),
        ("simg2img", "simg2img"),
    ):
        path = tmp_path / filename
        path.write_text("tool", encoding="utf-8")
        tools.append(ToolStatus(name, True, str(path), "test"))
    service.tool_statuses = tuple(tools)

    class AssemblyRunner:
        def run(self, args, timeout=10, cwd=None):
            executable = Path(args[0]).name
            if executable == "lpmake":
                Path(args[args.index("--output") + 1]).write_bytes(b"signed sparse super")
            elif executable == "simg2img":
                Path(args[2]).write_bytes(b"raw super")
            elif executable == "lpunpack":
                output = Path(args[2])
                (output / "product_a.img").write_bytes(product.read_bytes())
            return CommandResult(tuple(str(value) for value in args), 0, "verified", "")

    monkeypatch.setattr(release_forge_module, "SubprocessRunner", AssemblyRunner)

    receipt = service.assemble_signed_super(project_id)

    assert receipt.verified
    assert not receipt.phone_changed
    assert receipt.inputs[0].signed
    assert service.load_signed_assembly(project_id) == receipt
    (service.store.workspace / receipt.super_path).write_bytes(b"tampered")
    assert service.load_signed_assembly(project_id) is None
