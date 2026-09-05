from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import replace

from romverse.device.dna import DeviceDnaService
from romverse.nexus.compatibility import CompatibilityMatrixService
from romverse.nexus.planning import (
    FlashMode,
    ImpactLevel,
    InsightExporter,
    NexusObjective,
    NexusPlanner,
    NexusPlanStatus,
    RouteStageState,
)
from tests.test_device_dna import _device, _project


def _evidence(tmp_path, *, exact=True, device=True):
    store, registry, project, report = _project(tmp_path, exact=exact)
    profile = DeviceDnaService(store, registry).refresh(
        project.project_id,
        _device() if device else None,
        report,
    )
    matrix = CompatibilityMatrixService(store).assess(profile)
    return store, profile, matrix


def test_nexus_build_plan_is_deterministic_guardian_review_not_execution(tmp_path) -> None:
    store, profile, matrix = _evidence(tmp_path)

    planner = NexusPlanner(store)
    plan = planner.plan(profile, matrix, NexusObjective.BUILD_ROM)

    assert plan.status is NexusPlanStatus.READY_FOR_GUARDIAN
    assert plan.ready_for_guardian_review
    assert not plan.execution_authorized
    assert not plan.bootloader_relock_permitted
    assert [stage.label for stage in plan.route] == [
        "Understand",
        "Research",
        "Nexus Plan",
        "Guardian Review",
        "Execute",
        "Nexus Verification",
    ]
    assert plan.route[3].state is RouteStageState.CURRENT
    assert plan.route[4].state is RouteStageState.UPCOMING
    assert any(
        item.area == "Connected phone" and item.impact is ImpactLevel.NONE
        for item in plan.predictions
    )
    assert planner.plans.load(profile.project_id) == plan
    path = store.projects_root / profile.project_id / planner.plans.NAME
    payload = json.loads(path.read_text())
    assert payload["schema_version"] == 2
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_pathfinder_blocks_unknown_route_without_guessing(tmp_path) -> None:
    store, profile, matrix = _evidence(tmp_path, exact=False, device=False)

    plan = NexusPlanner(store).plan(profile, matrix, NexusObjective.BUILD_ROM)

    assert plan.status is NexusPlanStatus.NEEDS_EVIDENCE
    assert plan.research_requirements
    assert plan.route[1].state is RouteStageState.CURRENT
    assert plan.route[3].state is RouteStageState.BLOCKED
    assert plan.route[4].state is RouteStageState.BLOCKED
    assert any(
        "exact compatibility evidence" in item or "will not infer" in item
        for item in plan.research_requirements
    )


def test_flash_route_requires_mode_backup_and_separate_guardian_evidence(tmp_path) -> None:
    store, profile, matrix = _evidence(tmp_path)

    undecided = NexusPlanner(store).plan(profile, matrix, NexusObjective.FLASH_DEVICE)
    assert undecided.status is NexusPlanStatus.NEEDS_EVIDENCE
    assert any(
        "Dirty flash or Flash and wipe data" in item for item in undecided.research_requirements
    )
    assert any("local backup" in item for item in undecided.guardian_requirements)
    assert any(item.area == "Bootloader state" for item in undecided.predictions)
    assert not undecided.bootloader_relock_permitted

    wipe = NexusPlanner(store).plan(
        profile,
        matrix,
        NexusObjective.FLASH_DEVICE,
        flash_mode=FlashMode.WIPE_DATA,
    )
    user_data = next(item for item in wipe.predictions if item.area == "User data")
    assert user_data.impact is ImpactLevel.CRITICAL
    assert "erase user data" in user_data.prediction
    assert wipe.status is NexusPlanStatus.NEEDS_EVIDENCE


def test_pathfinder_requests_flash_evidence_without_false_terminal_stop(tmp_path) -> None:
    store, profile, matrix = _evidence(tmp_path, exact=False, device=True)

    plan = NexusPlanner(store).plan(
        profile,
        matrix,
        NexusObjective.FLASH_DEVICE,
        flash_mode=FlashMode.DIRTY_FLASH,
    )

    assert matrix.decision("guardian_flash").status.value == "Unknown"
    assert plan.status is NexusPlanStatus.NEEDS_EVIDENCE
    assert any("Confirm Guardian flash" in item for item in plan.research_requirements)
    assert not any(item.startswith("Stop:") for item in plan.research_requirements)
    assert plan.route[1].state is RouteStageState.CURRENT
    assert plan.route[3].state is RouteStageState.BLOCKED
    assert plan.route[4].state is RouteStageState.BLOCKED
    assert not plan.execution_authorized
    assert not plan.bootloader_relock_permitted


def test_pathfinder_retains_stop_for_proven_device_source_mismatch(tmp_path) -> None:
    store, registry, project, report = _project(tmp_path)
    profile = DeviceDnaService(store, registry).refresh(
        project.project_id,
        _device(codename="wrong-device", product="wrong-device"),
        report,
    )
    matrix = CompatibilityMatrixService(store).assess(profile)

    plan = NexusPlanner(store).plan(
        profile,
        matrix,
        NexusObjective.FLASH_DEVICE,
        flash_mode=FlashMode.DIRTY_FLASH,
    )

    assert any(item.startswith("Stop:") for item in plan.research_requirements)
    assert plan.status is NexusPlanStatus.NEEDS_EVIDENCE
    assert not plan.execution_authorized


def test_root_route_uses_ascension_and_keeps_phone_unchanged_during_preparation(tmp_path) -> None:
    store, profile, matrix = _evidence(tmp_path)

    plan = NexusPlanner(store).plan(profile, matrix, NexusObjective.ROOT_ROM)

    assert any("Ascension Protocol" in item for item in plan.guardian_requirements)
    root_candidate = next(
        item for item in plan.predictions if item.area == "Boot or init_boot candidate"
    )
    assert "Magisk or KernelSU" in root_candidate.prediction
    phone = next(item for item in plan.predictions if item.area == "Connected phone")
    assert phone.impact is ImpactLevel.NONE
    assert "should not install, flash, unlock, wipe, or relock" in phone.prediction
    assert not plan.execution_authorized


def test_nexus_adaptation_links_to_current_plan_and_marks_route(tmp_path) -> None:
    store, profile, matrix = _evidence(tmp_path)
    planner = NexusPlanner(store)
    initial = planner.plan(profile, matrix, NexusObjective.BUILD_ROM)

    adapted = planner.adapt(
        initial,
        profile,
        matrix,
        reason="A fresh inspection added stronger container evidence.",
    )

    assert adapted.adaptation_of == initial.plan_id
    assert adapted.adaptation_reason.startswith("A fresh inspection")
    assert adapted.route[0].state is RouteStageState.ADAPTED
    assert planner.plans.load(profile.project_id) == adapted


def test_insight_export_is_redacted_and_never_grants_authority(tmp_path) -> None:
    store, profile, matrix = _evidence(tmp_path)
    plan = NexusPlanner(store).plan(profile, matrix, NexusObjective.BUILD_ROM)

    output = InsightExporter.export(plan, tmp_path / "exports" / "insight.json")
    text = output.read_text(encoding="utf-8")
    payload = json.loads(text)

    assert payload["format"] == "romverse.insight-report"
    assert payload["privacy"] == "redacted"
    assert payload["execution_authorized"] is False
    assert payload["bootloader_relock_permitted"] is False
    assert "PRIVATE-SERIAL" not in text
    assert "decision_timeline" in payload


def test_nexus_plan_tampering_invalidates_persisted_plan(tmp_path) -> None:
    store, profile, matrix = _evidence(tmp_path)
    planner = NexusPlanner(store)
    planner.plan(profile, matrix, NexusObjective.BUILD_ROM)
    path = store.projects_root / profile.project_id / planner.plans.NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["execution_authorized"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert planner.plans.load(profile.project_id) is None


def test_nexus_plan_rejects_redigested_route_changes_and_hostile_records(tmp_path) -> None:
    store, profile, matrix = _evidence(tmp_path)
    planner = NexusPlanner(store)
    planner.plan(profile, matrix, NexusObjective.BUILD_ROM)
    path = store.projects_root / profile.project_id / planner.plans.NAME
    original = path.read_bytes()

    payload = json.loads(original)
    payload["route"][4]["state"] = "complete"
    unsigned = {
        key: value for key, value in payload.items() if key not in {"format", "plan_digest"}
    }
    payload["plan_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert planner.plans.load(profile.project_id) is None

    payload = json.loads(original)
    payload["unexpected"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert planner.plans.load(profile.project_id) is None

    payload = json.loads(original)
    payload["route"][0]["unexpected"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert planner.plans.load(profile.project_id) is None

    payload = json.loads(original)
    payload["execution_authorized"] = "false"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert planner.plans.load(profile.project_id) is None

    path.write_bytes(b"{" + b" " * planner.plans.MAX_BYTES + b"}")
    assert planner.plans.load(profile.project_id) is None

    outside = tmp_path / "outside-nexus-plan.json"
    outside.write_bytes(original)
    path.unlink()
    path.symlink_to(outside)
    assert planner.plans.load(profile.project_id) is None
    assert outside.read_bytes() == original


def test_legacy_nexus_plan_is_readable_and_replanning_upgrades_schema(tmp_path) -> None:
    store, profile, matrix = _evidence(tmp_path)
    planner = NexusPlanner(store)
    planner.plan(profile, matrix, NexusObjective.BUILD_ROM)
    path = store.projects_root / profile.project_id / planner.plans.NAME
    payload = json.loads(path.read_text())
    payload["schema_version"] = 1
    unsigned = {
        key: value for key, value in payload.items() if key not in {"format", "plan_digest"}
    }
    payload["plan_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    path.write_text(json.dumps(payload), encoding="utf-8")

    legacy = planner.plans.load(profile.project_id)
    assert legacy is not None
    assert legacy.schema_version == 1

    upgraded = planner.plan(profile, matrix, NexusObjective.BUILD_ROM)

    assert upgraded.schema_version == 2
    assert json.loads(path.read_text())["schema_version"] == 2


def test_nexus_plan_invalidates_when_device_dna_changes(tmp_path) -> None:
    store, registry, project, report = _project(tmp_path)
    dna_service = DeviceDnaService(store, registry)
    profile = dna_service.refresh(project.project_id, _device(), report)
    matrix = CompatibilityMatrixService(store).assess(profile)
    planner = NexusPlanner(store)
    planner.plan(profile, matrix, NexusObjective.BUILD_ROM)

    changed = dna_service.refresh(
        project.project_id,
        replace(_device(), security_patch="2026-09-01"),
        report,
    )

    assert changed.profile_digest != profile.profile_digest
    assert planner.plans.load(project.project_id) is None
