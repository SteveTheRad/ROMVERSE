from __future__ import annotations

import json
import os
import stat

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
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(store.directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(exported.stat().st_mode) == 0o600


def test_activity_store_round_trips_exact_context_and_migrates_legacy_events(tmp_path) -> None:
    store = ActivityStore(tmp_path)
    store.record("device", "Legacy scan", "Read-only evidence")
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    payload["schema_version"] = store.LEGACY_SCHEMA_VERSION
    for key in ("source_route", "context_type", "context_id"):
        payload["events"][0].pop(key)
    store.path.write_text(json.dumps(payload), encoding="utf-8")

    legacy = store.list_recent()[0]
    assert (legacy.source_route, legacy.context_type, legacy.context_id) == ("", "", "")

    exact = store.record(
        "rom-studio",
        "Project verified",
        "Protected source remained unchanged",
        outcome="success",
        source="ROM Studio",
        source_route="rom_studio",
        context_type="rom-project",
        context_id="project-one-1234abcd",
    )
    rewritten = json.loads(store.path.read_text(encoding="utf-8"))
    assert rewritten["schema_version"] == store.SCHEMA_VERSION
    assert store.list_recent()[0] == exact
    assert rewritten["events"][1]["context_id"] == ""


@pytest.mark.parametrize(
    ("route", "context_type", "context_id"),
    (
        ("rom_studio", "rom-project", ""),
        ("time_machine", "rom-project", "project-one-1234abcd"),
        ("rom_studio", "rom-project", "/private/device/path"),
        ("rom_studio", "device-serial", "abc123"),
    ),
)
def test_activity_store_rejects_incomplete_unsupported_or_path_context(
    tmp_path,
    route,
    context_type,
    context_id,
) -> None:
    with pytest.raises(ActivityStoreError, match="context|privacy-safe"):
        ActivityStore(tmp_path).record(
            "rom-studio",
            "Project verified",
            "Evidence",
            source_route=route,
            context_type=context_type,
            context_id=context_id,
        )


def test_activity_store_preserves_unreadable_ledger(tmp_path) -> None:
    path = tmp_path / "logs" / "activity-v1.json"
    path.parent.mkdir(parents=True)
    path.write_text("not json")

    with pytest.raises(ActivityStoreError, match="unreadable"):
        ActivityStore(tmp_path).record("device", "Scan", "Evidence")

    assert path.read_text() == "not json"


def test_activity_store_rejects_extra_fields_oversized_files_and_links(tmp_path) -> None:
    store = ActivityStore(tmp_path)
    store.record("device", "Scan", "Read-only evidence")
    original = store.path.read_text(encoding="utf-8")
    payload = json.loads(original)
    payload["events"][0]["execution_authority"] = "device"
    store.path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ActivityStoreError, match="fields are invalid"):
        store.list_recent()

    store.path.write_bytes(b" " * (store.MAX_FILE_BYTES + 1))
    with pytest.raises(ActivityStoreError, match="size limit"):
        store.list_recent()

    store.path.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text(original, encoding="utf-8")
    store.path.symlink_to(outside)
    with pytest.raises(ActivityStoreError, match="regular file"):
        store.list_recent()
    assert os.path.islink(store.path)
    assert outside.read_text(encoding="utf-8") == original
