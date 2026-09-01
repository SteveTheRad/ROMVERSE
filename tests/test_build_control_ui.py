from __future__ import annotations

import os
import zipfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton

from romverse.backup.handoff import BackupHandoffService, CloudBackupProvider
from romverse.core.settings import AppSettings
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.models import (
    CapabilityStatus,
    DevicePack,
    DeviceWriteTransport,
    PackCapability,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.artifact_binding import GuardianBoundArtifact
from romverse.guardian.flash_handoff import FlashMode
from romverse.guardian.manifest_review import (
    GuardianManifestCheck,
    GuardianManifestReview,
    ManifestReviewState,
)
from romverse.infrastructure.tools import ToolStatus
from romverse.intelligence.online_remediation import (
    ErrorFingerprint,
    OnlineRemediationService,
)
from romverse.intelligence.synapse import SynapseKnowledgeState, SynapseStore
from romverse.nexus.events import LiveConsoleEventStore, MissionState
from romverse.rom.builds import RomBuildPlanner
from romverse.rom.inspection import RomInspectionService
from romverse.rom.projects import RomProjectStore
from romverse.rom.readiness import (
    BuildGate,
    BuildReadinessReport,
    GateStatus,
    remediation_for,
)
from romverse.ui.build_control import (
    BuildControlCenter,
    CloudBackupConfirmationDialog,
    GuardianFlashModeDialog,
    GuardianManifestReviewDialog,
    PhoneBackupGuideDialog,
    PhoneMediaBackupDialog,
    SourceBlueprintWorker,
)
from romverse.ui.rom_studio import RomStudio


def _studio(tmp_path) -> RomStudio:
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("system.img", b"system")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Readiness UI", "test.pack")
    store.import_original(project.project_id, source)
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    inspection.extract_project_tree(project.project_id)
    RomBuildPlanner(store).plan(project.project_id)
    capability = PackCapability(
        "firmware.operations",
        "Firmware",
        CapabilityStatus.PLANNED,
        "locked",
        "Requires model-specific validation, signed pack updates, and physical recovery testing.",
    )
    pack = DevicePack(
        "test.pack",
        "1",
        "Test",
        10,
        ("test",),
        (),
        (),
        (capability,),
        (),
        "a" * 64,
    )
    tools = tuple(
        ToolStatus(name, True)
        for name in ("Python", "Git", "7-Zip", "Unzip", "Make", "Java", "AVBTool")
    )
    return RomStudio(store, DevicePackRegistry((pack,)), tools)


def test_direct_avb_action_resolves_missing_tools_before_starting_worker(
    tmp_path, monkeypatch
) -> None:
    QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    studio.payload_service = None
    studio.tool_statuses = (ToolStatus("AVBTool", False, detail="missing"),)
    control = BuildControlCenter(studio, auto_start=False)
    resolutions = []

    def resolve(required, **options):
        resolutions.append((required, options))
        studio.payload_service = SimpleNamespace(runner=SimpleNamespace())
        studio.tool_statuses = (
            ToolStatus("AVBTool", True, "/bin/true", "fixture", "Ready"),
            ToolStatus("Payload Dumper", True, "/bin/true", "fixture", "Ready"),
        )
        return True

    started = []
    studio._resolve_required_tools = resolve
    monkeypatch.setattr("romverse.ui.build_control.start_background", started.append)

    control._inspect_avb_topology()

    assert resolutions[0][0] == ("Payload Dumper", "AVBTool")
    assert resolutions[0][1]["parent"] is control
    assert started == [control.avb_worker]
    assert control.avb_worker is not None
    assert control.process_progress.maximum() == 0
    control.avb_worker = None
    control.close()
    studio.close()


def test_direct_signing_action_resolves_avbtool_before_eligibility_review(
    tmp_path, monkeypatch
) -> None:
    QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    control = BuildControlCenter(studio, auto_start=False)
    resolutions = []
    information = []

    def resolve(required, **options):
        resolutions.append((required, options))
        return True

    service = SimpleNamespace(
        eligibility=lambda _project_id: (False, "Exact signing policy is not authorized")
    )
    services = iter((None, service))
    studio._resolve_required_tools = resolve
    monkeypatch.setattr(control, "_signing_service", lambda: next(services))
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args: information.append(args),
    )

    control._signing_ceremony()

    assert resolutions[0][0] == ("AVBTool",)
    assert resolutions[0][1]["parent"] is control
    assert information
    assert "not authorized" in str(information[0]).casefold()
    control.close()
    studio.close()


def test_local_backup_resolves_adb_and_waits_for_atomic_runtime_activation(
    tmp_path, monkeypatch
) -> None:
    QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    studio.set_android_runtime(None, None)
    control = BuildControlCenter(studio, auto_start=False)
    device = AndroidDevice(
        "fixture",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        marketing_name="Xiaomi 17 Pro Max",
    )
    resolutions = []
    dialogs = []

    def resolve(required, **options):
        resolutions.append((required, options))
        studio.set_android_runtime(SimpleNamespace(), Path("/bin/true"))
        return True

    class BackupDialog:
        def __init__(self, *args):
            dialogs.append(args)

        def values(self):
            return None

    studio._resolve_required_tools = resolve
    monkeypatch.setattr("romverse.ui.build_control.PhoneMediaBackupDialog", BackupDialog)

    control._prepare_phone_media_backup(device)

    assert resolutions[0][0] == ("ADB",)
    assert resolutions[0][1]["parent"] is control
    assert dialogs
    assert "runtime activated" in control.status.text().casefold()
    control.close()
    studio.close()


def test_autopilot_recovery_creates_local_checkpoint_before_prompting(
    tmp_path, monkeypatch
) -> None:
    QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    control = BuildControlCenter(studio, auto_start=False)
    started: list[str] = []
    monkeypatch.setattr(studio.store, "list_snapshots", lambda _project_id: ())
    monkeypatch.setattr(studio, "_start_worker", started.append)

    control.autopilot_active = True
    control._autopilot_recovery()

    assert started == ["snapshot"]
    assert control.autopilot_waiting_for == "snapshot"
    assert control.process_progress.minimum() == 0
    assert control.process_progress.maximum() == 0
    assert "phone remain unchanged" in control.status.text()
    control.autopilot_active = False
    control.close()
    studio.close()


def test_autopilot_recovery_revalidates_legacy_evidence(tmp_path, monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    control = BuildControlCenter(studio, auto_start=False)
    launched = []
    monkeypatch.setattr(
        studio.store,
        "list_snapshots",
        lambda _project_id: (SimpleNamespace(schema_version=2),),
    )
    monkeypatch.setattr(
        "romverse.ui.build_control.RecoveryEvidenceService.load",
        lambda _service, _project_id: SimpleNamespace(schema_version=1),
    )
    monkeypatch.setattr("romverse.ui.build_control.start_background", launched.append)

    control.autopilot_active = True
    control._autopilot_recovery()

    assert len(launched) == 1
    assert launched[0] is control.recovery_worker
    assert launched[0].operation == "verify"
    assert control.autopilot_waiting_for == "recovery-evidence"
    assert "Rehashing" in control.status.text()
    control.recovery_worker = None
    control.autopilot_active = False
    control.close()
    studio.close()


def test_build_control_cards_explain_and_route_blocked_gates(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    control = BuildControlCenter(studio, auto_start=False)
    app.processEvents()

    blocked = control.gate_rows["device-pack-build"]
    assert "created automatically" in blocked.toolTip()
    assert "Auto-resolve" in blocked.toolTip()
    assert control.resolve_buttons["device-pack-build"].text() == "Auto-resolve"
    assert control.gate_rows["plan"].toolTip()
    assert "signing identity" in control.gate_rows["signer"].toolTip()
    signer_gate = next(gate for gate in control.report.gates if gate.gate_id == "signer")
    assert signer_gate.status is not GateStatus.PASS
    assert remediation_for(signer_gate).action_id == "autopilot"
    assert control.resolve_buttons["signer"].text() == "Auto-resolve"
    assert any(label.text() == "NEXT SAFE RESOLUTION" for label in control.findChildren(QLabel))
    assert any("ASCENSION PROTOCOL" in label.text() for label in control.findChildren(QLabel))
    assert any("Root is optional" in label.text() for label in control.findChildren(QLabel))
    assert control.autopilot_button.text() == "Auto-resolve && continue"
    assert "authoritative input" in control.autopilot_button.toolTip()

    opened: list[bool] = []
    studio.device_packs_requested.connect(lambda: opened.append(True))
    control._open_resolution("device-packs")
    assert opened == [True]
    studio.close()


def test_refresh_removes_stale_cards_and_footer_actions_remain_aligned(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    control = BuildControlCenter(studio, auto_start=False)
    control.resize(1160, 820)
    control.show()
    app.processEvents()
    assert any("Structure inspection" in label.text() for label in control.findChildren(QLabel))
    report = BuildReadinessReport(
        1,
        "1" * 32,
        control.project.project_id,
        "2026-08-31T00:00:00+00:00",
        (
            BuildGate(
                "device-pack-flash",
                "Device Pack flash and recovery contract",
                "Recovery",
                GateStatus.ATTENTION,
                "Safe local preparation is complete; signed exact write evidence is missing.",
                "flash",
            ),
            BuildGate(
                "physical-validation",
                "Operation and release scope",
                "Guardian",
                GateStatus.ATTENTION,
                "Independent physical recovery evidence is missing.",
                "release",
            ),
        ),
        True,
        True,
        True,
        True,
        False,
        (),
        (),
        "2" * 64,
    )

    control.refresh(report)
    control.evidence_watch.stop()
    app.processEvents()

    assert not any("Structure inspection" in label.text() for label in control.findChildren(QLabel))
    assert "0 blocked" in control.status.text()
    assert "2 need attention" in control.status.text()
    footer_labels = {
        "Refresh evidence",
        "Export evidence bundle",
        "Prepare exact build inputs",
        "Prepare local build plan",
        "Build verified local candidate",
        "Inspect AVB topology",
        "Offline signing ceremony",
        "Auto-resolve && continue",
        "Run safe pipeline simulation",
        "Close",
    }
    footer_buttons = tuple(
        button
        for button in control.findChildren(QPushButton)
        if button.text() in footer_labels and button.isVisible()
    )
    assert {button.text() for button in footer_buttons} == footer_labels
    assert all(
        not left.geometry().intersects(right.geometry())
        for index, left in enumerate(footer_buttons)
        for right in footer_buttons[index + 1 :]
    )
    control.close()
    studio.close()


def test_source_blueprint_worker_coalesces_duplicate_progress() -> None:
    class NoisyBlueprintService:
        @staticmethod
        def prepare(_project_id, progress):
            for _ in range(5_000):
                progress(4)
            for _ in range(5_000):
                progress(5)
            progress(3)
            progress(100)
            return "verified-blueprint"

    worker = SourceBlueprintWorker(NoisyBlueprintService(), "project")
    progress = []
    completed = []
    worker.signals.progress.connect(progress.append)
    worker.signals.complete.connect(completed.append)

    worker.execute()

    assert progress == [4, 5, 100]
    assert completed == ["verified-blueprint"]


def test_source_blueprint_preparation_starts_indeterminate_until_hash_bytes_arrive(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    control = BuildControlCenter(studio, auto_start=False)
    app.processEvents()
    started = []
    monkeypatch.setattr("romverse.ui.build_control.start_background", started.append)

    control._prepare_source_blueprint()

    assert started == [control.blueprint_worker]
    assert control.process_progress.maximum() == 0
    assert not control.process_progress.isTextVisible()
    assert "hashing exact local inputs" in control.status.text()

    control.blueprint_worker = None
    control.close()
    studio.close()


def test_build_control_can_render_a_new_report_without_reassessing(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    control = BuildControlCenter(studio, auto_start=False)
    app.processEvents()
    report = control.report
    assert report is not None
    control.service.assess = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("unexpected reassessment")
    )

    control.refresh(report)

    assert control.report is report
    control.close()
    studio.close()


def test_visible_build_control_refreshes_changed_evidence_without_window_focus(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    control = BuildControlCenter(studio, auto_start=False)
    control.show()
    app.processEvents()
    original = control.report
    assert original is not None
    updated = replace(
        original,
        gates=tuple(
            replace(
                gate,
                status=GateStatus.PASS,
                evidence="Protected OEM-signed source is byte-identical",
            )
            if gate.gate_id == "signer"
            else gate
            for gate in original.gates
        ),
        signing_ready=True,
        report_digest="f" * 64,
    )
    control.isActiveWindow = lambda: False
    control.service.assess = lambda *_args, **_kwargs: updated

    control._refresh_if_evidence_changed()

    assert control.report is updated
    assert "signer" not in control.resolve_buttons
    control.close()
    studio.close()


def test_guided_backup_entry_never_advances_flash_review(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    control = BuildControlCenter(studio, auto_start=False)
    app.processEvents()
    calls: list[tuple[tuple, dict]] = []
    control._show_final_handoff = lambda *args, **kwargs: calls.append((args, kwargs))

    control.start_guided_backup()

    assert calls == [(((),), {"backup_only": True})]
    control.close()
    studio.close()


def test_autopilot_prompts_for_user_backup_before_external_certification(
    tmp_path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    control = BuildControlCenter(studio, auto_start=False)
    prompted: list[bool] = []
    monkeypatch.setattr(control, "refresh", lambda: None)
    monkeypatch.setattr(control, "start_guided_backup", lambda: prompted.append(True))

    control._finish_autopilot(
        "A personal backup choice is required.",
        waiting_gate="user-backup",
    )
    app.processEvents()

    assert prompted == [True]
    control.close()
    studio.close()


def test_backup_receipt_resumes_readiness_instead_of_assuming_flash_ready(
    tmp_path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    control = BuildControlCenter(studio, auto_start=False)
    events: list[str] = []
    monkeypatch.setattr(control, "refresh", lambda: events.append("refresh"))
    monkeypatch.setattr(control, "_start_autopilot", lambda: events.append("autopilot"))

    control._resume_after_backup()

    assert events == ["refresh", "autopilot"]
    assert "reassessing" in control.status.text()
    assert "phone changed: NO" in control.status.text()
    control.close()
    studio.close()


def test_forge_backup_worker_reports_truthful_privacy_safe_live_console_failure(
    tmp_path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    studio.live_console_store = LiveConsoleEventStore(studio.store.workspace)
    control = BuildControlCenter(studio, auto_start=False)
    workers = []
    monkeypatch.setattr("romverse.ui.build_control.start_background", workers.append)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args, **_kwargs: None)
    private_source = tmp_path / "private-user-backup.zip"
    private_source.write_bytes(b"backup")

    control._verify_handoff_backup(private_source)

    assert workers == [control.recovery_worker]
    running = studio.live_console_store.list_recent()[0]
    assert running.state is MissionState.RUNNING
    assert running.stage == "forge-external-backup"
    assert running.project_id == control.project.project_id
    assert "unlock" in running.explanation
    control.recovery_worker.signals.progress.emit(43)
    progressed = studio.live_console_store.list_recent()[0]
    assert progressed.progress_percent == 43

    control._handoff_backup_failed(
        "/home/steve/Private/phone-bbb7782c.zip failed for serial bbb7782c"
    )

    terminal = studio.live_console_store.list_recent()[0]
    public_copy = " ".join(
        (terminal.title, terminal.summary, terminal.explanation, terminal.next_action)
    )
    assert terminal.state is MissionState.FAILED
    assert terminal.confidence.value == "verified"
    assert "/home/steve" not in public_copy
    assert "bbb7782c" not in public_copy
    assert "shared console excludes private paths" in public_copy
    control.close()
    studio.close()


def test_source_blueprint_worker_routes_measured_failure_to_live_console(
    tmp_path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    studio.live_console_store = LiveConsoleEventStore(studio.store.workspace)
    control = BuildControlCenter(studio, auto_start=False)
    workers = []
    monkeypatch.setattr("romverse.ui.build_control.start_background", workers.append)
    monkeypatch.setattr(control, "_source_online_guidance", lambda *_args, **_kwargs: None)

    control._prepare_source_blueprint()

    assert workers == [control.blueprint_worker]
    assert studio.live_console_store.list_recent()[0].stage == "forge-source-blueprint"
    control.blueprint_worker.signals.progress.emit(57)
    assert studio.live_console_store.list_recent()[0].progress_percent == 57
    control._source_blueprint_failed("/home/steve/Private/source.zip exposed serial bbb7782c")

    terminal = studio.live_console_store.list_recent()[0]
    shared = " ".join(
        (terminal.title, terminal.summary, terminal.explanation, terminal.next_action)
    )
    assert terminal.state is MissionState.FAILED
    assert terminal.progress_percent == 57
    assert "/home/steve" not in shared
    assert "bbb7782c" not in shared
    control.close()
    studio.close()


def test_all_forge_preparation_missions_require_explicit_terminal_outcomes(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    studio.live_console_store = LiveConsoleEventStore(studio.store.workspace)
    control = BuildControlCenter(studio, auto_start=False)
    stages = (
        "forge-build-inputs",
        "forge-local-candidate",
        "forge-avb-topology",
        "offline-signing-export",
        "offline-signing-import",
    )

    for stage in stages:
        control._start_preparation_console(stage)
        assert studio.live_console_store.list_recent()[0].state is MissionState.RUNNING
        control._finish_preparation_console(stage, MissionState.SUCCEEDED)
        terminal = studio.live_console_store.list_recent()[0]
        assert terminal.state is MissionState.SUCCEEDED
        assert terminal.progress_percent == 100
        assert terminal.confidence.value == "verified"

    assert len(studio.live_console_store.list_recent()) == len(stages) * 2
    control.close()
    studio.close()


def test_invalid_forge_completion_payload_becomes_failure_not_success(
    tmp_path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    studio.live_console_store = LiveConsoleEventStore(studio.store.workspace)
    control = BuildControlCenter(studio, auto_start=False)
    monkeypatch.setattr(control, "_source_online_guidance", lambda *_args, **_kwargs: None)
    control.blueprint_worker = SimpleNamespace()
    control._start_preparation_console("forge-source-blueprint")

    control._source_blueprint_complete(object())

    terminal = studio.live_console_store.list_recent()[0]
    assert terminal.state is MissionState.FAILED
    assert "without a success receipt" in terminal.summary
    assert not control.preparation_missions
    control.close()
    studio.close()


def test_backup_completion_dialog_never_claims_unready_project_is_ready(
    tmp_path,
    monkeypatch,
) -> None:
    QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    control = BuildControlCenter(studio, auto_start=False)
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        "romverse.ui.build_control.RecoveryEvidenceService.assess",
        lambda *_args, **_kwargs: SimpleNamespace(external_backup_ready=True),
    )

    def capture_dialog(dialog: QMessageBox) -> int:
        captured["title"] = dialog.windowTitle()
        captured["text"] = dialog.text()
        captured["detail"] = dialog.informativeText()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", capture_dialog)

    control._show_final_handoff(())

    assert "not yet flash-ready" in captured["text"]
    assert "remaining readiness evidence" in captured["detail"]
    assert "will not invent" in captured["detail"]
    assert "ready for the Guardian stage" not in captured["text"]
    control.close()
    studio.close()


def test_existing_cloud_confirmation_never_hides_local_drive_backup_route(
    tmp_path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        marketing_name="Xiaomi 17 Pro Max",
        codename="popsicle",
    )
    studio.devices = [device]
    project_id = studio.projects[0].project_id
    BackupHandoffService(studio.store).confirm_cloud(
        project_id,
        device,
        CloudBackupProvider.GOOGLE,
        "Completed today at 15:42",
        backup_completed=True,
        restore_access_confirmed=True,
        critical_data_scope_reviewed=True,
        limitations_acknowledged=True,
    )
    seen_buttons: list[str] = []

    def capture_buttons(dialog: QMessageBox) -> int:
        seen_buttons.extend(button.text() for button in dialog.buttons())
        return 0

    monkeypatch.setattr(QMessageBox, "exec", capture_buttons)
    control = BuildControlCenter(studio, auto_start=False)
    app.processEvents()

    control.start_guided_backup()

    assert "Back up to local drive…" in seen_buttons
    assert "Verify local backup file…" in seen_buttons
    assert "Confirm cloud backup…" in seen_buttons
    control.close()
    studio.close()


def test_local_drive_backup_is_the_highlighted_recommended_route(
    tmp_path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    control = BuildControlCenter(studio, auto_start=False)
    app.processEvents()
    captured: dict[str, object] = {}

    def capture_dialog(dialog: QMessageBox) -> int:
        local = next(
            button for button in dialog.buttons() if button.text() == "Back up to local drive…"
        )
        captured["object_name"] = local.objectName()
        captured["default"] = local.isDefault()
        captured["tooltip"] = local.toolTip()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", capture_dialog)

    control.start_guided_backup()

    assert captured["object_name"] == "Primary"
    assert captured["default"] is True
    assert "hash" in str(captured["tooltip"]).casefold()
    control.close()
    studio.close()


def test_backup_attention_card_opens_chooser_directly(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    control = BuildControlCenter(studio, auto_start=False)
    app.processEvents()
    calls: list[bool] = []
    control.start_guided_backup = lambda: calls.append(True)

    control.resolve_buttons["user-backup"].click()
    app.processEvents()

    assert calls == [True]
    control.close()
    studio.close()


def test_cloud_backup_confirmation_requires_status_and_every_explicit_check() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = CloudBackupConfirmationDialog("Xiaomi 17 Pro Max")
    app.processEvents()

    assert not dialog.confirm_button.isEnabled()
    dialog.last_backup.setText("Completed today at 3:42 PM")
    for check in dialog.checks:
        check.setChecked(True)
    app.processEvents()

    assert dialog.confirm_button.isEnabled()
    dialog.close()


def test_phone_backup_guide_is_provider_specific_and_hands_selection_forward() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = PhoneBackupGuideDialog("Xiaomi 17 Pro Max")
    dialog.provider.setCurrentIndex(dialog.provider.findData(CloudBackupProvider.XIAOMI))
    app.processEvents()

    assert "Xiaomi Account" in dialog.steps.text()
    assert "cannot inspect" in dialog.findChildren(QLabel)[1].text()
    assert dialog.finished_button.text() == "Continue after backup completes"

    confirmation = CloudBackupConfirmationDialog(
        "Xiaomi 17 Pro Max",
        selected_provider=CloudBackupProvider.XIAOMI,
    )
    assert (
        CloudBackupProvider(str(confirmation.provider.currentData())) is CloudBackupProvider.XIAOMI
    )
    confirmation.close()
    dialog.close()


def test_local_drive_backup_dialog_requires_destination_and_explicit_scope(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    dialog = PhoneMediaBackupDialog("Xiaomi 17 Pro Max")
    for check in dialog.scope_checks.values():
        check.setChecked(False)
    dialog.destination.setText(str(tmp_path))
    dialog._update_ready()
    app.processEvents()
    assert not dialog.start_button.isEnabled()

    dialog.scope_checks[next(iter(dialog.scope_checks))].setChecked(True)
    app.processEvents()
    assert dialog.start_button.isEnabled()
    assert "local drive" in dialog.windowTitle().casefold()
    dialog.close()


def test_local_drive_backup_dialog_preselects_saved_destination(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    dialog = PhoneMediaBackupDialog(
        "Xiaomi 17 Pro Max",
        default_destination=tmp_path,
    )
    app.processEvents()

    assert dialog.destination.text() == str(tmp_path)
    assert dialog.start_button.isEnabled()
    assert "Available at destination" in dialog.free_space.text()
    dialog.close()


def test_guardian_flash_mode_choices_are_explicit_and_exclusive() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = GuardianFlashModeDialog("Xiaomi 17 Pro Max")
    app.processEvents()

    assert not dialog.dirty.isChecked()
    assert not dialog.clean.isChecked()
    assert not dialog.review_button.isEnabled()
    title = next(
        label.text() for label in dialog.findChildren(QLabel) if "FORGE COMPLETE" in label.text()
    )
    assert "ASCENSION" not in title
    assert "PROJECT IS READY" in title
    dialog.clean.setChecked(True)
    app.processEvents()
    assert dialog.clean.isChecked()
    assert not dialog.dirty.isChecked()
    assert dialog.review_button.isEnabled()
    assert FlashMode.CLEAN_WIPE_DATA.display_name.startswith("Clean flash")
    dialog.close()


def test_guardian_manifest_review_is_truthful_and_has_no_consent_control() -> None:
    app = QApplication.instance() or QApplication([])
    manifest = GuardianManifestReview(
        1,
        "a" * 32,
        "2026-08-31T00:00:00+00:00",
        "project",
        "b" * 64,
        "c" * 64,
        "d" * 64,
        "e" * 20,
        "Xiaomi 17 Pro Max",
        "2509FPN0BC",
        "popsicle",
        FlashMode.DIRTY_KEEP_DATA,
        True,
        False,
        "xiaomi.popsicle",
        "1",
        "f" * 64,
        (
            GuardianManifestCheck(
                "partition-write-contract",
                "Exact partition-write contract",
                ManifestReviewState.BLOCKED,
                "Reference-only evidence",
                "Attach a signed exact-build contract.",
            ),
        ),
        (),
        ("No exact write contract.",),
        "blocked-missing-exact-write-contract",
        False,
        "none",
        False,
        False,
        (),
        "",
        "1" * 64,
    )
    dialog = GuardianManifestReviewDialog(manifest)
    app.processEvents()
    texts = [label.text() for label in dialog.findChildren(QLabel)]
    buttons = [button.text() for button in dialog.findChildren(QPushButton)]

    assert any("EXECUTION LOCKED" in text for text in texts)
    assert any("PARTITION WRITES • NONE AUTHORIZED" in text for text in texts)
    assert any("BOOTLOADER RELOCK: NEVER" in text for text in texts)
    assert buttons == ["Return to Genesis"]
    dialog.close()

    bound = GuardianBoundArtifact(
        1,
        "super",
        "super.img",
        "working_roms/project/build-candidates/one/super.img",
        "2" * 64,
        4096,
        123456789,
        DeviceWriteTransport.FASTBOOTD,
        "none",
        True,
        "verified-local-build",
        "3" * 64,
    )
    bound_dialog = GuardianManifestReviewDialog(
        replace(
            manifest,
            schema_version=2,
            partition_writes=(bound,),
            review_status="artifact-bound-review-only",
            artifact_binding_digest="4" * 64,
        )
    )
    app.processEvents()
    bound_texts = [label.text() for label in bound_dialog.findChildren(QLabel)]
    assert any("1 HASH-BOUND FOR REVIEW • NONE AUTHORIZED" in text for text in bound_texts)
    assert any("super  ←  super.img" in text for text in bound_texts)
    assert [button.text() for button in bound_dialog.findChildren(QPushButton)] == [
        "Return to Genesis"
    ]
    bound_dialog.close()


def test_online_research_completion_is_reported_truthfully_to_live_console(tmp_path) -> None:
    _app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    studio.live_console_store = LiveConsoleEventStore(studio.store.workspace)
    control = BuildControlCenter(studio, auto_start=False)
    started = studio.live_console_store.start(
        source="ROMVERSE Intelligence",
        stage="online-remediation",
        title="Research verified repair evidence",
        summary="Research started.",
        explanation="Remote text has no execution authority.",
        next_action="Wait for evidence checks.",
        project_id=control.project.project_id,
    )
    control.online_mission_id = started.mission_id
    receipt = OnlineRemediationService(studio.store.workspace).lookup(
        ErrorFingerprint.create("payload.bin extraction failed", category="source")
    )

    control._online_guidance_complete(receipt)

    latest = studio.live_console_store.list_recent()[0]
    assert latest.state is MissionState.SUCCEEDED
    assert latest.source == "ROMVERSE Intelligence"
    assert "source-attributed" in latest.summary
    assert latest.evidence_refs == (
        f"knowledge/online-remediation/{receipt.fingerprint.fingerprint_id}.romverse",
    )
    assert "execution authority" in control.status.toolTip()
    assert "FRESHNESS:" in control.status.toolTip()
    assert "CORROBORATION:" in control.status.toolTip()
    assert "SCOPE:" in control.status.toolTip()
    assert "CONFIDENCE:" in control.status.toolTip()
    control.close()
    studio.close()


def test_verified_typed_build_fix_becomes_private_archives_learning(
    tmp_path,
    monkeypatch,
) -> None:
    _app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    studio.app_settings = AppSettings(synapse_contributions_enabled=True)
    control = BuildControlCenter(studio, auto_start=False)
    fingerprint = ErrorFingerprint.create(
        "payload.bin extraction failed",
        category="source",
        source_kind="payload-bin",
        codename="popsicle",
        tool_name="Payload Dumper",
        tool_version="2.0.2",
    )
    control.online_receipt = OnlineRemediationService(studio.store.workspace).lookup(fingerprint)
    assert any(
        candidate.local_action_id == "inspect-payload-source"
        for candidate in control.online_receipt.candidates
    )
    monkeypatch.setattr(
        OnlineRemediationService,
        "record_verified_outcome",
        lambda *_args, **_kwargs: SimpleNamespace(outcome_digest="d" * 64),
    )

    control._record_online_fix_success(
        ("inspect-payload-source",),
        "b" * 64,
        "Typed payload inspection completed and verified exact source evidence.",
        f"projects/{control.project.project_id}/source-blueprint.romverse",
        "romverse.source-blueprint",
    )

    learned = SynapseStore(studio.store.workspace).list_knowledge()
    assert len(learned) == 1
    assert learned[0].state is SynapseKnowledgeState.VERIFIED_SUCCESS
    assert learned[0].scope.operation == "source"
    assert learned[0].scope.source_kind == "payload-bin"
    assert learned[0].scope.device_codename == "popsicle"
    assert learned[0].scope.tool_name == "payload-dumper"
    assert learned[0].execution_authority == "guidance-only"
    assert "ONLINE FIX VERIFIED WORKING" in control.status.text()
    control.close()
    studio.close()


def test_online_research_fingerprint_binds_only_verified_tool_runtime_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    _app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    studio.set_tool_statuses(
        tuple(
            ToolStatus("AVBTool", True, "/verified/avbtool", "avbtool 1.4.3", "Ready")
            if item.name == "AVBTool"
            else item
            for item in studio.tool_statuses
        )
    )
    control = BuildControlCenter(studio, auto_start=False)
    monkeypatch.setattr("romverse.ui.build_control.start_background", lambda _worker: None)

    control._source_online_guidance(
        "avbtool could not parse the exact vbmeta image",
        "avb",
        tool_name="AVBTool",
    )

    assert control.online_worker is not None
    assert control.online_worker.fingerprint.tool_name == "AVBTool"
    assert control.online_worker.fingerprint.tool_version == "avbtool 1.4.3"
    assert "/verified/avbtool" not in control.online_worker.fingerprint.query
    control.online_worker = None
    control.close()
    studio.close()


def test_online_research_does_not_claim_unverified_tool_identity(tmp_path) -> None:
    _app = QApplication.instance() or QApplication([])
    studio = _studio(tmp_path)
    control = BuildControlCenter(studio, auto_start=False)

    assert control._verified_tool_evidence("AVBTool") == ("", "")
    assert control._verified_tool_evidence("unknown tool") == ("", "")
    control.close()
    studio.close()
