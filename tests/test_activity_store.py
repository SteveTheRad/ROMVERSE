from __future__ import annotations

import json

import pytest

from romverse.core.activity import ActivityStore, ActivityStoreError


def test_activity_store_records_deduplicates_and_exports_redacted_ledger(tmp_path) -> None:
    store = ActivityStore(tmp_path)
    first = store.record(
        "device",
        "Device scan completed",
        "Authorized read-only evidence captured",
        outcome="success",
        source="Device Engine",
        dedupe_key="scan:device-key",
        dedupe_seconds=900,
    )
    repeated = store.record(
        "device",
        "Device scan completed",
        "Authorized read-only evidence captured",
        outcome="success",
        source="Device Engine",
        dedupe_key="scan:device-key",
        dedupe_seconds=900,
    )

    assert repeated.event_id == first.event_id
    assert store.list_recent() == (first,)
    exported = store.export(tmp_path / "export.json")
    payload = json.loads(exported.read_text())
    assert payload["privacy"] == "redacted"
    assert payload["events"][0]["source"] == "Device Engine"


def test_activity_store_preserves_unreadable_ledger(tmp_path) -> None:
    path = tmp_path / "logs" / "activity-v1.json"
    path.parent.mkdir(parents=True)
    path.write_text("not json")

    with pytest.raises(ActivityStoreError, match="unreadable"):
        ActivityStore(tmp_path).record("device", "Scan", "Evidence")

    assert path.read_text() == "not json"
