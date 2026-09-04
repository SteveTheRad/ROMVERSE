from __future__ import annotations

import hashlib
import json
import os
import zipfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

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
from romverse.rom.boot_observation import (
    BootFailureKind,
    BootObservationService,
    BootObservationStatus,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.ui.rom_studio import RomStudio


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


def _redigest(data: dict[str, object]) -> dict[str, object]:
    payload = dict(data)
    payload.pop("format", None)
    payload.pop("receipt_digest", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    data["receipt_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    return data


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
    assert stable.failure_kind is BootFailureKind.NONE
    assert not stable.knowledge_queries
    assert not service.needs_knowledge_lookup(stable)
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
    assert rebooted.failure_kind is BootFailureKind.REBOOT_LOOP
    assert "boot loop" in rebooted.knowledge_queries[0]
    assert "BUILD" in " ".join(rebooted.knowledge_queries)
    assert service.needs_knowledge_lookup(rebooted)
    failure = service.knowledge_failure(rebooted)
    assert failure is not None
    assert failure.phase == "boot"
    assert "boot.incomplete" in failure.finding_ids
    assert "boot.reboot_loop" in failure.finding_ids
    assert failure.operation == "read-only boot observation"
    assert failure.verified_inputs == (
        f"pack:{rebooted.pack_id}",
        f"source:{rebooted.source_original_sha256}",
    )
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


def test_boot_observation_classifies_timeout_probe_failure_and_non_android_mode(tmp_path):
    store, project, registry = _fixture(tmp_path)
    service = BootObservationService(store, registry)
    started = datetime(2026, 8, 29, tzinfo=UTC)

    timeout = service.observe(
        project.project_id,
        _device(boot_completed=False, uptime_seconds=1_201),
        started,
    )
    assert timeout.failure_kind is BootFailureKind.BOOT_TIMEOUT
    assert service.needs_knowledge_lookup(timeout)

    path = store.projects_root / project.project_id / service.NAME
    path.unlink()
    incomplete = service.observe(
        project.project_id,
        _device(boot_completed=None, uptime_seconds=None, errors=("getprop timed out",)),
        started,
    )
    assert incomplete.failure_kind is BootFailureKind.PROBE_INCOMPLETE
    assert "probe" in " ".join(incomplete.knowledge_queries).casefold()

    path.unlink()
    fastboot = service.observe(
        project.project_id,
        _device(state=DeviceState.FASTBOOT, boot_completed=None),
        started,
    )
    assert fastboot.failure_kind is BootFailureKind.DEVICE_MODE
    assert "fastboot" in fastboot.knowledge_queries[0]


def test_boot_observation_store_is_strict_bounded_and_rejects_links(tmp_path):
    store, project, registry = _fixture(tmp_path)
    service = BootObservationService(store, registry)
    receipt = service.observe(project.project_id, _device())
    path = store.projects_root / project.project_id / service.NAME
    original = path.read_bytes()

    data = json.loads(original)
    data["samples"][0]["uptime_seconds"] = True
    path.write_text(json.dumps(_redigest(data)), encoding="utf-8")
    assert service.load(project.project_id) is None

    path.write_bytes(original)
    data = json.loads(original)
    data["execution_authority"] = "flash"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert service.load(project.project_id) is None

    outside = tmp_path / "outside.romverse"
    outside.write_bytes(original)
    path.unlink()
    path.symlink_to(outside)
    assert service.load(project.project_id) is None

    path.unlink()
    path.write_bytes(b"{" + b" " * service.MAX_BYTES + b"}")
    assert service.load(project.project_id) is None
    assert receipt.schema_version == service.SCHEMA_VERSION


def test_schema_one_boot_observation_migrates_in_memory_with_lookup_terms(tmp_path):
    store, project, registry = _fixture(tmp_path)
    service = BootObservationService(store, registry)
    started = datetime(2026, 8, 29, tzinfo=UTC)
    service.observe(project.project_id, _device(uptime_seconds=1_000), started)
    receipt = service.observe(
        project.project_id,
        _device(uptime_seconds=10),
        started + timedelta(seconds=70),
    )
    path = store.projects_root / project.project_id / service.NAME
    legacy = json.loads(path.read_text(encoding="utf-8"))
    legacy["schema_version"] = 1
    legacy.pop("failure_kind")
    legacy.pop("knowledge_queries")
    path.write_text(json.dumps(_redigest(legacy)), encoding="utf-8")

    migrated = service.load(project.project_id)

    assert migrated is not None
    assert migrated.schema_version == 2
    assert migrated.failure_kind is BootFailureKind.REBOOT_LOOP
    assert migrated.knowledge_queries == receipt.knowledge_queries


def test_rom_studio_automatically_ranks_offline_archive_for_boot_attention(tmp_path):
    QApplication.instance() or QApplication([])
    store, project, registry = _fixture(tmp_path)
    service = BootObservationService(store, registry)
    started = datetime(2026, 8, 29, tzinfo=UTC)
    service.observe(project.project_id, _device(uptime_seconds=1_000), started)
    receipt = service.observe(
        project.project_id,
        _device(uptime_seconds=10),
        started + timedelta(seconds=70),
    )
    studio = RomStudio(store, registry)
    reports = []
    studio.offline_knowledge_updated.connect(reports.append)

    report = studio.scan_boot_observation_knowledge(receipt)

    assert report is not None
    assert report.trigger == "boot-failure"
    assert report.execution_authority == "none"
    assert report.matches
    assert "boot.incomplete" in report.matches[0].matched_evidence[0]
    assert reports == [report]
    assert (store.workspace / "knowledge" / "archive.romverse").is_file()
    studio.close()
