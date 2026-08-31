import json

import pytest

from romverse.diagnostics.analyzer import DiagnosticAnalyzer
from romverse.diagnostics.history import DiagnosticHistoryError, DiagnosticHistoryStore

from .test_diagnostics import device


def test_saved_report_is_redacted_and_stably_pseudonymous(tmp_path):
    source = device(build_fingerprint="private/fingerprint/value")
    report = DiagnosticAnalyzer().analyze(source)
    store = DiagnosticHistoryStore(tmp_path)
    first = store.save(report, source)
    second = store.save(report, source)
    first_data = json.loads(first.read_text())
    second_data = json.loads(second.read_text())

    serialized = first.read_text()
    assert source.serial not in serialized
    assert source.build_fingerprint not in serialized
    assert first_data["privacy"] == "redacted"
    assert first_data["snapshot_format"] == "romverse.diagnostic-snapshot"
    assert len(first_data["snapshot_digest"]) == 64
    assert first_data["device_key"] == second_data["device_key"]
    assert len(store.list_reports()) == 2
    assert (tmp_path / ".romverse-privacy.json").exists()
    assert all(item.integrity_verified for item in store.load_reports())
    assert not list(store.root.glob(".*.tmp"))


def test_saved_report_records_truthful_activity(tmp_path):
    from romverse.core.activity import ActivityStore

    activity = ActivityStore(tmp_path)
    source = device()
    report = DiagnosticAnalyzer().analyze(source)

    DiagnosticHistoryStore(tmp_path, activity).save(report, source)

    event = activity.list_recent()[0]
    assert event.title == "Health snapshot saved"
    assert event.outcome == "success"
    assert source.serial not in activity.path.read_text()


def test_history_loads_and_compares_same_device_snapshots(tmp_path):
    store = DiagnosticHistoryStore(tmp_path)
    source = device()
    healthy = DiagnosticAnalyzer().analyze(source)
    concerning_source = device(battery_percent=4)
    concerning = DiagnosticAnalyzer().analyze(concerning_source)
    store.save(healthy, source)
    store.save(concerning, concerning_source)

    reports = store.load_reports()
    assert len(reports) == 2
    comparison = store.compare(reports[0], reports[1])
    assert comparison is not None
    assert comparison.score_delta == -25
    assert [item.finding_id for item in comparison.added] == ["battery.low"]
    assert [item.finding_id for item in comparison.resolved] == ["baseline.clear"]


def test_history_ignores_invalid_or_unredacted_files(tmp_path):
    root = tmp_path / "diagnostics" / "history"
    root.mkdir(parents=True)
    (root / "diagnostic-broken.json").write_text("not json")
    (root / "diagnostic-unsafe.json").write_text(
        json.dumps({"schema_version": 1, "privacy": "raw"})
    )
    scan = DiagnosticHistoryStore(tmp_path).scan_reports()
    assert scan.reports == ()
    assert len(scan.rejected) == 2


def test_history_preserves_and_reports_tampered_snapshot(tmp_path):
    store = DiagnosticHistoryStore(tmp_path)
    source = device()
    path = store.save(DiagnosticAnalyzer().analyze(source), source)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["health_score"] = 1
    path.write_text(json.dumps(payload), encoding="utf-8")

    scan = store.scan_reports()
    assert scan.reports == ()
    assert len(scan.rejected) == 1
    assert scan.rejected[0].path == path
    assert "integrity mismatch" in scan.rejected[0].reason.casefold()
    assert path.exists()


def test_legacy_diagnostic_snapshot_remains_readable_but_unverified(tmp_path):
    store = DiagnosticHistoryStore(tmp_path)
    source = device()
    path = store.save(DiagnosticAnalyzer().analyze(source), source)
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in (
        "snapshot_format",
        "snapshot_version",
        "snapshot_id",
        "snapshot_digest",
    ):
        payload.pop(key)
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = store.load_reports()[0]
    assert not report.integrity_verified
    assert report.snapshot_digest == ""
    assert len(report.content_digest) == 64
    assert "legacy" in report.verification_reason.casefold()


def test_export_reverifies_selected_snapshot_and_stops_if_it_changed(tmp_path):
    store = DiagnosticHistoryStore(tmp_path)
    source = device()
    path = store.save(DiagnosticAnalyzer().analyze(source), source)
    selected = store.load_reports()[0]
    exported = store.export_report(selected, tmp_path / "exports" / "snapshot.json")
    assert exported.is_file()
    assert json.loads(exported.read_text())["snapshot_digest"] == selected.snapshot_digest

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["summary"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DiagnosticHistoryError, match="failed verification"):
        store.export_report(selected, tmp_path / "exports" / "rejected.json")
    assert not (tmp_path / "exports" / "rejected.json").exists()


def test_legacy_export_is_bound_to_the_exact_selected_content(tmp_path):
    store = DiagnosticHistoryStore(tmp_path)
    source = device()
    path = store.save(DiagnosticAnalyzer().analyze(source), source)
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in (
        "snapshot_format",
        "snapshot_version",
        "snapshot_id",
        "snapshot_digest",
    ):
        payload.pop(key)
    path.write_text(json.dumps(payload), encoding="utf-8")
    selected = store.load_reports()[0]

    payload["summary"] = "a different but still schema-valid legacy summary"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DiagnosticHistoryError, match="changed after it was selected"):
        store.export_report(selected, tmp_path / "legacy-export.json")
    assert not (tmp_path / "legacy-export.json").exists()


def test_history_rejects_symlinked_snapshot(tmp_path):
    store = DiagnosticHistoryStore(tmp_path)
    store.root.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    linked = store.root / "diagnostic-linked.json"
    linked.symlink_to(outside)

    scan = store.scan_reports()
    assert scan.reports == ()
    assert len(scan.rejected) == 1
    assert "regular local file" in scan.rejected[0].reason
