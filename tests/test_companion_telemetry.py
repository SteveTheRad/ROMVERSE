from dataclasses import asdict
from datetime import UTC, datetime

import pytest

from romverse.companion.raw_terminal import RawTerminalFeed
from romverse.companion.telemetry import (
    ActivityEvent,
    CompanionTelemetry,
    DeviceDnaCapabilityTelemetry,
    LiveConsoleTelemetryEvent,
    RawTerminalTelemetryRecord,
    RemoteCompanionSnapshot,
)


def test_telemetry_round_trips_known_read_only_fields() -> None:
    snapshot = CompanionTelemetry(
        captured_at=datetime.now(UTC).isoformat(),
        battery_percent=78,
        storage_used_bytes=20,
        storage_total_bytes=100,
        activity=(ActivityEvent("Scan complete", "Read-only health scan"),),
    )
    restored = CompanionTelemetry.from_mapping(snapshot.to_mapping() | {"shell": "blocked"})
    assert restored == snapshot


def test_telemetry_rejects_unsafe_ranges() -> None:
    with pytest.raises(ValueError, match="battery_percent"):
        CompanionTelemetry(battery_percent=101)
    with pytest.raises(ValueError, match="storage used"):
        CompanionTelemetry(storage_used_bytes=11, storage_total_bytes=10)


def test_telemetry_defaults_to_guardian_active() -> None:
    snapshot = CompanionTelemetry.from_mapping({})
    assert snapshot.guardian_active is True


def test_telemetry_round_trips_bounded_ascension_status() -> None:
    snapshot = CompanionTelemetry(
        ascension_state="review_ready",
        ascension_project="My ROM",
        ascension_method="magisk",
        ascension_target_partition="init_boot",
        ascension_blocker_count=0,
        ascension_stage_number=9,
        ascension_stage_title="Ready for final Guardian review",
        ascension_next_action="Review the exact manifest on Desktop.",
        ascension_why="The exact phone and rollback route must match.",
        ascension_romverse_action="ROMVERSE compiled a tamper-evident review.",
        ascension_manager_state="verified",
        ascension_manager_repository="topjohnwu/Magisk",
        ascension_manager_tag="v30.7",
        ascension_manager_asset="Magisk-v30.7.apk",
        ascension_manager_sha256_ref="e0d32d2123532860",
    )

    restored = CompanionTelemetry.from_mapping(snapshot.to_mapping())

    assert restored.ascension_state == "review_ready"
    assert restored.ascension_project == "My ROM"
    assert restored.ascension_method == "magisk"
    assert restored.ascension_target_partition == "init_boot"
    assert restored.ascension_blocker_count == 0
    assert restored.ascension_stage_number == 9
    assert restored.ascension_stage_title == "Ready for final Guardian review"
    assert restored.ascension_next_action == "Review the exact manifest on Desktop."
    assert "rollback" in restored.ascension_why
    assert "tamper-evident" in restored.ascension_romverse_action
    assert restored.ascension_manager_state == "verified"
    assert restored.ascension_manager_repository == "topjohnwu/Magisk"
    assert restored.ascension_manager_tag == "v30.7"
    assert restored.ascension_manager_asset == "Magisk-v30.7.apk"
    assert restored.ascension_manager_sha256_ref == "e0d32d2123532860"
    assert restored.ascension_phone_changed is False
    assert restored.ascension_execution_authority == "none"


def test_telemetry_round_trips_genuine_live_console_and_nexus_status() -> None:
    event = LiveConsoleTelemetryEvent(
        event_id="a" * 32,
        updated_at=datetime.now(UTC).isoformat(),
        source="ROMVERSE Nexus",
        stage="pathfinder-route",
        title="Nexus Plan updated",
        summary="Pathfinder created a source-bound route.",
        explanation="Device DNA and Compatibility Matrix evidence were used.",
        next_action="Resolve research requirements before Guardian review.",
        state="attention",
        progress_percent=100,
        confidence="unconfirmed",
        guardian_protected=True,
    )
    snapshot = CompanionTelemetry(
        live_console_events=(event,),
        nexus_status="needs-evidence",
        nexus_objective="flash-device",
        nexus_current_stage="Research",
        nexus_research_count=3,
        guardian_review_state="blocked",
    )

    restored = CompanionTelemetry.from_mapping(snapshot.to_mapping())

    assert restored == snapshot
    assert restored.live_console_events[0].title == "Nexus Plan updated"
    assert restored.live_console_execution_authority == "none"
    assert restored.raw_terminal_included is False


def test_live_console_telemetry_rejects_execution_or_invented_raw_terminal() -> None:
    with pytest.raises(ValueError, match="execution authority"):
        CompanionTelemetry(live_console_execution_authority="flash")
    with pytest.raises(ValueError, match="Raw terminal"):
        CompanionTelemetry(schema_version=5, raw_terminal_included=True)
    with pytest.raises(ValueError, match="Guardian-protected"):
        LiveConsoleTelemetryEvent(
            event_id="b" * 32,
            updated_at=datetime.now(UTC).isoformat(),
            source="Unknown",
            stage="fake",
            title="Fake event",
            summary="This event has no Guardian provenance.",
            explanation="It must be rejected.",
            next_action="Reject it.",
            state="succeeded",
            progress_percent=100,
            confidence="verified",
            guardian_protected=False,
        )


def test_link_v6_round_trips_bounded_privacy_filtered_raw_terminal() -> None:
    source = RawTerminalFeed().publish(
        "verified-boot-state",
        "$ adb -s <private-device> shell getprop ro.boot.verifiedbootstate\ngreen\nExit code: 0",
    )
    assert source is not None
    record = RawTerminalTelemetryRecord(**asdict(source))
    snapshot = CompanionTelemetry(
        raw_terminal_included=True,
        raw_terminal_integrity="verified-local-feed",
        raw_terminal_records=(record,),
    )

    restored = CompanionTelemetry.from_mapping(snapshot.to_mapping())

    assert restored == snapshot
    assert restored.schema_version == 6
    assert restored.raw_terminal_records[0].probe_id == "verified-boot-state"
    assert restored.live_console_execution_authority == "none"


def test_link_v6_rejects_unapproved_or_unmarked_raw_terminal() -> None:
    with pytest.raises(ValueError, match="inclusion marker"):
        CompanionTelemetry(raw_terminal_included=True)
    with pytest.raises(ValueError, match="not Link-approved"):
        RawTerminalTelemetryRecord(
            record_id="e" * 32,
            captured_at=datetime.now(UTC).isoformat(),
            probe_id="adb-devices",
            title="ADB devices",
            lines=("private serial",),
            success=True,
            record_digest="f" * 64,
        )
    source = RawTerminalFeed().publish("device-model", "Model\nExit code: 0")
    assert source is not None
    with pytest.raises(ValueError, match="does not match"):
        RawTerminalTelemetryRecord(**(asdict(source) | {"title": "Tampered title"}))


def test_link_v6_round_trips_bounded_device_dna_capability_map() -> None:
    capability = DeviceDnaCapabilityTelemetry(
        "source_adapter",
        "Automatic source adapter",
        "SUPPORTED",
        "Payload Atlas selected from bounded Android structure evidence.",
    )
    snapshot = CompanionTelemetry(
        device_dna_state="ready",
        device_dna_project="My ROM",
        device_dna_profile_ref="a" * 16,
        device_dna_warning_count=0,
        device_dna_capabilities=(capability,),
    )

    restored = CompanionTelemetry.from_mapping(snapshot.to_mapping())

    assert restored == snapshot
    assert restored.device_dna_capabilities[0].state == "SUPPORTED"
    assert restored.device_dna_execution_authority == "none"
    assert restored.device_dna_bootloader_relock == "never"


def test_link_v6_device_dna_rejects_authority_relock_or_invented_profile() -> None:
    with pytest.raises(ValueError, match="execution authority"):
        CompanionTelemetry(device_dna_execution_authority="flash")
    with pytest.raises(ValueError, match="relocking"):
        CompanionTelemetry(device_dna_bootloader_relock="allowed")
    with pytest.raises(ValueError, match="Unavailable Device DNA"):
        CompanionTelemetry(device_dna_project="Invented")


def test_telemetry_accepts_explicit_unrooted_ascension_skip() -> None:
    restored = CompanionTelemetry.from_mapping(
        CompanionTelemetry(
            ascension_state="skipped",
            ascension_project="Clean ROM",
            ascension_stage_title="Unrooted ROM selected",
        ).to_mapping()
    )

    assert restored.ascension_state == "skipped"
    assert restored.ascension_method == "none"


def test_telemetry_rejects_ascension_write_authority_or_phone_change() -> None:
    with pytest.raises(ValueError, match="phone change"):
        CompanionTelemetry(ascension_phone_changed=True)
    with pytest.raises(ValueError, match="execution authority"):
        CompanionTelemetry(ascension_execution_authority="flash")
    with pytest.raises(ValueError, match="stage"):
        CompanionTelemetry(ascension_stage_number=10)
    with pytest.raises(ValueError, match="romverse_action"):
        CompanionTelemetry(ascension_romverse_action="hidden\ncommand")


def test_link_v6_rejects_unverified_or_mismatched_ascension_manager_provenance() -> None:
    verified = {
        "ascension_method": "magisk",
        "ascension_manager_state": "verified",
        "ascension_manager_repository": "topjohnwu/Magisk",
        "ascension_manager_tag": "v30.7",
        "ascension_manager_asset": "Magisk-v30.7.apk",
        "ascension_manager_sha256_ref": "e0d32d2123532860",
    }
    assert CompanionTelemetry(**verified).ascension_manager_state == "verified"
    with pytest.raises(ValueError, match="Unavailable"):
        CompanionTelemetry(ascension_manager_repository="topjohnwu/Magisk")
    with pytest.raises(ValueError, match="repository"):
        CompanionTelemetry(**(verified | {"ascension_manager_repository": "example/Magisk"}))
    with pytest.raises(ValueError, match="asset"):
        CompanionTelemetry(**(verified | {"ascension_manager_asset": "Magisk-debug.apk"}))
    with pytest.raises(ValueError, match="fingerprint"):
        CompanionTelemetry(**(verified | {"ascension_manager_sha256_ref": "a" * 64}))
    with pytest.raises(ValueError, match="schema 6"):
        CompanionTelemetry(schema_version=5, **verified)


def test_schema_three_keeps_original_seven_stage_boundary() -> None:
    with pytest.raises(ValueError, match="stage"):
        CompanionTelemetry(schema_version=3, ascension_stage_number=8)


def test_schema_one_telemetry_ignores_future_ascension_fields() -> None:
    restored = CompanionTelemetry.from_mapping(
        {
            "schema_version": 1,
            "ascension_state": "review_ready",
            "ascension_phone_changed": True,
            "ascension_execution_authority": "flash",
            "ascension_romverse_action": "Run a hidden operation.",
        }
    )

    assert restored.schema_version == 1
    assert restored.ascension_state == "no_project"
    assert restored.ascension_phone_changed is False
    assert restored.ascension_execution_authority == "none"
    assert restored.ascension_romverse_action == ""


def remote_payload() -> dict[str, object]:
    return {
        "schema_version": 3,
        "captured_at_epoch_ms": 1_788_000_000_000,
        "manufacturer": "Xiaomi",
        "model": "2509FPN0BC",
        "device_codename": "popsicle",
        "android_version": "17",
        "sdk_int": 36,
        "companion_version": "0.1.0",
        "battery_percent": 82,
        "storage_used_bytes": 100,
        "storage_total_bytes": 200,
        "memory_available_bytes": 80,
        "memory_total_bytes": 160,
        "health_score": 94,
        "kernel_release": "6.12.23-popsicle",
        "root_signal": "not_observed",
        "root_manager_candidate": "magisk",
        "bootloader_state": "unknown",
        "kernelsu_support": "unknown",
        "guardian_active": True,
        "privacy_scope": "health_and_device_safety",
    }


def vitalis_payload() -> dict[str, object]:
    return remote_payload() | {
        "schema_version": 4,
        "battery_temperature_celsius": 31.5,
        "network_validated": True,
        "usb_connected": True,
        "health_score": 100,
        "vitalis_state": "OPTIMAL",
        "vitalis_evidence_percent": 100,
    }


def test_remote_companion_snapshot_round_trips_device_safety_contract() -> None:
    snapshot = RemoteCompanionSnapshot.from_mapping(remote_payload() | {"future_metric": 3})

    assert snapshot.model == "2509FPN0BC"
    assert snapshot.health_score == 94
    assert snapshot.kernel_release == "6.12.23-popsicle"
    assert snapshot.root_signal == "not_observed"
    assert snapshot.root_manager_candidate == "magisk"
    assert RemoteCompanionSnapshot.from_mapping(snapshot.to_mapping()) == snapshot


def test_schema_four_rederives_vitalis_score_state_and_coverage() -> None:
    snapshot = RemoteCompanionSnapshot.from_mapping(vitalis_payload())

    assert snapshot.health_score == 100
    assert snapshot.vitalis_state == "OPTIMAL"
    assert snapshot.vitalis_evidence_percent == 100
    assert RemoteCompanionSnapshot.from_mapping(snapshot.to_mapping()) == snapshot


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"health_score": 99}, "health_score"),
        ({"vitalis_state": "ATTENTION"}, "vitalis_state"),
        ({"vitalis_evidence_percent": 83}, "vitalis_evidence_percent"),
        ({"network_validated": "yes"}, "network_validated"),
        ({"storage_total_bytes": None}, "storage evidence"),
    ],
)
def test_schema_four_rejects_contradictory_vitalis_claims(
    change: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        RemoteCompanionSnapshot.from_mapping(vitalis_payload() | change)


def test_schema_four_missing_temperature_remains_unconfirmed() -> None:
    snapshot = RemoteCompanionSnapshot.from_mapping(
        vitalis_payload()
        | {
            "battery_temperature_celsius": None,
            "health_score": None,
            "vitalis_state": "UNCONFIRMED",
            "vitalis_evidence_percent": 83,
        }
    )

    assert snapshot.health_score is None
    assert snapshot.vitalis_state == "UNCONFIRMED"


def test_remote_health_freshness_rejects_replay_and_far_future_evidence() -> None:
    snapshot = RemoteCompanionSnapshot.from_mapping(vitalis_payload())
    captured = snapshot.captured_at_epoch_ms

    snapshot.verify_freshness(captured + 120_000)
    snapshot.verify_freshness(captured - 300_000)
    with pytest.raises(ValueError, match="stale"):
        snapshot.verify_freshness(captured + 120_001)
    with pytest.raises(ValueError, match="future"):
        snapshot.verify_freshness(captured - 300_001)


def test_remote_companion_snapshot_keeps_schema_one_compatibility() -> None:
    payload = remote_payload()
    for key in (
        "kernel_release",
        "root_signal",
        "root_manager_candidate",
        "bootloader_state",
        "kernelsu_support",
    ):
        payload.pop(key)
    payload.update(schema_version=1, privacy_scope="health_only")
    snapshot = RemoteCompanionSnapshot.from_mapping(payload)
    assert snapshot.schema_version == 1
    assert snapshot.kernel_release == ""


def test_remote_companion_snapshot_keeps_schema_two_root_manager_compatibility() -> None:
    payload = remote_payload()
    payload.pop("root_manager_candidate")
    payload["schema_version"] = 2

    snapshot = RemoteCompanionSnapshot.from_mapping(payload)

    assert snapshot.root_manager_candidate == "unknown"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"battery_percent": 101}, "battery_percent"),
        ({"memory_available_bytes": 161}, "available memory"),
        ({"guardian_active": False}, "Guardian"),
        ({"privacy_scope": "commands"}, "privacy scope"),
        ({"root_manager_candidate": "superuser"}, "root_manager_candidate"),
        ({"shell": "id"}, "forbidden"),
        ({"serial": "private"}, "forbidden"),
        ({"sdk_int": True}, "integer"),
    ],
)
def test_remote_companion_snapshot_rejects_unsafe_or_invalid_fields(
    change: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        RemoteCompanionSnapshot.from_mapping(remote_payload() | change)
