"""Runtime refusal and lifecycle regressions; every device and image is inert."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from romverse.guardian.local_flash import LocalFlashError, LocalFlashState
from romverse.guardian.source_installation import (
    SourceInstallationError,
    SourceInstallationExecutor,
    validate_source_installation_boot_binding,
)
from romverse.infrastructure.process import CommandResult
from romverse.rom.source_installation_history import load_latest_source_installation
from tests.test_source_installation_integration import installation as installation


def _preview(installation, **choices):
    executor = SourceInstallationExecutor(installation.source, installation.flash, installation.adb)
    recipe = installation.recipe(**choices)
    return executor, executor.inspect(installation.phone.device(), recipe)


def _execute(executor, plan, **kwargs):
    return executor.execute(plan, accepted_digest=plan.plan_digest, risk_accepted=True, **kwargs)


@pytest.mark.parametrize(
    "accepted,risk", [("wrong", True), (None, True), ("correct", False), ("correct", 1)]
)
def test_missing_exact_consent_never_starts_any_phone_change(installation, accepted, risk):
    executor, plan = _preview(installation)
    with pytest.raises(SourceInstallationError, match="Confirm"):
        executor.execute(
            plan,
            accepted_digest=plan.plan_digest if accepted == "correct" else accepted,
            risk_accepted=risk,
        )
    assert installation.phone.changes == []
    assert not list(executor.root.glob("*.json"))


@pytest.mark.parametrize(
    "field,value", [("product", "otherphone"), ("current_slot", "a"), ("fastboot_sha256", "f" * 64)]
)
def test_plan_edits_cannot_reuse_confirmation(installation, field, value):
    executor, plan = _preview(installation)
    with pytest.raises(SourceInstallationError, match="changed"):
        _execute(executor, replace(plan, **{field: value}))
    assert installation.phone.changes == []


def test_keepdata_plan_cannot_be_changed_to_wipe_with_original_consent(installation):
    executor, plan = _preview(installation, wipe=False)
    forged = replace(plan, recipe=replace(plan.recipe, wipe=True))
    with pytest.raises(SourceInstallationError, match="changed"):
        _execute(executor, forged)
    assert installation.phone.changes == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("product", "anotherdevice"),
        ("critical_unlocked", False),
        ("unlocked", False),
        ("mode", "fastbootd"),
    ],
)
def test_live_target_or_unlock_drift_stops_before_first_mutation(installation, field, value):
    executor, plan = _preview(installation)
    setattr(installation.phone, field, value)
    result = _execute(executor, plan)
    assert result.state is LocalFlashState.REJECTED
    assert not result.phone_change_attempted
    assert installation.phone.changes == []


def test_same_sized_wrong_product_is_not_accepted(installation):
    installation.phone.product = "wrong-device"
    with pytest.raises(LocalFlashError, match="different device"):
        _preview(installation)
    assert installation.phone.changes == []


def test_changed_host_tool_stops_before_first_mutation(installation):
    executor, plan = _preview(installation)
    plan.fastboot_path.write_bytes(b"DIFFERENT INERT TOOL")
    result = _execute(executor, plan)
    assert result.state is LocalFlashState.REJECTED
    assert "Fastboot changed" in result.summary
    assert installation.phone.changes == []


def test_source_changed_after_review_is_not_used(installation):
    executor, plan = _preview(installation)
    plan.recipe.archive_path.chmod(0o600)
    with plan.recipe.archive_path.open("ab") as stream:
        stream.write(b"SOURCE CHANGED")
    result = _execute(executor, plan)
    assert result.state is LocalFlashState.REJECTED
    assert installation.phone.changes == []


def test_insufficient_private_snapshot_space_stops_before_slot_selection(installation, monkeypatch):
    executor, plan = _preview(installation)
    monkeypatch.setattr(
        "romverse.guardian.source_installation.shutil.disk_usage",
        lambda _path: SimpleNamespace(free=0),
    )
    result = _execute(executor, plan)
    assert result.state is LocalFlashState.REJECTED
    assert "free bytes" in result.summary
    assert installation.phone.changes == []


def test_cancel_before_staging_is_non_mutating_and_consumes_consent(installation):
    executor, plan = _preview(installation)
    result = _execute(executor, plan, should_cancel=lambda: True)
    assert result.state is LocalFlashState.CANCELLED
    assert not result.phone_change_attempted
    assert installation.phone.changes == []
    with pytest.raises(SourceInstallationError, match="already used"):
        _execute(executor, plan)


def test_cancel_waits_for_current_command_then_skips_remaining_writes_erase_reboot(installation):
    executor, plan = _preview(installation, wipe=True)
    cancelled = False

    def after_command(_command):
        nonlocal cancelled
        if len(installation.phone.changes) == 2:
            cancelled = True

    installation.phone.on_change = after_command
    result = _execute(executor, plan, should_cancel=lambda: cancelled)
    assert result.state is LocalFlashState.CANCELLED
    assert [item.action for item in result.results] == ["set_active", "flash"]
    assert len(installation.phone.changes) == 2
    assert result.results[-1].completed
    assert result.phone_state_uncertain
    assert not result.reboot_requested


def test_set_active_ack_without_measured_slot_stops_before_any_image(installation):
    executor, plan = _preview(installation)
    installation.phone.on_change = lambda _command: setattr(installation.phone, "slot", "b")
    result = _execute(executor, plan)
    assert result.state is LocalFlashState.FAILED
    assert installation.phone.changes == [("set_active", "a")]
    assert result.results[0].returncode == 0
    assert result.results[0].verified_slot == ""
    assert not installation.phone.written


def test_every_command_has_private_durable_intent_and_shared_device_lock(installation):
    executor, plan = _preview(installation, reboot=False)
    observed = []

    def while_command_runs(_command):
        document = json.loads((executor.root / f"{plan.plan_id}.json").read_text())
        observed.append(document["in_flight_step"])
        assert document["state"] == "command-in-flight"
        assert document["snapshots_verified"] is True
        assert document["phone_change_attempted"] is True
        assert len(document["image_snapshots"]) == 50
        assert installation.phone.serial not in json.dumps(document)
        with (
            pytest.raises(LocalFlashError, match="using this phone"),
            installation.flash._device_lock(installation.phone.serial),
        ):
            pytest.fail("Another operation acquired the same phone")

    installation.phone.on_change = while_command_runs
    result = _execute(executor, plan)
    assert result.state is LocalFlashState.COMPLETED
    assert observed == list(range(52))
    assert result.phone_state_uncertain and not result.boot_verified


def test_private_image_changed_after_staging_stops_before_its_write(installation):
    executor, plan = _preview(installation)

    def damage_next_image(_command):
        if len(installation.phone.changes) != 1:
            return
        image = plan.recipe.images[0]
        snapshot = executor.root / "images" / plan.plan_id / f"{image.sha256}.img"
        snapshot.chmod(0o600)
        snapshot.write_bytes(b"TAMPERED PRIVATE IMAGE")

    installation.phone.on_change = damage_next_image
    result = _execute(executor, plan)
    assert result.state is LocalFlashState.FAILED
    assert len(installation.phone.changes) == 1
    assert installation.phone.written == []


def test_mid_procedure_target_change_stops_all_remaining_steps(installation):
    executor, plan = _preview(installation)

    def swap_phone(_command):
        if len(installation.phone.changes) == 2:
            installation.phone.product = "wrongdevice"

    installation.phone.on_change = swap_phone
    result = _execute(executor, plan)
    assert result.state is LocalFlashState.FAILED
    assert len(installation.phone.changes) == 2
    assert not result.reboot_requested


def test_completed_receipt_boot_binding_is_exact_phone_and_not_a_health_claim(installation):
    executor, plan = _preview(installation)
    result = _execute(executor, plan)
    assert result.state is LocalFlashState.COMPLETED
    binding = validate_source_installation_boot_binding(
        installation.flash, installation.phone.device(), result
    )
    assert binding["relative_path"].startswith("guardian/source-installation/")
    assert binding["relative_path"] == f"guardian/source-installation/{plan.plan_id}.json"
    assert "\\" not in binding["relative_path"]
    document = json.loads(result.receipt_path.read_text())
    for snapshot in document["image_snapshots"]:
        assert snapshot["relative_path"] == (
            f"guardian/source-installation/images/{plan.plan_id}/{snapshot['sha256']}.img"
        )
        assert "\\" not in snapshot["relative_path"]
    assert not result.boot_verified
    wrong = replace(installation.phone.device(), serial="another-phone")
    with pytest.raises(SourceInstallationError, match="exact phone"):
        validate_source_installation_boot_binding(installation.flash, wrong, result)
    with pytest.raises(SourceInstallationError, match="transport receipt"):
        validate_source_installation_boot_binding(
            installation.flash, installation.phone.device(), replace(result, boot_verified=True)
        )


def test_boot_binding_rejects_receipt_changed_after_completion(installation):
    executor, plan = _preview(installation)
    result = _execute(executor, plan)
    document = json.loads(result.receipt_path.read_text())
    document["production_certification"] = True
    result.receipt_path.write_text(json.dumps(document))
    with pytest.raises(SourceInstallationError, match="digest"):
        validate_source_installation_boot_binding(
            installation.flash, installation.phone.device(), result
        )


def test_unmeasurable_runner_result_leaves_interrupted_step_and_never_retries(
    installation, monkeypatch
):
    executor, plan = _preview(installation)
    original_run = installation.phone.run

    def mismatched(args, timeout=10, cwd=None):
        result = original_run(args, timeout, cwd)
        if "set_active" in args:
            return CommandResult(("other",), 0, "", "")
        return result

    monkeypatch.setattr(installation.phone, "run", mismatched)
    result = _execute(executor, plan)
    assert result.state is LocalFlashState.FAILED
    assert result.phone_change_attempted
    assert json.loads(result.receipt_path.read_text())["in_flight_step"] == 0
    assert len(installation.phone.changes) == 1
    with pytest.raises(SourceInstallationError, match="already used"):
        _execute(executor, plan)


def test_claimed_plan_survives_long_staging_but_unclaimed_plan_still_expires(
    installation, monkeypatch
):
    executor, plan = _preview(installation, reboot=False)
    other_executor, unclaimed = _preview(installation, reboot=False)
    clock_time = datetime.now(UTC)

    class TestDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock_time.astimezone(tz) if tz is not None else clock_time.replace(tzinfo=None)

    monkeypatch.setattr("romverse.guardian.source_installation.datetime", TestDateTime)
    original_stage = executor._stage

    def slow_stage(*args, **kwargs):
        nonlocal clock_time
        snapshots = original_stage(*args, **kwargs)
        clock_time += timedelta(seconds=executor.PLAN_VALID_FOR_SECONDS + 10)
        return snapshots

    monkeypatch.setattr(executor, "_stage", slow_stage)
    result = _execute(executor, plan)
    assert result.state is LocalFlashState.COMPLETED
    assert len(installation.phone.changes) == 52
    before = len(installation.phone.changes)
    with pytest.raises(SourceInstallationError, match="expired"):
        _execute(other_executor, unclaimed)
    assert len(installation.phone.changes) == before


@pytest.mark.parametrize("field,value", [("manufacturer", "Samsung"), ("codename", "komodo")])
def test_boot_binding_rejects_contradictory_known_identity_even_with_matching_product(
    installation, field, value
):
    executor, plan = _preview(installation)
    result = _execute(executor, plan)
    wrong = replace(installation.phone.device(), product="popsicle", **{field: value})
    with pytest.raises(SourceInstallationError, match="contradicts"):
        validate_source_installation_boot_binding(installation.flash, wrong, result)


def _override_super_probe(installation, monkeypatch, variable, reply):
    original = installation.phone.run

    def run(args, timeout=10, cwd=None):
        command = tuple(str(item) for item in args)
        if command[3:] == ("getvar", variable):
            installation.phone.calls.append(command)
            value = reply() if callable(reply) else reply
            if value is None:
                return CommandResult(command, 1, "", "FAILED (remote: 'GetVar Variable Not found')")
            return CommandResult(command, 0, "", f"(bootloader) {variable}: {value}\n")
        return original(args, timeout, cwd)

    monkeypatch.setattr(installation.phone, "run", run)


def test_declared_whole_super_with_unreported_slot_capability_runs_exact_procedure(
    installation, monkeypatch
):
    _override_super_probe(installation, monkeypatch, "has-slot:super", None)
    executor, plan = _preview(installation)
    facts = next(item for item in plan.partition_facts if item[0] == "super")
    assert facts[3] is None
    result = _execute(executor, plan)
    assert result.state is LocalFlashState.COMPLETED
    assert result.completed_count == 53
    super_writes = [step for step in installation.phone.changes if "super" in step]
    assert len(super_writes) == 1
    assert super_writes[0][:4] == ("-S", "700M", "flash", "super")
    assert not any("super_a" in step or "super_b" in step for step in installation.phone.changes)


@pytest.mark.parametrize(
    "variable,value,message",
    [
        ("has-slot:super", "yes", "exact super_a"),
        ("is-logical:super", "yes", "logical partition"),
        ("partition-size:super", "0x1", "too large"),
    ],
)
def test_known_incompatible_super_facts_still_stop_before_first_mutation(
    installation, monkeypatch, variable, value, message
):
    _override_super_probe(installation, monkeypatch, variable, value)
    with pytest.raises(LocalFlashError, match=message):
        _preview(installation)
    assert installation.phone.changes == []


def test_super_fact_drift_after_review_stops_before_the_super_write(installation, monkeypatch):
    # Even a newly reported "not slotted" value differs from the exact reviewed
    # unknown state; executing an existing plan must not silently adopt new facts.
    _override_super_probe(
        installation,
        monkeypatch,
        "has-slot:super",
        lambda: "no" if installation.phone.changes else None,
    )
    executor, plan = _preview(installation)
    result = _execute(executor, plan)
    assert result.state is LocalFlashState.FAILED
    assert "Partition facts changed for super" in result.summary
    assert len(installation.phone.written) == 47
    assert not any("super" in step for step in installation.phone.changes)
    assert not result.reboot_requested
    assert result.phone_state_uncertain


def test_crash_before_first_save_leaves_sealed_intent_that_new_attempt_can_supersede(
    installation, monkeypatch
):
    executor, plan = _preview(installation)
    original_verify = installation.source.verify

    class SimulatedPowerLoss(BaseException):
        pass

    def interrupted_before_staging(_recipe):
        raise SimulatedPowerLoss

    monkeypatch.setattr(installation.source, "verify", interrupted_before_staging)
    with pytest.raises(SimulatedPowerLoss):
        _execute(executor, plan)
    initial_path = executor.root / f"{plan.plan_id}.json"
    original_bytes = initial_path.read_bytes()
    document = json.loads(original_bytes)
    content = {key: value for key, value in document.items() if key != "record_digest"}
    assert (
        document["record_digest"]
        == hashlib.sha256(
            json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
    )
    assert document["state"] == "preparing"
    assert document["phone_change_attempted"] is False
    assert document["results"] == []
    assert "completed_at" not in document and "snapshots_verified" not in document
    assert installation.phone.changes == []
    interrupted = load_latest_source_installation(
        installation.source.store, installation.project_id
    )
    assert interrupted is not None and interrupted.state == "attention"
    assert interrupted.receipt_path == initial_path and interrupted.result is None
    with pytest.raises(SourceInstallationError, match="already used"):
        _execute(executor, plan)

    monkeypatch.setattr(installation.source, "verify", original_verify)
    fresh_plan = executor.inspect(installation.phone.device(), plan.recipe)
    result = _execute(executor, fresh_plan)
    assert result.state is LocalFlashState.COMPLETED
    # Mtime is not the authority for the dated, sealed operation chronology.
    initial_path.touch()
    latest = load_latest_source_installation(installation.source.store, installation.project_id)
    assert latest is not None and latest.state == "completed"
    assert latest.receipt_path == result.receipt_path
    assert latest.completed_count == 53
    assert initial_path.read_bytes() == original_bytes
