from __future__ import annotations

import hashlib
import json
import shutil
import stat
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from romverse.device_packs.models import (
    AvbHashtreeParameters,
    CapabilityStatus,
    DeviceBuildContract,
    DevicePack,
    DynamicPartitionGroup,
    ErofsRebuildParameters,
    FirmwareSourceContract,
    PackCapability,
    PartitionBuildRule,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.process import CommandResult
from romverse.infrastructure.provisioning import GENESIS_REQUIRED_TOOLS
from romverse.infrastructure.toolchain_evidence import ToolchainEvidenceService
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.build_contracts import ContractCheckStatus, DeviceBuildContractService
from romverse.rom.build_execution import LocalDeviceBuildExecutor
from romverse.rom.builds import RomBuildPlanner
from romverse.rom.inspection import RomInspectionService
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fixture(tmp_path):
    source = tmp_path / "exact-rom.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"payload container")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Contract build", "test.exact")
    project = store.import_original(project.project_id, source)
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    inspection.extract_project_tree(project.project_id)
    RomBuildPlanner(store).plan(project.project_id)

    product = b"p" * 512
    system = b"s" * 512
    partition_root = store.working_root / project.project_id / "partitions"
    partition_root.mkdir()
    (partition_root / "product.img").write_bytes(product)
    (partition_root / "system.img").write_bytes(system)
    payload_hash = "b" * 64
    manifest = {
        "format": "romverse.payload-manifest",
        "schema_version": 1,
        "project_id": project.project_id,
        "source_original_sha256": project.original.sha256,
        "payload_sha256": payload_hash,
        "partitions": [
            {
                "name": "product",
                "extracted_path": (partition_root / "product.img")
                .relative_to(store.workspace)
                .as_posix(),
                "actual_bytes": len(product),
                "sha256": _sha(product),
            },
            {
                "name": "system",
                "extracted_path": (partition_root / "system.img")
                .relative_to(store.workspace)
                .as_posix(),
                "actual_bytes": len(system),
                "sha256": _sha(system),
            },
        ],
    }
    (store.projects_root / project.project_id / "payload-manifest.romverse").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    metadata_root = store.projects_root / project.project_id / "rebuild-metadata"
    metadata_root.mkdir()
    fakeroot = metadata_root / "product.fakeroot"
    contexts = metadata_root / "product.file_contexts"
    fakeroot.write_bytes(b"bounded ownership state")
    contexts.write_bytes(b"/product(/.*)? u:object_r:system_file:s0\n")
    (metadata_root / "product.romverse").write_text(
        json.dumps(
            {
                "format": "romverse.rebuild-metadata",
                "partition": "product",
                "source_sha256": _sha(product),
                "fakeroot_path": fakeroot.name,
                "fakeroot_sha256": _sha(fakeroot.read_bytes()),
                "file_contexts_path": contexts.name,
                "file_contexts_sha256": _sha(contexts.read_bytes()),
            }
        ),
        encoding="utf-8",
    )
    contract = DeviceBuildContract(
        "test-contract",
        1,
        FirmwareSourceContract("EXACT.1", project.original.sha256, payload_hash),
        8192,
        512,
        3,
        True,
        (DynamicPartitionGroup("group_a", 4096), DynamicPartitionGroup("group_b", 4096)),
        (
            PartitionBuildRule(
                "product",
                len(product),
                1024,
                "group_a",
                "erofs",
                "rebuild",
                _sha(product),
                ErofsRebuildParameters(
                    "lz4hc",
                    12,
                    True,
                    1230768000,
                    "f404d989-620e-542a-bf51-02c97b5a42a9",
                    "/product",
                    True,
                    True,
                ),
                AvbHashtreeParameters("sha256", "e" * 64, False),
            ),
            PartitionBuildRule(
                "system", len(system), len(system), "group_a", "opaque", "passthrough", _sha(system)
            ),
        ),
        ("product", "system"),
        "c" * 64,
        "d" * 64,
        ("product.img", "vbmeta_system.img", "super.img"),
    )
    capability = PackCapability(
        "firmware.operations", "Exact build", CapabilityStatus.SUPPORTED, "model_specific", "test"
    )
    pack = DevicePack(
        "test.exact",
        "1",
        "Exact test",
        10,
        ("test",),
        ("model",),
        ("product",),
        (capability,),
        (),
        "a" * 64,
        contract,
    )
    tools = tuple(ToolStatus(name, True, f"/tools/{name}", "1") for name in GENESIS_REQUIRED_TOOLS)
    return store, project, DevicePackRegistry((pack,)), tools, metadata_root, partition_root


def test_exact_contract_creates_locked_phone_safe_deterministic_plan(tmp_path):
    store, project, registry, tools, _metadata, _partitions = _fixture(tmp_path)
    service = DeviceBuildContractService(store, registry, tools)

    assessment = service.assess(project.project_id)
    plan = service.create_plan(project.project_id)

    assert assessment.ready
    assert not plan.execution_locked
    assert not plan.phone_changed
    assert all(not step.phone_changed for step in plan.steps)
    assert [step.step_id for step in plan.steps] == [
        "rebuild-erofs",
        "verify-erofs",
        "stage-partition-image",
        "add-avb-footer",
        "make-vbmeta-system",
        "assemble-super",
        "unpack-and-compare",
    ]
    super_step = next(step for step in plan.steps if step.step_id == "assemble-super")
    assert "super:8192" in super_step.arguments
    assert "product_b:readonly:0:group_b" in super_step.arguments
    assert f"build-candidates/{plan.plan_id}/super.img" in super_step.outputs[0]
    assert service.load(project.project_id) == plan


def test_plan_survives_an_explicitly_build_compatible_pack_upgrade(tmp_path):
    store, project, registry, tools, _metadata, _partitions = _fixture(tmp_path)
    plan = DeviceBuildContractService(store, registry, tools).create_plan(project.project_id)
    old_pack = registry.packs[0]
    upgraded = replace(
        old_pack,
        version="2",
        sha256="b" * 64,
        build_compatible_pack_sha256=(old_pack.sha256,),
    )

    loaded = DeviceBuildContractService(store, DevicePackRegistry((upgraded,)), tools).load(
        project.project_id
    )

    assert loaded == plan


def test_plan_rejects_an_unrecognized_pack_digest_change(tmp_path):
    store, project, registry, tools, _metadata, _partitions = _fixture(tmp_path)
    DeviceBuildContractService(store, registry, tools).create_plan(project.project_id)
    changed = replace(registry.packs[0], version="2", sha256="b" * 64)

    loaded = DeviceBuildContractService(store, DevicePackRegistry((changed,)), tools).load(
        project.project_id
    )

    assert loaded is None


def test_contract_blocks_missing_rebuild_metadata(tmp_path):
    store, project, registry, tools, metadata, _partitions = _fixture(tmp_path)
    (metadata / "product.romverse").unlink()
    service = DeviceBuildContractService(store, registry, tools)

    assessment = service.assess(project.project_id)

    metadata_check = next(check for check in assessment.checks if check.check_id == "metadata")
    assert metadata_check.status is ContractCheckStatus.BLOCKED
    with pytest.raises(ProjectError, match="Rebuild metadata"):
        service.create_plan(project.project_id)


def test_contract_rehashes_partition_inputs_before_saving_plan(tmp_path):
    store, project, registry, tools, _metadata, partitions = _fixture(tmp_path)
    (partitions / "system.img").write_bytes(b"x" * 512)
    service = DeviceBuildContractService(store, registry, tools)

    with pytest.raises(ProjectError, match="system image changed"):
        service.create_plan(project.project_id)
    assert not (store.projects_root / project.project_id / service.PLAN_NAME).exists()


def test_contract_rejects_similar_but_not_exact_firmware(tmp_path):
    store, project, registry, tools, _metadata, _partitions = _fixture(tmp_path)
    pack = registry.packs[0]
    registry = DevicePackRegistry(
        (
            replace(
                pack,
                build_contract=replace(
                    pack.build_contract,
                    source=replace(pack.build_contract.source, archive_sha256="f" * 64),
                ),
            ),
        )
    )
    service = DeviceBuildContractService(store, registry, tools)

    source_check = next(
        check for check in service.assess(project.project_id).checks if check.check_id == "source"
    )

    assert source_check.status is ContractCheckStatus.BLOCKED


class _BuildRunner:
    def __init__(self, system_image):
        self.system_image = system_image
        self.calls = []

    def run(self, args, timeout=10, cwd=None):
        command = tuple(map(str, args))
        self.calls.append(command)
        executable = next(
            (
                name
                for name in (
                    "fakeroot",
                    "fsck.erofs",
                    "avbtool",
                    "lpmake",
                    "simg2img",
                    "lpunpack",
                    "lpdumps",
                )
                if name in command[0]
            ),
            "",
        )
        if executable == "fakeroot":
            output = Path(command[-2])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"filesystem")
        elif executable == "avbtool" and "add_hashtree_footer" in command:
            image = Path(command[command.index("--image") + 1])
            size = int(command[command.index("--partition_size") + 1])
            with image.open("r+b") as stream:
                stream.truncate(size)
        elif executable == "avbtool" and "make_vbmeta_image" in command:
            Path(command[command.index("--output") + 1]).write_bytes(b"vbmeta")
        elif executable == "lpmake":
            Path(command[command.index("--output") + 1]).write_bytes(b"sparse-super")
        elif executable == "simg2img":
            Path(command[2]).write_bytes(b"raw-super")
        elif executable == "lpunpack":
            unpacked = Path(command[2])
            output_root = Path(command[1]).parent.parent
            shutil.copyfile(output_root / "product.img", unpacked / "product_a.img")
            shutil.copyfile(self.system_image, unpacked / "system_a.img")
        return CommandResult(command, 0, "logical partition metadata", "")


class _MutatingBuildRunner(_BuildRunner):
    def __init__(self, system_image: Path, changed_tool: Path):
        super().__init__(system_image)
        self.changed_tool = changed_tool
        self.mutated = False

    def run(self, args, timeout=10, cwd=None):
        result = super().run(args, timeout=timeout, cwd=cwd)
        if not self.mutated:
            self.changed_tool.write_bytes(b"tool changed during build")
            self.mutated = True
        return result


def _executable_tools(tmp_path):
    tmp_path.mkdir(parents=True)
    paths = {}
    executable_names = {
        "Fakeroot": "fakeroot",
        "EROFS Builder": "mkfs.erofs",
        "EROFS Verifier": "fsck.erofs",
        "AVBTool": "avbtool",
        "LP Make": "lpmake",
        "LP Unpack": "lpunpack",
        "LP Dump": "lpdumps",
        "simg2img": "simg2img",
    }
    for name in GENESIS_REQUIRED_TOOLS:
        path = tmp_path / executable_names.get(name, name.casefold().replace(" ", "-"))
        path.write_bytes(b"tool")
        paths[name] = path
    return tuple(ToolStatus(name, True, str(path), "1") for name, path in paths.items())


def test_local_executor_builds_versioned_candidate_and_verifies_every_partition(tmp_path):
    store, project, registry, _tools, _metadata, partitions = _fixture(tmp_path)
    tools = _executable_tools(tmp_path / "tools")
    service = DeviceBuildContractService(store, registry, tools)
    plan = service.create_plan(project.project_id)
    runner = _BuildRunner(partitions / "system.img")
    executor = LocalDeviceBuildExecutor(store, registry, tools, runner)

    receipt = executor.execute(project.project_id)

    assert receipt.status == "success"
    assert receipt.schema_version == 2
    assert len(receipt.toolchain_manifest_digest) == 64
    assert not receipt.phone_changed
    assert [item.name for item in receipt.outputs] == [
        "product.img",
        "vbmeta_system.img",
        "super.img",
    ]
    assert all(f"build-candidates/{plan.plan_id}" in item.path for item in receipt.outputs)
    assert not any("adb" in call[0] or "fastboot" in call[0] for call in runner.calls)
    attempt = store.projects_root / project.project_id / executor.ATTEMPT_NAME
    assert json.loads(attempt.read_text())["status"] == "success"
    assert stat.S_IMODE(attempt.stat().st_mode) == 0o600
    output_receipt = (
        store.working_root
        / project.project_id
        / "build-candidates"
        / plan.plan_id
        / executor.RECEIPT_NAME
    )
    assert stat.S_IMODE(output_receipt.stat().st_mode) == 0o600
    manifest = ToolchainEvidenceService(store.workspace, "Linux").load_private(
        receipt.toolchain_manifest_digest
    )
    assert manifest.complete
    assert manifest.scope == f"local-build:{project.project_id}"
    assert set(manifest.required_tools) == {
        "AVBTool",
        "EROFS Builder",
        "EROFS Verifier",
        "Fakeroot",
        "LP Dump",
        "LP Make",
        "LP Unpack",
        "simg2img",
    }
    assert manifest.execution_authority == "none"
    assert not manifest.phone_changed
    assert executor.load_receipt(project.project_id) == receipt

    output = store.workspace / receipt.outputs[0].path
    output.write_bytes(output.read_bytes() + b"tampered")
    assert executor.load_receipt(project.project_id) is None


def test_local_build_receipt_rejects_hostile_files_and_missing_logs(tmp_path):
    store, project, registry, _tools, _metadata, partitions = _fixture(tmp_path)
    tools = _executable_tools(tmp_path / "tools")
    DeviceBuildContractService(store, registry, tools).create_plan(project.project_id)
    executor = LocalDeviceBuildExecutor(
        store,
        registry,
        tools,
        _BuildRunner(partitions / "system.img"),
    )
    receipt = executor.execute(project.project_id)
    attempt = store.projects_root / project.project_id / executor.ATTEMPT_NAME
    original = attempt.read_bytes()
    evidence = (
        store.workspace
        / "config"
        / "toolchain"
        / "evidence"
        / f"{receipt.toolchain_manifest_digest}.romverse-toolchain.json"
    )
    original_evidence = evidence.read_bytes()

    evidence.write_text("{}", encoding="utf-8")
    assert executor.load_receipt(project.project_id) is None
    evidence.write_bytes(original_evidence)

    payload = json.loads(original)
    payload["unexpected"] = "not in the receipt schema"
    attempt.write_text(json.dumps(payload), encoding="utf-8")
    assert executor.load_receipt(project.project_id) is None

    attempt.write_bytes(b"{" + b" " * executor.MAX_RECEIPT_BYTES + b"}")
    assert executor.load_receipt(project.project_id) is None

    outside = tmp_path / "outside-build-receipt.json"
    outside.write_bytes(original)
    attempt.unlink()
    attempt.symlink_to(outside)
    assert executor.load_receipt(project.project_id) is None
    assert outside.read_bytes() == original

    attempt.unlink()
    attempt.write_bytes(original)
    first_log = store.workspace / receipt.steps[0].log_path
    first_log.unlink()
    assert executor.load_receipt(project.project_id) is None


def test_local_build_preserves_strict_schema_one_receipt_compatibility(tmp_path):
    store, project, registry, _tools, _metadata, partitions = _fixture(tmp_path)
    tools = _executable_tools(tmp_path / "tools")
    DeviceBuildContractService(store, registry, tools).create_plan(project.project_id)
    executor = LocalDeviceBuildExecutor(
        store,
        registry,
        tools,
        _BuildRunner(partitions / "system.img"),
    )
    executor.execute(project.project_id)
    attempt = store.projects_root / project.project_id / executor.ATTEMPT_NAME
    payload = json.loads(attempt.read_text())
    payload["schema_version"] = 1
    payload.pop("toolchain_manifest_digest")
    unsigned = {key: value for key, value in payload.items() if key != "format"}
    unsigned.pop("receipt_digest")
    payload["receipt_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    attempt.write_text(json.dumps(payload), encoding="utf-8")

    legacy = executor.load_receipt(project.project_id)

    assert legacy is not None
    assert legacy.schema_version == 1
    assert legacy.toolchain_manifest_digest == ""


def test_local_executor_rederives_steps_even_if_plan_digest_is_recomputed(tmp_path):
    store, project, registry, _tools, _metadata, partitions = _fixture(tmp_path)
    tools = _executable_tools(tmp_path / "tools")
    service = DeviceBuildContractService(store, registry, tools)
    service.create_plan(project.project_id)
    path = store.projects_root / project.project_id / service.PLAN_NAME
    payload = json.loads(path.read_text())
    payload["steps"][0]["arguments"][-1] = "../outside"
    digest_payload = {key: value for key, value in payload.items() if key != "format"}
    digest_payload.pop("plan_digest")
    payload["plan_digest"] = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    path.write_text(json.dumps(payload), encoding="utf-8")
    runner = _BuildRunner(partitions / "system.img")
    executor = LocalDeviceBuildExecutor(store, registry, tools, runner)

    with pytest.raises(ProjectError, match="steps do not match"):
        executor.execute(project.project_id)

    assert runner.calls == []


def test_local_executor_stops_when_a_locked_tool_changes_during_build(tmp_path):
    store, project, registry, _tools, _metadata, partitions = _fixture(tmp_path)
    tools = _executable_tools(tmp_path / "tools")
    DeviceBuildContractService(store, registry, tools).create_plan(project.project_id)
    changed = next(Path(item.path) for item in tools if item.name == "LP Make")
    runner = _MutatingBuildRunner(partitions / "system.img", changed)
    executor = LocalDeviceBuildExecutor(store, registry, tools, runner)

    with pytest.raises(ProjectError, match="Locked build tool changed after preflight: LP Make"):
        executor.execute(project.project_id)

    attempt = store.projects_root / project.project_id / executor.ATTEMPT_NAME
    payload = json.loads(attempt.read_text())
    assert payload["status"] == "failed"
    assert payload["schema_version"] == 2
    assert len(payload["toolchain_manifest_digest"]) == 64
    assert payload["phone_changed"] is False
