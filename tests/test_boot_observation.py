from __future__ import annotations

import hashlib
import json
import os
import zipfile
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from romverse.core.privacy import WorkspacePrivacy
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.models import (
    CapabilityStatus,
    DeviceBuildContract,
    DevicePack,
    DynamicPartitionGroup,
    FirmwareSourceContract,
    PackCapability,
    PartitionBuildRule,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.guardian.execution_result_receipt import (
    ExecutionTerminalState,
    GatewayResultOutcome,
    GuardianExecutionResultReceipt,
    GuardianGatewayStepResult,
    VerifiedGuardianExecutionResult,
    canonical_execution_result_bytes,
    execution_result_digest,
)
from romverse.rom.boot_observation import (
    BootFailureKind,
    BootObservationService,
    BootObservationStatus,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.ui.rom_studio import RomStudio


def _fixture(tmp_path):
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"payload")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Boot", "test.exact")
    project = store.import_original(project.project_id, source)
    contract = DeviceBuildContract(
        "contract",
        1,
        FirmwareSourceContract("BUILD", project.original.sha256, "b" * 64),
        4096,
        512,
        2,
        False,
        (DynamicPartitionGroup("group", 4096),),
        (PartitionBuildRule("system", 512, 4096, "group", "opaque", "rebuild", "c" * 64),),
        ("system",),
        "d" * 64,
        "e" * 64,
        ("system.img", "vbmeta_system.img", "super.img"),
    )
    pack = DevicePack(
        "test.exact",
        "1",
        "Exact",
        10,
        ("test",),
        ("phone",),
        ("codename",),
        (
            PackCapability(
                "firmware.operations",
                "Build",
                CapabilityStatus.SUPPORTED,
                "model_specific",
                "Exact",
            ),
        ),
        (),
        "a" * 64,
        contract,
    )
    return store, project, DevicePackRegistry((pack,))


def _device(**changes):
    values = {
        "serial": "PRIVATE",
        "state": DeviceState.DEVICE,
        "manufacturer": "test",
        "model": "phone",
        "product": "codename",
        "codename": "codename",
        "build_id": "BUILD",
        "build_fingerprint": "test/codename/build",
        "boot_completed": True,
        "uptime_seconds": 1000,
        "slot_suffix": "_a",
        "battery_percent": 90,
    }
    values.update(changes)
    return AndroidDevice(**values)


def _redigest(data: dict[str, object]) -> dict[str, object]:
    payload = dict(data)
    payload.pop("format", None)
    payload.pop("receipt_digest", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    data["receipt_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    return data


def _verified_flash(store, project, device, completed_at: datetime):
    timestamp = completed_at.isoformat()
    result = GuardianGatewayStepResult(
        order=1,
        operation_id="flash-system",
        gateway_step_digest="e" * 64,
        started_at=(completed_at - timedelta(seconds=30)).isoformat(),
        completed_at=timestamp,
        outcome=GatewayResultOutcome.PASSED,
        returncode=0,
        timed_out=False,
        observed_value="",
        observed_size_bytes=0,
        observed_sha256="",
        evidence_sha256="f" * 64,
        error_code="",
        result_digest="",
    )
    result_payload = asdict(result)
    result_payload.pop("result_digest")
    result = replace(result, result_digest=execution_result_digest(result_payload))
    receipt = GuardianExecutionResultReceipt(
        schema_version=2,
        receipt_id="1" * 32,
        created_at=timestamp,
        started_at=(completed_at - timedelta(seconds=30)).isoformat(),
        completed_at=timestamp,
        gateway_contract_digest="2" * 64,
        project_id=project.project_id,
        plan_digest="3" * 64,
        manifest_digest="4" * 64,
        artifact_binding_digest="5" * 64,
        device_key=WorkspacePrivacy(store.workspace).pseudonym(device.serial),
        device_pack_id=project.device_pack_id,
        device_pack_version="1",
        device_pack_sha256="6" * 64,
        live_target_receipt_digest="7" * 64,
        final_consent_receipt_digest="8" * 64,
        runtime_signer_key_id="runtime",
        runtime_adapter_id="adapter",
        runtime_adapter_version=1,
        runtime_adapter_sha256="9" * 64,
        recorded_prewrite_slot="a",
        forward_result_count=1,
        forward_results_digest=execution_result_digest({"forward_results": [asdict(result)]}),
        forward_results=(result,),
        recovery_invoked=False,
        recovery_consent_receipt_digest="",
        wipe_consent_receipt_digest="",
        recovery_result_count=0,
        recovery_results_digest="b" * 64,
        recovery_results=(),
        terminal_state=ExecutionTerminalState.SUCCEEDED,
        phone_change_attempted=True,
        phone_change_verified=True,
        phone_state_uncertain=False,
        postconditions_verified=True,
        receipt_digest="c" * 64,
    )
    receipt_payload = asdict(receipt)
    receipt_payload.pop("receipt_digest")
    receipt = replace(receipt, receipt_digest=execution_result_digest(receipt_payload))
    signed_digest = hashlib.sha256(canonical_execution_result_bytes(asdict(receipt))).hexdigest()
    return VerifiedGuardianExecutionResult(receipt, "runtime", signed_digest)


def test_boot_observation_requires_time_based_stability_and_never_claims_flash(tmp_path):
    store, project, registry = _fixture(tmp_path)
    service = BootObservationService(store, registry)
    started = datetime(2026, 8, 29, tzinfo=UTC)

    first = service.observe(project.project_id, _device(), started)
    stable = service.observe(
        project.project_id,
        _device(uptime_seconds=1310),
        started + timedelta(seconds=310),
    )

    assert first.status is BootObservationStatus.WAITING
    assert stable.status is BootObservationStatus.STABLE
    assert stable.stable
    assert not stable.flash_linked
    assert not stable.verified_first_boot
    assert not stable.phone_changed
    assert stable.failure_kind is BootFailureKind.NONE
    assert not stable.knowledge_queries
    assert not service.needs_knowledge_lookup(stable)
    assert service.load(project.project_id) == stable
    assert service.next_sample_wait_seconds(first, started + timedelta(seconds=30)) == 30
    assert service.next_sample_wait_seconds(first, started + timedelta(seconds=70)) == 0
    assert "five-minute" in service.next_step(first)
    assert "Guardian write receipt" in service.next_step(stable)


def test_verified_guardian_flash_starts_and_maintains_a_first_boot_session(tmp_path):
    store, project, registry = _fixture(tmp_path)
    service = BootObservationService(store, registry)
    device = _device()
    started = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    service.observe(project.project_id, device, started - timedelta(minutes=10))
    verified = _verified_flash(store, project, device, started)

    first_boot = service.observe(
        project.project_id,
        _device(uptime_seconds=20),
        started + timedelta(seconds=5),
        verified_flash=verified,
    )
    stable = service.observe(
        project.project_id,
        _device(uptime_seconds=330),
        started + timedelta(seconds=315),
    )

    assert len(first_boot.samples) == 1
    assert first_boot.flash_linked
    assert first_boot.guardian_execution_receipt_digest == verified.signed_receipt_sha256
    assert not first_boot.verified_first_boot
    assert stable.status is BootObservationStatus.STABLE
    assert stable.flash_linked
    assert stable.verified_first_boot
    assert stable.guardian_execution_receipt_digest == verified.signed_receipt_sha256
    assert "Verified first boot" in service.next_step(stable)
    assert service.load(project.project_id) == stable
    fresh = BootObservationService(store, registry)
    assert fresh.load(project.project_id) is None
    assert fresh.load(project.project_id, verified_flash=verified, device=device) == stable


def test_boot_observation_rejects_a_mismatched_or_unsuccessful_guardian_result(tmp_path):
    store, project, registry = _fixture(tmp_path)
    service = BootObservationService(store, registry)
    device = _device()
    started = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    verified = _verified_flash(store, project, device, started)

    with pytest.raises(ProjectError, match="exact project and device"):
        service.observe(
            project.project_id,
            device,
            started + timedelta(seconds=5),
            verified_flash=VerifiedGuardianExecutionResult(
                replace(verified.receipt, device_key="0" * 20),
                verified.signer_key_id,
                verified.signed_receipt_sha256,
            ),
        )

    with pytest.raises(ProjectError, match="exact project and device"):
        service.observe(
            project.project_id,
            device,
            started + timedelta(seconds=5),
            verified_flash=VerifiedGuardianExecutionResult(
                replace(
                    verified.receipt,
                    terminal_state=ExecutionTerminalState.FAILED,
                    phone_change_verified=False,
                    postconditions_verified=False,
                ),
                verified.signer_key_id,
                verified.signed_receipt_sha256,
            ),
        )


def test_rom_studio_advances_flash_and_first_boot_only_from_linked_evidence(tmp_path):
    QApplication.instance() or QApplication([])
    store, project, registry = _fixture(tmp_path)
    device = _device()
    completed = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    verified = _verified_flash(store, project, device, completed)
    studio = RomStudio(store, registry)
    studio.refresh(project.project_id)
    studio.set_devices([device])
    timeline_events = []
    studio.guardian_flash_verified.connect(lambda *values: timeline_events.append(values))

    assert studio.register_guardian_execution_result(verified)
    assert timeline_events == [(device.serial, project.name, verified)]
    assert studio.guided_context().flash_complete
    assert not studio.guided_context().first_boot_verified

    service = BootObservationService(store, registry)
    service.observe(
        project.project_id,
        _device(uptime_seconds=20),
        completed + timedelta(seconds=5),
        verified_flash=verified,
    )
    service.observe(
        project.project_id,
        _device(uptime_seconds=330),
        completed + timedelta(seconds=315),
    )
    linked = studio.guided_context()

    assert linked.flash_complete
    assert linked.boot_observation_stable
    assert linked.first_boot_verified
    studio._latest_guardian_execution_result = None
    untrusted_after_restart = studio.guided_context()
    assert not untrusted_after_restart.flash_complete
    assert not untrusted_after_restart.boot_observation_stable
    assert not untrusted_after_restart.first_boot_verified
    studio.close()


def test_boot_observation_rejects_a_locally_forged_flash_link(tmp_path):
    store, project, registry = _fixture(tmp_path)
    service = BootObservationService(store, registry)
    started = datetime(2026, 8, 29, tzinfo=UTC)
    service.observe(project.project_id, _device(), started)
    service.observe(
        project.project_id,
        _device(uptime_seconds=1310),
        started + timedelta(seconds=310),
    )
    path = store.projects_root / project.project_id / service.NAME
    forged = json.loads(path.read_text(encoding="utf-8"))
    forged["flash_linked"] = True
    forged["guardian_execution_receipt_digest"] = "f" * 64
    forged["verified_first_boot"] = True
    path.write_text(json.dumps(_redigest(forged)), encoding="utf-8")

    assert BootObservationService(store, registry).load(project.project_id) is None
    with pytest.raises(ProjectError, match="will not be overwritten"):
        BootObservationService(store, registry).observe(
            project.project_id,
            _device(uptime_seconds=1400),
            started + timedelta(seconds=400),
        )


def test_boot_observation_detects_uptime_reset_and_build_change(tmp_path):
    store, project, registry = _fixture(tmp_path)
    service = BootObservationService(store, registry)
    started = datetime(2026, 8, 29, tzinfo=UTC)
    service.observe(project.project_id, _device(uptime_seconds=1000), started)

    rebooted = service.observe(
        project.project_id,
        _device(uptime_seconds=20),
        started + timedelta(seconds=70),
    )

    assert rebooted.status is BootObservationStatus.ATTENTION
    assert rebooted.reboot_detected
    assert rebooted.failure_kind is BootFailureKind.REBOOT_LOOP
    assert "boot loop" in rebooted.knowledge_queries[0]
    assert "BUILD" in " ".join(rebooted.knowledge_queries)
    assert service.needs_knowledge_lookup(rebooted)
    failure = service.knowledge_failure(rebooted)
    assert failure is not None
    assert failure.phase == "boot"
    assert "boot.incomplete" in failure.finding_ids
    assert "boot.reboot_loop" in failure.finding_ids
    assert failure.operation == "read-only boot observation"
    assert failure.verified_inputs == (
        f"pack:{rebooted.pack_id}",
        f"source:{rebooted.source_original_sha256}",
    )
    assert "uptime reset" in rebooted.diagnosis
    assert "Stop and review" in service.next_step(rebooted)

    path = store.projects_root / project.project_id / service.NAME
    data = json.loads(path.read_text())
    data["samples"][-1]["build_fingerprint"] = "changed"
    path.write_text(json.dumps(data))
    assert service.load(project.project_id) is None


def test_boot_observation_rejects_another_device_or_pack(tmp_path):
    store, project, registry = _fixture(tmp_path)
    service = BootObservationService(store, registry)
    service.observe(project.project_id, _device())

    with pytest.raises(ProjectError, match="another device"):
        service.observe(
            project.project_id,
            _device(serial="OTHER"),
            datetime.now(UTC) + timedelta(seconds=70),
        )
    wrong = replace(_device(), model="different")
    with pytest.raises(ProjectError, match="does not match"):
        service.observe(project.project_id, wrong)


def test_boot_observation_classifies_timeout_probe_failure_and_non_android_mode(tmp_path):
    store, project, registry = _fixture(tmp_path)
    service = BootObservationService(store, registry)
    started = datetime(2026, 8, 29, tzinfo=UTC)

    timeout = service.observe(
        project.project_id,
        _device(boot_completed=False, uptime_seconds=1_201),
        started,
    )
    assert timeout.failure_kind is BootFailureKind.BOOT_TIMEOUT
    assert service.needs_knowledge_lookup(timeout)

    path = store.projects_root / project.project_id / service.NAME
    path.unlink()
    incomplete = service.observe(
        project.project_id,
        _device(boot_completed=None, uptime_seconds=None, errors=("getprop timed out",)),
        started,
    )
    assert incomplete.failure_kind is BootFailureKind.PROBE_INCOMPLETE
    assert "probe" in " ".join(incomplete.knowledge_queries).casefold()

    path.unlink()
    fastboot = service.observe(
        project.project_id,
        _device(state=DeviceState.FASTBOOT, boot_completed=None),
        started,
    )
    assert fastboot.failure_kind is BootFailureKind.DEVICE_MODE
    assert "fastboot" in fastboot.knowledge_queries[0]


def test_boot_observation_store_is_strict_bounded_and_rejects_links(tmp_path):
    store, project, registry = _fixture(tmp_path)
    service = BootObservationService(store, registry)
    receipt = service.observe(project.project_id, _device())
    path = store.projects_root / project.project_id / service.NAME
    original = path.read_bytes()

    data = json.loads(original)
    data["samples"][0]["uptime_seconds"] = True
    path.write_text(json.dumps(_redigest(data)), encoding="utf-8")
    assert service.load(project.project_id) is None

    path.write_bytes(original)
    data = json.loads(original)
    data["execution_authority"] = "flash"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert service.load(project.project_id) is None

    outside = tmp_path / "outside.romverse"
    outside.write_bytes(original)
    path.unlink()
    path.symlink_to(outside)
    assert service.load(project.project_id) is None

    path.unlink()
    path.write_bytes(b"{" + b" " * service.MAX_BYTES + b"}")
    assert service.load(project.project_id) is None
    assert receipt.schema_version == service.SCHEMA_VERSION


def test_schema_one_boot_observation_migrates_in_memory_with_lookup_terms(tmp_path):
    store, project, registry = _fixture(tmp_path)
    service = BootObservationService(store, registry)
    started = datetime(2026, 8, 29, tzinfo=UTC)
    service.observe(project.project_id, _device(uptime_seconds=1_000), started)
    receipt = service.observe(
        project.project_id,
        _device(uptime_seconds=10),
        started + timedelta(seconds=70),
    )
    path = store.projects_root / project.project_id / service.NAME
    legacy = json.loads(path.read_text(encoding="utf-8"))
    legacy["schema_version"] = 1
    legacy.pop("failure_kind")
    legacy.pop("knowledge_queries")
    legacy.pop("guardian_execution_receipt_digest")
    path.write_text(json.dumps(_redigest(legacy)), encoding="utf-8")

    migrated = service.load(project.project_id)

    assert migrated is not None
    assert migrated.schema_version == 3
    assert migrated.failure_kind is BootFailureKind.REBOOT_LOOP
    assert migrated.knowledge_queries == receipt.knowledge_queries


def test_rom_studio_automatically_ranks_offline_archive_for_boot_attention(tmp_path):
    QApplication.instance() or QApplication([])
    store, project, registry = _fixture(tmp_path)
    service = BootObservationService(store, registry)
    started = datetime(2026, 8, 29, tzinfo=UTC)
    service.observe(project.project_id, _device(uptime_seconds=1_000), started)
    receipt = service.observe(
        project.project_id,
        _device(uptime_seconds=10),
        started + timedelta(seconds=70),
    )
    studio = RomStudio(store, registry)
    reports = []
    studio.offline_knowledge_updated.connect(reports.append)

    report = studio.scan_boot_observation_knowledge(receipt)

    assert report is not None
    assert report.trigger == "boot-failure"
    assert report.execution_authority == "none"
    assert report.matches
    assert "boot.incomplete" in report.matches[0].matched_evidence[0]
    assert reports == [report]
    assert (store.workspace / "knowledge" / "archive.romverse").is_file()
    studio.close()
