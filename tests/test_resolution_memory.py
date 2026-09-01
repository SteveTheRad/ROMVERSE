from __future__ import annotations

import json

from romverse.diagnostics.analyzer import DiagnosticAnalyzer
from romverse.knowledge.resolution_memory import ArchivesResolutionMemory
from romverse.repair.knowledge import knowledge_for
from romverse.repair.sessions import RepairSessionStore
from romverse.repair.templates import RepairConcern

from .test_diagnostics import device


def _session(
    store: RepairSessionStore,
    *,
    initial_battery: int,
    final_battery: int,
    article_key: str = "device-battery-low",
):
    analyzer = DiagnosticAnalyzer()
    source = device(battery_percent=initial_battery)
    started = store.start(
        RepairConcern.BATTERY_HEAT,
        source,
        analyzer.analyze(source),
        knowledge_for(RepairConcern.BATTERY_HEAT).recommended_steps,
        (article_key,),
    )
    return store.verify(
        started.session_id,
        source,
        analyzer.analyze(device(battery_percent=final_battery)),
    )


def test_resolution_memory_compiles_only_structured_verified_comparisons(tmp_path) -> None:
    store = RepairSessionStore(tmp_path)
    _session(store, initial_battery=8, final_battery=70)
    _session(store, initial_battery=8, final_battery=8)
    _session(store, initial_battery=70, final_battery=8)
    unverified = device(battery_percent=8)
    store.start(
        RepairConcern.BATTERY_HEAT,
        unverified,
        DiagnosticAnalyzer().analyze(unverified),
        knowledge_for(RepairConcern.BATTERY_HEAT).recommended_steps,
        ("device-battery-low",),
    )

    memory = ArchivesResolutionMemory(store).for_article("device-battery-low")

    assert memory is not None
    assert memory.comparisons == 3
    assert memory.improved == 1
    assert memory.unchanged == 1
    assert memory.needs_attention == 1
    assert "correlation" in memory.plain_text.casefold()
    assert "does not prove" in memory.plain_text.casefold()
    assert "automatic execution authority" in memory.plain_text.casefold()


def test_resolution_memory_is_exact_article_scoped_and_fail_closed(tmp_path) -> None:
    store = RepairSessionStore(tmp_path)
    session = _session(store, initial_battery=8, final_battery=70)
    memory = ArchivesResolutionMemory(store)

    assert memory.for_article("device-temperature-elevated") is None
    assert memory.for_article("not-a-real-article") is None

    path = store.root / f"{session.session_id}.romverse-repair.json"
    payload = json.loads(path.read_text())
    payload["session"]["verification_direction"] = "unchanged"
    path.write_text(json.dumps(payload))

    assert memory.for_article("device-battery-low") is None
