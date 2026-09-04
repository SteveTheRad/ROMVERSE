from __future__ import annotations

import json
import stat
from dataclasses import replace
from pathlib import Path

import pytest

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


def _policy_revision_with_all_lanes(inventory: DevicePackFoundryInventory):
    """Synthetic policy input; this fixture is not physical-device validation."""
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
        lanes=tuple(replace(lane, state=FoundryEvidenceState.EVIDENCED) for lane in revision.lanes),
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


def test_manufacturer_facts_and_expert_validation_reach_review_without_promotion(
    tmp_path: Path,
) -> None:
    original_inventory = _inventory(tmp_path)
    revision = _policy_revision_with_all_lanes(original_inventory)
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


def test_qualified_expert_can_cover_every_scope_without_manufacturer_participation(
    tmp_path: Path,
) -> None:
    original_inventory = _inventory(tmp_path)
    revision = _policy_revision_with_all_lanes(original_inventory)
    inventory = replace(original_inventory, revisions=(revision,))
    service = DevicePackPromotionService()
    expert = _contribution(
        revision,
        "qualified-expert",
        tuple(sorted(service.FACTUAL_SCOPES | service.EXPERT_SCOPES)),
        "f" * 64,
    )

    review = service.assess(revision, inventory, (expert,))

    assert review.eligible_for_governed_review
    assert review.blocker_count == 0
    assert review.contribution_envelope_sha256s == (expert.envelope_sha256,)
    assert review.publication_authority == "none"
    assert not review.production_registry_changed
    assert not review.runtime_promotion_supported


@pytest.mark.parametrize(
    "missing_scope,failed_check",
    [
        ("identity", "factual-contribution"),
        ("variant", "factual-contribution"),
        ("factory-firmware", "factual-contribution"),
        ("partitions-avb", "factual-contribution"),
        ("flash-rollback-contract", "expert-contribution"),
        ("simulation", "expert-contribution"),
        ("physical-device-test", "expert-contribution"),
    ],
)
def test_expert_route_still_requires_every_declared_scope(
    tmp_path: Path,
    missing_scope: str,
    failed_check: str,
) -> None:
    original_inventory = _inventory(tmp_path)
    revision = _policy_revision_with_all_lanes(original_inventory)
    inventory = replace(original_inventory, revisions=(revision,))
    service = DevicePackPromotionService()
    scopes = service.FACTUAL_SCOPES | service.EXPERT_SCOPES
    expert = _contribution(
        revision,
        "qualified-expert",
        tuple(sorted(scopes - {missing_scope})),
        "f" * 64,
    )

    review = service.assess(revision, inventory, (expert,))
    failed = tuple(check for check in review.checks if not check.passed)

    assert not review.eligible_for_governed_review
    assert len(failed) == 1
    assert failed[0].check_id == failed_check
    assert missing_scope in failed[0].evidence


@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"pack_id": "example.other-device"},
        {"pack_version": "9.0.0"},
        {"draft_sha256": "0" * 64},
        {"verified": False},
        {"contributor_role": "community-member"},
        {"publication_authority": "production"},
        {"production_registry_changed": True},
        {"review_required": False},
    ],
)
def test_unverified_or_wrong_revision_contributions_cannot_complete_evidence(
    tmp_path: Path,
    invalid_fields: dict[str, object],
) -> None:
    original_inventory = _inventory(tmp_path)
    revision = _policy_revision_with_all_lanes(original_inventory)
    inventory = replace(original_inventory, revisions=(revision,))
    service = DevicePackPromotionService()
    expert = _contribution(
        revision,
        "qualified-expert",
        tuple(sorted(service.FACTUAL_SCOPES | service.EXPERT_SCOPES)),
        "f" * 64,
    )

    review = service.assess(revision, inventory, (replace(expert, **invalid_fields),))

    assert not review.eligible_for_governed_review
    assert review.contribution_envelope_sha256s == ()
    assert {check.check_id for check in review.checks if not check.passed} == {
        "factual-contribution",
        "expert-contribution",
    }


def test_contribution_claims_do_not_replace_measured_validation(
    tmp_path: Path,
) -> None:
    inventory = _inventory(tmp_path)
    revision = inventory.revisions[0]
    service = DevicePackPromotionService()
    expert = _contribution(
        revision,
        "qualified-expert",
        tuple(sorted(service.FACTUAL_SCOPES | service.EXPERT_SCOPES)),
        "f" * 64,
    )

    review = service.assess(revision, inventory, (expert,))
    checks = {check.check_id: check for check in review.checks}

    assert checks["factual-contribution"].passed
    assert checks["expert-contribution"].passed
    assert not review.eligible_for_governed_review
    assert not checks["source-device-dna"].passed
    assert not checks["partitions-avb"].passed
    assert not checks["flash-rollback-contract"].passed
    assert not checks["simulation"].passed
    assert not checks["physical-device-test"].passed


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
