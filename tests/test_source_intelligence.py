from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from romverse.device.dna import CapabilityState, DeviceDnaService
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.local_store import LocalStoreError
from romverse.infrastructure.process import CommandResult
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.source_intelligence import (
    FirmwareAdapter,
    FirmwareSourceIntelligenceService,
)


class SourceRunner:
    def run(self, args, timeout=10, cwd=None):
        command = tuple(map(str, args))
        if "-j" in command:
            return CommandResult(
                command,
                0,
                json.dumps(
                    {
                        "partitions": [
                            {
                                "name": "product_a",
                                "group_name": "dynamic_a",
                                "size": "4096",
                                "is_dynamic": True,
                            },
                            {
                                "name": "product_b",
                                "group_name": "dynamic_b",
                                "is_dynamic": True,
                            },
                        ],
                        "groups": [
                            {"name": "dynamic_a", "maximum_size": "8192"},
                            {"name": "dynamic_b", "maximum_size": "8192"},
                        ],
                        "super_device": {"used_size": "4096", "total_size": "16384"},
                    }
                ),
                "",
            )
        if "-l" in command:
            return CommandResult(command, 0, "boot:4\nproduct:8\nvbmeta:1\n", "")
        return CommandResult(command, 0, "Footer version: 1.0\n", "")


def _project(tmp_path: Path, name: str, original_name: str):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create(name)
    original = tmp_path / original_name
    original.write_bytes(b"protected-source")
    store.import_original(project.project_id, original)
    tree = store.working_root / project.project_id / "tree"
    tree.mkdir(parents=True)
    return store, project, tree


def test_source_intelligence_selects_fastboot_super_and_persists_exact_blueprint(tmp_path):
    store, project, tree = _project(
        tmp_path,
        "Fastboot",
        "popsicle_images_OS3.0.318.0.WPBCNXM_20260804.0000.00_16.0_cn_test.tgz",
    )
    image_root = tree / "firmware" / "images"
    image_root.mkdir(parents=True)
    (image_root / "super.img").write_bytes(b"r" * (10 * 1024 * 1024))
    lpdump = tmp_path / "lpdumps"
    lpdump.write_bytes(b"tool")
    service = FirmwareSourceIntelligenceService(
        store,
        (ToolStatus("LP Dump", True, str(lpdump), "test"),),
        SourceRunner(),
    )

    analysis = service.analyze(project.project_id)
    progress = []
    blueprint = service.prepare(project.project_id, progress.append)

    assert analysis.adapter is FirmwareAdapter.FASTBOOT_SUPER
    assert blueprint.source_kind == "fastboot-super"
    assert blueprint.codename == "popsicle"
    assert blueprint.baseline_candidate_ready
    assert blueprint.partitions[0].name == "product_a"
    assert progress == [80, 100]
    assert service.load(project.project_id) == blueprint
    receipt_path = store.projects_root / project.project_id / "source-blueprint.romverse"
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600
    hostile = json.loads(receipt_path.read_text(encoding="utf-8"))
    hostile["groups"][0]["unexpected"] = True
    receipt_path.write_text(json.dumps(hostile), encoding="utf-8")
    assert service.load(project.project_id) is None


def test_source_intelligence_selects_nested_ota_payload_without_static_pack(tmp_path):
    store, project, tree = _project(
        tmp_path,
        "OTA",
        "popsicle-ota_full-OS4.0.0.23.XPBCNXM-user-17.0-test.zip",
    )
    payload_root = tree / "nested" / "ota"
    payload_root.mkdir(parents=True)
    (payload_root / "payload.bin").write_bytes(b"CrAU-payload")
    dumper = tmp_path / "payload-dumper-go"
    dumper.write_bytes(b"tool")
    service = FirmwareSourceIntelligenceService(
        store,
        (ToolStatus("Payload Dumper", True, str(dumper), "test"),),
        SourceRunner(),
    )

    analysis = service.analyze(project.project_id)
    progress = []
    blueprint = service.prepare(project.project_id, progress.append)

    assert analysis.adapter is FirmwareAdapter.OTA_PAYLOAD
    assert blueprint.source_kind == "ota-payload"
    assert [item.name for item in blueprint.partitions] == ["boot", "product", "vbmeta"]
    assert blueprint.baseline_candidate_ready
    assert progress == [100]
    assert service.load(project.project_id) == blueprint
    receipt_path = store.projects_root / project.project_id / service.OTA_NAME
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600

    dna = DeviceDnaService(store, DevicePackRegistry(())).refresh(project.project_id)
    assert dna.capability("source_adapter").state is CapabilityState.SUPPORTED
    assert dna.capability("tool_resolution").state is CapabilityState.SUPPORTED
    assert dna.capability("rom_build").state is CapabilityState.SUPPORTED
    assert dna.capability("guardian_flash").state is CapabilityState.UNSUPPORTED
    assert dna.fact("software.build").value == "OS4.0.0.23.XPBCNXM"
    assert dna.fact("software.build").evidence_ids == ("source.blueprint",)
    assert any(item.evidence_id == "source.blueprint" for item in dna.evidence)


def test_ota_blueprint_rejects_extra_oversized_and_symlinked_evidence(tmp_path):
    store, project, tree = _project(
        tmp_path,
        "OTA hostile files",
        "popsicle-ota_full-OS4.0.0.23.XPBCNXM-user-17.0-test.zip",
    )
    payload_path = tree / "payload.bin"
    payload_path.write_bytes(b"CrAU-payload")
    dumper = tmp_path / "payload-dumper-go"
    dumper.write_bytes(b"tool")
    service = FirmwareSourceIntelligenceService(
        store,
        (ToolStatus("Payload Dumper", True, str(dumper), "test"),),
        SourceRunner(),
    )
    service.prepare(project.project_id)
    receipt_path = store.projects_root / project.project_id / service.OTA_NAME
    original = receipt_path.read_bytes()

    payload = json.loads(original)
    payload["unexpected"] = True
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load(project.project_id) is None

    receipt_path.write_bytes(b"{" + b" " * service.MAX_BLUEPRINT_BYTES + b"}")
    assert service.load(project.project_id) is None

    outside = tmp_path / "outside-blueprint.json"
    outside.write_bytes(original)
    receipt_path.unlink()
    receipt_path.symlink_to(outside)
    assert service.load(project.project_id) is None
    with pytest.raises(LocalStoreError, match="regular file"):
        service.prepare(project.project_id)
    assert outside.read_bytes() == original


def test_ota_blueprint_is_invalidated_when_payload_metadata_changes(tmp_path):
    store, project, tree = _project(
        tmp_path,
        "OTA stale payload",
        "popsicle-ota_full-OS4.0.0.23.XPBCNXM-user-17.0-test.zip",
    )
    payload_path = tree / "payload.bin"
    payload_path.write_bytes(b"CrAU-payload")
    dumper = tmp_path / "payload-dumper-go"
    dumper.write_bytes(b"tool")
    service = FirmwareSourceIntelligenceService(
        store,
        (ToolStatus("Payload Dumper", True, str(dumper), "test"),),
        SourceRunner(),
    )
    service.prepare(project.project_id)

    payload_path.write_bytes(payload_path.read_bytes() + b"changed")

    assert service.load(project.project_id) is None


def test_source_intelligence_verifies_partition_bundle_without_granting_avb_authority(
    tmp_path,
):
    store, project, tree = _project(
        tmp_path,
        "Partition bundle",
        "popsicle_images_OS4.0.0.23.XPBCNXM_20260830_fastboot.zip",
    )
    images = tree / "images"
    images.mkdir()
    (images / "boot.img").write_bytes(b"ANDROID!" + b"\0" * 4096)
    (images / "vbmeta.img").write_bytes(b"AVB0" + b"\0" * 4096)
    progress = []
    service = FirmwareSourceIntelligenceService(store, (), SourceRunner())

    analysis = service.analyze(project.project_id)
    blueprint = service.prepare(project.project_id, progress.append)

    assert analysis.adapter is FirmwareAdapter.PARTITION_BUNDLE
    assert blueprint.source_kind == "partition-bundle"
    assert blueprint.baseline_candidate_ready
    assert not blueprint.avb_topology_verified
    assert blueprint.authority == "project-local-inventory-evidence-only"
    assert [item.name for item in blueprint.images] == ["boot", "vbmeta"]
    assert [item.image_format for item in blueprint.images] == [
        "Android boot image",
        "AVB metadata image",
    ]
    assert all(len(item.sha256) == 64 for item in blueprint.images)
    assert progress == [50, 100]
    assert progress[-1] == 100
    assert service.load(project.project_id) == blueprint
    receipt = store.projects_root / project.project_id / service.BUNDLE_NAME
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600


def test_partition_bundle_blueprint_rejects_ambiguity_tampering_and_stale_images(tmp_path):
    store, project, tree = _project(
        tmp_path,
        "Partition bundle ambiguity",
        "popsicle_fastboot.zip",
    )
    first = tree / "primary"
    second = tree / "secondary"
    first.mkdir()
    second.mkdir()
    (first / "boot.img").write_bytes(b"ANDROID!primary")
    (second / "boot.img").write_bytes(b"ANDROID!secondary")
    service = FirmwareSourceIntelligenceService(store, (), SourceRunner())

    with pytest.raises(ProjectError, match="more than one image for role boot"):
        service.prepare(project.project_id)

    (second / "boot.img").unlink()
    blueprint = service.prepare(project.project_id)
    receipt = store.projects_root / project.project_id / service.BUNDLE_NAME
    hostile = json.loads(receipt.read_text(encoding="utf-8"))
    hostile["images"][0]["unexpected"] = True
    receipt.write_text(json.dumps(hostile), encoding="utf-8")
    assert service.load(project.project_id) is None

    service.prepare(project.project_id)
    (first / "boot.img").write_bytes(b"ANDROID!changed-size")
    assert service.load(project.project_id) is None
    assert blueprint.phone_changed is False
