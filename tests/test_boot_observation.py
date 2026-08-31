from __future__ import annotations

import json
import zipfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.models import (
    CapabilityStatus,
    DeviceBuildContract,
    DevicePack,
    DynamicPartitionGroup,
    FirmwareSourceContract,
    PackCapability,
    PartitionBuildRule,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.rom.boot_observation import BootObservationService, BootObservationStatus
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


def _fixture(tmp_path):
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"payload")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Boot", "test.exact")
    project = store.import_original(project.project_id, source)
    contract = DeviceBuildContract(
        "contract",
        1,
        FirmwareSourceContract("BUILD", project.original.sha256, "b" * 64),
        4096,
        512,
        2,
        False,
        (DynamicPartitionGroup("group", 4096),),
        (PartitionBuildRule("system", 512, 4096, "group", "opaque", "rebuild", "c" * 64),),
        ("system",),
        "d" * 64,
        "e" * 64,
        ("system.img", "vbmeta_system.img", "super.img"),
    )
    pack = DevicePack(
        "test.exact",
        "1",
        "Exact",
        10,
        ("test",),
        ("phone",),
        ("codename",),
        (
            PackCapability(
                "firmware.operations",
                "Build",
                CapabilityStatus.SUPPORTED,
                "model_specific",
                "Exact",
            ),
        ),
        (),
        "a" * 64,
        contract,
    )
    return store, project, DevicePackRegistry((pack,))


def _device(**changes):
    values = {
        "serial": "PRIVATE",
        "state": DeviceState.DEVICE,
        "manufacturer": "test",
        "model": "phone",
        "product": "codename",
        "codename": "codename",
        "build_id": "BUILD",
        "build_fingerprint": "test/codename/build",
        "boot_completed": True,
        "uptime_seconds": 1000,
        "slot_suffix": "_a",
        "battery_percent": 90,
    }
    values.update(changes)
    return AndroidDevice(**values)


def test_boot_observation_requires_time_based_stability_and_never_claims_flash(tmp_path):
    store, project, registry = _fixture(tmp_path)
    service = BootObservationService(store, registry)
    started = datetime(2026, 8, 29, tzinfo=UTC)

    first = service.observe(project.project_id, _device(), started)
    stable = service.observe(
        project.project_id,
        _device(uptime_seconds=1310),
        started + timedelta(seconds=310),
    )

    assert first.status is BootObservationStatus.WAITING
    assert stable.status is BootObservationStatus.STABLE
    assert stable.stable
    assert not stable.flash_linked
    assert not stable.verified_first_boot
    assert not stable.phone_changed
    assert service.load(project.project_id) == stable
    assert service.next_sample_wait_seconds(first, started + timedelta(seconds=30)) == 30
    assert service.next_sample_wait_seconds(first, started + timedelta(seconds=70)) == 0
    assert "five-minute" in service.next_step(first)
    assert "Guardian write receipt" in service.next_step(stable)


def test_boot_observation_detects_uptime_reset_and_build_change(tmp_path):
    store, project, registry = _fixture(tmp_path)
    service = BootObservationService(store, registry)
    started = datetime(2026, 8, 29, tzinfo=UTC)
    service.observe(project.project_id, _device(uptime_seconds=1000), started)

    rebooted = service.observe(
        project.project_id,
        _device(uptime_seconds=20),
        started + timedelta(seconds=70),
    )

    assert rebooted.status is BootObservationStatus.ATTENTION
    assert rebooted.reboot_detected
    assert "uptime reset" in rebooted.diagnosis
    assert "Stop and review" in service.next_step(rebooted)

    path = store.projects_root / project.project_id / service.NAME
    data = json.loads(path.read_text())
    data["samples"][-1]["build_fingerprint"] = "changed"
    path.write_text(json.dumps(data))
    assert service.load(project.project_id) is None


def test_boot_observation_rejects_another_device_or_pack(tmp_path):
    store, project, registry = _fixture(tmp_path)
    service = BootObservationService(store, registry)
    service.observe(project.project_id, _device())

    with pytest.raises(ProjectError, match="another device"):
        service.observe(
            project.project_id,
            _device(serial="OTHER"),
            datetime.now(UTC) + timedelta(seconds=70),
        )
    wrong = replace(_device(), model="different")
    with pytest.raises(ProjectError, match="does not match"):
        service.observe(project.project_id, wrong)
