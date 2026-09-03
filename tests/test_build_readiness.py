import hashlib
import json
import zipfile

from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.attestations import (
    DevicePackAttestationVerifier,
    PhysicalRecoveryAttestationReport,
)
from romverse.device_packs.models import (
    AvbExecutionPolicy,
    AvbHashtreeParameters,
    AvbPolicyAuthority,
    AvbPolicyMode,
    CapabilityStatus,
    DeviceBuildContract,
    DevicePack,
    DevicePostWriteVerificationContract,
    DeviceWriteContract,
    DeviceWriteTransport,
    DynamicPartitionGroup,
    ErofsRebuildParameters,
    FirmwareSourceContract,
    PackCapability,
    PartitionBuildRule,
    PartitionReadbackRule,
    PartitionVerificationMethod,
    PartitionWriteRule,
    PostBootPropertyRule,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.infrastructure.process import SubprocessRunner
from romverse.infrastructure.provisioning import GENESIS_REQUIRED_TOOLS
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.builds import RomBuildPlanner
from romverse.rom.inspection import RomInspectionService
from romverse.rom.projects import RomProjectStore
from romverse.rom.readiness import BuildReadinessService, GateStatus, remediation_for
from romverse.rom.recipes import (
    RecipeExecutor,
    RecipeStep,
    RecipeStore,
    RomRecipe,
    save_run_receipt,
)
from romverse.rom.source_intelligence import FirmwareSourceIntelligenceService


def _registry(status=CapabilityStatus.PLANNED):
    capability = PackCapability("firmware.operations", "Firmware", status, "locked", "Test pack")
    pack = DevicePack("test.pack", "1", "Test", 10, ("test",), (), (), (capability,), (), "a" * 64)
    return DevicePackRegistry((pack,))


def _prepared_project(tmp_path):
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("system.img", b"system")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Ready", "test.pack")
    store.import_original(project.project_id, source)
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    inspection.extract_project_tree(project.project_id)
    RomBuildPlanner(store).plan(project.project_id)
    return store, project


def test_build_readiness_fails_closed_for_planned_device_pack(tmp_path):
    store, project = _prepared_project(tmp_path)
    tools = tuple(
        ToolStatus(name, True)
        for name in ("Python", "Git", "7-Zip", "Unzip", "Make", "Java", "AVBTool")
    )
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="test",
        model="Phone",
        battery_percent=80,
        bootloader_locked=False,
        verified_boot="orange",
    )
    service = BuildReadinessService(store, _registry(), tools)

    report = service.assess(project.project_id, (device,))

    assert report.workspace_ready
    assert not report.build_ready
    assert not report.flash_ready
    assert any(
        gate.gate_id == "device-pack-build" and gate.status is GateStatus.BLOCKED
        for gate in report.gates
    )
    assert any(
        gate.gate_id == "device-pack-flash" and gate.status is GateStatus.BLOCKED
        for gate in report.gates
    )
    pack_gate = next(gate for gate in report.gates if gate.gate_id == "device-pack-build")
    assert "Exact source contract required" in pack_gate.evidence
    resolution = remediation_for(pack_gate)
    assert "created automatically" in resolution.summary
    assert resolution.action_id == "autopilot"
    assert report.next_actions[0]
    assert (store.projects_root / project.project_id / service.REPORT_NAME).is_file()


def test_readiness_promotes_only_a_strict_recipe_receipt_bound_to_rollback_evidence(tmp_path):
    store, project = _prepared_project(tmp_path)
    project_dir = store.projects_root / project.project_id
    tree = store.working_root / project.project_id / "tree"
    snapshot_root = store.snapshots_root / project.project_id / "recipes"
    recipe = RomRecipe(
        1,
        "remove-system-image",
        "Remove staged image",
        "Contained test mutation",
        (RecipeStep("remove", "remove_package", "system.img"),),
    )
    RecipeStore().save(project_dir, recipe)
    executor = RecipeExecutor()
    receipt = executor.execute_approved(
        recipe,
        tree,
        snapshot_root,
        executor.issue_approval(recipe, tree),
    )
    receipt_path = save_run_receipt(
        project_dir,
        receipt,
        recipe=recipe,
        tree_root=tree,
        snapshot_root=snapshot_root,
    )
    service = BuildReadinessService(store, _registry())

    verified = service.assess(project.project_id, persist=False)
    assert (
        next(gate for gate in verified.gates if gate.gate_id == "recipe").status is GateStatus.PASS
    )

    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["authority"] = "forged"
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")
    rejected = service.assess(project.project_id, persist=False)
    recipe_gate = next(gate for gate in rejected.gates if gate.gate_id == "recipe")

    assert recipe_gate.status is GateStatus.BLOCKED
    assert "no matching verified receipt" in recipe_gate.evidence
    bundle = service.export_evidence_bundle(rejected)
    assert all(label != "recipe-receipt" for label, _path, _digest in bundle.artifacts)


def test_partition_bundle_blueprint_advances_local_baseline_but_not_flash_authority(tmp_path):
    store, project = _prepared_project(tmp_path)
    blueprint = FirmwareSourceIntelligenceService(store, (), SubprocessRunner()).prepare(
        project.project_id
    )

    report = BuildReadinessService(store, _registry()).assess(project.project_id)
    states = {gate.gate_id: gate.status for gate in report.gates}

    assert blueprint.source_kind == "partition-bundle"
    assert blueprint.authority == "project-local-inventory-evidence-only"
    assert not blueprint.avb_topology_verified
    assert states["device-pack-build"] is GateStatus.PASS
    assert states["device-build-plan"] is GateStatus.PASS
    assert states["local-candidate"] is GateStatus.PASS
    assert states["device-pack-flash"] is GateStatus.BLOCKED
    assert states["device"] is GateStatus.BLOCKED
    assert states["physical-validation"] is GateStatus.BLOCKED
    assert not report.flash_ready
    plan_gate = next(gate for gate in report.gates if gate.gate_id == "device-build-plan")
    assert plan_gate.label == "Deterministic source/build plan"
    assert "hash-backed 1-image baseline inventory" in plan_gate.evidence
    assert "fastboot super" not in plan_gate.evidence


def test_readiness_uses_structure_scoped_tools_without_granting_build_authority(tmp_path):
    store, project = _prepared_project(tmp_path)
    tools = tuple(
        ToolStatus(name, True)
        for name in (
            "Python",
            "simg2img",
            "AVBTool",
        )
    )

    report = BuildReadinessService(store, _registry(), tools).assess(project.project_id)

    tool_gate = next(gate for gate in report.gates if gate.gate_id == "tools")
    build_gate = next(gate for gate in report.gates if gate.gate_id == "device-pack-build")
    assert tool_gate.status is GateStatus.PASS
    assert "source-scoped" in tool_gate.evidence
    assert "simg2img" in tool_gate.evidence
    assert build_gate.status is GateStatus.BLOCKED
    assert not report.build_ready


def test_device_pack_flash_gate_cannot_be_bypassed_by_local_recovery_evidence(tmp_path):
    store, project = _prepared_project(tmp_path)
    service = BuildReadinessService(store, _registry())

    report = service.assess(project.project_id)
    gate = next(item for item in report.gates if item.gate_id == "device-pack-flash")

    assert gate.status is GateStatus.BLOCKED
    remediation = remediation_for(gate)
    assert "cannot replace" in remediation.fixes[-1]
    assert remediation.action_id == "device-packs"
    assert not report.flash_ready


def test_automatic_recovery_contract_stays_attention_until_exact_write_contract_exists(
    tmp_path,
    monkeypatch,
):
    from types import SimpleNamespace

    from romverse.ascension.evidence import AscensionEvidenceService
    from romverse.backup.handoff import BackupHandoffService, CloudBackupProvider
    from romverse.rom.build_execution import LocalDeviceBuildExecutor
    from romverse.rom.debloat import DebloatService
    from romverse.rom.source_intelligence import FirmwareSourceIntelligenceService

    store, project = _prepared_project(tmp_path)
    store.create_working_copy(project.project_id)
    store.create_snapshot(project.project_id)
    blueprint = SimpleNamespace(
        source_kind="fastboot-super",
        manufacturer="test",
        codename="product",
        plan_digest="1" * 64,
        candidate_sha256="2" * 64,
        baseline_candidate_ready=True,
        avb_topology_verified=False,
        blueprint_digest="3" * 64,
        partitions=(SimpleNamespace(name="system"),),
    )
    rollback = SimpleNamespace(record_digest="4" * 64, stock_recovery=object())
    monkeypatch.setattr(FirmwareSourceIntelligenceService, "load", lambda *_args: blueprint)
    monkeypatch.setattr(AscensionEvidenceService, "load", lambda *_args: rollback)
    tools = tuple(ToolStatus(name, True) for name in GENESIS_REQUIRED_TOOLS)
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="test",
        model="Phone",
        product="product",
        codename="product",
        battery_percent=90,
        bootloader_locked=False,
        verified_boot="orange",
    )

    # A redundant receipt from an earlier route must not override the currently
    # selected pristine protected source or create a false signing requirement.
    with monkeypatch.context() as stale_receipt:
        stale_receipt.setattr(
            LocalDeviceBuildExecutor,
            "load_receipt",
            lambda *_args: SimpleNamespace(receipt_digest="5" * 64),
        )
        report = BuildReadinessService(store, _registry(), tools).assess(
            project.project_id,
            (device,),
        )

    states = {gate.gate_id: gate.status for gate in report.gates}
    assert states["device-pack-flash"] is GateStatus.ATTENTION
    assert states["recovery"] is GateStatus.PASS
    assert states["signer"] is GateStatus.PASS
    assert states["user-backup"] is GateStatus.ATTENTION
    assert states["physical-validation"] is GateStatus.ATTENTION
    assert not report.guardian_handoff_ready
    assert not report.flash_ready
    assert report.blockers == ()
    assert "byte-identical" in next(
        gate.evidence for gate in report.gates if gate.gate_id == "signer"
    )

    BackupHandoffService(store).confirm_cloud(
        project.project_id,
        device,
        CloudBackupProvider.XIAOMI,
        "Completed today",
        backup_completed=True,
        restore_access_confirmed=True,
        critical_data_scope_reviewed=True,
        limitations_acknowledged=True,
    )
    completed = BuildReadinessService(store, _registry(), tools).assess(
        project.project_id,
        (device,),
    )

    assert (
        next(gate for gate in completed.gates if gate.gate_id == "user-backup").status
        is GateStatus.PASS
    )
    assert not completed.guardian_handoff_ready
    assert not completed.flash_ready
    assert (
        remediation_for(
            next(gate for gate in completed.gates if gate.gate_id == "device-pack-flash")
        ).action_id
        == "device-packs"
    )

    monkeypatch.setattr(
        DebloatService,
        "load_receipt",
        lambda *_args: SimpleNamespace(removed_app_count=1, keep_all=False),
    )
    mutated = BuildReadinessService(store, _registry(), tools).assess(
        project.project_id,
        (device,),
        persist=False,
    )
    mutated_states = {gate.gate_id: gate.status for gate in mutated.gates}
    assert mutated_states["local-candidate"] is GateStatus.BLOCKED
    assert mutated_states["signer"] is GateStatus.ATTENTION
    assert not mutated.signing_ready


def test_pipeline_simulation_stops_before_unsupported_build_and_never_changes_phone(tmp_path):
    store, project = _prepared_project(tmp_path)
    service = BuildReadinessService(store, _registry())
    report = service.assess(project.project_id)

    receipt = service.simulate(report)

    assert receipt.stopped_at == "Build"
    assert not receipt.phone_changed
    assert not receipt.success
    assert (store.projects_root / project.project_id / service.SIMULATION_NAME).is_file()


def test_ascension_build_seal_is_a_real_local_candidate_but_guardian_review_remains(
    tmp_path,
    monkeypatch,
):
    from types import SimpleNamespace

    from romverse.ascension.build_handoff import RootRomBuildHandoffService
    from romverse.ascension.evidence import AscensionEvidenceService
    from romverse.ascension.integration import RootRomIntegrationService
    from romverse.ascension.manifest import AscensionGuardianManifestService
    from romverse.ascension.models import AscensionMethod
    from romverse.ascension.planning import AscensionRootPlanService
    from romverse.rom.source_intelligence import FirmwareSourceIntelligenceService

    store, project = _prepared_project(tmp_path)
    store.create_working_copy(project.project_id)
    store.create_snapshot(project.project_id)
    blueprint = SimpleNamespace(
        source_kind="ota-payload",
        manufacturer="test",
        codename="product",
        plan_digest="1" * 64,
        candidate_sha256="2" * 64,
        baseline_candidate_ready=True,
        avb_topology_verified=False,
        blueprint_digest="3" * 64,
        partitions=(SimpleNamespace(name="system"),),
    )
    rollback = SimpleNamespace(record_digest="4" * 64, stock_recovery=object())
    integration = SimpleNamespace(integration_digest="5" * 64)
    seal = SimpleNamespace(
        integration_digest=integration.integration_digest,
        handoff_digest="6" * 64,
        target_partition="init_boot",
        artifact_sha256="7" * 64,
    )
    root_plan = SimpleNamespace(
        target_partition="init_boot",
        root_image_artifact_sha256=seal.artifact_sha256,
    )
    manifest = SimpleNamespace(review_ready=False, manifest_digest="8" * 64)
    monkeypatch.setattr(FirmwareSourceIntelligenceService, "load", lambda *_args: blueprint)
    monkeypatch.setattr(AscensionEvidenceService, "load", lambda *_args: rollback)
    monkeypatch.setattr(
        RootRomIntegrationService,
        "load",
        lambda _self, _project_id, method: (
            integration if method is AscensionMethod.MAGISK else None
        ),
    )
    monkeypatch.setattr(
        RootRomBuildHandoffService,
        "load",
        lambda _self, _project_id, method: seal if method is AscensionMethod.MAGISK else None,
    )
    monkeypatch.setattr(
        AscensionRootPlanService,
        "load",
        lambda _self, _project_id, method: root_plan if method is AscensionMethod.MAGISK else None,
    )
    monkeypatch.setattr(AscensionRootPlanService, "matches_device", lambda *_args: True)
    monkeypatch.setattr(
        AscensionGuardianManifestService,
        "load",
        lambda _self, _project_id, method: manifest if method is AscensionMethod.MAGISK else None,
    )
    monkeypatch.setattr(
        AscensionGuardianManifestService,
        "matches_device",
        lambda *_args: True,
    )
    tools = tuple(ToolStatus(name, True) for name in GENESIS_REQUIRED_TOOLS)
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="test",
        model="Phone",
        product="product",
        codename="product",
        battery_percent=90,
        bootloader_locked=False,
        verified_boot="orange",
    )

    report = BuildReadinessService(store, _registry(), tools).assess(
        project.project_id,
        (device,),
        persist=False,
    )

    states = {gate.gate_id: gate.status for gate in report.gates}
    assert states["local-candidate"] is GateStatus.PASS
    assert states["signer"] is GateStatus.PASS
    assert states["ascension-guardian"] is GateStatus.ATTENTION
    assert report.local_candidate_ready
    assert report.signing_ready
    assert not report.guardian_handoff_ready
    assert not report.flash_ready
    assert "OEM re-signing is not claimed" in next(
        gate.evidence for gate in report.gates if gate.gate_id == "signer"
    )


def test_exact_source_bound_pack_is_build_capable_while_phone_is_offline(tmp_path):
    source = tmp_path / "exact.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("system.img", b"system")
    archive_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Offline exact", "test.exact")
    project = store.import_original(project.project_id, source)
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    inspection.extract_project_tree(project.project_id)
    RomBuildPlanner(store).plan(project.project_id)
    contract = DeviceBuildContract(
        "test-contract",
        1,
        FirmwareSourceContract("TEST", archive_sha256, "b" * 64),
        4096,
        512,
        2,
        False,
        (DynamicPartitionGroup("group", 4096),),
        (
            PartitionBuildRule(
                "system",
                512,
                4096,
                "group",
                "erofs",
                "rebuild",
                "c" * 64,
                ErofsRebuildParameters(
                    "lz4hc",
                    12,
                    True,
                    0,
                    "00000000-0000-0000-0000-000000000000",
                    "/system",
                    True,
                    True,
                ),
                AvbHashtreeParameters("sha256", "d" * 64, False),
            ),
        ),
        ("system",),
        "e" * 64,
        "f" * 64,
        ("system.img", "super.img", "vbmeta_system.img"),
    )
    capability = PackCapability(
        "firmware.operations", "Firmware", CapabilityStatus.SUPPORTED, "model_specific", "Exact"
    )
    pack = DevicePack(
        "test.exact",
        "1",
        "Exact",
        10,
        ("test",),
        ("phone",),
        (),
        (capability,),
        (),
        "a" * 64,
        contract,
    )

    report = BuildReadinessService(store, DevicePackRegistry((pack,))).assess(
        project.project_id,
        (),
    )
    gate = next(item for item in report.gates if item.gate_id == "device-pack-build")

    assert gate.status is GateStatus.PASS
    assert "verified offline" in gate.evidence
    assert not report.flash_ready


def test_build_evidence_bundle_is_content_addressed_and_contains_only_manifests(tmp_path):
    store, project = _prepared_project(tmp_path)
    service = BuildReadinessService(
        store, _registry(), (ToolStatus("Python", True, "/python", "3"),)
    )
    report = service.assess(project.project_id)

    first = service.export_evidence_bundle(report)
    second = service.export_evidence_bundle(report)

    assert first.evidence_digest == second.evidence_digest
    assert first.output_path == second.output_path
    assert all("original_roms" not in path for _label, path, _digest in first.artifacts)
    assert (store.workspace / first.output_path).is_file()


def test_readiness_consumes_only_exact_stored_physical_attestation(tmp_path) -> None:
    source = tmp_path / "exact-flash.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("system.img", b"system")
    archive_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Flash evidence", "test.flash")
    store.import_original(project.project_id, source)
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    inspection.extract_project_tree(project.project_id)
    RomBuildPlanner(store).plan(project.project_id)
    envelope_sha256 = "8" * 64
    contract = DeviceBuildContract(
        "test-flash-contract",
        2,
        FirmwareSourceContract("TEST.FLASH", archive_sha256, "b" * 64),
        4096,
        512,
        2,
        False,
        (DynamicPartitionGroup("group", 4096),),
        (
            PartitionBuildRule(
                "system",
                512,
                4096,
                "group",
                "erofs",
                "rebuild",
                "c" * 64,
                ErofsRebuildParameters(
                    "lz4hc",
                    12,
                    True,
                    0,
                    "00000000-0000-0000-0000-000000000000",
                    "/system",
                    True,
                    True,
                ),
                AvbHashtreeParameters("sha256", "d" * 64, False),
            ),
        ),
        ("system",),
        "e" * 64,
        "f" * 64,
        ("system.img", "super.img", "vbmeta_system.img"),
        avb_execution_policy=AvbExecutionPolicy(
            AvbPolicyMode.SIGNED_CUSTOM_RECHAIN,
            AvbPolicyAuthority.FLASH_VALIDATED,
            "TEST.FLASH",
            "preserve_exact_source",
            "vbmeta_system",
            "SHA256_RSA2048",
            0,
            0,
            0,
            True,
            False,
            True,
            "a",
            "b",
            envelope_sha256,
        ),
        partition_write_contract=DeviceWriteContract(
            "test-flash-writes",
            2,
            "TEST.FLASH",
            envelope_sha256,
            True,
            False,
            True,
            True,
            (
                PartitionWriteRule(
                    "super",
                    "super.img",
                    DeviceWriteTransport.FASTBOOTD,
                    "none",
                    True,
                ),
            ),
            post_write_verification_contract=DevicePostWriteVerificationContract(
                "test-flash-post-write",
                1,
                "TEST.FLASH",
                envelope_sha256,
                (
                    PartitionReadbackRule(
                        "super",
                        DeviceWriteTransport.FASTBOOTD,
                        "none",
                        PartitionVerificationMethod.FASTBOOT_FETCH_SHA256,
                        4096,
                        "7" * 64,
                    ),
                ),
                (
                    PostBootPropertyRule("sys.boot_completed", "1"),
                    PostBootPropertyRule("ro.product.device", "product"),
                    PostBootPropertyRule("ro.build.fingerprint", "test/product/build"),
                    PostBootPropertyRule("ro.build.version.incremental", "TEST.FLASH"),
                    PostBootPropertyRule("ro.build.version.sdk", "37"),
                    PostBootPropertyRule("ro.build.version.security_patch", "2026-08-01"),
                    PostBootPropertyRule("ro.boot.verifiedbootstate", "orange"),
                ),
                True,
                300,
            ),
        ),
    )
    capabilities = (
        PackCapability(
            "firmware.operations",
            "Firmware",
            CapabilityStatus.SUPPORTED,
            "model_specific",
            "Exact build",
        ),
        PackCapability(
            "firmware.partition-layout",
            "Partition layout",
            CapabilityStatus.SUPPORTED,
            "model_specific",
            "Exact layout",
        ),
        PackCapability(
            "stock.recovery",
            "Stock recovery",
            CapabilityStatus.SUPPORTED,
            "model_specific",
            "Exact restore route",
        ),
    )
    pack = DevicePack(
        "test.flash",
        "1",
        "Flash Test",
        20,
        ("test",),
        ("phone",),
        ("product",),
        capabilities,
        (),
        "a" * 64,
        contract,
    )
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="test",
        model="phone",
        product="product",
        codename="product",
        battery_percent=90,
        bootloader_locked=False,
        verified_boot="orange",
    )
    attestation = PhysicalRecoveryAttestationReport(
        True,
        "radforge.release",
        pack.pack_id,
        pack.sha256,
        contract.source.build_id,
        device.model,
        device.product,
        tuple(sorted(DevicePackAttestationVerifier.REQUIRED_SCENARIOS)),
        "9" * 64,
        "2026-08-29T00:00:00+00:00",
        "2027-08-29T00:00:00+00:00",
        envelope_sha256,
        "verified fixture",
    )

    class ExactAttestationStore:
        @staticmethod
        def load_exact(_pack, _device):
            return attestation

    report = BuildReadinessService(
        store,
        DevicePackRegistry((pack,)),
        attestation_store=ExactAttestationStore(),
    ).assess(project.project_id, (device,))

    flash_contract = next(gate for gate in report.gates if gate.gate_id == "device-pack-flash")
    assert flash_contract.status is GateStatus.PASS
    assert not report.flash_ready
