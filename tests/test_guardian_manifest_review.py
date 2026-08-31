import hashlib
import json
import os
import stat
from dataclasses import replace

from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.models import (
    AvbExecutionPolicy,
    AvbPolicyAuthority,
    AvbPolicyMode,
    CapabilityStatus,
    DeviceBuildContract,
    DevicePack,
    DeviceWriteContract,
    DeviceWriteTransport,
    DynamicPartitionGroup,
    FirmwareSourceContract,
    PackCapability,
    PartitionBuildRule,
    PartitionWriteRule,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.flash_handoff import FlashMode, GuardianFlashHandoffService
from romverse.guardian.manifest_review import (
    GuardianManifestReviewService,
    ManifestReviewState,
)
from romverse.rom.projects import RomProjectStore
from romverse.rom.readiness import BuildGate, BuildReadinessReport, GateStatus


def _prepared(tmp_path):
    source = tmp_path / "firmware.zip"
    source.write_bytes(b"exact firmware")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Guardian review", "test.exact")
    project = store.import_original(project.project_id, source)
    gates = tuple(
        BuildGate(gate_id, label, phase, GateStatus.PASS, "verified", "flash")
        for gate_id, label, phase in (
            ("device-pack-flash", "Exact flash policy", "Recovery"),
            ("device", "Exact phone", "Flash"),
            ("battery", "Battery", "Flash"),
            ("boot", "Boot state", "Flash"),
            ("recovery", "Recovery", "Recovery"),
            ("ascension-guardian", "Root route", "Flash"),
            ("user-backup", "User backup", "Recovery"),
        )
    )
    report = BuildReadinessReport(
        1,
        "a" * 32,
        project.project_id,
        "2026-08-31T00:00:00+00:00",
        gates,
        True,
        True,
        True,
        True,
        True,
        (),
        (),
        "b" * 64,
    )
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        marketing_name="Xiaomi 17 Pro Max",
        product="popsicle",
        codename="popsicle",
    )
    capability = PackCapability(
        "firmware.operations",
        "Firmware",
        CapabilityStatus.PLANNED,
        "locked",
        "No physical partition-write contract.",
    )
    pack = DevicePack(
        "test.exact",
        "1",
        "Test exact device",
        10,
        ("xiaomi",),
        (),
        (),
        (capability,),
        (),
        "c" * 64,
    )
    registry = DevicePackRegistry((pack,))
    GuardianFlashHandoffService(store).prepare(
        project.project_id,
        report,
        device,
        FlashMode.DIRTY_KEEP_DATA,
    )
    return store, project, registry, report, device


def test_manifest_review_breaks_the_post_handoff_loop_without_inventing_writes(tmp_path):
    store, project, registry, report, device = _prepared(tmp_path)
    service = GuardianManifestReviewService(store, registry)

    manifest = service.compile(project.project_id, report, device)
    loaded = service.load(project.project_id)

    assert loaded == manifest
    assert manifest.review_status == "blocked-missing-exact-write-contract"
    assert not manifest.final_consent_available
    assert manifest.execution_authority == "none"
    assert not manifest.phone_changed
    assert not manifest.bootloader_relock_allowed
    assert manifest.partition_writes == ()
    assert manifest.command_manifest == ()
    assert any(
        check.check_id == "partition-write-contract" and check.state is ManifestReviewState.BLOCKED
        for check in manifest.checks
    )
    assert "no source-bound build or partition-write contract" in manifest.blockers[0]
    assert service.matches_current(manifest, report, device)


def test_declared_write_contract_still_waits_for_current_artifact_receipt_binding(tmp_path):
    store, project, registry, report, device = _prepared(tmp_path)
    pack = registry.packs[0]
    envelope_sha256 = "d" * 64
    source = FirmwareSourceContract("EXACT.BUILD", project.original.sha256, "e" * 64)
    policy = AvbExecutionPolicy(
        AvbPolicyMode.UNLOCKED_UNSIGNED_CHILD,
        AvbPolicyAuthority.FLASH_VALIDATED,
        source.build_id,
        "preserve_exact_source",
        "vbmeta_system",
        "NONE",
        0,
        0,
        0,
        True,
        True,
        True,
        "a",
        "b",
        envelope_sha256,
    )
    writes = DeviceWriteContract(
        "exact-writes",
        1,
        source.build_id,
        envelope_sha256,
        True,
        True,
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
    )
    contract = DeviceBuildContract(
        "exact-build",
        2,
        source,
        4096,
        512,
        2,
        False,
        (DynamicPartitionGroup("group", 4096),),
        (PartitionBuildRule("system", 512, 4096, "group", "opaque", "rebuild", "f" * 64),),
        ("system",),
        "1" * 64,
        "2" * 64,
        ("system.img", "super.img", "vbmeta_system.img"),
        avb_execution_policy=policy,
        partition_write_contract=writes,
    )
    service = GuardianManifestReviewService(
        store,
        DevicePackRegistry((replace(pack, build_contract=contract),)),
    )

    manifest = service.compile(project.project_id, report, device)

    assert manifest.review_status == "blocked-missing-current-artifact-binding"
    states = {check.check_id: check.state for check in manifest.checks}
    assert states["partition-write-contract"] is ManifestReviewState.PASS
    assert states["current-artifact-binding"] is ManifestReviewState.BLOCKED
    assert "artifact-binding receipt" in manifest.blockers[0]
    assert manifest.partition_writes == ()
    assert manifest.command_manifest == ()
    assert not manifest.final_consent_available


def test_manifest_review_ignores_ephemeral_report_identity_but_rejects_changed_facts(tmp_path):
    store, project, registry, report, device = _prepared(tmp_path)
    service = GuardianManifestReviewService(store, registry)
    manifest = service.compile(project.project_id, report, device)
    refreshed = replace(
        report,
        report_id="d" * 32,
        created_at="2026-08-31T01:00:00+00:00",
        report_digest="e" * 64,
    )
    assert service.matches_current(manifest, refreshed, device)

    changed = replace(
        refreshed,
        gates=(replace(refreshed.gates[0], evidence="changed evidence"), *refreshed.gates[1:]),
    )
    assert not service.matches_current(manifest, changed, device)


def test_manifest_review_storage_is_private_bounded_and_strict(tmp_path):
    store, project, registry, report, device = _prepared(tmp_path)
    service = GuardianManifestReviewService(store, registry)
    manifest = service.compile(project.project_id, report, device)
    root = store.projects_root / project.project_id / "guardian"
    latest = root / service.LATEST_NAME
    if os.name != "nt":
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        assert stat.S_IMODE(latest.stat().st_mode) == 0o600

    document = json.loads(latest.read_text(encoding="utf-8"))
    document["unexpected"] = True
    latest.write_text(json.dumps(document), encoding="utf-8")
    assert service.load(project.project_id) is None

    history = root / f"manifest-review-{manifest.manifest_id[:12]}.romverse"
    latest.unlink()
    latest.symlink_to(history)
    assert service.load(project.project_id) is None

    latest.unlink()
    latest.write_bytes(b"{" + b" " * service.MAX_BYTES + b"}")
    assert service.load(project.project_id) is None


def test_resealed_authority_or_source_changes_fail_closed(tmp_path):
    store, project, registry, report, device = _prepared(tmp_path)
    service = GuardianManifestReviewService(store, registry)
    service.compile(project.project_id, report, device)
    latest = store.projects_root / project.project_id / "guardian" / service.LATEST_NAME

    document = json.loads(latest.read_text(encoding="utf-8"))
    document["final_consent_available"] = True
    document["execution_authority"] = "flash"
    _reseal(document)
    latest.write_text(json.dumps(document), encoding="utf-8")
    assert service.load(project.project_id) is None

    service.compile(project.project_id, report, device)
    document = json.loads(latest.read_text(encoding="utf-8"))
    document["source_sha256"] = "f" * 64
    _reseal(document)
    latest.write_text(json.dumps(document), encoding="utf-8")
    assert service.load(project.project_id) is None


def test_schema_one_command_free_review_remains_readable_for_audit(tmp_path):
    store, project, registry, report, device = _prepared(tmp_path)
    service = GuardianManifestReviewService(store, registry)
    service.compile(project.project_id, report, device)
    latest = store.projects_root / project.project_id / "guardian" / service.LATEST_NAME
    document = json.loads(latest.read_text(encoding="utf-8"))
    document["schema_version"] = 1
    document.pop("artifact_binding_digest")
    document["checks"] = [
        item
        for item in document["checks"]
        if item["check_id"] not in {"current-artifact-binding", "execution-manifest"}
    ]
    _reseal(document)
    latest.write_text(json.dumps(document), encoding="utf-8")

    loaded = service.load(project.project_id)

    assert loaded is not None
    assert loaded.schema_version == 1
    assert loaded.artifact_binding_digest == ""
    assert loaded.partition_writes == ()
    assert loaded.command_manifest == ()


def _reseal(document: dict[str, object]) -> None:
    payload = dict(document)
    payload.pop("format", None)
    payload.pop("manifest_digest", None)
    document["manifest_digest"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
