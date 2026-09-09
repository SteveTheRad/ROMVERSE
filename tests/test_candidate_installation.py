"""Real source/base/build composition, with an explicit AVB boundary test double.

AVB cryptography and transport are exercised by their own suites. This fixture
does not represent a bootable ROM or a physically verified device.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from romverse.device_packs.registry import DevicePackRegistry
from romverse.rom.base_image_compatibility import REQUIRED_PARTITIONS, BaseImageCompatibilityService
from romverse.rom.build_contracts import DeviceBuildContractService
from romverse.rom.build_execution import LocalDeviceBuildExecutor
from romverse.rom.builds import RomBuildPlanner
from romverse.rom.candidate_installation import (
    CandidateInstallationRecipe,
    CandidateInstallationService,
    _composition_digest,
    candidate_composition_payload,
)
from romverse.rom.inspection import RomInspectionService
from romverse.rom.models import ProjectError
from romverse.rom.release_forge import SignedAssemblyInput, SignedAssemblyReceipt
from romverse.rom.signing_ceremony import OfflineSigningReceipt, SignedArtifactEvidence
from tests.test_base_image_compatibility import _fixture as base_fixture
from tests.test_base_image_compatibility import _integer, _partition
from tests.test_build_contracts import _BuildRunner, _executable_tools
from tests.test_build_contracts import _fixture as build_fixture
from tests.test_source_installation import _files


def _sha(value):
    return hashlib.sha256(value).hexdigest()


class _NoCommands:
    def run(self, *_args, **_kwargs):
        pytest.fail("Candidate composition must not issue tool or phone commands.")


class _SizedBuildRunner(_BuildRunner):
    def run(self, args, timeout=10, cwd=None):
        result = super().run(args, timeout=timeout, cwd=cwd)
        if "lpmake" in str(args[0]):
            Path(args[args.index("--output") + 1]).write_bytes(b"N" * 8192)
        return result


class _AvbBoundaryDouble:
    """Only the separate AVB measurement boundary is replaced in this suite."""

    def __init__(self, context, build):
        self.context = context
        self.build = build
        self.receipt = None
        self.prepares = 0
        self.verifies = 0

    def prepare(self, project_id, base):
        assert project_id == self.context.project.project_id
        self.prepares += 1
        hashes = {output.name: output.sha256 for output in self.build.outputs}
        self.receipt = SimpleNamespace(
            receipt_digest=_sha(f"avb-boundary:{base.receipt_digest}".encode()),
            project_id=project_id,
            source_sha256=self.context.project.original.sha256,
            build_receipt_digest=self.build.receipt_digest,
            root_sha256=_sha(self.context.images["images/vbmeta.img"]),
            candidate_super_sha256=hashes["super.img"],
            candidate_vbmeta_system_sha256=hashes["vbmeta_system.img"],
            product_sha256=hashes["product.img"],
            warnings=("Fixture-only AVB boundary; no OEM or boot claim.",),
            base_receipt_digest=base.receipt_digest,
            pack_sha256=self.context.registry.packs[0].sha256,
            contract_digest=base.contract_digest,
            execution_authority="none",
            phone_changed=False,
            oem_trusted=False,
        )
        return self.receipt

    def load(self, project_id):
        assert project_id == self.context.project.project_id
        return self.receipt

    def verify(self, receipt, base):
        self.verifies += 1
        assert receipt is self.receipt
        assert receipt.base_receipt_digest == base.receipt_digest
        return receipt


def _final_evidence(context, build):
    project_id = context.project.project_id
    workspace = context.store.workspace
    build_outputs = {item.name: item for item in build.outputs}
    signing_root = context.store.projects_root / project_id / "signing-evidence" / ("e" * 16)
    signing_root.mkdir(parents=True)
    signed_artifacts = []
    for name in ("product.img", "vbmeta_system.img"):
        output = build_outputs[name]
        source = workspace / output.path
        target = signing_root / name
        shutil.copyfile(source, target)
        current = target.stat()
        signed_artifacts.append(
            SignedArtifactEvidence(
                name,
                target.relative_to(workspace).as_posix(),
                _sha(target.read_bytes()),
                current.st_size,
                current.st_mtime_ns,
                "SHA256_RSA4096",
                "f" * 40,
                42,
                2,
                0,
                ("product", "system"),
            )
        )
    signing = OfflineSigningReceipt(
        2,
        "d" * 32,
        project_id,
        datetime.now(UTC).isoformat(),
        context.registry.packs[0].pack_id,
        context.registry.packs[0].sha256,
        context.registry.packs[0].build_contract.contract_id,
        build.receipt_digest,
        "e" * 64,
        tuple(signed_artifacts),
        True,
        False,
        False,
        "b" * 64,
    )
    assembly_root = (
        workspace / "working_roms" / project_id / "signed-assembly" / (("b" * 16) + "-" + ("a" * 8))
    )
    assembly_root.mkdir(parents=True)
    super_source = workspace / build_outputs["super.img"].path
    super_path = assembly_root / "super.img"
    shutil.copyfile(super_source, super_path)
    product = signed_artifacts[0]
    assembly = SignedAssemblyReceipt(
        1,
        project_id,
        datetime.now(UTC).isoformat(),
        build.receipt_digest,
        signing.receipt_digest,
        (SignedAssemblyInput("product", product.path, product.size_bytes, product.sha256, True),),
        super_path.relative_to(workspace).as_posix(),
        super_path.stat().st_size,
        _sha(super_path.read_bytes()),
        "9" * 64,
        True,
        False,
        "8" * 64,
    )
    return (
        SimpleNamespace(load_receipt=lambda _project_id: signing),
        SimpleNamespace(load_signed_assembly=lambda _project_id, **_kwargs: assembly),
        signing,
        assembly,
    )


def _fixture(tmp_path):
    template_root = tmp_path / "template"
    template_root.mkdir()
    template, template_project, template_registry, _, _, _ = build_fixture(template_root)
    images = _files()
    images["images/super.img"] = b"S" * 8192
    manifest = _integer(12, 0) + b"".join(
        _partition(name, images[f"images/{name}.img"]) for name in REQUIRED_PARTITIONS
    )
    manifest += _partition("product", b"p" * 512) + _partition("system", b"s" * 512)
    context_root = tmp_path / "candidate"
    context_root.mkdir()
    context = base_fixture(context_root, image_contents=images, manifest=manifest)
    store, project = context.store, context.project
    working = store.working_root / project.project_id
    shutil.copytree(template.working_root / template_project.project_id, working)
    (working / "tree" / "payload.bin").write_bytes(context.payload)
    shutil.copytree(
        template.projects_root / template_project.project_id / "rebuild-metadata",
        store.projects_root / project.project_id / "rebuild-metadata",
    )
    manifest_path = store.projects_root / project.project_id / "payload-manifest.romverse"
    manifest_data = json.loads(
        (
            template.projects_root / template_project.project_id / "payload-manifest.romverse"
        ).read_text()
    )
    manifest_data.update(
        project_id=project.project_id,
        source_original_sha256=project.original.sha256,
        payload_sha256=_sha(context.payload),
    )
    for row in manifest_data["partitions"]:
        row["extracted_path"] = row["extracted_path"].replace(
            template_project.project_id, project.project_id
        )
    manifest_path.write_text(json.dumps(manifest_data))
    original_pack = template_registry.packs[0]
    contract = replace(
        original_pack.build_contract,
        source=replace(
            original_pack.build_contract.source,
            archive_sha256=project.original.sha256,
            payload_sha256=_sha(context.payload),
        ),
        top_level_vbmeta_sha256=_sha(images["images/vbmeta.img"]),
    )
    context.registry = DevicePackRegistry(
        (
            replace(
                original_pack,
                pack_id=project.device_pack_id,
                manufacturers=("Xiaomi",),
                product_patterns=("popsicle",),
                build_contract=contract,
            ),
        )
    )
    RomInspectionService(store).inspect_project(project.project_id)
    RomBuildPlanner(store).plan(project.project_id)
    tools = _executable_tools(tmp_path / "tools")
    DeviceBuildContractService(store, context.registry, tools).create_plan(project.project_id)
    build = LocalDeviceBuildExecutor(
        store, context.registry, tools, _SizedBuildRunner(working / "partitions" / "system.img")
    ).execute(project.project_id)
    context.build = build
    context.tools = tools
    context.avb = _AvbBoundaryDouble(context, build)
    signing_service, release_service, context.signing, context.assembly = _final_evidence(
        context, build
    )
    context.service = CandidateInstallationService(
        store,
        context.registry,
        tools,
        _NoCommands(),
        avb_service=context.avb,
        signing_service=signing_service,
        release_service=release_service,
    )
    return context


def _prepare(context, **choices):
    return context.service.prepare(
        context.project.project_id, context.procedure.project_id, **choices
    )


def test_complete_candidate_replaces_exactly_two_roles_and_preserves_all_source_steps(tmp_path):
    context = _fixture(tmp_path)
    recipe = _prepare(context)
    source = context.recipe
    assert isinstance(recipe, CandidateInstallationRecipe)
    assert recipe.steps == source.steps and len(recipe.steps) == 53
    assert recipe.project_id == context.project.project_id
    assert recipe.source_sha256 == context.project.original.sha256
    assert recipe.procedure_project_id == context.procedure.project_id
    assert recipe.procedure_source_sha256 == source.source_sha256
    assert recipe.archive_path == source.archive_path
    assert len(recipe.images) == len(recipe.origins) == 50
    originals = {image.member: image for image in source.images}
    changed = [image for image in recipe.images if image != originals[image.member]]
    assert {image.name for image in changed} == {"super.img", "vbmeta_system.img"}
    assert sum(origin.source_kind == "base-package" for origin in recipe.origins) == 48
    assert sum(origin.source_kind == "signed-final" for origin in recipe.origins) == 2
    for origin in recipe.origins:
        if origin.source_kind == "signed-final":
            path = context.store.workspace / origin.relative_path
            assert path.is_file() and (
                "signed-assembly" in path.parts or "signing-evidence" in path.parts
            )
            assert path.name != "product.img"
        else:
            assert origin.relative_path == ""
    assert recipe.build_receipt_digest == context.build.receipt_digest
    assert recipe.recipe_digest == recipe.composition_digest != source.recipe_digest
    assert any("not a tested release" in warning for warning in recipe.warnings)
    assert any("slot B is not" in warning for warning in recipe.warnings)
    assert not recipe.wipe and recipe.reboot and recipe.requires_critical_unlock


def test_verification_reuses_exact_receipts_without_repreparing_or_changing_saved_base(tmp_path):
    context = _fixture(tmp_path)
    recipe = _prepare(context)
    receipt_path = (
        context.store.projects_root
        / context.project.project_id
        / BaseImageCompatibilityService.RECEIPT_NAME
    )
    before = receipt_path.read_bytes(), receipt_path.stat().st_mtime_ns
    assert context.service.verify(recipe) == recipe
    assert context.service.verify(recipe) == recipe
    assert context.avb.prepares == 1 and context.avb.verifies == 2
    assert (receipt_path.read_bytes(), receipt_path.stat().st_mtime_ns) == before


@pytest.mark.parametrize(
    "wipe,reboot,count",
    [(False, False, 52), (False, True, 53), (True, False, 54), (True, True, 55)],
)
def test_explicit_wipe_reboot_choices_keep_exact_understood_procedure(
    tmp_path, wipe, reboot, count
):
    context = _fixture(tmp_path)
    recipe = _prepare(context, wipe=wipe, reboot=reboot)
    assert len(recipe.steps) == count
    assert [step.partition for step in recipe.steps if step.action == "erase"] == (
        ["metadata", "userdata"] if wipe else []
    )
    assert (recipe.steps[-1].action == "reboot") is reboot
    assert context.service.verify(recipe) == recipe


@pytest.mark.parametrize("name", ["super.img", "vbmeta_system.img", "product.img"])
def test_changed_built_bytes_never_fall_back_even_with_original_mtime(tmp_path, name):
    context = _fixture(tmp_path)
    recipe = _prepare(context)
    output = next(output for output in context.build.outputs if output.name == name)
    path = context.store.workspace / output.path
    before = path.stat()
    path.write_bytes(b"X" * before.st_size)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    with pytest.raises(ProjectError, match="No current verified local build outputs exist"):
        context.service.verify(recipe)


def test_changed_working_tree_requires_new_build_not_new_certificate(tmp_path):
    context = _fixture(tmp_path)
    recipe = _prepare(context)
    tree = context.store.working_root / context.project.project_id / "tree"
    (tree / "new-edit.txt").write_text("after the reviewed build")
    with pytest.raises(ProjectError, match="tree or recipe changed"):
        context.service.verify(recipe)


def test_missing_build_output_does_not_select_original_source_image(tmp_path):
    context = _fixture(tmp_path)
    output = next(output for output in context.build.outputs if output.name == "super.img")
    (context.store.workspace / output.path).rename(context.store.workspace / "retained-super.img")
    with pytest.raises(ProjectError, match="No current verified local build"):
        _prepare(context)


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_sha256", "a" * 64),
        ("build_receipt_digest", "a" * 64),
        ("base_receipt_digest", "a" * 64),
        ("avb_receipt_digest", "a" * 64),
        ("signing_receipt_digest", "a" * 64),
        ("signed_assembly_receipt_digest", "a" * 64),
        ("wipe", True),
        ("reboot", False),
        ("label", "OEM trusted production release"),
    ],
)
def test_changed_review_fields_cannot_reuse_prior_composition(tmp_path, field, value):
    context = _fixture(tmp_path)
    recipe = _prepare(context)
    with pytest.raises(ProjectError, match="review changed"):
        context.service.verify(replace(recipe, **{field: value}))


def test_resealed_invented_image_origin_is_rederived_and_rejected(tmp_path):
    context = _fixture(tmp_path)
    recipe = _prepare(context)
    origins = list(recipe.origins)
    index = next(i for i, item in enumerate(origins) if item.source_kind == "signed-final")
    origins[index] = replace(origins[index], relative_path="working_roms/other/super.img")
    changed = replace(recipe, origins=tuple(origins))
    changed = replace(changed, recipe_digest=_composition_digest(changed))
    with pytest.raises(ProjectError, match="image roles or installation choices changed"):
        context.service.verify(changed)


def test_missing_or_replaced_base_receipt_cannot_regenerate_it_during_review(tmp_path):
    context = _fixture(tmp_path)
    recipe = _prepare(context)
    path = (
        context.store.projects_root / recipe.project_id / BaseImageCompatibilityService.RECEIPT_NAME
    )
    path.write_text("{}")
    before = path.stat().st_mtime_ns
    with pytest.raises(ProjectError, match="base or AVB evidence is missing or changed"):
        context.service.verify(recipe)
    assert path.read_text() == "{}" and path.stat().st_mtime_ns == before


def test_historical_composition_payload_has_no_absolute_archive_path(tmp_path):
    context = _fixture(tmp_path)
    recipe = _prepare(context)
    payload = candidate_composition_payload(recipe)
    assert "archive_path" not in payload and "recipe_digest" not in payload
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert str(context.store.workspace) not in encoded
    assert _sha(encoded.encode()) == recipe.recipe_digest
    relocated = replace(recipe, archive_path=tmp_path / "another-workspace" / "original.zip")
    assert _composition_digest(relocated) == recipe.recipe_digest
    with pytest.raises(ProjectError, match="image roles or installation choices changed"):
        context.service.verify(relocated)
