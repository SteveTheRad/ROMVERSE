from __future__ import annotations

import json
import stat
from datetime import UTC, datetime

import pytest

from romverse.core.privacy import WorkspacePrivacy
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.models import (
    AvbExecutionPolicy,
    AvbPolicyAuthority,
    AvbPolicyMode,
    CapabilityStatus,
    DeviceBuildContract,
    DeviceMode,
    DeviceModeTransitionRule,
    DevicePack,
    DevicePostWriteVerificationContract,
    DeviceRecoveryActionRule,
    DeviceRecoveryContract,
    DeviceRecoveryOperation,
    DeviceRecoveryStrategy,
    DeviceTransitionOperation,
    DeviceTransitionRecoveryContract,
    DeviceWriteContract,
    DeviceWriteTransport,
    DynamicPartitionGroup,
    FirmwareSourceContract,
    PackCapability,
    PartitionBuildRule,
    PartitionReadbackRule,
    PartitionVerificationMethod,
    PartitionWriteRule,
    PostBootPropertyRule,
)
from romverse.device_packs.registry import DevicePackRegistry
from romverse.knowledge.models import (
    DeviceKnowledgeScope,
    KnowledgeConfidence,
    KnowledgeKind,
    KnowledgeLookupReport,
    KnowledgeMatch,
    KnowledgeRecord,
    KnowledgeSource,
    KnowledgeSourceTier,
    MatchConfidence,
)
from romverse.repair.autopilot import (
    RecoveryAutopilotContext,
    RecoveryAutopilotError,
    RecoveryAutopilotService,
    RecoveryIncidentState,
    RecoveryRouteKind,
    RecoveryTrigger,
)
from romverse.rom.boot_observation import (
    BootFailureKind,
    BootObservationReceipt,
    BootObservationStatus,
    BootSample,
)
from romverse.rom.recovery_evidence import RecoveryEvidenceAssessment


def _device(state: DeviceState = DeviceState.DEVICE, **changes) -> AndroidDevice:
    values = {
        "serial": "PRIVATE-RECOVERY-SERIAL",
        "state": state,
        "manufacturer": "Test",
        "model": "Recovery Phone",
        "product": "recovery",
        "codename": "recovery",
        "build_id": "TEST.FLASH",
        "build_fingerprint": "test/recovery/recovery:17/TEST.FLASH/release:user/release-keys",
        "build_incremental": "TEST.FLASH",
        "boot_completed": state is DeviceState.DEVICE,
        "slot_suffix": "_a",
        "ab_update": True,
        "bootloader_locked": False,
        "verified_boot": "orange",
    }
    values.update(changes)
    return AndroidDevice(**values)


def _registry() -> DevicePackRegistry:
    attestation = "6" * 64
    source_sha256 = "a" * 64
    source = FirmwareSourceContract("TEST.FLASH", source_sha256, "b" * 64)
    writes = (
        PartitionWriteRule(
            "super",
            "super.img",
            DeviceWriteTransport.FASTBOOTD,
            "a",
            True,
        ),
    )
    verification = DevicePostWriteVerificationContract(
        "test-post-write",
        1,
        "TEST.FLASH",
        attestation,
        (
            PartitionReadbackRule(
                "super",
                DeviceWriteTransport.FASTBOOTD,
                "a",
                PartitionVerificationMethod.FASTBOOT_FETCH_SHA256,
                4096,
                "7" * 64,
            ),
        ),
        (
            PostBootPropertyRule("sys.boot_completed", "1"),
            PostBootPropertyRule("ro.product.device", "recovery"),
            PostBootPropertyRule("ro.build.fingerprint", "test/recovery/build"),
            PostBootPropertyRule("ro.build.version.incremental", "TEST.FLASH"),
            PostBootPropertyRule("ro.build.version.sdk", "37"),
            PostBootPropertyRule("ro.build.version.security_patch", "2026-08-01"),
            PostBootPropertyRule("ro.boot.verifiedbootstate", "orange"),
        ),
        True,
        300,
    )
    recovery = DeviceRecoveryContract(
        DeviceRecoveryStrategy.RECORDED_SLOT_THEN_STOCK_PACKAGE,
        "test.fastboot.stock",
        source_sha256,
        DeviceMode.BOOTLOADER,
        (
            DeviceRecoveryActionRule(
                1,
                DeviceRecoveryOperation.ACTIVATE_RECORDED_SLOT,
                "test.fastboot.stock.slot.restore",
                DeviceMode.BOOTLOADER,
                DeviceMode.BOOTLOADER,
                "recorded_prewrite",
                30,
                False,
            ),
            DeviceRecoveryActionRule(
                2,
                DeviceRecoveryOperation.RESTORE_STOCK_PACKAGE,
                "test.fastboot.stock.package.restore",
                DeviceMode.BOOTLOADER,
                DeviceMode.BOOTLOADER,
                "none",
                1800,
                True,
            ),
            DeviceRecoveryActionRule(
                3,
                DeviceRecoveryOperation.REBOOT_SYSTEM,
                "test.fastboot.stock.reboot",
                DeviceMode.BOOTLOADER,
                DeviceMode.ANDROID,
                "none",
                300,
                False,
            ),
            DeviceRecoveryActionRule(
                4,
                DeviceRecoveryOperation.VERIFY_POST_BOOT,
                "test.fastboot.stock.verify",
                DeviceMode.ANDROID,
                DeviceMode.ANDROID,
                "none",
                300,
                False,
            ),
        ),
        True,
        True,
        True,
        True,
        False,
        False,
    )
    transition = DeviceTransitionRecoveryContract(
        "test-transition-recovery",
        1,
        "TEST.FLASH",
        attestation,
        DeviceMode.BOOTLOADER,
        (
            DeviceModeTransitionRule(
                1,
                0,
                DeviceTransitionOperation.REBOOT_FASTBOOTD,
                DeviceMode.BOOTLOADER,
                DeviceMode.FASTBOOTD,
                "none",
                60,
            ),
            DeviceModeTransitionRule(
                2,
                1,
                DeviceTransitionOperation.SET_ACTIVE_SLOT,
                DeviceMode.FASTBOOTD,
                DeviceMode.FASTBOOTD,
                "a",
                30,
            ),
            DeviceModeTransitionRule(
                3,
                1,
                DeviceTransitionOperation.REBOOT_SYSTEM,
                DeviceMode.FASTBOOTD,
                DeviceMode.ANDROID,
                "none",
                300,
            ),
        ),
        DeviceMode.ANDROID,
        recovery,
        True,
        "none",
        False,
    )
    build = DeviceBuildContract(
        "test-build",
        3,
        source,
        8192,
        512,
        2,
        True,
        (
            DynamicPartitionGroup("test_dynamic_partitions_a", 4096),
            DynamicPartitionGroup("test_dynamic_partitions_b", 4096),
        ),
        (
            PartitionBuildRule(
                "super",
                4096,
                4096,
                "test_dynamic_partitions_a",
                "opaque",
                "rebuild",
                "7" * 64,
            ),
        ),
        ("super",),
        "8" * 64,
        "9" * 64,
        ("super.img",),
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
            attestation,
        ),
        partition_write_contract=DeviceWriteContract(
            "test-writes",
            3,
            "TEST.FLASH",
            attestation,
            True,
            False,
            True,
            True,
            writes,
            post_write_verification_contract=verification,
            transition_recovery_contract=transition,
        ),
    )
    return DevicePackRegistry(
        (
            DevicePack(
                "test.recovery",
                "1.0.0",
                "Test Recovery Phone",
                100,
                ("test",),
                ("recovery phone",),
                ("recovery",),
                (
                    PackCapability(
                        "recovery.contract",
                        "Recovery",
                        CapabilityStatus.SUPPORTED,
                        "model_specific",
                        "Exact test recovery contract",
                    ),
                ),
                (),
                "f" * 64,
                build,
            ),
        )
    )


def _verified_boot(workspace, source: AndroidDevice) -> BootObservationReceipt:
    device_key = WorkspacePrivacy(workspace).pseudonym(source.serial)
    sample = BootSample(
        datetime.now(UTC).isoformat(),
        device_key,
        DeviceState.DEVICE.value,
        True,
        600,
        source.slot_suffix,
        source.build_id,
        source.build_fingerprint,
        90,
        (),
    )
    return BootObservationReceipt(
        3,
        "project-one",
        "test.recovery",
        "test-build",
        "a" * 64,
        (sample,),
        BootObservationStatus.STABLE,
        True,
        False,
        True,
        "b" * 64,
        True,
        "Stable verified first boot",
        False,
        BootFailureKind.NONE,
        (),
        "c" * 64,
    )


def _cache_report(confidence: MatchConfidence) -> KnowledgeLookupReport:
    source = KnowledgeSource(
        "source.test.cache",
        "Test manufacturer recovery guide",
        "Test",
        "https://example.invalid/recovery",
        KnowledgeSourceTier.OFFICIAL_VENDOR,
        "Test Recovery Phone cache recovery",
        "2026-09-01",
    )
    record = KnowledgeRecord(
        "test.recovery.cache",
        1,
        "Exact recovery cache guidance",
        KnowledgeKind.RECOVERY,
        "Confirm the model-specific recovery cache target before any change.",
        ("Boot stalls after an update",),
        (),
        (),
        ("Confirm that the recovery UI reports a cache target",),
        ("Clear only the documented cache target",),
        ("Exact Test Recovery Phone identity",),
        ("A fresh boot observation completes",),
        ("Test Recovery Phone",),
        ("Do not use on an unidentified device",),
        ("Use the vendor recovery cache menu",),
        ("cache recovery",),
        DeviceKnowledgeScope(
            manufacturers=("test",),
            models=("recovery phone",),
            codenames=("recovery",),
            scope_note="Exact Test Recovery Phone recovery UI",
        ),
        (source.source_id,),
        KnowledgeConfidence.HIGH,
        2,
        (),
    )
    match = KnowledgeMatch(
        record,
        90,
        confidence,
        ("model: recovery phone", "codename: recovery"),
        (),
        (source,),
        "Guidance only; execution authority remains none.",
    )
    return KnowledgeLookupReport(
        "boot-failure",
        "d" * 64,
        "e" * 64,
        (match,),
        "none",
        ("Device-changing guidance requires fresh confirmation.",),
    )
def test_disconnected_incident_is_private_tamper_evident_and_not_repaired(tmp_path) -> None:
    service = RecoveryAutopilotService(tmp_path, _registry())

    incident = service.start(
        RecoveryAutopilotContext(
            RecoveryTrigger.FLASH_FAILURE,
            project_id="project-one",
            message="Phone disappeared after the write attempt",
        )
    )

    assert incident.state is RecoveryIncidentState.EMERGENCY
    assert incident.mode == "disconnected"
    assert not incident.repaired
    assert incident.routes[0].kind is RecoveryRouteKind.PHYSICAL_CHECK
    assert any(route.kind is RecoveryRouteKind.RECONNECT_USB for route in incident.routes)
    path = service.root / f"{incident.incident_id}{service.SUFFIX}"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert "PRIVATE-RECOVERY-SERIAL" not in path.read_text()

    payload = json.loads(path.read_text())
    payload["incident"]["repaired"] = True
    path.write_text(json.dumps(payload))
    with pytest.raises(RecoveryAutopilotError, match="outcome|integrity"):
        service.load(incident.incident_id)


def test_ranked_exact_routes_keep_wipe_last_and_never_grant_phone_authority(tmp_path) -> None:
    service = RecoveryAutopilotService(tmp_path, _registry())
    incident = service.start(
        RecoveryAutopilotContext(
            RecoveryTrigger.BOOTLOOP,
            device=_device(DeviceState.FASTBOOT, boot_completed=False),
            project_id="project-one",
            recovery_evidence=RecoveryEvidenceAssessment(
                True,
                True,
                True,
                ("external backup verified", "stock recovery verified"),
            ),
        )
    )

    kinds = [route.kind for route in incident.routes]
    assert RecoveryRouteKind.SLOT_REVIEW in kinds
    assert RecoveryRouteKind.IMAGE_RESTORE_REVIEW in kinds
    assert RecoveryRouteKind.EXACT_STOCK_RESTORE in kinds
    assert kinds[-1] is RecoveryRouteKind.DATA_RESET_GUIDANCE
    assert all(
        route.confirmation_required and route.execution_authority == "none"
        for route in incident.routes
        if route.changes_device
    )
    stock = next(
        route for route in incident.routes if route.kind is RecoveryRouteKind.EXACT_STOCK_RESTORE
    )
    assert stock.owner_route == "guardian_core"
    assert "verified" in " ".join(stock.requirements).casefold()


def test_cache_guidance_requires_scoped_medium_or_better_archive_evidence(tmp_path) -> None:
    service = RecoveryAutopilotService(tmp_path, _registry())
    trusted = service.start(
        RecoveryAutopilotContext(
            RecoveryTrigger.BOOTLOOP,
            device=_device(DeviceState.RECOVERY, boot_completed=False),
            project_id="cache-evidence",
            knowledge_report=_cache_report(MatchConfidence.HIGH),
        )
    )

    cache = next(
        route for route in trusted.routes if route.kind is RecoveryRouteKind.CACHE_GUIDANCE
    )
    assert cache.knowledge_record_ids == ("test.recovery.cache",)
    assert cache.changes_device
    assert cache.confirmation_required
    assert cache.execution_authority == "none"
    assert "does not assume" in cache.summary

    low_confidence = service.start(
        RecoveryAutopilotContext(
            RecoveryTrigger.BOOTLOOP,
            device=_device(DeviceState.RECOVERY, boot_completed=False),
            project_id="low-cache-evidence",
            knowledge_report=_cache_report(MatchConfidence.LOW),
        )
    )
    assert all(
        route.kind is not RecoveryRouteKind.CACHE_GUIDANCE
        for route in low_confidence.routes
    )


def test_post_flash_incident_needs_verified_boot_and_same_device_reconnect(tmp_path) -> None:
    service = RecoveryAutopilotService(tmp_path, _registry())
    opened = service.start(
        RecoveryAutopilotContext(
            RecoveryTrigger.BOOT_ATTENTION,
            project_id="project-one",
            message="Boot observation detected repeated restart evidence",
        )
    )
    phone = _device()

    visible_only = service.refresh(
        opened.incident_id,
        RecoveryAutopilotContext(
            RecoveryTrigger.BOOT_ATTENTION,
            device=phone,
            project_id="project-one",
        ),
    )
    assert not visible_only.repaired
    assert visible_only.state is RecoveryIncidentState.STABILIZING

    recovered = service.refresh(
        opened.incident_id,
        RecoveryAutopilotContext(
            RecoveryTrigger.BOOT_ATTENTION,
            device=phone,
            project_id="project-one",
            boot_observation=_verified_boot(tmp_path, phone),
        ),
    )
    assert recovered.repaired
    assert recovered.verified_reboot
    assert recovered.state is RecoveryIncidentState.RECOVERED
    assert recovered.routes == ()
    assert recovered.events[-1].title == "Recovery verified by fresh boot evidence"


def test_host_only_repair_result_still_requires_a_fresh_reconnect_scan(tmp_path) -> None:
    service = RecoveryAutopilotService(tmp_path, _registry())
    opened = service.start(
        RecoveryAutopilotContext(
            RecoveryTrigger.DEVICE_MODE,
            device=_device(DeviceState.OFFLINE, boot_completed=None),
            host_repair_available=True,
        )
    )
    host_route = next(
        route for route in opened.routes if route.kind is RecoveryRouteKind.HOST_ADB_REPAIR
    )
    result = service.record_route_result(
        opened.incident_id,
        host_route.route_id,
        "succeeded",
        "Verified host-only receipt saved; phone outcome not yet known.",
    )
    assert result.state is RecoveryIncidentState.VERIFYING
    assert not result.repaired

    reconnected = service.refresh(
        opened.incident_id,
        RecoveryAutopilotContext(
            RecoveryTrigger.DEVICE_MODE,
            device=_device(DeviceState.DEVICE, boot_completed=True),
        ),
    )
    assert reconnected.repaired
    assert reconnected.verified_reboot
    assert reconnected.events[-1].state is RecoveryIncidentState.RECOVERED


def test_known_incident_rejects_a_different_phone_during_refresh(tmp_path) -> None:
    service = RecoveryAutopilotService(tmp_path, _registry())
    opened = service.start(
        RecoveryAutopilotContext(
            RecoveryTrigger.DEVICE_MODE,
            device=_device(DeviceState.OFFLINE, boot_completed=None),
        )
    )

    with pytest.raises(RecoveryAutopilotError, match="does not match"):
        service.refresh(
            opened.incident_id,
            RecoveryAutopilotContext(
                RecoveryTrigger.DEVICE_MODE,
                device=_device(serial="ANOTHER-PHONE"),
            ),
        )

    preserved = service.load(opened.incident_id)
    assert preserved.device_key == opened.device_key
    assert not preserved.repaired
