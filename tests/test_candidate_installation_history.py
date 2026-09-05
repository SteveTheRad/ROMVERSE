"""Historical candidate evidence remains local, exact and explicitly unverified."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from types import SimpleNamespace

import pytest

from romverse.guardian.source_installation import (
    SourceInstallationError,
    _digest,
    validate_source_installation_boot_binding,
)
from romverse.rom.projects import RomProjectStore
from romverse.rom.source_installation_history import load_latest_source_installation
from tests.test_guardian_candidate_installation import candidate as candidate
from tests.test_guardian_candidate_installation import execute, preview
from tests.test_source_installation_history import _boot
from tests.test_source_installation_integration import installation as installation


def load(candidate):
    return load_latest_source_installation(candidate.store, candidate.recipe.project_id)


def document(result):
    return json.loads(result.receipt_path.read_text())


def save(path, record):
    record.pop("record_digest", None)
    record["record_digest"] = _digest(record)
    path.write_text(json.dumps(record))


def test_candidate_history_belongs_only_to_build_project_and_rehydrates_exact_result(candidate):
    result = execute(candidate, preview(candidate, reboot=False))
    outcome = load(candidate)
    assert outcome.project_id == candidate.recipe.project_id
    assert outcome.source_sha256 == candidate.recipe.source_sha256
    assert outcome.state == "completed"
    assert outcome.expected_count == outcome.completed_count == 52
    assert outcome.summary.startswith("Historical rebuilt-candidate installation:")
    assert outcome.historical and not outcome.current_artifact_bytes_verified
    assert outcome.result == result
    assert outcome.result.boot_verified is False
    assert load_latest_source_installation(candidate.store, candidate.base.project_id) is None
    binding = validate_source_installation_boot_binding(
        candidate.flash, candidate.phone.device(), outcome.result
    )
    assert binding["record_digest"] == document(result)["record_digest"]
    assert (
        binding["relative_path"]
        == result.receipt_path.relative_to(candidate.store.workspace).as_posix()
    )


def test_reopening_history_never_calls_services_phone_or_rehashes_and_does_not_change_files(
    candidate, monkeypatch
):
    execute(candidate)
    before = {
        path: path.stat().st_mtime_ns
        for path in candidate.store.workspace.rglob("*")
        if path.is_file()
    }

    def forbidden(*_args, **_kwargs):
        raise AssertionError(
            "Read-only history must not run preparation, hashing or phone commands"
        )

    monkeypatch.setattr(candidate.service, "verify", forbidden)
    monkeypatch.setattr(candidate.installation.source, "prepare", forbidden)
    monkeypatch.setattr(candidate.phone, "run", forbidden)
    monkeypatch.setattr(candidate.flash, "_hash_file", forbidden)
    monkeypatch.setattr(candidate.store, "verify_original", forbidden)
    outcome = load(candidate)
    assert outcome.state == "completed" and outcome.historical
    assert not outcome.current_artifact_bytes_verified
    assert before == {
        path: path.stat().st_mtime_ns
        for path in candidate.store.workspace.rglob("*")
        if path.is_file()
    }


def test_current_build_source_change_does_not_show_prior_candidate_as_current(
    candidate, monkeypatch
):
    execute(candidate)
    get = candidate.store.get

    def changed(project_id):
        project = get(project_id)
        return (
            replace(project, original=replace(project.original, sha256="e" * 64))
            if project_id == candidate.recipe.project_id
            else project
        )

    monkeypatch.setattr(candidate.store, "get", changed)
    assert load(candidate) is None


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-provenance",
        "unknown-format",
        "original-label",
        "version",
        "build-receipt",
        "base-receipt",
        "avb-receipt",
        "procedure-source",
        "image-hash",
        "snapshot-hash",
        "fallback",
        "traversal",
        "wrong-build-output",
        "same-project",
        "authority",
        "extra-field",
    ],
)
def test_forged_or_unknown_candidate_evidence_never_rehydrates_as_original_source(
    candidate, mutation
):
    result = execute(candidate, preview(candidate, reboot=False))
    record = document(result)
    payload = record["candidate_provenance"]
    if mutation == "missing-provenance":
        record.pop("candidate_provenance")
    elif mutation == "unknown-format":
        record["format"] = "romverse.future-candidate-installation"
    elif mutation == "original-label":
        record["format"] = "romverse.source-installation"
    elif mutation == "version":
        payload["composition_version"] = 2
    elif mutation in {"build-receipt", "base-receipt", "avb-receipt", "procedure-source"}:
        field = {
            "build-receipt": "build_receipt_digest",
            "base-receipt": "base_receipt_digest",
            "avb-receipt": "avb_receipt_digest",
            "procedure-source": "procedure_source_sha256",
        }[mutation]
        payload[field] = "f" * 64
    elif mutation == "image-hash":
        payload["images"][-3]["sha256"] = "f" * 64
    elif mutation == "snapshot-hash":
        record["image_snapshots"][-3]["sha256"] = "f" * 64
        record["image_snapshots"][-3]["relative_path"] = (
            f"guardian/source-installation/images/{result.receipt_path.stem}/{'f' * 64}.img"
        )
    elif mutation == "fallback":
        payload["origins"][-3].update(source_kind="base-package", relative_path="")
    elif mutation == "traversal":
        payload["origins"][-3]["relative_path"] = "../../super.img"
    elif mutation == "wrong-build-output":
        payload["origins"][-3]["relative_path"] = payload["origins"][-3]["relative_path"].replace(
            payload["project_id"], payload["procedure_project_id"]
        )
    elif mutation == "same-project":
        payload["procedure_project_id"] = payload["project_id"]
    elif mutation == "authority":
        record["production_certification"] = True
    else:
        payload["oem_trusted"] = True
    # Re-seal the outer local digest: the embedded composition still has to be
    # genuine/complete, not an arbitrary dictionary with a valid outer checksum.
    # Structural attacks additionally receive a matching composition checksum.
    if mutation in {
        "version",
        "fallback",
        "traversal",
        "wrong-build-output",
        "same-project",
        "extra-field",
    }:
        record["recipe_digest"] = _digest(payload)
    save(result.receipt_path, record)
    outcome = load(candidate)
    assert outcome.state == "attention"
    assert outcome.result is None
    assert outcome.boot_receipt_path is None
    with pytest.raises(SourceInstallationError):
        validate_source_installation_boot_binding(candidate.flash, candidate.phone.device(), result)


@pytest.mark.parametrize(
    "field,value",
    [("serial", "OTHER-SIMULATED-PHONE"), ("codename", "komodo"), ("manufacturer", "Samsung")],
)
def test_other_phone_cannot_attach_boot_success_to_candidate_history(candidate, field, value):
    result = execute(candidate)
    other = replace(candidate.phone.device(), **{field: value})
    with pytest.raises(SourceInstallationError):
        validate_source_installation_boot_binding(candidate.flash, other, result)


def test_measured_boot_links_candidate_record_but_does_not_certify_images_or_subsystems(candidate):
    result = execute(candidate)
    service, _session, report = _boot(candidate, result, stable=True)
    assert report.boot_observed and report.terminal
    outcome = load(candidate)
    assert outcome.boot_receipt_path == report.receipt_path
    assert outcome.boot_status == "Historical Android boot observed · subsystem checks pending"
    assert outcome.result.boot_verified is False
    assert outcome.historical and not outcome.current_artifact_bytes_verified
    boot = json.loads(report.receipt_path.read_text())
    assert boot["flash_binding"]["record_digest"] == document(result)["record_digest"]
    assert boot["phone_changed"] is False
    assert boot["production_certified"] is False
    service.stop(service.begin(candidate.phone.device(), flash_result=result))
    assert load(candidate).boot_status == "Historical boot check: stopped"


def test_later_failure_or_interrupted_intent_suppresses_earlier_candidate_success(candidate):
    execute(candidate, preview(candidate, reboot=False))
    candidate.phone.fail_partition = "super"
    failed = execute(candidate, preview(candidate, reboot=False))
    assert load(candidate).result == failed
    assert load(candidate).state == "failed"
    plan = preview(candidate, reboot=False)
    path = candidate.executor.root / f"{plan.plan_id}.json"
    save(path, candidate.executor._journal(plan))
    outcome = load(candidate)
    assert outcome.state == "attention"
    assert outcome.result is None
    assert outcome.receipt_path == path


def test_cancelled_before_staging_still_has_exact_candidate_provenance(candidate):
    result = execute(candidate, should_cancel=lambda: True)
    outcome = load(candidate)
    assert outcome.result == result
    assert outcome.state == "cancelled"
    assert not outcome.result.phone_change_attempted
    assert outcome.completed_count == 0
    assert not candidate.phone.changes


def test_candidate_history_and_boot_binding_survive_workspace_relocation_without_absolute_paths(
    candidate, tmp_path
):
    execute(candidate, preview(candidate, reboot=False))
    relocated = tmp_path / "relocated-workspace"
    shutil.copytree(candidate.store.workspace, relocated)
    outcome = load_latest_source_installation(
        RomProjectStore(relocated), candidate.recipe.project_id
    )
    assert outcome.state == "completed"
    assert outcome.receipt_path.is_relative_to(relocated)
    assert not outcome.current_artifact_bytes_verified
    readonly_context = SimpleNamespace(workspace=relocated, privacy=candidate.flash.privacy)
    binding = validate_source_installation_boot_binding(
        readonly_context, candidate.phone.device(), outcome.result
    )
    assert binding["relative_path"] == outcome.receipt_path.relative_to(relocated).as_posix()
