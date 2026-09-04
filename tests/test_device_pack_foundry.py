from __future__ import annotations

import json
from pathlib import Path

import pytest

from romverse.device_packs.drafts import DevicePackDraftService
from romverse.device_packs.foundry import (
    DevicePackFoundryService,
    FoundryEvidenceState,
)


def _request(pack_id: str = "example.model.identity") -> dict[str, object]:
    return {
        "format": "romverse.device-pack-draft-request",
        "schema_version": 1,
        "pack_id": pack_id,
        "version": "0.1.0",
        "display_name": "Example Model / Identity",
        "priority": 220,
        "match": {
            "manufacturers": ["Example OEM"],
            "model_patterns": ["Example Phone 1"],
            "product_patterns": ["example_product"],
        },
        "knowledge_sources": [
            {
                "source_id": "example.official-device",
                "label": "Official device reference",
                "url": "https://example.com/device",
                "authority": "Example OEM",
                "scope": "Published identity",
                "verified_on": "2026-08-29",
            }
        ],
        "notes": ["Read-only draft evidence."],
    }


def _source_request(pack_id: str = "example.model.identity") -> dict[str, object]:
    request = _request(pack_id)
    request["source_evidence"] = {
        "project_id": "project-one",
        "source_sha256": "a" * 64,
        "source_kind": "ota-payload",
        "blueprint_digest": "b" * 64,
        "plan_digest": "c" * 64,
        "authority": "project-local-build-evidence-only",
        "manufacturer": "Example OEM",
        "codename": "example_product",
        "build_id": "EXAMPLE.1",
        "partition_count": 42,
        "required_tools": ["Python", "Payload Dumper", "AVBTool"],
    }
    return request


def test_foundry_indexes_model_draft_as_experimental_without_registry_authority(
    tmp_path: Path,
) -> None:
    drafts = tmp_path / "device_pack_drafts"
    DevicePackDraftService().export(_request(), drafts, boundary=tmp_path)

    inventory = DevicePackFoundryService().inspect(drafts, boundary=tmp_path)

    assert inventory.pack_count == 1
    assert inventory.conflicts == ()
    assert inventory.issues == ()
    assert inventory.publication_authority == "none"
    assert not inventory.production_registry_changed
    revision = inventory.revisions[0]
    assert revision.publication_status == "experimental-draft"
    assert revision.execution_authority == "none"
    assert not revision.source_bound
    assert [lane.state for lane in revision.lanes] == [
        FoundryEvidenceState.EVIDENCED,
        FoundryEvidenceState.PARTIAL,
        FoundryEvidenceState.PENDING,
        FoundryEvidenceState.PENDING,
        FoundryEvidenceState.PENDING,
        FoundryEvidenceState.PENDING,
    ]


def test_foundry_promotes_only_measured_source_lanes_not_flash_authority(
    tmp_path: Path,
) -> None:
    drafts = tmp_path / "device_pack_drafts"
    exported = DevicePackDraftService().export(
        _source_request(),
        drafts,
        boundary=tmp_path,
    )

    inventory = DevicePackFoundryService().inspect(drafts, boundary=tmp_path)

    revision = inventory.revisions[0]
    assert revision.path == exported.output_path
    assert revision.source_bound
    assert revision.source_sha256 == "a" * 64
    assert revision.build_id == "EXAMPLE.1"
    assert revision.partition_count == 42
    assert not revision.source_avb_attached
    assert revision.lanes[2].state is FoundryEvidenceState.EVIDENCED
    assert revision.lanes[3].state is FoundryEvidenceState.PARTIAL
    assert revision.lanes[4].state is FoundryEvidenceState.PENDING
    assert revision.execution_authority == "none"


def test_foundry_detects_distinct_pack_lineages_claiming_the_same_identity(
    tmp_path: Path,
) -> None:
    drafts = tmp_path / "device_pack_drafts"
    service = DevicePackDraftService()
    service.export(_request("example.first"), drafts, boundary=tmp_path)
    service.export(_request("example.second"), drafts, boundary=tmp_path)

    inventory = DevicePackFoundryService().inspect(drafts, boundary=tmp_path)

    assert inventory.pack_count == 2
    assert len(inventory.conflicts) == 2
    assert {conflict.identity_kind for conflict in inventory.conflicts} == {
        "model",
        "product",
    }
    assert all(
        conflict.pack_ids == ("example.first", "example.second")
        for conflict in inventory.conflicts
    )
    assert all("Keep every matching draft experimental" in item.safest_action for item in inventory.conflicts)


def test_foundry_keeps_multiple_revisions_of_one_pack_as_version_history(
    tmp_path: Path,
) -> None:
    drafts = tmp_path / "device_pack_drafts"
    service = DevicePackDraftService()
    service.export(_request(), drafts, boundary=tmp_path)
    service.export(_source_request(), drafts, boundary=tmp_path)

    inventory = DevicePackFoundryService().inspect(drafts, boundary=tmp_path)
    best = inventory.best_for_identity(
        "Example OEM",
        "Example Phone 1",
        "example_product",
        "example_product",
    )

    assert len(inventory.revisions) == 2
    assert inventory.pack_count == 1
    assert inventory.conflicts == ()
    assert best is not None
    assert best.source_bound


def test_foundry_rejects_reformatted_tampered_and_linked_drafts(
    tmp_path: Path,
) -> None:
    drafts = tmp_path / "device_pack_drafts"
    exported = DevicePackDraftService().export(_request(), drafts, boundary=tmp_path)
    document = json.loads(exported.output_path.read_text(encoding="utf-8"))
    exported.output_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    inventory = DevicePackFoundryService().inspect(drafts, boundary=tmp_path)

    assert inventory.revisions == ()
    assert len(inventory.issues) == 1
    assert "canonical exported artifact" in inventory.issues[0].reason

    linked = tmp_path / "linked-drafts"
    linked.symlink_to(drafts, target_is_directory=True)
    with pytest.raises(ValueError, match="unsafe|outside"):
        DevicePackFoundryService().inspect(linked, boundary=tmp_path)
