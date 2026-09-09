from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace

from romverse.device.models import AndroidDevice, DeviceState
from romverse.infrastructure.provisioning import GENESIS_REQUIRED_TOOLS
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.guided import (
    STAGES,
    GuidedContext,
    GuidedMissionEngine,
    GuidedMissionState,
    GuidedMissionStore,
    GuidedStageStatus,
)


def test_source_integrity_stage_does_not_claim_publisher_provenance() -> None:
    stage = next(item for item in STAGES if item.stage_id == "provenance")

    assert stage.number == 3
    assert stage.short_title == "Source integrity"
    assert "publisher identity" in stage.explanation
    assert "signing-key trust" in stage.explanation
    assert "release channel" in stage.explanation
    assert "separately" in stage.recommendation

    assessment = GuidedMissionEngine().assess(
        GuidedContext(project_exists=True, original_imported=True, inspection_saved=True)
    )[2]
    assert assessment.status is GuidedStageStatus.COMPLETE
    assert "publisher provenance" in assessment.next_outcome
    assert "remain separate evidence" in assessment.next_outcome


def test_mission_starts_with_one_focused_action_and_locks_dependencies():
    assessments = GuidedMissionEngine().assess(GuidedContext())

    assert len(assessments) == 15
    assert assessments[0].status is GuidedStageStatus.READY
    assert assessments[1].status is GuidedStageStatus.LOCKED
    assert assessments[11].status is GuidedStageStatus.LOCKED
    assert GuidedMissionEngine.progress(assessments) == 0


def test_mission_reports_unauthorized_device_with_actionable_blocker():
    context = GuidedContext(
        project_exists=True,
        original_imported=True,
        inspection_saved=True,
        working_copy_ready=True,
        working_tree_ready=True,
        device=AndroidDevice("serial", DeviceState.UNAUTHORIZED),
        device_pack_id="generic-android",
        device_dna_ready=True,
        capability_map_ready=True,
    )

    device_stage = GuidedMissionEngine().assess(context)[4]

    assert device_stage.status is GuidedStageStatus.ATTENTION
    assert "approve" in " ".join(device_stage.blockers).casefold()


def test_device_stage_distinguishes_every_detected_non_android_connection_mode():
    cases = (
        (DeviceState.OFFLINE, "ADB detected the phone, but it is offline"),
        (DeviceState.FASTBOOT, "Phone detected in fastboot mode"),
        (DeviceState.BOOTLOADER, "Phone detected in bootloader mode"),
        (DeviceState.FASTBOOTD, "Phone detected in fastbootd mode"),
        (DeviceState.RECOVERY, "Phone detected in recovery mode"),
        (DeviceState.SIDELOAD, "Phone detected in sideload mode"),
        (DeviceState.UNKNOWN, "connection mode is unknown"),
    )

    for state, expected in cases:
        device = AndroidDevice("serial", state, model="Visible Phone")
        context = GuidedContext(
            project_exists=True,
            original_imported=True,
            inspection_saved=True,
            working_copy_ready=True,
            working_tree_ready=True,
            device=device,
            observed_devices=(device,),
            device_pack_id="generic-android",
            device_dna_ready=True,
            capability_map_ready=True,
        )

        device_stage = GuidedMissionEngine().assess(context)[4]
        blockers = " ".join(device_stage.blockers)

        assert device_stage.status is GuidedStageStatus.ATTENTION
        assert expected in blockers
        assert "Connect the target Android phone by USB." not in blockers


def test_device_stage_distinguishes_selection_required_from_nothing_detected():
    first = AndroidDevice("one", DeviceState.DEVICE, model="First Phone")
    second = AndroidDevice("two", DeviceState.DEVICE, model="Second Phone")
    context = GuidedContext(
        project_exists=True,
        original_imported=True,
        inspection_saved=True,
        working_copy_ready=True,
        working_tree_ready=True,
        observed_devices=(first, second),
    )

    device_stage = GuidedMissionEngine().assess(context)[4]
    blockers = " ".join(device_stage.blockers)

    assert "Choose one of the 2 detected Android devices" in blockers
    assert "Connect the target Android phone by USB." not in blockers


def test_device_stage_does_not_treat_a_failed_scan_as_proof_of_disconnection():
    context = GuidedContext(
        project_exists=True,
        original_imported=True,
        inspection_saved=True,
        working_copy_ready=True,
        working_tree_ready=True,
        device_scan_error="ADB transport failed during refresh",
    )

    device_stage = GuidedMissionEngine().assess(context)[4]
    blockers = " ".join(device_stage.blockers)

    assert "latest USB device scan failed" in blockers
    assert "not treating this as proof that the phone is disconnected" in blockers
    assert "ADB transport failed during refresh" in blockers


def test_device_stage_cannot_complete_without_current_device_dna_and_capability_map():
    context = GuidedContext(
        project_exists=True,
        original_imported=True,
        inspection_saved=True,
        working_copy_ready=True,
        working_tree_ready=True,
        device=AndroidDevice("serial", DeviceState.DEVICE, model="Phone"),
        device_pack_id="phone-pack",
    )

    device_stage = GuidedMissionEngine().assess(context)[4]

    assert device_stage.status is GuidedStageStatus.ATTENTION
    assert "Device DNA" in " ".join(device_stage.blockers)
    assert "Capability Map" in device_stage.stage.explanation


def test_mission_routes_verified_local_workflow_into_real_forge_control():
    tools = tuple(
        ToolStatus(name, True, f"/tools/{name.casefold()}", "1.0", "Ready")
        for name in GENESIS_REQUIRED_TOOLS
    )
    context = GuidedContext(
        project_exists=True,
        original_imported=True,
        inspection_saved=True,
        working_copy_ready=True,
        working_tree_ready=True,
        device=AndroidDevice("serial", DeviceState.DEVICE, model="Phone"),
        device_pack_id="phone-pack",
        device_dna_ready=True,
        capability_map_ready=True,
        customization_skipped=True,
        debloat_complete=True,
        root_choice="skip",
        build_plan_saved=True,
        build_plan_verified=True,
        recovery_snapshot_ready=True,
        tool_statuses=tools,
    )

    assessments = GuidedMissionEngine().assess(context)

    assert all(assessment.status is GuidedStageStatus.COMPLETE for assessment in assessments[:11])
    build = assessments[11]
    assert build.stage.stage_id == "build_sign"
    assert build.status is GuidedStageStatus.ATTENTION
    blocker = " ".join(build.blockers).casefold()
    assert all(
        meaning in blocker
        for meaning in ("forge control", "exact device pack plan", "byte-verify", "before signing")
    )
    assert build.stage.action == "build-sign"
    assert build.stage.action_label == "Resolve build automatically"
    assert "signed, validated rom artifact" in build.next_outcome.casefold()
    assert "guardian review" in build.next_outcome.casefold()


def test_unchanged_unrooted_choice_skips_all_optional_modification_stages():
    context = GuidedContext(
        project_exists=True,
        original_imported=True,
        inspection_saved=True,
        working_copy_ready=True,
        working_tree_ready=True,
        device=AndroidDevice(
            "fixture",
            DeviceState.DEVICE,
            transport="simulation",
            model="Fixture Phone",
        ),
        device_pack_id="fixture-pack",
        device_dna_ready=True,
        capability_map_ready=True,
        customization_skipped=True,
        recipe_skipped=True,
        root_choice="skip",
    )

    assessments = GuidedMissionEngine().assess(context)

    assert all(assessments[index].status is GuidedStageStatus.COMPLETE for index in range(5, 9))
    assert assessments[7].evidence == (
        "Verified base kept unchanged; optional app removal was not requested",
    )
    assert GuidedMissionEngine.current_index(assessments) == 9
    assert assessments[9].stage.stage_id == "toolchain"


def test_toolchain_stage_requires_every_proven_build_dependency():
    tools = tuple(
        ToolStatus(name, True, f"/tools/{name.casefold()}", "1.0", "Ready")
        for name in GENESIS_REQUIRED_TOOLS
        if name != "AVBTool"
    )
    context = GuidedContext(
        project_exists=True,
        original_imported=True,
        inspection_saved=True,
        working_copy_ready=True,
        working_tree_ready=True,
        device=AndroidDevice("serial", DeviceState.DEVICE, model="Phone"),
        device_pack_id="phone-pack",
        device_dna_ready=True,
        capability_map_ready=True,
        customization_skipped=True,
        debloat_complete=True,
        root_choice="skip",
        build_plan_saved=True,
        build_plan_verified=True,
        recovery_snapshot_ready=True,
        tool_statuses=tools,
    )

    toolchain = GuidedMissionEngine().assess(context)[9]

    assert toolchain.status is GuidedStageStatus.ATTENTION
    assert "avbtool" in " ".join(toolchain.blockers).casefold()
    assert toolchain.stage.action_label == "Install and verify requirements"


def test_guardian_stage_becomes_ready_after_every_handoff_prerequisite():
    tools = tuple(
        ToolStatus(name, True, f"/tools/{name.casefold()}", "1.0", "Ready")
        for name in GENESIS_REQUIRED_TOOLS
    )
    context = GuidedContext(
        project_exists=True,
        original_imported=True,
        inspection_saved=True,
        working_copy_ready=True,
        working_tree_ready=True,
        device=AndroidDevice("serial", DeviceState.DEVICE, model="Phone"),
        device_pack_id="phone-pack",
        device_dna_ready=True,
        capability_map_ready=True,
        customization_skipped=True,
        debloat_complete=True,
        root_choice="skip",
        build_plan_saved=True,
        build_plan_verified=True,
        recovery_snapshot_ready=True,
        tool_statuses=tools,
        build_artifact_ready=True,
        signed_artifact_ready=True,
        install_requested=True,
        guardian_handoff_ready=True,
    )

    assessments = GuidedMissionEngine().assess(context)

    assert assessments[11].status is GuidedStageStatus.COMPLETE
    assert assessments[12].status is GuidedStageStatus.COMPLETE
    assert assessments[13].status is GuidedStageStatus.READY
    assert "final Guardian review" in " ".join(assessments[13].evidence)
    assert assessments[14].status is GuidedStageStatus.LOCKED


def test_completed_local_build_defers_phone_install_until_explicitly_requested():
    tools = tuple(
        ToolStatus(name, True, f"/tools/{name.casefold()}", "1.0", "Ready")
        for name in GENESIS_REQUIRED_TOOLS
    )
    context = GuidedContext(
        project_exists=True,
        original_imported=True,
        inspection_saved=True,
        working_copy_ready=True,
        working_tree_ready=True,
        device=AndroidDevice("serial", DeviceState.DEVICE, model="Phone"),
        device_pack_id="phone-pack",
        device_dna_ready=True,
        capability_map_ready=True,
        customization_skipped=True,
        debloat_complete=True,
        root_choice="skip",
        build_plan_saved=True,
        build_plan_verified=True,
        recovery_snapshot_ready=True,
        tool_statuses=tools,
        build_artifact_ready=True,
        signed_artifact_ready=True,
        guardian_handoff_ready=True,
    )

    deferred = GuidedMissionEngine().assess(context)
    requested = GuidedMissionEngine().assess(replace(context, install_requested=True))

    assert all(item.status is GuidedStageStatus.COMPLETE for item in deferred[:13])
    assert deferred[13].status is GuidedStageStatus.FUTURE
    assert deferred[14].status is GuidedStageStatus.FUTURE
    assert requested[13].status is GuidedStageStatus.READY
    assert requested[14].status is GuidedStageStatus.LOCKED


def test_guardian_stage_explains_prepared_mode_without_claiming_a_flash():
    context = GuidedContext(
        install_requested=True,
        guardian_handoff_ready=True,
        guardian_flash_handoff_ready=True,
        guardian_flash_mode="Dirty flash • keep user data",
    )

    flash = GuidedMissionEngine().assess(context)[13]

    assert flash.status is GuidedStageStatus.READY
    assert "Dirty flash" in " ".join(flash.evidence)
    assert "No device write" in " ".join(flash.evidence)
    assert "relocking is permanently prohibited" in " ".join(flash.evidence)


def test_failure_diagnosis_and_cleanup_are_bounded_to_transaction_files(tmp_path):
    workspace = tmp_path / "workspace"
    original = workspace / "original_roms" / ".import-deadbeef.part"
    project_temp = workspace / "projects" / "safe-project" / "plan.tmp"
    keep = workspace / "projects" / "safe-project" / "keep.bin"
    outside = tmp_path / "outside.part"
    for path in (original, project_temp, keep, outside):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"data")

    failure = GuidedMissionEngine.diagnose("Insufficient free space for copy")
    removed = GuidedMissionEngine.clean_partial_files(workspace, "safe-project")

    assert failure.safe_cleanup
    assert set(removed) == {original, project_temp}
    assert keep.exists()
    assert outside.exists()


def test_mission_state_round_trip(tmp_path):
    store = GuidedMissionStore(tmp_path / "project")
    expected = GuidedMissionState(
        selected_stage="build_plan",
        customization_skipped=True,
        recipe_skipped=True,
        recipe_validated=False,
        build_plan_verified=True,
        last_error="",
        root_choice="skip",
        install_requested=True,
    )

    store.save(expected)
    loaded = store.load()

    assert loaded.selected_stage == "build_plan"
    assert loaded.customization_skipped
    assert loaded.recipe_skipped
    assert loaded.build_plan_verified
    assert loaded.root_choice == "skip"
    assert loaded.install_requested
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert payload["format"] == "romverse.guided-mission"
    assert payload["schema_version"] == 6
    assert len(payload["record_digest"]) == 64
    if os.name != "nt":
        assert store.path.stat().st_mode & 0o777 == 0o600


def test_mission_state_rejects_tamper_extra_fields_links_oversize_and_type_coercion(tmp_path):
    project_dir = tmp_path / "project"
    store = GuidedMissionStore(project_dir)
    store.save(GuidedMissionState(selected_stage="debloat", root_choice="skip"))
    original = store.path.read_bytes()

    payload = json.loads(original)
    payload["selected_stage"] = "flash"
    store.path.write_text(json.dumps(payload), encoding="utf-8")
    assert GuidedMissionStore(project_dir).load().updated_at == ""

    store.path.write_bytes(original)
    payload = json.loads(original)
    payload["execution_authority"] = "flash"
    store.path.write_text(json.dumps(payload), encoding="utf-8")
    assert GuidedMissionStore(project_dir).load().updated_at == ""

    store.path.write_bytes(original)
    payload = json.loads(original)
    payload["recipe_validated"] = 1
    store.path.write_text(json.dumps(payload), encoding="utf-8")
    assert GuidedMissionStore(project_dir).load().updated_at == ""

    outside = tmp_path / "outside-mission.json"
    outside.write_bytes(original)
    store.path.unlink()
    store.path.symlink_to(outside)
    assert GuidedMissionStore(project_dir).load().updated_at == ""

    store.path.unlink()
    store.path.write_bytes(b"{" + b" " * (64 * 1024) + b"}")
    assert GuidedMissionStore(project_dir).load().updated_at == ""


def test_strict_legacy_mission_state_remains_readable_and_upgrades_on_save(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    path = project_dir / GuidedMissionStore.NAME
    path.write_text(
        json.dumps(
            {
                "schema_version": 4,
                "updated_at": "2026-08-30T12:00:00+00:00",
                "selected_stage": "root_choice",
                "customization_skipped": True,
                "recipe_skipped": True,
                "recipe_validated": False,
                "build_plan_verified": False,
                "last_error": "",
                "root_choice": "skip",
            }
        ),
        encoding="utf-8",
    )
    store = GuidedMissionStore(project_dir)

    legacy = store.load()
    upgraded = store.save(legacy)
    reloaded = store.load()

    assert legacy.schema_version == 6
    assert legacy.selected_stage == "root_choice"
    assert legacy.root_choice == "skip"
    assert upgraded.schema_version == 6
    assert reloaded == upgraded
    assert json.loads(path.read_text(encoding="utf-8"))["format"] == "romverse.guided-mission"


def test_signed_schema_five_state_migrates_without_starting_phone_install(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    path = project_dir / GuidedMissionStore.NAME
    payload = {
        "format": "romverse.guided-mission",
        "schema_version": 5,
        "updated_at": "2026-09-03T12:00:00+00:00",
        "selected_stage": "flash",
        "customization_skipped": True,
        "recipe_skipped": True,
        "recipe_validated": False,
        "build_plan_verified": True,
        "last_error": "",
        "root_choice": "skip",
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["record_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = GuidedMissionStore(project_dir).load()

    assert loaded.schema_version == 6
    assert loaded.selected_stage == "flash"
    assert loaded.build_plan_verified
    assert not loaded.install_requested


def test_root_choice_requires_an_explicit_decision_and_supports_unrooted_route():
    base = GuidedContext(
        project_exists=True,
        original_imported=True,
        inspection_saved=True,
        working_copy_ready=True,
        working_tree_ready=True,
        device=AndroidDevice("serial", DeviceState.DEVICE, model="Phone"),
        device_pack_id="phone-pack",
        device_dna_ready=True,
        capability_map_ready=True,
        recipe_skipped=True,
        debloat_complete=True,
    )

    undecided = GuidedMissionEngine().assess(base)
    assert undecided[8].stage.stage_id == "root_choice"
    assert undecided[8].status is GuidedStageStatus.READY
    assert undecided[9].status is GuidedStageStatus.LOCKED

    unrooted = GuidedMissionEngine().assess(replace(base, root_choice="skip"))
    assert unrooted[8].status is GuidedStageStatus.COMPLETE
    assert "unrooted" in " ".join(unrooted[8].evidence).casefold()
    assert unrooted[9].stage.stage_id == "toolchain"
    assert unrooted[9].status is GuidedStageStatus.ATTENTION


def test_rooted_route_waits_for_completed_ascension_protocol():
    base = GuidedContext(
        project_exists=True,
        original_imported=True,
        inspection_saved=True,
        working_copy_ready=True,
        working_tree_ready=True,
        device=AndroidDevice("serial", DeviceState.DEVICE, model="Phone"),
        device_pack_id="phone-pack",
        device_dna_ready=True,
        capability_map_ready=True,
        recipe_skipped=True,
        debloat_complete=True,
        root_choice="ascension",
    )

    pending = GuidedMissionEngine().assess(base)
    assert pending[8].status is GuidedStageStatus.ATTENTION
    assert "Ascension Protocol" in " ".join(pending[8].blockers)
    assert pending[9].status is GuidedStageStatus.LOCKED

    complete = GuidedMissionEngine().assess(replace(base, ascension_complete=True))
    assert complete[8].status is GuidedStageStatus.COMPLETE
    assert complete[9].stage.stage_id == "toolchain"
    assert complete[9].status is GuidedStageStatus.ATTENTION


def test_unrooted_route_cannot_pass_while_a_rooted_input_is_still_integrated():
    context = GuidedContext(
        project_exists=True,
        original_imported=True,
        inspection_saved=True,
        working_copy_ready=True,
        working_tree_ready=True,
        device=AndroidDevice("serial", DeviceState.DEVICE, model="Phone"),
        device_pack_id="phone-pack",
        device_dna_ready=True,
        capability_map_ready=True,
        recipe_skipped=True,
        debloat_complete=True,
        root_choice="skip",
        ascension_integrated=True,
    )

    root_choice = GuidedMissionEngine().assess(context)[8]
    assert root_choice.status is GuidedStageStatus.ATTENTION
    assert "restore the pristine image" in " ".join(root_choice.blockers)


def test_customization_stage_offers_a_plain_recommended_unchanged_route():
    customization = GuidedMissionEngine().assess(
        GuidedContext(
            project_exists=True,
            original_imported=True,
            inspection_saved=True,
            working_copy_ready=True,
            working_tree_ready=True,
            device=AndroidDevice("serial", DeviceState.DEVICE, model="Phone"),
            device_pack_id="phone-pack",
            device_dna_ready=True,
            capability_map_ready=True,
        )
    )[5]

    assert customization.stage.stage_id == "customize"
    assert customization.status is GuidedStageStatus.READY
    assert "Recipe Forge" in customization.stage.action_label
    assert customization.stage.optional


def test_nebula_debloat_is_a_real_required_decision_before_build_planning():
    context = GuidedContext(
        project_exists=True,
        original_imported=True,
        inspection_saved=True,
        working_copy_ready=True,
        working_tree_ready=True,
        device=AndroidDevice("serial", DeviceState.DEVICE, model="Phone"),
        device_pack_id="phone-pack",
        device_dna_ready=True,
        capability_map_ready=True,
        recipe_skipped=True,
    )

    assessments = GuidedMissionEngine().assess(context)
    debloat = assessments[7]

    assert debloat.stage.stage_id == "debloat"
    assert debloat.status is GuidedStageStatus.READY
    assert "green" in debloat.stage.explanation.casefold()
    assert assessments[8].status is GuidedStageStatus.LOCKED

    completed = GuidedMissionEngine().assess(replace(context, debloat_complete=True))
    assert completed[7].status is GuidedStageStatus.COMPLETE


def test_first_boot_validation_requires_flash_receipt_and_linked_stable_observation() -> None:
    tools = tuple(
        ToolStatus(name, True, f"/tools/{name.casefold()}", "1.0", "Ready")
        for name in GENESIS_REQUIRED_TOOLS
    )
    context = GuidedContext(
        project_exists=True,
        original_imported=True,
        inspection_saved=True,
        working_copy_ready=True,
        working_tree_ready=True,
        device=AndroidDevice("serial", DeviceState.DEVICE, model="Phone"),
        device_pack_id="phone-pack",
        device_dna_ready=True,
        capability_map_ready=True,
        root_choice="skip",
        debloat_complete=True,
        customization_skipped=True,
        recipe_skipped=True,
        build_plan_saved=True,
        build_plan_verified=True,
        recovery_snapshot_ready=True,
        tool_statuses=tools,
        build_artifact_ready=True,
        signed_artifact_ready=True,
        install_requested=True,
        guardian_handoff_ready=True,
        first_boot_verified=False,
    )
    pending = GuidedMissionEngine().assess(context)

    assert pending[-1].status is GuidedStageStatus.LOCKED
    assert "No stable first-boot session" in " ".join(pending[-1].evidence)

    baseline_only = GuidedMissionEngine().assess(
        replace(context, boot_observation_stable=True, first_boot_verified=True)
    )
    assert baseline_only[-1].status is GuidedStageStatus.LOCKED
    assert "not linked" in " ".join(baseline_only[-1].evidence)

    verified = GuidedMissionEngine().assess(
        replace(context, flash_complete=True, first_boot_verified=True)
    )
    assert verified[-1].status is GuidedStageStatus.COMPLETE
    assert "First boot and health verification appears stable" in " ".join(verified[-1].evidence)
