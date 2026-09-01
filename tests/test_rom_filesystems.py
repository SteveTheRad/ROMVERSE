from __future__ import annotations

import struct
from pathlib import Path

from romverse.infrastructure.process import CommandResult
from romverse.rom.filesystems import PartitionFilesystemService
from romverse.rom.payloads import PayloadService
from romverse.rom.projects import RomProjectStore


class PayloadRunner:
    def run(self, args, timeout=10, cwd=None):
        command = tuple(map(str, args))
        if "-l" in command:
            return CommandResult(command, 0, "system:8\nproduct:8\nmodem:2\n", "")
        output = Path(command[command.index("-o") + 1])
        selected = command[command.index("-p") + 1].split(",")
        for name in selected:
            image = bytearray(4096)
            if name == "product":
                struct.pack_into("<I", image, 1024, 0xE0F5E1E2)
            else:
                image[1080:1082] = b"\x53\xef"
            (output / f"{name}.img").write_bytes(image)
        return CommandResult(command, 0, "", "")


class FilesystemRunner:
    def run(self, args, timeout=10, cwd=None):
        command = tuple(map(str, args))
        root = Path(cwd) / "root"
        if "fakeroot" in Path(command[0]).name:
            state = Path(command[command.index("-s") + 1])
            state.write_text("fakeroot ownership state\n")
            (root / "etc/selinux").mkdir(parents=True)
            (root / "etc/selinux/product_file_contexts").write_text(
                "/product(/.*)? u:object_r:system_file:s0\n"
            )
        else:
            (root / "system/etc").mkdir(parents=True)
            (root / "system/etc/build.prop").write_text("ro.romverse=test\n")
        return CommandResult(command, 0, "", "")


class SuperRunner(FilesystemRunner):
    def run(self, args, timeout=10, cwd=None):
        command = tuple(map(str, args))
        if "lpunpack" in Path(command[0]).name:
            output = Path(command[-1])
            image = bytearray(4096)
            image[1080:1082] = b"\x53\xef"
            (output / "system_a.img").write_bytes(image)
            (output / "product_a.img").write_bytes(image)
            (output / "ignored_radio_a.img").write_bytes(b"radio")
            return CommandResult(command, 0, "", "")
        return super().run(args, timeout, cwd)


def _services(tmp_path):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Filesystem test")
    original = tmp_path / "ota.zip"
    original.write_bytes(b"protected-original")
    store.import_original(project.project_id, original)
    tree = store.working_root / project.project_id / "tree"
    tree.mkdir(parents=True)
    (tree / "payload.bin").write_bytes(b"CrAU" + struct.pack(">Q", 1))
    payload_tool = tmp_path / "payload-dumper-go"
    payload_tool.write_bytes(b"tool")
    debugfs = tmp_path / "debugfs"
    debugfs.write_bytes(b"tool")
    erofs = tmp_path / "fsck.erofs"
    erofs.write_bytes(b"tool")
    fakeroot = tmp_path / "fakeroot"
    fakeroot.write_bytes(b"tool")
    payloads = PayloadService(store, payload_tool, PayloadRunner())
    payloads.scan(project.project_id)
    payloads.extract(project.project_id, ("system", "product", "modem"))
    filesystems = PartitionFilesystemService(
        store,
        payloads,
        FilesystemRunner(),
        debugfs=debugfs,
        erofs=erofs,
        fakeroot=fakeroot,
    )
    return store, project, filesystems


def test_filesystem_expansion_is_contained_and_manifested(tmp_path):
    store, project, service = _services(tmp_path)

    plan = service.plan(project.project_id, "system")
    manifest = service.expand(project.project_id, "system")
    loaded = service.load(project.project_id, "system")

    assert plan.safe
    assert loaded == manifest
    assert manifest.image_format == "ext4 filesystem"
    assert manifest.file_count == 1
    tree = store.workspace / manifest.tree_path
    assert tree.is_relative_to(store.working_root / project.project_id / "tree")
    assert (tree / "system/etc/build.prop").read_text() == "ro.romverse=test\n"


def test_fastboot_partition_image_expands_without_payload_manifest(tmp_path):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Fastboot filesystem")
    original = tmp_path / "fastboot.tgz"
    original.write_bytes(b"protected-original")
    store.import_original(project.project_id, original)
    tree = store.working_root / project.project_id / "tree"
    image = bytearray(4096)
    image[1080:1082] = b"\x53\xef"
    source = tree / "images" / "system.img"
    source.parent.mkdir(parents=True)
    source.write_bytes(image)
    debugfs = tmp_path / "debugfs"
    debugfs.write_bytes(b"tool")
    service = PartitionFilesystemService(
        store,
        None,
        FilesystemRunner(),
        debugfs=debugfs,
    )

    assert "system" in service.available_partitions(project.project_id)
    plan = service.plan(project.project_id, "system")
    manifest = service.expand(project.project_id, "system")

    assert plan.safe
    assert manifest.partition == "system"
    assert manifest.source_image_path.endswith("tree/images/system.img")
    assert (store.workspace / manifest.tree_path / "system/etc/build.prop").is_file()


def test_fastboot_super_is_unpacked_into_source_bound_partition_images(tmp_path):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Fastboot super")
    original = tmp_path / "fastboot.tgz"
    original.write_bytes(b"protected-original")
    store.import_original(project.project_id, original)
    tree = store.working_root / project.project_id / "tree"
    tree.mkdir(parents=True)
    (tree / "super.img").write_bytes(b"raw-super")
    lpunpack = tmp_path / "lpunpack"
    lpunpack.write_bytes(b"verified tool")
    service = PartitionFilesystemService(
        store,
        None,
        SuperRunner(),
        lpunpack=lpunpack,
    )

    receipt = (
        store.projects_root / project.project_id / service.MANIFEST_ROOT / service.SUPER_UNPACK_NAME
    )
    updates: list[tuple[int, int]] = []
    terminal_receipt_state = []

    def progress(done: int, total: int) -> None:
        updates.append((done, total))
        if done >= total:
            terminal_receipt_state.append(receipt.is_file())

    partitions = service.unpack_super(
        project.project_id,
        frozenset({"system", "product"}),
        progress,
    )
    materialized = store.working_root / project.project_id / "partitions" / "system.img"

    assert partitions == ("product", "system")
    assert updates == [(4096, 8192), (8192, 8192)]
    assert terminal_receipt_state == [True]
    assert materialized.is_file()
    assert receipt.is_file()
    assert "system" in service.available_partitions(project.project_id)
    assert store.verify_original(project.project_id).valid


def test_filesystem_expansion_blocks_critical_firmware_partition(tmp_path):
    _store, project, service = _services(tmp_path)

    plan = service.plan(project.project_id, "modem")

    assert not plan.safe
    assert "critical" in plan.reason.casefold()


def test_erofs_expansion_preserves_bounded_fakeroot_state(tmp_path):
    store, project, service = _services(tmp_path)

    manifest = service.expand(project.project_id, "product")
    loaded = service.load(project.project_id, "product")

    assert loaded == manifest
    assert manifest.schema_version == 2
    assert manifest.image_format == "EROFS filesystem"
    assert manifest.metadata_hashes == (
        (
            "etc/selinux/product_file_contexts",
            "79d2eef9bce817f0715dc64cd47f92e6b20bb946a4ed742759dbeca8ef69e910",
        ),
    )
    state = store.workspace / manifest.fakeroot_state_path
    assert state.read_text() == "fakeroot ownership state\n"
