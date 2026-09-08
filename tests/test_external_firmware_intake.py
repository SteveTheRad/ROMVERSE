from __future__ import annotations

import hashlib
import json
import os
import stat
import zipfile
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from romverse.device_packs.registry import DevicePackRegistry
from romverse.rom import external_intake
from romverse.rom.external_intake import ExternalFirmwareIntakeService
from romverse.rom.inspection import RomInspector
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.ui.rom_studio import RomStudio


def _source(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/com/android/metadata", b"post-device=popsicle\n")
        archive.writestr("images/super.img", b"fixture-super")
    path.chmod(0o444)
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _metadata_source(path: Path) -> tuple[Path, bytes, bytes]:
    build_info = (
        b"manufacturer=Xiaomi\n"
        b"codename=popsicle\n"
        b"firmware_version=OS4.0.0.32.XPBCNXM\n"
        b"android_version=17\n"
        b"region=China\n"
        b"channel=stable\n"
        b"base_provenance=official full OTA\n"
    )
    procedure = b"fastboot flash system system.img\n"
    manifest = (
        f"{hashlib.sha256(build_info).hexdigest()}  BUILD-INFO.txt\n"
        f"{hashlib.sha256(procedure).hexdigest()}  tools/flash_all.bat\n"
    ).encode()
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("tools/", b"")
        archive.writestr("BUILD-INFO.txt", build_info)
        archive.writestr("SHA256SUMS", manifest)
        archive.writestr("tools/flash_all.bat", procedure)
        archive.writestr(
            "META-INF/com/google/android/updater-script",
            b"ui_print('fixture');\n",
        )
        archive.writestr("images/super.img", b"fixture-super")
    path.chmod(0o444)
    return path, build_info, procedure


def test_external_intake_hashes_and_inspects_without_copying_or_authority(tmp_path) -> None:
    source = _source(tmp_path / "adbb99b9d6e6c3e6-HyperOS4-Xiaomi17ProMax-Debloated-CustomRom.zip")
    before = source.stat()
    before_digest = _sha256(source)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("External intake")
    progress: list[tuple[int, int]] = []

    receipt = ExternalFirmwareIntakeService(store).inspect(
        project.project_id,
        source,
        lambda done, total: progress.append((done, total)),
    )

    after = source.stat()
    assert _sha256(source) == before_digest == receipt.source_sha256
    assert (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_mode) == (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_mode,
    )
    assert receipt.project_id == project.project_id
    assert receipt.container == "zip"
    assert receipt.entry_count == 2
    assert receipt.partition_signals == ("super",)
    assert receipt.metadata_signals == ("meta-inf/com/android/metadata",)
    assert receipt.package_type == "Unclassified ZIP firmware container"
    assert receipt.identity_confidence == "unknown"
    assert receipt.authority == ExternalFirmwareIntakeService.AUTHORITY
    assert receipt.source_copied is False
    assert receipt.source_extracted is False
    assert receipt.phone_changed is False
    assert receipt.bootloader_relock == "never"
    assert progress[-1] == (source.stat().st_size, source.stat().st_size)
    assert store.get(project.project_id).original is None
    assert not store.originals_root.exists() or not tuple(store.originals_root.iterdir())
    assert ExternalFirmwareIntakeService(store).load(project.project_id) == receipt
    inventory = ExternalFirmwareIntakeService(store).load_inventory(project.project_id)
    assert inventory is not None
    assert inventory.metadata_members == ()
    assert inventory.identity_facts == ()
    assert inventory.procedure_members == ()
    assert inventory.execution_authority == "none"
    assert inventory.bootloader_relock == "never"


def test_external_intake_records_bounded_metadata_and_untrusted_procedures(tmp_path) -> None:
    source, build_info, procedure = _metadata_source(tmp_path / "firmware.zip")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Package metadata")
    service = ExternalFirmwareIntakeService(store)

    receipt = service.inspect(project.project_id, source)
    inventory = service.load_inventory(project.project_id)

    assert inventory is not None
    assert inventory.source_sha256 == receipt.source_sha256
    assert [(item.path, item.size_bytes, item.sha256) for item in inventory.metadata_members] == [
        ("BUILD-INFO.txt", len(build_info), hashlib.sha256(build_info).hexdigest()),
        (
            "SHA256SUMS",
            inventory.metadata_members[1].size_bytes,
            inventory.metadata_members[1].sha256,
        ),
    ]
    assert {item.field: item.value for item in inventory.identity_facts} == {
        "android_version": "17",
        "base_provenance": "official full OTA",
        "build_id": "OS4.0.0.32.XPBCNXM",
        "channel": "stable",
        "codename": "popsicle",
        "manufacturer": "Xiaomi",
        "region": "China",
    }
    assert [item.path for item in inventory.procedure_members] == [
        "META-INF/com/google/android/updater-script",
        "tools/flash_all.bat",
    ]
    assert (
        next(
            item.sha256
            for item in inventory.procedure_members
            if item.path == "tools/flash_all.bat"
        )
        == hashlib.sha256(procedure).hexdigest()
    )
    assert inventory.manifest_verified_paths == ("BUILD-INFO.txt", "tools/flash_all.bat")
    encoded = (store.projects_root / project.project_id / service.INVENTORY_NAME).read_text(
        encoding="utf-8"
    )
    assert "fastboot flash" not in encoded
    assert "ui_print" not in encoded
    assert inventory.identity_authority == "package-declared-unverified"
    assert inventory.procedure_authority == "untrusted-presence-only-never-executable"
    assert (
        inventory.build_authority
        == inventory.device_authority
        == inventory.execution_authority
        == "none"
    )


@pytest.mark.parametrize(
    "defect",
    [
        "duplicate",
        "duplicate_path",
        "encoding",
        "malformed",
        "oversized",
        "command",
        "relock",
        "manifest",
        "special_member",
    ],
)
def test_external_metadata_defects_fail_before_any_receipt(tmp_path, defect) -> None:
    source = tmp_path / "firmware.zip"
    build_info = b"manufacturer=Xiaomi\ncodename=popsicle\n"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(
            "BUILD-INFO.txt", b"manufacturer=Xiaomi\n" if defect == "duplicate" else build_info
        )
        if defect == "duplicate":
            archive.writestr("android-info.txt", b"manufacturer=Xiaomi\n")
        elif defect == "duplicate_path":
            archive.writestr("build-info.txt", b"codename=popsicle\n")
        elif defect == "encoding":
            archive.writestr("android-info.txt", b"codename=\xff\n")
        elif defect == "malformed":
            archive.writestr("android-info.txt", b"this is not key value metadata\n")
        elif defect == "oversized":
            archive.writestr("android-info.txt", b"x" * (256 * 1024 + 1))
        elif defect == "command":
            archive.writestr("android-info.txt", b"base=official; reboot\n")
        elif defect == "relock":
            archive.writestr("android-info.txt", b"base=fastboot flashing lock\n")
        elif defect == "special_member":
            special = zipfile.ZipInfo("tools/flash.sh")
            special.create_system = 3
            special.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(special, b"../payload/flash.sh")
        else:
            archive.writestr("SHA256SUMS", f"{'0' * 64}  BUILD-INFO.txt\n")
    source.chmod(0o444)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create(f"Rejected {defect}")
    service = ExternalFirmwareIntakeService(store)

    with pytest.raises(ProjectError):
        service.inspect(project.project_id, source)

    project_root = store.projects_root / project.project_id
    assert not (project_root / service.RECEIPT_NAME).exists()
    assert not (project_root / service.INVENTORY_NAME).exists()


def test_external_inventory_rejects_hidden_command_field(tmp_path) -> None:
    source, _build_info, _procedure = _metadata_source(tmp_path / "firmware.zip")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Strict inventory")
    service = ExternalFirmwareIntakeService(store)
    service.inspect(project.project_id, source)
    path = store.projects_root / project.project_id / service.INVENTORY_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["command"] = "fastboot flashing lock"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert service.load_inventory(project.project_id) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", True),
        ("manifest_verified_paths", ["missing/flash.sh"]),
    ],
)
def test_external_inventory_rejects_invalid_durable_fields(tmp_path, field, value) -> None:
    source, _build_info, _procedure = _metadata_source(tmp_path / "firmware.zip")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Strict durable inventory")
    service = ExternalFirmwareIntakeService(store)
    service.inspect(project.project_id, source)
    path = store.projects_root / project.project_id / service.INVENTORY_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[field] = value
    unsigned = dict(payload)
    unsigned.pop("format")
    unsigned.pop("record_digest")
    payload["record_digest"] = external_intake._digest(unsigned)
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert service.load_inventory(project.project_id) is None


def test_external_intake_does_not_reopen_selected_path_for_inspection(
    tmp_path, monkeypatch
) -> None:
    source = _source(tmp_path / "firmware.zip")
    expected = _sha256(source)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("One descriptor")
    original_open = Path.open

    def reject_source_reopen(path: Path, *args, **kwargs):
        if path == source:
            raise AssertionError("selected firmware path was reopened")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", reject_source_reopen)

    receipt = ExternalFirmwareIntakeService(store).inspect(project.project_id, source)

    assert receipt.source_sha256 == expected
    assert receipt.container == "zip"
    assert receipt.partition_signals == ("super",)


def test_external_intake_replacement_cannot_mix_path_metadata_with_open_descriptor(
    tmp_path, monkeypatch
) -> None:
    source = _source(tmp_path / "firmware.zip")
    original_digest = _sha256(source)
    replacement = tmp_path / "replacement.zip"
    with zipfile.ZipFile(replacement, "w") as archive:
        archive.writestr("images/vbmeta.img", b"replacement-vbmeta")
    replacement.chmod(0o444)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Directory entry replacement")
    observed = {}

    class ReplacingInspector(RomInspector):
        def inspect_stream(self, stream, expected_sha256, source_name):
            os.replace(replacement, source)
            report = super().inspect_stream(stream, expected_sha256, source_name)
            observed["digest"] = expected_sha256
            observed["partitions"] = report.partition_signals
            return report

    monkeypatch.setattr(external_intake, "RomInspector", ReplacingInspector)

    with pytest.raises(ProjectError, match="changed during bounded inspection"):
        ExternalFirmwareIntakeService(store).inspect(project.project_id, source)

    assert observed == {"digest": original_digest, "partitions": ("super",)}
    assert _sha256(source) != original_digest
    assert not (
        store.projects_root / project.project_id / ExternalFirmwareIntakeService.RECEIPT_NAME
    ).exists()


def test_external_intake_load_fails_closed_after_source_drift(tmp_path) -> None:
    source = _source(tmp_path / "firmware.zip")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Drift check")
    service = ExternalFirmwareIntakeService(store)
    service.inspect(project.project_id, source)

    source.chmod(0o644)
    source.write_bytes(b"changed")

    assert service.load(project.project_id) is None
    assert store.get(project.project_id).original is None


def test_external_intake_rejects_hidden_receipt_fields(tmp_path) -> None:
    source = _source(tmp_path / "firmware.zip")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Strict receipt")
    service = ExternalFirmwareIntakeService(store)
    service.inspect(project.project_id, source)
    path = store.projects_root / project.project_id / service.RECEIPT_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["command"] = "fastboot flashing lock"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert service.load(project.project_id) is None


def test_studio_presents_external_evidence_and_keeps_consequential_actions_locked(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    source, _build_info, _procedure = _metadata_source(
        tmp_path / "adbb99b9d6e6c3e6-HyperOS4-Xiaomi17ProMax-Debloated-CustomRom.zip"
    )
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("External intake UI")
    receipt = ExternalFirmwareIntakeService(store).inspect(project.project_id, source)

    studio = RomStudio(store, DevicePackRegistry(()))
    studio.refresh(project.project_id)
    app.processEvents()

    assert studio.current_project is not None
    assert studio.current_project.original is None
    assert studio.external_intake_button.isEnabled()
    assert studio.external_intake_button.text() == "Reinspect external firmware in place"
    assert studio.import_button.isEnabled()
    assert studio.original_name.text() == "External firmware inspected • not imported"
    assert receipt.source_sha256 in studio.original_detail.text()
    assert "no workspace copy" in studio.original_detail.text()
    assert "External read-only evidence" in studio.inspection_detail.text()
    assert "Known" in studio.inspection_detail.text()
    assert "Unconfirmed" in studio.inspection_detail.text()
    assert "Package-declared identity (UNVERIFIED)" in studio.inspection_detail.text()
    assert "Untrusted procedure presence (NEVER EXECUTED)" in studio.inspection_detail.text()
    assert "tools/flash_all.bat" in studio.inspection_detail.text()
    assert "Build/install/Guardian/flash authority  •  LOCKED" in studio.inspection_detail.text()
    assert studio.inspection_detail.textFormat() is Qt.TextFormat.PlainText
    assert studio.upgrade_passport_status.text() == (
        "READ-ONLY SOURCE EVIDENCE • RELATIONSHIP UNCONFIRMED"
    )
    assert "guardian_flash  •  UNCONFIRMED" in studio.device_dna_detail.text()
    assert "Compatibility Matrix  •  Unknown" in studio.device_dna_detail.text()
    for action in (
        studio.verify_button,
        studio.inspect_button,
        studio.working_button,
        studio.extract_button,
        studio.plan_button,
        studio.forge_button,
        studio.new_recipe_button,
    ):
        assert not action.isEnabled()
    studio.close()

    restarted = RomStudio(store, DevicePackRegistry(()))
    restarted.refresh(project.project_id)
    app.processEvents()
    assert restarted.current_project is not None
    assert restarted.current_project.original is None
    assert restarted.external_intake.load(project.project_id) == receipt
    assert restarted.external_intake_button.text() == "Reinspect external firmware in place"
    assert receipt.source_sha256 in restarted.original_detail.text()
    assert "Build/install/flash: LOCKED" in restarted.upgrade_passport_detail.text()
    restarted.close()
