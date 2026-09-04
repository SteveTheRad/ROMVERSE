import hashlib
import json
import os
from importlib.resources import files
from pathlib import Path

import pytest

from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.drafts import DevicePackDraftService
from romverse.device_packs.registry import DevicePackRegistry
from romverse.device_packs.requirements import ProjectSourceRequirements


def _request() -> dict[str, object]:
    return {
        "format": "romverse.device-pack-draft-request",
        "schema_version": 1,
        "pack_id": "example.model.identity",
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


def test_exact_model_draft_is_content_addressed_and_forces_all_actions_locked(tmp_path) -> None:
    exported = DevicePackDraftService().export(_request(), tmp_path)
    payload = exported.output_path.read_bytes()
    document = json.loads(payload)

    assert hashlib.sha256(payload).hexdigest() == exported.sha256
    assert exported.sha256[:12] in exported.output_path.name
    assert document["publication_status"] == "draft"
    assert document["capabilities"][0]["status"] == "limited"
    assert document["capabilities"][0]["scope"] == "evidence_only"
    assert all(item["scope"] == "locked" for item in document["capabilities"][1:])
    assert "Execution authority is NONE" in " ".join(document["notes"])


def test_draft_cannot_activate_even_if_manually_added_to_integrity_index(tmp_path) -> None:
    exported = DevicePackDraftService().export(_request(), tmp_path)
    root = tmp_path / "registry"
    root.mkdir()
    target = root / "example.json"
    target.write_bytes(exported.output_path.read_bytes())
    (root / "index.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "packs": [{"file": target.name, "sha256": exported.sha256}],
            }
        ),
        encoding="utf-8",
    )

    registry = DevicePackRegistry.load(root)

    assert registry.packs == ()
    assert len(registry.issues) == 1
    assert "drafts cannot activate" in registry.issues[0].reason


def test_draft_rejects_wildcards_unknown_fields_and_unsafe_sources() -> None:
    service = DevicePackDraftService()
    wildcard = _request()
    wildcard["match"]["model_patterns"] = ["*"]
    with pytest.raises(ValueError, match="wildcard"):
        service.build_document(wildcard)

    unknown = _request()
    unknown["flash_enabled"] = True
    with pytest.raises(ValueError, match="unsupported draft request fields"):
        service.build_document(unknown)

    unsafe = _request()
    unsafe["knowledge_sources"][0]["url"] = "http://example.com/device"
    with pytest.raises(ValueError, match="knowledge source URL"):
        service.build_document(unsafe)

    unsafe_identity = _request()
    unsafe_identity["pack_id"] = "../../escape"
    with pytest.raises(ValueError, match="unsafe pack id"):
        service.build_document(unsafe_identity)


def test_example_request_remains_accepted() -> None:
    path = Path("docs/device-pack-draft-request.example.json")
    request = DevicePackDraftService().load_request(path)
    document = DevicePackDraftService().build_document(request)

    assert document["pack_id"] == "example.model.identity"


def test_existing_published_builtins_remain_compatible() -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))

    assert registry.issues == ()
    assert registry.packs


def test_connected_device_request_is_private_exact_and_inherits_only_reviewed_sources() -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    device = AndroidDevice(
        "private-serial-that-must-not-appear",
        DeviceState.DEVICE,
        manufacturer="Google",
        model="Pixel 9 Pro",
        product="caiman",
        codename="caiman",
    )
    pack = registry.resolve(device).pack
    assert pack is not None

    request = DevicePackDraftService().request_from_device(pack, device)
    encoded = json.dumps(request)
    document = DevicePackDraftService().build_document(request)

    assert request["match"] == {
        "manufacturers": ["Google"],
        "model_patterns": ["Pixel 9 Pro"],
        "product_patterns": ["caiman"],
    }
    assert request["knowledge_sources"]
    assert "private-serial" not in encoded
    assert "execution" not in request
    assert document["publication_status"] == "draft"
    assert document["capabilities"][0]["status"] == "limited"
    assert all(capability["scope"] == "locked" for capability in document["capabilities"][1:])


def test_project_source_draft_binds_local_evidence_and_lists_every_flash_contract() -> None:
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    device = AndroidDevice(
        "private-serial-that-must-not-appear",
        DeviceState.DEVICE,
        brand="Xiaomi",
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        product="popsicle",
        codename="popsicle",
    )
    pack = next(item for item in registry.packs if item.pack_id == "xiaomi.hyperos")
    assert pack is not None
    source = ProjectSourceRequirements(
        "current-hyperos-source",
        "Current HyperOS source",
        "a" * 64,
        "xiaomi.hyperos",
        "ota-payload",
        "b" * 64,
        "c" * 64,
        "project-local-build-evidence-only",
        "Xiaomi",
        "popsicle",
        "OS4.0.0.25.XPBCNXM",
        58,
        ("Python", "Payload Dumper", "AVBTool"),
    )

    request = DevicePackDraftService().request_from_project_source(pack, device, source)
    document = DevicePackDraftService().build_document(request)
    encoded = json.dumps(document)

    assert document["publication_status"] == "draft"
    assert document["draft_context"]["source_sha256"] == "a" * 64
    assert document["draft_context"]["source_kind"] == "ota-payload"
    assert document["draft_context"]["partition_count"] == 58
    assert document["draft_context"]["execution_authority"] == "none"
    assert document["draft_context"]["phone_action_allowed"] is False
    assert set(document["draft_context"]["missing_flash_contracts"]) == set(
        DevicePackDraftService.MISSING_FLASH_CONTRACTS
    )
    assert "private-serial" not in encoded

    mismatched = ProjectSourceRequirements(
        source.project_id,
        source.project_name,
        source.source_sha256,
        source.device_pack_id,
        source.source_kind,
        source.blueprint_digest,
        source.plan_digest,
        source.authority,
        source.manufacturer,
        "different-device",
        source.build_id,
        source.partition_count,
        source.required_tools,
    )
    with pytest.raises(ValueError, match="does not match"):
        DevicePackDraftService().request_from_project_source(pack, device, mismatched)


def test_draft_storage_is_private_and_rejects_linked_inputs_and_directories(tmp_path) -> None:
    service = DevicePackDraftService()
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request()), encoding="utf-8")
    linked_request = tmp_path / "linked-request.json"
    linked_request.symlink_to(request_path)
    with pytest.raises(ValueError, match="unsafe or invalid"):
        service.load_request(linked_request)

    output_dir = tmp_path / "safe" / "drafts"
    exported = service.export(_request(), output_dir, boundary=tmp_path)
    if os.name != "nt":
        assert exported.output_path.stat().st_mode & 0o777 == 0o600
        assert output_dir.stat().st_mode & 0o777 == 0o700

    outside = tmp_path / "outside"
    outside.mkdir()
    linked_output = tmp_path / "linked-output"
    linked_output.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="could not be preserved safely"):
        service.export(_request(), linked_output, boundary=tmp_path)
    assert list(outside.iterdir()) == []
