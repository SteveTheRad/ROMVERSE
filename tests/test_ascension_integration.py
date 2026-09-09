from __future__ import annotations

import hashlib
import json
import stat
import struct
from pathlib import Path

import pytest

from romverse.ascension.build_handoff import RootRomBuildHandoffService
from romverse.ascension.evidence import AscensionEvidenceService
from romverse.ascension.integration import RootRomIntegrationService
from romverse.ascension.models import AscensionMethod, OfficialRootAsset, OfficialRootRelease
from romverse.ascension.preparation import RootPatchPreparationService
from romverse.rom.inspection import RomInspectionService
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from tests._ascension_trust import ExplicitTestRootReleaseService


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


def _prepared(
    tmp_path: Path,
    method: AscensionMethod,
    *,
    payload_partition: bool = False,
    patched_kernel: bytes = b"stock kernel",
):
    source = tmp_path / "popsicle_images_OS3.0.318.0.WPBCNXM_test.tgz"
    source.write_bytes(b"protected firmware")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create(f"Root ROM {method.value}")
    store.import_original(project.project_id, source)
    RomInspectionService(store).inspect_project(project.project_id)
    if payload_partition:
        root = store.working_root / project.project_id
        relative = Path("partitions/init_boot.img")
    else:
        root = store.working_root / project.project_id / "tree"
        relative = Path("images/init_boot.img")
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    pristine = _boot_v4(b"pristine ramdisk", b"stock kernel")
    target.write_bytes(pristine)
    AscensionEvidenceService(store).ensure(project.project_id, relative.as_posix())

    manager_name = (
        "Magisk-v30.7.apk" if method is AscensionMethod.MAGISK else "KernelSU_v3.3.0-release.apk"
    )
    repository = "topjohnwu/Magisk" if method is AscensionMethod.MAGISK else "tiann/KernelSU"
    tag = "v30.7" if method is AscensionMethod.MAGISK else "v3.3.0"
    manager = store.workspace / "tools" / "test" / manager_name
    manager.parent.mkdir(parents=True)
    manager.write_bytes(f"official {method.value} manager".encode())
    digest = hashlib.sha256(manager.read_bytes()).hexdigest()
    asset = OfficialRootAsset(
        method,
        repository,
        tag,
        "2026-08-29T00:00:00Z",
        manager_name,
        manager.stat().st_size,
        digest,
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
    preparation.prepare(project.project_id, method, release, manager)
    patched_source = tmp_path / f"{method.value}-patched.img"
    patched_source.write_bytes(_boot_v4(f"patched by {method.value}".encode(), patched_kernel))
    patched = preparation.import_patched(project.project_id, method, patched_source)
    return store, project.project_id, source, target, pristine, patched


def _redigest(document: dict[str, object], digest_field: str) -> None:
    payload = {key: value for key, value in document.items() if key not in {"format", digest_field}}
    document[digest_field] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _upstream_chain(tmp_path: Path):
    store, project_id, _source, target, pristine, _patched = _prepared(
        tmp_path, AscensionMethod.MAGISK
    )
    evidence = AscensionEvidenceService(store)
    preparation = RootPatchPreparationService(store)
    integration = RootRomIntegrationService(store)
    integration_receipt = integration.integrate(project_id, AscensionMethod.MAGISK)
    build = RootRomBuildHandoffService(store)
    build_receipt = build.seal(project_id, AscensionMethod.MAGISK)
    paths = {
        "rollback": store.projects_root / project_id / "ascension" / evidence.RECEIPT_NAME,
        "capsule": store.projects_root
        / project_id
        / "ascension"
        / "capsules"
        / AscensionMethod.MAGISK.value
        / preparation.RECEIPT_NAME,
        "patched": store.projects_root
        / project_id
        / "ascension"
        / "patched"
        / AscensionMethod.MAGISK.value
        / preparation.PATCHED_NAME,
        "integration": store.projects_root
        / project_id
        / "ascension"
        / "integration"
        / integration.RECEIPT_NAME,
        "build": store.projects_root
        / project_id
        / "ascension"
        / "build-handoff"
        / build.RECEIPT_NAME,
    }
    loaders = {
        "rollback": lambda: evidence.load(project_id),
        "capsule": lambda: preparation.load(project_id, AscensionMethod.MAGISK),
        "patched": lambda: preparation.load_patched(project_id, AscensionMethod.MAGISK),
        "integration": lambda: integration.load(project_id, AscensionMethod.MAGISK),
        "build": lambda: build.load(project_id, AscensionMethod.MAGISK),
    }
    return (
        store,
        project_id,
        target,
        pristine,
        integration_receipt,
        build_receipt,
        paths,
        loaders,
    )


def test_kernelsu_lkm_rejects_a_changed_kernel(tmp_path: Path) -> None:
    with pytest.raises(ProjectError, match="KernelSU LKM output changed the pristine kernel"):
        _prepared(
            tmp_path,
            AscensionMethod.KERNELSU_LKM,
            patched_kernel=b"other kernel",
        )


def test_magisk_kernel_change_is_preserved_as_caution_evidence(tmp_path: Path) -> None:
    _store, _project_id, _source, _target, _pristine, patched = _prepared(
        tmp_path,
        AscensionMethod.MAGISK,
        patched_kernel=b"other kernel",
    )

    assert patched.lineage_scope == "normalized-header-magisk-kernel-modified"
    assert patched.lineage_confidence == "caution"
    assert patched.source_kernel_sha256 != patched.patched_kernel_sha256


@pytest.mark.parametrize(
    ("method", "payload_partition"),
    (
        (AscensionMethod.MAGISK, False),
        (AscensionMethod.KERNELSU_LKM, True),
    ),
)
def test_verified_root_image_integrates_locally_and_rolls_back(
    tmp_path: Path,
    method: AscensionMethod,
    payload_partition: bool,
) -> None:
    store, project_id, source, target, pristine, patched = _prepared(
        tmp_path, method, payload_partition=payload_partition
    )
    service = RootRomIntegrationService(store)
    progress: list[int] = []

    receipt = service.integrate(project_id, method, progress.append)

    assert target.read_bytes() != pristine
    assert hashlib.sha256(target.read_bytes()).hexdigest() == patched.patched_image_sha256
    assert source.read_bytes() == b"protected firmware"
    assert receipt.authority == "isolated-rom-build-only"
    assert receipt.build_plan_refresh_required
    assert not receipt.phone_changed
    assert not receipt.bootloader_relock_allowed
    assert progress[0] == 0
    assert progress[-1] == 100
    assert progress == sorted(progress)
    assert any(0 < value < 100 for value in progress)
    assert service.load(project_id, method) == receipt

    build_progress: list[int] = []
    handoff_service = RootRomBuildHandoffService(store)
    handoff = handoff_service.seal(project_id, method, build_progress.append)
    artifact = store.workspace / handoff.artifact_relative_path
    assert artifact.read_bytes() == target.read_bytes()
    assert handoff.artifact_sha256 == patched.patched_image_sha256
    assert handoff.authority == "contained-rom-build-input-only"
    assert not handoff.flash_authority
    assert not handoff.phone_changed
    assert not handoff.bootloader_relock_allowed
    assert build_progress == []
    assert handoff_service.load(project_id, method) == handoff

    rollback = service.rollback_latest(project_id, method)

    assert rollback.success and not rollback.phone_changed
    assert target.read_bytes() == pristine
    assert service.load(project_id, method) is None
    assert handoff_service.load(project_id, method) is None


def test_root_rom_integration_fails_closed_if_working_input_changed(tmp_path: Path) -> None:
    store, project_id, _source, target, _pristine, _patched = _prepared(
        tmp_path, AscensionMethod.MAGISK
    )
    target.write_bytes(_boot_v4(b"unexpected third-party change"))

    with pytest.raises(ProjectError, match="pristine source-bound image"):
        RootRomIntegrationService(store).integrate(project_id, AscensionMethod.MAGISK)


def test_root_rom_integration_receipt_cannot_authorize_phone_or_relock(tmp_path: Path) -> None:
    store, project_id, _source, _target, _pristine, _patched = _prepared(
        tmp_path, AscensionMethod.MAGISK
    )
    service = RootRomIntegrationService(store)
    service.integrate(project_id, AscensionMethod.MAGISK)
    receipt_path = (
        store.projects_root / project_id / "ascension" / "integration" / service.RECEIPT_NAME
    )
    data = json.loads(receipt_path.read_text(encoding="utf-8"))
    data["phone_changed"] = True
    data["bootloader_relock_allowed"] = True
    data["authority"] = "fastboot"
    receipt_path.write_text(json.dumps(data), encoding="utf-8")

    assert service.load(project_id, AscensionMethod.MAGISK) is None


def test_root_build_handoff_rejects_tampered_authority_or_artifact(tmp_path: Path) -> None:
    store, project_id, _source, _target, _pristine, _patched = _prepared(
        tmp_path, AscensionMethod.MAGISK
    )
    RootRomIntegrationService(store).integrate(project_id, AscensionMethod.MAGISK)
    service = RootRomBuildHandoffService(store)
    receipt = service.seal(project_id, AscensionMethod.MAGISK)
    receipt_path = (
        store.projects_root / project_id / "ascension" / "build-handoff" / service.RECEIPT_NAME
    )
    document = json.loads(receipt_path.read_text(encoding="utf-8"))
    document["flash_authority"] = True
    document["bootloader_relock_allowed"] = True
    receipt_path.write_text(json.dumps(document), encoding="utf-8")
    assert service.load(project_id, AscensionMethod.MAGISK) is None

    service.seal(project_id, AscensionMethod.MAGISK)
    artifact = store.workspace / receipt.artifact_relative_path
    artifact.write_bytes(b"tampered root image")
    assert service.load(project_id, AscensionMethod.MAGISK) is None


def test_legacy_root_build_handoff_upgrades_without_losing_verified_artifact(
    tmp_path: Path,
) -> None:
    store, project_id, _source, _target, _pristine, _patched = _prepared(
        tmp_path, AscensionMethod.MAGISK
    )
    RootRomIntegrationService(store).integrate(project_id, AscensionMethod.MAGISK)
    service = RootRomBuildHandoffService(store)
    current = service.seal(project_id, AscensionMethod.MAGISK)
    receipt_path = (
        store.projects_root / project_id / "ascension" / "build-handoff" / service.RECEIPT_NAME
    )
    document = json.loads(receipt_path.read_text(encoding="utf-8"))
    legacy_payload = {
        key: value
        for key, value in document.items()
        if key
        not in {
            "format",
            "handoff_digest",
            "build_plan_tree_sha256",
            "build_plan_bound",
        }
    }
    legacy_payload["schema_version"] = 1
    document = {
        "format": service.FORMAT,
        **legacy_payload,
        "handoff_digest": hashlib.sha256(
            json.dumps(legacy_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    receipt_path.write_text(json.dumps(document), encoding="utf-8")

    legacy = service.load(project_id, AscensionMethod.MAGISK)
    assert legacy is not None and legacy.schema_version == 1
    assert legacy.artifact_sha256 == current.artifact_sha256

    upgraded = service.seal(project_id, AscensionMethod.MAGISK)
    assert upgraded.schema_version == 2
    assert upgraded.artifact_sha256 == current.artifact_sha256
    assert service.load(project_id, AscensionMethod.MAGISK) == upgraded


def test_incomplete_root_integration_recovers_pristine_input_before_retry(tmp_path: Path) -> None:
    store, project_id, _source, target, pristine, patched = _prepared(
        tmp_path, AscensionMethod.MAGISK
    )
    service = RootRomIntegrationService(store)
    snapshot = store.snapshots_root / project_id / "ascension-root" / "interrupted" / "pristine.img"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(pristine)
    target.write_bytes((store.workspace / patched.patched_image_path).read_bytes())
    unsigned = {
        "schema_version": 1,
        "project_id": project_id,
        "method": AscensionMethod.MAGISK.value,
        "target_relative_path": "images/init_boot.img",
        "snapshot_relative_path": snapshot.relative_to(store.workspace).as_posix(),
        "snapshot_size_bytes": snapshot.stat().st_size,
        "pristine_image_sha256": hashlib.sha256(pristine).hexdigest(),
        "patched_image_sha256": patched.patched_image_sha256,
        "phone_changed": False,
    }
    transaction = {
        "format": "romverse.root-rom-integration-transaction",
        **unsigned,
        "transaction_digest": hashlib.sha256(
            json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    transaction_path = (
        store.projects_root / project_id / "ascension" / "integration" / service.TRANSACTION_NAME
    )
    transaction_path.parent.mkdir(parents=True)
    transaction_path.write_text(json.dumps(transaction), encoding="utf-8")

    receipt = service.integrate(project_id, AscensionMethod.MAGISK)

    assert receipt.integrated_image_sha256 == patched.patched_image_sha256
    assert not transaction_path.exists()
    assert service.rollback_latest(project_id, AscensionMethod.MAGISK).success
    assert target.read_bytes() == pristine


def test_upstream_ascension_chain_uses_private_bounded_evidence(tmp_path: Path) -> None:
    (
        store,
        project_id,
        _target,
        _pristine,
        integration_receipt,
        build_receipt,
        paths,
        loaders,
    ) = _upstream_chain(tmp_path)

    assert all(loader() is not None for loader in loaders.values())
    for path in paths.values():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700

    integration_root = paths["integration"].parent
    integration_history = integration_root / (
        f"integration-{integration_receipt.integration_id[:12]}.romverse"
    )
    build_root = paths["build"].parent
    build_history = build_root / f"build-handoff-{build_receipt.handoff_id[:12]}.romverse"
    snapshot = store.workspace / integration_receipt.snapshot_relative_path
    artifact = store.workspace / build_receipt.artifact_relative_path
    assert stat.S_IMODE(integration_history.stat().st_mode) == 0o600
    assert stat.S_IMODE(build_history.stat().st_mode) == 0o600
    assert stat.S_IMODE(snapshot.stat().st_mode) == 0o600
    assert stat.S_IMODE(artifact.stat().st_mode) == 0o600


def test_upstream_ascension_loaders_reject_oversized_and_linked_receipts(
    tmp_path: Path,
) -> None:
    store, _project_id, _target, _pristine, *_rest, paths, loaders = _upstream_chain(tmp_path)
    maximum = RootRomBuildHandoffService.MAX_RECEIPT_BYTES

    for name, path in paths.items():
        original = path.read_bytes()
        with path.open("r+b") as stream:
            stream.truncate(maximum + 1)
        assert loaders[name]() is None
        path.write_bytes(original)

        outside = tmp_path / f"outside-{name}.romverse"
        outside.write_bytes(original)
        path.unlink()
        path.symlink_to(outside)
        assert loaders[name]() is None
        path.unlink()
        path.write_bytes(original)

    assert all(loader() is not None for loader in loaders.values())
    assert store.workspace.is_dir()


def test_upstream_ascension_loaders_reject_extra_fields_and_redigested_type_confusion(
    tmp_path: Path,
) -> None:
    _store, _project_id, _target, _pristine, *_rest, paths, loaders = _upstream_chain(tmp_path)
    changes = {
        "rollback": ("schema_version", True, "record_digest"),
        "capsule": ("input_image_size_bytes", True, "capsule_digest"),
        "patched": ("patched_image_size_bytes", True, "receipt_digest"),
        "integration": ("snapshot_size_bytes", True, "integration_digest"),
        "build": ("artifact_size_bytes", True, "handoff_digest"),
    }

    for name, path in paths.items():
        original = path.read_bytes()
        document = json.loads(original)
        document["unexpected_field"] = "must fail closed"
        path.write_text(json.dumps(document), encoding="utf-8")
        assert loaders[name]() is None

        document = json.loads(original)
        field, value, digest_field = changes[name]
        document[field] = value
        _redigest(document, digest_field)
        path.write_text(json.dumps(document), encoding="utf-8")
        assert loaders[name]() is None
        path.write_bytes(original)

    assert all(loader() is not None for loader in loaders.values())


def test_redirected_build_evidence_directory_fails_without_escaping_workspace(
    tmp_path: Path,
) -> None:
    store, project_id, _target, _pristine, *_rest, paths, loaders = _upstream_chain(tmp_path)
    root = paths["build"].parent
    saved = root.with_name("build-handoff-saved")
    root.rename(saved)
    outside = tmp_path / "redirected-build-evidence"
    outside.mkdir()
    root.symlink_to(outside, target_is_directory=True)

    assert loaders["build"]() is None
    with pytest.raises(ProjectError, match="vault could not be prepared safely"):
        RootRomBuildHandoffService(store).seal(project_id, AscensionMethod.MAGISK)
    assert not tuple(outside.iterdir())


def test_linked_incomplete_transaction_stops_before_local_rom_input_changes(
    tmp_path: Path,
) -> None:
    store, project_id, _source, target, pristine, _patched = _prepared(
        tmp_path, AscensionMethod.MAGISK
    )
    service = RootRomIntegrationService(store)
    integration_root = store.projects_root / project_id / "ascension" / "integration"
    integration_root.mkdir(parents=True)
    outside = tmp_path / "untrusted-transaction.romverse"
    outside.write_text("{}", encoding="utf-8")
    (integration_root / service.TRANSACTION_NAME).symlink_to(outside)

    with pytest.raises(ProjectError, match="invalid recovery metadata"):
        service.integrate(project_id, AscensionMethod.MAGISK)
    assert target.read_bytes() == pristine
