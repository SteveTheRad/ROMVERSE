from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import replace
from types import SimpleNamespace

import pytest

from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.models import (
    AvbExecutionPolicy,
    AvbPolicyAuthority,
    AvbPolicyMode,
    CapabilityStatus,
    DeviceBuildContract,
    DevicePack,
    DeviceWriteContract,
    DeviceWriteTransport,
    FirmwareSourceContract,
    PackCapability,
    PartitionWriteRule,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.artifact_binding import GuardianArtifactBindingService
from romverse.guardian.flash_handoff import FlashMode, GuardianFlashHandoffService
from romverse.guardian.manifest_review import (
    GuardianManifestReviewService,
    ManifestReviewState,
)
from romverse.rom.build_execution import LocalDeviceBuildExecutor
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.readiness import BuildGate, BuildReadinessReport, GateStatus
from romverse.ui.rom_studio import GuardianReviewWorker


def _setup(tmp_path, monkeypatch):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Binding", "test.binding")
    source = tmp_path / "firmware.zip"
    source.write_bytes(b"exact firmware")
    project = store.import_original(project.project_id, source)
    assert project.original is not None
    envelope_sha256 = "a" * 64
    policy = AvbExecutionPolicy(
        AvbPolicyMode.UNLOCKED_UNSIGNED_CHILD,
        AvbPolicyAuthority.FLASH_VALIDATED,
        "TEST.BUILD",
        "preserve_exact_source",
        "vbmeta_system",
        "NONE",
        0,
        0,
        0,
        True,
        True,
        True,
        "a",
        "b",
        envelope_sha256,
    )
    write_contract = DeviceWriteContract(
        "exact-writes",
        1,
        "TEST.BUILD",
        envelope_sha256,
        True,
        True,
        True,
        True,
        (
            PartitionWriteRule(
                "super",
                "super.img",
                DeviceWriteTransport.FASTBOOTD,
                "none",
                True,
            ),
        ),
    )
    contract = DeviceBuildContract(
        "exact-build",
        2,
        FirmwareSourceContract("TEST.BUILD", project.original.sha256, "b" * 64),
        4096,
        512,
        2,
        False,
        (),
        (),
        (),
        "c" * 64,
        "d" * 64,
        ("super.img",),
        avb_execution_policy=policy,
        partition_write_contract=write_contract,
    )
    pack = DevicePack(
        "test.binding",
        "1.0.0",
        "Test Binding Pack",
        10,
        ("test",),
        ("phone",),
        ("product",),
        (
            PackCapability(
                "firmware.operations",
                "Firmware",
                CapabilityStatus.SUPPORTED,
                "model_specific",
                "Exact fixture",
            ),
        ),
        (),
        "e" * 64,
        contract,
    )
    registry = DevicePackRegistry((pack,))
    artifact = store.working_root / project.project_id / "build-candidates" / "plan" / "super.img"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"verified super image")
    artifact_stat = artifact.stat()
    output = SimpleNamespace(
        name="super.img",
        path=artifact.relative_to(store.workspace).as_posix(),
        size_bytes=artifact_stat.st_size,
        modified_ns=artifact_stat.st_mtime_ns,
        sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
    )
    build = SimpleNamespace(
        contract_id=contract.contract_id,
        receipt_digest="f" * 64,
        outputs=(output,),
    )
    monkeypatch.setattr(LocalDeviceBuildExecutor, "load_receipt", lambda self, _id: build)
    report = BuildReadinessReport(
        1,
        "1" * 32,
        project.project_id,
        "2026-08-31T00:00:00+00:00",
        (
            BuildGate(
                "device-pack-flash",
                "Exact flash contract",
                "Flash",
                GateStatus.PASS,
                "verified",
                "flash",
            ),
        ),
        True,
        True,
        True,
        True,
        True,
        (),
        (),
        "2" * 64,
    )
    device = AndroidDevice(
        "private-serial",
        DeviceState.DEVICE,
        manufacturer="test",
        model="phone",
        marketing_name="Test Phone",
        product="product",
        codename="product",
    )
    handoff = GuardianFlashHandoffService(store).prepare(
        project.project_id,
        report,
        device,
        FlashMode.DIRTY_KEEP_DATA,
    )
    service = GuardianArtifactBindingService(store, registry)
    return service, project, pack, report, device, handoff, artifact, build


def test_guardian_binding_rehashes_exact_artifact_and_grants_no_authority(tmp_path, monkeypatch):
    service, project, _pack, _report, _device, handoff, artifact, build = _setup(
        tmp_path, monkeypatch
    )
    progress: list[int] = []

    receipt = service.prepare(project.project_id, progress.append)

    assert progress[0] == 0
    assert progress[-1] == 100
    assert receipt.handoff_digest == handoff.handoff_digest
    assert receipt.local_build_receipt_digest == build.receipt_digest
    assert receipt.execution_authority == "review-only"
    assert receipt.command_manifest == ()
    assert not receipt.phone_changed
    assert not receipt.bootloader_relock_allowed
    assert len(receipt.writes) == 1
    bound = receipt.writes[0]
    assert bound.partition == "super"
    assert bound.artifact_sha256 == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert bound.transport is DeviceWriteTransport.FASTBOOTD
    assert service.load(project.project_id) == receipt
    root = service.store.projects_root / project.project_id / "guardian"
    if os.name != "nt":
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        assert stat.S_IMODE((root / service.LATEST_NAME).stat().st_mode) == 0o600


def test_manifest_renders_bound_hashes_but_keeps_commands_and_consent_locked(tmp_path, monkeypatch):
    service, project, _pack, report, device, _handoff, _artifact, _build = _setup(
        tmp_path, monkeypatch
    )
    binding = service.prepare(project.project_id)
    manifests = GuardianManifestReviewService(service.store, service.registry)

    manifest = manifests.compile(project.project_id, report, device, binding=binding)

    assert manifest.review_status == "artifact-bound-review-only"
    assert manifest.artifact_binding_digest == binding.binding_digest
    assert manifest.partition_writes == binding.writes
    states = {check.check_id: check.state for check in manifest.checks}
    assert states["partition-write-contract"] is ManifestReviewState.PASS
    assert states["current-artifact-binding"] is ManifestReviewState.PASS
    assert states["execution-manifest"] is ManifestReviewState.BLOCKED
    assert manifest.command_manifest == ()
    assert not manifest.final_consent_available
    assert manifest.execution_authority == "none"
    assert manifests.load(project.project_id) == manifest

    latest = service.store.projects_root / project.project_id / "guardian" / manifests.LATEST_NAME
    document = json.loads(latest.read_text(encoding="utf-8"))
    document["partition_writes"][0]["artifact_sha256"] = "9" * 64
    digest_payload = {
        key: value for key, value in document.items() if key not in {"format", "manifest_digest"}
    }
    document["manifest_digest"] = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    latest.write_text(json.dumps(document), encoding="utf-8")
    assert manifests.load(project.project_id) is None


def test_guardian_review_worker_reports_real_hash_progress_without_phone_commands(
    tmp_path, monkeypatch
):
    service, project, _pack, report, device, _handoff, _artifact, _build = _setup(
        tmp_path, monkeypatch
    )
    completed = []
    failed = []
    progress = []
    binding = service.prepare(project.project_id)

    def prepare_with_measured_progress(_project_id, publish):
        for value in (0, 17, 63, 100):
            publish(value)
        return binding

    monkeypatch.setattr(service, "prepare", prepare_with_measured_progress)
    worker = GuardianReviewWorker(
        service,
        GuardianManifestReviewService(service.store, service.registry),
        project.project_id,
        report,
        device,
    )
    worker.signals.complete.connect(completed.append)
    worker.signals.failed.connect(failed.append)
    worker.signals.progress.connect(progress.append)

    worker.run()

    assert failed == []
    assert len(completed) == 1
    assert completed[0].partition_writes
    assert completed[0].command_manifest == ()
    assert worker.execution_plan is not None
    assert worker.execution_plan.plan_status == "blocked-missing-exact-post-write-verification"
    assert not worker.execution_plan.final_consent_available
    assert worker.execution_plan.execution_authority == "none"
    assert worker.gateway_contract is None
    assert progress == [0, 8, 32, 50, 100]
    assert progress == sorted(progress)
    assert 90 not in progress
    assert 94 not in progress


def test_guardian_binding_rejects_same_size_same_mtime_artifact_tampering(tmp_path, monkeypatch):
    service, project, _pack, _report, _device, _handoff, artifact, _build = _setup(
        tmp_path, monkeypatch
    )
    service.prepare(project.project_id)
    before = artifact.stat()
    artifact.write_bytes(b"X" * before.st_size)
    os.utime(artifact, ns=(before.st_atime_ns, before.st_mtime_ns))

    assert service.load(project.project_id) is None
    with pytest.raises(ProjectError, match="changed after"):
        service.prepare(project.project_id)


def test_guardian_binding_rejects_links_stale_handoff_and_resealed_relock(tmp_path, monkeypatch):
    service, project, _pack, report, device, _handoff, artifact, _build = _setup(
        tmp_path, monkeypatch
    )
    receipt = service.prepare(project.project_id)
    latest = service.store.projects_root / project.project_id / "guardian" / service.LATEST_NAME

    document = json.loads(latest.read_text(encoding="utf-8"))
    document["bootloader_relock_allowed"] = True
    digest_payload = {
        key: value for key, value in document.items() if key not in {"format", "binding_digest"}
    }
    document["binding_digest"] = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    latest.write_text(json.dumps(document), encoding="utf-8")
    assert service.load(project.project_id) is None

    service.prepare(project.project_id)
    alternate = artifact.with_name("alternate.img")
    alternate.write_bytes(artifact.read_bytes())
    artifact.unlink()
    artifact.symlink_to(alternate.name)
    assert service.load(project.project_id) is None

    artifact.unlink()
    artifact.write_bytes(alternate.read_bytes())
    os.utime(
        artifact,
        ns=(receipt.writes[0].artifact_modified_ns, receipt.writes[0].artifact_modified_ns),
    )
    GuardianFlashHandoffService(service.store).prepare(
        project.project_id,
        report,
        device,
        FlashMode.CLEAN_WIPE_DATA,
    )
    assert service.load(project.project_id) is None


def test_guardian_binding_enforces_declared_data_mode_and_signed_artifact_provenance(
    tmp_path, monkeypatch
):
    service, project, pack, _report, _device, _handoff, _artifact, _build = _setup(
        tmp_path, monkeypatch
    )
    assert pack.build_contract is not None
    write_contract = pack.build_contract.partition_write_contract
    assert write_contract is not None
    no_keep = replace(write_contract, preserve_user_data_supported=False)
    no_keep_pack = replace(
        pack,
        build_contract=replace(pack.build_contract, partition_write_contract=no_keep),
    )
    blocked_mode = GuardianArtifactBindingService(
        service.store,
        DevicePackRegistry((no_keep_pack,)),
    )
    with pytest.raises(ProjectError, match="does not support keeping user data"):
        blocked_mode.prepare(project.project_id)

    policy = pack.build_contract.avb_execution_policy
    assert policy is not None
    signed_policy = replace(
        policy,
        mode=AvbPolicyMode.SIGNED_CUSTOM_RECHAIN,
        candidate_algorithm="SHA256_RSA4096",
        signing_public_key_sha1="3" * 40,
    )
    signed_pack = replace(
        pack,
        build_contract=replace(pack.build_contract, avb_execution_policy=signed_policy),
    )
    signed_service = GuardianArtifactBindingService(
        service.store,
        DevicePackRegistry((signed_pack,)),
    )
    with pytest.raises(ProjectError, match="cannot prove a signed composite image"):
        signed_service.prepare(project.project_id)


def test_guardian_binding_storage_rejects_extra_oversized_and_linked_records(tmp_path, monkeypatch):
    service, project, _pack, _report, _device, _handoff, _artifact, _build = _setup(
        tmp_path, monkeypatch
    )
    service.prepare(project.project_id)
    latest = service.store.projects_root / project.project_id / "guardian" / service.LATEST_NAME
    original = latest.read_bytes()

    document = json.loads(original)
    document["unexpected"] = True
    latest.write_text(json.dumps(document), encoding="utf-8")
    assert service.load(project.project_id) is None

    latest.write_bytes(b"{" + b" " * service.MAX_BYTES + b"}")
    assert service.load(project.project_id) is None

    outside = tmp_path / "outside-binding.json"
    outside.write_bytes(original)
    latest.unlink()
    latest.symlink_to(outside)
    assert service.load(project.project_id) is None
