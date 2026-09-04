from __future__ import annotations

import json
import stat
from dataclasses import replace
from pathlib import Path

from romverse.device_packs.contributions import DevicePackContributionReport
from romverse.device_packs.drafts import DevicePackDraftService
from romverse.device_packs.foundry import (
    DevicePackFoundryInventory,
    DevicePackFoundryService,
    FoundryEvidenceState,
    FoundryIdentityConflict,
    FoundrySimulationEvidence,
)
from romverse.device_packs.promotion import DevicePackPromotionService


def _request() -> dict[str, object]:
    return {
        "format": "romverse.device-pack-draft-request",
        "schema_version": 1,
        "pack_id": "example.promotion-device",
        "version": "0.1.0",
        "display_name": "Example Promotion Device",
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
                "verified_on": "2026-09-01",
            }
        ],
        "notes": ["Read-only draft evidence."],
    }


def _inventory(tmp_path: Path) -> DevicePackFoundryInventory:
    drafts = tmp_path / "device_pack_drafts"
    DevicePackDraftService().export(_request(), drafts, boundary=tmp_path)
    return DevicePackFoundryService().inspect(drafts, boundary=tmp_path)


def _contribution(
    revision,
    role: str,
    scopes: tuple[str, ...],
    digest: str,
) -> DevicePackContributionReport:
    return DevicePackContributionReport(
        True,
        f"example.{role}",
        role,
        revision.pack_id,
        revision.version,
        revision.sha256,
        scopes,
        "9" * 64,
        "2026-09-01T00:00:00+00:00",
        "2026-12-01T00:00:00+00:00",
        digest,
        "verified",
    )


def _fully_evidenced(inventory: DevicePackFoundryInventory):
    revision = inventory.revisions[0]
    simulation = FoundrySimulationEvidence(
        "d" * 64,
        revision.pack_id,
        True,
        0,
        0,
        12,
        92,
        True,
        0,
        "none",
    )
    return replace(
        revision,
        project_id="project-one",
        source_sha256="a" * 64,
        build_id="EXAMPLE.1",
        partition_count=42,
        source_avb_attached=True,
        device_dna_attached=True,
        device_dna_profile_digest="b" * 64,
        device_dna_fact_count=18,
        simulation=simulation,
        missing_flash_contracts=(),
        lanes=tuple(
            replace(lane, state=FoundryEvidenceState.EVIDENCED)
            for lane in revision.lanes
        ),
    )


def test_promotion_review_records_real_blockers_without_runtime_authority(
    tmp_path: Path,
) -> None:
    inventory = _inventory(tmp_path)
    revision = inventory.revisions[0]

    review = DevicePackPromotionService().assess(revision, inventory, ())

    assert not review.eligible_for_governed_review
    assert review.status == "blocked"
    assert review.passed_count == 2
    assert review.blocker_count == 7
    assert review.publication_authority == "none"
    assert not review.production_registry_changed
    assert not review.runtime_promotion_supported
    checks = {check.check_id: check for check in review.checks}
    assert checks["exact-revision"].passed
    assert checks["identity-conflicts"].passed
    assert not checks["source-device-dna"].passed
    assert not checks["flash-rollback-contract"].passed
    assert not checks["physical-device-test"].passed


def test_only_complete_independent_evidence_reaches_governed_review_not_promotion(
    tmp_path: Path,
) -> None:
    original_inventory = _inventory(tmp_path)
    revision = _fully_evidenced(original_inventory)
    inventory = replace(original_inventory, revisions=(revision,))
    manufacturer = _contribution(
        revision,
        "manufacturer",
        ("factory-firmware", "identity", "partitions-avb", "variant"),
        "e" * 64,
    )
    expert = _contribution(
        revision,
        "qualified-expert",
        ("flash-rollback-contract", "physical-device-test", "simulation"),
        "f" * 64,
    )

    review = DevicePackPromotionService().assess(
        revision,
        inventory,
        (manufacturer, expert),
    )

    assert review.eligible_for_governed_review
    assert review.status == "eligible-for-governed-review"
    assert review.passed_count == len(review.checks) == 9
    assert review.blocker_count == 0
    assert review.contribution_envelope_sha256s == ("e" * 64, "f" * 64)
    assert review.publication_authority == "none"
    assert not review.production_registry_changed
    assert not review.runtime_promotion_supported

    conflict = FoundryIdentityConflict(
        "model",
        "example phone 1",
        (revision.pack_id, "example.competing-pack"),
        (revision.sha256, "0" * 64),
        "Reconcile evidence.",
    )
    conflicted = DevicePackPromotionService().assess(
        revision,
        replace(inventory, conflicts=(conflict,)),
        (manufacturer, expert),
    )
    assert not conflicted.eligible_for_governed_review
    assert conflicted.blocker_count == 1
    assert not next(
        check for check in conflicted.checks if check.check_id == "identity-conflicts"
    ).passed


def test_promotion_review_export_is_private_content_addressed_and_explicitly_non_promoting(
    tmp_path: Path,
) -> None:
    inventory = _inventory(tmp_path)
    review = DevicePackPromotionService().assess(inventory.revisions[0], inventory, ())
    service = DevicePackPromotionService()

    exported = service.export(
        review,
        tmp_path / "device_pack_promotion_reviews",
        boundary=tmp_path,
    )
    document = json.loads(exported.output_path.read_bytes())

    assert exported.output_path.name.endswith(".promotion-review.json")
    assert document["format"] == service.FORMAT
    assert document["report_digest"] == review.report_digest
    assert document["status"] == "blocked"
    assert document["publication_authority"] == "none"
    assert document["production_registry_changed"] is False
    assert document["runtime_promotion_supported"] is False
    assert stat.S_IMODE(exported.output_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(exported.output_path.stat().st_mode) == 0o600
