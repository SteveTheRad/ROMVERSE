from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from romverse.device.dna import DeviceDnaService
from romverse.nexus.compatibility import (
    CompatibilityMatrixService,
    CompatibilityStatus,
    EvidenceFreshness,
)
from tests.test_device_dna import _device, _project


def test_matrix_distinguishes_verified_strong_unknown_and_incompatible(tmp_path) -> None:
    store, registry, project, report = _project(tmp_path)
    profile = DeviceDnaService(store, registry).refresh(project.project_id, _device(), report)

    service = CompatibilityMatrixService(store)
    matrix = service.assess(profile)
    assert service.matrices.load(project.project_id) == matrix

    partition = matrix.decision("partition_mapping")
    assert partition.status is CompatibilityStatus.VERIFIED
    assert partition.proven_compatible
    assert partition.technically_possible
    assert "exact protected firmware source" in partition.scope

    identity = matrix.decision("device_identity")
    assert identity.status is CompatibilityStatus.STRONG_MATCH
    assert not identity.proven_compatible
    assert identity.technically_possible

    flash = matrix.decision("guardian_flash")
    assert flash.status is CompatibilityStatus.UNKNOWN
    assert not flash.technically_possible

    relock = matrix.decision("bootloader_relock")
    assert relock.status is CompatibilityStatus.KNOWN_INCOMPATIBLE
    assert not relock.technically_possible
    assert not relock.proven_compatible
    assert relock.evidence[0].source_type == "guardian-policy"
    assert matrix.community_telemetry_used is False
    assert matrix.guardian_advisory_only is True
    assert matrix.bootloader_relock_permitted is False
    path = store.projects_root / project.project_id / service.matrices.NAME
    assert json.loads(path.read_text())["schema_version"] == 2
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_matrix_marks_possible_without_claiming_proven_compatibility(tmp_path) -> None:
    store, registry, project, report = _project(tmp_path, exact=False)
    profile = DeviceDnaService(store, registry).refresh(project.project_id, None, report)

    matrix = CompatibilityMatrixService(store).assess(profile)
    build = matrix.decision("rom_build")

    assert build.status is CompatibilityStatus.LIMITED_EVIDENCE
    assert build.technically_possible
    assert not build.proven_compatible
    assert "exact compatibility evidence" in build.warnings[0]


def test_matrix_known_mismatch_informs_guardian_without_bypass(tmp_path) -> None:
    store, registry, project, report = _project(tmp_path)
    profile = DeviceDnaService(store, registry).refresh(
        project.project_id,
        _device(codename="wrong-device", product="wrong-device"),
        report,
    )

    matrix = CompatibilityMatrixService(store).assess(profile)
    identity = matrix.decision("device_identity")

    assert identity.status is CompatibilityStatus.KNOWN_INCOMPATIBLE
    assert not identity.proven_compatible
    assert matrix.guardian_advisory_only


def test_matrix_exposes_evidence_freshness(tmp_path) -> None:
    store, registry, project, report = _project(tmp_path)
    profile = DeviceDnaService(store, registry).refresh(project.project_id, _device(), report)
    created = datetime.fromisoformat(profile.created_at)

    matrix = CompatibilityMatrixService(store).assess(
        profile,
        as_of=created + timedelta(days=181),
    )

    assert matrix.decision("partition_mapping").freshness is EvidenceFreshness.STALE
    assert all(
        evidence.freshness is EvidenceFreshness.STALE
        for evidence in matrix.decision("partition_mapping").evidence
    )


def test_matrix_rejects_tampered_or_stale_persisted_receipts(tmp_path) -> None:
    store, registry, project, report = _project(tmp_path)
    profile = DeviceDnaService(store, registry).refresh(project.project_id, _device(), report)
    service = CompatibilityMatrixService(store)
    service.assess(profile, as_of=datetime.now(UTC))
    path = service.matrices.store.projects_root / project.project_id / service.matrices.NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["decisions"][0]["proven_compatible"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert service.matrices.load(project.project_id) is None


def test_matrix_rejects_redigested_decision_changes_and_hostile_records(tmp_path) -> None:
    store, registry, project, report = _project(tmp_path)
    profile = DeviceDnaService(store, registry).refresh(project.project_id, _device(), report)
    service = CompatibilityMatrixService(store)
    service.assess(profile)
    path = store.projects_root / project.project_id / service.matrices.NAME
    original = path.read_bytes()

    payload = json.loads(original)
    payload["decisions"][0]["proven_compatible"] = not payload["decisions"][0]["proven_compatible"]
    unsigned = {
        key: value for key, value in payload.items() if key not in {"format", "matrix_digest"}
    }
    payload["matrix_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.matrices.load(project.project_id) is None

    payload = json.loads(original)
    payload["unexpected"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.matrices.load(project.project_id) is None

    payload = json.loads(original)
    payload["decisions"][0]["unexpected"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.matrices.load(project.project_id) is None

    payload = json.loads(original)
    payload["guardian_advisory_only"] = "true"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.matrices.load(project.project_id) is None

    path.write_bytes(b"{" + b" " * service.matrices.MAX_BYTES + b"}")
    assert service.matrices.load(project.project_id) is None

    outside = tmp_path / "outside-matrix.json"
    outside.write_bytes(original)
    path.unlink()
    path.symlink_to(outside)
    assert service.matrices.load(project.project_id) is None
    assert outside.read_bytes() == original


def test_legacy_matrix_is_readable_and_assessment_upgrades_schema(tmp_path) -> None:
    store, registry, project, report = _project(tmp_path)
    profile = DeviceDnaService(store, registry).refresh(project.project_id, _device(), report)
    service = CompatibilityMatrixService(store)
    service.assess(profile)
    path = store.projects_root / project.project_id / service.matrices.NAME
    payload = json.loads(path.read_text())
    payload["schema_version"] = 1
    unsigned = {
        key: value for key, value in payload.items() if key not in {"format", "matrix_digest"}
    }
    payload["matrix_digest"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    path.write_text(json.dumps(payload), encoding="utf-8")

    legacy = service.matrices.load(project.project_id)
    assert legacy is not None
    assert legacy.schema_version == 1

    upgraded = service.assess(profile)

    assert upgraded.schema_version == 2
    assert json.loads(path.read_text())["schema_version"] == 2


def test_matrix_invalidates_when_current_device_dna_changes(tmp_path) -> None:
    store, registry, project, report = _project(tmp_path)
    dna_service = DeviceDnaService(store, registry)
    profile = dna_service.refresh(project.project_id, _device(), report)
    matrices = CompatibilityMatrixService(store)
    original = matrices.assess(profile)

    changed = dna_service.refresh(
        project.project_id,
        replace(_device(), security_patch="2026-09-01"),
        report,
    )

    assert changed.profile_digest != original.device_dna_digest
    assert matrices.matrices.load(project.project_id) is None
