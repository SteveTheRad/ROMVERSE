import hashlib
import json
import socket
import ssl
import urllib.error
import urllib.request
from datetime import UTC, datetime

import pytest

from romverse.companion.pairing import create_pairing_code
from romverse.companion.transport import CompanionTransport


def tls_context() -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def endpoint(transport: CompanionTransport, path: str) -> str:
    return f"https://127.0.0.1:{transport.port}{path}"


def open_link(request: str | urllib.request.Request):
    return urllib.request.urlopen(request, context=tls_context())


def remote_snapshot_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "captured_at_epoch_ms": int(datetime.now(UTC).timestamp() * 1_000),
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
        "guardian_active": True,
        "privacy_scope": "health_only",
    }


def vitalis_remote_snapshot_payload() -> dict[str, object]:
    return remote_snapshot_payload() | {
        "schema_version": 4,
        "battery_temperature_celsius": 31.5,
        "network_validated": True,
        "usb_connected": True,
        "health_score": 100,
        "vitalis_state": "OPTIMAL",
        "vitalis_evidence_percent": 100,
        "kernel_release": "6.12.23-popsicle",
        "root_signal": "not_observed",
        "root_manager_candidate": "magisk",
        "bootloader_state": "unknown",
        "kernelsu_support": "unknown",
        "privacy_scope": "health_and_device_safety",
    }


def test_transport_validates_tls_pairing_and_approval(tmp_path) -> None:
    pairing = create_pairing_code()
    transport = CompanionTransport(lambda: pairing, identity_root=tmp_path)
    if not transport.available:
        pytest.skip("execution environment denies local sockets")
    transport.start()
    try:
        request = urllib.request.Request(
            endpoint(transport, "/pair"),
            data=json.dumps({"code": pairing.code}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with open_link(request) as response:
            pair_response = json.load(response)
            assert response.headers["Strict-Transport-Security"] == "max-age=31536000"
        assert pair_response["status"] == "pending"
        assert pair_response["protocol_version"] == 3
        request_id = pair_response["request_id"]
        assert transport.pending
        status_request = urllib.request.Request(
            endpoint(transport, "/status"),
            headers={"X-ROMVERSE-Pairing-Request": request_id},
        )
        with open_link(status_request) as response:
            assert json.load(response)["status"] == "pending"
        transport.approve()
        with open_link(status_request) as response:
            approval = json.load(response)
        assert approval["status"] == "approved"
        token = approval["session_token"]
        telemetry_request = urllib.request.Request(
            endpoint(transport, "/telemetry"),
            headers={"Authorization": f"Bearer {token}"},
        )
        with open_link(telemetry_request) as response:
            telemetry = json.load(response)
        assert telemetry["schema_version"] == 6
        assert telemetry["ascension_state"] == "no_project"
        assert telemetry["ascension_phone_changed"] is False
        assert telemetry["ascension_execution_authority"] == "none"
        assert telemetry["live_console_execution_authority"] == "none"
        assert telemetry["raw_terminal_included"] is False
        assert telemetry["raw_terminal_integrity"] == "unavailable"
        assert telemetry["raw_terminal_records"] == []
        assert telemetry["device_dna_state"] == "unavailable"
        assert telemetry["device_dna_project"] == ""
        assert telemetry["device_dna_profile_ref"] == ""
        assert telemetry["device_dna_warning_count"] == 0
        assert telemetry["device_dna_capabilities"] == []
        assert telemetry["device_dna_execution_authority"] == "none"
        assert telemetry["device_dna_bootloader_relock"] == "never"
        remote_request = urllib.request.Request(
            endpoint(transport, "/companion/telemetry"),
            data=json.dumps(vitalis_remote_snapshot_payload()).encode(),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with open_link(remote_request) as response:
            accepted = json.load(response)
        assert accepted == {
            "protocol_version": 3,
            "status": "accepted",
            "privacy_scope": "health_and_device_safety",
        }
        assert transport.latest_remote_snapshot is not None
        assert transport.latest_remote_snapshot.model == "2509FPN0BC"
        assert transport.latest_remote_snapshot.vitalis_state == "OPTIMAL"
        assert transport.latest_remote_snapshot.vitalis_evidence_percent == 100
        assert transport.remote_snapshot_received_at is not None
        transport.reset()
        assert transport.latest_remote_snapshot is None
    finally:
        transport.close()


def test_transport_rejects_unapproved_telemetry_and_unknown_requests() -> None:
    pairing = create_pairing_code()
    transport = CompanionTransport(lambda: pairing)
    if not transport.available:
        pytest.skip("execution environment denies local sockets")
    transport.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as telemetry_error:
            open_link(endpoint(transport, "/telemetry"))
        with telemetry_error.value as error:
            assert error.code == 401

        status_request = urllib.request.Request(
            endpoint(transport, "/status"),
            headers={"X-ROMVERSE-Pairing-Request": "unknown-request"},
        )
        with pytest.raises(urllib.error.HTTPError) as status_error:
            open_link(status_request)
        with status_error.value as error:
            assert error.code == 403
    finally:
        transport.close()


def test_transport_unavailability_does_not_block_the_app(monkeypatch) -> None:
    def denied_server(*_args, **_kwargs):
        raise PermissionError("local sockets denied")

    monkeypatch.setattr("romverse.companion.transport.CompanionHTTPServer", denied_server)
    transport = CompanionTransport(lambda: None)

    assert not transport.available
    assert transport.port == 0
    assert "denied" in transport.availability_error
    transport.start()
    transport.close()


def test_transport_rejects_unauthorized_remote_telemetry_before_reading_body() -> None:
    transport = CompanionTransport(lambda: None)
    if not transport.available:
        pytest.skip("execution environment denies local sockets")
    transport.start()
    try:
        request = urllib.request.Request(
            endpoint(transport, "/companion/telemetry"),
            data=json.dumps(remote_snapshot_payload()).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            open_link(request)
        with error.value as response:
            assert response.code == 401
        assert transport.latest_remote_snapshot is None
    finally:
        transport.close()


def test_transport_bounds_pairing_and_remote_telemetry_requests() -> None:
    pairing = create_pairing_code()
    transport = CompanionTransport(lambda: pairing)
    if not transport.available:
        pytest.skip("execution environment denies local sockets")
    transport.start()
    try:
        pair_request = urllib.request.Request(
            endpoint(transport, "/pair"),
            data=json.dumps({"code": pairing.code}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with open_link(pair_request) as response:
            request_id = json.load(response)["request_id"]
        assert transport.approve()
        status_request = urllib.request.Request(
            endpoint(transport, "/status"),
            headers={"X-ROMVERSE-Pairing-Request": request_id},
        )
        with open_link(status_request) as response:
            token = json.load(response)["session_token"]

        invalid_request = urllib.request.Request(
            endpoint(transport, "/companion/telemetry"),
            data=b"[]",
            headers={"Authorization": f"Bearer {token}"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as invalid_error:
            open_link(invalid_request)
        with invalid_error.value as error:
            assert error.code == 400

        unsafe_request = urllib.request.Request(
            endpoint(transport, "/companion/telemetry"),
            data=json.dumps(remote_snapshot_payload() | {"command": "reboot"}).encode(),
            headers={"Authorization": f"Bearer {token}"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as unsafe_error:
            open_link(unsafe_request)
        with unsafe_error.value as error:
            assert error.code == 400

        stale_request = urllib.request.Request(
            endpoint(transport, "/companion/telemetry"),
            data=json.dumps(remote_snapshot_payload() | {"captured_at_epoch_ms": 1}).encode(),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as stale_error:
            open_link(stale_request)
        with stale_error.value as error:
            assert error.code == 400
            assert "stale" in json.load(error)["detail"]

        oversized_request = urllib.request.Request(
            endpoint(transport, "/companion/telemetry"),
            data=b"{" + b" " * CompanionTransport.MAX_REMOTE_TELEMETRY_BYTES + b"}",
            headers={"Authorization": f"Bearer {token}"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as oversized_error:
            open_link(oversized_request)
        with oversized_error.value as error:
            assert error.code == 413
        assert transport.latest_remote_snapshot is None
    finally:
        transport.close()


def test_transport_advertises_and_serves_only_its_exact_tls_identity(tmp_path) -> None:
    transport = CompanionTransport(lambda: None, identity_root=tmp_path)
    if not transport.available:
        pytest.skip("execution environment denies local sockets")
    transport.start()
    try:
        payload = transport.discovery_payload
        assert payload == {
            "service": "ROMVERSE_COMPANION",
            "port": transport.port,
            "scheme": "https",
            "protocol_version": 3,
            "certificate_sha256": transport.certificate_sha256,
            "safety_code": transport.safety_code,
        }
        with (
            socket.create_connection(("127.0.0.1", transport.port), timeout=2) as connection,
            tls_context().wrap_socket(connection, server_hostname="romverse.local") as secured,
        ):
            observed = hashlib.sha256(secured.getpeercert(binary_form=True)).hexdigest()
        assert observed == transport.certificate_sha256

        with pytest.raises((ConnectionError, urllib.error.URLError)):
            urllib.request.urlopen(f"http://127.0.0.1:{transport.port}/status", timeout=2)
    finally:
        transport.close()


def test_transport_remembers_approved_phone_across_desktop_restart(tmp_path) -> None:
    pairing = create_pairing_code()
    first = CompanionTransport(lambda: pairing, identity_root=tmp_path)
    if not first.available:
        pytest.skip("execution environment denies local sockets")
    first.start()
    try:
        pair_request = urllib.request.Request(
            endpoint(first, "/pair"),
            data=json.dumps({"code": pairing.code}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with open_link(pair_request) as response:
            request_id = json.load(response)["request_id"]
        assert first.approve()
        status_request = urllib.request.Request(
            endpoint(first, "/status"),
            headers={"X-ROMVERSE-Pairing-Request": request_id},
        )
        with open_link(status_request) as response:
            token = json.load(response)["session_token"]
    finally:
        first.close()

    restarted = CompanionTransport(lambda: None, identity_root=tmp_path)
    if not restarted.available:
        pytest.skip("execution environment denies local sockets")
    restarted.start()
    try:
        telemetry_request = urllib.request.Request(
            endpoint(restarted, "/telemetry"),
            headers={"Authorization": f"Bearer {token}"},
        )
        with open_link(telemetry_request) as response:
            assert json.load(response)["schema_version"] == 6
        assert restarted.approved
        restarted.reset()
        assert not (tmp_path / "remembered-session.romverse").exists()
    finally:
        restarted.close()
