from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import asdict, replace

import pytest

from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.artifact_binding import GuardianArtifactBindingService
from romverse.guardian.execution_gateway_contract import (
    GatewayEvidenceKind,
    GatewayStepPhase,
    GuardianExecutionGatewayContractService,
)
from romverse.guardian.manifest_review import GuardianManifestReviewService
from romverse.rom.models import ProjectError
from tests.test_guardian_execution_plan import (
    _prepared,
    _prepared_with_post_write_verification,
)


class _NoRuntimeRunner:
    def run(self, command, timeout=10):
        raise AssertionError(f"The inert gateway contract tried to run {command!r}")


def _service(plans):
    return GuardianExecutionGatewayContractService(
        plans.store,
        plans.registry,
        runner=_NoRuntimeRunner(),
    )


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_gateway_contract_requires_exact_schema_two_verification(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding = _prepared(tmp_path, monkeypatch)
    plans.compile(project.project_id, report, device)

    with pytest.raises(ProjectError, match="schema-2|execution plan"):
        _service(plans).compile(project.project_id, report, device)


def test_gateway_contract_compiles_typed_inert_result_template(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding, verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    plan = plans.compile(project.project_id, report, device)
    service = _service(plans)

    contract = service.compile(project.project_id, report, device)

    assert contract.plan_id == plan.plan_id
    assert contract.plan_digest == plan.plan_digest
    assert (
        contract.post_write_verification_contract_digest
        == plan.post_write_verification_contract_digest
    )
    assert contract.result_receipt_schema_version == 1
    assert contract.step_count == len(contract.steps)
    assert contract.write_count == 1
    assert contract.readback_count == 1
    assert contract.post_boot_property_count == len(verification.post_boot_properties)
    assert contract.contract_status == (
        "blocked-missing-signed-transition-recovery-and-final-consent"
    )
    assert not contract.final_consent_available
    assert contract.execution_authority == "none"
    assert not contract.runtime_invoked
    assert not contract.phone_changed

    phases = [step.phase for step in contract.steps]
    assert phases[:4] == [
        GatewayStepPhase.PRECONDITION,
        GatewayStepPhase.PRECONDITION,
        GatewayStepPhase.PRECONDITION,
        GatewayStepPhase.WRITE,
    ]
    assert phases[4] is GatewayStepPhase.READBACK
    assert all(phase is GatewayStepPhase.POST_BOOT for phase in phases[5:])

    readback = contract.steps[4]
    assert readback.arguments == (
        "-s",
        service.TARGET_TOKEN,
        "fetch",
        verification.readbacks[0].partition,
        f"{service.PRIVATE_OUTPUT_TOKEN}/{readback.output_relative_path}",
    )
    assert readback.evidence_kind is GatewayEvidenceKind.FILE_SIZE_AND_SHA256
    assert readback.expected_size_bytes == verification.readbacks[0].expected_size_bytes
    assert readback.expected_sha256 == verification.readbacks[0].expected_sha256
    assert not readback.phone_changes

    property_steps = contract.steps[5:]
    assert {step.property_name: step.expected_value for step in property_steps} == {
        rule.property_name: rule.expected_value for rule in verification.post_boot_properties
    }
    assert all(
        step.arguments
        == (
            "-s",
            service.ADB_TARGET_TOKEN,
            "shell",
            "getprop",
            step.property_name,
        )
        for step in property_steps
    )
    serialized = json.dumps(asdict(contract))
    serialized_commands = " ".join(token for step in contract.steps for token in step.arguments)
    assert device.serial not in serialized
    assert "reboot" not in serialized_commands
    assert "erase" not in serialized_commands
    assert "flashing lock" not in serialized_commands
    assert service.load(project.project_id, report, device) == contract

    path = service.store.projects_root / project.project_id / "guardian" / service.LATEST_NAME
    if os.name != "nt":
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_gateway_contract_supports_explicit_readback_slot(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding, verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    pack = plans.registry.packs[0]
    assert pack.build_contract is not None
    write_contract = pack.build_contract.partition_write_contract
    assert write_contract is not None
    slotted_write = replace(write_contract.writes[0], target_slot="a")
    slotted_verification = replace(
        verification,
        readbacks=(replace(verification.readbacks[0], target_slot="a"),),
    )
    plans.registry = DevicePackRegistry(
        (
            replace(
                pack,
                build_contract=replace(
                    pack.build_contract,
                    partition_write_contract=replace(
                        write_contract,
                        writes=(slotted_write,),
                        post_write_verification_contract=slotted_verification,
                    ),
                ),
            ),
        )
    )
    binding_service = GuardianArtifactBindingService(plans.store, plans.registry)
    binding = binding_service.prepare(project.project_id)
    manifest_service = GuardianManifestReviewService(plans.store, plans.registry)
    manifest_service.compile(project.project_id, report, device, binding=binding)
    plan = plans.compile(project.project_id, report, device)

    contract = _service(plans).compile(project.project_id, report, device)
    readback = next(step for step in contract.steps if step.phase is GatewayStepPhase.READBACK)

    assert plan.write_contract_version == 2
    assert readback.target_slot == "a"
    assert readback.arguments[2:5] == ("--slot", "a", "fetch")


def test_gateway_steps_read_back_each_partition_immediately(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding, verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    plan = plans.compile(project.project_id, report, device)
    first_write = plan.commands[-1]
    second_path = "working/example/build-candidates/plan/boot.img"
    second_write = replace(
        first_write,
        order=first_write.order + 1,
        operation_id="guardian.write.02.boot",
        arguments=(
            "-s",
            plans.TARGET_TOKEN,
            "flash",
            "boot",
            f"{plans.WORKSPACE_TOKEN}/{second_path}",
        ),
        partition="boot",
        artifact_relative_path=second_path,
        artifact_sha256="c" * 64,
    )
    second_readback = replace(
        verification.readbacks[0],
        partition="boot",
        expected_sha256="d" * 64,
    )

    steps = GuardianExecutionGatewayContractService._steps(
        replace(plan, commands=(*plan.commands, second_write)),
        replace(verification, readbacks=(*verification.readbacks, second_readback)),
    )

    first_index = next(
        index for index, step in enumerate(steps) if step.phase is GatewayStepPhase.WRITE
    )
    assert [step.phase for step in steps[first_index : first_index + 4]] == [
        GatewayStepPhase.WRITE,
        GatewayStepPhase.READBACK,
        GatewayStepPhase.WRITE,
        GatewayStepPhase.READBACK,
    ]
    assert steps[first_index + 1].partition == first_write.partition
    assert steps[first_index + 3].partition == second_write.partition


def test_gateway_contract_rejects_resealed_step_substitution(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding, _verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    plans.compile(project.project_id, report, device)
    service = _service(plans)
    service.compile(project.project_id, report, device)
    path = service.store.projects_root / project.project_id / "guardian" / service.LATEST_NAME
    document = json.loads(path.read_text(encoding="utf-8"))
    document["steps"][0]["expected_value"] = "forged-product"
    document["steps_digest"] = _digest({"steps": document["steps"]})
    payload = {
        key: value for key, value in document.items() if key not in {"format", "contract_digest"}
    }
    document["contract_digest"] = _digest(payload)
    path.write_text(json.dumps(document), encoding="utf-8")

    assert service.load(project.project_id, report, device) is None


def test_gateway_contract_rejects_stale_phone_and_changed_artifact(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding, _verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    plan = plans.compile(project.project_id, report, device)
    service = _service(plans)
    service.compile(project.project_id, report, device)

    assert service.load(project.project_id, report, replace(device, serial="other-phone")) is None

    write = next(command for command in plan.commands if command.phone_changes)
    artifact = service.store.workspace / write.artifact_relative_path
    before = artifact.stat()
    artifact.write_bytes(b"X" * before.st_size)
    os.utime(artifact, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert service.load(project.project_id, report, device) is None


def test_gateway_contract_rejects_resealed_uncontracted_command(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding, _verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    plans.compile(project.project_id, report, device)
    service = _service(plans)
    contract = service.compile(project.project_id, report, device)
    first = contract.steps[0]
    changed_step = replace(
        first,
        arguments=("-s", service.TARGET_TOKEN, "reboot", "bootloader"),
    )
    changed_steps = (changed_step, *contract.steps[1:])
    steps_digest = _digest({"steps": [asdict(step) for step in changed_steps]})
    changed = replace(
        contract,
        steps=changed_steps,
        steps_digest=steps_digest,
        contract_digest="",
    )
    payload = asdict(changed)
    payload.pop("contract_digest")
    changed = replace(changed, contract_digest=_digest(payload))

    with pytest.raises(ProjectError, match="safety validation"):
        service.validate(changed)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", True),
        ("runtime_invoked", True),
        ("execution_authority", "device-write"),
        ("final_consent_available", True),
        ("phone_changed", True),
    ],
)
def test_gateway_contract_rejects_authority_and_type_confusion(tmp_path, monkeypatch, field, value):
    plans, project, report, device, _manifest, _binding, _verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    plans.compile(project.project_id, report, device)
    service = _service(plans)
    service.compile(project.project_id, report, device)
    path = service.store.projects_root / project.project_id / "guardian" / service.LATEST_NAME
    document = json.loads(path.read_text(encoding="utf-8"))
    document[field] = value
    payload = {
        key: item for key, item in document.items() if key not in {"format", "contract_digest"}
    }
    document["contract_digest"] = _digest(payload)
    path.write_text(json.dumps(document), encoding="utf-8")

    assert service.load(project.project_id, report, device) is None


def test_gateway_contract_rejects_extra_fields_and_links(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding, _verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    plans.compile(project.project_id, report, device)
    service = _service(plans)
    service.compile(project.project_id, report, device)
    path = service.store.projects_root / project.project_id / "guardian" / service.LATEST_NAME
    document = json.loads(path.read_text(encoding="utf-8"))
    document["unexpected"] = "authority"
    path.write_text(json.dumps(document), encoding="utf-8")
    assert service.load(project.project_id, report, device) is None

    service.compile(project.project_id, report, device)
    target = path.with_name("linked-gateway-contract.json")
    path.replace(target)
    path.symlink_to(target.name)
    assert service.load(project.project_id, report, device) is None


def test_gateway_contract_rejects_oversized_record(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding, _verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    plans.compile(project.project_id, report, device)
    service = _service(plans)
    service.compile(project.project_id, report, device)
    path = service.store.projects_root / project.project_id / "guardian" / service.LATEST_NAME
    path.write_bytes(b"{" + b" " * service.MAX_BYTES)

    assert service.load(project.project_id, report, device) is None
