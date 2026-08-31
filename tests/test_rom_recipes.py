import hashlib
import json
import os

import pytest

from romverse.rom.models import ProjectError
from romverse.rom.recipes import (
    RecipeDraft,
    RecipeDraftStore,
    RecipeExecutor,
    RecipeRollbackReceipt,
    RecipeStep,
    RecipeStore,
    RomRecipe,
    load_run_receipt,
    preview_recipe,
    preview_recipe_changes,
    save_rollback_receipt,
    save_run_receipt,
)


def _test_payload_digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def test_recipe_draft_store_round_trips_private_source_bound_state(tmp_path):
    workspace = tmp_path / "workspace"
    project_dir = workspace / "projects" / "draft-project-12345678"
    project_dir.mkdir(parents=True)
    store = RecipeDraftStore(project_dir, workspace)
    draft = RecipeDraft(
        1,
        "draft-project-12345678",
        "a" * 64,
        "",
        4,
        "Tune build identity",
        "Keep a resumable reviewed change",
        "set_property",
        "system/build.prop",
        "",
        "ro.romverse.mode",
        "guided",
        False,
        False,
        (RecipeStep("step-1", "inspect", "system/build.prop"),),
    )

    sealed = store.save(draft)
    loaded = store.load(draft.project_id, draft.source_original_sha256)

    assert loaded == sealed
    assert len(sealed.record_digest) == 64
    assert not loaded.remove_acknowledged
    if os.name != "nt":
        assert store.path.stat().st_mode & 0o777 == 0o600


def test_recipe_draft_store_rejects_tampering_wrong_source_links_and_unsafe_targets(tmp_path):
    workspace = tmp_path / "workspace"
    project_dir = workspace / "projects" / "draft-project-12345678"
    project_dir.mkdir(parents=True)
    store = RecipeDraftStore(project_dir, workspace)
    draft = RecipeDraft(
        1,
        "draft-project-12345678",
        "b" * 64,
        "",
        1,
        "Inspect",
        "",
        "inspect",
        "",
        "",
        "",
        "",
        False,
        False,
        (),
    )
    store.save(draft)

    assert store.load(draft.project_id, "c" * 64) is None
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    payload["name"] = "Altered after sealing"
    store.path.write_text(json.dumps(payload), encoding="utf-8")
    assert store.load(draft.project_id, draft.source_original_sha256) is None

    external = tmp_path / "redirected.json"
    external.write_text(json.dumps(payload), encoding="utf-8")
    store.path.unlink()
    store.path.symlink_to(external)
    assert store.load(draft.project_id, draft.source_original_sha256) is None

    unsafe = RecipeDraft(
        1,
        draft.project_id,
        draft.source_original_sha256,
        "",
        2,
        "Unsafe",
        "",
        "inspect",
        "../../outside",
        "",
        "",
        "",
        False,
        False,
        (),
    )
    with pytest.raises(ProjectError, match="invalid or unbounded"):
        RecipeDraftStore(project_dir, workspace).save(unsafe)


def test_recipe_store_round_trips_locked_recipe(tmp_path):
    recipe = RomRecipe(
        1,
        "debloat",
        "Safe debloat",
        "Describe removals",
        (RecipeStep("one", "remove_package", "com.example"),),
    )
    store = RecipeStore()
    store.save(tmp_path, recipe)
    loaded = store.load(tmp_path)
    assert loaded is not None
    assert loaded.digest() == recipe.digest()
    assert loaded.persistence_schema_version == 2
    assert loaded.execution_locked
    payload = json.loads((tmp_path / RecipeStore.NAME).read_text(encoding="utf-8"))
    assert payload["persistence_schema_version"] == 2
    assert len(payload["record_digest"]) == 64
    if os.name != "nt":
        assert (tmp_path / RecipeStore.NAME).stat().st_mode & 0o777 == 0o600


def test_recipe_store_reads_strict_legacy_manifest_then_resaves_schema_two(tmp_path):
    recipe = RomRecipe(
        1,
        "legacy",
        "Legacy Recipe",
        "Read-compatible historical evidence",
        (RecipeStep("one", "inspect", "system/build.prop"),),
    )
    legacy = {
        "format": "romverse.recipe",
        "schema_version": 1,
        "recipe_id": recipe.recipe_id,
        "name": recipe.name,
        "description": recipe.description,
        "steps": [
            {
                "step_id": "one",
                "operation": "inspect",
                "target": "system/build.prop",
                "parameters": [],
            }
        ],
        "execution_locked": True,
        "recipe_digest": recipe.digest(),
    }
    path = tmp_path / RecipeStore.NAME
    path.write_text(json.dumps(legacy), encoding="utf-8")

    loaded = RecipeStore().load(tmp_path)

    assert loaded is not None
    assert loaded.persistence_schema_version == 1
    RecipeStore().save(tmp_path, loaded)
    upgraded = RecipeStore().load(tmp_path)
    assert upgraded is not None
    assert upgraded.persistence_schema_version == 2
    assert upgraded.digest() == recipe.digest()


def test_recipe_store_rejects_tampering_extra_fields_links_and_oversized_records(tmp_path):
    recipe = RomRecipe(
        1,
        "strict",
        "Strict Recipe",
        "Reject malformed storage",
        (RecipeStep("one", "inspect", "system/build.prop"),),
    )
    store = RecipeStore()
    path = store.save(tmp_path, recipe)

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["name"] = "Changed after sealing"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert store.load(tmp_path) is None

    store.save(tmp_path, recipe)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected_authority"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert store.load(tmp_path) is None

    store.save(tmp_path, recipe)
    outside = tmp_path.parent / f"{tmp_path.name}-redirected-recipe.json"
    outside.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.unlink()
    path.symlink_to(outside)
    assert store.load(tmp_path) is None
    path.unlink()

    path.write_bytes(b"{" + b"x" * RecipeStore.MAX_BYTES)
    assert store.load(tmp_path) is None


def test_recipe_store_rejects_unsafe_targets_and_unlocked_manifests(tmp_path):
    unsafe = RomRecipe(
        1,
        "unsafe",
        "Unsafe",
        "",
        (RecipeStep("one", "inspect", "../../protected-original"),),
    )
    with pytest.raises(ProjectError, match="invalid, unsafe, or unbounded"):
        RecipeStore().save(tmp_path, unsafe)

    unlocked = RomRecipe(
        1,
        "unlocked",
        "Unlocked",
        "",
        (RecipeStep("one", "inspect", "system/build.prop"),),
        False,
    )
    with pytest.raises(ProjectError, match="invalid, unsafe, or unbounded"):
        RecipeStore().save(tmp_path, unlocked)


def test_recipe_store_rejects_empty_recipe(tmp_path):
    try:
        RecipeStore().save(tmp_path, RomRecipe(1, "empty", "Empty", "", ()))
    except ProjectError:
        pass
    else:
        raise AssertionError("empty recipe should be rejected")


def test_recipe_store_rejects_duplicate_step_ids(tmp_path):
    recipe = RomRecipe(
        1,
        "duplicate",
        "Duplicate",
        "",
        (RecipeStep("same", "inspect", "x"), RecipeStep("same", "inspect", "y")),
    )
    try:
        RecipeStore().save(tmp_path, recipe)
    except ProjectError as exc:
        assert "unique" in str(exc)
    else:
        raise AssertionError("duplicate step IDs should be rejected")


def test_recipe_store_rejects_unknown_operation(tmp_path):
    recipe = RomRecipe(1, "unknown", "Unknown", "", (RecipeStep("step", "shell", "target"),))
    try:
        RecipeStore().save(tmp_path, recipe)
    except ProjectError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("unknown operation should be rejected")


def test_recipe_preview_resolves_targets_without_mutation(tmp_path):
    (tmp_path / "system.img").write_bytes(b"system")
    recipe = RomRecipe(
        1,
        "preview",
        "Preview",
        "",
        (RecipeStep("a", "inspect", "system.img"), RecipeStep("b", "inspect", "missing.img")),
    )
    preview = preview_recipe(recipe, tmp_path)
    assert preview.matched_targets == ("system.img",)
    assert preview.unresolved_targets == ("missing.img",)
    assert preview.execution_locked


def test_recipe_change_preview_shows_bounded_property_diff_without_mutation(tmp_path):
    target = tmp_path / "build.prop"
    target.write_text("ro.foo=old\nro.keep=yes\n", encoding="utf-8")
    recipe = RomRecipe(
        1,
        "preview-change",
        "Preview change",
        "",
        (
            RecipeStep(
                "property",
                "set_property",
                "build.prop",
                (("key", "ro.foo"), ("value", "new")),
            ),
        ),
    )

    preview = preview_recipe_changes(recipe, tmp_path)[0]

    assert preview.changed
    assert "-ro.foo=old" in preview.detail
    assert "+ro.foo=new" in preview.detail
    assert target.read_text(encoding="utf-8") == "ro.foo=old\nro.keep=yes\n"


def test_recipe_change_preview_describes_replace_and_remove(tmp_path):
    target = tmp_path / "target.bin"
    target.write_bytes(b"old")
    removable = tmp_path / "system" / "Demo.apk"
    removable.parent.mkdir()
    removable.write_bytes(b"package")
    replacement = tmp_path / "replacement.bin"
    replacement.write_bytes(b"new bytes")
    recipe = RomRecipe(
        1,
        "preview-multiple",
        "Preview multiple",
        "",
        (
            RecipeStep(
                "replace",
                "replace_file",
                "target.bin",
                (("source", str(replacement)),),
            ),
            RecipeStep("remove", "remove_package", "system/Demo.apk"),
        ),
    )

    previews = preview_recipe_changes(recipe, tmp_path)

    assert [item.changed for item in previews] == [True, True]
    assert "Before:" in previews[0].detail
    assert "Rollback coverage" in previews[1].detail
    assert target.read_bytes() == b"old"
    assert removable.exists()


def test_recipe_executor_preview_is_read_only_for_all_step_types(tmp_path):
    (tmp_path / "system.img").write_bytes(b"system")
    safe = RomRecipe(1, "safe", "Safe", "", (RecipeStep("a", "inspect", "system.img"),))
    assert RecipeExecutor().execute(safe, tmp_path).matched_targets == ("system.img",)
    approval = RecipeExecutor.issue_approval(safe, tmp_path)
    assert approval.recipe_digest == safe.digest()
    assert len(approval.approval_token) == 64
    blocked = RomRecipe(
        1, "blocked", "Blocked", "", (RecipeStep("a", "remove_package", "system.img"),)
    )
    assert RecipeExecutor().execute(blocked, tmp_path).matched_targets == ("system.img",)
    assert (tmp_path / "system.img").read_bytes() == b"system"


def test_replace_file_requires_approval_and_creates_backup(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    target = tree / "system.img"
    target.write_bytes(b"old")
    source = tmp_path / "replacement.img"
    source.write_bytes(b"new")
    recipe = RomRecipe(
        1,
        "replace",
        "Replace",
        "",
        (RecipeStep("step", "replace_file", "system.img", (("source", str(source)),)),),
        False,
    )
    executor = RecipeExecutor()
    try:
        executor.apply_replace_file(recipe, tree, tmp_path / "backup")
    except ProjectError as exc:
        assert "approval" in str(exc)
    else:
        raise AssertionError("replace_file should require approval")
    executor.apply_replace_file(
        recipe, tree, tmp_path / "backup", approved=True, approval_digest=recipe.digest()
    )
    assert target.read_bytes() == b"new"
    assert (tmp_path / "backup" / "system.img").read_bytes() == b"old"


def test_set_property_updates_text_target_with_backup(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    target = tree / "build.prop"
    target.write_text("ro.foo=old\n", encoding="utf-8")
    recipe = RomRecipe(
        1,
        "prop",
        "Property",
        "",
        (RecipeStep("step", "set_property", "build.prop", (("key", "ro.foo"), ("value", "new"))),),
        False,
    )
    receipt = RecipeExecutor().apply_set_property(
        recipe, tree, tmp_path / "backup", True, recipe.digest()
    )
    assert "ro.foo=new" in target.read_text(encoding="utf-8")
    assert (tmp_path / "backup" / "build.prop").read_text(encoding="utf-8") == "ro.foo=old\n"
    assert receipt.success


def test_approved_multi_step_recipe_snapshots_verifies_and_rolls_back(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    prop = tree / "system" / "build.prop"
    prop.parent.mkdir()
    prop.write_text("ro.romverse=old\n", encoding="utf-8")
    removable = tree / "system" / "app" / "Demo" / "Demo.apk"
    removable.parent.mkdir(parents=True)
    removable.write_bytes(b"old package")
    target = tree / "vendor" / "etc" / "feature.conf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old feature")
    replacement = tmp_path / "replacement.conf"
    replacement.write_bytes(b"new feature")
    recipe = RomRecipe(
        1,
        "complete-run",
        "Complete run",
        "",
        (
            RecipeStep(
                "property",
                "set_property",
                "system/build.prop",
                (("key", "ro.romverse"), ("value", "new")),
            ),
            RecipeStep(
                "replace",
                "replace_file",
                "vendor/etc/feature.conf",
                (("source", str(replacement)),),
            ),
            RecipeStep("remove", "remove_package", "system/app/Demo"),
        ),
    )
    executor = RecipeExecutor()
    approval = executor.issue_approval(recipe, tree)
    snapshot_root = tmp_path / "snapshots"
    progress: list[tuple[int, int]] = []
    terminal_receipt_state = []

    def report_progress(done: int, total: int) -> None:
        progress.append((done, total))
        if done >= total:
            terminal_receipt_state.append(
                bool(tuple(snapshot_root.glob("*/execution-receipt.romverse")))
            )

    receipt = executor.execute_approved(
        recipe,
        tree,
        snapshot_root,
        approval,
        report_progress,
    )

    assert receipt.success
    assert receipt.rollback_available
    assert progress == [(1, 3), (2, 3), (3, 3)]
    assert terminal_receipt_state == [True]
    assert "ro.romverse=new" in prop.read_text(encoding="utf-8")
    assert target.read_bytes() == b"new feature"
    assert not removable.exists()
    snapshots = executor.list_snapshots(tmp_path / "snapshots")
    assert len(snapshots) == 1
    rollback = executor.rollback(tree, snapshots[0], snapshots[0].snapshot_digest)
    assert rollback.success
    assert prop.read_text(encoding="utf-8") == "ro.romverse=old\n"
    assert target.read_bytes() == b"old feature"
    assert removable.read_bytes() == b"old package"


def test_recipe_run_receipt_is_private_strict_and_bound_to_recipe_snapshot_and_tree(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    target = tree / "system" / "build.prop"
    target.parent.mkdir()
    target.write_text("ro.romverse=old\n", encoding="utf-8")
    recipe = RomRecipe(
        1,
        "strict-run",
        "Strict run",
        "",
        (
            RecipeStep(
                "property",
                "set_property",
                "system/build.prop",
                (("key", "ro.romverse"), ("value", "new")),
            ),
        ),
    )
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    snapshot_root = tmp_path / "snapshots"
    executor = RecipeExecutor()
    receipt = executor.execute_approved(
        recipe,
        tree,
        snapshot_root,
        executor.issue_approval(recipe, tree),
    )

    path = save_run_receipt(
        project_dir,
        receipt,
        recipe=recipe,
        tree_root=tree,
        snapshot_root=snapshot_root,
    )
    loaded = load_run_receipt(
        project_dir,
        recipe=recipe,
        tree_root=tree,
        snapshot_root=snapshot_root,
    )

    assert loaded == receipt
    assert receipt.schema_version == 2
    assert len(receipt.receipt_digest) == 64
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
        snapshot = snapshot_root / receipt.snapshot_id / "snapshot.romverse"
        assert snapshot.stat().st_mode & 0o777 == 0o600

    original = path.read_bytes()
    payload = json.loads(original)
    payload["steps"][0]["target"] = "vendor/build.prop"
    unsigned = dict(payload)
    unsigned.pop("receipt_digest")
    payload["receipt_digest"] = _test_payload_digest(unsigned)
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert (
        load_run_receipt(
            project_dir,
            recipe=recipe,
            tree_root=tree,
            snapshot_root=snapshot_root,
        )
        is None
    )

    path.write_bytes(original)
    payload = json.loads(original)
    payload["unexpected"] = "cannot weaken the receipt"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_run_receipt(project_dir) is None

    path.write_bytes(original)
    outside = tmp_path / "outside-receipt.json"
    outside.write_bytes(original)
    path.unlink()
    path.symlink_to(outside)
    assert load_run_receipt(project_dir) is None

    path.unlink()
    path.write_bytes(b"{" + b" " * (256 * 1024) + b"}")
    assert load_run_receipt(project_dir) is None


def test_recipe_snapshot_rejects_tamper_links_oversize_and_backup_rebinding(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    target = tree / "system" / "app" / "Demo.apk"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"protected original bytes")
    recipe = RomRecipe(
        1,
        "snapshot-guard",
        "Snapshot guard",
        "",
        (RecipeStep("remove", "remove_package", "system/app/Demo.apk"),),
    )
    snapshot_root = tmp_path / "snapshots"
    executor = RecipeExecutor()
    receipt = executor.execute_approved(
        recipe,
        tree,
        snapshot_root,
        executor.issue_approval(recipe, tree),
    )
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    save_run_receipt(
        project_dir,
        receipt,
        recipe=recipe,
        tree_root=tree,
        snapshot_root=snapshot_root,
    )
    snapshot_dir = snapshot_root / receipt.snapshot_id
    manifest = snapshot_dir / "snapshot.romverse"
    original = manifest.read_bytes()
    snapshot = RecipeExecutor.load_snapshot(snapshot_dir, boundary=snapshot_root)
    assert snapshot is not None

    payload = json.loads(original)
    payload["tree_root"] = str(tmp_path / "different-tree")
    unsigned = dict(payload)
    unsigned.pop("format")
    unsigned.pop("snapshot_digest")
    payload["snapshot_digest"] = _test_payload_digest(unsigned)
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    assert (
        load_run_receipt(
            project_dir,
            recipe=recipe,
            tree_root=tree,
            snapshot_root=snapshot_root,
        )
        is None
    )

    manifest.write_bytes(original)
    outside = tmp_path / "outside-snapshot.json"
    outside.write_bytes(original)
    manifest.unlink()
    manifest.symlink_to(outside)
    assert RecipeExecutor.load_snapshot(snapshot_dir, boundary=snapshot_root) is None

    manifest.unlink()
    manifest.write_bytes(b"{" + b" " * (256 * 1024) + b"}")
    assert RecipeExecutor.load_snapshot(snapshot_dir, boundary=snapshot_root) is None

    manifest.write_bytes(original)
    backup = snapshot_dir / "files" / "system" / "app" / "Demo.apk"
    external = tmp_path / "forged-backup.apk"
    external.write_bytes(b"forged")
    backup.unlink()
    backup.symlink_to(external)
    with pytest.raises(ProjectError, match="links"):
        executor.rollback(tree, snapshot, snapshot.snapshot_digest)
    assert not target.exists()


def test_strict_schema_one_inspection_receipt_remains_readable(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    target = tree / "system.img"
    target.write_bytes(b"system")
    recipe = RomRecipe(
        1,
        "legacy-inspection",
        "Legacy inspection",
        "",
        (RecipeStep("inspect", "inspect", "system.img"),),
    )
    executor = RecipeExecutor()
    receipt = executor.execute_approved(
        recipe,
        tree,
        tmp_path / "snapshots",
        executor.issue_approval(recipe, tree),
    )
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    payload = {
        "format": "romverse.recipe-receipt",
        "schema_version": 1,
        "run_id": receipt.run_id,
        "started_at": receipt.started_at,
        "completed_at": receipt.completed_at,
        "recipe_digest": receipt.recipe_digest,
        "tree_before_sha256": receipt.tree_before_sha256,
        "tree_after_sha256": receipt.tree_after_sha256,
        "snapshot_id": "",
        "snapshot_digest": "",
        "steps": [
            {
                "step_id": item.step_id,
                "operation": item.operation,
                "target": item.target,
                "before_sha256": item.before_sha256,
                "after_sha256": item.after_sha256,
                "changed": item.changed,
            }
            for item in receipt.steps
        ],
        "rollback_available": False,
        "success": True,
    }
    (project_dir / "latest-recipe-receipt.romverse").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    loaded = load_run_receipt(project_dir, recipe=recipe, tree_root=tree)

    assert loaded is not None
    assert loaded.schema_version == 1
    assert loaded.receipt_digest == ""


def test_recipe_rollback_receipt_is_private_atomic_and_rejects_linked_target(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    receipt = RecipeRollbackReceipt(
        "20260830T120000-abcdef12",
        "a" * 64,
        ("system/app/Demo.apk",),
        "b" * 64,
        True,
    )

    path = save_rollback_receipt(project_dir, receipt)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["format"] == "romverse.recipe-rollback"
    assert len(payload["receipt_digest"]) == 64
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600

    outside = tmp_path / "outside-rollback.json"
    outside.write_text("{}", encoding="utf-8")
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(ProjectError, match="stored safely"):
        save_rollback_receipt(project_dir, receipt)


def test_recipe_failure_automatically_restores_affected_target(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    target = tree / "system" / "app" / "Demo.apk"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"must survive")
    recipe = RomRecipe(
        1,
        "transaction",
        "Transaction",
        "",
        (
            RecipeStep("remove", "remove_package", "system/app/Demo.apk"),
            RecipeStep("inspect-after-remove", "inspect", "system/app/Demo.apk"),
        ),
    )
    executor = RecipeExecutor()
    approval = executor.issue_approval(recipe, tree)
    try:
        executor.execute_approved(recipe, tree, tmp_path / "snapshots", approval)
    except ProjectError as exc:
        assert "restored" in str(exc)
    else:
        raise AssertionError("recipe should fail when a later target disappears")
    assert target.read_bytes() == b"must survive"


def test_recipe_approval_binds_tree_and_replacement_content(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    target = tree / "target.bin"
    target.write_bytes(b"old")
    replacement = tmp_path / "replacement.bin"
    replacement.write_bytes(b"approved")
    recipe = RomRecipe(
        1,
        "bound",
        "Bound",
        "",
        (
            RecipeStep(
                "replace",
                "replace_file",
                "target.bin",
                (("source", str(replacement)),),
            ),
        ),
    )
    executor = RecipeExecutor()
    approval = executor.issue_approval(recipe, tree)
    replacement.write_bytes(b"changed after approval")
    try:
        executor.execute_approved(recipe, tree, tmp_path / "snapshots", approval)
    except ProjectError as exc:
        assert "inputs changed" in str(exc)
    else:
        raise AssertionError("changed replacement should invalidate approval")
    assert target.read_bytes() == b"old"


def test_recipe_rejects_target_traversal_before_snapshot(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"private")
    recipe = RomRecipe(
        1,
        "escape",
        "Escape",
        "",
        (RecipeStep("remove", "remove_package", "../outside.bin"),),
    )
    try:
        RecipeExecutor.issue_approval(recipe, tree)
    except ProjectError as exc:
        assert "contained relative path" in str(exc)
    else:
        raise AssertionError("path traversal should be rejected")
    assert outside.read_bytes() == b"private"
