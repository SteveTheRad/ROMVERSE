from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path

import pytest
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
    source = _source(tmp_path / "adbb99b9d6e6c3e6-HyperOS4-Xiaomi17ProMax-Debloated-CustomRom.zip")
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
