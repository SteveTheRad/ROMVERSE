from __future__ import annotations

import hashlib
import json
import struct
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from romverse.ascension.build_handoff import RootRomBuildHandoffService
from romverse.ascension.evidence import AscensionEvidenceService
from romverse.ascension.integration import RootRomIntegrationService
from romverse.ascension.models import AscensionMethod, OfficialRootAsset, OfficialRootRelease
from romverse.ascension.preparation import RootPatchPreparationService
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.builds import RomBuildPlanner
from romverse.rom.forge import ForgeBundleService
from romverse.rom.guided import GuidedMissionState, GuidedMissionStore
from romverse.rom.inspection import RomInspectionService
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from tests._ascension_trust import ExplicitTestRootReleaseService


def _prepared_project(tmp_path: Path) -> tuple[RomProjectStore, str]:
    source = tmp_path / "firmware.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("META/info.txt", b"ROMVERSE\n")
        archive.writestr("IMAGES/system.img", b"system-image")
        archive.writestr("IMAGES/init_boot.img", _boot_v4(b"pristine ramdisk"))
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Forge", "generic.android")
    store.import_original(project.project_id, source)
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    inspection.extract_project_tree(project.project_id)
    RomBuildPlanner(store).plan(project.project_id)
    return store, project.project_id


def _boot_v4(ramdisk: bytes, kernel: bytes = b"") -> bytes:
    header = bytearray(1584)
    header[:8] = b"ANDROID!"
    struct.pack_into("<I", header, 8, len(kernel))
    struct.pack_into("<I", header, 12, len(ramdisk))
    struct.pack_into("<I", header, 20, len(header))
    struct.pack_into("<I", header, 40, 4)
    image = bytes(header).ljust(4096, b"\0") + kernel
    image = image.ljust((len(image) + 4095) // 4096 * 4096, b"\0")
    return image + ramdisk


def _prepare_rooted_input(
    tmp_path: Path,
    store: RomProjectStore,
    project_id: str,
    method: AscensionMethod,
    *,
    payload_partition: bool = False,
):
    relative = (
        Path("partitions/init_boot.img") if payload_partition else Path("IMAGES/init_boot.img")
    )
    target = (
        store.working_root / project_id / relative
        if payload_partition
        else store.working_root / project_id / "tree" / relative
    )
    if payload_partition:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_boot_v4(b"payload pristine ramdisk"))
    AscensionEvidenceService(store).ensure(project_id, relative.as_posix())
    manager_name = (
        "Magisk-v30.7.apk" if method is AscensionMethod.MAGISK else "KernelSU_v3.3.0-release.apk"
    )
    repository = "topjohnwu/Magisk" if method is AscensionMethod.MAGISK else "tiann/KernelSU"
    tag = "v30.7" if method is AscensionMethod.MAGISK else "v3.3.0"
    manager = store.workspace / "tools" / "forge-test" / manager_name
    manager.parent.mkdir(parents=True, exist_ok=True)
    manager.write_bytes(f"official {method.value} manager".encode())
    asset = OfficialRootAsset(
        method,
        repository,
        tag,
        "2026-08-29T00:00:00Z",
        manager_name,
        manager.stat().st_size,
        hashlib.sha256(manager.read_bytes()).hexdigest(),
        f"https://github.com/{repository}/releases/download/{tag}/{manager_name}",
    )
    release = OfficialRootRelease(
        method,
        repository,
        tag,
        asset.published_at,
        asset,
        f"https://github.com/{repository}/releases/tag/{tag}",
    )
    preparation = RootPatchPreparationService(
        store,
        ExplicitTestRootReleaseService(release, manager),
    )
    preparation.prepare(project_id, method, release, manager)
    patched = tmp_path / f"{method.value}-forge-patched.img"
    patched.write_bytes(_boot_v4(f"rooted by {method.value}".encode()))
    patched_receipt = preparation.import_patched(project_id, method, patched)
    RootRomIntegrationService(store).integrate(project_id, method)
    return target, patched_receipt


def test_forge_bundle_is_deterministic_verified_and_truthfully_non_flashable(
    tmp_path: Path,
) -> None:
    store, project_id = _prepared_project(tmp_path)
    service = ForgeBundleService(store)

    first = service.create(project_id)
    second = service.create(project_id)

    assert first.output_path == second.output_path
    assert first.archive_sha256 == second.archive_sha256
    assert first.schema_version == 2
    assert not first.build_plan_digest
    assert not first.source_sha256
    assert not first.toolchain_manifest_digest
    assert not first.guided_choice_digest
    assert not first.signed and not first.bootable and not first.flashable
    assert service.verify(project_id).valid
    output = store.workspace / first.output_path
    with zipfile.ZipFile(output) as archive:
        assert archive.namelist()[0] == service.MANIFEST_MEMBER
        manifest = json.loads(archive.read(service.MANIFEST_MEMBER))
        assert manifest["schema_version"] == 3
        assert manifest["safety"] == {
            "bootable": False,
            "flashable": False,
            "phone_changed": False,
            "protected_original_included": False,
            "signed": False,
        }
        assert "tree/IMAGES/system.img" in archive.namelist()
        assert all("original_roms" not in name for name in archive.namelist())


def test_schema3_forge_requires_fresh_bound_tool_evidence(tmp_path: Path) -> None:
    store, project_id = _prepared_project(tmp_path)
    tool = store.workspace / "fixture-tools" / "romverse-bound-python"
    tool.parent.mkdir()
    tool.write_bytes(b"verified python fixture")
    statuses = (ToolStatus("Python", True, str(tool), "fixture", "Ready"),)
    GuidedMissionStore(store.projects_root / project_id).save(
        GuidedMissionState(
            customization_skipped=True,
            recipe_skipped=True,
            root_choice="skip",
        )
    )
    RomBuildPlanner(store, statuses, ("Python",)).plan(project_id)

    with pytest.raises(ProjectError, match="Fresh source-scoped tool evidence"):
        ForgeBundleService(store).create(project_id)
    tool.write_bytes(b"changed after planning")
    with pytest.raises(ProjectError, match="tool evidence changed"):
        ForgeBundleService(store, statuses).create(project_id)
    assert ForgeBundleService(store).load_receipt(project_id) is None


def test_schema3_forge_receipt_cannot_be_downgraded_to_legacy(tmp_path: Path) -> None:
    store, project_id = _prepared_project(tmp_path)
    tool = store.workspace / "fixture-tools" / "romverse-bound-python"
    tool.parent.mkdir()
    tool.write_bytes(b"verified python fixture")
    statuses = (ToolStatus("Python", True, str(tool), "fixture", "Ready"),)
    GuidedMissionStore(store.projects_root / project_id).save(
        GuidedMissionState(
            customization_skipped=True,
            recipe_skipped=True,
            root_choice="skip",
        )
    )
    RomBuildPlanner(store, statuses, ("Python",)).plan(project_id)
    service = ForgeBundleService(store, statuses)
    receipt = service.create(project_id)
    assert receipt.schema_version == 3
    assert service.verify(project_id).valid

    receipt_path = store.projects_root / project_id / service.RECEIPT_NAME
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["schema_version"] = 2
    for field in (
        "build_plan_digest",
        "source_sha256",
        "toolchain_manifest_digest",
        "guided_choice_digest",
    ):
        payload[field] = ""
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    verification = service.verify(project_id)
    assert not verification.valid
    assert verification.status == "Forge Bundle exact build-plan binding is invalid"


def test_forge_history_collision_never_overwrites_existing_evidence(tmp_path: Path) -> None:
    store, project_id = _prepared_project(tmp_path)
    service = ForgeBundleService(store)
    receipt = service.create(project_id)
    history_digest = service.preserve_history(project_id, receipt)
    history_path = (
        store.projects_root / project_id / "forge-history" / f"{history_digest}.romverse"
    )
    history_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ProjectError, match="content-address collision"):
        service.preserve_history(project_id, receipt)

    assert history_path.read_text(encoding="utf-8") == "{}\n"
    assert service.load_receipt(project_id) == receipt
    assert service.verify(project_id).valid


def test_forge_bundle_streams_zip64_members_and_reports_every_long_phase(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store, project_id = _prepared_project(tmp_path)
    tree = store.working_root / project_id / "tree"
    (tree / "IMAGES" / "large-super.img").write_bytes(b"R" * 4096)
    RomBuildPlanner(store).plan(project_id)
    # Exercise the real ZIP64 branch without allocating a multi-gigabyte test image.
    monkeypatch.setattr(zipfile, "ZIP64_LIMIT", 1024)
    create_progress: list[tuple[int, int]] = []
    verify_progress: list[tuple[int, int]] = []
    service = ForgeBundleService(store)

    receipt = service.create(project_id, lambda done, total: create_progress.append((done, total)))
    verification = service.verify(
        project_id,
        lambda done, total: verify_progress.append((done, total)),
    )

    assert verification.valid
    assert create_progress[-1][0] == create_progress[-1][1]
    assert verify_progress[-1][0] == verify_progress[-1][1]
    assert sum(done >= total for done, total in create_progress) == 1
    assert sum(done >= total for done, total in verify_progress) == 1
    assert all(
        previous[0] <= current[0]
        for previous, current in zip(create_progress, create_progress[1:], strict=False)
    )
    with zipfile.ZipFile(store.workspace / receipt.output_path) as archive:
        assert archive.getinfo("tree/IMAGES/large-super.img").file_size == 4096


def test_forge_bundle_refuses_tree_changes_after_plan(tmp_path: Path) -> None:
    store, project_id = _prepared_project(tmp_path)
    tree = store.working_root / project_id / "tree"
    (tree / "extra.txt").write_text("not planned", encoding="utf-8")

    with pytest.raises(ProjectError, match="file set changed"):
        ForgeBundleService(store).create(project_id)


def test_forge_bundle_stops_before_writing_when_destination_space_is_insufficient(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store, project_id = _prepared_project(tmp_path)
    monkeypatch.setattr(
        "romverse.rom.forge.shutil.disk_usage",
        lambda _path: SimpleNamespace(free=1),
    )

    with pytest.raises(ProjectError, match="needs .* free.*1 B is available"):
        ForgeBundleService(store).create(project_id)

    output_root = store.workspace / "builds" / project_id
    assert not tuple(output_root.glob("*.forge.part"))


def test_forge_bundle_rejects_tampered_escape_path(tmp_path: Path) -> None:
    store, project_id = _prepared_project(tmp_path)
    plan_path = store.projects_root / project_id / RomBuildPlanner.PLAN_NAME
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["input_files"] = ["../outside.img"]
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    with pytest.raises(ProjectError, match="unsafe relative path"):
        ForgeBundleService(store).create(project_id)


def test_forge_bundle_verification_detects_archive_tampering(tmp_path: Path) -> None:
    store, project_id = _prepared_project(tmp_path)
    service = ForgeBundleService(store)
    receipt = service.create(project_id)
    with (store.workspace / receipt.output_path).open("ab") as output:
        output.write(b"tampered")

    result = service.verify(project_id)

    assert not result.valid
    assert result.status == "Forge Bundle archive hash mismatch"


def test_forge_bundle_rejects_duplicate_cross_platform_paths(tmp_path: Path) -> None:
    store, project_id = _prepared_project(tmp_path)
    plan_path = store.projects_root / project_id / RomBuildPlanner.PLAN_NAME
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["input_files"] = ["META/info.txt", "meta/INFO.txt"]
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    with pytest.raises(ProjectError, match="duplicate input paths"):
        ForgeBundleService(store).create(project_id)


def test_forge_bundle_preserves_symlink_metadata_without_following_target(tmp_path: Path) -> None:
    store, project_id = _prepared_project(tmp_path)
    tree = store.working_root / project_id / "tree"
    external = tmp_path / "external-secret"
    external.write_bytes(b"outside bytes must not enter the bundle")
    link = tree / "system-link"
    link.symlink_to(external)
    RomBuildPlanner(store).plan(project_id)

    receipt = ForgeBundleService(store).create(project_id)

    with zipfile.ZipFile(store.workspace / receipt.output_path) as archive:
        info = archive.getinfo("tree/system-link")
        assert (info.external_attr >> 16) & 0o170000 == 0o120000
        assert archive.read(info).decode() == str(external)
        assert b"outside bytes" not in archive.read(info)
    assert ForgeBundleService(store).verify(project_id).valid


def test_forge_bundle_binds_fastboot_tree_ascension_build_seal(tmp_path: Path) -> None:
    store, project_id = _prepared_project(tmp_path)
    target, patched = _prepare_rooted_input(tmp_path, store, project_id, AscensionMethod.MAGISK)
    seal = RootRomBuildHandoffService(store).seal(project_id, AscensionMethod.MAGISK)

    service = ForgeBundleService(store)
    receipt = service.create(project_id)

    assert receipt.ascension_handoff_digest == seal.handoff_digest
    assert receipt.rooted_partition == "init_boot"
    assert receipt.rooted_artifact_sha256 == patched.patched_image_sha256
    with zipfile.ZipFile(store.workspace / receipt.output_path) as archive:
        manifest = json.loads(archive.read(service.MANIFEST_MEMBER))
        assert manifest["ascension"]["member"] == "tree/IMAGES/init_boot.img"
        assert manifest["ascension"]["packaging_route"] == "fastboot-image-tree"
        assert manifest["ascension"]["bootloader_relock_allowed"] is False
        assert archive.read("tree/IMAGES/init_boot.img") == target.read_bytes()
        assert not any(name.startswith("ascension/") for name in archive.namelist())
    assert service.verify(project_id).valid


def test_forge_bundle_embeds_payload_ascension_artifact_with_provenance(
    tmp_path: Path,
) -> None:
    store, project_id = _prepared_project(tmp_path)
    target, patched = _prepare_rooted_input(
        tmp_path,
        store,
        project_id,
        AscensionMethod.KERNELSU_LKM,
        payload_partition=True,
    )
    seal = RootRomBuildHandoffService(store).seal(project_id, AscensionMethod.KERNELSU_LKM)

    service = ForgeBundleService(store)
    receipt = service.create(project_id)

    assert receipt.ascension_handoff_digest == seal.handoff_digest
    with zipfile.ZipFile(store.workspace / receipt.output_path) as archive:
        manifest = json.loads(archive.read(service.MANIFEST_MEMBER))
        member = "ascension/rooted-init_boot.img"
        assert manifest["ascension"]["member"] == member
        assert manifest["ascension"]["packaging_route"] == "payload-partition"
        assert archive.read(member) == target.read_bytes()
        assert hashlib.sha256(archive.read(member)).hexdigest() == patched.patched_image_sha256
    assert service.verify(project_id).valid


def test_forge_bundle_refuses_integrated_root_without_build_seal(tmp_path: Path) -> None:
    store, project_id = _prepared_project(tmp_path)
    _prepare_rooted_input(tmp_path, store, project_id, AscensionMethod.MAGISK)
    RomBuildPlanner(store).plan(project_id)

    with pytest.raises(ProjectError, match="Ascension Build Seal"):
        ForgeBundleService(store).create(project_id)
