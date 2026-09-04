from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from romverse.device.intelligence import (
    DeviceIntelligenceError,
    DeviceIntelligenceHistoryStore,
)
from romverse.device.models import AndroidDevice, DeviceState, StorageInfo
from tests.test_boot_observation import (
    _device as _guardian_device,
)
from tests.test_boot_observation import (
    _fixture as _guardian_fixture,
)
from tests.test_boot_observation import (
    _verified_flash,
)


def _xiaomi(serial: str = "raw-private-serial") -> AndroidDevice:
    return AndroidDevice(
        serial,
        DeviceState.DEVICE,
        transport="usb",
        manufacturer="Xiaomi",
        brand="Xiaomi",
        marketing_name="Xiaomi 17 Pro Max",
        model="2509FPN0BC",
        product="popsicle",
        codename="popsicle",
        android_version="17",
        build_id="OS4.0.0.25.XPBCNXM",
        build_fingerprint="xiaomi/popsicle/popsicle:17/private/full/fingerprint",
        security_patch="2026-08-01",
        battery_percent=76,
        battery_temperature_c=31.5,
        storage=StorageInfo(
            total_bytes=512_000_000_000,
            available_bytes=208_000_000_000,
            percent_used=59,
        ),
        bootloader_locked=False,
        verified_boot="orange",
        slot_suffix="_a",
        soc_platform="sm8850",
        ab_update=True,
        virtual_ab=True,
        dynamic_partitions=True,
    )


def test_passport_history_records_useful_facts_without_private_identity(tmp_path) -> None:
    store = DeviceIntelligenceHistoryStore(tmp_path)

    snapshot = store.record_scan(
        _xiaomi(),
        match_reason="Manufacturer matched Xiaomi knowledge",
        observed_at=datetime(2026, 9, 5, 8, 30, tzinfo=UTC),
    )

    assert snapshot.display_name == "Xiaomi 17 Pro Max"
    assert snapshot.region == "China"
    assert snapshot.chipset == "sm8850"
    assert snapshot.firmware_version == "OS4.0.0.25.XPBCNXM"
    assert snapshot.bootloader_state == "unlocked"
    assert snapshot.active_slot == "a"
    assert snapshot.slot_scheme == "Virtual A/B"
    assert "Dynamic partitions reported" in snapshot.partition_summary
    assert snapshot.health_summary == "No warning found in the current bounded live telemetry"
    encoded = store.path.read_text(encoding="utf-8")
    assert "raw-private-serial" not in encoded
    assert "xiaomi/popsicle/popsicle:17/private/full/fingerprint" not in encoded
    assert len(snapshot.device_key) == 20
    assert store.load(device_serial="raw-private-serial") == (snapshot,)


def test_passport_history_deduplicates_each_device_without_cross_device_loss(tmp_path) -> None:
    store = DeviceIntelligenceHistoryStore(tmp_path)
    first_time = datetime(2026, 9, 5, 8, 30, tzinfo=UTC)
    first = store.record_scan(_xiaomi("phone-a"), observed_at=first_time)
    second = store.record_scan(
        replace(_xiaomi("phone-b"), model="SM-S928B", codename="e3q"),
        observed_at=first_time + timedelta(minutes=1),
    )

    duplicate = store.record_scan(
        _xiaomi("phone-a"),
        observed_at=first_time + timedelta(minutes=2),
    )
    refreshed = store.record_scan(
        _xiaomi("phone-a"),
        observed_at=first_time + timedelta(minutes=16),
    )

    assert duplicate.scan_id == first.scan_id
    assert refreshed.scan_id != first.scan_id
    assert tuple(item.scan_id for item in store.load()) == (
        refreshed.scan_id,
        second.scan_id,
        first.scan_id,
    )
    assert tuple(item.scan_id for item in store.load(device_serial="phone-a")) == (
        refreshed.scan_id,
        first.scan_id,
    )


def test_passport_history_rejects_changed_or_unbounded_local_evidence(tmp_path) -> None:
    store = DeviceIntelligenceHistoryStore(tmp_path)
    store.record_scan(_xiaomi())
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    payload["snapshots"][0]["firmware_version"] = "substituted"
    store.path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DeviceIntelligenceError, match="digest does not match"):
        store.load()

    store.path.write_bytes(b"{" + b"x" * store.MAX_BYTES)
    with pytest.raises(DeviceIntelligenceError, match="size boundary"):
        store.load()


def test_device_timeline_records_only_exact_verified_guardian_flash_results(tmp_path) -> None:
    project_store, project, _registry = _guardian_fixture(tmp_path)
    store = DeviceIntelligenceHistoryStore(project_store.workspace)
    device = _guardian_device()
    verified = _verified_flash(
        project_store,
        project,
        device,
        datetime(2026, 9, 5, 9, 0, tzinfo=UTC),
    )

    event = store.record_verified_flash(device.serial, project.name, verified)
    duplicate = store.record_verified_flash(device.serial, project.name, verified)

    assert duplicate == event
    assert event.event_type == "flash"
    assert event.outcome == "verified"
    assert event.evidence_digest == verified.signed_receipt_sha256
    assert event.project_id == project.project_id
    assert "1 partition operation(s) passed" in event.detail
    assert store.load_operations(device_serial=device.serial) == (event,)
    encoded = store.operation_path.read_text(encoding="utf-8")
    assert device.serial not in encoded

    with pytest.raises(DeviceIntelligenceError, match="successful Guardian flash"):
        store.record_verified_flash(
            device.serial,
            project.name,
            replace(verified, signer_key_id="substituted"),
        )
