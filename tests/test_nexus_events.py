from __future__ import annotations

import json

import pytest

from romverse.nexus.events import (
    LiveConsoleEventStore,
    LiveConsoleStoreError,
    MissionConfidence,
    MissionState,
)


def _start(store: LiveConsoleEventStore):
    return store.start(
        source="ROM Studio",
        stage="firmware-inspection",
        title="Inspect protected firmware",
        summary="ROMVERSE started bounded firmware inspection.",
        explanation="Inspection identifies package structure before extraction.",
        next_action="Wait while the protected source is inspected.",
        project_id="project-1",
        guardian_protected=True,
    )


def test_live_console_preserves_truthful_mission_lifecycle(tmp_path) -> None:
    store = LiveConsoleEventStore(tmp_path)
    started = _start(store)

    running = store.progress(
        started.mission_id,
        42,
        summary="Reading bounded container metadata.",
    )
    finished = store.finish(
        started.mission_id,
        MissionState.SUCCEEDED,
        summary="Firmware inspection completed.",
        explanation="The inspection report was written and source-bound.",
        next_action="Review Device DNA and the Capability Map.",
        confidence=MissionConfidence.HIGH,
        evidence_refs=("projects/project-1/inspection-report.json",),
    )

    events = store.list_recent()
    assert events == (finished, running)
    assert events[0].progress_percent == 100
    assert events[0].state is MissionState.SUCCEEDED
    assert events[1].progress_percent == 42
    assert events[1].state is MissionState.RUNNING
    assert events[0].guardian_protected
    assert "serial" not in store.path.read_text(encoding="utf-8").casefold()


def test_live_console_rejects_false_or_invalid_state_transitions(tmp_path) -> None:
    store = LiveConsoleEventStore(tmp_path)
    started = _start(store)
    store.progress(started.mission_id, 60)

    with pytest.raises(LiveConsoleStoreError, match="backwards"):
        store.progress(started.mission_id, 20)
    with pytest.raises(LiveConsoleStoreError, match="terminal state"):
        store.finish(
            started.mission_id,
            MissionState.INFORMATION,
            summary="Not a terminal result.",
            explanation="No outcome exists.",
            next_action="Continue.",
        )
    with pytest.raises(LiveConsoleStoreError, match="No running"):
        store.progress("missing-mission", 10)


def test_live_console_notes_dedupe_and_preserve_unconfirmed_evidence(tmp_path) -> None:
    store = LiveConsoleEventStore(tmp_path)
    first = store.note(
        source="Device DNA",
        stage="capability-map",
        title="Device DNA compiled",
        summary="Unknown firmware capabilities remain unconfirmed.",
        explanation="ROMVERSE did not find enough exact evidence to claim support.",
        next_action="Import exact firmware evidence or connect the matching device.",
        state=MissionState.ATTENTION,
        confidence=MissionConfidence.UNCONFIRMED,
        project_id="project-2",
        evidence_refs=("projects/project-2/device-dna.romverse",),
        dedupe_key="dna-project-2-digest",
    )
    second = store.note(
        source="Device DNA",
        stage="capability-map",
        title="Device DNA compiled",
        summary="Unknown firmware capabilities remain unconfirmed.",
        explanation="ROMVERSE did not find enough exact evidence to claim support.",
        next_action="Import exact firmware evidence or connect the matching device.",
        state=MissionState.ATTENTION,
        confidence=MissionConfidence.UNCONFIRMED,
        project_id="project-2",
        evidence_refs=("projects/project-2/device-dna.romverse",),
        dedupe_key="dna-project-2-digest",
    )

    assert second == first
    assert store.list_recent() == (first,)


def test_live_console_rejects_private_or_escaping_evidence_references(tmp_path) -> None:
    store = LiveConsoleEventStore(tmp_path)
    common = dict(
        source="Nexus",
        stage="test",
        title="Evidence check",
        summary="Testing safe evidence references.",
        explanation="Private values do not belong in the console.",
        next_action="Correct the reference.",
    )
    with pytest.raises(LiveConsoleStoreError, match="workspace"):
        store.note(**common, evidence_refs=("../private.txt",))
    with pytest.raises(LiveConsoleStoreError, match="credentials"):
        store.note(**common, evidence_refs=("logs/token=private",))


def test_live_console_detects_ledger_tampering(tmp_path) -> None:
    store = LiveConsoleEventStore(tmp_path)
    _start(store)
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    payload["events"][0]["summary"] = "Fabricated success"
    store.path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(LiveConsoleStoreError, match="digest mismatch"):
        store.list_recent()
