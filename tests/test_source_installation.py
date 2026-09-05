from __future__ import annotations

import hashlib
import io
import os
import stat
import struct
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.source_installation import (
    POPSICLE_PHYSICAL_PARTITIONS,
    POPSICLE_SCRIPT_SHA256,
    SourceInstallationService,
    _hash_stream,
)

SCRIPT = Path(__file__).parent / "fixtures" / "source-installation" / "flash_all.sh"


def _files():
    return {
        "flash_all.sh": SCRIPT.read_bytes(),
        **{
            f"images/{name}.img": b"inert firmware fixture " + name.encode()
            for name in (*POPSICLE_PHYSICAL_PARTITIONS, "super", "vbmeta_system", "vbmeta")
        },
    }


def _package(tmp_path, *, files=None, manifest=None, prefix="outputs/popsicle", extras=()):
    files = _files() if files is None else files
    checksums = (
        manifest
        if manifest is not None
        else "".join(
            f"{hashlib.sha256(data).hexdigest()}  ./{name}\n" for name, data in files.items()
        ).encode()
    )
    path = tmp_path / "source.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(f"{prefix}/{name}" if prefix else name, data)
        archive.writestr(f"{prefix}/SHA256SUMS" if prefix else "SHA256SUMS", checksums)
        for name, data in extras:
            archive.writestr(name, data)
    return path


def _import(tmp_path, **kwargs):
    package = _package(tmp_path, **kwargs)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Source installation").project_id, package)
    return store, project, SourceInstallationService(store)


def test_fixture_is_the_complete_exact_reviewed_script():
    assert hashlib.sha256(SCRIPT.read_bytes()).hexdigest() == POPSICLE_SCRIPT_SHA256
    assert len(POPSICLE_PHYSICAL_PARTITIONS) == 47


@pytest.mark.parametrize(
    "wipe,reboot,count",
    [(False, True, 53), (False, False, 52), (True, True, 55), (True, False, 54)],
)
def test_complete_recipe_preserves_source_order_and_explicit_choices(tmp_path, wipe, reboot, count):
    store, project, service = _import(tmp_path)
    original = store.original_path(project.project_id)
    before = original.stat()
    prepared = service.prepare(project.project_id, wipe=wipe, reboot=reboot)
    assert len(prepared.steps) == count
    assert len(prepared.images) == 50
    assert prepared.steps[0].action == "set_active"
    assert prepared.steps[0].slot == "a"
    writes = [step for step in prepared.steps if step.action == "flash"]
    assert [step.partition for step in writes] == [
        f"{name}_a" for name in POPSICLE_PHYSICAL_PARTITIONS
    ] + ["super", "vbmeta_system_a", "vbmeta_a"]
    assert writes[-3].chunk_size == "700M"
    assert all(not step.chunk_size for step in (*writes[:-3], *writes[-2:]))
    assert [step.partition for step in prepared.steps if step.action == "erase"] == (
        ["metadata", "userdata"] if wipe else []
    )
    assert prepared.steps[-2 if reboot else -1].action == "set_active"
    assert (prepared.steps[-1].action == "reboot") is reboot
    assert prepared.expected_product == "popsicle"
    assert prepared.expected_manufacturer == "Xiaomi"
    assert prepared.requires_critical_unlock
    assert "archive_path" not in repr(prepared)
    assert not store.working_root.exists()
    assert original.stat().st_mtime_ns == before.st_mtime_ns
    assert service.verify(prepared) == prepared
    assert any("slot B is not" in warning for warning in prepared.warnings)
    assert any("Anti-rollback" in warning for warning in prepared.warnings)
    assert not any(step.action in {"unlock", "relock", "oem", "shell"} for step in prepared.steps)


def test_recipe_digest_changes_for_wipe_and_reboot_choices(tmp_path):
    _store, project, service = _import(tmp_path)
    recipes = [
        service.prepare(project.project_id, wipe=wipe, reboot=reboot)
        for wipe, reboot in ((False, False), (False, True), (True, False), (True, True))
    ]
    assert len({recipe.recipe_digest for recipe in recipes}) == 4


@pytest.mark.parametrize("prefix", ["", "./outputs/popsicle"])
def test_safe_root_and_normalized_paths_keep_exact_archive_member_names(tmp_path, prefix):
    _store, project, service = _import(tmp_path, prefix=prefix)
    recipe = service.prepare(project.project_id)
    assert (
        recipe.images[0].member == f"{prefix}/images/abl.img"
        if prefix
        else recipe.images[0].member == "images/abl.img"
    )
    assert recipe.steps[1].image_member == recipe.images[0].member


def test_altered_script_is_rejected_even_with_updated_checksums(tmp_path):
    files = _files()
    files["flash_all.sh"] += b"\n# unreviewed alteration\n"
    _store, project, service = _import(tmp_path, files=files)
    with pytest.raises(ProjectError, match="not yet supported"):
        service.prepare(project.project_id)


def test_missing_required_image_never_becomes_partial_install(tmp_path):
    files = _files()
    del files["images/vbmeta_system.img"]
    _store, project, service = _import(tmp_path, files=files)
    with pytest.raises(ProjectError, match="missing a required image"):
        service.prepare(project.project_id)


def test_manifest_image_hash_is_freshly_verified(tmp_path):
    files = _files()
    manifest = "".join(
        f"{hashlib.sha256(data).hexdigest()}  ./{name}\n" for name, data in files.items()
    ).encode()
    files["images/boot.img"] = b"changed after manifest"
    _store, project, service = _import(tmp_path, files=files, manifest=manifest)
    with pytest.raises(ProjectError, match="checksum mismatch: boot.img"):
        service.prepare(project.project_id)


def test_protected_source_change_with_restored_mtime_is_detected(tmp_path):
    store, project, service = _import(tmp_path)
    recipe = service.prepare(project.project_id)
    original = store.original_path(project.project_id)
    before = original.stat()
    original.chmod(0o600)
    with original.open("r+b") as stream:
        stream.seek(60)
        value = stream.read(1)
        stream.seek(60)
        stream.write(bytes([value[0] ^ 1]))
    os.utime(original, ns=(before.st_atime_ns, before.st_mtime_ns))
    with pytest.raises(ProjectError, match="SHA-256 changed"):
        service.verify(recipe)


def test_tampered_recipe_cannot_create_unreviewed_partition_write(tmp_path):
    _store, project, service = _import(tmp_path)
    recipe = service.prepare(project.project_id)
    changed = replace(
        recipe, steps=(replace(recipe.steps[1], partition="persist"), *recipe.steps[2:])
    )
    with pytest.raises(ProjectError, match="choices changed"):
        service.verify(changed)


@pytest.mark.parametrize(
    "extra",
    [
        "outputs/popsicle/./images/boot.img",
        "../outside.img",
        "outputs/popsicle/../escape.img",
        "/absolute.img",
        "windows\\boot.img",
    ],
)
def test_ambiguous_and_unsafe_archive_paths_are_rejected(tmp_path, extra):
    _store, project, service = _import(tmp_path, extras=((extra, b"untrusted"),))
    with pytest.raises(ProjectError, match="ambiguous|path"):
        service.prepare(project.project_id)


def test_multiple_installer_roots_are_not_guessed(tmp_path):
    _store, project, service = _import(
        tmp_path, extras=(("other/flash_all.sh", SCRIPT.read_bytes()),)
    )
    with pytest.raises(ProjectError, match="ambiguous"):
        service.prepare(project.project_id)


def test_link_member_is_never_followed(tmp_path):
    item = zipfile.ZipInfo("outputs/popsicle/linked.img")
    item.create_system = 3
    item.external_attr = (stat.S_IFLNK | 0o777) << 16
    _store, project, service = _import(tmp_path, extras=((item, b"../../outside"),))
    with pytest.raises(ProjectError, match="linked"):
        service.prepare(project.project_id)


@pytest.mark.parametrize("suffix", [b"invalid line\n", b"0" * 64 + b"  ../outside\n"])
def test_manifest_unknown_lines_and_escape_fail_closed(tmp_path, suffix):
    _store, project, service = _import(tmp_path, manifest=suffix)
    with pytest.raises(ProjectError, match="malformed|escapes"):
        service.prepare(project.project_id)


def test_unlisted_file_under_package_root_is_not_silently_ignored(tmp_path):
    _store, project, service = _import(
        tmp_path, extras=(("outputs/popsicle/unlisted.txt", b"extra"),)
    )
    with pytest.raises(ProjectError, match="cover every package file"):
        service.prepare(project.project_id)


def _sparse(*, chunks=None, blocks=3):
    chunks = (
        chunks
        if chunks is not None
        else ((0xCAC1, 1, b"x" * 4096), (0xCAC2, 1, b"abcd"), (0xCAC3, 1, b""))
    )
    return struct.pack("<I4H4I", 0xED26FF3A, 1, 0, 28, 12, 4096, blocks, len(chunks), 0) + b"".join(
        struct.pack("<2H2I", kind, 0, count, 12 + len(payload)) + payload
        for kind, count, payload in chunks
    )


def test_sparse_geometry_is_checked_without_expanding_images(tmp_path):
    files = _files()
    files["images/super.img"] = _sparse()
    _store, project, service = _import(tmp_path, files=files)
    recipe = service.prepare(project.project_id)
    image = next(item for item in recipe.images if item.name == "super.img")
    assert image.expanded_size_bytes == 3 * 4096
    assert image.size_bytes == len(files["images/super.img"])
    assert image.sha256 == hashlib.sha256(files["images/super.img"]).hexdigest()


@pytest.mark.parametrize(
    "data",
    [
        _sparse(blocks=5),
        _sparse() + b"trailing",
        _sparse(chunks=((0xCAFF, 1, b""),), blocks=1),
        _sparse(chunks=((0xCAC4, 1, b"abcd"),), blocks=1),
        _sparse()[:-1],
        b"\x3a\xff\x26\xed",
    ],
)
def test_invalid_sparse_members_are_rejected(data):
    with pytest.raises(ProjectError, match="sparse|Sparse|chunk|header"):
        _hash_stream(io.BytesIO(data), len(data), image=True, maximum_expanded=1024**4)


def test_boolean_choices_are_not_coerced_from_strings(tmp_path):
    _store, project, service = _import(tmp_path)
    with pytest.raises(ProjectError, match="explicitly"):
        service.prepare(project.project_id, wipe="false")
