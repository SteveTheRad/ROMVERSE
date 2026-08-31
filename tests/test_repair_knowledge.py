from romverse.repair.knowledge import knowledge_for, search_knowledge
from romverse.repair.templates import RepairConcern


def test_every_repair_concern_has_offline_playbook() -> None:
    for concern in RepairConcern:
        entry = knowledge_for(concern)
        assert entry.overview
        assert entry.likely_causes
        assert entry.evidence_to_collect
        assert entry.recommended_steps
        assert entry.risk_note
        assert entry.safe_automation


def test_repair_knowledge_search_is_case_insensitive() -> None:
    results = search_knowledge("USB")
    assert results
    assert results[0].concern is RepairConcern.USB_ADB


def test_repair_knowledge_empty_search_returns_full_catalog() -> None:
    assert len(search_knowledge("")) == len(tuple(RepairConcern))
