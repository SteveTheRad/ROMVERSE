"""Mixed-origin transport tests: tiny real files, inert phone, no hardware proof."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import fields, replace
from pathlib import PurePosixPath
from types import SimpleNamespace

import pytest

from romverse.guardian.local_flash import LocalFlashState
from romverse.guardian.source_installation import (
    SourceInstallationError,
    SourceInstallationExecutor,
    _digest,
)
from romverse.rom.candidate_installation import (
    CandidateImageOrigin,
    CandidateInstallationRecipe,
    candidate_composition_payload,
)
from romverse.rom.source_installation import SourceInstallationRecipe
from tests.test_source_installation_integration import (
    _actual_changes,
    _expected_changes,
)
from tests.test_source_installation_integration import (
    installation as installation,
)


def seal_recipe(recipe):
    return replace(recipe, recipe_digest=_digest(candidate_composition_payload(recipe)))


@pytest.fixture
def candidate(installation, tmp_path):
    """An explicit synthetic composition oracle, not genuine AVB/base validation.

    The production composition service has its own integration tests. This fake
    only establishes the reviewed recipe, so these tests independently exercise
    runtime fresh-byte validation even if an upstream verifier misses drift.
    """
    store = installation.source.store
    ota = tmp_path / "inert-build-ota.zip"
    ota.write_bytes(b"INERT BUILD OTA SOURCE IDENTITY ONLY")
    project = store.import_original(store.create("SIMULATION rebuilt OTA").project_id, ota)
    base = installation.recipe()
    output = store.working_root / project.project_id / "build-candidates" / ("c" * 32)
    output.mkdir(parents=True)
    built_bytes, origins, images = {}, [], []
    for image in base.images:
        role = PurePosixPath(image.member).stem
        if role in {"super", "vbmeta_system"}:
            contents = (f"INERT SOURCE INSTALLATION IMAGE REBUILT {role}\n".encode()) * 7
            path = output / f"{role}.img"
            path.write_bytes(contents)
            built_bytes[role] = contents
            image = replace(
                image,
                sha256=hashlib.sha256(contents).hexdigest(),
                size_bytes=len(contents),
                expanded_size_bytes=len(contents),
            )
            origins.append(
                CandidateImageOrigin(
                    image.member, "rebuilt", path.relative_to(store.workspace).as_posix()
                )
            )
        else:
            origins.append(CandidateImageOrigin(image.member, "base-package", ""))
        images.append(image)
    values = {item.name: getattr(base, item.name) for item in fields(SourceInstallationRecipe)}
    values.update(
        project_id=project.project_id, source_sha256=project.original.sha256, images=tuple(images)
    )
    recipe = seal_recipe(
        CandidateInstallationRecipe(
            **values,
            composition_version=1,
            procedure_project_id=base.project_id,
            procedure_source_sha256=base.source_sha256,
            procedure_recipe_digest=base.recipe_digest,
            base_receipt_digest="1" * 64,
            build_receipt_digest="2" * 64,
            build_plan_digest="3" * 64,
            build_pack_sha256="4" * 64,
            build_recipe_digest="",
            build_toolchain_digest="",
            avb_receipt_digest="5" * 64,
            origins=tuple(origins),
        )
    )

    class ReviewedComposition:
        def verify(self, reviewed):
            # Intentionally no rebuilt byte check: the runtime must independently
            # preserve exactly the two reviewed inputs, with no archive fallback.
            installation.source.verify(
                installation.recipe(wipe=reviewed.wipe, reboot=reviewed.reboot)
            )
            if seal_recipe(reviewed).recipe_digest != reviewed.recipe_digest:
                raise SourceInstallationError("Synthetic reviewed composition changed")
            return reviewed

    service = ReviewedComposition()
    executor = SourceInstallationExecutor(service, installation.flash, installation.adb)
    return SimpleNamespace(
        recipe=recipe,
        base=base,
        executor=executor,
        installation=installation,
        phone=installation.phone,
        flash=installation.flash,
        adb=installation.adb,
        store=store,
        built_bytes=built_bytes,
        output=output,
        service=service,
    )


def preview(candidate, **choices):
    if choices:
        base = candidate.installation.recipe(**choices)
        recipe = seal_recipe(
            replace(
                candidate.recipe,
                steps=base.steps,
                wipe=base.wipe,
                reboot=base.reboot,
                procedure_recipe_digest=base.recipe_digest,
            )
        )
    else:
        recipe = candidate.recipe
    return candidate.executor.inspect(candidate.phone.device(), recipe)


def execute(candidate, plan=None, **kwargs):
    plan = plan or preview(candidate)
    return candidate.executor.execute(
        plan, accepted_digest=plan.plan_digest, risk_accepted=True, **kwargs
    )


@pytest.mark.parametrize(
    "wipe,reboot", [(False, True), (True, True), (False, False), (True, False)]
)
def test_exact_two_replacements_preserve_all_other_bytes_and_declared_order(
    candidate, wipe, reboot
):
    plan = preview(candidate, wipe=wipe, reboot=reboot)
    result = execute(candidate, plan)
    assert result.state is LocalFlashState.COMPLETED
    assert _actual_changes(candidate.phone) == _expected_changes(wipe=wipe, reboot=reboot)
    assert candidate.phone.slot == "a"  # The reviewed procedure starts with slot B.
    written = dict(candidate.phone.written)
    assert len(written) == 50
    assert written["super"] == candidate.built_bytes["super"]
    assert written["vbmeta_system_a"] == candidate.built_bytes["vbmeta_system"]
    for image in candidate.base.images:
        role = PurePosixPath(image.member).stem
        if role not in candidate.built_bytes:
            assert hashlib.sha256(written[role + "_a"]).hexdigest() == image.sha256
    assert not any("lock" in command for command in candidate.phone.changes)
    assert not result.boot_verified
    document = json.loads(result.receipt_path.read_text())
    assert document["format"] == "romverse.candidate-installation"
    assert document["project_id"] == candidate.recipe.project_id
    assert document["source_sha256"] == candidate.recipe.source_sha256
    assert (
        document["candidate_provenance"]["procedure_source_sha256"] == candidate.base.source_sha256
    )
    assert document["production_certification"] is False
    assert _digest(document["candidate_provenance"]) == plan.recipe.recipe_digest
    assert str(candidate.store.workspace) not in json.dumps(document)


@pytest.mark.parametrize("role", ["super", "vbmeta_system"])
@pytest.mark.parametrize("drift", ["same-size", "missing", "resized"])
def test_stale_rebuilt_input_stops_before_first_changing_command_without_base_fallback(
    candidate, role, drift
):
    plan = preview(candidate)
    path = candidate.output / f"{role}.img"
    if drift == "missing":
        path.unlink()
    else:
        original = path.read_bytes()
        path.write_bytes(b"X" + original[1:] if drift == "same-size" else original + b"resized")
    result = execute(candidate, plan)
    assert result.state is LocalFlashState.REJECTED
    assert not result.phone_change_attempted
    assert not candidate.phone.changes


@pytest.mark.parametrize("accepted,risk", [("wrong", True), ("correct", False)])
def test_candidate_decline_or_wrong_digest_never_starts(candidate, accepted, risk):
    plan = preview(candidate)
    with pytest.raises(SourceInstallationError, match="Confirm"):
        candidate.executor.execute(
            plan,
            accepted_digest=plan.plan_digest if accepted == "correct" else accepted,
            risk_accepted=risk,
        )
    assert not candidate.phone.changes


def test_failure_does_not_retry_or_continue_child_writes_erase_or_reboot(candidate):
    plan = preview(candidate, wipe=True)
    candidate.phone.fail_partition = "super"
    result = execute(candidate, plan)
    assert result.state is LocalFlashState.FAILED
    assert candidate.phone.changes[-1][:4] == ("-S", "700M", "flash", "super")
    assert [name for name, _contents in candidate.phone.written].count("super") == 1
    assert not any(name == "vbmeta_system_a" for name, _contents in candidate.phone.written)
    assert result.phone_state_uncertain and not result.reboot_requested
    with pytest.raises(SourceInstallationError, match="already used"):
        execute(candidate, plan)


def test_cancel_after_slot_selection_keeps_built_images_private_and_skips_all_writes(
    candidate, monkeypatch
):
    stopped = False

    def stop(_command):
        nonlocal stopped
        stopped = True

    monkeypatch.setattr(candidate.phone, "on_change", stop)
    result = execute(candidate, should_cancel=lambda: stopped)
    assert result.state is LocalFlashState.CANCELLED
    assert candidate.phone.changes == [("set_active", "a")]
    assert not candidate.phone.written


@pytest.mark.parametrize(
    "change",
    [
        "fallback",
        "extra-rebuilt",
        "traversal",
        "absolute",
        "wrong-project",
        "wrong-plan",
        "relock",
        "version",
    ],
)
def test_invalid_composition_roles_or_authority_are_rejected_even_when_resealed(candidate, change):
    recipe = candidate.recipe
    origins = list(recipe.origins)
    if change == "fallback":
        origins[-3] = replace(origins[-3], source_kind="base-package", relative_path="")
    elif change == "extra-rebuilt":
        origins[0] = replace(origins[-3], member=origins[0].member)
    elif change in {"traversal", "absolute", "wrong-project", "wrong-plan"}:
        value = origins[-3].relative_path
        value = {
            "traversal": "../" + value,
            "absolute": "/" + value,
            "wrong-project": value.replace(recipe.project_id, recipe.procedure_project_id),
            "wrong-plan": value.replace("c" * 32, "d" * 32),
        }[change]
        origins[-3] = replace(origins[-3], relative_path=value)
    elif change == "relock":
        recipe = replace(recipe, steps=(*recipe.steps, replace(recipe.steps[0], action="lock")))
    else:
        recipe = replace(recipe, composition_version=2)
    recipe = seal_recipe(replace(recipe, origins=tuple(origins)))
    with pytest.raises(SourceInstallationError):
        candidate.executor.inspect(candidate.phone.device(), recipe)
    assert not candidate.phone.changes


def test_snapshot_uses_expanded_geometry_not_just_file_size(candidate):
    recipe = candidate.recipe
    images = list(recipe.images)
    images[-3] = replace(images[-3], expanded_size_bytes=images[-3].expanded_size_bytes + 4)
    plan = candidate.executor.inspect(
        candidate.phone.device(), seal_recipe(replace(recipe, images=tuple(images)))
    )
    result = execute(candidate, plan)
    assert result.state is LocalFlashState.REJECTED
    assert not candidate.phone.changes


def test_source_input_change_after_all_staging_cannot_change_private_write_bytes(
    candidate, monkeypatch
):
    def change_originals(_command):
        if len(candidate.phone.changes) == 1:
            for role in candidate.built_bytes:
                (candidate.output / f"{role}.img").write_bytes(b"unreviewed changed build input")

    monkeypatch.setattr(candidate.phone, "on_change", change_originals)
    result = execute(candidate)
    assert result.state is LocalFlashState.COMPLETED
    assert dict(candidate.phone.written)["super"] == candidate.built_bytes["super"]
    assert (
        dict(candidate.phone.written)["vbmeta_system_a"] == candidate.built_bytes["vbmeta_system"]
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("unlocked", False),
        ("critical_unlocked", False),
        ("product", "komodo"),
        ("mode", "fastbootd"),
    ],
)
def test_candidate_does_not_relax_device_or_unlock_checks(candidate, field, value):
    plan = preview(candidate)
    setattr(candidate.phone, field, value)
    result = execute(candidate, plan)
    assert result.state is LocalFlashState.REJECTED
    assert not candidate.phone.changes


def test_rebuilt_symlink_never_uses_archive_fallback(candidate, tmp_path):
    plan = preview(candidate)
    target = candidate.output / "super.img"
    other = tmp_path / "outside-super.img"
    target.rename(other)
    try:
        target.symlink_to(other)
    except OSError as exc:
        if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows runner lacks privilege for this real symlink fixture")
        raise
    result = execute(candidate, plan)
    assert result.state is LocalFlashState.REJECTED
    assert not candidate.phone.changes
