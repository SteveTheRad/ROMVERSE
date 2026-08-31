from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from romverse.rom.debloat import DebloatRisk, DebloatService
from romverse.rom.models import ProjectError
from romverse.rom.projects import RomProjectStore


def _project(tmp_path):
    source = tmp_path / "firmware.zip"
    source.write_bytes(b"immutable source firmware")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Debloat test")
    store.import_original(project.project_id, source)
    tree = store.working_root / project.project_id / "tree"
    apps = {
        "system/app/FacebookStub/FacebookStub.apk": b"optional partner app",
        "product/app/Notes/Notes.apk": b"unknown notes app",
        "system/priv-app/SystemUI/SystemUI.apk": b"critical system ui",
        "vendor/app/Netflix/Netflix.apk": b"optional streaming app",
        "data/app/UserApp/UserApp.apk": b"not a system image app",
    }
    for relative, content in apps.items():
        target = tree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return store, project, tree, source


def test_scan_classifies_system_apps_and_excludes_user_data(tmp_path):
    store, project, _tree, _source = _project(tmp_path)
    progress: list[int] = []

    scan = DebloatService(store).scan(project.project_id, progress.append)
    by_name = {item.display_name: item for item in scan.candidates}

    assert set(by_name) == {"FacebookStub", "Netflix", "Notes", "SystemUI"}
    assert by_name["FacebookStub"].risk is DebloatRisk.SAFE
    assert by_name["Netflix"].risk is DebloatRisk.SAFE
    assert by_name["Notes"].risk is DebloatRisk.CAUTION
    assert by_name["SystemUI"].risk is DebloatRisk.PROTECTED
    assert by_name["SystemUI"].privileged
    assert progress[0] == 0
    assert progress[-1] == 100
    assert progress == sorted(progress)
    assert any(0 < value < 100 for value in progress)
    assert DebloatService(store).load_scan(project.project_id) == scan
    discovery = DebloatService(store).load_discovery(project.project_id)
    assert discovery is not None
    assert discovery.apk_files_examined == 5
    assert discovery.recognized_apk_files == 4
    assert discovery.candidate_groups == 4
    assert discovery.excluded_apk_files == 1
    assert discovery.partitions == ("product", "system", "vendor")
    assert not discovery.materialization_attempted
    assert not discovery.phone_changed


def test_empty_loose_tree_does_not_create_a_false_completed_scan(tmp_path):
    source = tmp_path / "firmware.zip"
    source.write_bytes(b"immutable source firmware")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Image OTA")
    store.import_original(project.project_id, source)
    (store.working_root / project.project_id / "tree").mkdir(parents=True)

    with pytest.raises(ProjectError, match="filesystem extractors"):
        DebloatService(store).scan(project.project_id)

    assert DebloatService(store).load_scan(project.project_id) is None
    discovery = DebloatService(store).load_discovery(project.project_id)
    assert discovery is not None
    assert discovery.apk_files_examined == 0
    assert discovery.candidate_groups == 0
    assert discovery.materialization_attempted
    assert not discovery.phone_changed


def test_discovery_report_rejects_tampering(tmp_path):
    store, project, _tree, _source = _project(tmp_path)
    service = DebloatService(store)
    service.scan(project.project_id)
    path = store.projects_root / project.project_id / "debloat" / service.DISCOVERY_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["phone_changed"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert service.load_discovery(project.project_id) is None


def test_image_based_ota_is_prepared_and_scanned_before_review(tmp_path):
    source = tmp_path / "firmware.zip"
    source.write_bytes(b"immutable source firmware")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Image OTA")
    store.import_original(project.project_id, source)
    tree = store.working_root / project.project_id / "tree"
    tree.mkdir(parents=True)
    extracted = False

    class Payloads:
        def load(self, _project_id):
            return SimpleNamespace(
                partitions=(
                    SimpleNamespace(
                        name="product",
                        category="Android filesystem",
                        extracted_path="product.img" if extracted else "",
                    ),
                )
            )

        def extract(self, _project_id, selected, progress):
            nonlocal extracted
            assert selected == ("product",)
            extracted = True
            progress(37, 100)
            progress(100, 100)
            return self.load(_project_id)

    class Filesystems:
        def list_manifests(self, _project_id):
            return ()

        def plan(self, _project_id, partition):
            assert partition == "product"
            return SimpleNamespace(safe=True, reason="ready")

        def expand(self, _project_id, partition):
            app = tree / "partition_files" / partition / "root" / "app" / "FacebookStub"
            app.mkdir(parents=True)
            (app / "FacebookStub.apk").write_bytes(b"optional partner app")

    progress = []
    scan = DebloatService(store, Payloads(), Filesystems()).scan(
        project.project_id, progress.append
    )

    assert extracted
    assert len(scan.candidates) == 1
    assert scan.candidates[0].display_name == "FacebookStub"
    assert scan.candidates[0].partition == "product"
    assert scan.candidates[0].risk is DebloatRisk.SAFE
    assert progress == [0, 99, 100]


def test_fastboot_partition_bundle_is_materialized_without_payload_service(tmp_path):
    source = tmp_path / "firmware.tgz"
    source.write_bytes(b"immutable source firmware")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Fastboot image bundle")
    store.import_original(project.project_id, source)
    tree = store.working_root / project.project_id / "tree"
    image = tree / "images" / "product.img"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"contained image")

    class Filesystems:
        def available_partitions(self, _project_id):
            return ("product",)

        def list_manifests(self, _project_id):
            return ()

        def plan(self, _project_id, partition):
            assert partition == "product"
            return SimpleNamespace(safe=True, reason="ready")

        def expand(self, _project_id, partition):
            app = tree / "partition_files" / partition / "root" / "app" / "Netflix"
            app.mkdir(parents=True)
            (app / "Netflix.apk").write_bytes(b"streaming")

    scan = DebloatService(store, None, Filesystems()).scan(project.project_id)

    assert [candidate.display_name for candidate in scan.candidates] == ["Netflix"]
    assert scan.candidates[0].risk is DebloatRisk.SAFE


def test_fastboot_super_is_automatically_unpacked_before_debloat_scan(tmp_path):
    source = tmp_path / "firmware.tgz"
    source.write_bytes(b"immutable source firmware")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Fastboot super")
    store.import_original(project.project_id, source)
    tree = store.working_root / project.project_id / "tree"
    tree.mkdir(parents=True)
    (tree / "super.img").write_bytes(b"contained super")
    unpacked = False

    class Filesystems:
        def available_partitions(self, _project_id):
            return ("product",) if unpacked else ("super",)

        def unpack_super(self, _project_id, allowed, progress):
            nonlocal unpacked
            assert "product" in allowed
            unpacked = True
            progress(1, 2)
            progress(2, 2)
            return ("product",)

        def list_manifests(self, _project_id):
            return ()

        def plan(self, _project_id, partition):
            assert partition == "product"
            return SimpleNamespace(safe=True, reason="ready")

        def expand(self, _project_id, partition):
            app = tree / "partition_files" / partition / "root" / "app" / "Netflix"
            app.mkdir(parents=True)
            (app / "Netflix.apk").write_bytes(b"streaming")

    progress: list[int] = []
    scan = DebloatService(store, None, Filesystems()).scan(
        project.project_id,
        progress.append,
    )

    assert unpacked
    assert [candidate.display_name for candidate in scan.candidates] == ["Netflix"]
    assert progress == [0, 99, 100]


def test_scan_recognizes_nested_partition_roots_and_case_variants(tmp_path):
    source = tmp_path / "firmware.zip"
    source.write_bytes(b"immutable source firmware")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Nested partition layouts")
    store.import_original(project.project_id, source)
    tree = store.working_root / project.project_id / "tree"
    apps = {
        "expanded/system/system/app/FacebookStub/FacebookStub.APK": b"partner",
        "root/product/app/Netflix/Netflix.apk": b"streaming",
        "images/system_ext/root/priv-app/PermissionController/PermissionController.apk": b"core",
        "data/system/app/DoNotTouch/DoNotTouch.apk": b"user data",
    }
    for relative, content in apps.items():
        target = tree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    scan = DebloatService(store).scan(project.project_id)
    by_name = {item.display_name: item for item in scan.candidates}

    assert set(by_name) == {"FacebookStub", "Netflix", "PermissionController"}
    assert by_name["FacebookStub"].partition == "system"
    assert by_name["Netflix"].partition == "product"
    assert by_name["PermissionController"].partition == "system_ext"
    assert by_name["PermissionController"].risk is DebloatRisk.PROTECTED


def test_non_system_apk_does_not_prevent_payload_partition_preparation(tmp_path):
    source = tmp_path / "firmware.zip"
    source.write_bytes(b"immutable source firmware")
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Mixed loose and image apps")
    store.import_original(project.project_id, source)
    tree = store.working_root / project.project_id / "tree"
    user_app = tree / "data" / "app" / "UserApp" / "UserApp.apk"
    user_app.parent.mkdir(parents=True)
    user_app.write_bytes(b"user app")
    extracted = False

    class Payloads:
        def load(self, _project_id):
            return SimpleNamespace(
                partitions=(
                    SimpleNamespace(
                        name="product",
                        category="Android filesystem",
                        extracted_path="product.img" if extracted else "",
                    ),
                )
            )

        def extract(self, _project_id, selected, progress):
            nonlocal extracted
            assert selected == ("product",)
            extracted = True
            progress(1, 1)
            return self.load(_project_id)

    class Filesystems:
        def list_manifests(self, _project_id):
            return ()

        def plan(self, _project_id, partition):
            assert partition == "product"
            return SimpleNamespace(safe=True, reason="ready")

        def expand(self, _project_id, partition):
            app = tree / "partition_files" / partition / "root" / "app" / "Netflix"
            app.mkdir(parents=True)
            (app / "Netflix.apk").write_bytes(b"streaming")

    progress: list[int] = []
    scan = DebloatService(store, Payloads(), Filesystems()).scan(
        project.project_id, progress.append
    )

    assert extracted
    assert [item.display_name for item in scan.candidates] == ["Netflix"]
    assert progress == sorted(progress)
    assert progress[-1] == 100
    discovery = DebloatService(store, Payloads(), Filesystems()).load_discovery(project.project_id)
    assert discovery is not None
    assert discovery.apk_files_examined == 2
    assert discovery.recognized_apk_files == 1
    assert discovery.excluded_apk_files == 1
    assert discovery.materialization_attempted


def test_empty_legacy_receipt_is_not_accepted_as_debloat_completion(tmp_path):
    store, project, _tree, _source = _project(tmp_path)
    service = DebloatService(store)
    scan = service.scan(project.project_id)
    receipt = service.apply(service.create_plan(scan, ()))
    scan_path = store.projects_root / project.project_id / "debloat" / service.SCAN_NAME
    payload = json.loads(scan_path.read_text())
    payload["candidates"] = []
    payload["content_digest"] = hashlib.sha256(b"[]").hexdigest()
    unsigned = {
        key: value for key, value in payload.items() if key not in {"format", "scan_digest"}
    }
    payload["scan_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    scan_path.write_text(json.dumps(payload))

    assert receipt.keep_all
    assert service.load_scan(project.project_id) is None
    assert service.load_receipt(project.project_id) is None


def test_plan_rejects_red_and_requires_orange_confirmation(tmp_path):
    store, project, _tree, _source = _project(tmp_path)
    service = DebloatService(store)
    scan = service.scan(project.project_id)
    by_name = {item.display_name: item for item in scan.candidates}

    with pytest.raises(ProjectError, match="red protected"):
        service.create_plan(scan, (by_name["SystemUI"].candidate_id,))
    with pytest.raises(ProjectError, match="explicit confirmation"):
        service.create_plan(scan, (by_name["Notes"].candidate_id,))

    plan = service.create_plan(
        scan,
        (by_name["FacebookStub"].candidate_id, by_name["Notes"].candidate_id),
        acknowledge_caution=True,
    )
    assert not plan.keep_all
    assert plan.caution_ids == (by_name["Notes"].candidate_id,)


def test_apply_is_reversible_and_never_changes_original_or_phone(tmp_path):
    store, project, tree, source = _project(tmp_path)
    service = DebloatService(store)
    scan = service.scan(project.project_id)
    by_name = {item.display_name: item for item in scan.candidates}
    plan = service.create_plan(
        scan,
        (by_name["FacebookStub"].candidate_id, by_name["Netflix"].candidate_id),
    )
    progress: list[int] = []

    receipt = service.apply(plan, progress.append)

    assert receipt.success and receipt.rollback_available
    assert receipt.removed_app_count == 2
    assert receipt.protected_original_unchanged
    assert not receipt.phone_changed
    assert progress == [100]
    assert not (tree / "system/app/FacebookStub").exists()
    assert not (tree / "vendor/app/Netflix").exists()
    assert (tree / "system/priv-app/SystemUI").is_dir()
    assert source.read_bytes() == b"immutable source firmware"
    assert service.load_receipt(project.project_id) == receipt

    rollback = service.rollback_latest(project.project_id)
    assert rollback.success
    assert (tree / "system/app/FacebookStub/FacebookStub.apk").is_file()
    assert (tree / "vendor/app/Netflix/Netflix.apk").is_file()
    assert service.load_receipt(project.project_id) is None


def test_keep_every_app_records_a_completed_no_change_decision(tmp_path):
    store, project, tree, _source = _project(tmp_path)
    service = DebloatService(store)
    scan = service.scan(project.project_id)
    before = sorted(path.relative_to(tree) for path in tree.rglob("*.apk"))

    receipt = service.apply(service.create_plan(scan, ()))

    assert receipt.success and receipt.keep_all
    assert receipt.removed_app_count == 0
    assert not receipt.rollback_available
    assert sorted(path.relative_to(tree) for path in tree.rglob("*.apk")) == before
    assert service.load_receipt(project.project_id) == receipt


def test_tampered_plan_and_changed_tree_fail_closed(tmp_path):
    store, project, tree, _source = _project(tmp_path)
    service = DebloatService(store)
    scan = service.scan(project.project_id)
    safe = next(item for item in scan.candidates if item.risk is DebloatRisk.SAFE)
    plan = service.create_plan(scan, (safe.candidate_id,))
    plan_path = store.projects_root / project.project_id / "debloat" / service.PLAN_NAME
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    payload["selected_paths"] = ["system/priv-app/SystemUI"]
    plan_path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.load_plan(project.project_id) is None
    with pytest.raises(ProjectError, match="integrity"):
        service.apply(plan)

    plan = service.create_plan(service.scan(project.project_id), (safe.candidate_id,))
    (tree / "product/app/NewApp/NewApp.apk").parent.mkdir(parents=True)
    (tree / "product/app/NewApp/NewApp.apk").write_bytes(b"new")
    with pytest.raises(ProjectError, match="changed after selection"):
        service.apply(plan)
