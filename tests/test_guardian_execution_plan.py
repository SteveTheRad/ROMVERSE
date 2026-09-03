from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import asdict, replace

import pytest

from romverse.device_packs.models import (
    DevicePostWriteVerificationContract,
    DeviceWriteTransport,
    PartitionReadbackRule,
    PartitionVerificationMethod,
    PostBootPropertyRule,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.artifact_binding import GuardianArtifactBindingService
from romverse.guardian.execution_plan import (
    ExecutionPlanPhase,
    GuardianExecutionPlanService,
)
from romverse.guardian.manifest_review import GuardianManifestReviewService
from romverse.rom.models import ProjectError
from tests.test_guardian_artifact_binding import _setup


def _prepared(tmp_path, monkeypatch):
    service, project, _pack, report, device, _handoff, _artifact, _build = _setup(
        tmp_path, monkeypatch
    )
    binding = service.prepare(project.project_id)
    manifest = GuardianManifestReviewService(service.store, service.registry).compile(
        project.project_id,
        report,
        device,
        binding=binding,
    )
    plans = GuardianExecutionPlanService(service.store, service.registry)
    return plans, project, report, device, manifest, binding


def _prepared_with_post_write_verification(tmp_path, monkeypatch):
    service, project, pack, report, device, _handoff, _artifact, _build = _setup(
        tmp_path, monkeypatch
    )
    assert pack.build_contract is not None
    write_contract = pack.build_contract.partition_write_contract
    assert write_contract is not None
    write_rule = write_contract.writes[0]
    verification = DevicePostWriteVerificationContract(
        "exact-post-write",
        1,
        write_contract.source_build_id,
        write_contract.attestation_sha256,
        (
            PartitionReadbackRule(
                write_rule.partition,
                write_rule.transport,
                write_rule.target_slot,
                PartitionVerificationMethod.FASTBOOT_FETCH_SHA256,
                4096,
                "b" * 64,
            ),
        ),
        (
            PostBootPropertyRule("sys.boot_completed", "1"),
            PostBootPropertyRule("ro.product.device", "product"),
            PostBootPropertyRule("ro.build.fingerprint", "test/product/build"),
            PostBootPropertyRule("ro.build.version.incremental", "TEST.BUILD"),
            PostBootPropertyRule("ro.build.version.sdk", "37"),
            PostBootPropertyRule("ro.build.version.security_patch", "2026-08-01"),
            PostBootPropertyRule("ro.boot.verifiedbootstate", "orange"),
        ),
        True,
        300,
    )
    upgraded_write_contract = replace(
        write_contract,
        version=2,
        post_write_verification_contract=verification,
    )
    upgraded_pack = replace(
        pack,
        build_contract=replace(
            pack.build_contract,
            partition_write_contract=upgraded_write_contract,
        ),
    )
    registry = DevicePackRegistry((upgraded_pack,))
    binding = GuardianArtifactBindingService(service.store, registry).prepare(project.project_id)
    manifest = GuardianManifestReviewService(service.store, registry).compile(
        project.project_id,
        report,
        device,
        binding=binding,
    )
    plans = GuardianExecutionPlanService(service.store, registry)
    return plans, project, report, device, manifest, binding, verification


def test_execution_plan_derives_exact_redacted_review_only_commands(tmp_path, monkeypatch):
    plans, project, report, device, manifest, binding = _prepared(tmp_path, monkeypatch)

    plan = plans.compile(project.project_id, report, device)

    assert plan.manifest_digest == manifest.manifest_digest
    assert plan.artifact_binding_digest == binding.binding_digest
    assert plan.plan_status == "blocked-missing-exact-post-write-verification"
    assert not plan.final_consent_available
    assert plan.execution_authority == "none"
    assert not plan.phone_changed
    assert not plan.bootloader_relock_allowed
    assert [command.phase for command in plan.commands] == [
        ExecutionPlanPhase.PRECONDITION,
        ExecutionPlanPhase.PRECONDITION,
        ExecutionPlanPhase.PRECONDITION,
        ExecutionPlanPhase.WRITE,
    ]
    assert plan.commands[0].arguments == (
        "-s",
        plans.TARGET_TOKEN,
        "getvar",
        "product",
    )
    assert plan.commands[2].expected_result.startswith("is-userspace must report yes")
    write = plan.commands[-1]
    assert write.arguments == (
        "-s",
        plans.TARGET_TOKEN,
        "flash",
        "super",
        f"{plans.WORKSPACE_TOKEN}/{binding.writes[0].artifact_relative_path}",
    )
    assert write.artifact_sha256 == hashlib.sha256(b"verified super image").hexdigest()
    assert write.phone_changes
    assert device.serial not in json.dumps(asdict(plan))
    assert plans.load(project.project_id, report, device) == plan
    different_device = replace(device, serial="another-private-serial")
    assert plans.load(project.project_id, report, different_device) is None

    root = plans.store.projects_root / project.project_id / "guardian"
    if os.name != "nt":
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        assert stat.S_IMODE((root / plans.LATEST_NAME).stat().st_mode) == 0o600


def test_execution_plan_binds_exact_post_write_contract_but_keeps_consent_locked(
    tmp_path, monkeypatch
):
    plans, project, report, device, _manifest, _binding, verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )

    plan = plans.compile(project.project_id, report, device)
    pack = next(item for item in plans.registry.packs if item.pack_id == plan.device_pack_id)
    assert pack.build_contract is not None
    write_contract = pack.build_contract.partition_write_contract
    assert write_contract is not None
    verification_metadata = plans._verification_metadata(write_contract)

    assert plan.write_contract_version == 2
    assert plan.post_write_verification_contract_id == verification.contract_id
    assert plan.post_write_verification_contract_version == 1
    assert (
        plan.post_write_verification_contract_digest
        == verification_metadata["post_write_verification_contract_digest"]
    )
    assert plan.post_write_readback_count == 1
    assert plan.post_boot_property_count == 7
    assert plan.post_boot_timeout_seconds == 300
    assert plan.plan_status == "ready-for-inert-gateway-contract"
    assert not plan.final_consent_available
    assert plan.execution_authority == "none"
    assert not plan.phone_changed
    assert plans.load(project.project_id, report, device) == plan

    changed_verification = replace(
        verification,
        readbacks=(replace(verification.readbacks[0], expected_sha256="c" * 64),),
    )
    changed_contract = replace(
        write_contract,
        post_write_verification_contract=changed_verification,
    )
    plans.registry = DevicePackRegistry(
        (
            replace(
                pack,
                build_contract=replace(
                    pack.build_contract,
                    partition_write_contract=changed_contract,
                ),
            ),
        )
    )
    assert plans.load(project.project_id, report, device) is None


def test_execution_plan_rehashes_artifacts_and_rejects_changed_current_evidence(
    tmp_path, monkeypatch
):
    plans, project, report, device, _manifest, _binding = _prepared(tmp_path, monkeypatch)
    plan = plans.compile(project.project_id, report, device)
    artifact = plans.store.workspace / plan.commands[-1].artifact_relative_path
    original_stat = artifact.stat()
    artifact.write_bytes(b"tampered super image!")
    os.utime(artifact, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    assert plans.load(project.project_id, report, device) is None
    with pytest.raises(ProjectError, match="rehash"):
        plans.compile(project.project_id, report, device)


def test_execution_plan_rejects_rewritten_command_even_with_new_outer_digest(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding = _prepared(tmp_path, monkeypatch)
    plans.compile(project.project_id, report, device)
    path = plans.store.projects_root / project.project_id / "guardian" / plans.LATEST_NAME
    document = json.loads(path.read_text(encoding="utf-8"))
    document["commands"][-1]["arguments"][-3:] = ["erase", "userdata", "ignored.img"]
    payload = {
        key: value for key, value in document.items() if key not in {"format", "plan_digest"}
    }
    document["plan_digest"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    path.write_text(json.dumps(document), encoding="utf-8")

    assert plans.load(project.project_id, report, device) is None


def test_execution_plan_permanently_rejects_relock_tokens(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding = _prepared(tmp_path, monkeypatch)
    plan = plans.compile(project.project_id, report, device)
    command = replace(
        plan.commands[-1],
        arguments=("-s", plans.TARGET_TOKEN, "flashing", "lock"),
    )
    changed = replace(plan, commands=(*plan.commands[:-1], command))

    with pytest.raises(ProjectError, match="integrity or safety"):
        plans.validate(changed)


def test_execution_plan_rejects_uncontracted_fastboot_options(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding = _prepared(tmp_path, monkeypatch)
    plan = plans.compile(project.project_id, report, device)
    write = plan.commands[-1]
    command = replace(
        write,
        arguments=(
            "-s",
            plans.TARGET_TOKEN,
            "--force",
            "flash",
            write.partition,
            write.arguments[-1],
        ),
    )
    changed = replace(plan, commands=(*plan.commands[:-1], command))

    with pytest.raises(ProjectError, match="integrity or safety"):
        plans.validate(changed)


def test_execution_plan_previews_explicit_slots_and_manual_mode_boundaries(tmp_path, monkeypatch):
    plans, _project, _report, _device, manifest, _binding = _prepared(tmp_path, monkeypatch)
    first = replace(manifest.partition_writes[0], target_slot="a")
    second = replace(
        first,
        order=2,
        partition="boot",
        artifact_name="boot.img",
        artifact_relative_path="working/example/build-candidates/plan/boot.img",
        artifact_sha256="a" * 64,
        transport=DeviceWriteTransport.FASTBOOT,
        target_slot="none",
    )

    commands = plans._commands(replace(manifest, partition_writes=(first, second)))

    assert commands[3].arguments == (
        "-s",
        plans.TARGET_TOKEN,
        "getvar",
        "has-slot:super",
    )
    assert commands[4].arguments[-5:] == (
        "--slot",
        "a",
        "flash",
        "super",
        f"{plans.WORKSPACE_TOKEN}/{first.artifact_relative_path}",
    )
    assert commands[5].arguments == (
        "-s",
        plans.TARGET_TOKEN,
        "getvar",
        "is-userspace",
    )
    assert commands[5].expected_result.startswith("is-userspace must report no")
    assert commands[6].phase is ExecutionPlanPhase.WRITE
    flattened = " ".join(token for command in commands for token in command.arguments)
    assert "reboot" not in flattened
    assert "erase" not in flattened
    assert "flashing lock" not in flattened


def test_execution_plan_rejects_stale_readiness_before_compiling(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding = _prepared(tmp_path, monkeypatch)
    changed = replace(
        report,
        gates=(replace(report.gates[0], evidence="changed evidence"),),
    )

    with pytest.raises(ProjectError, match="current artifact-bound"):
        plans.compile(project.project_id, changed, device)


def test_execution_plan_rejects_wrong_field_shape_and_oversized_storage(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding = _prepared(tmp_path, monkeypatch)
    plans.compile(project.project_id, report, device)
    path = plans.store.projects_root / project.project_id / "guardian" / plans.LATEST_NAME
    document = json.loads(path.read_text(encoding="utf-8"))
    document["unexpected"] = True
    path.write_text(json.dumps(document), encoding="utf-8")
    assert plans.load(project.project_id, report, device) is None

    path.write_bytes(b"x" * (plans.MAX_BYTES + 1))
    assert plans.load(project.project_id, report, device) is None


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("schema_version", True),
        ("write_contract_id", "forged-contract"),
        ("write_attestation_sha256", "9" * 64),
        ("post_write_verification_contract_version", True),
        ("post_write_readback_count", 1),
    ),
)
def test_execution_plan_rejects_resealed_type_or_contract_mutation(
    tmp_path, monkeypatch, field, value
):
    plans, project, report, device, _manifest, _binding = _prepared(tmp_path, monkeypatch)
    plans.compile(project.project_id, report, device)
    path = plans.store.projects_root / project.project_id / "guardian" / plans.LATEST_NAME
    document = json.loads(path.read_text(encoding="utf-8"))
    document[field] = value
    payload = {
        key: value for key, value in document.items() if key not in {"format", "plan_digest"}
    }
    document["plan_digest"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    path.write_text(json.dumps(document), encoding="utf-8")

    assert plans.load(project.project_id, report, device) is None
