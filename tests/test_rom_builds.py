import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from romverse.infrastructure.tools import ToolStatus
from romverse.rom.builds import RomBuildPlanner
from romverse.rom.debloat import DebloatService
from romverse.rom.guided import GuidedMissionState, GuidedMissionStore
from romverse.rom.inspection import RomInspectionService
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore
from romverse.rom.recipes import (
    RecipeExecutor,
    RecipeStep,
    RecipeStore,
    RomRecipe,
    save_run_receipt,
)


def _guided_tool_statuses(store):
    tool_root = store.workspace / "fixture-tools"
    tool_root.mkdir()
    statuses = []
    for name in ("Python", "Payload Dumper", "AVBTool"):
        path = tool_root / f"romverse-fixture-{name.casefold().replace(' ', '-')}"
        path.write_bytes(f"verified {name}".encode())
        statuses.append(ToolStatus(name, True, str(path), "fixture", "Ready"))
    return tuple(statuses)


def _guided_project_with_receipts(tmp_path):
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as output:
        output.writestr("system/build.prop", b"ro.romverse=before\n")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Receipt-bound plan").project_id, source)
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    tree = inspection.extract_project_tree(project.project_id)
    project_dir = store.projects_root / project.project_id
    recipe = RomRecipe(
        1,
        "receipt-bound",
        "Receipt-bound Recipe",
        "Stage 11 regression fixture",
        (
            RecipeStep(
                "property",
                "set_property",
                "system/build.prop",
                (("key", "ro.romverse"), ("value", "after")),
            ),
        ),
    )
    RecipeStore().save(project_dir, recipe)
    executor = RecipeExecutor()
    snapshot_root = store.snapshots_root / project.project_id / "recipes"
    recipe_receipt = executor.execute_approved(
        recipe,
        tree,
        snapshot_root,
        executor.issue_approval(recipe, tree),
    )
    save_run_receipt(
        project_dir,
        recipe_receipt,
        recipe=recipe,
        tree_root=tree,
        snapshot_root=snapshot_root,
    )
    debloat = DebloatService(store)
    scan = debloat.scan(project.project_id)
    debloat_receipt = debloat.apply(debloat.create_plan(scan, ()))
    GuidedMissionStore(project_dir).save(
        GuidedMissionState(
            selected_stage="build_plan",
            recipe_validated=True,
            root_choice="skip",
        )
    )
    planner = RomBuildPlanner(
        store,
        _guided_tool_statuses(store),
        ("Python", "Payload Dumper", "AVBTool"),
    )
    return store, project, planner, recipe, recipe_receipt, debloat_receipt


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


def test_guided_build_plan_binds_source_tools_choices_and_remains_local(tmp_path):
    source = tmp_path / "rom.zip"
    with zipfile.ZipFile(source, "w") as output:
        output.writestr("system/build.prop", b"ro.romverse=verified\n")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.import_original(store.create("Bound plan").project_id, source)
    inspection = RomInspectionService(store)
    inspection.inspect_project(project.project_id)
    inspection.extract_project_tree(project.project_id)
    GuidedMissionStore(store.projects_root / project.project_id).save(
        GuidedMissionState(
            customization_skipped=True,
            recipe_skipped=True,
            root_choice="skip",
        )
    )
    statuses = _guided_tool_statuses(store)
    planner = RomBuildPlanner(
        store,
        tuple(statuses),
        ("Python", "Payload Dumper", "AVBTool"),
    )

    plan = planner.plan(project.project_id)

    assert plan.schema_version == 4
    assert plan.source_sha256 == project.original.sha256
    assert plan.required_tools == ("Python", "Payload Dumper", "AVBTool")
    assert len(plan.toolchain_manifest_digest) == 64
    assert len(plan.guided_choice_digest) == 64
    assert plan.recipe_receipt_digest == ""
    assert plan.debloat_receipt_digest == ""
    assert len(plan.plan_digest) == 64
    assert plan.local_only
    assert not plan.flashable
    assert plan.execution_locked
    assert plan.execution_authority == "none"
    assert planner.load(project.project_id) == plan
    assert planner.verify_tree(project.project_id).valid

    GuidedMissionStore(store.projects_root / project.project_id).save(
        GuidedMissionState(root_choice="ascension")
    )
    assert "choices changed" in planner.verify_tree(project.project_id).status
    GuidedMissionStore(store.projects_root / project.project_id).save(
        GuidedMissionState(
            customization_skipped=True,
            recipe_skipped=True,
            root_choice="skip",
        )
    )
    Path(statuses[0].path).write_bytes(b"changed tool")
    assert "tool evidence changed" in planner.verify_tree(project.project_id).status

    plan_path = store.projects_root / project.project_id / planner.PLAN_NAME
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    payload["flashable"] = True
    plan_path.write_text(json.dumps(payload), encoding="utf-8")
    assert planner.load(project.project_id) is None


def test_guided_build_plan_binds_current_recipe_and_debloat_receipts(tmp_path):
    store, project, planner, _recipe, recipe_receipt, debloat_receipt = (
        _guided_project_with_receipts(tmp_path)
    )

    plan = planner.plan(project.project_id)

    assert plan.schema_version == 4
    assert plan.recipe_receipt_digest == recipe_receipt.receipt_digest
    assert plan.debloat_receipt_digest == debloat_receipt.receipt_digest
    assert planner.load(project.project_id) == plan
    assert planner.verify_tree(project.project_id).valid
    assert plan.execution_authority == "none"
    assert plan.execution_locked and plan.local_only and not plan.flashable


@pytest.mark.parametrize(
    "receipt_name", ["latest-recipe-receipt.romverse", "debloat/latest-receipt.romverse"]
)
def test_guided_build_plan_rejects_missing_required_receipt(tmp_path, receipt_name):
    store, project, planner, _recipe, _recipe_receipt, _debloat_receipt = (
        _guided_project_with_receipts(tmp_path)
    )
    (store.projects_root / project.project_id / receipt_name).unlink()

    with pytest.raises(ProjectError, match="verified .* receipt"):
        planner.plan(project.project_id)

    assert planner.load(project.project_id) is None


@pytest.mark.parametrize(
    "receipt_name", ["latest-recipe-receipt.romverse", "debloat/latest-receipt.romverse"]
)
def test_guided_build_plan_invalidates_deleted_bound_receipt(tmp_path, receipt_name):
    store, project, planner, _recipe, _recipe_receipt, _debloat_receipt = (
        _guided_project_with_receipts(tmp_path)
    )
    planner.plan(project.project_id)
    (store.projects_root / project.project_id / receipt_name).unlink()

    verification = planner.verify_tree(project.project_id)

    assert not verification.valid
    assert "receipt is unavailable, changed, or invalid" in verification.status


@pytest.mark.parametrize(
    "receipt_name", ["latest-recipe-receipt.romverse", "debloat/latest-receipt.romverse"]
)
def test_guided_build_plan_invalidates_tampered_bound_receipt(tmp_path, receipt_name):
    store, project, planner, _recipe, _recipe_receipt, _debloat_receipt = (
        _guided_project_with_receipts(tmp_path)
    )
    planner.plan(project.project_id)
    path = store.projects_root / project.project_id / receipt_name
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["created_at"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")

    verification = planner.verify_tree(project.project_id)

    assert not verification.valid
    assert "receipt is unavailable, changed, or invalid" in verification.status


def test_guided_build_plan_invalidates_replaced_recipe_receipt(tmp_path):
    store, project, planner, recipe, original, _debloat_receipt = (
        _guided_project_with_receipts(tmp_path)
    )
    planner.plan(project.project_id)
    tree = store.working_root / project.project_id / "tree"
    snapshot_root = store.snapshots_root / project.project_id / "recipes"
    executor = RecipeExecutor()
    replacement = executor.execute_approved(
        recipe,
        tree,
        snapshot_root,
        executor.issue_approval(recipe, tree),
    )
    save_run_receipt(
        store.projects_root / project.project_id,
        replacement,
        recipe=recipe,
        tree_root=tree,
        snapshot_root=snapshot_root,
    )

    assert replacement.receipt_digest != original.receipt_digest
    assert not planner.verify_tree(project.project_id).valid


def test_guided_build_plan_invalidates_replaced_debloat_receipt(tmp_path):
    store, project, planner, _recipe, _recipe_receipt, original = (
        _guided_project_with_receipts(tmp_path)
    )
    planner.plan(project.project_id)
    debloat = DebloatService(store)
    replacement = debloat.apply(debloat.create_plan(debloat.scan(project.project_id), ()))

    assert replacement.receipt_digest != original.receipt_digest
    assert not planner.verify_tree(project.project_id).valid


def test_guided_build_plan_receipt_digest_is_covered_by_plan_digest(tmp_path):
    store, project, planner, _recipe, _recipe_receipt, _debloat_receipt = (
        _guided_project_with_receipts(tmp_path)
    )
    planner.plan(project.project_id)
    path = store.projects_root / project.project_id / planner.PLAN_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["recipe_receipt_digest"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert planner.load(project.project_id) is None


def test_legacy_schema3_plan_is_readable_but_cannot_replace_required_receipts(tmp_path):
    store, project, planner, _recipe, _recipe_receipt, _debloat_receipt = (
        _guided_project_with_receipts(tmp_path)
    )
    planner.plan(project.project_id)
    path = store.projects_root / project.project_id / planner.PLAN_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = 3
    payload.pop("recipe_receipt_digest")
    payload.pop("debloat_receipt_digest")
    unsigned = dict(payload)
    unsigned.pop("format")
    unsigned.pop("plan_digest")
    payload["plan_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = planner.load(project.project_id)

    assert loaded is not None and loaded.schema_version == 3
    verification = planner.verify_tree(project.project_id)
    assert not verification.valid
    assert verification.status == "Bound Recipe execution receipt is missing from the build plan"


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
