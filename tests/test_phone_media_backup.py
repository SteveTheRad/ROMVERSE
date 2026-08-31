from __future__ import annotations

import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from romverse.backup.media import PhoneMediaBackupService, PhoneMediaScope
from romverse.device.models import AndroidDevice, DeviceState
from romverse.guardian.approval import ApprovalStore
from romverse.guardian.backup_transfer import media_pull_digest
from romverse.guardian.models import GuardianDeniedError, OperationClass, OperationRequest
from romverse.guardian.policy import GuardianPolicy
from romverse.infrastructure.process import CommandResult
from romverse.rom.projects import RomProjectStore
from romverse.rom.recovery_evidence import RecoveryEvidenceService


def _device() -> AndroidDevice:
    return AndroidDevice(
        "private-serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        marketing_name="Xiaomi 17 Pro Max",
        product="popsicle",
        codename="popsicle",
    )


class BackupGateway:
    def __init__(self) -> None:
        self.requests: list[OperationRequest] = []

    def execute(self, request: OperationRequest, timeout: float = 10) -> CommandResult:
        self.requests.append(request)
        remote = request.arguments[3]
        local = Path(request.arguments[4])
        if remote == "/sdcard/Pictures":
            return CommandResult(request.arguments, 1, "", "remote object does not exist")
        local.mkdir(parents=True)
        (local / "photo.jpg").write_bytes(b"verified-phone-photo")
        (local / "nested").mkdir()
        (local / "nested" / "note.txt").write_text("ROMVERSE")
        return CommandResult(request.arguments, 0, "2 files pulled", "")


def test_phone_media_backup_creates_verified_archive_and_truthful_receipt(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    destination = tmp_path / "local-drive"
    workspace.mkdir()
    destination.mkdir()
    gateway = BackupGateway()
    service = PhoneMediaBackupService(
        workspace,
        Path("/usr/bin/adb"),
        gateway,  # type: ignore[arg-type]
    )
    plan = service.prepare(
        _device(),
        destination,
        (PhoneMediaScope.CAMERA, PhoneMediaScope.PICTURES),
    )
    service.approve(plan)
    progress: list[tuple[int, int]] = []

    receipt_path = Path(plan.archive_path).with_suffix(".zip.romverse")
    terminal_receipt_state = []

    def record_progress(done: int, total: int) -> None:
        progress.append((done, total))
        if done >= total:
            terminal_receipt_state.append(receipt_path.is_file())

    receipt = service.execute(plan, record_progress)

    archive = Path(plan.archive_path)
    assert archive.is_file()
    assert receipt.file_count == 2
    assert receipt.captured_scopes == (PhoneMediaScope.CAMERA.value,)
    assert receipt.unavailable_scopes == (PhoneMediaScope.PICTURES.value,)
    assert not receipt.app_private_data_included
    assert not receipt.contacts_or_messages_claimed
    assert not receipt.phone_changed
    assert not receipt.bootloader_changed
    assert receipt.execution_authority == "guardian-approved-read-only-backup"
    assert progress == [(8, 28), (28, 28)]
    assert terminal_receipt_state == [True]
    assert len(gateway.requests) == 2
    assert all(request.category is OperationClass.READ_ONLY for request in gateway.requests)
    assert not (destination / f".ROMVERSE-{plan.plan_id}.partial").exists()

    with zipfile.ZipFile(archive) as bundle:
        manifest = json.loads(bundle.read("ROMVERSE-MANIFEST.json"))
        assert manifest["coverage"] == "user-accessible shared storage only"
        assert {entry["path"] for entry in manifest["files"]} == {
            "DCIM/nested/note.txt",
            "DCIM/photo.jpg",
        }
    sidecar = json.loads(archive.with_suffix(".zip.romverse").read_text())
    assert sidecar["receipt_digest"] == receipt.receipt_digest
    assert service.verify_receipt(archive, receipt) == receipt


def test_romverse_local_backup_evidence_is_bound_to_the_exact_phone(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    destination = tmp_path / "local-drive"
    destination.mkdir()
    store = RomProjectStore(workspace)
    project = store.create("Exact phone backup")
    source = tmp_path / "firmware.zip"
    source.write_bytes(b"protected firmware")
    store.import_original(project.project_id, source)
    service = PhoneMediaBackupService(
        workspace,
        Path("/usr/bin/adb"),
        BackupGateway(),  # type: ignore[arg-type]
    )
    device = _device()
    plan = service.prepare(device, destination, (PhoneMediaScope.CAMERA,))
    service.approve(plan)
    receipt = service.execute(plan)
    archive = Path(plan.archive_path)
    recovery = RecoveryEvidenceService(store)

    recovery.register_phone_media_backup(project.project_id, archive, receipt)

    exact = recovery.assess(project.project_id, device)
    different = recovery.assess(project.project_id, replace(device, serial="another-phone"))
    assert exact.external_backup_ready
    assert any("exact connected phone bound" in item for item in exact.evidence)
    assert not different.external_backup_ready
    assert any("different phone" in item for item in different.evidence)

    sidecar = archive.with_suffix(".zip.romverse")
    payload = json.loads(sidecar.read_text())
    payload["device_key"] = "0" * 20
    sidecar.write_text(json.dumps(payload))
    with pytest.raises(Exception, match="receipt"):
        service.verify_receipt(archive, receipt)


def test_phone_media_backup_rejects_workspace_destination_and_modified_plan(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    service = PhoneMediaBackupService(
        workspace,
        Path("/usr/bin/adb"),
        BackupGateway(),  # type: ignore[arg-type]
    )
    with pytest.raises(Exception, match="outside the ROMVERSE workspace"):
        service.prepare(_device(), workspace, (PhoneMediaScope.CAMERA,))

    destination = tmp_path / "backup"
    destination.mkdir()
    plan = service.prepare(_device(), destination, (PhoneMediaScope.CAMERA,))
    with pytest.raises(GuardianDeniedError, match="integrity"):
        service.execute(replace(plan, device_name="Different phone"))


def test_guardian_allows_only_exact_approved_shared_storage_pull(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    destination = tmp_path / "local-drive"
    workspace.mkdir()
    destination.mkdir()
    partial = destination / ".ROMVERSE-plan.partial"
    partial.mkdir()
    local = partial / "DCIM"
    serial = "private-serial"
    policy = GuardianPolicy(workspace)
    target = policy.privacy.pseudonym(serial)
    digest = media_pull_digest(serial, "/sdcard/DCIM", local)
    ApprovalStore(workspace).issue(digest, target)
    request = OperationRequest(
        "backup.pull_media",
        OperationClass.READ_ONLY,
        "/usr/bin/adb",
        ("-s", serial, "pull", "/sdcard/DCIM", str(local)),
        "Copy reviewed camera media",
        target=serial,
        approval_digest=digest,
        approval_target=target,
    )

    assert policy.assess(request).allowed
    assert not policy.assess(
        replace(
            request,
            arguments=("-s", serial, "pull", "/data", str(partial / "data")),
        )
    ).allowed
    assert not policy.assess(replace(request, operation_id="bootloader.relock")).allowed
