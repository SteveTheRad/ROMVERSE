from __future__ import annotations

import hashlib
from dataclasses import replace

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
from romverse.rom.build_inputs import BuildInputPreparationService
from romverse.rom.models import ProjectError
from romverse.rom.payloads import PayloadManifest, PayloadPartition
from romverse.rom.projects import RomProjectStore


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class Payloads:
    def __init__(self, initial, complete):
        self.initial = initial
        self.complete = complete
        self.extractions = []
        self.scans = 0

    def load(self, _project_id):
        return self.initial

    def scan(self, _project_id):
        self.scans += 1
        return self.initial

    def extract(self, _project_id, selected):
        self.extractions.append(tuple(selected))
        return self.complete


class Filesystems:
    def __init__(self):
        self.ready = set()
        self.expansions = []

    def load(self, _project_id, partition):
        return object() if partition in self.ready else None

    def expand(self, _project_id, partition):
        self.ready.add(partition)
        self.expansions.append(partition)
        return object()


class Metadata:
    def __init__(self):
        self.calls = []

    def prepare(self, project_id, contract):
        self.calls.append((project_id, contract.contract_id))
        return ("receipt",)


def _fixture(tmp_path, *, payload_digest="b" * 64):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Inputs", "exact")
    source = tmp_path / "exact.zip"
    source.write_bytes(b"exact source")
    project = store.import_original(project.project_id, source)
    product = b"product"
    system = b"system"
    initial = PayloadManifest(
        1,
        project.project_id,
        "now",
        project.original.sha256,
        "tree/payload.bin",
        1,
        payload_digest,
        "payload-dumper-go",
        (
            PayloadPartition("product", len(product), "dynamic", True, False),
            PayloadPartition(
                "system",
                len(system),
                "dynamic",
                True,
                False,
                "working/system.img",
                len(system),
                _sha(system),
                "EROFS filesystem",
            ),
        ),
    )
    complete = replace(
        initial,
        partitions=(
            PayloadPartition(
                "product",
                len(product),
                "dynamic",
                True,
                False,
                "working/product.img",
                len(product),
                _sha(product),
                "EROFS filesystem",
            ),
            initial.partitions[1],
        ),
    )
    contract = DeviceBuildContract(
        "input-contract",
        1,
        FirmwareSourceContract("EXACT", project.original.sha256, "b" * 64),
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
                "system",
                len(system),
                len(system),
                "group_a",
                "opaque",
                "passthrough",
                _sha(system),
            ),
        ),
        ("product", "system"),
        "c" * 64,
        "d" * 64,
        ("product.img", "vbmeta_system.img", "super.img"),
        (),
        (
            FileContextSource("system", ("etc/selinux/plat_file_contexts",)),
            FileContextSource("product", ("etc/selinux/product_file_contexts",)),
        ),
    )
    return store, project, contract, initial, complete


def test_build_input_preparation_extracts_and_expands_only_contract_requirements(tmp_path):
    store, project, contract, initial, complete = _fixture(tmp_path)
    payloads = Payloads(initial, complete)
    filesystems = Filesystems()
    metadata = Metadata()
    service = BuildInputPreparationService(store, payloads, filesystems, metadata)

    result = service.prepare(project.project_id, contract)

    assert result.extracted_partitions == ("product",)
    assert result.expanded_filesystems == ("system", "product")
    assert result.metadata_receipts == ("receipt",)
    assert not result.phone_changed
    assert payloads.extractions == [("product",)]
    assert payloads.scans == 0
    assert metadata.calls == [(project.project_id, contract.contract_id)]


def test_build_input_preparation_rejects_wrong_payload_before_extraction(tmp_path):
    store, project, contract, initial, complete = _fixture(tmp_path, payload_digest="f" * 64)
    payloads = Payloads(initial, complete)
    service = BuildInputPreparationService(store, payloads, Filesystems(), Metadata())

    with pytest.raises(ProjectError, match="payload.bin does not match"):
        service.prepare(project.project_id, contract)
    assert payloads.extractions == []
