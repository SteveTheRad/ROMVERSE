from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

import pytest

from romverse.device.dna import DeviceDnaService
from romverse.device_packs.drafts import DevicePackDraftService
from romverse.device_packs.foundry import (
    DevicePackFoundryService,
    FoundryEvidenceState,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.device_packs.requirements import ProjectSourceRequirements
from romverse.rom.simulation import RomSimulationService
from tests.test_device_dna import _device as _dna_device
from tests.test_device_dna import _project as _dna_project


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


def test_foundry_illuminates_sealed_device_dna_without_treating_region_as_matcher(
    tmp_path: Path,
) -> None:
    store, dna_registry, project, inspection = _dna_project(tmp_path)
    device = _dna_device()
    profile = DeviceDnaService(store, dna_registry).refresh(
        project.project_id,
        device,
        inspection,
    )
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    seed = next(pack for pack in registry.packs if pack.pack_id == "xiaomi.hyperos")
    source = ProjectSourceRequirements(
        project.project_id,
        project.name,
        project.original.sha256,
        "xiaomi.hyperos",
        "ota-payload",
        "b" * 64,
        "c" * 64,
        "project-local-build-evidence-only",
        "Xiaomi",
        "popsicle",
        "OS4.0.0.23.XPBCNXM",
        len(profile.partitions),
        ("Python", "Payload Dumper", "AVBTool"),
    )
    drafts = store.workspace / "device_pack_drafts"
    service = DevicePackDraftService()
    request = service.request_from_project_source(seed, device, source, device_dna=profile)
    service.export(
        request,
        drafts,
        boundary=store.workspace,
    )
    simulation = RomSimulationService(store, dna_registry).rehearse(
        project.project_id,
        device,
    )
    assert not simulation.successful

    inventory = DevicePackFoundryService().inspect(drafts, boundary=store.workspace)

    revision = inventory.revisions[0]
    assert revision.version == "0.3.0"
    assert revision.device_dna_attached
    assert revision.device_dna_profile_digest == profile.profile_digest
    assert revision.device_dna_fact_count > 10
    assert revision.device_dna_partition_count == 1
    assert revision.device_dna_region == "China"
    assert revision.lanes[1].state is FoundryEvidenceState.EVIDENCED
    assert "observation only" in revision.lanes[1].detail
    assert revision.lanes[3].state is FoundryEvidenceState.PARTIAL
    assert revision.simulation is not None
    assert revision.simulation.receipt_digest == simulation.receipt_digest
    assert not revision.simulation.successful
    assert revision.simulation.blocker_count > 0
    assert revision.lanes[5].state is FoundryEvidenceState.PARTIAL
    assert "resolve them" in revision.lanes[5].detail
    assert revision.evidenced_lane_count == 3
    assert revision.execution_authority == "none"

    simulation_path = (
        store.projects_root / project.project_id / RomSimulationService.RECEIPT_NAME
    )
    changed_simulation = json.loads(simulation_path.read_text(encoding="utf-8"))
    changed_simulation["confidence_percent"] = 92
    simulation_path.write_text(json.dumps(changed_simulation), encoding="utf-8")
    without_simulation = DevicePackFoundryService().inspect(
        drafts,
        boundary=store.workspace,
    ).revisions[0]
    assert without_simulation.simulation is None
    assert without_simulation.lanes[5].state is FoundryEvidenceState.PENDING

    forged = json.loads(json.dumps(request))
    region = next(
        fact
        for fact in forged["device_dna_evidence"]["facts"]
        if fact["fact_id"] == "software.region"
    )
    region["value"] = "Forged region"
    service.export(forged, drafts, boundary=store.workspace)
    reloaded = DevicePackFoundryService().inspect(drafts, boundary=store.workspace)
    assert len(reloaded.revisions) == 1
    assert len(reloaded.issues) == 1
    assert "sealed workspace profile" in reloaded.issues[0].reason


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
