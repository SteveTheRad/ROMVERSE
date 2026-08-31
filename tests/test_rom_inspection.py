import io
import json
import stat
import struct
import tarfile
import zipfile
from dataclasses import replace

import pytest

from romverse.rom.inspection import (
    ContainerKind,
    FindingSeverity,
    RomInspectionService,
    RomInspector,
)
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


def test_zip_inventory_detects_android_signals_without_extraction(tmp_path):
    archive = tmp_path / "ota.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("payload.bin", b"payload")
        output.writestr("META-INF/com/android/metadata", b"ota-type=AB")
        output.writestr("IMAGES/boot.img", b"boot")
        output.writestr("system.new.dat.br", b"system")
    report = RomInspector().inspect(archive, "expected")
    assert report.container is ContainerKind.ZIP
    assert report.entry_count == 4
    assert {"ota_payload", "boot", "system"} <= set(report.partition_signals)
    assert "meta-inf/com/android/metadata" in report.metadata_signals
    assert report.complete


def test_zip_flags_traversal_and_symbolic_links(tmp_path):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("../../outside", b"unsafe")
        link = zipfile.ZipInfo("system/link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        output.writestr(link, "../../target")
    report = RomInspector().inspect(archive, "expected")
    ids = {finding.finding_id for finding in report.findings}
    assert "archive.unsafe_path" in ids
    assert "archive.link" in ids
    assert any(finding.severity is FindingSeverity.CRITICAL for finding in report.findings)


def test_hostile_finding_and_metadata_growth_is_bounded(tmp_path):
    archive = tmp_path / "many-unsafe.zip"
    with zipfile.ZipFile(archive, "w") as output:
        for index in range(300):
            output.writestr(f"../outside-{index}", b"unsafe")
            output.writestr(f"prefix-{index}/META-INF/com/android/metadata", b"metadata")
    inspector = RomInspector()
    report = inspector.inspect(archive, "expected")
    assert len(report.findings) == inspector.MAX_FINDINGS + 1
    assert report.findings[-1].finding_id == "inspection.finding_limit"
    assert report.metadata_signals == ("meta-inf/com/android/metadata",)


def test_tar_flags_link_and_inventory(tmp_path):
    archive = tmp_path / "firmware.tar"
    with tarfile.open(archive, "w") as output:
        data = b"vbmeta"
        image = tarfile.TarInfo("AP/vbmeta.img")
        image.size = len(data)
        output.addfile(image, io.BytesIO(data))
        link = tarfile.TarInfo("AP/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../outside"
        output.addfile(link)
    report = RomInspector().inspect(archive, "expected")
    assert report.container is ContainerKind.TAR
    assert "vbmeta" in report.partition_signals
    assert any(finding.finding_id == "archive.link" for finding in report.findings)


def test_tar_special_entries_are_critical_and_cannot_be_extracted(tmp_path):
    archive = tmp_path / "special.tar"
    with tarfile.open(archive, "w") as output:
        device = tarfile.TarInfo("system/dev/unsafe")
        device.type = tarfile.CHRTYPE
        output.addfile(device)
    report = RomInspector().inspect(archive, "expected")
    assert any(
        finding.finding_id == "archive.special_entry"
        and finding.severity is FindingSeverity.CRITICAL
        for finding in report.findings
    )

    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Special archive").project_id, archive)
    with pytest.raises(ProjectError, match="critical structure findings"):
        RomInspectionService(store).extract_project_tree(project.project_id)


@pytest.mark.parametrize(
    ("content", "kind"),
    [
        (b"ANDROID!" + b"\0" * 4096, ContainerKind.ANDROID_BOOT),
        (b"CrAU" + b"\0" * 4096, ContainerKind.ANDROID_PAYLOAD),
        (b"AVB0" + b"\0" * 4096, ContainerKind.ANDROID_VBMETA),
        (struct.pack("<I", 0xED26FF3A) + b"\0" * 4096, ContainerKind.ANDROID_SPARSE),
        (b"\0" * 1080 + b"\x53\xef" + b"\0" * 100, ContainerKind.EXT4),
        (b"\0" * 1024 + struct.pack("<I", 0xE0F5E1E2), ContainerKind.EROFS),
    ],
)
def test_android_container_magic_detection(tmp_path, content, kind):
    path = tmp_path / "container.img"
    path.write_bytes(content)
    assert RomInspector().inspect(path, "expected").container is kind


def test_corrupt_zip_becomes_finding_instead_of_exception(tmp_path):
    path = tmp_path / "broken.zip"
    path.write_bytes(b"PK\x03\x04not-a-real-central-directory")
    report = RomInspector().inspect(path, "expected")
    assert not report.complete
    assert report.findings[0].finding_id == "archive.invalid"


def test_service_verifies_original_then_persists_versioned_report(tmp_path):
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as output:
        output.writestr("super.img", b"super")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Inspection")
    store.import_original(project.project_id, source)
    service = RomInspectionService(store)
    report = service.inspect_project(project.project_id)
    loaded = service.load_report(project.project_id)
    assert loaded == report
    path = store.projects_root / project.project_id / service.REPORT_NAME
    payload = json.loads(path.read_text())
    assert payload["format"] == "romverse.inspection"
    assert payload["schema_version"] == 2
    assert len(payload["record_digest"]) == 64
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_inspection_report_rejects_tampering_oversize_and_symlink(tmp_path):
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as output:
        output.writestr("payload.bin", b"payload")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Hostile report").project_id, source)
    service = RomInspectionService(store)
    service.inspect_project(project.project_id)
    path = store.projects_root / project.project_id / service.REPORT_NAME
    original = path.read_bytes()

    payload = json.loads(original)
    payload["container"] = "android_boot"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load_report(project.project_id) is None

    payload = json.loads(original)
    payload["unexpected"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load_report(project.project_id) is None

    path.write_bytes(b"{" + b" " * service.MAX_REPORT_BYTES + b"}")
    assert service.load_report(project.project_id) is None

    outside = tmp_path / "outside-inspection.json"
    outside.write_bytes(original)
    path.unlink()
    path.symlink_to(outside)
    assert service.load_report(project.project_id) is None
    assert outside.read_bytes() == original


def test_legacy_inspection_is_readable_and_reinspected_before_extraction(tmp_path):
    source = tmp_path / "legacy.zip"
    with zipfile.ZipFile(source, "w") as output:
        output.writestr("IMAGES/system.img", b"system")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Legacy inspection").project_id, source)
    service = RomInspectionService(store)
    service.inspect_project(project.project_id)
    path = store.projects_root / project.project_id / service.REPORT_NAME
    payload = json.loads(path.read_text())
    payload["schema_version"] = 1
    payload.pop("record_digest")
    path.write_text(json.dumps(payload), encoding="utf-8")

    legacy = service.load_report(project.project_id)
    assert legacy is not None
    assert legacy.schema_version == 1

    tree = service.extract_project_tree(project.project_id)
    refreshed = service.load_report(project.project_id)
    stored = json.loads(path.read_text())

    assert (tree / "IMAGES/system.img").read_bytes() == b"system"
    assert refreshed is not None
    assert refreshed.schema_version == 2
    assert stored["schema_version"] == 2
    assert len(stored["record_digest"]) == 64


def test_inspection_rejects_original_mutation_during_scan(tmp_path):
    source = tmp_path / "mutable.img"
    source.write_bytes(b"ANDROID!" + b"\0" * 4096)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Mutable inspection").project_id, source)

    class MutatingInspector(RomInspector):
        def inspect(self, path, expected_sha256, source_name=""):
            report = super().inspect(path, expected_sha256, source_name)
            path.chmod(0o644)
            path.write_bytes(path.read_bytes() + b"changed")
            return report

    with pytest.raises(ProjectError, match="changed during structure inspection"):
        RomInspectionService(store, MutatingInspector()).inspect_project(project.project_id)

    report_path = store.projects_root / project.project_id / RomInspectionService.REPORT_NAME
    assert not report_path.exists()


def test_service_refuses_inspection_after_original_tampering(tmp_path):
    source = tmp_path / "rom.img"
    source.write_bytes(b"ANDROID!" + b"\0" * 100)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Tampered inspection")
    imported = store.import_original(project.project_id, source)
    protected = store.workspace / imported.original.workspace_path
    protected.chmod(0o644)
    protected.write_bytes(b"changed")
    with pytest.raises(ProjectError, match="integrity check failed"):
        RomInspectionService(store).inspect_project(project.project_id)


def test_service_extracts_clean_zip_into_contained_tree(tmp_path):
    source = tmp_path / "clean.zip"
    with zipfile.ZipFile(source, "w") as output:
        output.writestr("IMAGES/system.img", b"system")
        output.writestr("META-INF/com/android/metadata", b"ota")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Extraction")
    store.import_original(project.project_id, source)
    tree = RomInspectionService(store).extract_project_tree(project.project_id)
    assert (tree / "IMAGES/system.img").read_bytes() == b"system"
    assert tree.is_relative_to(store.working_root)
    assert stat.S_IMODE(tree.stat().st_mode) == 0o700
    assert stat.S_IMODE((tree / "IMAGES").stat().st_mode) == 0o700
    assert stat.S_IMODE((tree / "IMAGES/system.img").stat().st_mode) == 0o600
    summary = RomInspectionService(store).summarize_working_tree(project.project_id)
    assert summary is not None
    assert summary.file_count == 2
    assert "IMAGES/system.img" in summary.notable_files


def test_extraction_rejects_a_preplanted_tree_link(tmp_path):
    source = tmp_path / "clean.zip"
    with zipfile.ZipFile(source, "w") as output:
        output.writestr("IMAGES/system.img", b"system")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Linked tree").project_id, source)
    service = RomInspectionService(store)
    service.inspect_project(project.project_id)
    parent = store.working_root / project.project_id
    parent.mkdir(parents=True)
    outside = tmp_path / "outside-tree"
    outside.mkdir()
    tree = parent / "tree"
    tree.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ProjectError, match="already exists or is unsafe"):
        service.extract_project_tree(project.project_id)

    assert tuple(outside.iterdir()) == ()
    assert service.summarize_working_tree(project.project_id) is None


def test_service_stages_direct_payload_with_verified_progress(tmp_path):
    content = b"CrAU" + b"p" * (5 * 1024 * 1024)
    source = tmp_path / "downloaded-firmware.bin"
    source.write_bytes(content)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Direct payload").project_id, source)
    service = RomInspectionService(store)
    report = service.inspect_project(project.project_id)
    updates: list[int] = []

    tree = service.extract_project_tree(
        project.project_id,
        progress=lambda done, total: updates.append(round(done * 100 / total)),
    )

    assert report.container is ContainerKind.ANDROID_PAYLOAD
    assert (tree / "payload.bin").read_bytes() == content
    assert service.extraction_budget(project.project_id, report).expected_bytes == len(content)
    assert updates == sorted(updates)
    assert updates[-1] == 100
    assert any(0 < value < 100 for value in updates)


def test_service_preserves_original_partition_name_for_direct_sparse_super(tmp_path):
    content = struct.pack("<I", 0xED26FF3A) + b"s" * 4096
    source = tmp_path / "super.img"
    source.write_bytes(content)
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Direct super").project_id, source)
    service = RomInspectionService(store)

    report = service.inspect_project(project.project_id)
    tree = service.extract_project_tree(project.project_id)

    assert report.source_name == "super.img"
    assert report.partition_signals == ("super",)
    assert (tree / "super.img").read_bytes() == content


def test_service_refuses_unidentified_direct_binary_workspace(tmp_path):
    source = tmp_path / "mystery.bin"
    source.write_bytes(b"not a recognized Android container")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Unknown binary").project_id, source)

    with pytest.raises(ProjectError, match="no confirmed Android partition role"):
        RomInspectionService(store).extract_project_tree(project.project_id)


def test_inspection_and_extraction_report_real_monotonic_progress(tmp_path):
    source = tmp_path / "progress.zip"
    with zipfile.ZipFile(source, "w") as output:
        output.writestr("IMAGES/system.img", b"s" * (5 * 1024 * 1024))
        output.writestr("IMAGES/product.img", b"p" * (3 * 1024 * 1024))
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Progress")
    store.import_original(project.project_id, source)
    service = RomInspectionService(store)
    inspection_updates: list[int] = []
    extraction_updates: list[int] = []

    service.inspect_project(
        project.project_id,
        progress=lambda done, total: inspection_updates.append(round(done * 100 / total)),
    )
    service.extract_project_tree(
        project.project_id,
        progress=lambda done, total: extraction_updates.append(round(done * 100 / total)),
    )

    assert inspection_updates[-1] == 100
    assert extraction_updates[-1] == 100
    assert inspection_updates == sorted(inspection_updates)
    assert extraction_updates == sorted(extraction_updates)
    assert any(0 < value < 100 for value in extraction_updates)


def test_service_blocks_unsafe_zip_extraction(tmp_path):
    source = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(source, "w") as output:
        output.writestr("../outside", b"unsafe")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Blocked extraction")
    store.import_original(project.project_id, source)
    with pytest.raises(ProjectError, match="critical structure findings"):
        RomInspectionService(store).extract_project_tree(project.project_id)


def test_adaptive_budget_accepts_a_large_factory_ota_when_space_is_available():
    gib = 1024 * 1024 * 1024

    budget = RomInspectionService.calculate_extraction_budget(
        expected_bytes=9_121_315_072,
        source_bytes=9_121_317_293,
        free_bytes=633 * gib,
    )

    assert budget.safe
    assert "verified" in budget.reason.casefold()
    assert budget.reserve_bytes >= 4 * gib


def test_extraction_budget_rejects_unbound_report_input(tmp_path):
    source = tmp_path / "budget.zip"
    with zipfile.ZipFile(source, "w") as output:
        output.writestr("payload.bin", b"payload")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Budget evidence").project_id, source)
    service = RomInspectionService(store)
    report = service.inspect_project(project.project_id)

    with pytest.raises(ProjectError, match="unavailable or unsafe"):
        service.extraction_budget(project.project_id, replace(report, source_name="other.zip"))


def test_adaptive_budget_blocks_low_disk_space_with_clear_requirement():
    gib = 1024 * 1024 * 1024

    budget = RomInspectionService.calculate_extraction_budget(
        expected_bytes=9 * gib,
        source_bytes=8 * gib,
        free_bytes=10 * gib,
    )

    assert not budget.safe
    assert "requires" in budget.reason.casefold()
    assert "available" in budget.reason.casefold()


def test_adaptive_budget_keeps_anti_zip_bomb_ratio_guard():
    gib = 1024 * 1024 * 1024

    budget = RomInspectionService.calculate_extraction_budget(
        expected_bytes=120 * gib,
        source_bytes=1 * gib,
        free_bytes=500 * gib,
    )

    assert not budget.safe
    assert "ratio" in budget.reason.casefold()
