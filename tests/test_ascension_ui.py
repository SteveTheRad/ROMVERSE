import hashlib
import zipfile
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
)

from romverse.ascension.final_handoff import AscensionFinalHandoff
from romverse.ascension.manager_launch import RootManagerLaunchPlan
from romverse.ascension.manifest import (
    AscensionGuardianManifest,
    AscensionManifestCheck,
    ManifestState,
)
from romverse.ascension.models import (
    AscensionAssessment,
    AscensionGate,
    AscensionMethod,
    GateState,
    OfficialRootAsset,
    OfficialRootRelease,
)
from romverse.ascension.output import PatchedOutputDiscovery
from romverse.ascension.preparation import PatchedImageReceipt
from romverse.core.privacy import WorkspacePrivacy
from romverse.device.apk_install import ApkInstallRequest, create_install_plan
from romverse.device.models import AndroidDevice, DeviceState, StorageInfo
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.process import CommandResult
from romverse.nexus.events import LiveConsoleEventStore, MissionState
from romverse.rom.projects import RomProjectStore
from romverse.ui.ascension_protocol import (
    AscensionBuildSealWorker,
    AscensionConsentReviewDialog,
    AscensionHandoffWorker,
    AscensionIntegrationWorker,
    AscensionManagerInstallCompletion,
    AscensionManagerInstallPreparation,
    AscensionManagerInstallWorker,
    AscensionManagerLaunchWorker,
    AscensionManagerPlanWorker,
    AscensionManifestDialog,
    AscensionOutputDiscoveryCompletion,
    AscensionPreparationWorker,
    AscensionProtocolDialog,
)
from romverse.ui.companion_center import CompanionCenter
from romverse.ui.rom_studio import RomStudio


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _output_discovery_completion(
    project_id: str,
    names: tuple[str, ...],
    *,
    method: AscensionMethod = AscensionMethod.MAGISK,
) -> AscensionOutputDiscoveryCompletion:
    refs = tuple(hashlib.sha256(name.encode("utf-8")).hexdigest() for name in names)
    return AscensionOutputDiscoveryCompletion(
        names,
        PatchedOutputDiscovery(
            schema_version=1,
            discovery_id="1" * 32,
            project_id=project_id,
            method=method,
            created_at="2026-08-31T00:00:00+00:00",
            handoff_receipt_digest="2" * 64,
            device_key="private-device-key",
            state="found" if names else "none",
            candidate_count=len(names),
            candidate_refs=refs,
            candidate_set_digest="3" * 64,
            recommended_name_ref=refs[0] if refs else "",
            truncated=False,
            data_scope="filenames-only",
            source_directory="/sdcard/Download",
            ordering="modified-descending",
            phone_changed=False,
            execution_authority="none",
            receipt_digest="4" * 64,
        ),
    )


def _bind_output_discovery(
    studio: RomStudio,
    dialog: AscensionProtocolDialog,
    completion: AscensionOutputDiscoveryCompletion,
    monkeypatch,
) -> None:
    studio.devices = [AndroidDevice("device-serial", DeviceState.DEVICE)]
    monkeypatch.setattr(
        dialog,
        "_patched_output_service",
        lambda: SimpleNamespace(load_discovery=lambda *_args: completion.receipt),
    )


def test_rom_studio_exposes_guardian_locked_ascension_dialog(tmp_path: Path) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Root prep")
    source = tmp_path / "popsicle_images_OS3.0.318.0.WPBCNXM_20260804.0000.00_16.0_cn_test.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    updates: list[bool] = []
    learning_queries: list[str] = []
    studio.ascension_status_changed.connect(lambda: updates.append(True))
    studio.knowledge_requested.connect(learning_queries.append)

    assert studio.ascension_button.text() == "Ascension Protocol"
    dialog = AscensionProtocolDialog(studio)
    assert "Ascension Protocol" in dialog.windowTitle()
    assert "AUTO ROUTE" in dialog.recommendation_badge.text()
    assert "Complete source and device checks" in dialog.recommendation_badge.text()
    assert "auto" in dialog.acquire_button.text().casefold()
    assert dialog.method.isHidden()
    assert "advanced" in dialog.route_toggle.text().casefold()
    assert "phone changed: NO" in dialog.status.text()
    labels = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    assert "NEXT SAFE ACTION" in labels
    assert "ROMVERSE WILL DO" in labels
    assert "YOUR PART" in labels
    assert "WHY THIS MATTERS" in labels
    assert "bootloader relock" in labels
    assert "AUTOMATIC ROUTE RECORD" in labels
    assert "AUTOMATIC RESOLUTION PLAN" in labels
    assert "ROMVERSE STEP(S)" in labels
    assert "private bounded storage: VERIFIED" in labels
    assert "execution authority: NONE" in labels
    assert "EVIDENCE RECOVERY" in labels
    assert "returns to the first safe stage" in labels
    assert "1\nPrerequisites" in labels
    assert "2\nOfficial manager" in labels
    assert "3\nPatch capsule" in labels
    assert "4\nPhone handoff" in labels
    assert "5\nPatched image" in labels
    assert "8\nDevice binding" in labels
    assert "9\nGuardian review" in labels
    assert dialog.route_record is not None
    assert dialog.route_record.execution_authority == "none"
    assert not dialog.route_record.bootloader_relock_allowed
    assert dialog.learn_button.text() == "Learn this stage"
    assert dialog.current_brief is not None
    assert dialog.current_brief.stage_number == 1
    journey_progress = dialog.findChild(QProgressBar, "AscensionJourneyProgress")
    assert journey_progress is not None
    assert journey_progress.value() == 0
    assert journey_progress.format() == "0 of 9 evidence checkpoints verified  •  %p%"
    assert updates
    dialog.learn_button.click()
    assert learning_queries == ["Ascension stage 1"]
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_ascension_auto_scans_only_one_unambiguous_contained_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Payload root prerequisites")
    source = tmp_path / "popsicle_images_OS3.0.318.0.WPBCNXM_test.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    tree = store.working_root / project.project_id / "tree"
    tree.mkdir(parents=True)
    (tree / "PAYLOAD.BIN").write_bytes(b"payload")
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    studio.payload_service = SimpleNamespace(load=lambda _project_id: None)
    dialog = AscensionProtocolDialog(studio)
    operations: list[tuple[str, str, tuple[str, ...]]] = []
    monkeypatch.setattr(
        dialog,
        "_start_prerequisite_operation",
        lambda operation, message, partitions=(): (
            operations.append((operation, message, partitions)) or True
        ),
    )

    assert dialog._try_automatic_patch_target()
    assert operations == [
        (
            "scan-payload",
            "Scanning payload.bin and identifying the exact boot partitions …",
            (),
        )
    ]

    nested = tree / "second"
    nested.mkdir()
    (nested / "payload.bin").write_bytes(b"another-payload")
    operations.clear()
    assert not dialog._try_automatic_patch_target()
    assert operations == []
    dialog.close()
    studio.close()


def test_ascension_prepares_safe_fastboot_archive_before_target_discovery(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Automatic fastboot source preparation")
    source = tmp_path / "popsicle_fastboot.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("images/init_boot.img", b"contained boot image")
        archive.writestr("images/vbmeta.img", b"contained vbmeta")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.inspection.inspect_project(project.project_id)
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    operations: list[tuple[str, str]] = []
    monkeypatch.setattr(
        dialog,
        "_start_prerequisite_operation",
        lambda operation, message, partitions=(): operations.append((operation, message)) or True,
    )

    assert dialog._try_automatic_patch_target()
    assert operations[0][0] == "extract"
    assert "isolated tree" in operations[0][1]
    assert not (store.working_root / project.project_id / "tree").exists()
    dialog.close()
    studio.close()


def test_ascension_does_not_auto_extract_archive_with_unsafe_target_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Unsafe fastboot source")
    source = tmp_path / "unsafe_fastboot.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("../init_boot.img", b"unsafe boot image")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    report = studio.inspection.inspect_project(project.project_id)
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    operations: list[str] = []
    monkeypatch.setattr(
        dialog,
        "_start_prerequisite_operation",
        lambda operation, _message, partitions=(): operations.append(operation) or True,
    )

    assert any(finding.finding_id == "archive.unsafe_path" for finding in report.findings)
    assert not dialog._try_automatic_patch_target()
    assert operations == []
    assert not (store.working_root / project.project_id / "tree").exists()
    dialog.close()
    studio.close()


def test_ascension_prepares_exactly_named_raw_boot_image_as_isolated_input(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Direct boot image root input")
    source = tmp_path / "boot.img"
    source.write_bytes(b"ANDROID!" + b"\0" * 4096)
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.inspection.inspect_project(project.project_id)
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    operations: list[str] = []
    monkeypatch.setattr(
        dialog,
        "_start_prerequisite_operation",
        lambda operation, _message, partitions=(): operations.append(operation) or True,
    )

    assert dialog._try_automatic_patch_target()
    assert operations == ["extract"]
    dialog.close()
    studio.close()


def test_ascension_keeps_renamed_raw_boot_role_unconfirmed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Unconfirmed direct image role")
    source = tmp_path / "mystery.img"
    source.write_bytes(b"ANDROID!" + b"\0" * 4096)
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    report = studio.inspection.inspect_project(project.project_id)
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    operations: list[str] = []
    monkeypatch.setattr(
        dialog,
        "_start_prerequisite_operation",
        lambda operation, _message, partitions=(): operations.append(operation) or True,
    )

    assert report.container.value == "android_boot"
    assert report.partition_signals == ()
    assert not dialog._try_automatic_patch_target()
    assert operations == []
    dialog.close()
    studio.close()


def test_ascension_resolves_missing_payload_tools_then_resumes_exact_scan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Automatic payload tool resolution")
    source = tmp_path / "popsicle_ota.zip"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    tree = store.working_root / project.project_id / "tree"
    tree.mkdir(parents=True)
    (tree / "payload.bin").write_bytes(b"payload")
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    studio.payload_service = None
    dialog = AscensionProtocolDialog(studio)
    resolutions: list[tuple[tuple[str, ...], str, bool]] = []
    operations: list[str] = []

    def resolve(required: tuple[str, ...], *, purpose: str, automatic: bool) -> bool:
        resolutions.append((required, purpose, automatic))
        studio.payload_service = SimpleNamespace(load=lambda _project_id: None)
        return True

    monkeypatch.setattr(dialog, "_resolve_required_tools", resolve)
    monkeypatch.setattr(
        dialog,
        "_start_prerequisite_operation",
        lambda operation, _message, partitions=(): operations.append(operation) or True,
    )

    assert dialog._try_automatic_patch_target()
    assert resolutions == [
        (
            ("Python", "Payload Dumper"),
            "Ascension found one contained payload.bin and needs only Payload Dumper to identify and extract its boot images.",
            True,
        )
    ]
    assert operations == ["scan-payload"]
    dialog.close()
    studio.close()


def test_ascension_manager_acquisition_waits_for_exact_verification_tools(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Root manager verification tools")
    source = tmp_path / "popsicle_firmware.zip"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    resolutions: list[tuple[tuple[str, ...], bool]] = []

    def unresolved(required: tuple[str, ...], *, purpose: str, automatic: bool) -> bool:
        assert "signer verification" in purpose
        resolutions.append((required, automatic))
        return False

    monkeypatch.setattr(dialog, "_resolve_required_tools", unresolved)

    dialog._acquire(automatic=True)

    assert resolutions == [(("AAPT2", "APK Signer"), True)]
    assert dialog.worker is None
    dialog.close()
    studio.close()


def test_ascension_completed_payload_scan_chains_to_the_next_safe_step(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Payload scan continuation")
    source = tmp_path / "popsicle_images_OS3.0.318.0.WPBCNXM_test.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    dialog.prerequisite_operation = "scan-payload"
    continued: list[bool] = []
    monkeypatch.setattr(dialog, "refresh", lambda: None)
    monkeypatch.setattr(dialog, "_ensure_patch_capsule", lambda: continued.append(True))

    dialog._prerequisite_complete("scan-payload", object())
    app.processEvents()

    assert dialog.prerequisite_operation == ""
    assert continued == [True]
    assert dialog.acquire_button.isEnabled()
    dialog.close()
    studio.close()


def test_ascension_starts_online_resolution_only_while_visible(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Visible automatic root preparation")
    source = tmp_path / "popsicle_images_OS3.0.318.0.WPBCNXM_test.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    starts: list[bool] = []
    monkeypatch.setattr(dialog, "_ensure_official_manager", lambda: starts.append(True))

    app.processEvents()
    assert starts == []

    dialog.show()
    dialog.close()
    app.processEvents()
    assert starts == []

    dialog.show()
    app.processEvents()
    assert starts == [True]
    dialog.close()
    studio.close()


def test_ascension_reports_truthful_progress_to_romverse_live_console(tmp_path: Path) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Live Console root preparation")
    source = tmp_path / "popsicle_images_OS3.0.318.0.WPBCNXM_test.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.live_console_store = LiveConsoleEventStore(store.workspace)
    studio.refresh(project.project_id)

    dialog = AscensionProtocolDialog(studio)
    events = studio.live_console_store.list_recent()

    assert len(events) == 1
    assert events[0].source == "Ascension Protocol"
    assert events[0].stage == "root-preparation"
    assert events[0].state is MissionState.RUNNING
    assert events[0].progress_percent == 0
    assert "Stage 1 of 9" in events[0].summary
    assert events[0].guardian_protected
    assert "device-dna.romverse" in events[0].evidence_refs[0]
    assert "rooted ROM input" in events[0].title
    assert "root" in events[0].explanation.casefold()

    companion = CompanionCenter(studio.live_console_store)
    telemetry = companion._telemetry_snapshot()
    assert telemetry.live_console_integrity == "trusted"
    assert len(telemetry.live_console_events) == 1
    assert telemetry.live_console_events[0].source == "Ascension Protocol"
    assert telemetry.live_console_events[0].progress_percent == 0
    assert telemetry.live_console_events[0].guardian_protected
    assert telemetry.live_console_execution_authority == "none"
    assert not telemetry.raw_terminal_included
    companion.shutdown()

    dialog.accept()
    paused = studio.live_console_store.list_recent()[0]
    assert paused.state is MissionState.ATTENTION
    assert paused.progress_percent == 0
    assert "paused" in paused.summary.casefold()
    assert "preserved" in paused.explanation.casefold()
    assert "root applied" not in paused.summary.casefold()
    studio.close()


def test_ascension_rechecks_when_live_device_context_changes(tmp_path: Path) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Live evidence")
    source = tmp_path / "popsicle_images_OS3.0.318.0.WPBCNXM_test.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)

    refreshes: list[bool] = []
    original_refresh = dialog.refresh

    def record_refresh() -> None:
        refreshes.append(True)
        original_refresh()

    dialog.refresh = record_refresh
    studio.set_devices([])
    assert not refreshes

    studio.set_devices([AndroidDevice("serial", DeviceState.DEVICE, codename="popsicle")])
    assert refreshes


def test_ascension_routes_verified_patch_into_rooted_rom_before_guardian_review(
    tmp_path: Path,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Rooted ROM route")
    source = tmp_path / "popsicle_images_OS3.0.318.0.WPBCNXM_test.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)

    dialog.patched_receipt = object()
    dialog.integration_receipt = None
    dialog._update_primary_action(dialog.current_report)
    assert dialog.acquire_button.text() == "Integrate verified root image into ROM"

    dialog.integration_receipt = object()
    dialog.build_seal_receipt = None
    dialog._update_primary_action(dialog.current_report)
    assert dialog.acquire_button.text() == "Seal rooted ROM build input"

    dialog.build_seal_receipt = object()
    dialog._update_primary_action(dialog.current_report)
    assert "Guardian" in dialog.acquire_button.text()


def test_ascension_primary_button_copy_and_dispatch_use_the_same_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Ascension state resolver")
    source = tmp_path / "popsicle_images_OS3.0.318.0.WPBCNXM_test.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    ready_report = SimpleNamespace(blocked=False, gates=())
    calls: list[str] = []
    monkeypatch.setattr(dialog, "_integrate_root_rom", lambda: calls.append("integrate"))
    monkeypatch.setattr(dialog, "_seal_root_build", lambda: calls.append("seal"))
    monkeypatch.setattr(dialog, "_review_guardian_manifest", lambda: calls.append("review"))
    monkeypatch.setattr(dialog, "_open_verified_manager", lambda: calls.append("open-manager"))
    monkeypatch.setattr(dialog, "_find_patched_on_phone", lambda: calls.append("find-phone"))
    monkeypatch.setattr(dialog, "_import_patched", lambda: calls.append("import"))
    monkeypatch.setattr(dialog, "_review_handoff", lambda: calls.append("review-handoff"))
    monkeypatch.setattr(dialog, "_resolve_blocked_preparation", lambda: calls.append("resolve"))
    monkeypatch.setattr(dialog, "_ensure_patch_capsule", lambda: calls.append("prepare"))
    monkeypatch.setattr(dialog, "_acquire", lambda: calls.append("acquire"))

    def assert_action(expected: str, label: str, report=ready_report) -> None:
        dialog.current_report = report
        dialog._update_primary_action(report)
        assert label in dialog.acquire_button.text()
        assert dialog._primary_action_key(report) == expected
        dialog._primary_action()
        assert calls[-1] == expected

    dialog.patched_receipt = object()
    dialog.integration_receipt = None
    assert_action("integrate", "Integrate")

    dialog.integration_receipt = object()
    dialog.build_seal_receipt = None
    assert_action("seal", "Seal")

    dialog.build_seal_receipt = object()
    assert_action("review", "Guardian")

    dialog.patched_receipt = None
    dialog.integration_receipt = None
    dialog.build_seal_receipt = None
    dialog.patch_capsule = object()
    dialog.handoff_receipt = object()
    monkeypatch.setattr(dialog, "_patched_output_service", lambda: object())
    assert_action("open-manager", "Open verified")

    dialog.manager_launch_receipt = object()
    assert_action("find-phone", "Find")

    dialog.handoff_receipt = None
    dialog.manager_launch_receipt = None
    monkeypatch.setattr(dialog, "_handoff_service", lambda: object())
    assert_action("review-handoff", "Review guided")

    dialog.patch_capsule = None
    blocked_report = SimpleNamespace(blocked=True, gates=())
    assert_action("resolve", "Auto-resolve", blocked_report)

    dialog.verified_release = object()
    assert_action("prepare", "Continue automatic")

    dialog.verified_release = None
    assert_action("acquire", "Start automatic")
    dialog.close()
    studio.close()


def test_new_safety_blockers_outrank_historical_phone_handoff_actions(
    tmp_path: Path,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Ascension blocker precedence")
    source = tmp_path / "popsicle_images_OS3.0.318.0.WPBCNXM_test.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    dialog.patch_capsule = object()
    dialog.handoff_receipt = object()
    dialog.manager_launch_receipt = object()

    rooted = AscensionAssessment(
        project.project_id,
        AscensionMethod.MAGISK,
        "protected source",
        "boot.img",
        (
            AscensionGate(
                "root-state",
                "Current root state",
                GateState.BLOCKED,
                "An existing root identity is present.",
                "Review the existing root manager first.",
            ),
        ),
    )
    dialog._update_primary_action(rooted)
    assert dialog._primary_action_key(rooted) == "resolve"
    assert dialog.acquire_button.text() == "Review existing root first"

    mismatch = AscensionAssessment(
        project.project_id,
        AscensionMethod.MAGISK,
        "protected source",
        "boot.img",
        (
            AscensionGate(
                "device-match",
                "Source and device identity",
                GateState.BLOCKED,
                "The connected phone differs from the protected source.",
                "Select firmware for the connected phone.",
            ),
        ),
    )
    dialog._update_primary_action(mismatch)
    assert dialog._primary_action_key(mismatch) == "resolve"
    assert dialog.acquire_button.text() == "Select matching firmware"
    dialog.close()
    studio.close()


def test_ascension_marks_fresh_offline_manager_cache_as_attention_not_current(
    tmp_path: Path,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Cached official manager")
    source = tmp_path / "firmware.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    manager = tmp_path / "Magisk-v30.7.apk"
    manager.write_bytes(b"test manager")
    asset = OfficialRootAsset(
        AscensionMethod.MAGISK,
        "topjohnwu/Magisk",
        "v30.7",
        "2026-02-23T08:07:01Z",
        manager.name,
        manager.stat().st_size,
        "a" * 64,
        "https://github.com/topjohnwu/Magisk/releases/download/v30.7/Magisk-v30.7.apk",
    )
    dialog.verified_release = OfficialRootRelease(
        AscensionMethod.MAGISK,
        "topjohnwu/Magisk",
        "v30.7",
        "2026-02-23T08:07:01Z",
        asset,
        "https://github.com/topjohnwu/Magisk/releases/tag/v30.7",
    )
    dialog.manager_path = manager
    dialog.manager_acquisition_mode = "verified-cache"
    dialog.manager_verification_note = "Verified within the last 30 days."

    dialog.refresh()

    cache_label = next(
        label for label in dialog.findChildren(QLabel) if "REVALIDATED CACHE" in label.text()
    )
    card = cache_label.parentWidget()
    assert isinstance(card, QFrame)
    assert card.property("gateStatus") == "attention"
    assert "ONLINE FRESHNESS PENDING" in cache_label.text()
    assert "installed on phone: NO" in cache_label.text()
    dialog.close()
    studio.close()


def test_kernelsu_manager_plan_reports_real_inspection_progress_and_install_does_not_fake_it(
    tmp_path: Path,
) -> None:
    _app()
    manager = tmp_path / "KernelSU_v3.3.0-release.apk"
    with zipfile.ZipFile(manager, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"binary-manifest-placeholder")
        archive.writestr("classes.dex", b"dex\n035\0")
        archive.writestr("META-INF/KSU.RSA", b"certificate-placeholder")
        archive.writestr("assets/measured.bin", b"x" * 3 * 1024 * 1024)
    request = ApkInstallRequest(
        str(manager),
        "device-serial",
        battery_percent=90,
        device_free_bytes=2 * 1024**3,
    )
    manager_digest = hashlib.sha256(manager.read_bytes()).hexdigest()
    asset = OfficialRootAsset(
        AscensionMethod.KERNELSU_LKM,
        "tiann/KernelSU",
        "v3.3.0",
        "2026-08-28T00:00:00Z",
        manager.name,
        manager.stat().st_size,
        manager_digest,
        "https://github.com/tiann/KernelSU/releases/download/v3.3.0/KernelSU_v3.3.0-release.apk",
    )
    release = OfficialRootRelease(
        AscensionMethod.KERNELSU_LKM,
        "tiann/KernelSU",
        "v3.3.0",
        "2026-08-28T00:00:00Z",
        asset,
        "https://github.com/tiann/KernelSU/releases/tag/v3.3.0",
    )
    progress: list[int] = []
    plans: list[object] = []
    plan_worker = AscensionManagerPlanWorker(
        request,
        "private-device-key",
        method=AscensionMethod.KERNELSU_LKM,
        expected_release=release,
        expected_manager_path=manager,
        release_service=SimpleNamespace(load_verified=lambda _method: (release, manager.resolve())),
    )
    plan_worker.signals.progress.connect(progress.append)
    plan_worker.signals.complete.connect(plans.append)

    plan_worker.execute()

    assert len(plans) == 1
    assert isinstance(plans[0], AscensionManagerInstallPreparation)
    assert progress[0] == 0
    assert progress[-1] == 100
    assert progress == sorted(set(progress))
    assert any(0 < value < 70 for value in progress)

    install_progress: list[int] = []
    completed: list[object] = []
    service = SimpleNamespace(
        install=lambda _plan: CommandResult(("adb", "install"), 0, "Success\n", "")
    )
    install_worker = AscensionManagerInstallWorker(service, plans[0].plan)
    install_worker.signals.progress.connect(install_progress.append)
    install_worker.signals.complete.connect(completed.append)

    install_worker.execute()

    assert len(completed) == 1
    assert isinstance(completed[0], AscensionManagerInstallCompletion)
    assert completed[0].plan_digest == plans[0].plan.digest
    assert completed[0].target_key == plans[0].plan.target_key
    assert completed[0].apk_sha256 == plans[0].plan.inspection.sha256
    assert completed[0].result.returncode == 0
    assert install_progress == []


def test_kernelsu_manager_install_phase_is_visibly_indeterminate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Truthful KernelSU install progress")
    source = tmp_path / "firmware.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    manager = tmp_path / "KernelSU_v3.3.0-release.apk"
    with zipfile.ZipFile(manager, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"binary-manifest-placeholder")
        archive.writestr("classes.dex", b"dex\n035\0")
        archive.writestr("META-INF/KSU.RSA", b"certificate-placeholder")
    device = AndroidDevice(
        "device-serial",
        DeviceState.DEVICE,
        manufacturer="Example",
        model="Phone",
        codename="device",
        battery_percent=90,
        storage=StorageInfo(available_bytes=2 * 1024**3),
    )
    studio.devices = [device]
    studio.gateway = object()
    studio.adb_executable = Path("/usr/bin/adb")
    dialog = AscensionProtocolDialog(studio)
    dialog.method.setCurrentIndex(dialog.method.findData(AscensionMethod.KERNELSU_LKM))
    target_key = WorkspacePrivacy(store.workspace).pseudonym(device.serial)
    plan = create_install_plan(
        ApkInstallRequest(
            str(manager),
            device.serial,
            battery_percent=device.battery_percent,
            device_free_bytes=device.storage.available_bytes,
        ),
        target_key,
    )
    asset = OfficialRootAsset(
        AscensionMethod.KERNELSU_LKM,
        "tiann/KernelSU",
        "v3.3.0",
        "2026-08-28T00:00:00Z",
        manager.name,
        plan.inspection.file_size,
        plan.inspection.sha256,
        "https://github.com/tiann/KernelSU/releases/download/v3.3.0/KernelSU_v3.3.0-release.apk",
    )
    release = OfficialRootRelease(
        AscensionMethod.KERNELSU_LKM,
        "tiann/KernelSU",
        "v3.3.0",
        "2026-08-28T00:00:00Z",
        asset,
        "https://github.com/tiann/KernelSU/releases/tag/v3.3.0",
    )
    dialog.verified_release = release
    dialog.manager_path = manager
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    started: list[object] = []
    monkeypatch.setattr("romverse.ui.ascension_protocol.start_background", started.append)

    dialog._kernelsu_manager_plan_ready(
        AscensionManagerInstallPreparation(plan, release, manager.resolve())
    )

    assert len(started) == 1
    assert isinstance(started[0], AscensionManagerInstallWorker)
    assert dialog.progress.minimum() == 0
    assert dialog.progress.maximum() == 0
    assert not dialog.progress.isTextVisible()
    assert "does not expose a trustworthy install percentage" in dialog.status.text()
    dialog.close()
    studio.close()


def test_ascension_manager_verification_and_open_stay_indeterminate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Truthful Manager open progress")
    source = tmp_path / "firmware.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    plan = RootManagerLaunchPlan(
        project.project_id,
        AscensionMethod.MAGISK,
        "a" * 64,
        "device-serial",
        "private-device-key",
        "com.topjohnwu.magisk",
        "b" * 64,
        "c" * 64,
        "/data/app/verified/base.apk",
        str(store.workspace / "temporary-manager.apk"),
        "d" * 64,
        "e" * 64,
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(dialog, "_manager_launch_service", lambda: object())
    started = []
    monkeypatch.setattr("romverse.ui.ascension_protocol.start_background", started.append)

    dialog._manager_path_ready(plan)

    assert len(started) == 1
    assert isinstance(started[0], AscensionManagerLaunchWorker)
    assert dialog.progress.minimum() == 0
    assert dialog.progress.maximum() == 0
    assert not dialog.progress.isTextVisible()
    assert "does not expose a trustworthy completion percentage" in dialog.status.text()
    dialog.worker = None
    dialog.close()
    studio.close()


def test_ascension_guardian_phone_handoff_stays_indeterminate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Truthful Ascension handoff progress")
    source = tmp_path / "firmware.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    device = AndroidDevice(
        "device-serial",
        DeviceState.DEVICE,
        manufacturer="Example",
        model="Phone",
        codename="device",
        battery_percent=90,
        storage=StorageInfo(available_bytes=2 * 1024**3),
    )
    studio.devices = [device]
    dialog = AscensionProtocolDialog(studio)
    apk_plan = SimpleNamespace(
        inspection=SimpleNamespace(sha256="a" * 64),
        digest="b" * 64,
        assessment=SimpleNamespace(reasons=()),
    )
    plan = SimpleNamespace(
        safety_ready=True,
        apk_plan=apk_plan,
        transfer_assessment=SimpleNamespace(reasons=()),
        remote_input_path="/sdcard/Download/romverse-magisk-input.img",
        device_key="private-device-key",
        transfer_digest="c" * 64,
    )
    service = SimpleNamespace(plan=lambda *_args: plan)
    monkeypatch.setattr(dialog, "_handoff_service", lambda: service)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    started = []
    monkeypatch.setattr("romverse.ui.ascension_protocol.start_background", started.append)

    dialog._review_handoff()

    assert len(started) == 1
    assert isinstance(started[0], AscensionHandoffWorker)
    assert dialog.progress.minimum() == 0
    assert dialog.progress.maximum() == 0
    assert not dialog.progress.isTextVisible()
    assert "does not expose a trustworthy completion percentage" in dialog.status.text()
    dialog.worker = None
    dialog.close()
    studio.close()


def test_ascension_patched_image_import_waits_indeterminately_for_measured_bytes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Truthful patched image import progress")
    source = tmp_path / "firmware.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    candidate = tmp_path / "magisk_patched.img"
    candidate.write_bytes(b"fixture")
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(candidate), "Android boot image (*.img)"),
    )
    started = []
    monkeypatch.setattr("romverse.ui.ascension_protocol.start_background", started.append)

    dialog._import_patched()

    assert len(started) == 1
    assert isinstance(started[0], AscensionPreparationWorker)
    assert dialog.progress.minimum() == 0
    assert dialog.progress.maximum() == 0
    assert not dialog.progress.isTextVisible()
    assert "measured vault-copy" in dialog.status.text()
    dialog.worker = None
    dialog.close()
    studio.close()


def test_ascension_patch_capsule_waits_for_measured_copy_progress(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Truthful patch capsule progress")
    source = tmp_path / "firmware.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    manager = store.workspace / "verified-manager.apk"
    manager.write_bytes(b"verified manager")
    asset = OfficialRootAsset(
        AscensionMethod.MAGISK,
        "topjohnwu/Magisk",
        "v30.7",
        "2026-08-28T00:00:00Z",
        manager.name,
        manager.stat().st_size,
        hashlib.sha256(manager.read_bytes()).hexdigest(),
        "https://github.com/topjohnwu/Magisk/releases/download/v30.7/Magisk-v30.7.apk",
    )
    dialog.verified_release = OfficialRootRelease(
        AscensionMethod.MAGISK,
        asset.repository,
        asset.tag,
        asset.published_at,
        asset,
        "https://github.com/topjohnwu/Magisk/releases/tag/v30.7",
    )
    dialog.manager_path = manager
    dialog.current_report = SimpleNamespace(blocked=False, gates=())
    monkeypatch.setattr(dialog, "_revalidate_official_manager", lambda _method: True)
    started = []
    monkeypatch.setattr("romverse.ui.ascension_protocol.start_background", started.append)

    dialog._ensure_patch_capsule()

    assert len(started) == 1
    assert isinstance(started[0], AscensionPreparationWorker)
    assert dialog.progress.minimum() == 0
    assert dialog.progress.maximum() == 0
    assert not dialog.progress.isTextVisible()
    assert "measured byte progress" in dialog.status.text()
    dialog.worker = None
    dialog.close()
    studio.close()


def test_ascension_integration_is_measured_and_build_seal_is_honestly_indeterminate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Truthful local root build progress")
    source = tmp_path / "firmware.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    started = []
    monkeypatch.setattr("romverse.ui.ascension_protocol.start_background", started.append)

    dialog.patched_receipt = object()
    dialog._integrate_root_rom()

    assert len(started) == 1
    assert isinstance(started[0], AscensionIntegrationWorker)
    assert dialog.progress.maximum() == 0
    assert "measured byte progress" in dialog.status.text()

    dialog.worker = None
    dialog.integration_receipt = object()
    dialog._seal_root_build()

    assert len(started) == 2
    assert isinstance(started[1], AscensionBuildSealWorker)
    assert dialog.progress.maximum() == 0
    assert not dialog.progress.isTextVisible()
    assert "no trustworthy total" in dialog.status.text()
    dialog.worker = None
    dialog.close()
    studio.close()


def test_ascension_failure_explains_and_retries_the_exact_manager_open_stage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Safe manager retry")
    source = tmp_path / "firmware.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    dialog.patch_capsule = object()
    dialog.handoff_receipt = object()
    dialog.manager_launch_receipt = None
    dialog.current_report = SimpleNamespace(blocked=False, gates=())
    calls: list[str] = []
    monkeypatch.setattr(dialog, "_open_verified_manager", lambda: calls.append("open-manager"))

    dialog._failed(
        "The vaulted manager freshness check is 31 days old. Reconnect so ROMVERSE can verify the current stable release."
    )

    assert dialog.acquire_button.text() == "Retry the safe step"
    assert "31 days old" in dialog.status.text()
    assert "No phone partition was changed" in dialog.status.text()
    assert dialog._primary_action_key(dialog.current_report) == "open-manager"
    dialog._primary_action()
    assert calls == ["open-manager"]
    dialog.close()
    studio.close()


def test_ascension_rejects_untyped_terminal_completions(tmp_path: Path) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Typed Ascension completions")
    source = tmp_path / "firmware.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)

    dialog._capsule_ready(object())
    assert dialog.patch_capsule is None
    assert "unexpected or unverified terminal evidence" in dialog.status.text()

    dialog._handoff_ready(object())
    assert dialog.handoff_receipt is None
    assert "unexpected or unverified terminal evidence" in dialog.status.text()

    dialog._kernelsu_manager_installed(object())
    assert dialog.manager_install_plan is None
    assert "unexpected terminal evidence" in dialog.status.text()

    dialog._phone_outputs_found(object())
    assert dialog.output_discovery is None
    assert "unexpected terminal evidence" in dialog.status.text()
    assert "No phone partition was changed" in dialog.status.text()
    dialog.close()
    studio.close()


def test_ascension_retries_only_typed_connectivity_failures_with_a_visible_bound(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Bounded Manager network recovery")
    source = tmp_path / "firmware.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.live_console_store = LiveConsoleEventStore(store.workspace)
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    dialog.automatic_attempted.update(AscensionMethod)
    dialog.show()
    app.processEvents()
    retries: list[bool] = []
    monkeypatch.setattr(dialog, "_acquire", lambda: retries.append(True))

    sensitive = "/home/steve/private/manager.apk device bbb7782c"
    dialog._manager_connectivity_failed(f"official provider timed out near {sensitive}")
    assert dialog.manager_retry_timer.isActive()
    assert dialog.manager_retry_attempts[AscensionMethod.MAGISK] == 1
    assert "retry automatically" in dialog.status.text()
    assert "Rejected hashes" in dialog.status.text()
    assert not dialog.acquire_button.isEnabled()
    assert any(
        event.stage == "official-manager-connectivity"
        for event in studio.live_console_store.list_recent()
    )

    dialog.manager_retry_timer.stop()
    dialog._retry_official_manager()
    assert retries == [True]
    dialog._manager_connectivity_failed(f"official provider reset the connection near {sensitive}")
    assert dialog.manager_retry_attempts[AscensionMethod.MAGISK] == 2
    dialog.manager_retry_timer.stop()
    dialog._retry_official_manager()
    assert retries == [True, True]

    dialog._manager_connectivity_failed(f"official provider still unavailable near {sensitive}")
    assert not dialog.manager_retry_timer.isActive()
    assert dialog.acquire_button.text() == "Retry the safe step"
    assert "after 2 bounded automatic retries" in dialog.status.text()
    assert sensitive in dialog.status.text()
    assert "No phone partition was changed" in dialog.status.text()
    shared_console_text = "\n".join(
        "\n".join((event.title, event.summary, event.explanation, event.next_action))
        for event in studio.live_console_store.list_recent()
    )
    assert sensitive not in shared_console_text
    assert "/home/steve" not in shared_console_text
    assert "bbb7782c" not in shared_console_text
    dialog.close()
    studio.close()


def test_verified_patch_continues_into_safe_local_integration_automatically(
    tmp_path: Path,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Automatic local Ascension")
    source = tmp_path / "popsicle_images_OS3.0.318.0.WPBCNXM_test.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    dialog.automatic_attempted.update(AscensionMethod)
    dialog.refresh = lambda: None
    continued: list[bool] = []
    dialog._integrate_root_rom = lambda: continued.append(True)
    receipt = PatchedImageReceipt(
        2,
        "receipt",
        project.project_id,
        AscensionMethod.MAGISK,
        "2026-08-29T00:00:00+00:00",
        "1" * 64,
        "2" * 64,
        "projects/project/patched.img",
        "3" * 64,
        1024,
        4,
        512,
        "android-boot-header-and-source-bound-capsule",
        "none",
        False,
        "4" * 64,
        lineage_scope="normalized-header-and-kernel",
        lineage_confidence="high",
        normalized_header_sha256="5" * 64,
        source_kernel_size_bytes=1024,
        patched_kernel_size_bytes=1024,
        source_kernel_sha256="6" * 64,
        patched_kernel_sha256="6" * 64,
    )

    dialog._patched_ready(receipt)
    dialog._continue_after_patched()

    assert dialog.patched_receipt is receipt
    assert continued == [True]
    assert "high immutable-lineage confidence" in dialog.status.text()
    assert "continuing automatically" in dialog.status.text()


def test_multiple_phone_outputs_recommend_the_newest_match(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Newest patched output")
    source = tmp_path / "firmware.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    choices: list[tuple[object, ...]] = []
    retrieved: list[str] = []

    def choose(*args):
        choices.append(args)
        return args[3][args[4]], True

    monkeypatch.setattr(QInputDialog, "getItem", choose)
    monkeypatch.setattr(dialog, "_retrieve_phone_output", retrieved.append)
    completion = _output_discovery_completion(
        project.project_id,
        (
            "magisk_patched-31000_new.img",
            "magisk_patched-30000_old.img",
        ),
    )
    _bind_output_discovery(studio, dialog, completion, monkeypatch)
    dialog._phone_outputs_found(completion)

    assert choices[0][4] == 0
    assert "newest first" in str(choices[0][2])
    assert retrieved == ["magisk_patched-31000_new.img"]
    dialog.close()
    studio.close()


def test_automatic_output_watch_waits_without_repeated_prompts_and_flows_to_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Automatic patched output watch")
    source = tmp_path / "firmware.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    dialog.output_watch_active = True
    dialog.output_watch_started_at = 100.0
    dialog.output_watch_timer.start()
    dialog.method.setEnabled(False)
    dialog.acquire_button.setEnabled(False)
    monkeypatch.setattr("romverse.ui.ascension_protocol.monotonic", lambda: 130.0)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: (_ for _ in ()).throw(AssertionError("watch must not prompt each scan")),
    )

    empty = _output_discovery_completion(project.project_id, ())
    _bind_output_discovery(studio, dialog, empty, monkeypatch)
    dialog._phone_outputs_found(empty)

    assert dialog.output_watch_active
    assert dialog.output_watch_timer.isActive()
    assert not dialog.acquire_button.isEnabled()
    assert "automatic watch continues" in dialog.status.text()

    retrieved: list[str] = []
    monkeypatch.setattr(dialog, "_retrieve_phone_output", retrieved.append)
    monkeypatch.setattr(dialog, "_record_output_discovery_note", lambda _method: None)
    found = _output_discovery_completion(
        project.project_id,
        ("magisk_patched-verified.img",),
    )
    _bind_output_discovery(studio, dialog, found, monkeypatch)
    dialog._phone_outputs_found(found)

    assert not dialog.output_watch_active
    assert not dialog.output_watch_timer.isActive()
    assert retrieved == ["magisk_patched-verified.img"]
    dialog.close()
    studio.close()


def test_automatic_output_watch_times_out_honestly_and_stops_when_dialog_closes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Bounded patched output watch")
    source = tmp_path / "firmware.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    dialog.output_watch_active = True
    dialog.output_watch_started_at = 10.0
    dialog.output_watch_timer.start()
    monkeypatch.setattr(
        "romverse.ui.ascension_protocol.monotonic",
        lambda: 10.0 + dialog.OUTPUT_WATCH_SECONDS + 1,
    )

    dialog._watch_phone_output_tick()

    assert not dialog.output_watch_active
    assert not dialog.output_watch_timer.isActive()
    assert "finished after nine minutes" in dialog.status.text()
    assert "Nothing was copied or changed" in dialog.status.text()

    dialog.output_watch_active = True
    dialog.output_watch_started_at = 20.0
    dialog.output_watch_timer.start()
    dialog.accept()
    assert not dialog.output_watch_active
    assert not dialog.output_watch_timer.isActive()
    studio.close()


def test_automatic_output_watch_stops_when_exact_phone_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Disconnected patched output watch")
    source = tmp_path / "firmware.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    dialog.output_watch_active = True
    dialog.output_watch_started_at = 100.0
    dialog.output_watch_last_scan_at = 0.0
    dialog.output_watch_timer.start()
    monkeypatch.setattr("romverse.ui.ascension_protocol.monotonic", lambda: 120.0)

    dialog._watch_phone_output_tick()

    assert not dialog.output_watch_active
    assert not dialog.output_watch_timer.isActive()
    assert "exact authorized phone is unavailable" in dialog.status.text()
    assert "no file was copied" in dialog.status.text()
    dialog.close()
    studio.close()


def test_output_discovery_diagnostic_is_privacy_safe_and_persistent(
    tmp_path: Path,
) -> None:
    _app()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Output discovery diagnosis")
    source = tmp_path / "firmware.tgz"
    source.write_bytes(b"firmware")
    store.import_original(project.project_id, source)
    studio = RomStudio(store, DevicePackRegistry(()))
    studio.live_console_store = LiveConsoleEventStore(store.workspace)
    studio.refresh(project.project_id)
    dialog = AscensionProtocolDialog(studio)
    dialog.output_discovery = PatchedOutputDiscovery(
        schema_version=1,
        discovery_id="a" * 32,
        project_id=project.project_id,
        method=AscensionMethod.MAGISK,
        created_at="2026-08-30T00:00:00+00:00",
        handoff_receipt_digest="b" * 64,
        device_key="device-key",
        state="found",
        candidate_count=2,
        candidate_refs=("c" * 64, "d" * 64),
        candidate_set_digest="e" * 64,
        recommended_name_ref="c" * 64,
        truncated=False,
        data_scope="filenames-only",
        source_directory="/sdcard/Download",
        ordering="modified-descending",
        phone_changed=False,
        execution_authority="none",
        receipt_digest="f" * 64,
    )

    dialog._record_output_discovery_note(AscensionMethod.MAGISK)
    event = studio.live_console_store.list_recent()[0]
    rendered = " ".join((event.title, event.summary, event.explanation, event.next_action))

    assert event.stage == "patched-output-discovery"
    assert event.state is MissionState.INFORMATION
    assert event.confidence.value == "verified"
    assert "2 matching" in event.summary
    assert "filenames only" in event.explanation
    assert "magisk_patched" not in rendered
    assert "PRIVATE-SERIAL" not in rendered
    assert event.evidence_refs == (
        f"projects/{project.project_id}/ascension/phone-output/magisk/latest-discovery.romverse",
    )
    dialog.close()
    studio.close()


def test_guardian_manifest_dialog_explains_exact_change_and_prohibitions() -> None:
    _app()
    check = AscensionManifestCheck(
        "slot-policy",
        "Exact target slot",
        ManifestState.BLOCKED,
        "No flash-validated slot policy is active.",
        "Install an exact signed Device Pack update.",
        "open-device-atlas",
        "Open Device Atlas",
    )
    manifest = AscensionGuardianManifest(
        1,
        "manifest",
        "2026-08-29T00:00:00+00:00",
        "project",
        "plan",
        "1" * 64,
        AscensionMethod.MAGISK,
        "2" * 64,
        "pack",
        "1",
        "3" * 64,
        "device-key",
        "Xiaomi 17 Pro Max",
        "popsicle",
        "init_boot",
        "",
        "usb-fastboot-final-handoff",
        "4" * 64,
        "5" * 64,
        "6" * 64,
        (check,),
        ("Re-identify the exact phone without changing it.",),
        ("Bootloader relock", "User-data wipe"),
        True,
        "none",
        (),
        False,
        False,
        "7" * 64,
    )

    actions: list[str] = []
    dialog = AscensionManifestDialog(manifest, resolver=actions.append)
    labels = "\n".join(label.text() for label in dialog.findChildren(QLabel))

    assert "Xiaomi 17 Pro Max" in labels
    assert "slot not yet proven" in labels
    assert "Bootloader relock" in labels
    assert "commands: NONE" in labels
    assert "1 safety gate" in labels
    action = next(
        button
        for button in dialog.findChildren(QPushButton)
        if button.text() == "Open Device Atlas"
    )
    action.click()
    assert actions == ["open-device-atlas"]


def _sealed_handoff(prohibited: tuple[str, ...]) -> AscensionFinalHandoff:
    return AscensionFinalHandoff(
        2,
        "handoff",
        "2026-08-29T00:00:00+00:00",
        "project",
        AscensionMethod.MAGISK,
        "manifest",
        "7" * 64,
        "plan",
        "1" * 64,
        "2" * 64,
        "pack",
        "1",
        "3" * 64,
        "device-key",
        "Xiaomi 17 Pro Max",
        "popsicle",
        "init_boot",
        "a",
        "a",
        "usb-fastboot-final-handoff",
        "usb",
        82,
        True,
        "projects/project/pristine.img",
        "4" * 64,
        "projects/project/patched.img",
        "5" * 64,
        1024,
        "6" * 64,
        "v30.7",
        "8" * 64,
        True,
        True,
        "verified-local-file",
        True,
        "none",
        (),
        False,
        False,
        False,
        False,
        prohibited,
        "9" * 64,
    )


def test_guardian_manifest_dialog_shows_sealed_final_handoff_without_success_claim() -> None:
    _app()
    check = AscensionManifestCheck(
        "final-consent",
        "Final human confirmation",
        ManifestState.ATTENTION,
        "No write is authorized.",
        "Review the exact consequences.",
        "none",
        "",
    )
    prohibited = (
        "Bootloader relock",
        "Bootloader unlock",
        "User-data wipe",
        "Write to any partition or slot not named by this manifest",
        "Use an image whose SHA-256 differs from this manifest",
    )
    manifest = AscensionGuardianManifest(
        2,
        "manifest",
        "2026-08-29T00:00:00+00:00",
        "project",
        "plan",
        "1" * 64,
        AscensionMethod.MAGISK,
        "2" * 64,
        "pack",
        "1",
        "3" * 64,
        "device-key",
        "Xiaomi 17 Pro Max",
        "popsicle",
        "init_boot",
        "a",
        "usb-fastboot-final-handoff",
        "4" * 64,
        "5" * 64,
        "6" * 64,
        (check,),
        ("Re-identify the exact phone without changing it.",),
        prohibited,
        True,
        "none",
        (),
        False,
        False,
        "7" * 64,
    )
    handoff = _sealed_handoff(prohibited)

    actions: list[str] = []
    dialog = AscensionManifestDialog(
        manifest,
        resolver=actions.append,
        final_handoff=handoff,
    )
    labels = "\n".join(label.text() for label in dialog.findChildren(QLabel))

    assert "Final Guardian handoff packet is ready" in labels
    assert "EXACT EVIDENCE SEALED" in labels
    assert "82% battery" in labels
    assert "hash-verified local-drive backup" in labels
    assert "PRIVATE • BOUNDED • LINK-SAFE" in labels
    assert "Execution authority  •  NONE" in labels
    assert "root applied: NO" in labels
    consent = next(
        button
        for button in dialog.findChildren(QPushButton)
        if button.text() == "Begin final consent review"
    )
    consent.click()
    assert actions == ["record-final-consent"]


def test_consent_review_requires_every_acknowledgement_and_typed_phrase() -> None:
    _app()
    prohibited = (
        "Bootloader relock",
        "Bootloader unlock",
        "User-data wipe",
        "Write to any partition or slot not named by this manifest",
        "Use an image whose SHA-256 differs from this manifest",
    )
    dialog = AscensionConsentReviewDialog(_sealed_handoff(prohibited))
    labels = "\n".join(label.text() for label in dialog.findChildren(QLabel))

    assert "KEEP DATA / NO WIPE" in labels
    assert "PERMANENTLY PROHIBITED" in labels
    assert "rejects corrupt, oversized, linked, redirected, or stale evidence" in labels
    assert "Execution authority: NONE" in labels
    assert "QCheckBox#ConsentCheck::indicator" in dialog.styleSheet()
    assert not dialog.record_button.isEnabled()
    for _key, checkbox in dialog.checkboxes:
        checkbox.setChecked(True)
    assert not dialog.record_button.isEnabled()
    dialog.phrase.setText("ASCEND")
    assert dialog.record_button.isEnabled()
    dialog.record_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert set(dialog.accepted_acknowledgements) == {
        key for key, _copy in AscensionConsentReviewDialog.ITEMS
    }
