from __future__ import annotations

import json
import os
import stat
import struct
from pathlib import Path

import pytest

from romverse.infrastructure.process import CommandResult
from romverse.rom.models import ProjectError
from romverse.rom.payloads import PayloadService
from romverse.rom.projects import RomProjectStore


class FakePayloadRunner:
    def run(self, args, timeout=10):
        command = tuple(map(str, args))
        if "-l" in command:
            return CommandResult(command, 0, "boot:4\nsystem:8\nmodem:2\n", "")
        output = Path(command[command.index("-o") + 1])
        selected = command[command.index("-p") + 1].split(",")
        for name in selected:
            target = output / f"{name}.img"
            if name == "system":
                target.write_bytes(b"\0" * 1080 + b"\x53\xef" + b"system")
            else:
                target.write_bytes(b"ANDROID!" + struct.pack("<I", 1))
        return CommandResult(command, 0, "", "")


def _service(tmp_path):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Payload test")
    original = tmp_path / "ota.zip"
    original.write_bytes(b"protected-original")
    store.import_original(project.project_id, original)
    tree = store.working_root / project.project_id / "tree"
    tree.mkdir(parents=True)
    (tree / "payload.bin").write_bytes(b"CrAU" + b"payload-data")
    executable = tmp_path / "payload-dumper-go"
    executable.write_bytes(b"tool")
    return store, project, PayloadService(store, executable, FakePayloadRunner())


def test_payload_scan_persists_partition_evidence(tmp_path):
    store, project, service = _service(tmp_path)
    progress = []

    manifest = service.scan(project.project_id, lambda done, total: progress.append((done, total)))
    loaded = service.load(project.project_id)

    assert loaded == manifest
    assert manifest.schema_version == 2
    assert manifest.payload_modified_ns > 0
    assert len(manifest.tool_sha256) == 64
    assert len(manifest.record_digest) == 64
    assert [item.name for item in manifest.partitions] == ["boot", "system", "modem"]
    assert manifest.partitions[1].estimated_bytes == 8 * 1024
    assert manifest.partitions[1].recommended
    assert manifest.partitions[2].critical
    assert len(manifest.payload_sha256) == 64
    receipt = store.projects_root / project.project_id / service.MANIFEST_NAME
    assert receipt.is_file()
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    assert progress == [(manifest.payload_size, manifest.payload_size)]


def test_payload_extraction_is_selected_transactional_and_hashed(tmp_path):
    store, project, service = _service(tmp_path)
    service.scan(project.project_id)

    plan = service.plan_extraction(project.project_id, ("boot", "system"))
    progress = []
    manifest = service.extract(
        project.project_id,
        plan.selected,
        lambda done, total: progress.append((done, total)),
    )

    assert plan.safe
    partitions = {item.name: item for item in manifest.partitions}
    assert partitions["boot"].image_format == "Android boot image"
    assert partitions["system"].image_format == "ext4 filesystem"
    assert len(partitions["system"].sha256) == 64
    assert not partitions["modem"].extracted_path
    assert (store.workspace / partitions["system"].extracted_path).is_file()
    assert not any((store.working_root / project.project_id).glob(".partitions-*.part"))
    assert progress[0][0] == 0
    assert progress[-1][0] == progress[-1][1]
    assert progress == sorted(progress)
    assert len({total for _done, total in progress}) == 1
    assert all(done < total for done, total in progress[:-1])


def test_payload_extraction_rejects_linked_existing_partition_target(tmp_path):
    store, project, service = _service(tmp_path)
    service.scan(project.project_id)
    destination = store.working_root / project.project_id / "partitions"
    destination.mkdir(parents=True)
    outside = tmp_path / "outside-boot.img"
    outside.write_bytes(b"outside must remain unchanged")
    (destination / "boot.img").symlink_to(outside)

    with pytest.raises(ProjectError, match="not a regular contained file"):
        service.extract(project.project_id, ("boot",))

    assert outside.read_bytes() == b"outside must remain unchanged"
    assert not any((store.working_root / project.project_id).glob(".partitions-*.part"))


def test_payload_parser_rejects_duplicate_or_unsafe_names():
    with pytest.raises(ProjectError, match="invalid partition list"):
        PayloadService.parse_partition_list("system:1\nsystem:2\n")
    with pytest.raises(ProjectError, match="invalid partition list"):
        PayloadService.parse_partition_list("../system:1\n")


def test_payload_plan_rejects_unknown_partition(tmp_path):
    _store, project, service = _service(tmp_path)
    service.scan(project.project_id)

    with pytest.raises(ProjectError, match="does not match"):
        service.plan_extraction(project.project_id, ("unknown",))


def test_payload_discovery_accepts_case_variants_without_weakening_ambiguity(tmp_path):
    store, project, service = _service(tmp_path)
    payload = store.working_root / project.project_id / "tree" / "payload.bin"
    payload.rename(payload.with_name("PAYLOAD.BIN"))

    manifest = service.scan(project.project_id)

    assert manifest.payload_path.endswith("/PAYLOAD.BIN")
    nested = payload.parent / "nested"
    nested.mkdir()
    (nested / "Payload.bin").write_bytes(b"CrAUduplicate")
    with pytest.raises(ProjectError, match="Multiple payload.bin"):
        service.payload_path(project.project_id)


def test_payload_manifest_rejects_extra_nested_oversized_and_linked_evidence(tmp_path):
    store, project, service = _service(tmp_path)
    service.scan(project.project_id)
    receipt = store.projects_root / project.project_id / service.MANIFEST_NAME
    original = receipt.read_bytes()

    payload = json.loads(original)
    payload["unexpected"] = True
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load(project.project_id) is None

    payload = json.loads(original)
    payload["partitions"][0]["unexpected"] = True
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load(project.project_id) is None

    payload = json.loads(original)
    payload["payload_sha256"] = "0" * 64
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load(project.project_id) is None

    receipt.write_bytes(b"{" + b" " * service.MAX_MANIFEST_BYTES + b"}")
    assert service.load(project.project_id) is None

    outside = tmp_path / "outside-payload-manifest.json"
    outside.write_bytes(original)
    receipt.unlink()
    receipt.symlink_to(outside)
    assert service.load(project.project_id) is None
    with pytest.raises(OSError, match="regular file"):
        service.scan(project.project_id)
    assert outside.read_bytes() == original


def test_payload_extraction_rehashes_payload_and_verified_tool(tmp_path):
    store, project, service = _service(tmp_path)
    service.scan(project.project_id)
    payload = service.payload_path(project.project_id)
    payload_stat = payload.stat()
    original = payload.read_bytes()
    payload.write_bytes(bytes([original[0] ^ 1]) + original[1:])
    os.utime(payload, ns=(payload_stat.st_atime_ns, payload_stat.st_mtime_ns))

    with pytest.raises(ProjectError, match="SHA-256 changed"):
        service.extract(project.project_id, ("boot",))

    payload.write_bytes(original)
    os.utime(payload, ns=(payload_stat.st_atime_ns, payload_stat.st_mtime_ns))
    tool_stat = service.executable.stat()
    service.executable.write_bytes(b"evil")
    os.utime(service.executable, ns=(tool_stat.st_atime_ns, tool_stat.st_mtime_ns))

    with pytest.raises(ProjectError, match="Dumper identity changed"):
        service.extract(project.project_id, ("boot",))


def test_legacy_payload_manifest_is_automatically_rescanned_before_extraction(tmp_path):
    store, project, service = _service(tmp_path)
    service.scan(project.project_id)
    receipt = store.projects_root / project.project_id / service.MANIFEST_NAME
    legacy = json.loads(receipt.read_text(encoding="utf-8"))
    legacy["schema_version"] = 1
    legacy.pop("payload_modified_ns")
    legacy.pop("tool_sha256")
    legacy.pop("record_digest")
    receipt.write_text(json.dumps(legacy), encoding="utf-8")

    loaded = service.load(project.project_id)

    assert loaded is not None
    assert loaded.schema_version == 1
    progress = []
    upgraded = service.extract(
        project.project_id,
        ("boot",),
        lambda done, total: progress.append((done, total)),
    )

    assert upgraded.schema_version == 2
    assert upgraded.partitions[0].extracted_path.endswith("/boot.img")
    assert service.load(project.project_id) == upgraded
    assert progress[0][0] == 0
    assert progress[-1][0] == progress[-1][1]
    assert progress == sorted(progress)
    assert all(done < total for done, total in progress[:-1])


def test_failed_legacy_payload_rescan_preserves_reviewable_history(tmp_path):
    store, project, service = _service(tmp_path)
    service.scan(project.project_id)
    receipt = store.projects_root / project.project_id / service.MANIFEST_NAME
    legacy = json.loads(receipt.read_text(encoding="utf-8"))
    legacy["schema_version"] = 1
    legacy.pop("payload_modified_ns")
    legacy.pop("tool_sha256")
    legacy.pop("record_digest")
    receipt.write_text(json.dumps(legacy), encoding="utf-8")

    class FailedRescanRunner(FakePayloadRunner):
        def run(self, args, timeout=10):
            command = tuple(map(str, args))
            if "-l" in command:
                return CommandResult(command, 1, "", "payload metadata is unreadable")
            return super().run(args, timeout)

    service.runner = FailedRescanRunner()

    with pytest.raises(ProjectError, match="payload metadata is unreadable"):
        service.extract(project.project_id, ("boot",))

    assert json.loads(receipt.read_text(encoding="utf-8"))["schema_version"] == 1
    assert service.load(project.project_id).schema_version == 1
