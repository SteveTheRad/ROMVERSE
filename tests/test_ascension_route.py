from __future__ import annotations

import json
import stat
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from romverse.ascension.models import (
    AscensionAssessment,
    AscensionGate,
    AscensionMethod,
    AscensionRecommendation,
    GateState,
    OfficialRootAsset,
    OfficialRootRelease,
)
from romverse.ascension.route import AscensionRouteRecordService
from romverse.ascension.route import _digest as _route_digest
from romverse.ascension.support import (
    KernelSuSupportEvidenceService,
)
from romverse.ascension.support import (
    _digest as _support_digest,
)
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.registry import DevicePackRegistry
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from tests._ascension_trust import ExplicitTestRootReleaseService


class _Assessment:
    def __init__(self, *, ready: bool) -> None:
        self.ready = ready

    def recommend(self, project_id, device=None, companion=None):
        del project_id, device, companion
        return AscensionRecommendation(
            AscensionMethod.MAGISK,
            "Magisk image patch recommended" if self.ready else "Complete checks first",
            "Exact evidence permits contained preparation only."
            if self.ready
            else "ROMVERSE needs more evidence before selecting a route.",
            ("Protected source inspected",),
            self.ready,
        )

    def assess(self, project_id, method, device=None, companion=None):
        del device, companion
        gate = AscensionGate(
            "source",
            "Protected source",
            GateState.PASS if self.ready else GateState.BLOCKED,
            "Exact source is protected" if self.ready else "Source identity is unresolved",
            "Complete automatic detection" if not self.ready else "",
        )
        return AscensionAssessment(
            project_id,
            method,
            "Xiaomi popsicle fastboot firmware",
            "init_boot.img" if self.ready else "",
            (gate,),
            True,
        )


def _project(tmp_path: Path) -> tuple[RomProjectStore, str]:
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Ascension route")
    source = tmp_path / "popsicle_images_OS3.0.318.0.WPBCNXM_test.tgz"
    source.write_bytes(b"protected-firmware")
    store.import_original(project.project_id, source)
    return store, project.project_id


def _device() -> AndroidDevice:
    return AndroidDevice(
        "authorized-serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        codename="popsicle",
        kernel_version="6.12.23-android16-0-popsicle",
    )


def test_route_record_persists_one_safe_source_bound_decision(tmp_path: Path) -> None:
    store, project_id = _project(tmp_path)
    service = AscensionRouteRecordService(
        store,
        DevicePackRegistry(()),
        _Assessment(ready=True),  # type: ignore[arg-type]
    )

    record = service.resolve(project_id, _device())
    repeated = service.resolve(project_id, _device())

    assert record == repeated
    assert record.recommended_method is AscensionMethod.MAGISK
    assert record.schema_version == 2
    assert record.patch_target == "init_boot.img"
    assert record.ready_for_local_preparation
    assert record.state == "unconfirmed"
    assert record.confidence == "unconfirmed"
    assert record.source_authority == "unconfirmed"
    assert record.execution_authority == "none"
    assert record.command_manifest == ()
    assert not record.bootloader_relock_allowed
    assert not record.phone_changed
    assert service.load(project_id) == record
    assert service.matches_device(record, _device())
    assert not service.matches_device(
        record,
        replace(_device(), kernel_version="6.12.24-android16-0-popsicle"),
    )


def test_blocked_route_record_authorizes_nothing(tmp_path: Path) -> None:
    store, project_id = _project(tmp_path)
    service = AscensionRouteRecordService(
        store,
        DevicePackRegistry(()),
        _Assessment(ready=False),  # type: ignore[arg-type]
    )

    record = service.resolve(project_id, _device())

    assert record.state == "blocked"
    assert record.confidence == "unconfirmed"
    assert record.recommended_method is None
    assert record.candidate_method is AscensionMethod.MAGISK
    assert record.blocker_count == 1
    assert not record.ready_for_local_preparation
    assert record.execution_authority == "none"


def test_route_record_invalidates_when_device_dna_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store, project_id = _project(tmp_path)
    service = AscensionRouteRecordService(
        store,
        DevicePackRegistry(()),
        _Assessment(ready=True),  # type: ignore[arg-type]
    )
    service.resolve(project_id, _device())

    monkeypatch.setattr(
        "romverse.ascension.route.DeviceDnaStore.load",
        lambda _self, _project_id: SimpleNamespace(profile_digest="f" * 64),
    )

    assert service.load(project_id) is None


def test_route_record_rejects_tampered_execution_authority(tmp_path: Path) -> None:
    store, project_id = _project(tmp_path)
    service = AscensionRouteRecordService(
        store,
        DevicePackRegistry(()),
        _Assessment(ready=True),  # type: ignore[arg-type]
    )
    service.resolve(project_id, _device())
    path = store.projects_root / project_id / "ascension" / "route" / service.RECORD_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["execution_authority"] = "flash"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert service.load(project_id) is None


def test_route_record_storage_is_private_bounded_and_type_strict(tmp_path: Path) -> None:
    store, project_id = _project(tmp_path)
    service = AscensionRouteRecordService(
        store,
        DevicePackRegistry(()),
        _Assessment(ready=True),  # type: ignore[arg-type]
    )
    service.resolve(project_id, _device())
    root = store.projects_root / project_id / "ascension" / "route"
    path = root / service.RECORD_NAME

    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["ready_for_local_preparation"] = 1
    unsigned = {
        key: value for key, value in payload.items() if key not in {"format", "record_digest"}
    }
    payload["record_digest"] = _route_digest(unsigned)
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load(project_id) is None

    service.resolve(project_id, _device())
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected"] = "field"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load(project_id) is None

    with path.open("wb") as stream:
        stream.truncate(service.MAX_BYTES + 1)
    assert service.load(project_id) is None

    outside = tmp_path / "outside-route.romverse"
    outside.write_text("{}", encoding="utf-8")
    path.unlink()
    path.symlink_to(outside)
    assert service.load(project_id) is None


def test_route_record_refuses_redirected_evidence_directory(tmp_path: Path) -> None:
    store, project_id = _project(tmp_path)
    service = AscensionRouteRecordService(
        store,
        DevicePackRegistry(()),
        _Assessment(ready=True),  # type: ignore[arg-type]
    )
    outside = tmp_path / "outside-route"
    outside.mkdir()
    ascension = store.projects_root / project_id / "ascension"
    ascension.mkdir()
    (ascension / "route").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ProjectError, match="stored safely"):
        service.resolve(project_id, _device())


def _support_service(
    store: RomProjectStore,
    manager: Path,
) -> KernelSuSupportEvidenceService:
    manager.write_bytes(b"verified-kernelsu-manager")
    digest = "a" * 64
    asset = OfficialRootAsset(
        AscensionMethod.KERNELSU_LKM,
        "tiann/KernelSU",
        "v3.3.0",
        "2026-08-30T00:00:00Z",
        "KernelSU_v3.3.0-release.apk",
        manager.stat().st_size,
        digest,
        "https://github.com/tiann/KernelSU/releases/download/v3.3.0/KernelSU_v3.3.0-release.apk",
    )
    release = OfficialRootRelease(
        AscensionMethod.KERNELSU_LKM,
        "tiann/KernelSU",
        "v3.3.0",
        "2026-08-30T00:00:00Z",
        asset,
        "https://github.com/tiann/KernelSU/releases/tag/v3.3.0",
    )
    return KernelSuSupportEvidenceService(
        store,
        ExplicitTestRootReleaseService(release, manager),  # type: ignore[arg-type]
    )


def test_kernelsu_support_storage_is_private_bounded_and_type_strict(tmp_path: Path) -> None:
    store, project_id = _project(tmp_path)
    service = _support_service(store, tmp_path / "manager.apk")
    evidence = service.record(project_id, _device(), "v3.3.0", "a" * 64, "supported")
    root = store.projects_root / project_id / "ascension"
    path = root / service.RECEIPT_NAME

    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert service.load(project_id, _device()) == evidence

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["manager_installed"] = 1
    unsigned = {
        key: value for key, value in payload.items() if key not in {"format", "evidence_digest"}
    }
    payload["evidence_digest"] = _support_digest(unsigned)
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load(project_id, _device()) is None

    service.record(project_id, _device(), "v3.3.0", "a" * 64, "supported")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected"] = "field"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load(project_id, _device()) is None

    with path.open("wb") as stream:
        stream.truncate(service.MAX_BYTES + 1)
    assert service.load(project_id, _device()) is None

    outside = tmp_path / "outside-support.romverse"
    outside.write_text("{}", encoding="utf-8")
    path.unlink()
    path.symlink_to(outside)
    assert service.load(project_id, _device()) is None


def test_kernelsu_support_refuses_redirected_evidence_directory(tmp_path: Path) -> None:
    store, project_id = _project(tmp_path)
    service = _support_service(store, tmp_path / "manager.apk")
    outside = tmp_path / "outside-support"
    outside.mkdir()
    ascension = store.projects_root / project_id / "ascension"
    ascension.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ProjectError, match="stored safely"):
        service.record(project_id, _device(), "v3.3.0", "a" * 64, "supported")
