from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from romverse.ascension.companion import AscensionCompanionStatus
from romverse.companion.raw_terminal import RawTerminalFeed
from romverse.companion.telemetry import RemoteCompanionSnapshot
from romverse.device.dna import CapabilityMapEntry, CapabilityState, DeviceDnaProfile
from romverse.nexus.events import LiveConsoleEventStore, MissionState
from romverse.ui.companion_center import CompanionCenter


def test_companion_center_renders_authenticated_remote_health_snapshot() -> None:
    app = QApplication.instance() or QApplication([])
    center = CompanionCenter()
    snapshot = RemoteCompanionSnapshot(
        captured_at_epoch_ms=1_788_000_000_000,
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        device_codename="popsicle",
        android_version="17",
        sdk_int=37,
        companion_version="0.1.0",
        battery_percent=82,
        storage_used_bytes=100 * 1024**3,
        storage_total_bytes=200 * 1024**3,
        memory_available_bytes=8 * 1024**3,
        memory_total_bytes=16 * 1024**3,
        health_score=100,
        battery_temperature_celsius=31.5,
        network_validated=True,
        usb_connected=True,
        vitalis_state="OPTIMAL",
        vitalis_evidence_percent=100,
        schema_version=4,
        root_manager_candidate="magisk",
    )
    center.transport._record_remote_snapshot(snapshot)

    center._update_remote_snapshot()
    app.processEvents()

    rendered = center.remote_summary.text()
    assert "AUTHENTICATED" in rendered
    assert "Xiaomi 2509FPN0BC (popsicle)" in rendered
    assert "Battery 82%" in rendered
    assert "Storage 100.0 GB / 200.0 GB" in rendered
    assert "RAM 8.0 GB / 16.0 GB" in rendered
    assert "Guardian health 100/100" in rendered
    assert "Vitalis OPTIMAL • 100% evidence" in rendered
    assert "health and device safety privacy scope" in rendered
    assert "Kernel unknown" in rendered
    assert "Manager candidate magisk" in rendered
    center.shutdown()


def test_companion_center_publishes_read_only_ascension_status() -> None:
    QApplication.instance() or QApplication([])
    center = CompanionCenter()

    center.set_ascension_status(
        AscensionCompanionStatus(
            state="blocked",
            project_name="My ROM",
            method="magisk",
            target_partition="init_boot",
            blocker_count=2,
            romverse_action="ROMVERSE is resolving safe local evidence gates.",
            manager_state="verified",
            manager_repository="topjohnwu/Magisk",
            manager_tag="v30.7",
            manager_asset="Magisk-v30.7.apk",
            manager_sha256_ref="e0d32d2123532860",
        )
    )

    telemetry = center._telemetry
    assert telemetry.schema_version == 6
    assert telemetry.ascension_state == "blocked"
    assert telemetry.ascension_project == "My ROM"
    assert telemetry.ascension_method == "magisk"
    assert telemetry.ascension_target_partition == "init_boot"
    assert telemetry.ascension_blocker_count == 2
    assert telemetry.ascension_phone_changed is False
    assert telemetry.ascension_execution_authority == "none"
    assert telemetry.ascension_stage_number == 0
    assert telemetry.ascension_romverse_action == "ROMVERSE is resolving safe local evidence gates."
    assert telemetry.ascension_manager_state == "verified"
    assert telemetry.ascension_manager_repository == "topjohnwu/Magisk"
    assert telemetry.ascension_manager_asset == "Magisk-v30.7.apk"
    assert telemetry.ascension_manager_sha256_ref == "e0d32d2123532860"
    center.shutdown()


def test_companion_center_publishes_only_genuine_bounded_live_console_events(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    store = LiveConsoleEventStore(tmp_path)
    store.note(
        source="Device DNA",
        stage="capability-map",
        title="Capability Map updated",
        summary="Unknown evidence at /home/private/source.zip remains explicit.",
        explanation=f"ROMVERSE did not infer compatibility from {'a' * 64}.",
        next_action="Review the unconfirmed capability.",
        state=MissionState.ATTENTION,
    )
    center = CompanionCenter(store)

    telemetry = center._telemetry_snapshot()

    assert telemetry.schema_version == 6
    assert telemetry.live_console_integrity == "trusted"
    assert len(telemetry.live_console_events) == 1
    device_event = next(
        item for item in telemetry.live_console_events if item.source == "Device DNA"
    )
    assert "/home/private" not in device_event.summary
    assert "a" * 64 not in device_event.explanation
    assert "<local-path>" in device_event.summary
    assert "<sha256>" in device_event.explanation
    assert telemetry.live_console_execution_authority == "none"
    assert telemetry.raw_terminal_included is False
    center.shutdown()


def test_companion_center_publishes_device_dna_without_treating_no_relock_as_a_problem() -> None:
    QApplication.instance() or QApplication([])
    profile = DeviceDnaProfile(
        1,
        "profile",
        "project-id",
        "2026-08-30T00:00:00+00:00",
        "f" * 64,
        (),
        (),
        (
            CapabilityMapEntry(
                "source_adapter",
                "Automatic source adapter",
                CapabilityState.SUPPORTED,
                "Payload Atlas selected.",
            ),
            CapabilityMapEntry(
                "bootloader_relock",
                "Bootloader relocking",
                CapabilityState.UNSUPPORTED,
                "ROMVERSE never permits bootloader relocking.",
            ),
        ),
        (),
        (),
        False,
        "a" * 64,
    )
    center = CompanionCenter()

    center.set_device_dna(profile, "My ROM")

    telemetry = center._telemetry_snapshot()
    assert telemetry.device_dna_state == "ready"
    assert telemetry.device_dna_project == "My ROM"
    assert telemetry.device_dna_profile_ref == "a" * 16
    assert len(telemetry.device_dna_capabilities) == 2
    assert telemetry.device_dna_execution_authority == "none"
    assert telemetry.device_dna_bootloader_relock == "never"
    center.shutdown()


def test_companion_center_requires_matching_tls_safety_code_before_approval(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    store = LiveConsoleEventStore(tmp_path)
    center = CompanionCenter(store, workspace=tmp_path)

    assert center.transport.available
    assert "https://" in center.network_status.text()
    assert center.transport.safety_code in center.identity_status.text()
    assert center.transport.certificate_sha256 in center.identity_status.text()
    assert not center.approve.isEnabled()
    assert not center.safety_confirm.isEnabled()
    assert not center.copy_button.isEnabled()
    assert not center.reset_link.isEnabled()
    assert store.list_recent() == ()

    center.generate_code()
    assert center.copy_button.isEnabled()
    assert center.reset_link.isEnabled()
    assert any(item.title == "Encrypted Companion pairing opened" for item in store.list_recent())
    pairing = center._pairing
    assert pairing is not None
    assert center.transport._sessions.request(pairing, pairing.code, "127.0.0.1")
    center._update_expiry()
    assert center.safety_confirm.isEnabled()
    assert not center.approve.isEnabled()
    center.safety_confirm.setChecked(True)
    assert center.approve.isEnabled()
    center.approve_device()
    assert "Paired" in center.state.text()
    assert not center.copy_button.isEnabled()
    assert center.reset_link.isEnabled()
    assert center.generate.text() == "Replace wireless pairing code"
    assert "30 days" in center.expiry.text()
    assert "12 hours" not in center.expiry.text()
    assert any(item.title == "Encrypted Companion Link approved" for item in store.list_recent())
    center.shutdown()


def test_companion_center_restores_and_can_revoke_remembered_pairing(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    first = CompanionCenter(workspace=tmp_path)
    assert first.transport.available
    first.generate_code()
    pairing = first._pairing
    assert pairing is not None
    request_id = first.transport._sessions.request(pairing, pairing.code, "127.0.0.1")
    assert request_id
    first.safety_confirm.setEnabled(True)
    first.safety_confirm.setChecked(True)
    first.approve_device()
    token = first.transport._sessions.status(request_id).session_token
    assert token
    session_path = tmp_path / "config" / "companion-link" / "remembered-session.romverse"
    assert session_path.is_file()
    first.shutdown()

    restarted = CompanionCenter(workspace=tmp_path)
    assert restarted.transport.approved
    assert restarted.transport._sessions.authorize(token)
    assert "Remembered pairing active" in restarted.state.text()
    assert restarted.generate.text() == "Replace wireless pairing code"
    assert not restarted.copy_button.isEnabled()
    assert restarted.reset_link.isEnabled()
    assert "30 days" in restarted.expiry.text()

    restarted.reset_pairing()

    assert not restarted.transport.approved
    assert not restarted.transport._sessions.authorize(token)
    assert not session_path.exists()
    assert restarted.state.text() == "Not paired"
    assert restarted.generate.text() == "Generate wireless code"
    assert not restarted.copy_button.isEnabled()
    assert not restarted.reset_link.isEnabled()
    assert "revoked" in restarted.expiry.text()
    restarted.shutdown()


def test_companion_center_relays_only_verified_raw_terminal_feed(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    feed = RawTerminalFeed()
    feed.publish(
        "android-version",
        "$ adb -s private-serial shell getprop ro.build.version.release\n17\n\nExit code: 0",
        private_values=("private-serial",),
    )
    center = CompanionCenter(LiveConsoleEventStore(tmp_path), feed)

    telemetry = center._telemetry_snapshot()

    assert telemetry.schema_version == 6
    assert telemetry.raw_terminal_included
    assert telemetry.raw_terminal_integrity == "verified-local-feed"
    assert len(telemetry.raw_terminal_records) == 1
    assert telemetry.raw_terminal_records[0].probe_id == "android-version"
    assert "private-serial" not in "\n".join(telemetry.raw_terminal_records[0].lines)
    assert telemetry.live_console_execution_authority == "none"
    center.shutdown()
