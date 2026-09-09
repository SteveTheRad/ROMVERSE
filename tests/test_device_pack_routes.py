from __future__ import annotations

import json
import stat
from importlib.resources import files
from pathlib import Path

import pytest

from romverse.device.dna import DeviceDnaService
from romverse.device_packs.drafts import DevicePackDraftService
from romverse.device_packs.foundry import DevicePackFoundryService
from romverse.device_packs.registry import DevicePackRegistry
from romverse.device_packs.requirements import ProjectSourceRequirements
from romverse.device_packs.routes import DevicePackRouteBlueprintService, FoundryRouteState
from tests.test_device_dna import _device as _dna_device
from tests.test_device_dna import _project as _dna_project


def _sealed_revision(tmp_path: Path):
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
    draft_service = DevicePackDraftService()
    request = draft_service.request_from_project_source(
        seed,
        device,
        source,
        device_dna=profile,
    )
    drafts = store.workspace / "device_pack_drafts"
    draft_service.export(request, drafts, boundary=store.workspace)
    revision = (
        DevicePackFoundryService()
        .inspect(
            drafts,
            boundary=store.workspace,
        )
        .revisions[0]
    )
    return store, revision


def test_route_blueprint_records_measured_operational_facts_without_inventing_routes(
    tmp_path: Path,
) -> None:
    store, revision = _sealed_revision(tmp_path)

    blueprint = DevicePackRouteBlueprintService().derive(
        revision,
        boundary=store.workspace,
    )

    observations = {item.fact_id: item for item in blueprint.observations}
    assert observations["bootloader.state"].value == "unlocked"
    assert observations["boot.active_slot"].value == "a"
    assert observations["partition.ab_scheme"].value == "Virtual A/B"
    assert "Dynamic partitions" in observations["partition.architecture"].value
    assert observations["security.verified_boot"].value == "orange"
    assert observations["capability.fastboot"].value == "fastbootd reported by Android"
    assert observations["partition.source_count"].value == "1"
    assert blueprint.minimum_identity_facts_present
    assert len(blueprint.routes) == 4
    assert blueprint.routes[0].state is FoundryRouteState.NEEDS_EVIDENCE
    assert all(route.state is FoundryRouteState.BLOCKED for route in blueprint.routes[1:])
    assert blueprint.blocked_route_count == 3
    assert not blueprint.bootloader_relock_allowed
    assert not blueprint.automatic_device_actions
    assert blueprint.execution_authority == "none"
    assert any(
        "target and recovery slots cannot be inferred" in item
        for item in blueprint.operational_characteristics
    )


def test_route_blueprint_export_is_private_content_addressed_and_contains_no_command(
    tmp_path: Path,
) -> None:
    store, revision = _sealed_revision(tmp_path)
    service = DevicePackRouteBlueprintService()
    blueprint = service.derive(revision, boundary=store.workspace)

    exported = service.export(
        blueprint,
        store.workspace / "device_pack_route_blueprints",
        boundary=store.workspace,
    )
    payload = exported.output_path.read_bytes()
    document = json.loads(payload)

    assert exported.output_path.name.endswith(".route-blueprint.json")
    assert document["format"] == service.FORMAT
    assert document["blueprint_digest"] == blueprint.blueprint_digest
    assert document["automatic_device_actions"] is False
    assert document["execution_authority"] == "none"
    assert document["bootloader_relock_allowed"] is False
    assert b"PRIVATE-SERIAL" not in payload
    assert b'"command"' not in payload
    assert stat.S_IMODE(exported.output_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(exported.output_path.stat().st_mode) == 0o600


def test_route_blueprint_rejects_identity_only_or_changed_draft_bytes(tmp_path: Path) -> None:
    store, revision = _sealed_revision(tmp_path)
    service = DevicePackRouteBlueprintService()
    revision.path.write_bytes(revision.path.read_bytes().replace(b"DRAFT ONLY", b"DRAFT FAKE"))

    with pytest.raises(ValueError, match="exact draft revision"):
        service.derive(revision, boundary=store.workspace)

    model_workspace = tmp_path / "identity-only"
    model_workspace.mkdir()
    request = {
        "format": "romverse.device-pack-draft-request",
        "schema_version": 1,
        "pack_id": "example.identity-only",
        "version": "0.1.0",
        "display_name": "Example Identity Only",
        "priority": 220,
        "match": {
            "manufacturers": ["Example"],
            "model_patterns": ["Example One"],
            "product_patterns": ["example_one"],
        },
        "knowledge_sources": [
            {
                "source_id": "example.official",
                "label": "Official reference",
                "url": "https://example.com/device",
                "authority": "Example",
                "scope": "Identity",
                "verified_on": "2026-09-01",
            }
        ],
        "notes": [],
    }
    drafts = model_workspace / "device_pack_drafts"
    DevicePackDraftService().export(request, drafts, boundary=model_workspace)
    identity_revision = (
        DevicePackFoundryService()
        .inspect(
            drafts,
            boundary=model_workspace,
        )
        .revisions[0]
    )
    with pytest.raises(ValueError, match="exact-source draft"):
        service.derive(identity_revision, boundary=model_workspace)
