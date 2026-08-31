import json
import stat
import zipfile

from romverse.rom.builds import RomBuildPlanner
from romverse.rom.dna import DnaStore, derive_dna
from romverse.rom.inspection import RomInspectionService
from romverse.rom.projects import RomProjectStore


def test_rom_dna_is_deterministic_for_project_provenance(tmp_path):
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as output:
        output.writestr("system.img", b"system")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("DNA", "generic.android")
    store.import_original(project.project_id, source)
    service = RomInspectionService(store)
    service.inspect_project(project.project_id)
    service.extract_project_tree(project.project_id)
    RomBuildPlanner(store).plan(project.project_id)
    first = derive_dna(store, project.project_id)
    second = derive_dna(store, project.project_id)
    assert first == second
    assert len(first.fingerprint) == 64
    dna_store = DnaStore()
    path = dna_store.save(store, first)
    assert dna_store.load(store, project.project_id) == first
    assert dna_store.verify(store, project.project_id)
    payload = json.loads(path.read_text())
    assert payload["schema_version"] == 2
    assert len(payload["record_digest"]) == 64
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_rom_dna_rejects_hostile_records_and_stale_provenance(tmp_path):
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as output:
        output.writestr("system.img", b"system")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(
        store.create("Hostile DNA", "generic.android").project_id,
        source,
    )
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    tree = inspection.extract_project_tree(project.project_id)
    RomBuildPlanner(store).plan(project.project_id)
    dna_store = DnaStore()
    dna_store.save(store, derive_dna(store, project.project_id))
    path = store.projects_root / project.project_id / dna_store.NAME
    original = path.read_bytes()

    payload = json.loads(original)
    payload["unexpected"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert dna_store.load(store, project.project_id) is None

    path.write_bytes(b"{" + b" " * dna_store.MAX_BYTES + b"}")
    assert dna_store.load(store, project.project_id) is None

    outside = tmp_path / "outside-rom-dna.json"
    outside.write_bytes(original)
    path.unlink()
    path.symlink_to(outside)
    assert dna_store.load(store, project.project_id) is None
    assert outside.read_bytes() == original

    path.unlink()
    path.write_bytes(original)
    (tree / "system.img").write_bytes(b"changed")
    RomBuildPlanner(store).plan(project.project_id)
    assert dna_store.load(store, project.project_id) is None


def test_legacy_rom_dna_is_readable_and_save_upgrades_schema(tmp_path):
    source = tmp_path / "legacy.zip"
    with zipfile.ZipFile(source, "w") as output:
        output.writestr("system.img", b"system")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(
        store.create("Legacy DNA", "generic.android").project_id,
        source,
    )
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    inspection.extract_project_tree(project.project_id)
    RomBuildPlanner(store).plan(project.project_id)
    dna_store = DnaStore()
    current = derive_dna(store, project.project_id)
    path = dna_store.save(store, current)
    payload = json.loads(path.read_text())
    payload.pop("schema_version")
    payload.pop("record_digest")
    path.write_text(json.dumps(payload), encoding="utf-8")

    legacy = dna_store.load(store, project.project_id)
    assert legacy is not None
    assert legacy.schema_version == 1

    dna_store.save(store, current)

    assert json.loads(path.read_text())["schema_version"] == 2
    assert dna_store.load(store, project.project_id) == current
