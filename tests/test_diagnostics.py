from datetime import date

from romverse.device.models import AndroidDevice, DeviceState, StorageInfo
from romverse.diagnostics.analyzer import DiagnosticAnalyzer
from romverse.diagnostics.models import Severity


def device(**changes):
    values = {
        "serial": "PRIVATE-SERIAL-123",
        "state": DeviceState.DEVICE,
        "manufacturer": "RadForge",
        "model": "Reference Phone",
        "battery_percent": 75,
        "battery_temperature_c": 31.0,
        "storage": StorageInfo(percent_used=45),
        "security_patch": "2026-07-01",
        "bootloader_locked": True,
        "verified_boot": "green",
        "root_detected": False,
        "connection_note": "Connected",
    }
    values.update(changes)
    return AndroidDevice(**values)


def test_healthy_snapshot_has_clear_baseline():
    report = DiagnosticAnalyzer(date(2026, 8, 27)).analyze(device())
    assert report.health_score == 100
    assert report.highest_severity is Severity.HEALTHY
    assert report.findings[0].finding_id == "baseline.clear"


def test_manager_candidate_is_information_not_active_root_claim() -> None:
    report = DiagnosticAnalyzer(date(2026, 8, 27)).analyze(
        device(
            root_detected=False,
            root_signal_source="adb-shell-id",
            root_manager_candidate="magisk",
            root_manager_evidence="allowlisted-package-presence",
        )
    )

    finding = next(
        item for item in report.findings if item.finding_id == "security.root_manager_candidate"
    )
    assert finding.severity is Severity.INFORMATION
    assert "active root unconfirmed" in finding.title
    assert report.health_score == 100


def test_concerning_signals_are_evidence_backed():
    report = DiagnosticAnalyzer(date(2026, 8, 27)).analyze(
        device(
            battery_percent=4,
            battery_temperature_c=46.5,
            storage=StorageInfo(percent_used=98),
            security_patch="2024-01-01",
            bootloader_locked=False,
            verified_boot="red",
            root_detected=True,
        )
    )
    ids = {finding.finding_id for finding in report.findings}
    assert {
        "battery.low",
        "battery.temperature",
        "storage.capacity",
        "security.patch_age",
        "security.bootloader",
        "security.verified_boot",
        "security.root",
    } <= ids
    assert report.highest_severity is Severity.CRITICAL
    assert report.health_score == 0
    evidence_ids = {item.evidence_id for item in report.evidence}
    assert all(set(finding.evidence_ids) <= evidence_ids for finding in report.findings)


def test_unauthorized_device_does_not_claim_health():
    report = DiagnosticAnalyzer(date(2026, 8, 27)).analyze(
        device(state=DeviceState.UNAUTHORIZED, connection_note="Accept USB prompt")
    )
    assert report.health_score == 40
    assert report.findings[0].finding_id == "connection.unavailable"
    assert report.highest_severity is Severity.WARNING


def test_incomplete_boot_and_recent_boot_are_reported_from_read_only_evidence():
    incomplete = DiagnosticAnalyzer(date(2026, 8, 27)).analyze(
        device(boot_completed=False, uptime_seconds=90, slot_suffix="_a")
    )
    recent = DiagnosticAnalyzer(date(2026, 8, 27)).analyze(
        device(boot_completed=True, uptime_seconds=90, slot_suffix="_a")
    )

    assert any(item.finding_id == "boot.incomplete" for item in incomplete.findings)
    assert incomplete.health_score == 80
    assert any(item.finding_id == "boot.recent" for item in recent.findings)
    assert recent.health_score == 100
    evidence = {item.evidence_id: item.value for item in incomplete.evidence}
    assert evidence["boot.uptime"] == "00:01:30"
    assert evidence["boot.slot"] == "_a"
