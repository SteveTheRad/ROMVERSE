from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import asdict, replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from romverse.core.settings import AppSettings
from romverse.device_packs.models import (
    DeviceMode,
    DeviceModeTransitionRule,
    DeviceRecoveryOperation,
    DeviceTransitionOperation,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.artifact_binding import GuardianArtifactBindingService
from romverse.guardian.audit import GuardianAuditStore
from romverse.guardian.execution_gateway_contract import (
    GatewayEvidenceKind,
    GatewayStepPhase,
    GuardianExecutionGatewayContractService,
    gateway_contract_matches_plan,
)
from romverse.guardian.manifest_review import GuardianManifestReviewService
from romverse.rom.models import ProjectError
from romverse.ui.build_control import GuardianManifestReviewDialog
from romverse.ui.guardian_center import GuardianCenter
from romverse.ui.main_window import MainWindow
from romverse.ui.rom_studio import GuardianReviewWorker, RomStudio
from tests.test_guardian_execution_plan import (
    _prepared,
    _prepared_with_post_write_verification,
    _prepared_with_transition_recovery,
)


class _NoRuntimeRunner:
    def run(self, command, timeout=10):
        raise AssertionError(f"The inert gateway contract tried to run {command!r}")


def _service(plans):
    return GuardianExecutionGatewayContractService(
        plans.store,
        plans.registry,
        runner=_NoRuntimeRunner(),
    )


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _reseal_contract(contract, *, steps=None, recovery_steps=None, **changes):
    if steps is not None:
        changes["steps"] = tuple(steps)
        changes["steps_digest"] = _digest({"steps": [asdict(step) for step in changes["steps"]]})
    if recovery_steps is not None:
        changes["recovery_steps"] = tuple(recovery_steps)
        changes["recovery_steps_digest"] = _digest(
            {"recovery_steps": [asdict(step) for step in changes["recovery_steps"]]}
        )
    changed = replace(contract, **changes, contract_digest="")
    payload = asdict(changed)
    payload.pop("contract_digest")
    return replace(changed, contract_digest=_digest(payload))


def test_gateway_contract_requires_exact_schema_two_verification(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding = _prepared(tmp_path, monkeypatch)
    plans.compile(project.project_id, report, device)

    with pytest.raises(ProjectError, match="schema-2|execution plan"):
        _service(plans).compile(project.project_id, report, device)


def test_gateway_contract_compiles_typed_inert_result_template(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding, verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    plan = plans.compile(project.project_id, report, device)
    service = _service(plans)

    contract = service.compile(project.project_id, report, device)

    assert contract.plan_id == plan.plan_id
    assert contract.plan_digest == plan.plan_digest
    assert (
        contract.post_write_verification_contract_digest
        == plan.post_write_verification_contract_digest
    )
    assert contract.schema_version == 2
    assert contract.result_receipt_schema_version == 2
    assert contract.step_count == len(contract.steps)
    assert contract.write_count == 1
    assert contract.readback_count == 1
    assert contract.post_boot_property_count == len(verification.post_boot_properties)
    assert contract.contract_status == (
        "blocked-missing-signed-transition-recovery-and-final-consent"
    )
    assert not contract.final_consent_available
    assert contract.execution_authority == "none"
    assert not contract.runtime_invoked
    assert not contract.phone_changed

    phases = [step.phase for step in contract.steps]
    assert phases[:4] == [
        GatewayStepPhase.PRECONDITION,
        GatewayStepPhase.PRECONDITION,
        GatewayStepPhase.PRECONDITION,
        GatewayStepPhase.WRITE,
    ]
    assert phases[4] is GatewayStepPhase.READBACK
    assert all(phase is GatewayStepPhase.POST_BOOT for phase in phases[5:])

    readback = contract.steps[4]
    assert readback.arguments == (
        "-s",
        service.TARGET_TOKEN,
        "fetch",
        verification.readbacks[0].partition,
        f"{service.PRIVATE_OUTPUT_TOKEN}/{readback.output_relative_path}",
    )
    assert readback.evidence_kind is GatewayEvidenceKind.FILE_SIZE_AND_SHA256
    assert readback.expected_size_bytes == verification.readbacks[0].expected_size_bytes
    assert readback.expected_sha256 == verification.readbacks[0].expected_sha256
    assert not readback.phone_changes

    property_steps = contract.steps[5:]
    assert {step.property_name: step.expected_value for step in property_steps} == {
        rule.property_name: rule.expected_value for rule in verification.post_boot_properties
    }
    assert all(
        step.arguments
        == (
            "-s",
            service.ADB_TARGET_TOKEN,
            "shell",
            "getprop",
            step.property_name,
        )
        for step in property_steps
    )
    serialized = json.dumps(asdict(contract))
    serialized_commands = " ".join(token for step in contract.steps for token in step.arguments)
    assert device.serial not in serialized
    assert "reboot" not in serialized_commands
    assert "erase" not in serialized_commands
    assert "flashing lock" not in serialized_commands
    assert service.load(project.project_id, report, device) == contract

    path = service.store.projects_root / project.project_id / "guardian" / service.LATEST_NAME
    if os.name != "nt":
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_guardian_worker_seals_schema_two_plan_and_gateway_contract(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding, _verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    worker = GuardianReviewWorker(
        GuardianArtifactBindingService(plans.store, plans.registry),
        GuardianManifestReviewService(plans.store, plans.registry),
        project.project_id,
        report,
        device,
    )
    completed = []
    failed = []
    progress = []
    terminal_records = []
    worker.signals.complete.connect(completed.append)
    worker.signals.failed.connect(failed.append)

    def record_progress(value):
        progress.append(value)
        if value == 100:
            guardian_root = plans.store.projects_root / project.project_id / "guardian"
            terminal_records.append(
                tuple(
                    (guardian_root / name).is_file()
                    for name in (
                        "manifest-review.romverse",
                        "execution-plan.romverse",
                        "execution-gateway-contract.romverse",
                    )
                )
            )

    worker.signals.progress.connect(record_progress)

    worker.run()

    assert failed == []
    assert len(completed) == 1
    assert worker.execution_plan is not None
    assert worker.execution_plan.plan_status == "ready-for-inert-gateway-contract"
    assert worker.gateway_contract is not None
    assert worker.gateway_contract.readback_count == worker.gateway_contract.write_count
    assert worker.gateway_contract.execution_authority == "none"
    assert not worker.gateway_contract.runtime_invoked
    assert not worker.gateway_contract.phone_changed
    assert progress[0] == 0
    assert progress[-1] == 100
    assert progress == sorted(progress)
    assert 90 not in progress
    assert 94 not in progress
    assert terminal_records == [(True, True, True)]


def test_guardian_worker_seals_schema_three_transition_aware_gateway(
    tmp_path,
    monkeypatch,
):
    plans, project, report, device, _manifest, _binding, _verification, transition = (
        _prepared_with_transition_recovery(tmp_path, monkeypatch)
    )
    worker = GuardianReviewWorker(
        GuardianArtifactBindingService(
            plans.store,
            plans.registry,
            runner=_NoRuntimeRunner(),
        ),
        GuardianManifestReviewService(plans.store, plans.registry),
        project.project_id,
        report,
        device,
    )
    completed = []
    failed = []
    progress = []
    worker.signals.complete.connect(completed.append)
    worker.signals.failed.connect(failed.append)
    worker.signals.progress.connect(progress.append)

    worker.run()

    assert failed == []
    assert len(completed) == 1
    assert worker.execution_plan is not None
    assert worker.execution_plan.plan_status == (
        "ready-for-inert-transition-aware-gateway-contract"
    )
    assert worker.execution_plan.transition_recovery_contract_id == transition.contract_id
    assert worker.execution_plan.execution_authority == "none"
    assert not worker.execution_plan.phone_changed
    assert worker.gateway_contract is not None
    assert worker.gateway_contract.mode_transition_count == len(transition.transitions)
    assert worker.gateway_contract.recovery_action_count == len(transition.recovery.actions)
    assert worker.gateway_contract.transition_recovery_contract_digest == (
        worker.execution_plan.transition_recovery_contract_digest
    )
    assert worker.gateway_contract.execution_authority == "none"
    assert not worker.gateway_contract.runtime_invoked
    assert not worker.gateway_contract.phone_changed
    guardian_root = plans.store.projects_root / project.project_id / "guardian"
    assert (guardian_root / "artifact-binding.romverse").is_file()
    assert (guardian_root / "manifest-review.romverse").is_file()
    assert (guardian_root / "execution-plan.romverse").is_file()
    assert (guardian_root / "execution-gateway-contract.romverse").is_file()
    assert progress[0] == 0
    assert progress[-1] == 100
    assert progress == sorted(progress)
    assert 90 not in progress
    assert 94 not in progress


def test_schema_three_gateway_binds_exact_transitions_and_recovery_without_runtime(
    tmp_path,
    monkeypatch,
):
    plans, project, report, device, _manifest, _binding, verification, transition = (
        _prepared_with_transition_recovery(tmp_path, monkeypatch)
    )
    plan = plans.compile(project.project_id, report, device)
    service = _service(plans)

    contract = service.compile(project.project_id, report, device)

    assert contract.write_contract_version == 3
    assert contract.transition_recovery_contract_id == transition.contract_id
    assert contract.transition_recovery_contract_digest == plan.transition_recovery_contract_digest
    assert contract.transition_entry_mode == DeviceMode.BOOTLOADER.value
    assert contract.transition_final_mode == DeviceMode.ANDROID.value
    assert contract.mode_transition_count == 2
    assert contract.recovery_action_count == 3
    assert contract.recovery_adapter_id == transition.recovery.adapter_id
    assert contract.recovery_stock_package_sha256 == transition.recovery.stock_package_sha256
    assert contract.recovery_may_wipe_user_data
    assert not contract.recovery_automatic_wipe_allowed
    assert not contract.recovery_bootloader_relock_allowed
    assert contract.contract_status == ("blocked-missing-live-runtime-receipts-and-final-consent")

    phases = [step.phase for step in contract.steps]
    assert phases[:7] == [
        GatewayStepPhase.PRECONDITION,
        GatewayStepPhase.PRECONDITION,
        GatewayStepPhase.TRANSITION,
        GatewayStepPhase.PRECONDITION,
        GatewayStepPhase.WRITE,
        GatewayStepPhase.READBACK,
        GatewayStepPhase.TRANSITION,
    ]
    assert all(phase is GatewayStepPhase.POST_BOOT for phase in phases[7:])
    transitions = tuple(
        step for step in contract.steps if step.phase is GatewayStepPhase.TRANSITION
    )
    assert transitions[0].transition_operation is DeviceTransitionOperation.REBOOT_FASTBOOTD
    assert transitions[0].arguments == (
        "-s",
        service.TARGET_TOKEN,
        "reboot",
        "fastboot",
    )
    assert transitions[0].evidence_kind is GatewayEvidenceKind.DEVICE_MODE_EQUALS
    assert transitions[0].expected_value == DeviceMode.FASTBOOTD.value
    assert transitions[1].transition_operation is DeviceTransitionOperation.REBOOT_SYSTEM
    assert transitions[1].arguments == ("-s", service.TARGET_TOKEN, "reboot")
    assert transitions[1].expected_value == DeviceMode.ANDROID.value

    assert [step.operation for step in contract.recovery_steps] == [
        DeviceRecoveryOperation.RESTORE_STOCK_PACKAGE,
        DeviceRecoveryOperation.REBOOT_SYSTEM,
        DeviceRecoveryOperation.VERIFY_POST_BOOT,
    ]
    assert contract.recovery_steps[0].may_wipe_user_data
    assert contract.recovery_steps[0].phone_changes_if_executed
    assert not contract.recovery_steps[-1].phone_changes_if_executed
    assert all(not hasattr(step, "executable") for step in contract.recovery_steps)
    assert len(verification.readbacks) == contract.readback_count
    assert device.serial not in json.dumps(asdict(contract))
    assert service.load(project.project_id, report, device) == contract


def test_guardian_ui_shows_plan_and_result_template_without_execution_control(
    tmp_path,
    monkeypatch,
):
    app = QApplication.instance() or QApplication([])
    plans, project, report, device, manifest, _binding, _verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    plan = plans.compile(project.project_id, report, device)
    contract = _service(plans).compile(project.project_id, report, device)

    dialog = GuardianManifestReviewDialog(
        manifest,
        execution_plan=plan,
        gateway_contract=contract,
    )
    app.processEvents()
    texts = [label.text() for label in dialog.findChildren(QLabel)]
    buttons = [button.text() for button in dialog.findChildren(QPushButton)]
    assert any("INERT EXECUTION PLAN" in text for text in texts)
    assert any("VERIFICATION RESULT TEMPLATE" in text for text in texts)
    assert any("READ BACK super" in text for text in texts)
    assert any("sys.boot_completed = 1" in text for text in texts)
    assert any("This template did not run anything" in text for text in texts)
    assert any("independently verified live-target" in text for text in texts)
    assert any("Live-target check v1 is read-only" in text for text in texts)
    assert buttons == ["Return to Genesis", "Open Guardian Core"]
    dialog.close()

    center = GuardianCenter(GuardianAuditStore(plans.store.workspace), auto_start=False)
    assert center.open_studio_review(manifest, project.name, plan, contract)
    detail = center.studio_review_detail.text()
    assert "INERT EXECUTION PLAN" in detail
    assert "RESULT TEMPLATE" in detail
    assert "immediate readback" in detail
    assert "Runtime invoked: no" in detail
    assert "SIGNED RESULT VERIFIER v2" in detail
    assert "Runtime trust: not enrolled" in detail
    assert "LIVE TARGET CHECK v1" in detail
    assert "two-minute validity" in detail
    assert "Execution: none" in detail
    center.close()


def test_guardian_ui_shows_signed_transition_and_recovery_contingency_without_controls(
    tmp_path,
    monkeypatch,
):
    app = QApplication.instance() or QApplication([])
    plans, project, report, device, manifest, _binding, _verification, _transition = (
        _prepared_with_transition_recovery(tmp_path, monkeypatch)
    )
    plan = plans.compile(project.project_id, report, device)
    contract = _service(plans).compile(project.project_id, report, device)

    dialog = GuardianManifestReviewDialog(
        manifest,
        execution_plan=plan,
        gateway_contract=contract,
    )
    app.processEvents()
    texts = [label.text() for label in dialog.findChildren(QLabel)]
    buttons = [button.text() for button in dialog.findChildren(QPushButton)]
    assert any("SIGNED TRANSITION" in text for text in texts)
    assert any("BOOTLOADER → FASTBOOTD" in text for text in texts)
    assert any("SIGNED RECOVERY CONTINGENCY" in text for text in texts)
    assert any("RESTORE STOCK PACKAGE" in text for text in texts)
    assert any("MAY WIPE USER DATA" in text for text in texts)
    assert any("Automatic wipe is forbidden" in text for text in texts)
    assert buttons == ["Return to Genesis", "Open Guardian Core"]
    assert all("execute" not in button.casefold() for button in buttons)
    assert all("flash" not in button.casefold() for button in buttons)
    dialog.close()

    center = GuardianCenter(GuardianAuditStore(plans.store.workspace), auto_start=False)
    assert center.open_studio_review(manifest, project.name, plan, contract)
    detail = center.studio_review_detail.text()
    assert "SIGNED ORCHESTRATION" in detail
    assert "2 mode/slot transition(s) / 3 recovery action(s)" in detail
    assert "recovery may wipe: yes (automatic wipe forbidden)" in detail
    assert "Runtime invoked: no" in detail
    assert "SIGNED RESULT VERIFIER v2" in detail
    assert "Runtime trust: not enrolled" in detail
    assert "LIVE TARGET CHECK v1" in detail
    assert "Execution: none" in detail
    center.close()


def test_studio_refuses_tampered_cached_gateway_context(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    plans, project, report, device, manifest, _binding, _verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    plan = plans.compile(project.project_id, report, device)
    contract = _service(plans).compile(project.project_id, report, device)
    studio = RomStudio(plans.store, plans.registry)
    studio._latest_guardian_execution_plan = plan
    studio._latest_guardian_gateway_contract = contract

    assert studio.guardian_execution_context(manifest) == (plan, contract)
    studio._latest_guardian_gateway_contract = replace(contract, runtime_invoked=True)
    assert studio.guardian_execution_context(manifest) == (plan, None)
    center = GuardianCenter(GuardianAuditStore(plans.store.workspace), auto_start=False)
    assert not center.open_studio_review(
        manifest,
        project.name,
        plan,
        replace(contract, execution_authority="device-write"),
    )
    center.close()
    studio.close()
    app.processEvents()


def test_main_window_carries_exact_gateway_context_into_guardian_core(
    tmp_path,
    monkeypatch,
):
    app = QApplication.instance() or QApplication([])
    plans, project, report, device, manifest, _binding, _verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    plan = plans.compile(project.project_id, report, device)
    contract = _service(plans).compile(project.project_id, report, device)
    logo = Path(__file__).parents[1] / "src/romverse/assets/romverse-app-icon.png"
    window = MainWindow(
        None,
        logo,
        plans.store.workspace,
        app_icon_path=logo,
        pack_registry=plans.registry,
        app_settings=AppSettings(online_intelligence_enabled=False),
    )
    monkeypatch.setattr(
        "romverse.ui.main_window.BuildReadinessService.assess",
        lambda *_args, **_kwargs: report,
    )
    try:
        window.rom_studio.set_devices([device])
        window.rom_studio._latest_guardian_execution_plan = plan
        window.rom_studio._latest_guardian_gateway_contract = contract
        window.rom_studio.guardian_review_requested.emit(
            project.project_id,
            manifest.manifest_digest,
        )
        app.processEvents()

        assert window.stack.currentWidget() is window.guardian_center
        detail = window.guardian_center.studio_review_detail.text()
        assert plan.plan_digest[:16] in detail
        assert contract.contract_digest[:16] in detail
        assert "1 immediate readback" in detail
        assert "7 first-boot checks" in detail
        assert "Runtime invoked: no" in detail
        assert "SIGNED RESULT VERIFIER v2" in detail
        assert "Runtime trust: not enrolled" in detail
        assert "Execution: none" in detail
    finally:
        window.companion_center.transport.close()
        window.close()


def test_gateway_contract_supports_explicit_readback_slot(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding, verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    pack = plans.registry.packs[0]
    assert pack.build_contract is not None
    write_contract = pack.build_contract.partition_write_contract
    assert write_contract is not None
    slotted_write = replace(write_contract.writes[0], target_slot="a")
    slotted_verification = replace(
        verification,
        readbacks=(replace(verification.readbacks[0], target_slot="a"),),
    )
    plans.registry = DevicePackRegistry(
        (
            replace(
                pack,
                build_contract=replace(
                    pack.build_contract,
                    partition_write_contract=replace(
                        write_contract,
                        writes=(slotted_write,),
                        post_write_verification_contract=slotted_verification,
                    ),
                ),
            ),
        )
    )
    binding_service = GuardianArtifactBindingService(plans.store, plans.registry)
    binding = binding_service.prepare(project.project_id)
    manifest_service = GuardianManifestReviewService(plans.store, plans.registry)
    manifest_service.compile(project.project_id, report, device, binding=binding)
    plan = plans.compile(project.project_id, report, device)

    contract = _service(plans).compile(project.project_id, report, device)
    readback = next(step for step in contract.steps if step.phase is GatewayStepPhase.READBACK)

    assert plan.write_contract_version == 2
    assert readback.target_slot == "a"
    assert readback.arguments[2:5] == ("--slot", "a", "fetch")


def test_schema_three_gateway_places_signed_slot_activation_after_readback(
    tmp_path,
    monkeypatch,
):
    plans, project, report, device, _manifest, _binding, verification, transition = (
        _prepared_with_transition_recovery(tmp_path, monkeypatch)
    )
    pack = plans.registry.packs[0]
    assert pack.build_contract is not None
    write_contract = pack.build_contract.partition_write_contract
    assert write_contract is not None
    slotted_transition = replace(
        transition,
        transitions=(
            transition.transitions[0],
            DeviceModeTransitionRule(
                2,
                1,
                DeviceTransitionOperation.SET_ACTIVE_SLOT,
                DeviceMode.FASTBOOTD,
                DeviceMode.FASTBOOTD,
                "a",
                30,
            ),
            replace(transition.transitions[1], order=3),
        ),
    )
    slotted_write_contract = replace(
        write_contract,
        writes=(replace(write_contract.writes[0], target_slot="a"),),
        post_write_verification_contract=replace(
            verification,
            readbacks=(replace(verification.readbacks[0], target_slot="a"),),
        ),
        transition_recovery_contract=slotted_transition,
    )
    plans.registry = DevicePackRegistry(
        (
            replace(
                pack,
                build_contract=replace(
                    pack.build_contract,
                    partition_write_contract=slotted_write_contract,
                ),
            ),
        )
    )
    binding = GuardianArtifactBindingService(plans.store, plans.registry).prepare(
        project.project_id
    )
    GuardianManifestReviewService(plans.store, plans.registry).compile(
        project.project_id,
        report,
        device,
        binding=binding,
    )
    plans.compile(project.project_id, report, device)

    contract = _service(plans).compile(project.project_id, report, device)

    write_index = next(
        index for index, step in enumerate(contract.steps) if step.phase is GatewayStepPhase.WRITE
    )
    assert [step.phase for step in contract.steps[write_index : write_index + 4]] == [
        GatewayStepPhase.WRITE,
        GatewayStepPhase.READBACK,
        GatewayStepPhase.TRANSITION,
        GatewayStepPhase.TRANSITION,
    ]
    activation = contract.steps[write_index + 2]
    assert activation.transition_operation is DeviceTransitionOperation.SET_ACTIVE_SLOT
    assert activation.arguments == ("-s", _service(plans).TARGET_TOKEN, "set_active", "a")
    assert activation.evidence_kind is GatewayEvidenceKind.ACTIVE_SLOT_EQUALS
    assert activation.expected_value == "a"
    assert contract.steps[write_index + 3].transition_operation is (
        DeviceTransitionOperation.REBOOT_SYSTEM
    )


def test_gateway_steps_read_back_each_partition_immediately(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding, verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    plan = plans.compile(project.project_id, report, device)
    first_write = plan.commands[-1]
    second_path = "working/example/build-candidates/plan/boot.img"
    second_write = replace(
        first_write,
        order=first_write.order + 1,
        operation_id="guardian.write.02.boot",
        arguments=(
            "-s",
            plans.TARGET_TOKEN,
            "flash",
            "boot",
            f"{plans.WORKSPACE_TOKEN}/{second_path}",
        ),
        partition="boot",
        artifact_relative_path=second_path,
        artifact_sha256="c" * 64,
    )
    second_readback = replace(
        verification.readbacks[0],
        partition="boot",
        expected_sha256="d" * 64,
    )

    steps = GuardianExecutionGatewayContractService._steps(
        replace(plan, commands=(*plan.commands, second_write)),
        replace(verification, readbacks=(*verification.readbacks, second_readback)),
    )

    first_index = next(
        index for index, step in enumerate(steps) if step.phase is GatewayStepPhase.WRITE
    )
    assert [step.phase for step in steps[first_index : first_index + 4]] == [
        GatewayStepPhase.WRITE,
        GatewayStepPhase.READBACK,
        GatewayStepPhase.WRITE,
        GatewayStepPhase.READBACK,
    ]
    assert steps[first_index + 1].partition == first_write.partition
    assert steps[first_index + 3].partition == second_write.partition


def test_gateway_contract_rejects_resealed_step_substitution(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding, _verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    plans.compile(project.project_id, report, device)
    service = _service(plans)
    service.compile(project.project_id, report, device)
    path = service.store.projects_root / project.project_id / "guardian" / service.LATEST_NAME
    document = json.loads(path.read_text(encoding="utf-8"))
    document["steps"][0]["expected_value"] = "forged-product"
    document["steps_digest"] = _digest({"steps": document["steps"]})
    payload = {
        key: value for key, value in document.items() if key not in {"format", "contract_digest"}
    }
    document["contract_digest"] = _digest(payload)
    path.write_text(json.dumps(document), encoding="utf-8")

    assert service.load(project.project_id, report, device) is None


def test_gateway_contract_rejects_stale_phone_and_changed_artifact(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding, _verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    plan = plans.compile(project.project_id, report, device)
    service = _service(plans)
    service.compile(project.project_id, report, device)

    assert service.load(project.project_id, report, replace(device, serial="other-phone")) is None

    write = next(command for command in plan.commands if command.phone_changes)
    artifact = service.store.workspace / write.artifact_relative_path
    before = artifact.stat()
    artifact.write_bytes(b"X" * before.st_size)
    os.utime(artifact, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert service.load(project.project_id, report, device) is None


def test_gateway_contract_rejects_resealed_uncontracted_command(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding, _verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    plans.compile(project.project_id, report, device)
    service = _service(plans)
    contract = service.compile(project.project_id, report, device)
    first = contract.steps[0]
    changed_step = replace(
        first,
        arguments=("-s", service.TARGET_TOKEN, "reboot", "bootloader"),
    )
    changed_steps = (changed_step, *contract.steps[1:])
    steps_digest = _digest({"steps": [asdict(step) for step in changed_steps]})
    changed = replace(
        contract,
        steps=changed_steps,
        steps_digest=steps_digest,
        contract_digest="",
    )
    payload = asdict(changed)
    payload.pop("contract_digest")
    changed = replace(changed, contract_digest=_digest(payload))

    with pytest.raises(ProjectError, match="safety validation"):
        service.validate(changed)


@pytest.mark.parametrize(
    "mutation",
    (
        "transition_arguments",
        "transition_expected_mode",
        "transition_from_mode",
        "recovery_action_id",
        "recovery_adapter_id",
        "recovery_stock_sha256",
        "recovery_wipe_disclosure",
    ),
)
def test_schema_three_gateway_rejects_resealed_orchestration_tampering(
    tmp_path,
    monkeypatch,
    mutation,
):
    plans, project, report, device, _manifest, _binding, _verification, _transition = (
        _prepared_with_transition_recovery(tmp_path, monkeypatch)
    )
    plan = plans.compile(project.project_id, report, device)
    service = _service(plans)
    contract = service.compile(project.project_id, report, device)
    changed = contract
    if mutation.startswith("transition_"):
        steps = list(contract.steps)
        index = next(
            index for index, step in enumerate(steps) if step.phase is GatewayStepPhase.TRANSITION
        )
        if mutation == "transition_arguments":
            steps[index] = replace(
                steps[index],
                arguments=("-s", service.TARGET_TOKEN, "reboot", "bootloader"),
            )
        elif mutation == "transition_expected_mode":
            steps[index] = replace(steps[index], expected_value="bootloader")
        else:
            steps[index] = replace(steps[index], from_mode=DeviceMode.FASTBOOTD)
        changed = _reseal_contract(contract, steps=steps)
    elif mutation == "recovery_action_id":
        recovery = list(contract.recovery_steps)
        recovery[0] = replace(recovery[0], adapter_action_id="foreign.adapter.restore")
        changed = _reseal_contract(contract, recovery_steps=recovery)
    elif mutation == "recovery_adapter_id":
        changed = _reseal_contract(contract, recovery_adapter_id="foreign.adapter")
    elif mutation == "recovery_stock_sha256":
        changed = _reseal_contract(contract, recovery_stock_package_sha256="f" * 64)
    else:
        changed = _reseal_contract(contract, recovery_may_wipe_user_data=False)

    with pytest.raises(ProjectError, match="safety validation"):
        service.validate(changed)
    service._write(changed)
    assert service.load(project.project_id, report, device) is None
    assert not gateway_contract_matches_plan(changed, plan)


def test_schema_three_gateway_expires_when_signed_transition_contract_changes(
    tmp_path,
    monkeypatch,
):
    plans, project, report, device, _manifest, _binding, _verification, transition = (
        _prepared_with_transition_recovery(tmp_path, monkeypatch)
    )
    plans.compile(project.project_id, report, device)
    service = _service(plans)
    service.compile(project.project_id, report, device)
    pack = plans.registry.packs[0]
    assert pack.build_contract is not None
    write_contract = pack.build_contract.partition_write_contract
    assert write_contract is not None
    changed_transition = replace(
        transition,
        transitions=(
            replace(
                transition.transitions[0],
                timeout_seconds=transition.transitions[0].timeout_seconds + 1,
            ),
            *transition.transitions[1:],
        ),
    )
    changed_registry = DevicePackRegistry(
        (
            replace(
                pack,
                build_contract=replace(
                    pack.build_contract,
                    partition_write_contract=replace(
                        write_contract,
                        transition_recovery_contract=changed_transition,
                    ),
                ),
            ),
        )
    )
    service.registry = changed_registry

    assert service.load(project.project_id, report, device) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", True),
        ("runtime_invoked", True),
        ("execution_authority", "device-write"),
        ("final_consent_available", True),
        ("phone_changed", True),
    ],
)
def test_gateway_contract_rejects_authority_and_type_confusion(tmp_path, monkeypatch, field, value):
    plans, project, report, device, _manifest, _binding, _verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    plans.compile(project.project_id, report, device)
    service = _service(plans)
    service.compile(project.project_id, report, device)
    path = service.store.projects_root / project.project_id / "guardian" / service.LATEST_NAME
    document = json.loads(path.read_text(encoding="utf-8"))
    document[field] = value
    payload = {
        key: item for key, item in document.items() if key not in {"format", "contract_digest"}
    }
    document["contract_digest"] = _digest(payload)
    path.write_text(json.dumps(document), encoding="utf-8")

    assert service.load(project.project_id, report, device) is None


def test_gateway_contract_rejects_extra_fields_and_links(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding, _verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    plans.compile(project.project_id, report, device)
    service = _service(plans)
    service.compile(project.project_id, report, device)
    path = service.store.projects_root / project.project_id / "guardian" / service.LATEST_NAME
    document = json.loads(path.read_text(encoding="utf-8"))
    document["unexpected"] = "authority"
    path.write_text(json.dumps(document), encoding="utf-8")
    assert service.load(project.project_id, report, device) is None

    service.compile(project.project_id, report, device)
    target = path.with_name("linked-gateway-contract.json")
    path.replace(target)
    path.symlink_to(target.name)
    assert service.load(project.project_id, report, device) is None


def test_gateway_contract_rejects_oversized_record(tmp_path, monkeypatch):
    plans, project, report, device, _manifest, _binding, _verification = (
        _prepared_with_post_write_verification(tmp_path, monkeypatch)
    )
    plans.compile(project.project_id, report, device)
    service = _service(plans)
    service.compile(project.project_id, report, device)
    path = service.store.projects_root / project.project_id / "guardian" / service.LATEST_NAME
    path.write_bytes(b"{" + b" " * service.MAX_BYTES)

    assert service.load(project.project_id, report, device) is None
