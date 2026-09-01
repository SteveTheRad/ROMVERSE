from __future__ import annotations

import hashlib
import json
import stat
import struct
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from romverse.ascension.build_handoff import RootRomBuildHandoffService
from romverse.ascension.consent import AscensionConsentReviewService
from romverse.ascension.evidence import AscensionEvidenceService
from romverse.ascension.final_handoff import AscensionFinalHandoffService
from romverse.ascension.integration import RootRomIntegrationService
from romverse.ascension.manifest import (
    AscensionGuardianManifest,
    AscensionGuardianManifestService,
    AscensionManifestCheck,
    ManifestState,
)
from romverse.ascension.models import AscensionMethod, OfficialRootAsset, OfficialRootRelease
from romverse.ascension.planning import AscensionRootPlanService
from romverse.ascension.preparation import RootPatchPreparationService
from romverse.backup.handoff import BackupHandoffService, CloudBackupProvider
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.registry import DevicePackRegistry
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.recovery_evidence import RecoveryEvidenceService
from tests._ascension_trust import ExplicitTestRootReleaseService


def _boot_v4(ramdisk: bytes, kernel: bytes = b"") -> bytes:
    header = bytearray(1584)
    header[:8] = b"ANDROID!"
    struct.pack_into("<I", header, 8, len(kernel))
    struct.pack_into("<I", header, 12, len(ramdisk))
    struct.pack_into("<I", header, 20, len(header))
    struct.pack_into("<I", header, 40, 4)
    image = bytes(header).ljust(4096, b"\0") + kernel
    image = image.ljust((len(image) + 4095) // 4096 * 4096, b"\0")
    return image + ramdisk


class _ManifestProvider:
    def __init__(self, store: RomProjectStore, manifest: AscensionGuardianManifest) -> None:
        self.store = store
        self.manifest = manifest

    def load(self, project_id: str, method: AscensionMethod):
        if project_id == self.manifest.project_id and method is self.manifest.method:
            return self.manifest
        return None

    def matches_device(self, manifest, device) -> bool:
        plan = AscensionRootPlanService(self.store).load(manifest.project_id, manifest.method)
        return bool(plan and AscensionRootPlanService(self.store).matches_device(plan, device))


def _prepared(tmp_path: Path, *, cloud_backup: bool = False):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Final Ascension")
    source = tmp_path / "popsicle_images_OS3.0.318.0.WPBCNXM_test.tgz"
    source.write_bytes(b"protected exact firmware")
    project = store.import_original(project.project_id, source)

    images = store.working_root / project.project_id / "tree" / "images"
    images.mkdir(parents=True)
    (images / "init_boot.img").write_bytes(_boot_v4(b"pristine ramdisk"))
    (images / "recovery.img").write_bytes(b"stock recovery")
    AscensionEvidenceService(store).ensure(project.project_id, "images/init_boot.img")

    manager = store.workspace / "tools" / "test" / "Magisk.apk"
    manager.parent.mkdir(parents=True)
    manager.write_bytes(b"verified manager")
    manager_sha = hashlib.sha256(manager.read_bytes()).hexdigest()
    asset = OfficialRootAsset(
        AscensionMethod.MAGISK,
        "topjohnwu/Magisk",
        "v30.7",
        "2026-02-23T00:00:00Z",
        manager.name,
        manager.stat().st_size,
        manager_sha,
        "https://github.com/topjohnwu/Magisk/releases/download/v30.7/Magisk.apk",
    )
    release = OfficialRootRelease(
        AscensionMethod.MAGISK,
        asset.repository,
        asset.tag,
        asset.published_at,
        asset,
        "https://github.com/topjohnwu/Magisk/releases/tag/v30.7",
    )
    preparation = RootPatchPreparationService(
        store,
        ExplicitTestRootReleaseService(release, manager),
    )
    preparation.prepare(project.project_id, AscensionMethod.MAGISK, release, manager)
    patched = tmp_path / "magisk_patched.img"
    patched.write_bytes(_boot_v4(b"manager patched ramdisk"))
    preparation.import_patched(project.project_id, AscensionMethod.MAGISK, patched)
    RootRomIntegrationService(store).integrate(project.project_id, AscensionMethod.MAGISK)
    RootRomBuildHandoffService(store).seal(project.project_id, AscensionMethod.MAGISK)

    device = AndroidDevice(
        "exact-serial",
        DeviceState.DEVICE,
        transport="usb",
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        marketing_name="Xiaomi 17 Pro Max",
        product="popsicle",
        codename="popsicle",
        battery_percent=82,
        bootloader_locked=False,
        slot_suffix="_a",
    )
    if cloud_backup:
        BackupHandoffService(store).confirm_cloud(
            project.project_id,
            device,
            CloudBackupProvider.GOOGLE,
            "Completed today at 15:42",
            backup_completed=True,
            restore_access_confirmed=True,
            critical_data_scope_reviewed=True,
            limitations_acknowledged=True,
        )
    else:
        backup = tmp_path / "phone-backup.zip"
        backup.write_bytes(b"independently readable backup")
        RecoveryEvidenceService(store).register(project.project_id, "external_backup", backup)
    plan = AscensionRootPlanService(store).create(
        project.project_id,
        AscensionMethod.MAGISK,
        device,
    )
    required = AscensionFinalHandoffService.REQUIRED_PASS_CHECKS
    checks = tuple(
        AscensionManifestCheck(
            check_id,
            check_id,
            ManifestState.PASS,
            "verified",
            "recheck if changed",
            "none",
            "",
        )
        for check_id in sorted(required)
    ) + (
        AscensionManifestCheck(
            "final-consent",
            "Final human confirmation",
            ManifestState.ATTENTION,
            "No write is authorized.",
            "Review the exact consequences.",
            "none",
            "",
        ),
    )
    prohibited = (
        "Bootloader relock",
        "Bootloader unlock",
        "User-data wipe",
        "EDL or OEM service-mode write",
        "Write to any partition or slot not named by this manifest",
        "Use an image whose SHA-256 differs from this manifest",
    )
    manifest = AscensionGuardianManifest(
        2,
        "manifest-id",
        "2026-08-29T00:00:00+00:00",
        project.project_id,
        plan.plan_id,
        plan.plan_digest,
        AscensionMethod.MAGISK,
        project.original.sha256,
        "xiaomi.popsicle.flash-validated",
        "1.0.0",
        "3" * 64,
        plan.device_key,
        plan.device_name,
        plan.device_codename,
        plan.target_partition,
        "a",
        "usb-fastboot-final-handoff",
        plan.pristine_image_sha256,
        plan.patched_image_sha256,
        plan.stock_recovery_sha256,
        checks,
        ("Re-identify the exact phone without changing it.",),
        prohibited,
        True,
        "none",
        (),
        False,
        False,
        "4" * 64,
    )
    provider = _ManifestProvider(store, manifest)
    return store, project.project_id, device, provider


def _redigest(payload: dict[str, object], digest_key: str) -> None:
    unsigned = {key: value for key, value in payload.items() if key not in {"format", digest_key}}
    payload[digest_key] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_final_handoff_binds_every_exact_artifact_but_grants_no_execution(tmp_path: Path):
    store, project_id, device, provider = _prepared(tmp_path)
    service = AscensionFinalHandoffService(store, provider)

    handoff = service.prepare(project_id, AscensionMethod.MAGISK, device)

    assert service.load(project_id, AscensionMethod.MAGISK, device) == handoff
    assert handoff.device_name == "Xiaomi 17 Pro Max"
    assert handoff.target_partition == "init_boot"
    assert handoff.target_slot == handoff.observed_slot == "a"
    assert handoff.observed_transport == "usb"
    assert handoff.battery_percent == 82
    assert handoff.bootloader_unlocked_observed
    assert handoff.external_backup_verified
    assert handoff.execution_authority == "none"
    assert handoff.command_manifest == ()
    assert not handoff.bootloader_unlock_allowed
    assert not handoff.bootloader_relock_allowed
    assert not handoff.user_data_wipe_allowed
    assert not handoff.phone_changed
    assert "Bootloader relock" in handoff.prohibited_actions


def test_final_handoff_accepts_exact_cloud_confirmation_without_false_file_claim(
    tmp_path: Path,
):
    store, project_id, device, provider = _prepared(tmp_path, cloud_backup=True)
    service = AscensionFinalHandoffService(store, provider)

    handoff = service.prepare(project_id, AscensionMethod.MAGISK, device)

    assert service.load(project_id, AscensionMethod.MAGISK, device) == handoff
    assert handoff.backup_handoff_ready
    assert handoff.backup_evidence_kind == "user-confirmed-cloud"
    assert not handoff.external_backup_verified


def test_consent_review_binds_exact_handoff_but_grants_no_execution(tmp_path: Path):
    store, project_id, device, provider = _prepared(tmp_path)
    handoffs = AscensionFinalHandoffService(store, provider)
    handoff = handoffs.prepare(project_id, AscensionMethod.MAGISK, device)
    now = datetime(2026, 8, 30, 1, 2, 3, tzinfo=UTC)
    service = AscensionConsentReviewService(store, handoffs, lambda: now)

    review = service.record(
        handoff,
        device,
        service.REQUIRED_ACKNOWLEDGEMENTS,
    )

    assert service.load(project_id, AscensionMethod.MAGISK, device) == review
    assert service.load(project_id, AscensionMethod.MAGISK) is None
    assert review.device_name == "Xiaomi 17 Pro Max"
    assert review.target_partition == "init_boot"
    assert review.target_slot == "a"
    assert review.data_action == "keep-data-no-wipe"
    assert review.execution_authority == "none"
    assert review.command_manifest == ()
    assert not review.bootloader_unlock_allowed
    assert not review.bootloader_relock_allowed
    assert not review.user_data_wipe_allowed
    assert not review.phone_changed


def test_consent_review_requires_every_plain_language_acknowledgement(tmp_path: Path):
    store, project_id, device, provider = _prepared(tmp_path)
    handoffs = AscensionFinalHandoffService(store, provider)
    handoff = handoffs.prepare(project_id, AscensionMethod.MAGISK, device)
    service = AscensionConsentReviewService(store, handoffs)

    with pytest.raises(ProjectError, match="every required"):
        service.record(
            handoff,
            device,
            service.REQUIRED_ACKNOWLEDGEMENTS - {"bootloader-relock-prohibited"},
        )


def test_consent_review_expires_and_changed_phone_evidence_invalidates_it(tmp_path: Path):
    store, project_id, device, provider = _prepared(tmp_path)
    handoffs = AscensionFinalHandoffService(store, provider)
    handoff = handoffs.prepare(project_id, AscensionMethod.MAGISK, device)
    clock = [datetime(2026, 8, 30, 1, 2, 3, tzinfo=UTC)]
    service = AscensionConsentReviewService(store, handoffs, lambda: clock[0])
    service.record(handoff, device, service.REQUIRED_ACKNOWLEDGEMENTS)

    wrong_slot = replace(device, slot_suffix="_b")
    assert service.load(project_id, AscensionMethod.MAGISK, wrong_slot) is None
    clock[0] += timedelta(minutes=10)
    assert service.load(project_id, AscensionMethod.MAGISK, device) is None


def test_consent_review_rejects_receipt_tampering(tmp_path: Path):
    store, project_id, device, provider = _prepared(tmp_path)
    handoffs = AscensionFinalHandoffService(store, provider)
    handoff = handoffs.prepare(project_id, AscensionMethod.MAGISK, device)
    service = AscensionConsentReviewService(store, handoffs)
    service.record(handoff, device, service.REQUIRED_ACKNOWLEDGEMENTS)
    path = store.projects_root / project_id / "ascension" / "guardian" / service.RECEIPT_NAME
    data = json.loads(path.read_text(encoding="utf-8"))
    data["bootloader_relock_allowed"] = True
    data["command_manifest"] = [["fastboot", "flashing", "lock"]]
    path.write_text(json.dumps(data), encoding="utf-8")

    assert service.load(project_id, AscensionMethod.MAGISK, device) is None


@pytest.mark.parametrize(
    ("change", "message"),
    (
        ({"serial": "wrong-phone"}, "exact phone"),
        ({"bootloader_locked": True}, "unlocked bootloader"),
        ({"bootloader_locked": None}, "unlocked bootloader"),
        ({"transport": "wireless"}, "direct USB"),
        ({"battery_percent": 49}, "at least 50%"),
        ({"battery_percent": None}, "at least 50%"),
        ({"slot_suffix": "_b"}, "slot evidence"),
        ({"slot_suffix": ""}, "slot evidence"),
    ),
)
def test_final_handoff_fails_closed_on_changed_live_evidence(
    tmp_path: Path,
    change: dict[str, object],
    message: str,
):
    store, project_id, device, provider = _prepared(tmp_path)

    with pytest.raises(ProjectError, match=message):
        AscensionFinalHandoffService(store, provider).prepare(
            project_id,
            AscensionMethod.MAGISK,
            replace(device, **change),
        )


def test_final_handoff_rejects_missing_gate_or_unsafe_manifest(tmp_path: Path):
    store, project_id, device, provider = _prepared(tmp_path)
    without_policy = tuple(
        check for check in provider.manifest.checks if check.check_id != "flash-policy"
    )
    provider.manifest = replace(provider.manifest, checks=without_policy)

    with pytest.raises(ProjectError, match="missing required passing"):
        AscensionFinalHandoffService(store, provider).prepare(
            project_id,
            AscensionMethod.MAGISK,
            device,
        )

    provider.manifest = replace(
        provider.manifest,
        checks=provider.manifest.checks
        + (
            AscensionManifestCheck(
                "flash-policy",
                "flash-policy",
                ManifestState.PASS,
                "verified",
                "",
                "none",
                "",
            ),
        ),
        execution_authority="device-write",
    )
    with pytest.raises(ProjectError, match="unsafe execution authority"):
        AscensionFinalHandoffService(store, provider).prepare(
            project_id,
            AscensionMethod.MAGISK,
            device,
        )


def test_final_handoff_tampering_or_artifact_change_invalidates_receipt(tmp_path: Path):
    store, project_id, device, provider = _prepared(tmp_path)
    service = AscensionFinalHandoffService(store, provider)
    handoff = service.prepare(project_id, AscensionMethod.MAGISK, device)
    path = store.projects_root / project_id / "ascension" / "guardian" / service.RECEIPT_NAME
    data = json.loads(path.read_text(encoding="utf-8"))
    data["bootloader_relock_allowed"] = True
    data["command_manifest"] = [["fastboot", "flashing", "lock"]]
    path.write_text(json.dumps(data), encoding="utf-8")
    assert service.load(project_id, AscensionMethod.MAGISK, device) is None

    service.prepare(project_id, AscensionMethod.MAGISK, device)
    patched = store.workspace / handoff.patched_image_path
    patched.chmod(0o600)
    patched.write_bytes(_boot_v4(b"tampered patched image"))
    assert service.load(project_id, AscensionMethod.MAGISK, device) is None


def test_root_plan_storage_is_private_bounded_and_type_strict(tmp_path: Path) -> None:
    store, project_id, device, _provider = _prepared(tmp_path)
    service = AscensionRootPlanService(store)
    root = store.projects_root / project_id / "ascension" / "plan"
    path = root / service.RECEIPT_NAME

    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["backup_handoff_ready"] = 1
    _redigest(payload, "plan_digest")
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load(project_id, AscensionMethod.MAGISK) is None

    service.create(project_id, AscensionMethod.MAGISK, device)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected"] = "field"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load(project_id, AscensionMethod.MAGISK) is None

    with path.open("wb") as stream:
        stream.truncate(service.MAX_BYTES + 1)
    assert service.load(project_id, AscensionMethod.MAGISK) is None

    outside = tmp_path / "outside-plan.romverse"
    outside.write_text("{}", encoding="utf-8")
    path.unlink()
    path.symlink_to(outside)
    assert service.load(project_id, AscensionMethod.MAGISK) is None


def test_root_plan_refuses_redirected_evidence_directory(tmp_path: Path) -> None:
    store, project_id, device, _provider = _prepared(tmp_path)
    service = AscensionRootPlanService(store)
    root = store.projects_root / project_id / "ascension" / "plan"
    outside = tmp_path / "outside-plan"
    root.rename(outside)
    root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ProjectError, match="stored safely"):
        service.create(project_id, AscensionMethod.MAGISK, device)


def test_guardian_manifest_storage_is_private_bounded_and_type_strict(
    tmp_path: Path,
) -> None:
    store, project_id, device, _provider = _prepared(tmp_path)
    service = AscensionGuardianManifestService(store, DevicePackRegistry(()))
    manifest = service.prepare(project_id, AscensionMethod.MAGISK, device)
    root = store.projects_root / project_id / "ascension" / "guardian"
    path = root / service.RECEIPT_NAME
    history = root / f"guardian-manifest-{manifest.manifest_id[:12]}.romverse"

    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(history.stat().st_mode) == 0o600

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["final_consent_required"] = 1
    _redigest(payload, "manifest_digest")
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load(project_id, AscensionMethod.MAGISK) is None

    service.prepare(project_id, AscensionMethod.MAGISK, device)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected"] = "field"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load(project_id, AscensionMethod.MAGISK) is None

    with path.open("wb") as stream:
        stream.truncate(service.MAX_BYTES + 1)
    assert service.load(project_id, AscensionMethod.MAGISK) is None

    outside = tmp_path / "outside-manifest.romverse"
    outside.write_text("{}", encoding="utf-8")
    path.unlink()
    path.symlink_to(outside)
    assert service.load(project_id, AscensionMethod.MAGISK) is None


def test_guardian_manifest_refuses_redirected_evidence_directory(tmp_path: Path) -> None:
    store, project_id, device, _provider = _prepared(tmp_path)
    service = AscensionGuardianManifestService(store, DevicePackRegistry(()))
    root = store.projects_root / project_id / "ascension" / "guardian"
    outside = tmp_path / "outside-guardian"
    outside.mkdir()
    root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ProjectError, match="stored safely"):
        service.prepare(project_id, AscensionMethod.MAGISK, device)


def test_final_handoff_storage_is_private_bounded_and_type_strict(tmp_path: Path) -> None:
    store, project_id, device, provider = _prepared(tmp_path)
    service = AscensionFinalHandoffService(store, provider)
    handoff = service.prepare(project_id, AscensionMethod.MAGISK, device)
    root = store.projects_root / project_id / "ascension" / "guardian"
    path = root / service.RECEIPT_NAME
    history = root / f"final-handoff-{handoff.handoff_id[:12]}.romverse"

    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(history.stat().st_mode) == 0o600

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["battery_percent"] = True
    _redigest(payload, "handoff_digest")
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load(project_id, AscensionMethod.MAGISK, device) is None

    service.prepare(project_id, AscensionMethod.MAGISK, device)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected"] = "field"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load(project_id, AscensionMethod.MAGISK, device) is None

    with path.open("wb") as stream:
        stream.truncate(service.MAX_BYTES + 1)
    assert service.load(project_id, AscensionMethod.MAGISK, device) is None

    outside = tmp_path / "outside-final-handoff.romverse"
    outside.write_text("{}", encoding="utf-8")
    path.unlink()
    path.symlink_to(outside)
    assert service.load(project_id, AscensionMethod.MAGISK, device) is None


def test_consent_storage_is_private_bounded_and_type_strict(tmp_path: Path) -> None:
    store, project_id, device, provider = _prepared(tmp_path)
    handoffs = AscensionFinalHandoffService(store, provider)
    handoff = handoffs.prepare(project_id, AscensionMethod.MAGISK, device)
    service = AscensionConsentReviewService(store, handoffs)
    service.record(handoff, device, service.REQUIRED_ACKNOWLEDGEMENTS)
    root = store.projects_root / project_id / "ascension" / "guardian"
    path = root / service.RECEIPT_NAME

    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["bootloader_relock_allowed"] = 0
    _redigest(payload, "review_digest")
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load(project_id, AscensionMethod.MAGISK, device) is None

    service.record(handoff, device, service.REQUIRED_ACKNOWLEDGEMENTS)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected"] = "field"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load(project_id, AscensionMethod.MAGISK, device) is None

    with path.open("wb") as stream:
        stream.truncate(service.MAX_BYTES + 1)
    assert service.load(project_id, AscensionMethod.MAGISK, device) is None

    outside = tmp_path / "outside-consent.romverse"
    outside.write_text("{}", encoding="utf-8")
    path.unlink()
    path.symlink_to(outside)
    assert service.load(project_id, AscensionMethod.MAGISK, device) is None
    with pytest.raises(ProjectError, match="stored safely"):
        service.record(handoff, device, service.REQUIRED_ACKNOWLEDGEMENTS)
