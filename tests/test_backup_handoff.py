import json
import zipfile

from romverse.backup.handoff import BackupHandoffService, CloudBackupProvider
from romverse.device.models import AndroidDevice, DeviceState
from romverse.rom.projects import RomProjectStore


def _prepared(tmp_path):
    source = tmp_path / "firmware.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("boot.img", b"boot")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Cloud handoff", "test.pack")
    store.import_original(project.project_id, source)
    device = AndroidDevice(
        "serial",
        DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        marketing_name="Xiaomi 17 Pro Max",
        codename="popsicle",
        rom_display="OS4.0.0.23.XPBCNXM",
    )
    return store, project, device


def test_cloud_handoff_is_exact_device_bound_and_never_claims_content_inspection(tmp_path):
    store, project, device = _prepared(tmp_path)
    service = BackupHandoffService(store)

    receipt = service.confirm_cloud(
        project.project_id,
        device,
        CloudBackupProvider.XIAOMI,
        "Backup completed today at 15:42",
        backup_completed=True,
        restore_access_confirmed=True,
        critical_data_scope_reviewed=True,
        limitations_acknowledged=True,
    )

    assert service.load(project.project_id, device) == receipt
    assert not receipt.independently_readable_file_verified
    assert not receipt.cloud_contents_inspected
    assert not receipt.phone_changed
    other = AndroidDevice(
        "other",
        DeviceState.DEVICE,
        model="different",
        codename="different",
    )
    assert service.load(project.project_id, other) is None


def test_tampered_cloud_handoff_is_rejected(tmp_path):
    store, project, device = _prepared(tmp_path)
    service = BackupHandoffService(store)
    service.confirm_cloud(
        project.project_id,
        device,
        CloudBackupProvider.GOOGLE,
        "Google Backup says complete",
        backup_completed=True,
        restore_access_confirmed=True,
        critical_data_scope_reviewed=True,
        limitations_acknowledged=True,
    )
    path = store.projects_root / project.project_id / service.RECEIPT_NAME
    payload = json.loads(path.read_text())
    payload["cloud_contents_inspected"] = True
    path.write_text(json.dumps(payload))

    assert service.load(project.project_id, device) is None
