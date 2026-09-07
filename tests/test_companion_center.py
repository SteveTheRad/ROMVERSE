from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame

from romverse.ascension.companion import AscensionCompanionStatus
from romverse.companion.raw_terminal import RawTerminalFeed
from romverse.companion.telemetry import RemoteCompanionSnapshot
from romverse.companion.transfers import CompanionTransferKind
from romverse.device.dna import CapabilityMapEntry, CapabilityState, DeviceDnaProfile
from romverse.device.models import AndroidDevice, DeviceState, StorageInfo
from romverse.nexus.events import LiveConsoleEventStore, MissionState
from romverse.ui.companion_center import CompanionCenter


class FakeUsbPairingService:
    def __init__(self) -> None:
        self.prepared: dict[str, object] | None = None
        self.approved = False
        self.launched = False

    def prepare(self, **values):
        self.prepared = values
        return SimpleNamespace(values=values)

    def approve(self, _plan):
        self.approved = True
        return ()

    def launch(self, _plan):
        self.launched = True
        return SimpleNamespace(ok=True, detail="confirmation opened")


def test_companion_link_keeps_pairing_controls_readable_in_a_scroll_surface(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    center = CompanionCenter(workspace=tmp_path)
    center.resize(760, 560)
    center.show()
    app.processEvents()

    assert center.scroll.widgetResizable()
    assert center.scroll.horizontalScrollBar().maximum() == 0
    assert center.findChild(QFrame, "CompanionPairingCard") is not None
    assert center.findChild(QFrame, "PairingApprovalBar") is not None
    assert center.findChild(QFrame, "CompanionTransferCard") is not None
    assert center.generate.height() >= 30
    assert center.copy_button.height() >= 30
    assert center.approve.height() >= 30
    center.shutdown()
    center.close()


def test_secure_handoff_enables_only_for_a_confirmed_companion_link(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    center = CompanionCenter(workspace=tmp_path)
    assert not center.transfer_button.isEnabled()
    assert "Pair Companion" in center.transfer_status.text()

    center.generate_code()
    pairing = center._pairing
    assert pairing is not None
    request_id = center.transport._sessions.request(pairing, pairing.code, "127.0.0.1")
    assert request_id
    center._update_expiry()
    center.safety_confirm.setChecked(True)
    center.approve_device()

    assert center.transfer_button.isEnabled()
    assert "Encrypted bridge ready" in center.transfer_status.text()
    report = tmp_path / "first-light-report.json"
    report.write_text('{"camera":"verified"}')
    service = center.transfer_service
    assert service is not None
    offer = service.stage(service.inspect(report, CompanionTransferKind.REPORT))
    center._transfer_staged(offer)

    assert "READY FOR COMPANION" in center.transfer_status.text()
    assert center.transfer_clear.isEnabled()
    center.reset_pairing()
    assert service.list_active() == ()
    assert not center.transfer_button.isEnabled()
    assert not center.transfer_clear.isEnabled()
    center.shutdown()


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
    assert center.transport.port == 0
    assert not center.transport.running
    assert center.transport._server is None
    assert center.transport._discovery_thread is None
    assert "endpoint idle" in center.network_status.text()
    assert center.transport.safety_code in center.identity_status.text()
    assert center.transport.certificate_sha256 in center.identity_status.text()
    assert not center.approve.isEnabled()
    assert not center.safety_confirm.isEnabled()
    assert not center.copy_button.isEnabled()
    assert not center.reset_link.isEnabled()
    assert store.list_recent() == ()

    center.generate_code()
    assert center.transport.running
    assert center.transport.port > 0
    assert "https://" in center.network_status.text()
    server = center.transport._server
    discovery_thread = center.transport._discovery_thread
    center.generate_code()
    assert center.transport._server is server
    assert center.transport._discovery_thread is discovery_thread
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
    assert not center.transport.running
    assert discovery_thread is not None and not discovery_thread.is_alive()


def test_companion_center_reports_one_bounded_listener_start_failure(tmp_path, monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    attempts = 0

    def denied_server(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise PermissionError("local sockets denied")

    monkeypatch.setattr("romverse.companion.transport.CompanionHTTPServer", denied_server)
    center = CompanionCenter(workspace=tmp_path)

    assert center.generate.isEnabled()
    assert center.transport._server is None
    center.generate_code()

    assert attempts == 2
    assert center._pairing is None
    assert center.state.text() == "Wireless pairing unavailable"
    assert not center.generate.isEnabled()
    assert not center.transport.running
    assert center.transport._discovery_thread is None
    assert "denied" in center.transport.availability_error

    center.generate_code()
    assert attempts == 2
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
    assert restarted.transport.running
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


def test_usb_evidence_never_masquerades_as_encrypted_companion_pairing(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    center = CompanionCenter(workspace=tmp_path)
    phone = AndroidDevice(
        "private-serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        marketing_name="Xiaomi 17 Pro Max",
        battery_percent=88,
        storage=StorageInfo(total_bytes=200, used_bytes=50),
        companion_installed=True,
        companion_version="0.2.0-alpha.1",
    )

    center.set_device_snapshot([phone])

    assert center._usb_ready
    assert "Companion installed" in center.device_status.text()
    assert center.state.text() == "USB connected • wireless Link not paired"
    assert "Encrypted Companion Link is separate" in center.instructions.text()
    assert center.generate.isEnabled()

    center.generate_code()
    assert center.state.text() == "Awaiting device approval"
    center.set_device_snapshot([phone])
    assert center.state.text() == "Awaiting device approval"
    pairing = center._pairing
    assert pairing is not None
    request_id = center.transport._sessions.request(pairing, pairing.code, "127.0.0.1")
    assert request_id
    center._update_expiry()
    center.safety_confirm.setChecked(True)
    center.approve_device()

    assert "Paired • read-only wireless telemetry enabled" in center.state.text()
    assert "USB also connected" in center.state.text()
    assert center.generate.isEnabled()

    center.reset_pairing()

    assert center.state.text() == (
        "Wireless Link not paired • USB read-only evidence remains available"
    )
    assert "USB continues supplying Desktop's read-only device scan" in center.instructions.text()
    assert center.generate.isEnabled()
    center.shutdown()


def test_non_usb_adb_never_enables_or_claims_physical_usb(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    cases = (
        ("emulator-5554", "emulator", "Local Android emulator"),
        ("192.168.1.17:5555", "network", "Network ADB"),
        ("LOCALADB", "adb", "Unconfirmed ADB transport"),
    )

    for serial, transport, source in cases:
        center = CompanionCenter(workspace=tmp_path / transport)
        target = AndroidDevice(
            serial,
            DeviceState.DEVICE,
            transport=transport,
            model="Development target",
            companion_installed=True,
        )

        center.set_device_snapshot([target])

        assert not center._usb_ready
        assert center._usb_serial == ""
        assert not center.usb_pair.isEnabled()
        assert source in center.device_status.text()
        assert center.state.text() == f"{source} connected • wireless Link not paired"
        assert "USB connected" not in center.state.text()
        assert "USB also connected" not in center.state.text()
        assert "USB" not in center.instructions.text()

        center.generate_code()
        pairing = center._pairing
        assert pairing is not None
        request_id = center.transport._sessions.request(
            pairing,
            pairing.code,
            "127.0.0.1",
        )
        assert request_id
        center._update_expiry()
        center.safety_confirm.setChecked(True)
        center.approve_device()

        assert "Paired • read-only wireless telemetry enabled" in center.state.text()
        assert "USB also connected" not in center.state.text()
        assert "Physical USB" not in center.instructions.text()
        assert not center.usb_pair.isEnabled()

        center.reset_pairing()

        assert center.state.text() == "Not paired"
        assert "USB" not in center.state.text()
        assert not center._usb_ready
        assert center._usb_serial == ""
        assert not center.usb_pair.isEnabled()
        center.shutdown()


def test_nonready_virtual_and_network_targets_remain_fail_closed_without_usb_claims(
    tmp_path,
) -> None:
    QApplication.instance() or QApplication([])
    cases = (
        ("emulator-5554", "emulator", DeviceState.UNAUTHORIZED, "Local Android emulator"),
        ("192.168.1.17:5555", "network", DeviceState.OFFLINE, "Network ADB"),
    )

    for serial, transport, state, source in cases:
        center = CompanionCenter(workspace=tmp_path / f"{transport}-{state.value}")
        target = AndroidDevice(serial, state, transport=transport, model="Development target")

        center.set_device_snapshot([target])

        assert not center._usb_ready
        assert not center.usb_pair.isEnabled()
        assert center.state.text().startswith(f"{source} detected")
        assert "USB" not in center.state.text()
        assert "USB" not in center.instructions.text()
        center.shutdown()

    center = CompanionCenter(workspace=tmp_path / "multiple")
    observed = [
        AndroidDevice("emulator-5554", DeviceState.DEVICE, transport="emulator"),
        AndroidDevice("192.168.1.17:5555", DeviceState.DEVICE, transport="network"),
    ]
    center.set_device_snapshot([], observed_devices=observed)
    assert not center._usb_ready
    assert "2 Android targets detected" in center.device_status.text()
    assert "USB" not in center.device_status.text()
    center.shutdown()


def test_disconnected_usb_state_does_not_linger_as_connected(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    center = CompanionCenter(workspace=tmp_path)
    phone = AndroidDevice(
        "private-serial",
        DeviceState.DEVICE,
        model="Test phone",
        companion_installed=True,
    )
    center.set_device_snapshot([phone])
    assert center._usb_ready

    center.set_device_snapshot([])

    assert not center._usb_ready
    assert center.state.text() == "Not paired"
    assert "no Android target detected" in center.device_status.text()
    assert center.generate.isEnabled()
    center.shutdown()


def test_usb_assist_waits_for_phone_confirmation_then_approves_automatically(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    service = FakeUsbPairingService()
    center = CompanionCenter(workspace=tmp_path, usb_pairing_service=service)
    phone = AndroidDevice(
        "private-serial",
        DeviceState.DEVICE,
        model="Test phone",
        companion_installed=True,
    )
    center.set_device_snapshot([phone])

    assert center.usb_pair.isEnabled()
    center.pair_connected_usb()

    assert service.prepared is not None
    assert service.prepared["serial"] == "private-serial"
    assert service.approved
    assert service.launched
    assert "safety code on your phone" in center.state.text()
    assert not center.transport.approved
    pairing = center._pairing
    assert pairing is not None

    request_id = center.transport._sessions.request(pairing, pairing.code, "127.0.0.1")
    assert request_id
    center._update_expiry()

    assert center.transport.approved
    assert "Paired • read-only wireless telemetry enabled" in center.state.text()
    assert not center.safety_confirm.isEnabled()
    assert not center.usb_pair.isEnabled()
    center.shutdown()


def test_usb_assist_requires_companion_on_the_selected_authorized_phone(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    service = FakeUsbPairingService()
    center = CompanionCenter(workspace=tmp_path, usb_pairing_service=service)
    phone = AndroidDevice(
        "private-serial",
        DeviceState.DEVICE,
        model="Test phone",
        companion_installed=False,
    )

    center.set_device_snapshot([phone])

    assert not center.usb_pair.isEnabled()
    assert "Install ROMVERSE Companion" in center.usb_pair.toolTip()
    center.shutdown()


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
