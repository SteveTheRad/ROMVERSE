from __future__ import annotations

import json
import os
import stat
from dataclasses import asdict, replace

import pytest

from romverse.device.models import DeviceState
from romverse.guardian.recovery_preparation import (
    GuardianRecoveryPreparationError,
    GuardianRecoveryPreparationService,
)
from romverse.repair.autopilot import (
    RecoveryAutopilotContext,
    RecoveryAutopilotService,
    RecoveryRouteKind,
    RecoveryTrigger,
)
from romverse.rom.recovery_evidence import RecoveryEvidenceService
from tests.test_guardian_execution_plan import _prepared_with_transition_recovery


def _context(tmp_path, monkeypatch):
    plans, project, _report, device, *_rest = _prepared_with_transition_recovery(
        tmp_path, monkeypatch
    )
    source = tmp_path / "firmware.zip"
    recovery_evidence = RecoveryEvidenceService(plans.store)
    recovery_evidence.register(project.project_id, "external_backup", source)
    recovery_evidence.register(project.project_id, "stock_recovery", source)
    phone = replace(
        device,
        state=DeviceState.FASTBOOT,
        boot_completed=False,
        slot_suffix="_a",
        ab_update=True,
        bootloader_locked=False,
    )
    autopilot = RecoveryAutopilotService(plans.store.workspace, plans.registry)
    incident = autopilot.start(
        RecoveryAutopilotContext(
            RecoveryTrigger.BOOTLOOP,
            device=phone,
            project_id=project.project_id,
            recovery_evidence=recovery_evidence.assess(project.project_id, phone),
        )
    )
    route = next(
        item for item in incident.routes if item.kind is RecoveryRouteKind.EXACT_STOCK_RESTORE
    )
    assert route.owner_route == "guardian_core"
    return plans, project, phone, autopilot, incident, route


def test_preparation_binds_current_incident_phone_project_source_pack_and_actions(
    tmp_path, monkeypatch
) -> None:
    plans, project, phone, autopilot, incident, route = _context(tmp_path, monkeypatch)
    service = GuardianRecoveryPreparationService(plans.store, plans.registry, autopilot)

    prepared = service.prepare(incident.incident_id, route.route_id, [phone])

    assert prepared.incident_id == incident.incident_id
    assert prepared.incident_record_digest == incident.record_digest
    assert prepared.route_id == route.route_id
    assert prepared.project_id == project.project_id
    assert prepared.device_key == incident.device_key
    assert prepared.expected_product == phone.product
    assert prepared.expected_entry_mode == "bootloader"
    assert prepared.source_original_sha256 == project.original.sha256
    assert prepared.device_pack_id == incident.pack_id
    assert prepared.device_pack_sha256 == incident.pack_sha256
    assert prepared.focused_operation.value == "restore_stock_package"
    assert prepared.steps[0].operation is prepared.focused_operation
    assert prepared.steps[-1].operation.value == "verify_post_boot"
    assert prepared.may_wipe_user_data
    assert prepared.guardian_validation_required
    assert prepared.user_confirmation_required
    assert prepared.execution_authority == "none"
    assert not prepared.runtime_invoked
    assert not prepared.phone_changed
    assert not prepared.bootloader_relock_allowed
    assert service.load(incident.incident_id, route.route_id, [phone]) == prepared
    path = (
        plans.store.workspace
        / "diagnostics"
        / "recovery-preparations"
        / incident.incident_id
        / service.LATEST_NAME
    )
    assert phone.serial not in path.read_text(encoding="utf-8")
    if os.name != "nt":
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_preparation_rejects_same_model_different_phone_and_stale_incident(
    tmp_path, monkeypatch
) -> None:
    plans, _project, phone, autopilot, incident, route = _context(tmp_path, monkeypatch)
    service = GuardianRecoveryPreparationService(plans.store, plans.registry, autopilot)
    prepared = service.prepare(incident.incident_id, route.route_id, [phone])
    other_phone = replace(phone, serial="different-physical-phone")

    with pytest.raises(GuardianRecoveryPreparationError, match="one exact phone"):
        service.prepare(incident.incident_id, route.route_id, [other_phone])

    autopilot.record_route_result(
        incident.incident_id,
        route.route_id,
        "reviewed",
        "Current route was reviewed after the preparation was sealed.",
    )
    assert service.load(incident.incident_id, route.route_id, [phone]) is None
    assert prepared.execution_authority == "none"


def test_preparation_tampering_fails_strict_validation(tmp_path, monkeypatch) -> None:
    plans, _project, phone, autopilot, incident, route = _context(tmp_path, monkeypatch)
    service = GuardianRecoveryPreparationService(plans.store, plans.registry, autopilot)
    prepared = service.prepare(incident.incident_id, route.route_id, [phone])
    path = (
        plans.store.workspace
        / "diagnostics"
        / "recovery-preparations"
        / incident.incident_id
        / service.LATEST_NAME
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    document["source_original_sha256"] = "9" * 64
    path.write_text(json.dumps(document), encoding="utf-8")

    assert service.load(incident.incident_id, route.route_id, [phone]) is None
    with pytest.raises(GuardianRecoveryPreparationError, match="strict validation"):
        service.validate(replace(prepared, source_original_sha256="9" * 64))
    assert asdict(prepared)["execution_authority"] == "none"


def test_preparation_load_rejects_changed_external_evidence(tmp_path, monkeypatch) -> None:
    plans, _project, phone, autopilot, incident, route = _context(tmp_path, monkeypatch)
    service = GuardianRecoveryPreparationService(plans.store, plans.registry, autopilot)
    prepared = service.prepare(incident.incident_id, route.route_id, [phone])
    source = tmp_path / "firmware.zip"
    source.write_bytes(b"changed after preparation")

    assert service.load(incident.incident_id, route.route_id, [phone]) is None
    assert prepared.execution_authority == "none"
