from __future__ import annotations

from romverse.diagnostics.analyzer import DiagnosticAnalyzer
from romverse.repair.knowledge import knowledge_for
from romverse.repair.sessions import RepairSessionStore
from romverse.repair.templates import RepairConcern

from .test_diagnostics import device


def test_repair_session_tracks_review_without_claiming_success(tmp_path) -> None:
    store = RepairSessionStore(tmp_path)
    source = device(battery_percent=8)
    report = DiagnosticAnalyzer().analyze(source)
    steps = knowledge_for(RepairConcern.BATTERY_HEAT).recommended_steps

    session = store.start(RepairConcern.BATTERY_HEAT, source, report, steps)
    reviewed = store.update_reviewed(session.session_id, tuple(range(len(steps))))

    assert reviewed.status == "ready_for_verification"
    assert reviewed.verification_summary == ""
    assert (
        source.serial not in (store.root / f"{session.session_id}.romverse-repair.json").read_text()
    )


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
    assert verified.verification_health_score > verified.initial_health_score
    assert "improved" in verified.verification_summary
    assert store.list_recent()[0] == verified
