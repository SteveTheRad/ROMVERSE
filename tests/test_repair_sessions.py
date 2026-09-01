from __future__ import annotations

import json
import stat
from dataclasses import asdict, replace

import pytest

from romverse.diagnostics.analyzer import DiagnosticAnalyzer
from romverse.repair.knowledge import knowledge_for
from romverse.repair.sessions import RepairSessionError, RepairSessionStore
from romverse.repair.templates import RepairConcern

from .test_diagnostics import device


def test_repair_session_tracks_review_without_claiming_success(tmp_path) -> None:
    store = RepairSessionStore(tmp_path)
    source = device(battery_percent=8)
    report = DiagnosticAnalyzer().analyze(source)
    steps = knowledge_for(RepairConcern.BATTERY_HEAT).recommended_steps

    session = store.start(
        RepairConcern.BATTERY_HEAT,
        source,
        report,
        steps,
        ("device-battery-low",),
    )
    reviewed = store.update_reviewed(session.session_id, tuple(range(len(steps))))

    assert reviewed.status == "ready_for_verification"
    assert reviewed.integrity_verified
    assert reviewed.archive_article_keys == ("device-battery-low",)
    assert reviewed.verification_summary == ""
    path = store.root / f"{session.session_id}.romverse-repair.json"
    payload = json.loads(path.read_text())
    assert payload["schema_version"] == 2
    assert payload["session"]["record_digest"] == reviewed.record_digest
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert source.serial not in path.read_text()


def test_fresh_repair_verification_compares_evidence(tmp_path) -> None:
    store = RepairSessionStore(tmp_path)
    source = device(battery_percent=8)
    initial = DiagnosticAnalyzer().analyze(source)
    session = store.start(
        RepairConcern.BATTERY_HEAT,
        source,
        initial,
        knowledge_for(RepairConcern.BATTERY_HEAT).recommended_steps,
    )
    improved = DiagnosticAnalyzer().analyze(device(battery_percent=70))

    verified = store.verify(session.session_id, source, improved)

    assert verified.status == "verified"
    assert verified.integrity_verified
    assert verified.verification_direction == "improved"
    assert verified.resolved_finding_ids == ("battery.low",)
    assert verified.added_finding_ids == ("baseline.clear",)
    assert verified.verification_health_score > verified.initial_health_score
    assert "improved" in verified.verification_summary
    assert store.list_recent()[0] == verified


def test_repair_session_rejects_changed_or_re_digested_false_outcome(tmp_path) -> None:
    store = RepairSessionStore(tmp_path)
    source = device(battery_percent=8)
    initial = DiagnosticAnalyzer().analyze(source)
    session = store.start(
        RepairConcern.BATTERY_HEAT,
        source,
        initial,
        knowledge_for(RepairConcern.BATTERY_HEAT).recommended_steps,
        ("device-battery-low",),
    )
    verified = store.verify(
        session.session_id,
        source,
        DiagnosticAnalyzer().analyze(device(battery_percent=70)),
    )
    path = store.root / f"{session.session_id}.romverse-repair.json"
    payload = json.loads(path.read_text())
    payload["session"]["verification_summary"] = "Fresh evidence is magically fixed."
    path.write_text(json.dumps(payload))

    with pytest.raises(RepairSessionError, match="integrity mismatch"):
        store.load(session.session_id)
    assert store.list_recent() == ()

    false_outcome = replace(
        verified,
        verification_direction="unchanged",
        record_digest="",
    )
    false_outcome = replace(
        false_outcome,
        record_digest=store._session_digest(false_outcome),
    )
    payload["session"] = asdict(false_outcome)
    path.write_text(json.dumps(payload))

    with pytest.raises(RepairSessionError, match="does not match its evidence"):
        store.load(session.session_id)


def test_repair_session_rejects_linked_storage(tmp_path) -> None:
    store = RepairSessionStore(tmp_path)
    source = device()
    report = DiagnosticAnalyzer().analyze(source)
    session = store.start(
        RepairConcern.NETWORK,
        source,
        report,
        knowledge_for(RepairConcern.NETWORK).recommended_steps,
    )
    path = store.root / f"{session.session_id}.romverse-repair.json"
    moved = tmp_path / "outside-session.json"
    path.replace(moved)
    path.symlink_to(moved)

    with pytest.raises(RepairSessionError, match="unreadable"):
        store.load(session.session_id)
    assert store.list_recent() == ()


@pytest.mark.parametrize(
    "mutation",
    ("extra-envelope-field", "extra-session-field", "boolean-score", "duplicate-finding"),
)
def test_repair_session_rejects_noncanonical_schema(tmp_path, mutation: str) -> None:
    store = RepairSessionStore(tmp_path)
    source = device(battery_percent=8)
    report = DiagnosticAnalyzer().analyze(source)
    session = store.start(
        RepairConcern.BATTERY_HEAT,
        source,
        report,
        knowledge_for(RepairConcern.BATTERY_HEAT).recommended_steps,
    )
    path = store.root / f"{session.session_id}.romverse-repair.json"
    payload = json.loads(path.read_text())
    if mutation == "extra-envelope-field":
        payload["unexpected"] = True
    elif mutation == "extra-session-field":
        payload["session"]["unexpected"] = True
    elif mutation == "boolean-score":
        payload["session"]["initial_health_score"] = True
    else:
        payload["session"]["initial_finding_ids"] *= 2
    path.write_text(json.dumps(payload))

    with pytest.raises(RepairSessionError, match="unreadable"):
        store.load(session.session_id)


def test_repair_session_rejects_oversized_evidence(tmp_path) -> None:
    store = RepairSessionStore(tmp_path)
    source = device()
    report = DiagnosticAnalyzer().analyze(source)
    session = store.start(
        RepairConcern.NETWORK,
        source,
        report,
        knowledge_for(RepairConcern.NETWORK).recommended_steps,
    )
    path = store.root / f"{session.session_id}.romverse-repair.json"
    path.write_bytes(b"{" + b"x" * store.MAXIMUM_BYTES)

    with pytest.raises(RepairSessionError, match="size boundary"):
        store.load(session.session_id)
    assert store.list_recent() == ()


def test_legacy_repair_session_is_readable_but_untrusted_until_resaved(tmp_path) -> None:
    store = RepairSessionStore(tmp_path)
    source = device()
    report = DiagnosticAnalyzer().analyze(source)
    session = store.start(
        RepairConcern.NETWORK,
        source,
        report,
        knowledge_for(RepairConcern.NETWORK).recommended_steps,
        ("android-network-triage",),
    )
    path = store.root / f"{session.session_id}.romverse-repair.json"
    payload = json.loads(path.read_text())
    payload["schema_version"] = 1
    for field in (
        "archive_article_keys",
        "verification_direction",
        "resolved_finding_ids",
        "added_finding_ids",
        "record_digest",
    ):
        payload["session"].pop(field)
    path.write_text(json.dumps(payload))

    legacy = store.load(session.session_id)
    assert not legacy.integrity_verified
    assert legacy.archive_article_keys == ()

    upgraded = store.update_reviewed(session.session_id, ())
    assert upgraded.integrity_verified
    assert json.loads(path.read_text())["schema_version"] == 2
