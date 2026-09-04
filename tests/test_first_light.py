from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from romverse.device.intelligence import (
    DeviceIntelligenceHistoryStore,
    DeviceOperationEvent,
)
from romverse.device.models import AndroidDevice, DeviceState, StorageInfo
from romverse.rom.boot_observation import (
    BootFailureKind,
    BootObservationReceipt,
    BootObservationStatus,
    BootSample,
)
from romverse.rom.boot_observation import (
    _digest as _boot_digest,
)
from romverse.rom.first_light import (
    FirstLightEvidenceKind,
    FirstLightOverall,
    FirstLightService,
    FirstLightStatus,
)
from romverse.rom.first_light import (
    _digest as _first_light_digest,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


def _fixture(tmp_path):
    workspace = tmp_path / "workspace"
    store = RomProjectStore(workspace)
    source = tmp_path / "firmware.zip"
    source.write_bytes(b"exact firmware")
    project = store.create("First Light", "test.first-light")
    project = store.import_original(project.project_id, source)
    assert project.original is not None
    pack = SimpleNamespace(
        pack_id="test.first-light",
        build_contract=SimpleNamespace(
            contract_id="contract",
            source=SimpleNamespace(
                archive_sha256=project.original.sha256,
                build_id="TARGET.2",
            ),
        ),
    )
    registry = SimpleNamespace(
        packs=(pack,),
        resolve=lambda _device: SimpleNamespace(pack=pack),
    )
    device = AndroidDevice(
        "serial-private",
        DeviceState.DEVICE,
        transport="usb",
        manufacturer="Example",
        model="Phone",
        product="first",
        codename="first",
        android_version="16",
        build_id="TARGET.2",
        build_fingerprint="example/first/first:16/TARGET.2:user/release-keys",
        security_patch="2026-09-01",
        storage=StorageInfo(128_000, 64_000, 64_000, 50),
        slot_suffix="_a",
        verified_boot="orange",
        ab_update=True,
        virtual_ab=True,
        dynamic_partitions=True,
    )
    privacy = FirstLightService(store, registry).privacy
    now = datetime.now(UTC)
    sample_values = {
        "device_pseudonym": privacy.pseudonym(device.serial),
        "state": DeviceState.DEVICE.value,
        "boot_completed": True,
        "slot_suffix": "_a",
        "build_id": device.build_id,
        "build_fingerprint": device.build_fingerprint,
        "battery_percent": 80,
        "probe_errors": (),
    }
    samples = (
        BootSample(
            observed_at=(now - timedelta(minutes=6)).isoformat(),
            uptime_seconds=600,
            **sample_values,
        ),
        BootSample(
            observed_at=now.isoformat(),
            uptime_seconds=960,
            **sample_values,
        ),
    )
    boot_payload = {
        "schema_version": 3,
        "project_id": project.project_id,
        "pack_id": pack.pack_id,
        "contract_id": pack.build_contract.contract_id,
        "source_original_sha256": project.original.sha256,
        "samples": samples,
        "status": BootObservationStatus.STABLE,
        "stable": True,
        "reboot_detected": False,
        "flash_linked": True,
        "guardian_execution_receipt_digest": "a" * 64,
        "verified_first_boot": True,
        "diagnosis": (
            "Android remained boot-complete on the same build and slot across the stability window"
        ),
        "phone_changed": False,
        "failure_kind": BootFailureKind.NONE,
        "knowledge_queries": (),
    }
    boot_digest_payload = {**boot_payload, "samples": [asdict(item) for item in samples]}
    boot = BootObservationReceipt(
        **boot_payload,
        receipt_digest=_boot_digest(boot_digest_payload),
    )
    return FirstLightService(store, registry), project.project_id, device, boot


def test_first_light_starts_only_from_verified_boot_and_keeps_unknowns_untested(
    tmp_path,
):
    service, project_id, device, boot = _fixture(tmp_path)

    report = service.start(project_id, device, boot)
    subsystems = {item.subsystem_id: item for item in report.subsystems}

    assert report.overall is FirstLightOverall.INCOMPLETE
    assert not report.public_release_ready
    assert subsystems["first_boot"].status is FirstLightStatus.WORKING
    assert subsystems["build_identity"].status is FirstLightStatus.WORKING
    assert subsystems["partition_state"].status is FirstLightStatus.WORKING
    assert subsystems["usb"].status is FirstLightStatus.WORKING
    assert subsystems["wifi"].status is FirstLightStatus.UNTESTED
    automated = (
        subsystems["first_boot"],
        subsystems["build_identity"],
        subsystems["partition_state"],
        subsystems["usb"],
    )
    assert all(item.evidence_kind is FirstLightEvidenceKind.AUTOMATED for item in automated)
    assert not report.phone_changed
    assert service.load(project_id) == report


def test_first_light_requires_every_subsystem_before_public_release(tmp_path):
    service, project_id, device, boot = _fixture(tmp_path)
    report = service.start(project_id, device, boot)

    for subsystem in report.subsystems:
        if subsystem.subsystem_id in service.AUTOMATED_IDS:
            continue
        report = service.record_observation(
            report,
            subsystem.subsystem_id,
            FirstLightStatus.WORKING,
            FirstLightEvidenceKind.USER,
            f"Tester completed the {subsystem.label} check successfully.",
        )

    assert report.overall is FirstLightOverall.VERIFIED
    assert report.public_release_ready
    assert not report.knowledge_queries


def test_first_light_compares_the_verified_pre_flash_passport(tmp_path):
    service, project_id, device, boot = _fixture(tmp_path)
    history = DeviceIntelligenceHistoryStore(service.store.workspace)
    baseline = history.record_scan(
        replace(
            device,
            android_version="15",
            build_id="BASE.1",
            rom_display="BASE.1",
            slot_suffix="_b",
            security_patch="2026-08-01",
        ),
        observed_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    event_payload = {
        "schema_version": 1,
        "event_id": "1" * 24,
        "occurred_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
        "device_key": history.privacy.pseudonym(device.serial),
        "event_type": "flash",
        "outcome": "verified",
        "title": "Verified Guardian flash",
        "detail": "All governed partition operations passed.",
        "project_id": project_id,
        "pack_id": boot.pack_id,
        "evidence_digest": boot.guardian_execution_receipt_digest,
    }
    history._save_operations(
        (DeviceOperationEvent(**event_payload, record_digest=history._digest(event_payload)),)
    )

    report = service.start(project_id, device, boot)
    changes = {item.field_id: item for item in report.baseline_changes}

    assert report.baseline_scan_id == baseline.scan_id
    assert changes["android"].before == "15"
    assert changes["android"].after == "16"
    assert changes["firmware"].before == "BASE.1"
    assert changes["firmware"].after == "TARGET.2"
    assert changes["slot"].before == "b"
    assert changes["slot"].after == "a"
    assert changes["slot_scheme"].state == "unchanged"


def test_first_light_failure_routes_a_specific_offline_knowledge_query(tmp_path):
    service, project_id, device, boot = _fixture(tmp_path)
    report = service.start(project_id, device, boot)

    report = service.record_observation(
        report,
        "android_auto",
        FirstLightStatus.FAILED,
        FirstLightEvidenceKind.USER,
        "Projection did not appear on a known-working vehicle after USB permission approval.",
        "Cable and vehicle were validated with the stock build.",
    )

    assert report.overall is FirstLightOverall.FAILED
    assert not report.public_release_ready
    assert report.knowledge_queries == (
        "Android Android Auto vehicle projection failed after ROM flash",
    )
    failure = service.knowledge_failure(report)
    assert failure is not None
    assert failure.phase == "first-light"
    assert failure.finding_ids == ("first-light.android_auto",)
    assert failure.verified_inputs[-1] == f"boot:{report.boot_observation_digest}"


def test_first_light_rejects_identity_mismatch_and_manual_automated_claim(tmp_path):
    service, project_id, device, boot = _fixture(tmp_path)

    with pytest.raises(ProjectError, match="exact successful Guardian"):
        service.start(
            project_id,
            AndroidDevice("other-device", DeviceState.DEVICE, build_id="TARGET.2"),
            boot,
        )
    report = service.start(project_id, device, boot)
    with pytest.raises(ProjectError, match="automated read-only"):
        service.record_observation(
            report,
            "first_boot",
            FirstLightStatus.WORKING,
            FirstLightEvidenceKind.USER,
            "Manual claim",
        )


def test_first_light_detects_redigested_tampering_and_exports_exact_report(tmp_path):
    service, project_id, device, boot = _fixture(tmp_path)
    report = service.start(project_id, device, boot)
    path = service.store.projects_root / project_id / service.NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["subsystems"][0]["status"] = "failed"
    unsigned = {key: value for key, value in payload.items() if key != "format"}
    unsigned.pop("report_digest")
    payload["report_digest"] = _first_light_digest(unsigned)
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert service.load(project_id) is None

    path.write_text(
        json.dumps({"format": service.FORMAT, **asdict(report)}),
        encoding="utf-8",
    )
    export_root = tmp_path / "exports"
    export_root.mkdir()
    exported = service.export_report(report, export_root)
    exported_payload = json.loads(exported.read_text(encoding="utf-8"))
    assert exported_payload["report_digest"] == report.report_digest
    assert "serial-private" not in exported.read_text(encoding="utf-8")
    with pytest.raises(ProjectError, match="already exists"):
        service.export_report(report, exported)
