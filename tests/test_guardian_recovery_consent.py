from __future__ import annotations

import inspect
import json
import os
import stat
from dataclasses import replace
from datetime import UTC, datetime, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QLineEdit

from romverse.core.settings import ExperienceMode
from romverse.guardian.audit import GuardianAuditStore
from romverse.guardian.recovery_consent import (
    GuardianRecoveryConsentGrant,
    GuardianRecoveryConsentReceiptService,
    RecoveryConsentValidationError,
)
from romverse.ui.guardian_center import GuardianCenter
from romverse.ui.recovery_consent import RecoveryConsentDialog
from tests.test_guardian_recovery_live_target import _OBSERVED_AT, _live_context


def _consent_context(tmp_path, monkeypatch):
    live_service, prepared, phone, autopilot, adb, fastboot = _live_context(
        tmp_path,
        monkeypatch,
    )
    live_target = live_service.observe(prepared, phone)
    consent = GuardianRecoveryConsentReceiptService(
        live_service,
        clock=lambda: _OBSERVED_AT + timedelta(seconds=30),
    )
    return consent, live_target, prepared, phone, autopilot, adb, fastboot


def test_recovery_consent_binds_exact_plan_target_and_consequences_without_authority(
    tmp_path, monkeypatch
) -> None:
    service, target, prepared, phone, _autopilot, adb, fastboot = _consent_context(
        tmp_path,
        monkeypatch,
    )
    discovery_calls = (adb.calls, fastboot.discovery_calls, tuple(fastboot.getvar_calls))

    grant = service.issue(prepared, target, phone, confirmed=True)
    receipt = grant.receipt

    assert receipt.preparation_id == prepared.preparation_id
    assert receipt.preparation_digest == prepared.preparation_digest
    assert receipt.live_target_receipt_digest == target.receipt_digest
    assert receipt.incident_id == prepared.incident_id
    assert receipt.route_id == prepared.route_id
    assert receipt.project_id == prepared.project_id
    assert receipt.device_key == prepared.device_key
    assert receipt.source_original_sha256 == prepared.source_original_sha256
    assert receipt.device_pack_id == prepared.device_pack_id
    assert receipt.device_pack_version == prepared.device_pack_version
    assert receipt.device_pack_sha256 == prepared.device_pack_sha256
    assert receipt.steps_digest == prepared.steps_digest
    assert receipt.step_count == len(receipt.consequences) == prepared.step_count
    assert receipt.may_wipe_user_data
    assert receipt.wipe_risk_accepted
    assert receipt.recovery_consent_recorded
    assert receipt.consent_scope_only
    assert not receipt.ephemeral_grant_token_persisted
    assert receipt.execution_authority == "none"
    assert not receipt.automatic_retry_allowed
    assert not receipt.bootloader_relock_allowed
    assert not receipt.runtime_invoked
    assert not receipt.phone_changed
    assert discovery_calls == (adb.calls, fastboot.discovery_calls, tuple(fastboot.getvar_calls))
    service.validate_grant(
        grant,
        prepared,
        target,
        phone,
        now=_OBSERVED_AT + timedelta(seconds=60),
    )

    path = service._path(prepared.incident_id)
    serialized = path.read_text(encoding="utf-8")
    assert phone.serial not in serialized
    assert grant.ephemeral_token not in serialized
    assert "flash" not in serialized
    if os.name != "nt":
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_recovery_consent_decline_expiry_and_substitute_fail_closed(tmp_path, monkeypatch) -> None:
    service, target, prepared, phone, _autopilot, *_rest = _consent_context(
        tmp_path,
        monkeypatch,
    )

    with pytest.raises(RecoveryConsentValidationError, match="declined"):
        service.issue(prepared, target, phone, confirmed=False)
    assert not service._path(prepared.incident_id).exists()

    with pytest.raises(RecoveryConsentValidationError, match="current exact"):
        service.issue(
            prepared,
            target,
            replace(phone, serial="same-model-substitute"),
            confirmed=True,
        )

    service.clock = lambda: _OBSERVED_AT + timedelta(seconds=121)
    with pytest.raises(RecoveryConsentValidationError, match="current exact"):
        service.issue(prepared, target, phone, confirmed=True)
    assert not service._path(prepared.incident_id).exists()


def test_recovery_consent_rejects_incident_drift_and_bad_memory_token(
    tmp_path, monkeypatch
) -> None:
    service, target, prepared, phone, autopilot, *_rest = _consent_context(
        tmp_path,
        monkeypatch,
    )
    grant = service.issue(prepared, target, phone, confirmed=True)
    bad = GuardianRecoveryConsentGrant(grant.receipt, "0" * 64)
    with pytest.raises(RecoveryConsentValidationError, match="token"):
        service.validate_grant(bad, prepared, target, phone)

    autopilot.record_route_result(
        prepared.incident_id,
        prepared.route_id,
        "reviewed",
        "The incident changed after Recovery consent.",
    )
    assert service.load(prepared, target, phone) is None
    with pytest.raises(RecoveryConsentValidationError, match="current and exact"):
        service.validate_grant(grant, prepared, target, phone)


def test_recovery_consent_load_rejects_tamper_extra_duplicate_and_link(
    tmp_path, monkeypatch
) -> None:
    service, target, prepared, phone, _autopilot, *_rest = _consent_context(
        tmp_path,
        monkeypatch,
    )
    service.issue(prepared, target, phone, confirmed=True)
    path = service._path(prepared.incident_id)
    original = path.read_text(encoding="utf-8")

    document = json.loads(original)
    document["execution_authority"] = "recovery"
    path.write_text(json.dumps(document), encoding="utf-8")
    assert service.load(prepared, target, phone) is None

    document = json.loads(original)
    document["unexpected"] = True
    path.write_text(json.dumps(document), encoding="utf-8")
    assert service.load(prepared, target, phone) is None

    duplicate = original.replace(
        '"schema_version": 1,',
        '"schema_version": 1, "schema_version": 1,',
        1,
    )
    assert duplicate != original
    path.write_text(duplicate, encoding="utf-8")
    assert service.load(prepared, target, phone) is None

    if os.name != "nt":
        ordinary = path.with_name("ordinary-recovery-consent.json")
        ordinary.write_text(original, encoding="utf-8")
        path.unlink()
        path.symlink_to(ordinary.name)
        assert service.load(prepared, target, phone) is None


def test_recovery_consent_service_has_no_executor_or_mutation_surface() -> None:
    names = set(dir(GuardianRecoveryConsentReceiptService))
    forbidden = {
        "consume",
        "erase",
        "execute",
        "flash",
        "reboot",
        "relock",
        "restore",
        "retry",
        "set_active",
        "unlock",
        "wipe",
    }

    assert names.isdisjoint(forbidden)
    source = inspect.getsource(GuardianRecoveryConsentReceiptService)
    assert "subprocess" not in source
    assert "fastboot." not in source
    assert "adb." not in source


def test_recovery_consent_dialog_is_one_readable_decision_without_typed_code(
    tmp_path, monkeypatch
) -> None:
    QApplication.instance() or QApplication([])
    _service, target, prepared, _phone, _autopilot, *_rest = _consent_context(
        tmp_path,
        monkeypatch,
    )
    dialog = RecoveryConsentDialog(prepared, target)
    try:
        copy = "\n".join(item.text() for item in dialog.findChildren(QLabel))
        assert dialog.windowTitle() == "Confirm this Recovery plan"
        assert dialog.minimumWidth() >= 720
        assert "THIS PLAN MAY ERASE USER DATA" in copy
        assert "Recording consent does not start Recovery" in copy
        assert "Restore the exact source-bound stock package" in copy
        assert "bootloader relocking is prohibited" in copy
        assert dialog.confirm_button.text() == "I understand — record consent"
        assert not dialog.findChildren(QLineEdit)
    finally:
        dialog.close()


def test_guardian_records_one_recovery_consent_but_starts_no_action(tmp_path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    live_service, prepared, phone, autopilot, _adb, _fastboot = _live_context(
        tmp_path,
        monkeypatch,
    )
    live_service.clock = lambda: datetime.now(UTC)
    incident = autopilot.load(prepared.incident_id)
    route = next(item for item in incident.routes if item.route_id == prepared.route_id)
    queued = []
    monkeypatch.setattr("romverse.ui.guardian_center.start_background", queued.append)
    monkeypatch.setattr(
        "romverse.ui.guardian_center.RecoveryConsentDialog.exec",
        lambda _dialog: QDialog.DialogCode.Accepted,
    )
    center = GuardianCenter(GuardianAuditStore(live_service.store.workspace), auto_start=False)
    try:
        assert center.open_recovery_review(incident, route, prepared, live_service, phone)
        queued.pop().run()
        app.processEvents()
        assert center.recovery_consent_button.isEnabled()

        center.recovery_consent_button.click()
        grant = center.recovery_consent_grant
        assert grant is not None
        assert grant.receipt.execution_authority == "none"
        assert "RECOVERY CONSENT RECORDED" in center.recovery_target_status.text()
        assert "No Recovery action started" in center.recovery_target_status.text()
        assert not center.recovery_consent_button.isEnabled()
        assert not grant.receipt.runtime_invoked
        assert not grant.receipt.phone_changed

        center.set_experience_mode(ExperienceMode.EXPERT)
        assert grant.receipt.receipt_digest[:20] in center.recovery_target_status.text()
        assert "Execution: none" in center.recovery_target_status.text()
        center.set_experience_mode(ExperienceMode.GUIDED)
        assert "No Recovery action started" in center.recovery_target_status.text()

        center._recovery_target_expiry_timer.stop()
        center._expire_recovery_target_receipt()
        assert center.recovery_consent_grant is None
        assert not center.recovery_consent_button.isEnabled()
        assert "PHONE CHECK EXPIRED" in center.recovery_target_status.text()
    finally:
        center.close()


def test_guardian_declined_recovery_dialog_records_nothing(tmp_path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    live_service, prepared, phone, autopilot, _adb, _fastboot = _live_context(
        tmp_path,
        monkeypatch,
    )
    live_service.clock = lambda: datetime.now(UTC)
    incident = autopilot.load(prepared.incident_id)
    route = next(item for item in incident.routes if item.route_id == prepared.route_id)
    queued = []
    monkeypatch.setattr("romverse.ui.guardian_center.start_background", queued.append)
    monkeypatch.setattr(
        "romverse.ui.guardian_center.RecoveryConsentDialog.exec",
        lambda _dialog: QDialog.DialogCode.Rejected,
    )
    center = GuardianCenter(GuardianAuditStore(live_service.store.workspace), auto_start=False)
    try:
        assert center.open_recovery_review(incident, route, prepared, live_service, phone)
        queued.pop().run()
        app.processEvents()
        exact_status = center.recovery_target_status.text()
        center.recovery_consent_button.click()

        assert center.recovery_consent_grant is None
        assert center.recovery_target_status.text() == exact_status
        assert center.recovery_consent_button.isEnabled()
        consent_path = (
            live_service.store.workspace
            / "diagnostics"
            / "recovery-preparations"
            / prepared.incident_id
            / GuardianRecoveryConsentReceiptService.LATEST_NAME
        )
        assert not consent_path.exists()
    finally:
        center.close()
