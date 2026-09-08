from __future__ import annotations

import os
import time
import zipfile
from dataclasses import replace
from importlib.resources import files
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from romverse.ascension.entry import AscensionEntryBrief, AscensionEntryState
from romverse.ascension.models import AscensionMethod
from romverse.core.settings import AppSettings, ExperienceMode
from romverse.device.dna import CapabilityState
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.manifest_review import GuardianManifestReviewService
from romverse.infrastructure.provisioning import GENESIS_REQUIRED_TOOLS
from romverse.infrastructure.tools import ToolStatus
from romverse.intelligence.online_remediation import ErrorFingerprint, OnlineRemediationService
from romverse.nexus.compatibility import CompatibilityStatus
from romverse.nexus.events import LiveConsoleEventStore, MissionState
from romverse.rom.builds import RomBuildPlanner
from romverse.rom.forge import ForgeBundleService
from romverse.rom.guided import (
    GuidedContext,
    GuidedMissionEngine,
    GuidedMissionState,
    GuidedMissionStore,
    GuidedStageStatus,
)
from romverse.rom.inspection import RomInspectionService
from romverse.rom.models import ArtifactVerification
from romverse.rom.projects import RomProjectStore
from romverse.rom.recipes import (
    RecipeDraftStore,
    RecipeExecutor,
    RecipeStep,
    RecipeStore,
    RomRecipe,
)
from romverse.ui.companion_center import CompanionCenter
from romverse.ui.guided_mission import GENESIS_STAGE_ACTIONS, GuidedBuildMission
from romverse.ui.guided_recipe import RecipeForgeSequence
from romverse.ui.knowledge_center import KnowledgeGuideDialog
from romverse.ui.partition_workspace import PartitionWorkspace, _filesystem_required_tools
from romverse.ui.rom_studio import (
    FirmwareImportResult,
    ProjectNameDialog,
    ProjectWorker,
    RomStudio,
)
from tests.test_guardian_manifest_review import _prepared as _prepared_guardian_manifest


def test_new_project_dialog_opens_readable_and_validates_name() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = ProjectNameDialog()

    assert dialog.minimumWidth() >= 620
    assert dialog.minimumHeight() >= 340
    assert dialog.windowTitle() == "New ROMVERSE project"
    assert not dialog.create_button.isEnabled()

    dialog.name_input.setText("  HyperOS 4 daily driver  ")
    app.processEvents()

    assert dialog.create_button.isEnabled()
    assert dialog.project_name == "HyperOS 4 daily driver"
    assert dialog.hint.text() == "Ready to create"
    dialog.close()


def test_rom_studio_project_card_uses_authoritative_genesis_state_and_ignores_legacy_summary(
    tmp_path,
):
    app = QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Genesis progress")
    project_dir = store.projects_root / project.project_id
    (project_dir / "guided-state.json").write_text(
        '{"completed_steps": 7, "total_steps": 7}', encoding="utf-8"
    )
    GuidedMissionStore(project_dir).save(
        GuidedMissionState(selected_stage="debloat", root_choice="skip")
    )

    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    app.processEvents()

    assert "GENESIS • 2/15 • FIRMWARE" in studio.project_list.item(0).text()
    GuidedMissionStore(project_dir).save(
        GuidedMissionState(
            selected_stage="debloat",
            last_error="A verified prerequisite needs attention",
            root_choice="skip",
        )
    )
    studio.refresh(project.project_id)
    app.processEvents()
    assert "GENESIS • ATTENTION" in studio.project_list.item(0).text()
    studio.close()


def test_recovery_bay_solution_binds_exact_project_source_without_starting_worker(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "phone-ota.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"CrAU fixture")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Smart source review")
    project = store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    fingerprint = ErrorFingerprint.create("payload.bin OTA update engine")
    receipt = OnlineRemediationService(store.workspace).lookup(fingerprint)
    lead = receipt.candidates[0]
    assert lead.local_action_id == "inspect-payload-source"

    assert studio.open_repair_solution_handoff(
        lead.local_action_id,
        receipt.fingerprint.fingerprint_id,
        receipt.receipt_digest,
        lead.source_id,
        receipt,
    )
    app.processEvents()

    assert studio._pending_repair_solution == (
        "inspect-payload-source",
        receipt.fingerprint.fingerprint_id,
        receipt.receipt_digest,
        lead.source_id,
        project.project_id,
        project.original.sha256,
        receipt,
    )
    assert "RECOVERY BAY SMART SOLUTION" in studio.dashboard_handoff_eyebrow.text()
    assert project.original.sha256[:16] in studio.dashboard_handoff_detail.text()
    assert "NO DIALOG, WORKER, BUILD, FLASH, OR PHONE ACTION STARTED" in (
        studio.dashboard_handoff_detail.text()
    )
    assert studio.worker is None
    assert not studio.open_repair_solution_handoff(
        "run-community-command",
        "a" * 64,
        "b" * 64,
        "community.report",
        receipt,
    )
    studio.close()


def test_genesis_flight_plan_uses_the_same_evidence_assessment_as_the_sequence(tmp_path):
    QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Flight plan truth")
    GuidedMissionStore(store.projects_root / project.project_id).save(
        GuidedMissionState(root_choice="skip")
    )
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)

    context = studio.guided_context()
    assessments = GuidedMissionEngine().assess(context)
    current = assessments[GuidedMissionEngine.current_index(assessments)]
    plan = studio.genesis_flight_plan()

    assert plan.project_name == "Flight plan truth"
    assert plan.stage_number == current.stage.number == 2
    assert plan.stage_title == current.stage.title
    assert plan.status is current.status is GuidedStageStatus.READY
    assert plan.progress_percent == GuidedMissionEngine.progress(assessments) == 13
    assert plan.verified_stages == 2
    assert plan.root_route == "Unrooted build"
    assert not plan.recovery_ready
    assert not plan.guardian_ready
    studio.close()


def test_rom_studio_refreshes_project_and_genesis_handoff_after_modal_journey(
    tmp_path, monkeypatch
):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "boot.img"
    source.write_bytes(b"ANDROID!" + b"\0" * 4096)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Modal continuity")
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    completions = []
    studio.operation_completed.connect(lambda operation, result: completions.append(operation))

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(source), ""),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        "romverse.ui.rom_studio.start_background",
        lambda worker: worker.run(),
    )

    def complete_one_real_genesis_stage() -> None:
        mission = app.activeModalWidget()
        assert isinstance(mission, GuidedBuildMission)
        assert mission.selected_index == 1
        mission._run_stage()
        assert mission.selected_index == 3
        mission.accept()

    QTimer.singleShot(0, complete_one_real_genesis_stage)
    assert studio.open_dashboard_intent("Build ROM")
    app.processEvents()

    durable = GuidedMissionStore(store.projects_root / project.project_id).load()
    flight = studio.genesis_flight_plan()
    current = store.get(project.project_id)
    assert durable.selected_stage == "workspace"
    assert current.original is not None
    assert current.original.sha256 == studio.current_project.original.sha256
    assert flight.stage_number == 4
    assert "GENESIS • 4/15 • WORKING LAB" in studio.project_list.item(0).text()
    assert "Stage 4/15: Prepare an isolated working tree" in (
        studio.dashboard_handoff_detail.text()
    )
    assert studio.dashboard_handoff_badge.text() == "CURRENT STAGE"
    assert completions == ["import"]
    assert len(tuple(store.originals_root.iterdir())) == 1
    assert RomBuildPlanner(store).load(project.project_id) is None
    assert studio.worker is None
    assert studio.devices == []
    studio.close()


def test_rom_studio_refresh_never_recursively_rescans_an_extracted_tree(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    source = tmp_path / "firmware.zip"
    with zipfile.ZipFile(source, "w") as output:
        output.writestr("IMAGES/system.img", b"system")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Responsive tree").project_id, source)
    RomInspectionService(store).extract_project_tree(project.project_id)

    def forbidden_scan(*_args, **_kwargs):
        raise AssertionError("Desktop refresh attempted a recursive working-tree scan")

    monkeypatch.setattr(RomInspectionService, "summarize_working_tree", forbidden_scan)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)

    assert studio.inspection.working_tree_exists(project.project_id)
    assert "Working tree" in studio.project_meta.text()
    assert "Tree inventory" in studio.time_machine_detail.text()
    studio.close()


def test_rom_studio_command_deck_handoffs_report_exact_ready_workflows(
    tmp_path,
    monkeypatch,
):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "firmware.zip"
    with zipfile.ZipFile(source, "w") as output:
        output.writestr("system/build.prop", b"ro.romverse=verified\n")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Handoff Project").project_id, source)
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    store.create_working_copy(project.project_id)
    inspection.extract_project_tree(project.project_id)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    workers = []
    monkeypatch.setattr("romverse.ui.rom_studio.start_background", workers.append)

    assert studio.open_dashboard_intent("Pre-Build Simulation")
    app.processEvents()
    assert studio.command_tabs.currentIndex() == 1
    assert studio.dashboard_handoff_badge.text() == "SIMULATING"
    assert "freezing Handoff Project's exact current inputs" in (
        studio.dashboard_handoff_detail.text()
    )
    assert "no build" in studio.dashboard_handoff_detail.text()
    assert len(workers) == 1 and workers[0].operation == "plan"

    workers.pop(0).run()
    app.processEvents()

    assert len(workers) == 1 and workers[0].operation == "verify-plan"
    assert studio.dashboard_handoff_badge.text() == "VERIFYING"

    workers.pop(0).run()
    app.processEvents()

    assert studio.dashboard_handoff_badge.text() == "VERIFIED"
    assert studio.dashboard_handoff_title.text() == "Pre-Build Simulation → Dry run complete"
    assert "execution-locked" in studio.dashboard_handoff_detail.text()
    assert "Forge Bundle is the next intentional local action" in (
        studio.dashboard_handoff_detail.text()
    )
    assert "unsigned, non-bootable, non-flashable" in studio.dashboard_handoff_detail.text()
    assert studio.forge_button.isEnabled()
    assert studio.focusWidget() is studio.forge_button
    assert ForgeBundleService(store).load_receipt(project.project_id) is None
    assert RomBuildPlanner(store).load(project.project_id) is not None
    assert studio.worker is None

    assert studio.open_dashboard_intent("Pre-Build Simulation")
    app.processEvents()
    assert len(workers) == 1 and workers[0].operation == "verify-plan"
    assert studio.dashboard_handoff_badge.text() == "VERIFYING"

    workers.pop(0).run()
    app.processEvents()

    assert workers == []
    assert studio.dashboard_handoff_badge.text() == "VERIFIED"
    assert "Saved typed result for Handoff Project" in studio.dashboard_handoff_detail.text()
    assert studio.focusWidget() is studio.forge_button
    assert ForgeBundleService(store).load_receipt(project.project_id) is None
    assert studio.worker is None

    interrupted = store.projects_root / project.project_id / "build-plan.tmp"
    interrupted.write_text("unfinished dry run\n", encoding="utf-8")
    assert studio.open_dashboard_intent("Pre-Build Simulation")
    app.processEvents()
    assert workers == []
    assert interrupted.is_file()
    assert studio.dashboard_handoff_title.text() == (
        "Pre-Build Simulation → Interrupted dry run needs attention"
    )
    assert "completion is unknown" in studio.dashboard_handoff_detail.text()
    assert "did not retry" in studio.dashboard_handoff_detail.text()
    assert studio.worker is None

    assert studio.open_dashboard_intent("Recipes")
    app.processEvents()
    assert studio.command_tabs.currentIndex() == 2
    assert studio.dashboard_handoff_badge.text() == "READY"
    assert "Handoff Project is ready for Recipe Forge" in (studio.dashboard_handoff_detail.text())
    assert "Nothing changes until explicit approval" in (studio.dashboard_handoff_detail.text())
    assert studio.worker is None
    assert not studio.open_dashboard_intent("Unknown workflow")
    studio.close()


def test_partition_atlas_uses_honest_shared_progress_states(tmp_path):
    QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Partition progress")
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    atlas = PartitionWorkspace(studio)

    atlas._operation_started("scan-payload")
    assert not atlas.progress.isHidden()
    assert atlas.progress.minimum() == 0
    assert atlas.progress.maximum() == 0
    assert not atlas.progress.isTextVisible()

    atlas._operation_started("extract-payload")
    assert atlas.progress.minimum() == 0
    assert atlas.progress.maximum() == 0
    assert "Measured output-byte verification" in atlas.detail.text()
    atlas._operation_progress("extract-payload", 37)
    assert atlas.progress.maximum() == 100
    assert atlas.progress.value() == 37

    atlas._operation_failed("extract-payload", "fixture stopped")
    assert atlas.progress.isHidden()
    assert "stopped safely" in atlas.detail.text()
    atlas.close()
    studio.close()


def test_partition_atlas_routes_source_avb_inspection_without_phone_authority(tmp_path):
    QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Source AVB route")
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    partitions = tuple(
        SimpleNamespace(
            name=name,
            estimated_bytes=4096,
            category="Firmware / boot chain",
            recommended=False,
            critical=True,
            extracted_path=f"working/{name}.img",
            actual_bytes=4096,
            sha256="a" * 64,
            image_format="AVB metadata",
        )
        for name in ("vbmeta", "vbmeta_system")
    )

    class Payloads:
        def load(self, _project_id):
            return SimpleNamespace(partitions=partitions)

        def plan_extraction(self, _project_id, selected):
            return SimpleNamespace(safe=bool(selected), reason="Local extraction is safe")

    class Filesystems:
        def load(self, _project_id, _partition):
            return None

    class SourceAvb:
        def load(self, _project_id):
            return SimpleNamespace(signing_identity_consistent=True)

    studio.payload_service = Payloads()
    studio.filesystem_service = Filesystems()
    studio.source_avb_service = SourceAvb()
    operations = []
    studio._start_worker = lambda operation, **options: operations.append((operation, options))
    atlas = PartitionWorkspace(studio)

    assert atlas.source_avb_state.text() == "CONSISTENT"
    assert atlas.avb_button.isEnabled()
    assert atlas.avb_button.text() == "Reinspect source AVB"
    assert "does not sign, flash" in atlas.avb_button.toolTip()

    atlas._inspect_source_avb()

    assert operations == [("inspect-source-avb", {})]
    atlas._operation_started("inspect-source-avb")
    assert atlas.busy
    assert "source evidence only" in atlas.detail.text()
    atlas.close()
    studio.close()


def test_partition_atlas_resolves_its_missing_tool_and_continues(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    source = tmp_path / "ota.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"payload")
    project = store.create("Scoped partition tools")
    project = store.import_original(project.project_id, source)
    tree = store.working_root / project.project_id / "tree"
    tree.mkdir(parents=True)
    (tree / "payload.bin").write_bytes(b"payload")
    monkeypatch.setattr("romverse.ui.rom_studio.shutil.which", lambda _name: None)
    studio = RomStudio(
        store,
        DevicePackRegistry(()),
        (ToolStatus("Payload Dumper", False, detail="not installed"),),
    )
    studio.refresh(project.project_id)

    assert studio.partition_button.isEnabled()
    assert studio.partition_button.text() == "Resolve Partition tools"

    setup_calls = []
    opened = []

    class StatusLabel:
        def setText(self, message):
            setup_calls.append(("purpose", message))

    class SetupDialog:
        last_message = ""
        status = StatusLabel()

        def __init__(self, _host, _statuses, _workspace, _parent, **options):
            setup_calls.append(("options", options))

        def setWindowTitle(self, title):
            setup_calls.append(("title", title))

        def exec(self):
            setup_calls.append(("exec", True))

    class Verifier:
        def __init__(self, *_args):
            pass

        def verify_extended(self):
            return (ToolStatus("Payload Dumper", True, "/bin/true", "fixture"),)

    class Atlas:
        def __init__(self, owner):
            opened.append(owner)

        def exec(self):
            opened.append("exec")

    monkeypatch.setattr("romverse.ui.toolchain_center.ToolchainSetupDialog", SetupDialog)
    monkeypatch.setattr(
        "romverse.ui.toolchain_center.activate_verified_managed_tools", lambda _workspace: ()
    )
    monkeypatch.setattr("romverse.ui.rom_studio.ToolVerifier", Verifier)
    monkeypatch.setattr("romverse.ui.partition_workspace.PartitionWorkspace", Atlas)

    studio._open_partition_workspace()
    app.processEvents()

    options = next(value for kind, value in setup_calls if kind == "options")
    assert options["required_names"] == ("Payload Dumper",)
    assert options["auto_start"]
    assert options["auto_close"]
    assert studio.payload_service is not None
    assert studio.partition_button.text() == "Partition Atlas"
    assert opened == [studio, "exec"]
    assert "verified" in studio.operation_status.text().casefold()
    studio.close()


def test_switching_to_empty_project_clears_prepared_project_actions(tmp_path):
    QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    source = tmp_path / "prepared.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"payload")
    prepared = store.create("Prepared")
    prepared = store.import_original(prepared.project_id, source)
    tree = store.working_root / prepared.project_id / "tree"
    tree.mkdir(parents=True)
    (tree / "payload.bin").write_bytes(b"payload")
    empty = store.create("Empty")
    studio = RomStudio(
        store,
        DevicePackRegistry(()),
        (ToolStatus("Payload Dumper", True, "/bin/true", "fixture"),),
    )
    studio.refresh(prepared.project_id)

    assert studio.new_recipe_button.isEnabled()
    assert studio.guided_recipe_button.isEnabled()
    assert studio.partition_button.isEnabled()

    empty_row = next(
        index
        for index, project in enumerate(studio.projects)
        if project.project_id == empty.project_id
    )
    studio.project_list.setCurrentRow(empty_row)

    assert not studio.new_recipe_button.isEnabled()
    assert not studio.guided_recipe_button.isEnabled()
    assert not studio.partition_button.isEnabled()
    assert not studio.recipe_button.isEnabled()
    assert not studio.add_step_button.isEnabled()
    assert not studio.rollback_button.isEnabled()
    assert not studio.replace_button.isEnabled()
    assert not studio.property_button.isEnabled()
    assert studio.partition_button.text() == "Partition Atlas"
    studio.close()


def test_partition_atlas_recognizes_nested_case_variant_from_sealed_tree_index(tmp_path):
    QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    source = tmp_path / "case-variant.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("OTA/PAYLOAD.BIN", b"payload")
    project = store.create("Case variant")
    project = store.import_original(project.project_id, source)
    tree = store.working_root / project.project_id / "tree" / "OTA"
    tree.mkdir(parents=True)
    (tree / "PAYLOAD.BIN").write_bytes(b"payload")
    inspection = RomInspectionService(store)
    summary = inspection.refresh_working_tree_summary(project.project_id)
    assert summary is not None
    assert summary.notable_files == ("OTA/PAYLOAD.BIN",)

    studio = RomStudio(
        store,
        DevicePackRegistry(()),
        (ToolStatus("Payload Dumper", True, "/bin/true", "fixture"),),
    )
    studio.refresh(project.project_id)

    assert studio.partition_button.isEnabled()
    assert studio.partition_button.text() == "Partition Atlas"
    studio.close()


def test_partition_atlas_resolves_exact_filesystem_reader_before_expansion(tmp_path):
    QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Filesystem resolver")
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    partition = SimpleNamespace(
        name="system",
        estimated_bytes=4096,
        category="Android filesystem",
        recommended=True,
        critical=False,
        extracted_path="working/system.img",
        actual_bytes=4096,
        sha256="a" * 64,
        image_format="ext4 filesystem",
    )

    class Payloads:
        def load(self, _project_id):
            return SimpleNamespace(partitions=(partition,))

        def plan_extraction(self, _project_id, selected):
            return SimpleNamespace(safe=bool(selected), reason="Local extraction is safe")

    class MissingFilesystem:
        def load(self, _project_id, _partition):
            return None

        def plan(self, _project_id, name):
            return SimpleNamespace(
                partition=name,
                image_format="ext4 filesystem",
                safe=False,
                reason="Required read-only extractor is unavailable for ext4 filesystem",
            )

    class ReadyFilesystem(MissingFilesystem):
        def plan(self, _project_id, name):
            return SimpleNamespace(
                partition=name,
                image_format="ext4 filesystem",
                safe=True,
                reason="Filesystem expansion budget verified",
            )

    studio.payload_service = Payloads()
    studio.filesystem_service = MissingFilesystem()
    atlas = PartitionWorkspace(studio)
    atlas.table.setCurrentCell(0, 0)
    atlas._update_filesystem_actions()

    assert atlas.expand_button.isEnabled()
    assert atlas.expand_button.text() == "Resolve filesystem tools"
    assert _filesystem_required_tools("ext4 filesystem") == ("EXT4 Browser",)
    assert _filesystem_required_tools("EROFS filesystem") == (
        "EROFS Verifier",
        "Fakeroot",
    )

    resolutions = []
    operations = []

    def resolve(required, **options):
        resolutions.append((required, options))
        studio.filesystem_service = ReadyFilesystem()
        return True

    studio._resolve_required_tools = resolve
    studio._start_worker = lambda operation, **options: operations.append((operation, options))
    atlas._expand_filesystem()

    assert resolutions[0][0] == ("EXT4 Browser",)
    assert resolutions[0][1]["parent"] is atlas
    assert operations == [("expand-filesystem", {"partitions": ("system",)})]
    atlas.close()
    studio.close()


def test_guardian_review_starts_indeterminate_until_real_binding_bytes_arrive(
    tmp_path, monkeypatch
):
    QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    studio = RomStudio(store, DevicePackRegistry(()))
    worker = ProjectWorker(store, "fixture", "verify")
    started = []
    monkeypatch.setattr("romverse.ui.rom_studio.start_background", started.append)

    studio._launch_worker(worker, "guardian-review")

    assert started == [worker]
    assert studio.progress.maximum() == 0
    assert not studio.progress.isTextVisible()
    assert "measured byte progress" in studio.operation_status.text()
    assert "without inventing" in studio.operation_status.text()

    studio.worker = None
    studio.close()


def test_import_and_detection_start_indeterminate_until_measured_copy_bytes_arrive(
    tmp_path, monkeypatch
):
    QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    studio = RomStudio(store, DevicePackRegistry(()))
    worker = ProjectWorker(store, "import", "fixture", tmp_path / "source.zip")
    started = []
    monkeypatch.setattr("romverse.ui.rom_studio.start_background", started.append)

    studio._launch_worker(worker, "import")

    assert started == [worker]
    assert studio.progress.maximum() == 0
    assert not studio.progress.isTextVisible()
    assert "measured byte progress" in studio.operation_status.text()
    assert "without inventing" in studio.operation_status.text()

    studio.worker = None
    extraction = ProjectWorker(store, "extract", "fixture")
    studio._launch_worker(extraction, "extract")
    assert started == [worker, extraction]
    assert studio.progress.maximum() == 0
    assert not studio.progress.isTextVisible()
    assert "measured extracted bytes" in studio.operation_status.text()

    studio.worker = None
    studio.close()


def test_genesis_surfaces_a_safe_recovery_state_when_progress_storage_is_linked(tmp_path):
    QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Linked progress")
    project_dir = store.projects_root / project.project_id
    outside = tmp_path / "outside-guided-mission.json"
    outside.write_text("{}", encoding="utf-8")
    (project_dir / GuidedMissionStore.NAME).symlink_to(outside)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    mission = GuidedBuildMission(studio)
    mission.selected_index = 1

    saved = mission._save_state()

    assert not saved
    assert mission.failure is not None
    assert mission.failure.title == "Genesis progress needs attention"
    assert "unchanged" in " ".join(mission.failure.recommendations)
    assert outside.read_text(encoding="utf-8") == "{}"
    requested: list[str] = []
    studio.knowledge_requested.connect(requested.append)
    mission._open_stage_learning()
    assert requested == []
    assert mission.result() == mission.DialogCode.Rejected
    mission.close()
    studio.close()


def test_rom_studio_creates_and_renders_device_dna_without_guessing(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "mystery-build.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"CrAU test")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("DNA UI").project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    app.processEvents()

    profile = studio.device_dna.profiles.load(project.project_id)
    assert profile is not None
    assert profile.fact("identity.model").value == "Unconfirmed"
    assert profile.capability("device_identity").state is CapabilityState.UNCONFIRMED
    assert "Capability Map" in studio.device_dna_detail.text()
    assert "Compatibility Matrix" in studio.device_dna_detail.text()
    assert "Offline Archives" in studio.device_dna_detail.text()
    assert "AUTOMATIC SCAN COMPLETE" in studio.device_dna_detail.text()
    assert "EXECUTION AUTHORITY: NONE" in studio.device_dna_detail.text()
    assert studio.compatibility.matrices.load(project.project_id) is not None
    assert "Bootloader relock: NEVER" in studio.device_dna_detail.text()
    assert "Firmware files are selected and supplied by you" in (
        studio.firmware_responsibility_notice.text()
    )

    studio.inspection.inspect_project(project.project_id)
    studio.refresh(project.project_id)
    strengthened = studio.device_dna.profiles.load(project.project_id)
    assert strengthened is not None
    assert strengthened.profile_id != profile.profile_id
    assert strengthened.capability("firmware_detection").state is CapabilityState.SUPPORTED
    studio.close()


def test_rom_studio_worker_failure_automatically_queries_offline_archives(tmp_path):
    QApplication.instance() or QApplication([])
    source = tmp_path / "failure-fixture.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"CrAU test")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Failure lookup").project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    reports = []
    studio.offline_knowledge_updated.connect(reports.append)
    studio._active_operation = "extract"
    studio._active_project_id = project.project_id

    studio._worker_failed("adb: error: more than one device/emulator")

    assert reports
    report = reports[-1]
    assert report.trigger == "build-failure"
    assert report.execution_authority == "none"
    assert report.matches[0].record.record_id == "catalog.adb-multiple-targets"
    assert "Offline Archives scanned" in studio.operation_status.text()
    assert "guidance only; no action started" in studio.operation_status.text().casefold()
    studio.close()


def test_rom_studio_renders_a_newer_same_device_firmware_as_an_upgrade_candidate(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "popsicle-ota_full-OS4.0.0.25.XPBCNXM-user-17.0-test.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"CrAU test")
        archive.writestr("META-INF/com/android/metadata", "ota-type=AB")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Upgrade UI").project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    studio.set_devices(
        [
            AndroidDevice(
                "private-serial",
                DeviceState.DEVICE,
                manufacturer="Xiaomi",
                model="2509FPN0BC",
                codename="popsicle",
                product="popsicle",
                rom_display="OS4.0.0.23.XPBCNXM",
            )
        ]
    )
    app.processEvents()

    assert (
        "Firmware relationship: UPGRADE CANDIDATE • OS4.0.0.23.XPBCNXM → OS4.0.0.25.XPBCNXM [high]"
    ) in studio.device_dna_detail.text()
    assert studio.upgrade_passport.property("upgradeState") == "verified"
    assert studio.upgrade_passport_status.text() == "NEWER EXACT-DEVICE CANDIDATE"
    assert "UPGRADE CANDIDATE" in studio.upgrade_passport_detail.text()
    assert "Install/flash: NO" in studio.upgrade_passport_detail.text()
    assert "Phone changed: NO" in studio.upgrade_passport_detail.text()
    profile = studio.device_dna.profiles.load(project.project_id)
    assert profile is not None
    assert profile.capability("guardian_flash").state is CapabilityState.UNCONFIRMED
    studio.close()


def test_firmware_import_worker_automatically_inspects_before_device_dna(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "unknown-auto-detect.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"CrAU test")
        archive.writestr("META-INF/com/android/metadata", "ota-type=AB")
    store = RomProjectStore(tmp_path / "workspace")
    store.CHUNK_SIZE = 8
    project = store.create("Automatic detection")
    completed = []
    progress = []
    worker = ProjectWorker(
        store,
        "import",
        project.project_id,
        source,
        RomInspectionService(store),
    )
    worker.signals.complete.connect(completed.append)
    worker.signals.progress.connect(progress.append)

    worker.run()

    assert len(completed) == 1
    result = completed[0]
    assert isinstance(result, FirmwareImportResult)
    assert result.project.original is not None
    assert result.inspection.partition_signals == ("ota_payload",)
    assert RomInspectionService(store).load_report(project.project_id) == result.inspection
    assert progress == sorted(progress)
    assert progress[-1] == 100
    assert any(0 < value < 100 for value in progress)
    assert 68 not in progress

    studio = RomStudio(store, DevicePackRegistry(()))
    app.processEvents()
    profile = studio.device_dna.profiles.load(project.project_id)
    assert profile is not None
    assert profile.capability("firmware_detection").state is CapabilityState.SUPPORTED
    assert profile.capability("source_adapter").state is CapabilityState.SUPPORTED
    assert "Android OTA payload" in studio.device_dna_detail.text()
    studio.close()


def test_rom_studio_surfaces_the_same_verified_source_blueprint_as_forge(
    tmp_path,
    monkeypatch,
):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "popsicle-ota_full-OS4.0.0.25.XPBCNXM-user-17.0-test.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"CrAU test")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Blueprint UI").project_id, source)
    blueprint = SimpleNamespace(
        project_id=project.project_id,
        source_archive_sha256=project.original.sha256,
        source_kind="ota-payload",
        baseline_candidate_ready=True,
        phone_changed=False,
        authority="project-local-build-evidence-only",
        blueprint_digest="a" * 64,
        plan_digest="b" * 64,
        manufacturer="Xiaomi",
        codename="popsicle",
        build_id="OS4.0.0.25.XPBCNXM",
        android_version="17",
        region="CN",
        partitions=(
            SimpleNamespace(name="system", estimated_bytes=3_000_000, image_format="unknown"),
        ),
    )
    monkeypatch.setattr(
        "romverse.device.dna.FirmwareSourceIntelligenceService.load",
        lambda _self, _project_id: blueprint,
    )

    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    app.processEvents()

    profile = studio.device_dna.profiles.load(project.project_id)
    assert profile is not None
    assert profile.capability("rom_build").state is CapabilityState.SUPPORTED
    assert "Source Intelligence" in studio.device_dna_detail.text()
    assert "Project-local Ota Payload blueprint" in studio.device_dna_detail.text()
    assert "Build preparation evidence only" in studio.device_dna_detail.text()
    assert "no device-write or flash authority" in studio.device_dna_detail.text()
    studio.close()


def test_project_worker_coalesces_duplicate_progress_before_it_reaches_the_ui(tmp_path):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Large archive progress")
    completed = []
    progress = []

    class NoisyInspection:
        @staticmethod
        def extract_project_tree(_project_id, progress):
            for _ in range(5_000):
                progress(4, 100)
            for _ in range(5_000):
                progress(5, 100)
            progress(3, 100)
            progress(995, 1_000)
            progress(100, 100)
            return tmp_path / "workspace" / "working" / _project_id / "tree"

    worker = ProjectWorker(
        store,
        "extract",
        project.project_id,
        inspection=NoisyInspection(),
    )
    worker.signals.complete.connect(completed.append)
    worker.signals.progress.connect(progress.append)

    worker.run()

    assert len(completed) == 1
    assert progress == [4, 5, 99, 100]


def test_recipe_worker_reports_completed_steps_and_finishes_after_project_receipt(tmp_path):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Measured recipe")
    tree = store.working_root / project.project_id / "tree"
    tree.mkdir(parents=True)
    for name in ("one.txt", "two.txt", "three.txt"):
        (tree / name).write_text(name, encoding="utf-8")
    recipe = RomRecipe(
        1,
        "measured-recipe",
        "Measured recipe",
        "",
        tuple(RecipeStep(name, "inspect", name) for name in ("one.txt", "two.txt", "three.txt")),
    )
    project_dir = store.projects_root / project.project_id
    RecipeStore().save(project_dir, recipe)
    receipt_path = project_dir / "latest-recipe-receipt.romverse"
    worker = ProjectWorker(store, "execute-recipe", project.project_id)
    progress = []
    terminal_receipt_state = []
    worker.signals.progress.connect(progress.append)
    worker.signals.progress.connect(
        lambda value: (
            terminal_receipt_state.append(receipt_path.is_file()) if value == 100 else None
        )
    )

    worker.run()

    assert progress == [33, 66, 100]
    assert terminal_receipt_state == [True]


def test_recipe_execution_starts_indeterminate_until_completed_step_count_arrives(
    tmp_path, monkeypatch
):
    QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    studio = RomStudio(store, DevicePackRegistry(()))
    worker = ProjectWorker(store, "execute-recipe", "fixture")
    started = []
    monkeypatch.setattr("romverse.ui.rom_studio.start_background", started.append)

    studio._launch_worker(worker, "execute-recipe")

    assert started == [worker]
    assert studio.progress.maximum() == 0
    assert not studio.progress.isTextVisible()
    assert "completed recipe steps" in studio.operation_status.text()

    studio.worker = None
    studio.close()


def test_rom_studio_enables_transactional_recipe_and_restore_workflow(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("system/build.prop", "ro.romverse=old\n")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("UI recipe")
    store.import_original(project.project_id, source)
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    store.create_working_copy(project.project_id)
    inspection.extract_project_tree(project.project_id)
    recipe = RomRecipe(
        1,
        "property",
        "Property",
        "",
        (
            RecipeStep(
                "step-1",
                "set_property",
                "system/build.prop",
                (("key", "ro.romverse"), ("value", "new")),
            ),
        ),
    )
    RecipeStore().save(store.projects_root / project.project_id, recipe)

    studio = RomStudio(store, DevicePackRegistry(()))
    app.processEvents()
    assert studio.recipe_button.isEnabled()
    assert studio.replace_button.text() == "Run approved recipe"
    assert studio.replace_button.isEnabled()
    assert not studio.property_button.isEnabled()
    assert studio.rollback_button.text() == "Open Time Machine"

    executor = RecipeExecutor()
    tree = store.working_root / project.project_id / "tree"
    approval = executor.issue_approval(recipe, tree)
    executor.execute_approved(
        recipe,
        tree,
        store.snapshots_root / project.project_id / "recipes",
        approval,
    )
    studio.refresh(project.project_id)
    app.processEvents()
    assert studio.property_button.text() == "Restore recipe snapshot"
    assert studio.property_button.isEnabled()
    studio.close()


def test_successful_working_copy_snapshot_and_preview_never_render_as_danger(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("system/build.prop", "ro.romverse=old\n")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Successful Studio states")
    store.import_original(project.project_id, source)
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)

    studio._start_worker("working-copy")
    _wait_for_studio(app, studio)
    assert studio.operation_status.objectName() == "Good"

    studio._start_worker("extract")
    _wait_for_studio(app, studio)
    studio._start_worker("snapshot")
    _wait_for_studio(app, studio)
    assert studio.operation_status.objectName() == "Good"

    recipe = RomRecipe(
        1,
        "inspect",
        "Inspect",
        "Read-only preview",
        (RecipeStep("step-1", "inspect", "system/build.prop", ()),),
    )
    RecipeStore().save(store.projects_root / project.project_id, recipe)
    studio._start_worker("preview-recipe")
    _wait_for_studio(app, studio)
    assert studio.operation_status.objectName() == "Good"
    assert "preview" in studio.operation_status.text().casefold()
    studio.close()


def test_rom_studio_automatically_recovers_an_interrupted_transaction_before_retry(
    tmp_path,
):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("system/build.prop", "ro.romverse=recover\n")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Recovery route").project_id, source)
    interrupted = store.working_root / project.project_id / ".original-baseline.bin.deadbeef.part"
    interrupted.parent.mkdir(parents=True, exist_ok=True)
    interrupted.write_bytes(b"incomplete")
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)

    studio._start_worker("working-copy")
    _wait_for_studio(app, studio)

    assert not interrupted.exists()
    assert studio.operation_status.objectName() == "Good"
    assert "Automatic recovery cleared 1 interrupted" in studio.operation_status.text()
    assert "Protected original: unchanged" in studio.operation_status.text()
    assert "phone: unchanged" in studio.operation_status.text()
    assert "relock: never" in studio.operation_status.text()
    studio.close()


def _wait_for_studio(app, studio: RomStudio) -> None:
    deadline = time.monotonic() + 3
    while studio.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert studio.worker is None


def test_guided_build_mission_is_full_size_and_evidence_driven(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    studio = RomStudio(store, DevicePackRegistry(()))
    mission = GuidedBuildMission(studio)
    app.processEvents()

    assert mission.minimumWidth() >= 980
    assert len(mission.stage_buttons) == 15
    assert mission.stage_buttons[8].stage_id == "root_choice"
    assert mission.stage_buttons[0].text().endswith("Project")
    assert mission.action_button.text() == "Create ROM project"
    assert not mission.next_button.isEnabled()
    assert not mission.skip_button.isVisible()
    assert mission.auto_button.text() == "Auto-resolve && continue"
    assert "safe local stages" in mission.auto_button.toolTip()
    assert mission.learn_button.text() == "Learn this stage"

    mission._operation_started("extract")
    assert not mission.process_frame.isHidden()
    assert mission.process_progress.minimum() == 0
    assert mission.process_progress.maximum() == 0
    mission._operation_progress("extract", 37)
    assert mission.process_progress.maximum() == 100
    assert mission.process_progress.value() == 37
    assert "37%" in mission.process_label.text()
    mission._operation_failed("extract", "test stop")
    assert mission.process_frame.isHidden()
    assert mission.state.last_error == "extract: test stop"

    mission._operation_completed("snapshot", object())
    assert "rejected unexpected or stale" in mission.state.last_error

    mission.close()
    studio.close()


def test_genesis_uses_task_evidence_action_hierarchy_and_responsive_layout(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    studio = RomStudio(store, DevicePackRegistry(()))
    mission = GuidedBuildMission(studio)
    mission.resize(1000, 700)
    mission.show()
    app.processEvents()

    assert mission.task_card.objectName() == "MissionTaskCard"
    assert mission.action_button.property("primary") is True
    assert mission.next_button.property("primary") is False
    assert mission.auto_button.objectName() == "MissionAutopilot"
    assert [button.phase.label for button in mission.phase_buttons] == [
        "SCAN",
        "MATCH",
        "BUILD",
        "VERIFY",
        "BACKUP",
        "FLASH",
        "DIAGNOSE",
    ]
    assert mission.rail_scroll.isHidden()
    assert mission.task_list_button.text() == "Show detailed tasks"
    assert mission.firmware_identity_title.text() == "No firmware selected"
    assert mission.device_identity_title.text() == "No device connected"
    assert mission.supporting_panel.isHidden()
    assert mission.details_button.text() == "Show evidence & guidance"
    assert mission.rail_scroll.width() == 238
    recommendation_index = mission.supporting_grid.indexOf(mission.recommendation_card)
    recommendation_position = mission.supporting_grid.getItemPosition(recommendation_index)
    assert recommendation_position[:2] == (1, 0)

    mission.details_button.click()
    assert not mission.supporting_panel.isHidden()
    assert mission.details_button.text() == "Hide evidence & guidance"

    mission.resize(1200, 790)
    app.processEvents()
    assert mission.rail_scroll.width() == 285
    recommendation_index = mission.supporting_grid.indexOf(mission.recommendation_card)
    recommendation_position = mission.supporting_grid.getItemPosition(recommendation_index)
    assert recommendation_position[:2] == (0, 1)

    mission.close()
    studio.close()


def test_genesis_expert_view_expands_evidence_and_reduced_motion_stays_static(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    settings = AppSettings(
        experience_mode=ExperienceMode.EXPERT,
        reduced_motion=True,
    )
    studio = RomStudio(store, DevicePackRegistry(()), app_settings=settings)
    mission = GuidedBuildMission(studio)
    mission.show()
    app.processEvents()

    assert mission.mode_badge.text() == "ARCHITECT  •  DEEP VIEW"
    assert not mission.rail_scroll.isHidden()
    assert mission.task_list_button.text() == "Hide detailed tasks"
    assert not mission.supporting_panel.isHidden()
    mission._select_stage(1)
    assert mission.task_effect.opacity() == 1.0

    mission.close()
    studio.close()


def test_every_advertised_genesis_stage_has_a_registered_ui_action() -> None:
    from romverse.rom.guided import STAGES

    assert {stage.action for stage in STAGES} == GENESIS_STAGE_ACTIONS


def test_genesis_opens_guardian_when_automatic_work_is_done_before_backup(
    tmp_path, monkeypatch
) -> None:
    QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Guardian handoff route")
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)

    class Readiness:
        local_candidate_ready = True
        signing_ready = True
        guardian_handoff_ready = True
        flash_ready = False

    monkeypatch.setattr(
        "romverse.ui.rom_studio.BuildReadinessService.assess",
        lambda *_args, **_kwargs: Readiness(),
    )

    context = studio.guided_context()

    assert context.guardian_handoff_ready
    assert not context.guardian_flash_handoff_ready
    studio.close()


def test_rom_studio_rejects_untyped_or_changed_terminal_evidence(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("system/build.prop", "ro.romverse=test\n")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Terminal evidence").project_id, source)
    saved = store.create_working_copy(project.project_id)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    failures: list[tuple[str, str]] = []
    completions: list[tuple[str, object]] = []
    studio.operation_failed.connect(
        lambda operation, message: failures.append((operation, message))
    )
    studio.operation_completed.connect(
        lambda operation, result: completions.append((operation, result))
    )

    studio.worker = ProjectWorker(store, "working-copy", project.project_id)
    studio._active_operation = "working-copy"
    studio._active_project_id = project.project_id
    studio._worker_complete(object())
    app.processEvents()

    assert failures[-1][0] == "working-copy"
    assert "unexpected or stale terminal evidence" in failures[-1][1]
    assert completions == []
    assert not studio.is_validated_completion("working-copy", saved)

    studio.worker = ProjectWorker(store, "working-copy", project.project_id)
    studio._active_operation = "working-copy"
    studio._active_project_id = project.project_id
    studio._worker_complete(replace(saved, current_sha256="0" * 64))
    app.processEvents()

    assert "changed working-copy evidence" in failures[-1][1]
    assert completions == []
    studio.close()


def test_simulation_rejects_forged_success_evidence_bound_to_another_tree(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("system/build.prop", "ro.romverse=test\n")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Forged verification").project_id, source)
    RomInspectionService(store).inspect_project(project.project_id)
    store.create_working_copy(project.project_id)
    RomInspectionService(store).extract_project_tree(project.project_id)
    plan = RomBuildPlanner(store).plan(project.project_id)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    failures: list[tuple[str, str]] = []
    studio.operation_failed.connect(
        lambda operation, message: failures.append((operation, message))
    )
    studio._automatic_simulation_verification_plan = plan
    studio.worker = ProjectWorker(store, "verify-plan", project.project_id)
    studio._active_operation = "verify-plan"
    studio._active_project_id = project.project_id

    studio._worker_complete(
        ArtifactVerification(
            True,
            "Working tree matches build plan",
            "0" * 64,
            "0" * 64,
        )
    )
    app.processEvents()

    assert failures == [
        ("verify-plan", "ROM Studio rejected mismatched build-plan verification evidence")
    ]
    assert studio.worker is None
    assert studio._automatic_simulation_verification_plan is None
    assert RomBuildPlanner(store).load(project.project_id) == plan
    assert studio.dashboard_handoff_title.text() == (
        "Pre-Build Simulation → Current tree needs attention"
    )
    assert studio.dashboard_handoff_badge.text() == "ATTENTION"
    assert "did not retry or infer success" in studio.dashboard_handoff_detail.text()
    assert "no build or phone action" in studio.dashboard_handoff_detail.text()
    studio.close()


def test_validated_guardian_completion_can_open_persistent_guardian_core(
    tmp_path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    store, project, registry, report, device = _prepared_guardian_manifest(tmp_path)
    manifest = GuardianManifestReviewService(store, registry).compile(
        project.project_id,
        report,
        device,
    )
    studio = RomStudio(store, registry)
    requested: list[tuple[str, str]] = []
    studio.guardian_review_requested.connect(
        lambda project_id, digest: requested.append((project_id, digest))
    )

    class ReviewDialog:
        def __init__(self, _manifest, _parent) -> None:
            self.open_guardian_core_requested = True

        def exec(self) -> int:
            return 1

    monkeypatch.setattr(
        "romverse.ui.build_control.GuardianManifestReviewDialog",
        ReviewDialog,
    )
    studio.worker = SimpleNamespace()
    studio._active_operation = "guardian-review"
    studio._active_project_id = project.project_id

    studio._worker_complete(manifest)
    app.processEvents()

    assert requested == [(project.project_id, manifest.manifest_digest)]
    assert studio.is_validated_completion("guardian-review", manifest)
    assert studio.worker is None
    assert "commands: NONE" in studio.operation_status.text()
    studio.close()


def test_genesis_opens_the_exact_stage_learning_guide_and_saves_place(tmp_path):
    QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Learning route")
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    mission = GuidedBuildMission(studio)
    requested: list[str] = []
    studio.knowledge_requested.connect(requested.append)
    mission.selected_index = 7

    mission._open_stage_learning()

    saved = GuidedMissionStore(store.projects_root / project.project_id).load()
    assert requested == ["Incremental debloat safety"]
    assert saved.selected_stage == "debloat"
    assert mission.result() == mission.DialogCode.Accepted
    studio.close()


def test_genesis_device_learning_routes_each_detected_state_to_its_exact_fix(tmp_path):
    QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Connection learning")
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    mission = GuidedBuildMission(studio)
    mission.selected_index = 4

    cases = (
        (DeviceState.UNAUTHORIZED, "adb unauthorized"),
        (DeviceState.OFFLINE, "adb device offline"),
        (
            DeviceState.FASTBOOT,
            "Phone detected in bootloader Fastboot or userspace fastbootd",
        ),
        (
            DeviceState.RECOVERY,
            "Phone detected in Android recovery or ADB sideload mode",
        ),
        (
            DeviceState.SIDELOAD,
            "Phone detected in Android recovery or ADB sideload mode",
        ),
        (DeviceState.UNKNOWN, "Android device connection"),
        (
            DeviceState.DEVICE,
            "Android device identity fields: brand, manufacturer, model, device, and product",
        ),
    )
    for state, expected in cases:
        device = AndroidDevice("serial", state, model="Visible Phone")
        studio.set_devices([device])
        assert mission._stage_learning_query("device") == expected

    first = AndroidDevice("one", DeviceState.DEVICE, model="First Phone")
    second = AndroidDevice("two", DeviceState.DEVICE, model="Second Phone")
    studio.set_devices([], observed_devices=[first, second])
    assert mission._stage_learning_query("device") == "multiple devices"

    studio.set_devices([], scan_error="ADB transport failed")
    assert mission._stage_learning_query("device") == "ADB transport failure"

    studio.set_devices([])
    assert mission._stage_learning_query("device") == "USB debugging Android connection"
    assert mission._stage_learning_query("debloat") == "Incremental debloat safety"
    mission.close()
    studio.close()


def test_genesis_root_choice_explains_the_evidence_route_before_consent(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Root preview")
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    mission = GuidedBuildMission(studio)
    mission.root_entry_brief = AscensionEntryBrief(
        AscensionEntryState.SUPPORTED,
        "Magisk image patch recommended",
        "Exact source and device evidence agree.",
        AscensionMethod.MAGISK,
        "init_boot.img",
        "verified",
        ("Exact source verified", "Device DNA identity supported"),
        "a" * 16,
    )
    mission.root_preview_attempted = True
    mission.selected_index = 8

    mission._render_stage()

    assert "ROOT ROUTE  •  SUPPORTED" in mission.recommendation.text()
    assert "Recommended method: Magisk" in mission.recommendation.text()
    assert "Source image target: init_boot.img" in mission.recommendation.text()
    assert "Phone changed now: NO" in mission.action_button.toolTip()
    assert "Bootloader relock: NEVER" in mission.action_button.toolTip()
    mission.close()
    studio.close()


def test_genesis_resolves_the_root_preview_in_background_without_guessing(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "unknown-root-source.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("system/build.prop", "ro.product.device=unknown\n")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Background root preview")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    studio.set_devices(
        [
            AndroidDevice(
                "serial-1",
                DeviceState.DEVICE,
                model="Unknown phone",
                codename="unknown",
                kernel_version="6.1-test",
            )
        ]
    )
    mission = GuidedBuildMission(studio)
    mission.assessments = tuple(
        replace(item, status=GuidedStageStatus.READY) if index == 8 else item
        for index, item in enumerate(mission.assessments)
    )
    mission.selected_index = 8

    mission._render_stage()
    deadline = time.monotonic() + 3
    while mission.root_preview_active and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)

    assert not mission.root_preview_active
    assert mission.root_preview_attempted
    assert mission.root_entry_brief.method is None
    assert mission.root_entry_brief.state in {
        AscensionEntryState.BLOCKED,
        AscensionEntryState.UNCONFIRMED,
    }
    assert "Execution authority: NONE" in mission.recommendation.text()
    assert "Bootloader relock: NEVER" in mission.recommendation.text()
    mission.close()
    studio.close()


def test_genesis_reports_real_progress_pause_and_failure_to_live_console(tmp_path):
    QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.live_console_store = LiveConsoleEventStore(store.workspace)
    mission = GuidedBuildMission(studio)

    opened = studio.live_console_store.list_recent()
    assert len(opened) == 1
    assert opened[0].source == "Genesis Sequence"
    assert opened[0].state is MissionState.RUNNING
    assert opened[0].progress_percent == 0
    assert "Stage 1 of 15" in opened[0].summary
    assert "relock" in opened[0].explanation.casefold()

    mission._operation_started("extract")
    mission._operation_progress("extract", 45)
    progressed = studio.live_console_store.list_recent()[0]
    assert progressed.state is MissionState.RUNNING
    assert progressed.progress_percent == 3
    assert "45%" in progressed.summary

    mission._operation_failed("extract", "test resolver stopped")
    failed = studio.live_console_store.list_recent()[0]
    assert failed.state is MissionState.ATTENTION
    assert failed.progress_percent == 3
    assert "stopped safely" in failed.summary.casefold()
    assert "no phone write" in failed.explanation.casefold()

    companion = CompanionCenter(studio.live_console_store)
    telemetry = companion._telemetry_snapshot()
    assert telemetry.live_console_events[0].source == "Genesis Sequence"
    assert telemetry.live_console_events[0].state == "attention"
    assert telemetry.live_console_execution_authority == "none"
    companion.shutdown()
    mission.close()
    studio.close()


def test_genesis_opens_forge_control_as_a_visible_child_and_releases_autopilot(
    tmp_path,
):
    app = QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Visible Forge handoff")
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    mission = GuidedBuildMission(studio)
    app.processEvents()
    opened_with = []
    studio._open_build_control = lambda parent=None: opened_with.append(parent)

    mission.selected_index = 11
    mission._run_stage()

    assert opened_with == [mission]

    mission.assessments = tuple(
        replace(item, status=GuidedStageStatus.ATTENTION) if index == 11 else item
        for index, item in enumerate(mission.assessments)
    )
    mission.selected_index = 11
    mission.autopilot_active = True
    mission._refresh = lambda select_current=False: None
    mission._advance_autopilot()

    assert not mission.autopilot_active
    assert mission.auto_button.text() == "Auto-resolve && continue"
    assert "paused at Forge Control" in mission.status_text.text()
    assert "Guardian review" not in mission.status_text.text()
    assert opened_with == [mission, mission]

    mission.close()
    studio.close()


def test_genesis_presents_completed_local_build_as_100_percent_with_install_deferred(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Completed local build")
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    mission = GuidedBuildMission(studio)
    tools = tuple(
        ToolStatus(name, True, f"/tools/{name.casefold()}", "1.0", "Ready")
        for name in GENESIS_REQUIRED_TOOLS
    )
    mission._context = lambda: GuidedContext(
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

    mission._refresh(select_current=True)
    app.processEvents()

    assert mission.selected_index == 13
    assert mission.overall_progress.value() == 100
    assert "13 OF 13 LOCAL BUILD STAGES VERIFIED" in mission.progress_copy.text()
    assert mission.action_button.text() == "Continue to optional flash setup"
    assert mission.save_button.text() == "Finish local build"
    assert "Local ROM build complete" in mission.status_text.text()
    mission.close()
    studio.close()


def test_genesis_local_image_route_never_requires_production_manifest_or_forge_loop(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Manifest route")
    source = tmp_path / "source.img"
    source.write_bytes(b"inert UI source fixture")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    mission = GuidedBuildMission(studio)
    app.processEvents()
    manifest_calls = []
    forge_calls = []
    image_calls = []
    studio._open_guardian_manifest_review = lambda parent=None: manifest_calls.append(parent)
    studio._open_build_control = lambda parent=None: forge_calls.append(parent)
    studio.project_flash_requested.connect(image_calls.append)
    mission._refresh = lambda select_current=False: None
    mission.state = replace(mission.state, install_requested=True)
    mission.selected_index = 13

    mission._context = lambda: GuidedContext(guardian_flash_handoff_ready=True)
    mission._run_stage()
    app.processEvents()
    assert image_calls == [project.project_id]
    assert manifest_calls == []
    assert forge_calls == []

    mission._context = lambda: GuidedContext(guardian_flash_handoff_ready=False)
    mission._run_stage()
    app.processEvents()
    assert image_calls == [project.project_id, project.project_id]
    assert manifest_calls == []
    assert forge_calls == []
    mission.close()
    studio.close()


def test_genesis_autopilot_runs_safe_local_stages_then_pauses_for_device(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("system/build.prop", "ro.romverse=verified\n")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Genesis autopilot")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    mission = GuidedBuildMission(studio)

    mission._start_autopilot()
    deadline = time.monotonic() + 5
    while mission.autopilot_active and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)

    assert not mission.autopilot_active
    assert studio.inspection.load_report(project.project_id) is not None
    assert store.working_copy(project.project_id) is not None
    assert studio.inspection.summarize_working_tree(project.project_id) is not None
    assert mission.assessments[mission.selected_index].stage.stage_id == "device"
    assert "No Android device is currently visible" in mission.status_text.text()
    mission.close()
    studio.close()


def test_genesis_device_stage_requests_a_fresh_scan_and_rebuilds_device_dna(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("system/build.prop", "ro.romverse=verified\n")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Fresh Device DNA", "fixture-device-pack")
    store.import_original(project.project_id, source)
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    store.create_working_copy(project.project_id)
    inspection.extract_project_tree(project.project_id)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    studio.device_scan_available = True
    scan_requests = []
    studio.device_scan_requested.connect(lambda: scan_requests.append(True))
    mission = GuidedBuildMission(studio)
    mission.selected_index = 4

    mission._run_stage()

    assert scan_requests == [True]
    assert mission.active_operation == "device-scan"
    assert not mission.process_frame.isHidden()

    studio.set_devices(
        [
            AndroidDevice(
                "serial-1",
                DeviceState.DEVICE,
                manufacturer="ROMVERSE",
                model="Fixture Phone",
                product="fixture",
                codename="fixture",
            )
        ]
    )
    studio.device_scan_finished.emit(True, "Fresh device scan completed.")
    app.processEvents()

    profile = studio.device_dna.profiles.load(project.project_id)
    assert profile is not None
    assert profile.fact("identity.model").value == "Fixture Phone"
    assert mission.active_operation == ""
    assert mission.process_frame.isHidden()
    assert mission.assessments[4].status is GuidedStageStatus.COMPLETE
    assert mission.stage_buttons[4].text().endswith("Device DNA")
    mission.close()
    studio.close()


def test_genesis_simulated_device_continues_visibly_without_hardware_authority(
    tmp_path, monkeypatch
):
    from tests.test_device_dna import _device, _pack, _source

    app = QApplication.instance() or QApplication([])
    source = _source(tmp_path)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Simulated compatibility", "xiaomi.popsicle.test")
    project = store.import_original(project.project_id, source)
    registry = DevicePackRegistry((_pack(project.original.sha256),))
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    store.create_working_copy(project.project_id)
    inspection.extract_project_tree(project.project_id)
    studio = RomStudio(store, registry)
    studio.refresh(project.project_id)
    studio.device_scan_available = True
    scan_requests = []
    studio.device_scan_requested.connect(lambda: scan_requests.append(True))
    mission = GuidedBuildMission(studio)
    mission.show()
    app.processEvents()

    assert mission.assessments[mission.selected_index].stage.stage_id == "device"
    mission.action_button.click()
    assert scan_requests == [True]
    assert mission.active_operation == "device-scan"

    simulated = _device(
        transport="simulation",
        connection_note="SIMULATION ONLY • NOT HARDWARE VERIFIED",
    )
    studio.set_devices([simulated])
    studio.device_scan_finished.emit(True, "Deterministic device simulation completed.")
    app.processEvents()

    profile = studio.device_dna.profiles.load(project.project_id)
    matrix = studio.compatibility.matrices.load(project.project_id)
    assert profile is not None
    assert matrix is not None
    assert any(item.evidence_id == "device.simulation" for item in profile.evidence)
    assert all(item.evidence_id != "device.live" for item in profile.evidence)
    assert matrix.decision("device_identity").status is CompatibilityStatus.LIMITED_EVIDENCE
    assert matrix.decision("guardian_flash").status is CompatibilityStatus.UNKNOWN
    assert matrix.guardian_advisory_only
    assert not matrix.bootloader_relock_permitted
    assert "SIMULATION ONLY • NOT HARDWARE VERIFIED" in studio.device_dna_detail.text()
    assert mission.device_identity_detail.text() == "SIMULATION ONLY • NOT HARDWARE VERIFIED"
    assert mission.assessments[4].status is GuidedStageStatus.COMPLETE
    assert mission.assessments[mission.selected_index].stage.stage_id == "customize"
    assert mission.skip_button.isVisible()
    assert mission.skip_button.text() == "Keep verified base unchanged • Recommended"

    mission.skip_button.click()
    app.processEvents()

    assert mission.assessments[5].status is GuidedStageStatus.COMPLETE
    assert mission.assessments[6].status is GuidedStageStatus.COMPLETE
    assert mission.assessments[7].status is GuidedStageStatus.COMPLETE
    assert mission.assessments[8].status is GuidedStageStatus.COMPLETE
    assert mission.assessments[mission.selected_index].stage.stage_id == "toolchain"

    resolution_calls = []
    tool_root = store.workspace / "fixture-tools"
    tool_root.mkdir()

    def resolve_tools(required, *, purpose):
        resolution_calls.append((required, purpose))
        statuses = []
        for name in required:
            path = tool_root / f"romverse-fixture-{name.casefold().replace(' ', '-')}"
            path.write_bytes(f"verified {name}".encode())
            statuses.append(ToolStatus(name, True, str(path), "1", "Ready"))
        studio.set_tool_statuses(tuple(statuses))
        return True

    mission._resolve_required_tools = resolve_tools
    mission.action_button.click()
    app.processEvents()

    assert len(resolution_calls) == 1
    assert resolution_calls[0][0] == ("Python", "Payload Dumper", "AVBTool")
    assert "source-bound build dependency" in resolution_calls[0][1]
    assert mission.assessments[9].status is GuidedStageStatus.COMPLETE
    assert mission.assessments[mission.selected_index].stage.stage_id == "build_plan"

    workers = []
    monkeypatch.setattr("romverse.ui.rom_studio.start_background", workers.append)
    source_before = store.verify_original(project.project_id)
    mission.action_button.click()
    assert len(workers) == 1 and workers[0].operation == "plan"
    workers.pop().run()
    app.processEvents()
    assert len(workers) == 1 and workers[0].operation == "verify-plan"
    workers.pop().run()
    app.processEvents()

    plan = RomBuildPlanner(store).load(project.project_id)
    assert plan is not None
    assert plan.schema_version == 3
    assert plan.source_sha256 == project.original.sha256
    assert plan.required_tools == ("Python", "Payload Dumper", "AVBTool")
    assert plan.local_only and not plan.flashable and plan.execution_locked
    assert plan.execution_authority == "none"
    assert RomBuildPlanner(
        store,
        studio.tool_statuses,
        plan.required_tools,
    ).verify_tree(project.project_id).valid
    assert store.verify_original(project.project_id) == source_before
    assert mission.assessments[10].status is GuidedStageStatus.COMPLETE
    assert mission.assessments[mission.selected_index].stage.stage_id == "build_sign"

    context = studio.guided_context()
    assert context.device is simulated
    assert not context.guardian_handoff_ready
    assert not context.guardian_flash_handoff_ready
    assert not context.flash_complete
    assert store.verify_original(project.project_id).valid
    project_root = store.projects_root / project.project_id
    assert not (project_root / "forge-bundle.romverse").exists()
    assert not (project_root / "boot-observation.romverse").exists()
    assert not (project_root / "guardian").exists()

    persisted = GuidedMissionStore(project_root).load()
    assert persisted.selected_stage == "build_sign"
    assert persisted.customization_skipped
    assert persisted.recipe_skipped
    assert persisted.root_choice == "skip"
    assert studio.current_project.project_id == project.project_id
    assert studio.current_project.original.sha256 == project.original.sha256
    assert "SIMULATION ONLY • NOT HARDWARE VERIFIED" in studio.device_dna_detail.text()
    assert not (project_root / "recipe.romverse").exists()
    studio.close()


def test_genesis_keeps_the_exact_connection_blocker_visible_after_a_successful_scan(
    tmp_path,
):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("system/build.prop", "ro.romverse=verified\n")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Connection truth", "fixture-device-pack")
    store.import_original(project.project_id, source)
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    store.create_working_copy(project.project_id)
    inspection.extract_project_tree(project.project_id)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    studio.device_scan_available = True
    mission = GuidedBuildMission(studio)
    mission.selected_index = 4

    mission._run_stage()
    unauthorized = AndroidDevice(
        "serial-1",
        DeviceState.UNAUTHORIZED,
        manufacturer="ROMVERSE",
        model="Visible Phone",
    )
    studio.set_devices([unauthorized])
    studio.device_scan_finished.emit(True, "Fresh device scan completed.")
    app.processEvents()

    assert mission.active_operation == ""
    assert mission.assessments[4].status is GuidedStageStatus.ATTENTION
    assert "USB phone detected" in mission.status_text.text()
    assert "approve" in mission.status_text.text()
    assert mission.status_text.text() != "Fresh device scan completed."
    mission.close()
    studio.close()


def test_genesis_resolves_image_materialization_tools_before_nebula_debloat(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "payload-ota.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"CrAU fixture")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Debloat tool resolution")
    store.import_original(project.project_id, source)
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    mission = GuidedBuildMission(studio)
    mission.selected_index = 7
    resolved = []
    opened = []

    def resolve(required, *, purpose):
        resolved.append((required, purpose))
        return True

    class Dialog:
        completed = False

        def __init__(self, service, project_id, parent):
            opened.append((service, project_id, parent))

        def exec(self):
            return 0

    monkeypatch.setattr(mission, "_resolve_required_tools", resolve)
    monkeypatch.setattr("romverse.ui.debloat_sequence.NebulaDebloatDialog", Dialog)

    mission._run_stage()
    app.processEvents()

    required, purpose = resolved[0]
    assert {
        "Payload Dumper",
        "simg2img",
        "EXT4 Browser",
        "EROFS Verifier",
        "Fakeroot",
    }.issubset(required)
    assert "read-only tools" in purpose
    assert opened[0][1:] == (project.project_id, mission)
    mission.close()
    studio.close()


def test_genesis_tool_resolution_fails_closed_when_required_reader_remains_missing(
    tmp_path, monkeypatch
):
    QApplication.instance() or QApplication([])
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Missing reader")
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    mission = GuidedBuildMission(studio)

    class Status:
        def setText(self, _text):
            pass

    class Dialog:
        last_message = "Installation was closed before completion."
        status = Status()

        def __init__(self, *_args, **_kwargs):
            pass

        def setWindowTitle(self, _title):
            pass

        def exec(self):
            return 0

    class Verifier:
        def __init__(self, *_args):
            pass

        def verify_extended(self):
            return (ToolStatus("Python", True, "/usr/bin/python3", "3"),)

    monkeypatch.setattr("romverse.ui.toolchain_center.ToolchainSetupDialog", Dialog)
    monkeypatch.setattr(
        "romverse.ui.toolchain_center.activate_verified_managed_tools", lambda _workspace: ()
    )
    monkeypatch.setattr("romverse.ui.rom_studio.ToolVerifier", Verifier)

    resolved = mission._resolve_required_tools(
        ("Python", "Payload Dumper"),
        purpose="Expose OTA partitions.",
    )

    assert not resolved
    assert mission.failure is not None
    assert mission.failure.title == "Forge Arsenal still needs attention"
    assert "Payload Dumper" in " ".join(mission.failure.recommendations)
    mission.close()
    studio.close()


def test_recipe_forge_creates_multistep_reviewed_recipe_without_prompt_chain(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("system/build.prop", "ro.romverse=old\n")
        archive.writestr("product/product.prop", "ro.product.romverse=test\n")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Forge recipe")
    store.import_original(project.project_id, source)
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    store.create_working_copy(project.project_id)
    inspection.extract_project_tree(project.project_id)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    studio.live_console_store = LiveConsoleEventStore(store.workspace)
    forge = RecipeForgeSequence(studio)
    app.processEvents()
    guides: list[tuple[str, str]] = []
    monkeypatch.setattr(
        KnowledgeGuideDialog,
        "exec",
        lambda dialog: guides.append((dialog.query, dialog.stage_label)),
    )

    assert forge.minimumWidth() >= 980
    assert len(forge.stage_buttons) == 6
    assert forge.learn_button.text() == "Learn this stage"
    recipe_events = studio.live_console_store.list_recent()
    assert len(recipe_events) == 1
    assert recipe_events[0].source == "Recipe Forger"
    assert recipe_events[0].state is MissionState.RUNNING
    assert recipe_events[0].progress_percent == 0
    forge.name_input.setText("Inspect build properties")
    forge.description_input.setText("Record the current ROM identity before modification")
    forge._next()
    forge.operation_buttons["inspect"].click()
    forge._next()
    target = store.working_root / project.project_id / "tree/system/build.prop"
    index = forge.target_model.index(str(target))
    forge._target_clicked(index)
    forge._next()
    draft_before_learning = (
        forge.name_input.text(),
        forge.description_input.text(),
        forge.operation,
        forge.target,
        forge.stage,
    )
    forge.learn_button.click()
    assert guides == [("Recipe Forger stage 4", "Stage 4 of 6  •  Configure")]
    assert (
        forge.name_input.text(),
        forge.description_input.text(),
        forge.operation,
        forge.target,
        forge.stage,
    ) == draft_before_learning
    forge._next()
    forge._add_another_step()
    assert forge.stage == 1
    forge.operation_buttons["inspect"].click()
    forge._next()
    second_target = store.working_root / project.project_id / "tree/product/product.prop"
    second_index = forge.target_model.index(str(second_target))
    forge._target_clicked(second_index)
    forge._next()
    forge._next()
    forge._next()

    saved = RecipeStore().load(store.projects_root / project.project_id)
    assert forge.stage == 5
    assert saved is not None
    assert saved.name == "Inspect build properties"
    assert len(saved.steps) == 2
    assert saved.steps[0].operation == "inspect"
    assert saved.steps[0].target == "system/build.prop"
    assert saved.steps[1].target == "product/product.prop"
    assert not (store.projects_root / project.project_id / RecipeDraftStore.NAME).exists()

    completed = studio.live_console_store.list_recent()
    assert completed[0].source == "Recipe Forger"
    assert completed[0].state is MissionState.SUCCEEDED
    assert completed[0].progress_percent == 100
    assert "execution remains locked" in completed[0].summary.casefold()
    assert "no phone was changed" in completed[0].explanation.casefold()

    forge.close()
    studio.close()


def test_recipe_forge_resumes_private_draft_and_downgrades_a_stale_target(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("system/build.prop", "ro.romverse=old\n")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Resume recipe")
    store.import_original(project.project_id, source)
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    store.create_working_copy(project.project_id)
    inspection.extract_project_tree(project.project_id)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)

    forge = RecipeForgeSequence(studio)
    forge.name_input.setText("Resume property change")
    forge.description_input.setText("Preserve this unfinished design")
    forge._next()
    forge.operation_buttons["set_property"].click()
    forge._next()
    target = store.working_root / project.project_id / "tree/system/build.prop"
    forge._target_clicked(forge.target_model.index(str(target)))
    forge._next()
    forge.key_input.setText("ro.romverse")
    forge.value_input.setText("resumed")
    forge._save_draft_now()
    forge.close()

    resumed = RecipeForgeSequence(studio)
    app.processEvents()
    assert resumed.stage == 3
    assert resumed.name_input.text() == "Resume property change"
    assert resumed.description_input.text() == "Preserve this unfinished design"
    assert resumed.operation == "set_property"
    assert resumed.target == "system/build.prop"
    assert resumed.key_input.text() == "ro.romverse"
    assert resumed.value_input.text() == "resumed"
    assert "DRAFT RESUMED" in resumed.progress_copy.text()
    assert "resumed a private draft" in studio.operation_status.text()
    resumed.close()

    target.unlink()
    stale = RecipeForgeSequence(studio)
    app.processEvents()
    assert stale.stage == 2
    assert stale.target == ""
    assert stale.name_input.text() == "Resume property change"
    assert not stale.next_button.isEnabled()
    stale.close()
    studio.close()


def test_rom_studio_exposes_verified_non_flashable_forge_bundle_workflow(
    tmp_path,
    monkeypatch,
):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("IMAGES/system.img", b"system")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Forge bundle UI")
    store.import_original(project.project_id, source)
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    inspection.extract_project_tree(project.project_id)
    RomBuildPlanner(store).plan(project.project_id)

    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    workers = []
    monkeypatch.setattr("romverse.ui.rom_studio.start_background", workers.append)
    app.processEvents()

    assert studio.forge_button.isEnabled()
    assert "non-flashable" in studio.forge_button.toolTip()
    assert not studio.verify_forge_button.isEnabled()

    assert studio.open_dashboard_intent("Pre-Build Simulation")
    assert len(workers) == 1 and workers[0].operation == "verify-plan"
    workers.pop(0).run()
    app.processEvents()

    assert studio.dashboard_handoff_badge.text() == "VERIFIED"
    assert studio.focusWidget() is studio.forge_button
    studio.forge_button.click()
    assert len(workers) == 1 and workers[0].operation == "forge-bundle"
    workers.pop(0).run()
    app.processEvents()

    receipt = ForgeBundleService(store).load_receipt(project.project_id)
    assert receipt is not None
    assert len(workers) == 1 and workers[0].operation == "verify-forge"
    assert studio.dashboard_handoff_title.text() == "Forge Bundle → Verifying artifact"
    assert studio.dashboard_handoff_badge.text() == "VERIFYING"
    assert not studio.verify_forge_button.isEnabled()
    assert receipt.output_path in studio.time_machine_detail.text()
    assert "unsigned, non-bootable, non-flashable" in studio.time_machine_detail.text()
    assert "Root route  •  unrooted" in studio.time_machine_detail.text()

    workers.pop(0).run()
    app.processEvents()

    assert workers == []
    assert studio.worker is None
    assert studio.verify_forge_button.isEnabled()
    assert studio.dashboard_handoff_title.text() == "Forge Bundle → Verified intermediate"
    assert studio.dashboard_handoff_badge.text() == "VERIFIED INTERMEDIATE"
    assert receipt.archive_sha256[:16] in studio.dashboard_handoff_detail.text()
    assert "unsigned, non-bootable, and non-flashable" in (studio.dashboard_handoff_detail.text())
    assert "grants no build, signing, Guardian, device, flash, or execution authority" in (
        studio.dashboard_handoff_detail.text()
    )
    assert studio.focusWidget() is studio.build_control_button
    assert studio.devices == []
    studio.close()


def test_intentional_forge_verification_stops_on_archive_drift_without_retry(
    tmp_path,
    monkeypatch,
):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("IMAGES/system.img", b"system")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Forge verification drift")
    store.import_original(project.project_id, source)
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    inspection.extract_project_tree(project.project_id)
    RomBuildPlanner(store).plan(project.project_id)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    workers = []
    failures = []
    monkeypatch.setattr("romverse.ui.rom_studio.start_background", workers.append)
    studio.operation_failed.connect(
        lambda operation, message: failures.append((operation, message))
    )

    assert studio.open_dashboard_intent("Pre-Build Simulation")
    workers.pop(0).run()
    app.processEvents()
    assert studio.dashboard_handoff_badge.text() == "VERIFIED"

    studio.forge_button.click()
    assert len(workers) == 1 and workers[0].operation == "forge-bundle"
    workers.pop(0).run()
    app.processEvents()
    receipt = ForgeBundleService(store).load_receipt(project.project_id)
    assert receipt is not None
    assert len(workers) == 1 and workers[0].operation == "verify-forge"
    output = store.workspace / receipt.output_path
    output.write_bytes(b"adversarial archive drift")
    workers.pop(0).run()
    app.processEvents()

    assert len(failures) == 1
    assert failures[0][0] == "verify-forge"
    assert "archive hash mismatch" in failures[0][1]
    assert workers == []
    assert studio.worker is None
    assert ForgeBundleService(store).load_receipt(project.project_id) == receipt
    assert output.is_file()
    assert studio.dashboard_handoff_title.text() == "Forge Bundle → Verification needs attention"
    assert studio.dashboard_handoff_badge.text() == "ATTENTION"
    assert "did not retry, infer success" in studio.dashboard_handoff_detail.text()
    assert studio.focusWidget() is studio.verify_forge_button
    assert studio.devices == []
    studio.close()


def test_rom_studio_identifies_new_base_and_demotes_mismatched_exact_contract(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = (
        tmp_path / "popsicle_images_OS3.0.318.0.WPBCNXM_20260804.0000.00_16.0_cn_f1a4098622.tgz"
    )
    source.write_bytes(b"different protected firmware base")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create(
        "Different base",
        "xiaomi.popsicle.hyperos4.os4.0.0.23",
    )
    store.import_original(project.project_id, source)
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))

    studio = RomStudio(store, registry)
    app.processEvents()

    updated = store.get(project.project_id)
    assert updated.device_pack_id == "xiaomi.hyperos"
    assert "OS3.0.318.0.WPBCNXM" in studio.project_meta.text()
    assert "Xiaomi fastboot image archive" in studio.project_meta.text()
    assert "No exact build contract exists" in studio.operation_status.text()
    assert studio.operation_status.objectName() == "Warning"
    studio.close()


def test_rom_studio_auto_associates_one_live_oem_as_knowledge_only(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "unknown-samsung-payload.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"CrAU test")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Samsung knowledge").project_id, source)
    RomInspectionService(store).inspect_project(project.project_id)
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    studio = RomStudio(store, registry)

    studio.set_devices(
        [
            AndroidDevice(
                "private-samsung",
                DeviceState.DEVICE,
                manufacturer="Samsung",
                model="SM-S938B",
                product="pa3qxeea",
                codename="pa3q",
            )
        ]
    )
    app.processEvents()

    updated = store.get(project.project_id)
    profile = studio.device_dna.profiles.load(project.project_id)
    assert updated.device_pack_id == "samsung.oneui"
    assert profile is not None
    assert profile.fact("identity.manufacturer").value == "Samsung"
    assert profile.capability("device_identity").state is CapabilityState.SUPPORTED
    assert (
        "firmware target identity remains unconfirmed"
        in profile.capability("device_identity").detail
    )
    assert profile.capability("source_adapter").state is CapabilityState.SUPPORTED
    assert profile.capability("guardian_flash").state is CapabilityState.UNCONFIRMED
    assert any(
        item.source_ref == "samsung.oneui" and item.confidence.value == "medium"
        for item in profile.evidence
    )
    assert "read-only knowledge only" in studio.operation_status.text()
    studio.close()


def test_rom_studio_keeps_single_wrong_phone_as_visible_unsupported_evidence(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "popsicle-ota_full-OS4.0.0.23.XPBCNXM-user-17.0-test.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"CrAU test")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Wrong phone").project_id, source)
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    studio = RomStudio(store, registry)

    studio.set_devices(
        [
            AndroidDevice(
                "private-google",
                DeviceState.DEVICE,
                manufacturer="Google",
                model="Pixel 9 Pro XL",
                product="komodo",
                codename="komodo",
            )
        ]
    )
    app.processEvents()

    profile = studio.device_dna.profiles.load(project.project_id)
    assert profile is not None
    assert profile.fact("identity.model").value == "Pixel 9 Pro XL"
    assert profile.capability("device_identity").state is CapabilityState.UNSUPPORTED
    assert profile.capability("guardian_flash").state is CapabilityState.UNSUPPORTED
    assert "does not match" in studio.device_dna_detail.text()
    studio.close()


def test_rom_studio_does_not_guess_knowledge_pack_with_multiple_live_devices(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "unknown-multi-device.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"CrAU test")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Ambiguous phones").project_id, source)
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    studio = RomStudio(store, registry)

    studio.set_devices(
        [
            AndroidDevice(
                "private-samsung",
                DeviceState.DEVICE,
                manufacturer="Samsung",
                model="SM-S938B",
                product="pa3qxeea",
                codename="pa3q",
            ),
            AndroidDevice(
                "private-google",
                DeviceState.DEVICE,
                manufacturer="Google",
                model="Pixel 9 Pro XL",
                product="komodo",
                codename="komodo",
            ),
        ]
    )
    app.processEvents()

    profile = studio.device_dna.profiles.load(project.project_id)
    assert store.get(project.project_id).device_pack_id == ""
    assert profile is not None
    assert profile.fact("identity.model").value == "Unconfirmed"
    assert profile.capability("device_identity").state is CapabilityState.UNCONFIRMED
    studio.close()
