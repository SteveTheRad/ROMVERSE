from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from romverse.device_packs.models import (
    AvbHashtreeParameters,
    DeviceBuildContract,
    DynamicPartitionGroup,
    ErofsRebuildParameters,
    FileContextSource,
    FirmwareSourceContract,
    PartitionBuildRule,
)
from romverse.infrastructure.process import CommandResult
from romverse.rom.filesystems import FilesystemManifest, PartitionFilesystemService
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.rebuild_metadata import RebuildMetadataService


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class MetadataRunner:
    def __init__(self) -> None:
        self.calls = []

    def run(self, args, timeout=10, cwd=None):
        command = tuple(map(str, args))
        self.calls.append((command, timeout, cwd))
        state = Path(command[command.index("-s") + 1])
        state.write_bytes(state.read_bytes() + b"reconciled\n")
        return CommandResult(command, 0, "", "")


def _fixture(tmp_path):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Metadata", "test.exact")
    context_paths = {
        "system": "system/etc/selinux/plat_file_contexts",
        "system_ext": "etc/selinux/system_ext_file_contexts",
        "product": "etc/selinux/product_file_contexts",
        "vendor": "etc/selinux/vendor_file_contexts",
        "odm": "etc/selinux/odm_file_contexts",
    }
    rules = []
    context_sources = []
    manifest_root = store.projects_root / project.project_id / "filesystems"
    manifest_root.mkdir(parents=True)
    for index, (partition, relative) in enumerate(context_paths.items(), 1):
        tree = (
            store.working_root
            / project.project_id
            / "tree"
            / "partition_files"
            / partition
            / "root"
        )
        context = tree / relative
        context.parent.mkdir(parents=True)
        payload = (
            f"# {partition} comments are excluded\n"
            f"/{partition}(/.*)? u:object_r:{partition}_file:s0\n"
        ).encode()
        context.write_bytes(payload)
        state = tree.parent / "fakeroot.state"
        state.write_bytes(f"{partition} ownership\n".encode())
        source_sha = f"{index:x}" * 64
        manifest = FilesystemManifest(
            2,
            project.project_id,
            partition,
            "2026-08-29T00:00:00+00:00",
            f"working_roms/{project.project_id}/partitions/{partition}.img",
            source_sha,
            "EROFS filesystem",
            tree.relative_to(store.workspace).as_posix(),
            1,
            3,
            0,
            0,
            len(payload),
            "fsck.erofs",
            state.relative_to(store.workspace).as_posix(),
            ((relative, _sha_bytes(payload)),),
        )
        (manifest_root / f"{partition}.romverse").write_text(
            json.dumps({"format": "romverse.filesystem-manifest", **asdict(manifest)}),
            encoding="utf-8",
        )
        rules.append(
            PartitionBuildRule(
                partition,
                512,
                1024 if partition == "product" else 512,
                "group_a",
                "erofs" if partition == "product" else "opaque",
                "rebuild" if partition == "product" else "passthrough",
                source_sha,
                ErofsRebuildParameters(
                    "lz4hc",
                    12,
                    True,
                    1230768000,
                    "f404d989-620e-542a-bf51-02c97b5a42a9",
                    "/product",
                    True,
                    True,
                )
                if partition == "product"
                else None,
                AvbHashtreeParameters("sha256", "e" * 64, False)
                if partition == "product"
                else None,
            )
        )
        context_sources.append(FileContextSource(partition, (relative,)))
    contract = DeviceBuildContract(
        "metadata-contract",
        1,
        FirmwareSourceContract("EXACT", "a" * 64, "b" * 64),
        8192,
        512,
        3,
        True,
        (DynamicPartitionGroup("group_a", 4096), DynamicPartitionGroup("group_b", 4096)),
        tuple(rules),
        ("product",),
        "c" * 64,
        "d" * 64,
        ("product.img", "vbmeta_system.img", "super.img"),
        (),
        tuple(context_sources),
    )
    fakeroot = tmp_path / "fakeroot"
    fakeroot.write_bytes(b"tool")
    runner = MetadataRunner()
    filesystems = PartitionFilesystemService(store, None, runner)
    service = RebuildMetadataService(store, filesystems, runner, fakeroot)
    return store, project, contract, service, runner, context_paths


def test_rebuild_metadata_combines_source_bound_contexts_and_reconciles_ownership(tmp_path):
    store, project, contract, service, runner, context_paths = _fixture(tmp_path)

    receipts = service.prepare(project.project_id, contract)

    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.contract_id == contract.contract_id
    assert [item.partition for item in receipt.context_sources] == list(context_paths)
    output = store.projects_root / project.project_id / "rebuild-metadata"
    contexts = (output / receipt.file_contexts_path).read_text()
    assert "comments are excluded" not in contexts
    assert contexts.splitlines() == [
        f"/{name}(/.*)? u:object_r:{name}_file:s0" for name in context_paths
    ]
    assert (output / receipt.fakeroot_path).read_bytes().endswith(b"reconciled\n")
    command = runner.calls[0][0]
    assert command[0].endswith("fakeroot")
    assert command[command.index("--") + 1] == "/usr/bin/chown"
    assert "adb" not in command and "fastboot" not in command


def test_rebuild_metadata_rejects_context_changed_after_extraction(tmp_path):
    store, project, contract, service, _runner, context_paths = _fixture(tmp_path)
    system_context = (
        store.working_root
        / project.project_id
        / "tree"
        / "partition_files"
        / "system"
        / "root"
        / context_paths["system"]
    )
    system_context.write_text("tampered\n")

    with pytest.raises(ProjectError, match="Expand system"):
        service.prepare(project.project_id, contract)
    assert not (
        store.projects_root / project.project_id / "rebuild-metadata" / "product.romverse"
    ).exists()
