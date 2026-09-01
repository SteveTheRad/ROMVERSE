import zipfile

from romverse.rom.builds import RomBuildPlanner
from romverse.rom.inspection import RomInspectionService
from romverse.rom.projects import RomProjectStore
from romverse.rom.recipes import RecipeStep, RecipeStore, RomRecipe


def test_build_planner_persists_locked_dry_run_plan(tmp_path):
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as output:
        output.writestr("IMAGES/system.img", b"system")
        output.writestr("IMAGES/vendor.img", b"vendor")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Build plan", "generic.android")
    store.import_original(project.project_id, source)
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    inspection.extract_project_tree(project.project_id)
    RecipeStore().save(
        store.projects_root / project.project_id,
        RomRecipe(1, "base", "Base", "", (RecipeStep("inspect", "inspect", "IMAGES/system.img"),)),
    )
    planner = RomBuildPlanner(store)
    plan = planner.plan(project.project_id)
    assert plan.execution_locked
    assert plan.guardian_status == "ready"
    assert plan.guardian_risk == "none"
    assert plan.guardian_manifest_digest
    assert len(plan.tree_sha256) == 64
    assert plan.recipe_digest
    assert plan.partitions == ("system", "vendor")
    assert planner.verify_tree(project.project_id).valid
    (store.working_root / project.project_id / "tree" / "IMAGES" / "system.img").write_bytes(
        b"changed"
    )
    assert not planner.verify_tree(project.project_id).valid
    ready, missing = planner.readiness(project.project_id)
    assert not ready
    assert "Working tree matches build plan" in missing
    assert planner.load(project.project_id) == plan


def test_build_planner_records_symlinks_without_following_them(tmp_path):
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as output:
        output.writestr("system.img", b"system")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Symlink plan")
    store.import_original(project.project_id, source)
    service = RomInspectionService(store)
    service.inspect_project(project.project_id)
    tree = service.extract_project_tree(project.project_id)
    external = tmp_path / "outside"
    external.write_bytes(b"must never be read")
    (tree / "link").symlink_to(external)
    planner = RomBuildPlanner(store)

    plan = planner.plan(project.project_id)

    assert plan.schema_version == 2
    assert plan.input_symlinks == (("link", str(external)),)
    assert "link" not in plan.input_files
    assert planner.verify_tree(project.project_id).valid
    (tree / "link").unlink()
    (tree / "link").symlink_to("different-target")
    verification = planner.verify_tree(project.project_id)
    assert not verification.valid
    assert "symbolic-link set changed" in verification.status


def test_build_planner_refreshes_tree_index_before_deriving_inputs(tmp_path):
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as output:
        output.writestr("IMAGES/system.img", b"system")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Fresh plan").project_id, source)
    service = RomInspectionService(store)
    tree = service.extract_project_tree(project.project_id)
    assert service.cached_working_tree_summary(project.project_id).notable_files == (
        "IMAGES/system.img",
    )

    (tree / "IMAGES" / "vendor.img").write_bytes(b"vendor")
    plan = RomBuildPlanner(store).plan(project.project_id)

    assert plan.partitions == ("system", "vendor")
    assert "IMAGES/vendor.img" in plan.input_files
    refreshed = RomInspectionService(store).cached_working_tree_summary(project.project_id)
    assert refreshed is not None
    assert refreshed.notable_files == ("IMAGES/system.img", "IMAGES/vendor.img")


def test_build_planner_reports_readiness_gates(tmp_path):
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Readiness")
    planner = RomBuildPlanner(store)
    ready, missing = planner.readiness(project.project_id)
    assert not ready
    assert "Protected original imported" in missing
